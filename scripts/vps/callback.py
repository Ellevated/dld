#!/usr/bin/env python3
"""
Module: callback
Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect, write audit log.

Uses:
  - db: release_slot, finish_task, update_project_phase, record_decision, count_demotes_since
  - event_writer: notify, notify_circuit_event
  - lifecycle: read_lifecycle, write_lifecycle  (ADR-023 — sole status writer)
  - subprocess: pueue CLI fallback

Used by:
  - Pueue daemon (pueue.yml callback config)

CLI: python3 callback.py <pueue_id> '<group>' '<result>'
INVARIANT: Always exit 0. Every step in try/except.

TECH-171: _write_audit / _emit_audit append one JSONL line per verify_status_sync call.
Audit log path: $CALLBACK_AUDIT_LOG or scripts/vps/callback-audit.jsonl.
ARCH-186: verify_status_sync writes only to lifecycle.yaml (no markdown edits).
TECH-207: _step6_dispatch_qa_reflect — merge-confirmed QA dispatch fallback.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import event_writer  # noqa: E402
import gate_logic  # noqa: E402 — single source of gate logic (TECH-210)
import lifecycle  # noqa: E402  — atomic YAML writer (ADR-023)

log = logging.getLogger("callback")

# Spec-id regex (TECH-182). `[a-z]*` captures sub-spec suffixes (ARCH-176a/b/c).
# Mirrors orchestrator.scan_backlog regex (v3.15.8).
_SPEC_ID_RE = re.compile(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*")


def _load_env() -> None:
    """Load .env from SCRIPT_DIR. Manual parser."""
    env_file = SCRIPT_DIR / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def _setup_logging() -> None:
    """Append-mode file + stderr logging."""
    log_file = SCRIPT_DIR / "callback-debug.log"
    handler = logging.FileHandler(str(log_file), mode="a")
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(stderr_handler)


def resolve_label(pueue_id: str) -> str:
    """Get task label. DB-first, pueue CLI fallback."""
    # Layer 1: DB (reliable — no socket dependency)
    try:
        row = db.get_task_by_pueue_id(int(pueue_id))
        if row:
            project_id = row["project_id"]
            task_label = row["task_label"]
            if task_label.startswith(f"{project_id}:"):
                label = task_label
            else:
                label = f"{project_id}:{task_label}"
            log.info("resolve_label from DB: %s", label)
            return label
    except Exception as exc:
        log.warning("resolve_label DB failed: %s", exc)

    # Layer 2: pueue CLI (fallback — may fail due to socket mismatch)
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        task = data.get("tasks", {}).get(pueue_id, {})
        label = task.get("label", "unknown") or "unknown"
        if label != "unknown":
            log.info("resolve_label from pueue: %s", label)
        return label
    except Exception:
        return "unknown"


def parse_label(label: str) -> tuple:
    """Split label into (project_id, task_label)."""
    if ":" in label:
        project_id, _, task_label = label.partition(":")
        return project_id, task_label
    log.warning("label '%s' has no colon", label)
    return label, label


def map_result(result: str) -> tuple:
    """Map pueue result string to (status, exit_code)."""
    if "Success" in result:
        return "done", 0
    return "failed", 1


def _find_log_file(project_name: str, after_ts: float = 0.0) -> Path | None:
    """Find most recent log file for project in logs/ dir.

    `after_ts` (Unix epoch) — if given, only return a file whose mtime is
    strictly later. Prevents picking up stale logs from previous tasks when
    the current task's runner was SIGKILL'd before it could write its own.
    """
    log_dir = SCRIPT_DIR / "logs"
    if not log_dir.is_dir():
        return None
    pattern = f"{project_name}-*.log"
    files = sorted(log_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files:
        if f.stat().st_mtime > after_ts:
            return f
    return None


def _skill_from_pueue_command(pueue_id: str) -> tuple[str, float]:
    """Read skill + task start_time from `pueue status --json`.

    Pueue stores the original launch command. Our run-agent.sh signature is:
        run-agent.sh <project_dir> <provider> <skill> <task...>
    So the 4th argv is always the skill.

    This is the only deterministic source of truth for skill on a
    SIGKILL'd run (TIMEOUT_SECONDS) — claude-runner.py never reaches its
    finally-clause to write the JSON log file, so log-file inference picks
    up a stale neighbour's log.

    Returns (skill, start_ts). Both empty/0.0 on failure (caller falls back).
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return "", 0.0
        data = json.loads(r.stdout)
        task = data.get("tasks", {}).get(str(pueue_id), {})
        cmd = task.get("command") or task.get("original_command") or ""
        # Extract 4th token (after run-agent.sh project_dir provider <skill>)
        # Tolerant to absolute / relative path of run-agent.sh.
        parts = cmd.split()
        skill = ""
        for i, p in enumerate(parts):
            if p.endswith("run-agent.sh") and i + 3 < len(parts):
                skill = parts[i + 3]
                break
        # Parse start_ts to filter stale neighbour logs
        start_ts = 0.0
        s = task.get("status", {})
        if isinstance(s, dict):
            inner = s.get("Running") or s.get("Done") or {}
            start_str = inner.get("start") if isinstance(inner, dict) else None
            if start_str:
                try:
                    from datetime import datetime

                    start_ts = datetime.fromisoformat(start_str.replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass
        return skill, start_ts
    except Exception as exc:
        log.warning("_skill_from_pueue_command failed: %s", exc)
        return "", 0.0


def _parse_log_file(log_path: Path) -> tuple:
    """Parse JSON log file → (skill, result_preview, task_status). Logs cache metrics."""
    try:
        data = json.loads(log_path.read_text())
        skill = data.get("skill", "")
        full_preview = str(data.get("result_preview", ""))
        preview = full_preview[:500]

        # task_status resolution (most→least reliable):
        #   1. top-level field — claude-runner._extract_task_status writes it
        #      from the FULL result text (untruncated, format-agnostic).
        #   2. whole-preview JSON — legacy bare-JSON final message.
        #   3. regex scan of full preview — agent wrapped task_status in a
        #      markdown ```json fence (Opus 4.x). Scans full_preview (up to
        #      1000 chars) NOT the 500-char display preview, so the token is
        #      not lost to truncation.
        task_status = str(data.get("task_status", "") or "")
        if not task_status and preview:
            try:
                inner = json.loads(preview)
                task_status = str(inner.get("task_status", "") or "")
            except json.JSONDecodeError:
                pass
        if not task_status and full_preview:
            m = re.search(r'"task_status"\s*:\s*"([a-z_]+)"', full_preview)
            if m:
                task_status = m.group(1)

        input_tokens = int(data.get("input_tokens", 0) or 0)
        output_tokens = int(data.get("output_tokens", 0) or 0)
        cache_creation_input_tokens = int(data.get("cache_creation_input_tokens", 0) or 0)
        cache_read_input_tokens = int(data.get("cache_read_input_tokens", 0) or 0)
        denom = cache_read_input_tokens + input_tokens
        cache_hit_rate = round(cache_read_input_tokens / denom, 4) if denom > 0 else 0.0
        log.info(
            "USAGE %s: in=%d out=%d cache_creation=%d cache_read=%d cache_hit_rate=%.4f",
            log_path.name,
            input_tokens,
            output_tokens,
            cache_creation_input_tokens,
            cache_read_input_tokens,
            cache_hit_rate,
        )

        return skill, preview, task_status
    except Exception:
        return "", "", ""


def extract_agent_output(pueue_id: str, project_id: str = "") -> tuple:
    """Extract skill, result_preview, and task_status.

    Resolution order (skill first, preview second, task_status third):
      0. pueue command — deterministic, survives SIGKILL'd runners
      1. log file (newer than task start) — reliable for clean exits
      2. DB task_log row
      3. pueue raw log
    """
    # Layer 0: skill from pueue command (deterministic, never fooled by stale logs)
    pueue_skill, start_ts = _skill_from_pueue_command(pueue_id)

    # Layer 1: Read from log file (reliable — written by claude-runner.py at end of run)
    if project_id:
        try:
            state = db.get_project_state(project_id)
            if state:
                project_name = Path(state.get("path", "")).name
                if project_name:
                    log_path = _find_log_file(project_name, after_ts=start_ts)
                    if log_path:
                        skill, preview, task_status = _parse_log_file(log_path)
                        # If pueue gave us a skill, trust it over the log file's
                        # (covers edge case of a still-stale log slipping through).
                        if pueue_skill:
                            skill = pueue_skill
                        if skill:
                            log.info("extract_agent_output from log: %s", log_path.name)
                            return skill, preview, task_status
        except Exception as exc:
            log.warning("extract_agent_output log file failed: %s", exc)

    # If log file missing/stale but pueue knew the skill — return it now.
    if pueue_skill:
        log.info("extract_agent_output skill from pueue command: %s", pueue_skill)
        return pueue_skill, "", ""

    # Layer 1b: Try DB task_log for skill (if no log file found)
    try:
        row = db.get_task_by_pueue_id(int(pueue_id))
        if row and row.get("skill"):
            log.info("extract_agent_output skill from DB: %s", row["skill"])
            return row["skill"], "", ""
    except Exception as exc:
        log.warning("extract_agent_output DB failed: %s", exc)

    # Layer 2: pueue log (fallback — may fail due to socket mismatch)
    try:
        result = subprocess.run(
            ["pueue", "log", pueue_id, "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(result.stdout)
        task_data = data.get("tasks", {}).get(pueue_id, {})
        output = task_data.get("output", "")
        if not output:
            output = result.stdout

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{") and '"skill"' in line:
                try:
                    obj = json.loads(line)
                    skill = obj.get("skill", "")
                    preview = str(obj.get("result_preview", ""))[:500]
                    task_status = str(obj.get("task_status", "") or "")
                    return skill, preview, task_status
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return "", "", ""


def resolve_spec_id(task_label: str, preview: str, project_path: str) -> str | None:
    """Multi-layer spec_id resolution."""
    # Layer 1: from task label
    m = _SPEC_ID_RE.search(task_label)
    if m:
        return m.group(0)

    # Layer 2: from preview text
    if preview:
        m = _SPEC_ID_RE.search(preview)
        if m:
            return m.group(0)

    # Layer 3: from inbox done files
    if task_label.startswith("inbox-") and project_path:
        done_dir = Path(project_path) / "ai" / "inbox" / "done"
        if done_dir.is_dir():
            for f in sorted(done_dir.glob("*.md"), reverse=True):
                text = f.read_text(errors="replace")
                m = re.search(r"\*\*SpecID:\*\*\s*(\S+)", text)
                if m:
                    sm = _SPEC_ID_RE.search(m.group(1))
                    if sm:
                        return sm.group(0)
    return None


def is_already_queued(label: str) -> bool:
    """Check if a task with this label is Running or Queued."""
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        for task in data.get("tasks", {}).values():
            if task.get("label") == label:
                status = task.get("status", {})
                if isinstance(status, dict) and ("Running" in status or "Queued" in status):
                    return True
        return False
    except Exception:
        return False


def _pueue_add(group: str, label: str, cmd: list) -> int | None:
    """Submit task to pueue. Returns task ID or None."""
    try:
        pueue_cmd = [
            "pueue",
            "add",
            "--group",
            group,
            "--label",
            label,
            "--print-task-id",
            "--",
        ] + cmd
        result = subprocess.run(
            pueue_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stdout.strip().splitlines():
            m = re.search(r"(\d+)", line.strip())
            if m:
                return int(m.group(1))
        return None
    except Exception:
        return None


def dispatch_qa(project_id: str, project_path: str, spec_id: str, provider: str) -> None:
    """Dispatch QA task via pueue."""
    qa_label = f"{project_id}:qa-{spec_id}"
    if is_already_queued(qa_label):
        log.info("skip duplicate QA: %s", qa_label)
        return
    runner_group = f"{provider}-runner"
    pueue_id = _pueue_add(
        runner_group,
        qa_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_path, provider, "qa", f"/qa {spec_id}"],
    )
    if pueue_id:
        db.try_acquire_slot(project_id, provider, pueue_id)
        db.log_task(project_id, qa_label, "qa", "running", pueue_id)
        log.info("QA dispatched: %s pueue_id=%d", qa_label, pueue_id)
    else:
        log.warning("QA dispatch failed: %s", qa_label)


def dispatch_reflect(project_id: str, project_path: str, task_label: str, provider: str) -> None:
    """Dispatch reflect task via pueue."""
    reflect_label = f"{project_id}:reflect-{task_label}"
    if is_already_queued(reflect_label):
        log.info("skip duplicate reflect: %s", reflect_label)
        return
    runner_group = f"{provider}-runner"
    pueue_id = _pueue_add(
        runner_group,
        reflect_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_path, provider, "reflect", "/reflect"],
    )
    if pueue_id:
        db.try_acquire_slot(project_id, provider, pueue_id)
        db.log_task(project_id, reflect_label, "reflect", "running", pueue_id)
        log.info("reflect dispatched: %s pueue_id=%d", reflect_label, pueue_id)
    else:
        log.warning("reflect dispatch failed: %s", reflect_label)


# --- TECH-166 / TECH-167: Implementation guard helpers ----------------------

# Backticked path-shape: anything between backticks with a dot extension.
# Drops the extension whitelist — Go (.go), Astro (.astro), Terraform (.tf),
# Dockerfile, .env.example, etc. are all valid project files. False positives
# like `foo.bar` are harmless: git log finds no commits and they're ignored.
_ALLOWED_FILE_EXT_RE = re.compile(r"`([^\s`\n]+\.[a-zA-Z][\w-]*)`")

# --- TECH-167 v1 canonical format -------------------------------------------
# Strict heading: "## Allowed Files" (case-sensitive, no suffix, no qualifier).
_ALLOWED_FILES_V1_HEADING_RE = re.compile(r"^##[ \t]+Allowed Files[ \t]*$")
# Marker comment that opts a spec into v1 strict parsing.
_ALLOWED_FILES_V1_MARKER_RE = re.compile(r"<!--\s*callback-allowlist\s+v1\b[^>]*-->")
# Canonical bullet: "- `path/with.ext` optional trailing prose".
_ALLOWED_FILES_V1_BULLET_RE = re.compile(r"^-[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$")
# TECH-208: numbered-list items (e.g. "1. `path/to/file.py` — reason").
_ALLOWED_FILES_V1_NUMBERED_RE = re.compile(
    r"^\d+\.[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$"
)

# --- TECH-166 legacy fallback (kept for specs without the v1 marker) --------
# Heading variants seen across DLD projects (case-insensitive):
#   ## Allowed Files
#   ## Allowed Files (whitelist|canonical|STRICT|...)
#   ## Updated Allowed Files
#   ## Files Allowed to Modify
_ALLOWED_FILES_HEADING_RE = re.compile(
    r"^##\s+(?:(?:Updated\s+)?Allowed\s+Files\b|Files\s+Allowed\s+to\s+Modify\b)",
    re.IGNORECASE,
)
_NEXT_H2_RE = re.compile(r"^##\s+\S")


def _parse_allowed_files_v1(spec_text: str) -> list[str] | None:
    """Strict canonical v1 parser. Returns:

    list[str]: \u22651 paths (success).
    []        : marker present but ZERO valid bullets \u2014 degrade-closed.
    None      : v1 marker not present (caller should try legacy fallback).
    """
    lines = spec_text.splitlines()

    # Locate the canonical heading (must be EXACT \u2014 case-sensitive, no suffix).
    heading_idxs = [i for i, ln in enumerate(lines) if _ALLOWED_FILES_V1_HEADING_RE.match(ln)]
    if not heading_idxs:
        return None  # caller falls back to legacy
    # Use the first canonical heading; section ends at next H2.
    start = heading_idxs[0] + 1
    end = len(lines)
    for j in range(start, len(lines)):
        if _NEXT_H2_RE.match(lines[j]):
            end = j
            break
    section = lines[start:end]
    section_text = "\n".join(section)

    # Marker is the v1 opt-in. Without it, spec is legacy; defer.
    if not _ALLOWED_FILES_V1_MARKER_RE.search(section_text):
        return None

    # Strict mode: canonical dash-bullets AND numbered-list items (TECH-208).
    # No fenced blocks, no backtick-paths outside bullets, no fallback to
    # _ALLOWED_FILE_EXT_RE.
    paths: list[str] = []
    for ln in section:
        m = _ALLOWED_FILES_V1_BULLET_RE.match(ln) or _ALLOWED_FILES_V1_NUMBERED_RE.match(ln)
        if m:
            paths.append(m.group(1))
    # Empty list with marker present = degrade-closed (explicit empty allowlist).
    return paths


def _parse_allowed_files_legacy(spec_text: str) -> list[str] | None:
    """Pre-TECH-167 parser: heading variants + any backticked-path-shape.

    Used only when v1 marker is absent (legacy specs). Same semantics as the
    pre-TECH-167 implementation: section heading match \u2192 extract every
    backticked path inside the section.
    """
    lines = spec_text.splitlines()
    in_section = False
    section_buf: list[str] = []
    for line in lines:
        if not in_section:
            if _ALLOWED_FILES_HEADING_RE.match(line):
                in_section = True
            continue
        if _NEXT_H2_RE.match(line):
            break
        section_buf.append(line)
    if not in_section:
        return None
    return _ALLOWED_FILE_EXT_RE.findall("\n".join(section_buf))


def _parse_allowed_files(spec_path: Path) -> list[str] | None:
    """Extract allowlist for the implementation guard.

    Strategy (TECH-167):
        1. If spec has the v1 marker \u2192 strict canonical parse (no fallback).
        2. Else \u2192 legacy parser (heading variants, any backticked paths).
        3. Section absent entirely \u2192 None (degrade-open sentinel).

    Returns:
        list[str]: explicit list (may be empty if v1 marker present but
                   bullets malformed \u2192 degrade-closed).
        None:      no Allowed Files section at all (legacy spec without
                   any allowlist \u2014 caller decides degrade-open semantics).
    """
    try:
        text = spec_path.read_text(errors="replace")
    except OSError as exc:
        log.warning("ALLOWED_FILES: read failed for %s: %s", spec_path, exc)
        return None

    v1 = _parse_allowed_files_v1(text)
    if v1 is not None:
        log.info(
            "ALLOWED_FILES: v1 canonical parse for %s → %d path(s)",
            spec_path.name,
            len(v1),
        )
        return v1

    legacy = _parse_allowed_files_legacy(text)
    if legacy is not None:
        log.info(
            "ALLOWED_FILES: legacy fallback parse for %s → %d path(s)",
            spec_path.name,
            len(legacy),
        )
    return legacy


def _get_started_at(pueue_id: int) -> str | None:
    """Read started_at for a pueue task from task_log (read-only db access)."""
    try:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT started_at FROM task_log WHERE pueue_id = ? ORDER BY id DESC LIMIT 1",
                (pueue_id,),
            ).fetchone()
            if row is None:
                return None
            return row[0] if not hasattr(row, "keys") else row["started_at"]
    except Exception as exc:  # noqa: BLE001 — defensive (callback must not crash)
        log.warning("ALLOWED_FILES: started_at lookup failed for %s: %s", pueue_id, exc)
        return None


def _audit_log_path() -> Path:
    """Return path to callback-audit.jsonl (from CALLBACK_AUDIT_LOG env or default)."""
    env_val = os.environ.get("CALLBACK_AUDIT_LOG", "")
    if env_val:
        return Path(env_val)
    return SCRIPT_DIR / "callback-audit.jsonl"


def _write_audit(record: dict) -> None:
    """Append one JSON line to the audit log. Atomic: write to tmp, then rename."""
    try:
        audit_path = _audit_log_path()
        line = json.dumps(record, ensure_ascii=False) + "\n"
        # Atomic append: open in append mode (kernel-level atomicity for O_APPEND)
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:  # noqa: BLE001 — must not crash callback
        log.warning("AUDIT: write failed: %s", exc)


def _is_test_path(rel_path: str) -> bool:
    """True if rel_path looks like a test file."""
    p = rel_path.lower()
    return (
        p.startswith("tests/")
        or "/tests/" in p
        or "_test." in p
        or p.endswith("_test.py")
        or p.endswith("_test.ts")
        or p.endswith(".test.ts")
        or p.endswith(".test.js")
        or p.endswith(".spec.ts")
        or p.endswith(".spec.js")
    )


def _commit_stats(
    project_path: str,
    allowed: list[str] | None,
    started_at: str | None,
) -> tuple[int, int, int]:
    """Return (code_loc, test_loc, code_commits) via git log --numstat.

    - code_loc:    total lines added in non-test allowed files.
    - test_loc:    total lines added in test files.
    - code_commits: number of commits that touched non-test allowed files.

    Returns (0, 0, 0) on any error or when guard would degrade-open.
    """
    if not allowed or started_at is None:
        return 0, 0, 0
    cmd = [
        "git",
        "-C",
        project_path,
        "log",
        "--all",
        f"--since={started_at}",
        "--pretty=format:COMMIT",
        "--numstat",
        "--",
        *allowed,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return 0, 0, 0
    if r.returncode != 0:
        return 0, 0, 0

    code_loc = 0
    test_loc = 0
    code_commits = 0
    commit_has_code = False

    for line in r.stdout.splitlines():
        if line.strip() == "COMMIT":
            if commit_has_code:
                code_commits += 1
            commit_has_code = False
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            try:
                added = int(parts[0])
            except ValueError:
                added = 0
            rel_path = parts[2]
            if _is_test_path(rel_path):
                test_loc += added
            else:
                code_loc += added
                if added > 0:
                    commit_has_code = True
    # Flush last commit
    if commit_has_code:
        code_commits += 1

    return code_loc, test_loc, code_commits


def _detect_out_of_scope_files(
    project_path: str,
    spec_id: str,
    allowed: list[str] | None,
    started_at: str | None,
) -> list[str]:
    """Return files touched by spec-attributed commits but NOT in the allowlist.

    BUG-199 Fix C: detection-only (WARNING), not enforcement.
    Inspects commits since started_at whose subject implements spec_id,
    and returns any paths they touched that are NOT in the allowed list.
    """
    if not allowed or not started_at or not spec_id:
        return []
    cmd = [
        "git",
        "-C",
        project_path,
        "log",
        "--all",
        f"--since={started_at}",
        "--pretty=format:%h%x00%s",
        "--name-only",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []

    allowed_set = set(allowed)
    out_of_scope: set[str] = set()
    is_spec_commit = False

    for line in r.stdout.splitlines():
        if "\x00" in line:
            # New commit header: hash\x00subject
            _, _, current_subject = line.partition("\x00")
            is_spec_commit = gate_logic.match_subject(current_subject, spec_id)
        elif line.strip() and is_spec_commit:
            # File path from --name-only
            rel_path = line.strip()
            if rel_path not in allowed_set and not rel_path.startswith("ai/"):
                out_of_scope.add(rel_path)

    return sorted(out_of_scope)


def _subject_implements(subject: str, spec_id: str) -> bool:
    """Return True iff the commit *subject* (first line) declares it implements spec_id.

    TECH-177: Body/footer/trailer mentions DO NOT count. Cross-references in
    body (e.g. `see also FTR-925`, `Refs: FTR-925`) caused false-positive
    auto-close in awardybot 2026-05-04 incident.

    Accepted forms (canonical):
      - Conventional Commits with spec_id in scope (case-insensitive):
          `feat(FTR-925): ...`
          `feat(ftr-925): ...`                # lowercase scope OK (BUG-192)
          `fix(FTR-925)!: ...`
          `feat(FTR-925,FTR-926): ...`        # multi-spec scope
          `chore(area, FTR-925): ...`         # whitespace tolerated
      - Merge commit (branch prefix tolerated, BUG-192; colon/branch/quote
        forms added 2026-07-02 after plpilot TECH-349/BUG-346 false-blocked):
          `merge FTR-925`
          `merge FTR-925: ...`
          `Merge feature/FTR-925: ...`        # branch-prefix form
          `merge: feature/FTR-925 — ...`      # colon after merge
          `Merge branch 'fix/FTR-925-slug'`   # git default merge subject
      - Trailing parenthesized ID at end of subject (2026-07-02, plpilot
        BUG-338/339/340/346/347 false-blocked — coders put the ID in the
        tail, not the scope):
          `fix(security): revoke grants (FTR-925)`
          `fix: truncate safely (FTR-925)`
          `feat: x (FTR-925, FTR-926)`        # multi-spec tail
      - Legacy bare prefix:
          `FTR-925: ...`

    Rejected:
      - body / footer / trailer mentions
      - `feat(other): ... see FTR-925`        # ID after ':' is not a scope
      - `feat: FTR-925 something`             # no scope, ID inside message
      - `fix: x (see FTR-925)`                # tail parens must be IDs only

    Keep in sync with gate_logic.match_subject (L-derived-2, until MP-011).
    """
    if not subject or not spec_id:
        return False
    # Conventional: <type>(<scope>)[!]: <description>
    m = re.match(r"^[a-z]+\(([^)]*)\)!?:", subject)
    if m:
        scopes = [s.strip() for s in m.group(1).split(",")]
        if any(s.strip().upper() == spec_id.upper() for s in scopes):
            return True
    # Merge commit: `merge[:] [branch] ['][prefix/]SPEC-ID`
    if re.match(
        rf"^merge[:\s]\s*(?:branch\s+)?['\"]?(?:\S+/)?{re.escape(spec_id)}\b",
        subject,
        re.IGNORECASE,
    ):
        return True
    # Trailing parenthesized ID(s): `... (SPEC-ID)` / `... (SPEC-A, SPEC-B)`.
    # Every comma-separated element must BE a spec-id-shaped token — free text
    # like `(see SPEC-ID)` stays rejected (TECH-177 body-mention discipline).
    m = re.search(r"\(([^()]*)\)\s*$", subject)
    if m:
        tail = [s.strip() for s in m.group(1).split(",")]
        if all(_SPEC_ID_RE.fullmatch(s) for s in tail) and any(
            s.upper() == spec_id.upper() for s in tail
        ):
            return True
    # Legacy bare: `SPEC-ID: <description>`
    if re.match(rf"^{re.escape(spec_id)}:\s", subject):
        return True
    return False


def _fetch_develop(project_path: str) -> None:
    """Rule 4: refresh origin/develop ref before gate evaluation.

    Best-effort: on network failure we fall through and evaluate against
    the local snapshot of origin/develop. The gate is conservative
    (only marks done on positive match), so stale-origin failure means
    "may stay blocked one extra cycle", not "false-done".
    """
    try:
        subprocess.run(
            ["git", "-C", project_path, "fetch", "origin", "develop", "--quiet"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("FETCH: failed for %s: %s", project_path, exc)


def _is_done_on_develop(project_path: str, spec_id: str, allowed_files: list[str]) -> bool:
    """Rule 1 (THE gate): True iff origin/develop contains a commit whose
    subject implements spec_id (per `_subject_implements`) AND that touches
    at least one path in `allowed_files`.

    No activity window. No `--all`. No auto-close path. The state of
    `origin/develop` is the only thing that matters.

    Second `--first-parent` pass (2026-07-02, plpilot BUG-338 false-blocked):
    default history simplification hides no-ff merge commits from the
    path-filtered log (merge is TREESAME to its feature parent), so a
    `Merge BUG-338: ...` subject was never examined. `--first-parent`
    computes TREESAME against the first parent only — merges bringing
    allowed-file changes into develop DO appear there.

    Returns False on any error or empty inputs — conservative by design,
    fail-closed: ambiguity → blocked, not done.

    Bookkeeping paths are stripped first (2026-07-27) — see
    `gate_logic.strip_bookkeeping_paths`. A spec listing `ai/lifecycle/<ID>.yaml`
    was matching its own birth commit (`lifecycle(BUG-460): queued`), which is a
    conventional commit with the spec id in scope touching an allowed path.

    Keep in sync with gate_logic.find_implementation_commit (L-derived-2).
    """
    if not spec_id or not allowed_files:
        return False
    allowed_files = gate_logic.strip_bookkeeping_paths(allowed_files)
    if not allowed_files:
        log.warning(
            "GATE: %s — allowlist is bookkeeping-only, no implementation evidence possible",
            spec_id,
        )
        return False
    for extra_args in ([], ["--first-parent"]):
        cmd = [
            "git",
            "-C",
            project_path,
            "log",
            *extra_args,
            "origin/develop",
            "--pretty=%h%x00%s",
            "--",
            *allowed_files,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("GATE: git log failed for %s: %s", spec_id, exc)
            return False
        if r.returncode != 0:
            log.warning(
                "GATE: git log rc=%s stderr=%s",
                r.returncode,
                r.stderr.strip()[:200],
            )
            return False
        for line in r.stdout.splitlines():
            if not line:
                continue
            _, _, subject = line.partition("\x00")
            if _subject_implements(subject, spec_id):
                return True
    return False


# --- TECH-169: Circuit-breaker -----------------------------------------------

# Threshold: more than this many demotes within WINDOW_MIN → circuit OPEN.
CIRCUIT_THRESHOLD = 3
CIRCUIT_WINDOW_MIN = 10
# Healing: if there were no demotes in the last HEAL_MIN minutes, circuit
# auto-closes (lazy check inside is_circuit_open).
CIRCUIT_HEAL_MIN = 30
# Reset CLI clears decisions newer than this (matches HEAL_MIN by design).
CIRCUIT_RESET_CLEAR_MIN = 30
# Pueue group paused on OPEN / resumed on RESET.
CIRCUIT_PUEUE_GROUP = "claude-runner"


def is_circuit_open() -> bool:
    """Return True if circuit-breaker is currently OPEN.

    Logic:
      1. Count demotes in last CIRCUIT_WINDOW_MIN minutes.
      2. If count > CIRCUIT_THRESHOLD → OPEN.
      3. Auto-heal: if count == 0 over CIRCUIT_HEAL_MIN window → CLOSED
         (cheap because we just compared to 0 above; no extra query).

    Pure function over DB state — no in-memory flag (callback is short-lived
    per pueue completion).
    """
    try:
        recent = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
    except Exception as exc:  # noqa: BLE001 — callback must not crash
        log.warning("CIRCUIT: count_demotes_since failed: %s", exc)
        return False
    if recent > CIRCUIT_THRESHOLD:
        # Lazy auto-heal: if last 30 min were quiet, ignore stale window.
        try:
            heal = db.count_demotes_since(CIRCUIT_HEAL_MIN)
        except Exception:
            heal = recent
        if heal == 0:
            log.info("CIRCUIT: auto-heal — no demotes in %d min", CIRCUIT_HEAL_MIN)
            return False
        return True
    return False


def _pueue_pause(group: str = CIRCUIT_PUEUE_GROUP) -> bool:
    """Best-effort pause of a pueue group. Returns True on success.

    Never raises — pueue might be missing, socket mismatch, etc.
    """
    try:
        r = subprocess.run(
            ["pueue", "pause", "--group", group],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            log.warning("CIRCUIT: paused pueue group=%s", group)
            return True
        log.warning(
            "CIRCUIT: pause failed (rc=%s) stderr=%s",
            r.returncode,
            r.stderr.strip()[:200],
        )
        return False
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("CIRCUIT: pause subprocess error: %s", exc)
        return False


def _pueue_resume(group: str = CIRCUIT_PUEUE_GROUP) -> bool:
    """Best-effort resume of a pueue group. Returns True on success."""
    try:
        r = subprocess.run(
            ["pueue", "start", "--group", group],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            log.warning("CIRCUIT: resumed pueue group=%s", group)
            return True
        log.warning(
            "CIRCUIT: resume failed (rc=%s) stderr=%s",
            r.returncode,
            r.stderr.strip()[:200],
        )
        return False
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("CIRCUIT: resume subprocess error: %s", exc)
        return False


def _trip_circuit(project_id: str, spec_id: str | None, count: int) -> None:
    """Side-effects fired exactly once when circuit transitions to OPEN.

    1. Log structured warning.
    2. Record an explicit 'circuit_open' decision (NOT counted as demote).
    3. Notify via event_writer (Telegram-equivalent).
    4. Pause claude-runner pueue group (best-effort).
    """
    log.error(
        "CIRCUIT_OPEN: %d demotes in %d min, refusing further status mutations until reset",
        count,
        CIRCUIT_WINDOW_MIN,
    )
    try:
        db.record_decision(
            project_id,
            spec_id,
            "circuit_open",
            f"threshold_exceeded:{count}/{CIRCUIT_WINDOW_MIN}min",
            demoted=False,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record_decision(circuit_open) failed: %s", exc)
    try:
        event_writer.notify_circuit_event(
            action="open",
            count=count,
            window_min=CIRCUIT_WINDOW_MIN,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: notify_circuit_event(open) failed: %s", exc)
    _pueue_pause()


def _reset_circuit_cli() -> None:
    """Operator-triggered circuit reset.

    Steps:
      1. Clear callback_decisions newer than CIRCUIT_RESET_CLEAR_MIN.
      2. Resume claude-runner pueue group.
      3. Send reset event (Telegram-equivalent).
    """
    try:
        deleted = db.clear_decisions(CIRCUIT_RESET_CLEAR_MIN)
        log.warning("CIRCUIT_RESET: cleared %d decision row(s)", deleted)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT_RESET: clear_decisions failed: %s", exc)
    _pueue_resume()
    try:
        event_writer.notify_circuit_event(action="reset", count=0, window_min=CIRCUIT_WINDOW_MIN)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT_RESET: notify failed: %s", exc)
    print(f"circuit reset: cleared decisions, resumed {CIRCUIT_PUEUE_GROUP}")


# -----------------------------------------------------------------------------


def _emit_audit(
    project_id: str,
    spec_id: str,
    pueue_id: int | None,
    target_in: str,
    target_out: str,
    reason: str,
    allowed_count: int,
    code_loc: int,
    test_loc: int,
    code_commits: int,
    started_at: str | None,
    start_wall: float,
    **extra: object,
) -> None:
    """Build audit record and write one JSONL line. Called once per verify_status_sync exit."""
    duration_ms = int((time.monotonic() - start_wall) * 1000)
    record = {
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_id": project_id,
        "spec_id": spec_id,
        "pueue_id": pueue_id,
        "target_in": target_in,
        "target_out": target_out,
        "reason": reason,
        "allowed_count": allowed_count,
        "code_loc": code_loc,
        "test_loc": test_loc,
        "code_commits": code_commits,
        "started_at": started_at,
        "duration_ms": duration_ms,
    }
    if extra:
        record.update(extra)
    _write_audit(record)


def _record(project_id, spec_id, action, reason, *, demoted=False):
    """db.record_decision, never raises (BLE001)."""
    try:
        db.record_decision(project_id, spec_id, action, reason, demoted=demoted)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record_decision failed: %s", exc)


def _render_and_commit_backlog(project_path: str, project_id: str) -> None:
    """Rule 5: inline render of ai/backlog.md after every lifecycle write.

    Best-effort. Lifecycle yaml is the SoT; backlog.md is a render. If render
    fails, lifecycle write still succeeds and the next callback retries the
    render. Logged but never raises.
    """
    try:
        import render_backlog

        content = render_backlog.render_backlog(project_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("RENDER: render_backlog failed for %s: %s", project_id, exc)
        return
    try:
        ok = lifecycle.write_file_atomic(
            project_path,
            "ai/backlog.md",
            content,
            "render(backlog): auto-sync from lifecycle",
            by="callback",
        )
        if not ok:
            log.warning("RENDER: write_file_atomic returned False for %s", project_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("RENDER: write_file_atomic raised for %s: %s", project_id, exc)


def verify_status_sync(
    project_path: str,
    spec_id: str,
    target: str = "done",
    pueue_id: int | None = None,
    autopilot_signaled: bool = False,
) -> None:
    """Single gate: lifecycle.status = done iff origin/develop contains a commit
    with `<spec_id>:` in its subject AND touching at least one allowed file.

    Implements the 2026-05-21 redesign (8 rules). The decision is a pure
    function of (origin/develop after fetch, allowed_files, existing lifecycle).
    Pueue exit code and activity windows do NOT factor into done/blocked.

    Rules enforced here:
      1. done iff commit on origin/develop with `<spec_id>:` subject + allowed_files
      3. noop if no ai/lifecycle/<spec_id>.yaml in this project
      4. fetch origin/develop before evaluating
      5. inline render of ai/backlog.md after every lifecycle write
      7. done is terminal — never demote done

    Preserves:
      - Circuit breaker (TECH-169) on mass-demote
      - Audit log (TECH-171) one JSONL line per call
    """
    target_in = target
    start_wall = time.monotonic()
    project_id = Path(project_path).name

    # Circuit breaker (TECH-169)
    if is_circuit_open():
        log.warning("CIRCUIT_OPEN: skip verify_status_sync(%s)", spec_id)
        _record(project_id, spec_id, "noop", "circuit_open")
        _emit_audit(
            project_id,
            spec_id,
            pueue_id,
            target_in,
            "noop",
            "circuit_open",
            0,
            0,
            0,
            0,
            None,
            start_wall,
        )
        return

    # Rule 3: project boundary
    existing = lifecycle.read_lifecycle(project_path, spec_id)
    if not existing:
        log.info("NOOP: %s — no lifecycle.yaml in %s", spec_id, project_id)
        _record(project_id, spec_id, "noop", "not_in_project")
        _emit_audit(
            project_id,
            spec_id,
            pueue_id,
            target_in,
            "noop",
            "not_in_project",
            0,
            0,
            0,
            0,
            None,
            start_wall,
        )
        return

    existing_status = existing.get("status")

    # Rule 7: done is terminal
    if existing_status == "done":
        log.info("NOOP: %s — already done (terminal)", spec_id)
        _record(project_id, spec_id, "noop", "already_done_terminal")
        _emit_audit(
            project_id,
            spec_id,
            pueue_id,
            target_in,
            "done",
            "already_done_terminal",
            0,
            0,
            0,
            0,
            None,
            start_wall,
        )
        return

    # Allowed files (used by gate + telemetry)
    spec_file = next(iter(Path(project_path).glob(f"ai/features/{spec_id}*.md")), None)
    allowed = gate_logic.parse_allowed_files(spec_file) if spec_file else None
    started_at = _get_started_at(int(pueue_id)) if pueue_id else None
    code_loc, test_loc, code_commits = _commit_stats(project_path, allowed, started_at)

    # BUG-199 Fix C: detect out-of-scope files touched by spec-attributed commits
    out_of_scope_files = _detect_out_of_scope_files(project_path, spec_id, allowed, started_at)
    if out_of_scope_files:
        log.warning(
            "OUT_OF_SCOPE: %s — commits attributed to %s touched %d file(s) outside allowlist: %s",
            project_id,
            spec_id,
            len(out_of_scope_files),
            ", ".join(out_of_scope_files[:10]),
        )

    # TECH-197: push-local-before-gate — flush timeout-interrupted merge
    # When timeout kills autopilot between "git merge" and "git push develop",
    # implementation sits in local develop but NOT origin. Push it now.
    if not autopilot_signaled and target == "blocked":
        try:
            subprocess.run(
                ["git", "-C", project_path, "push", "origin", "develop"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            log.info("PUSH_LOCAL: %s — best-effort push develop for %s", spec_id, project_id)
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("PUSH_LOCAL: %s — failed: %s", spec_id, exc)

    if not allowed:
        # Cannot evaluate the gate → block with explicit reason.
        new_status = "blocked"
        reason = "missing_allowed_files" if allowed is None else "empty_allowed_files"
        log.warning("GATE: %s — %s, blocking", spec_id, reason)
    else:
        # Rule 4: fetch before evaluating the gate
        gate_logic.fetch_develop(project_path)
        # Rule 1: THE gate
        if gate_logic.find_implementation_commit(project_path, spec_id, allowed):
            new_status = "done"
            reason = ""
        else:
            # Default: blocked with operator recovery hint
            blocked_reason = (
                f"no_merged_implementation — if implementation IS real, run: "
                f"python3 scripts/vps/spec_operator.py force-done {project_id} {spec_id} "
                f"'gate regex bug, verified manually' --by=operator"
            )
            # TECH-197: grace-retry — network race (impl pushed but not yet visible)
            # Only retry when push-local was attempted or result=done (normal success)
            if not autopilot_signaled:
                for attempt in range(1, 4):  # up to 3 retries
                    time.sleep(5)
                    gate_logic.fetch_develop(project_path)
                    if gate_logic.find_implementation_commit(project_path, spec_id, allowed):
                        new_status = "done"
                        reason = ""
                        log.info("GRACE_RETRY: %s — resolved on attempt %d", spec_id, attempt)
                        break
                else:
                    new_status = "blocked"
                    reason = blocked_reason
            else:
                # Autopilot EXPLICITLY signaled blocked/needs_review and the gate
                # finds no merged implementation — this is the expected, correct
                # outcome of a deliberate self-block (e.g. unmet dependency), NOT
                # a gate/guard anomaly. Surface the real cause instead of the
                # misleading no_merged_implementation hint (which tells the
                # operator to force-done a spec the autopilot intentionally held).
                new_status = "blocked"
                reason = "autopilot_signaled_blocked"

    # Autopilot explicitly signaled blocked/needs_review → honor over gate=done
    # (autopilot saw something the gate can't infer: tests failed, need human, etc.)
    # TECH-197: only override when autopilot EXPLICITLY signaled (not timeout/crash)
    if autopilot_signaled and target == "blocked" and new_status == "done":
        new_status = "blocked"
        reason = "autopilot_signaled_blocked"

    # No-op if state already matches
    if existing_status == new_status:
        log.info("NOOP: %s — already %s", spec_id, new_status)
        _record(project_id, spec_id, "noop", "already_correct")
        _emit_audit(
            project_id,
            spec_id,
            pueue_id,
            target_in,
            new_status,
            "already_correct",
            len(allowed) if allowed else 0,
            code_loc,
            test_loc,
            code_commits,
            started_at,
            start_wall,
        )
        return

    # Demote accounting (circuit breaker)
    if new_status == "blocked":
        _record(project_id, spec_id, "demote", reason, demoted=True)
        try:
            count = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
            if count > CIRCUIT_THRESHOLD:
                _trip_circuit(project_id, spec_id, count)
        except Exception as exc:  # noqa: BLE001
            log.warning("CIRCUIT: count/trip failed: %s", exc)
    else:
        _record(project_id, spec_id, "sync", "fixed")

    log.warning(
        "STATUS_SYNC: %s — %s → %s (%s)",
        spec_id,
        existing_status,
        new_status,
        reason or "ok",
    )
    try:
        lifecycle.write_lifecycle(
            project_path,
            spec_id,
            new_status,
            reason=reason or None,
            by="callback",
            pueue_id=pueue_id,
        )
    except lifecycle.LifecycleAlreadyDoneError as exc:
        # Rule 7 structural guard (ADR-025): race between Rule 7 fast-path read
        # (lines ~1074-1092) and write — another writer flipped to done in between.
        # Benign NOOP — emit warning for investigation.
        log.warning("STATUS_SYNC: %s — Rule 7 structural save (%s)", spec_id, exc)
        _record(project_id, spec_id, "noop", "rule_7_saved")
        try:
            event_writer.notify(
                project_path,
                "callback",
                "failed",
                f"rule_7_saved: {spec_id} — callback attempted '{new_status}', "
                f"spec already done. Investigate who wrote lifecycle({spec_id}): done.",
            )
        except Exception:  # noqa: BLE001
            pass  # notify is best-effort
        _emit_audit(
            project_id,
            spec_id,
            pueue_id,
            target_in,
            "done",
            "rule_7_saved",
            len(allowed) if allowed else 0,
            code_loc,
            test_loc,
            code_commits,
            started_at,
            start_wall,
        )
        return
    except Exception as exc:  # noqa: BLE001
        log.warning("STATUS_SYNC: lifecycle.write failed for %s: %s", spec_id, exc)
        _emit_audit(
            project_id,
            spec_id,
            pueue_id,
            target_in,
            "error",
            f"write_failed:{exc}",
            len(allowed) if allowed else 0,
            code_loc,
            test_loc,
            code_commits,
            started_at,
            start_wall,
        )
        return

    # Rule 5 (ARCH-196): inline backlog render REMOVED — backlog.md is now
    # single-writer (spark/autopilot Edit). The render helper is retained
    # at line ~975 as an operator emergency CLI tool only.

    _emit_audit(
        project_id,
        spec_id,
        pueue_id,
        target_in,
        new_status,
        reason or "ok",
        len(allowed) if allowed else 0,
        code_loc,
        test_loc,
        code_commits,
        started_at,
        start_wall,
        out_of_scope_files=out_of_scope_files if out_of_scope_files else None,
    )


def write_event_for_skill(project_path: str, skill: str, status: str, task_label: str) -> None:
    """Write OpenClaw event for applicable skills."""
    if skill not in ("autopilot", "qa", "reflect", "spark"):
        return
    if status != "done" and not (status == "failed" and skill == "qa"):
        return

    artifact_rel = ""
    p = Path(project_path)
    if skill == "qa":
        qa_files = sorted(p.glob("ai/qa/[0-9]*-*.md"))
        if qa_files:
            artifact_rel = str(qa_files[-1].relative_to(p))
    elif skill == "reflect":
        reflect_files = sorted(p.glob("ai/reflect/findings-*.md"))
        if reflect_files:
            artifact_rel = str(reflect_files[-1].relative_to(p))

    event_writer.notify(
        project_path,
        skill,
        status,
        f"{skill} {status} for {task_label}",
        artifact_rel,
    )


def _step6_dispatch_qa_reflect(
    skill: str,
    status: str,
    task_status: str,
    project_id: str,
    task_label: str,
    preview: str,
) -> None:
    """Step 6: Post-autopilot tail — dispatch QA + Reflect.

    TECH-194 Layer E: allowlist gate — only dispatch when completion is confirmed.
    TECH-207: merge-confirmed fallback — when task_status is missing/displaced
    but the implementation IS confirmed merged on origin/develop, dispatch anyway.

    Dispatch conditions (any of):
      1. task_status == "complete" (explicit signal — original path)
      2. task_status not in ("blocked", "needs_review") AND implementation
         confirmed merged on origin/develop (merge fallback)

    Skip conditions:
      - skill != "autopilot" or status != "done"
      - task_status in ("blocked", "needs_review") — deliberate hold
      - No merge confirmed and task_status != "complete" — SIGKILL/abort
    """
    if skill != "autopilot" or status != "done":
        return

    # Explicit block signals — never dispatch (TECH-194 Layer E preserved)
    if task_status in ("blocked", "needs_review"):
        log.info(
            "skip QA+reflect dispatch: task_status=%r (explicit block signal)",
            task_status,
        )
        return

    # Resolve state once — reused by both explicit_complete and merge fallback paths.
    try:
        state = db.get_project_state(project_id)
    except Exception as exc:
        log.warning("skip QA+reflect: get_project_state failed for %s: %s", project_id, exc)
        return
    if not state:
        log.info("skip QA+reflect: no project_state for %s", project_id)
        return
    project_path = state.get("path", "")
    provider = state.get("provider", "claude") or "claude"
    if not project_path:
        log.info("skip QA+reflect: empty project_path for %s", project_id)
        return

    spec_id = resolve_spec_id(task_label, preview, project_path)

    dispatch_via = ""  # tracks which path triggered dispatch

    if task_status == "complete":
        dispatch_via = "explicit_complete"
    else:
        # TECH-207: merge-confirmed fallback — check origin/develop.
        # Reuses the same gate logic as Step 7 (verify_status_sync).
        if not spec_id:
            log.info(
                "skip QA+reflect merge fallback: no spec_id for %s",
                task_label,
            )
            return

        try:
            spec_file = next(
                iter(Path(project_path).glob(f"ai/features/{spec_id}*.md")),
                None,
            )
            allowed = gate_logic.parse_allowed_files(spec_file) if spec_file else None
            if not allowed:
                log.info(
                    "skip QA+reflect merge fallback: no allowed_files for %s",
                    spec_id,
                )
                return

            gate_logic.fetch_develop(project_path)
            if gate_logic.find_implementation_commit(project_path, spec_id, allowed):
                dispatch_via = "QA_DISPATCH_MERGE_FALLBACK"
                log.info(
                    "QA_DISPATCH_MERGE_FALLBACK: task_status=%r but impl confirmed "
                    "merged on origin/develop for %s — dispatching QA+Reflect",
                    task_status,
                    spec_id,
                )
            else:
                log.info(
                    "skip QA+reflect dispatch: task_status=%r, no merge confirmed "
                    "for %s (SIGKILL/abort/incomplete)",
                    task_status,
                    spec_id,
                )
                return
        except Exception as exc:
            log.warning(
                "QA_DISPATCH_MERGE_FALLBACK: error checking merge for %s: %s",
                task_label,
                exc,
            )
            return

    # Dispatch QA + Reflect (shared path for both explicit_complete and merge fallback)
    try:
        if spec_id:
            dispatch_qa(project_id, project_path, spec_id, provider)
        else:
            log.info("skip QA: no spec_id resolved for %s", task_label)
        dispatch_reflect(project_id, project_path, task_label, provider)
    except Exception as exc:
        log.warning("post-autopilot dispatch failed (%s): %s", dispatch_via, exc)


def main() -> None:  # pragma: no cover
    """Main callback entry point. ALWAYS exits 0.

    Two modes:
      • Pueue callback: argv = [pueue_id, group, result]  — fired by daemon.
      • Operator CLI:   argv = ['--reset-circuit']        — manual reset.
    """
    try:
        _load_env()
        _setup_logging()

        # TECH-169: operator CLI mode
        if len(sys.argv) > 1 and sys.argv[1] == "--reset-circuit":
            _reset_circuit_cli()
            return

        pueue_id = sys.argv[1] if len(sys.argv) > 1 else "0"
        group = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        result = sys.argv[3] if len(sys.argv) > 3 else "unknown"

        log.info("callback: id=%s group=%s result=%s", pueue_id, group, result)

        # Skip night-reviewer group
        if group == "night-reviewer":
            log.info("skip night-reviewer callback")
            sys.exit(0)

        label = resolve_label(pueue_id)
        project_id, task_label = parse_label(label)
        status, exit_code = map_result(result)

        log.info("parsed: project=%s task=%s status=%s", project_id, task_label, status)

        # Step 1: Release slot (ALWAYS)
        try:
            db.release_slot(pueue_id)
        except Exception as exc:
            log.warning("release_slot failed: %s", exc)

        # Step 2: Finish task
        try:
            db.finish_task(pueue_id, status, exit_code)
        except Exception as exc:
            log.warning("finish_task failed: %s", exc)

        # Step 3: Update phase
        try:
            if task_label.startswith(("qa-", "reflect-")):
                new_phase = "idle"  # non-blocking tail tasks
            elif status == "done":
                if task_label.startswith("inbox-"):
                    new_phase = "idle"
                else:
                    new_phase = "qa_pending"
            else:
                new_phase = "failed"

            current_task = task_label if new_phase == "qa_pending" else None
            db.update_project_phase(project_id, new_phase, current_task)
            log.info("phase updated: %s -> %s", project_id, new_phase)
        except Exception as exc:
            log.warning("update_phase failed: %s", exc)

        # Step 4: Extract agent output
        skill, preview, task_status = "", "", ""
        try:
            skill, preview, task_status = extract_agent_output(pueue_id, project_id)
            log.info(
                "agent output: skill=%s preview_len=%d task_status=%s",
                skill,
                len(preview),
                task_status,
            )
        except Exception as exc:
            log.warning("extract_agent_output failed: %s", exc)

        # Step 5: Write OpenClaw event
        try:
            project_path = ""
            state = db.get_project_state(project_id)
            if state:
                project_path = state.get("path", "")
            if project_path:
                write_event_for_skill(project_path, skill, status, task_label)
        except Exception as exc:
            log.warning("write_event failed: %s", exc)

        # Step 6: Post-autopilot tail — dispatch QA + Reflect
        # Extracted to _step6_dispatch_qa_reflect (TECH-207)
        try:
            _step6_dispatch_qa_reflect(
                skill=skill,
                status=status,
                task_status=task_status,
                project_id=project_id,
                task_label=task_label,
                preview=preview,
            )
        except Exception as exc:
            log.warning("step6 dispatch failed: %s", exc)

        # Step 7: Verify spec + backlog status sync
        if skill == "autopilot" and status in ("done", "failed"):
            try:
                if not project_path:
                    state = db.get_project_state(project_id)
                    project_path = state.get("path", "") if state else ""
                if project_path:
                    sid = resolve_spec_id(task_label, preview, project_path)
                    if sid:
                        if status == "done":
                            # task_status=blocked or needs_review → demote to blocked
                            if task_status in ("blocked", "needs_review"):
                                target = "blocked"
                                log.info(
                                    "STATUS: task_status=%s → target=blocked (overrides pueue Success)",
                                    task_status,
                                )
                            else:
                                # task_status="" (missing) or "complete" → honour pueue Success
                                target = "done"
                        else:
                            target = "blocked"
                        verify_status_sync(
                            project_path,
                            sid,
                            target,
                            pueue_id=int(pueue_id) if pueue_id else None,
                            autopilot_signaled=task_status in ("blocked", "needs_review"),
                        )
            except Exception as exc:
                log.warning("status_sync check failed: %s", exc)

    except Exception:
        log.exception("callback fatal error")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
