#!/usr/bin/env python3
"""
Module: callback
Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect, write audit log.
Uses: db, event_writer, subprocess (pueue CLI fallback)
Used by: Pueue daemon (pueue.yml callback config)
CLI: python3 callback.py <pueue_id> '<group>' '<result>'
INVARIANT: Always exit 0. Every step in try/except.

TECH-171: _write_audit / _emit_audit append one JSONL line per verify_status_sync call.
Audit log path: $CALLBACK_AUDIT_LOG or scripts/vps/callback-audit.jsonl.
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

log = logging.getLogger("callback")


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
        preview = str(data.get("result_preview", ""))[:500]

        # task_status: prefer top-level field; fall back to parsing result_preview as JSON
        task_status = str(data.get("task_status", "") or "")
        if not task_status and preview:
            try:
                inner = json.loads(preview)
                task_status = str(inner.get("task_status", "") or "")
            except json.JSONDecodeError:
                pass

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
    # `[a-z]*` captures sub-spec suffixes (e.g. ARCH-176a/b/c/d). Mirrors
    # orchestrator.scan_backlog regex (v3.15.8). Without it status_sync
    # would target the parent ARCH-176 instead of ARCH-176a.
    spec_re = re.compile(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*")

    # Layer 1: from task label
    m = spec_re.search(task_label)
    if m:
        return m.group(0)

    # Layer 2: from preview text
    if preview:
        m = spec_re.search(preview)
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
                    sm = spec_re.search(m.group(1))
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


_VALID_STATUSES = frozenset({"draft", "queued", "in_progress", "blocked", "resumed", "done"})


def _read_head_blob(project_path: str, rel_path: str) -> str | None:
    """Read file content as it exists at HEAD. None if missing or git error.

    Used by status-sync to operate on canonical state instead of working tree —
    callback never sees (or commits) operator's uncommitted edits.
    """
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "show", f"HEAD:{rel_path}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("HEAD_READ: subprocess failed for %s: %s", rel_path, exc)
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _apply_spec_status(text: str, target: str) -> tuple[bool, str]:
    """Return (changed, new_text) with **Status:** flipped to target."""
    if target not in _VALID_STATUSES:
        return (False, text)
    new_text, count = re.subn(r"(\*\*Status:\*\*)\s*\S+", rf"\1 {target}", text, count=1)
    return (bool(count), new_text)


def _apply_backlog_status(text: str, spec_id: str, target: str) -> tuple[bool, str]:
    """Return (changed, new_text) with backlog row status flipped to target."""
    if target not in _VALID_STATUSES:
        return (False, text)
    pattern = rf"(\|\s*{re.escape(spec_id)}\s*\|.*?\|)\s*\S+\s*(\|)"
    new_text, count = re.subn(pattern, rf"\1 {target} \2", text, count=1)
    return (bool(count), new_text)


def _apply_blocked_reason(text: str, reason: str) -> tuple[bool, str]:
    """Return (changed, new_text) with **Blocked Reason:** appended/updated."""
    line = f"**Blocked Reason:** {reason}"
    new_text, n = re.subn(r"\*\*Blocked Reason:\*\*\s*[^\n]*", line, text, count=1)
    if n == 0:
        new_text, n = re.subn(r"(\*\*Status:\*\*[^\n]*\n)", rf"\1{line}\n", text, count=1)
    return (bool(n), new_text if n else text)


def _git_commit_push(
    project_path: str,
    spec_id: str,
    target: str,
    fixes: list[tuple[str, str]],
) -> None:
    """Commit (path, new_content) pairs via plumbing — does NOT touch working tree.

    Uses `git hash-object -w` + `git update-index --cacheinfo` so the index is
    populated directly from new_content. The commit captures only those blobs.
    Any uncommitted operator edits (in the same files or others) stay in the
    working tree untouched, preventing the callback from snatching unrelated
    changes the way `git add <file>` did.
    """
    if not fixes:
        return
    git = ["git", "-C", project_path]
    for rel_path, new_content in fixes:
        try:
            r = subprocess.run(
                git + ["hash-object", "-w", "--stdin"],
                input=new_content,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            blob_sha = r.stdout.strip()
            subprocess.run(
                git + ["update-index", "--cacheinfo", f"100644,{blob_sha},{rel_path}"],
                capture_output=True,
                timeout=10,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            log.warning(
                "STATUS_FIX: plumbing stage failed for %s: %s",
                rel_path,
                stderr[:200],
            )
            return
    msg = f"docs: mark {spec_id} as {target} (callback auto-fix)"
    r = subprocess.run(git + ["commit", "-m", msg], capture_output=True, timeout=30)
    if r.returncode != 0:
        log.warning(
            "STATUS_FIX: commit failed for %s: %s",
            spec_id,
            r.stderr.decode(errors="replace")[:200],
        )
        return
    subprocess.run(git + ["push", "origin", "develop"], capture_output=True, timeout=60)
    log.info(
        "STATUS_FIX: committed and pushed %s → %s (%d file(s), no working-tree mutation)",
        spec_id,
        target,
        len(fixes),
    )


def _resync_backlog_to_spec(
    project_path: str,
    spec_id: str,
    spec_status: str,
    backlog_path: Path,
) -> None:
    """Sync backlog row status to spec authority — stop dispatch loops.

    When a guard fires (target=done blocked by spec=blocked, or target=blocked
    blocked by spec=done), the spec is treated as authoritative. Without this
    resync, the backlog can stay in a state (queued/resumed/in_progress) that
    causes the orchestrator to dispatch the spec on every poll cycle, while
    autopilot then SKIPs because of the inconsistency. v3.15.6.

    Idempotent: if backlog already matches `spec_status`, no commit.
    """
    if not backlog_path.is_file():
        return
    head = _read_head_blob(project_path, "ai/backlog.md")
    if head is None:
        return
    backlog_re = re.compile(
        rf"\|\s*{re.escape(spec_id)}\s*\|.*?\|\s*{re.escape(spec_status)}\s*\|",
        re.IGNORECASE,
    )
    if backlog_re.search(head):
        return  # already in sync at HEAD
    ok, new_text = _apply_backlog_status(head, spec_id, spec_status)
    if not ok or new_text == head:
        return
    log.warning(
        "STATUS_SYNC: %s — resynced backlog to spec authority (%s) to break dispatch loop",
        spec_id,
        spec_status,
    )
    _git_commit_push(project_path, spec_id, spec_status, [("ai/backlog.md", new_text)])


# --- TECH-166 / TECH-167: Implementation guard helpers ----------------------

# Backticked path-shape: anything between backticks with a dot extension.
# Drops the extension whitelist — Go (.go), Astro (.astro), Terraform (.tf),
# Dockerfile, .env.example, etc. are all valid project files. False positives
# like `foo.bar` are harmless: git log finds no commits and they're ignored.
_ALLOWED_FILE_EXT_RE = re.compile(r"`([^\s`\n]+\.[a-zA-Z][\w-]*)`")

# --- TECH-175: outer DLD-CALLBACK-MARKER pair --------------------------------
_DLD_MARKER_START_RE = re.compile(
    r"^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$"
)
_DLD_MARKER_END_RE = re.compile(r"^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$")
_DLD_SUPPORTED_MARKER_VERSIONS: frozenset[str] = frozenset({"1"})

# --- TECH-167 v1 canonical format -------------------------------------------
# Strict heading: "## Allowed Files" (case-sensitive, no suffix, no qualifier).
_ALLOWED_FILES_V1_HEADING_RE = re.compile(r"^##[ \t]+Allowed Files[ \t]*$")
# Marker comment that opts a spec into v1 strict parsing.
_ALLOWED_FILES_V1_MARKER_RE = re.compile(
    r"<!--\s*callback-allowlist\s+v1\b[^>]*-->"
)
# Canonical bullet: "- `path/with.ext` optional trailing prose".
_ALLOWED_FILES_V1_BULLET_RE = re.compile(
    r"^-[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$"
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


def _parse_allowed_files_marker(spec_text: str) -> list[str] | None:
    """Marker-aware parser (TECH-175). Returns:

        list[str]: >=0 paths inside a v1 marker block containing
                   ## Allowed Files (success or empty=degrade-closed).
        None     : no DLD-CALLBACK-MARKER blocks present (caller falls
                   back to TECH-167 v1 / legacy parsers).
    """
    lines = spec_text.splitlines()
    i = 0
    while i < len(lines):
        m = _DLD_MARKER_START_RE.match(lines[i])
        if not m:
            i += 1
            continue
        ver = m.group("ver")
        # Find matching END (no nesting allowed; first END wins).
        j = i + 1
        while j < len(lines) and not _DLD_MARKER_END_RE.match(lines[j]):
            j += 1
        if j >= len(lines):
            log.warning(
                "ALLOWED_FILES: unmatched DLD-CALLBACK-MARKER-START at line %d"
                " → degrade-closed",
                i + 1,
            )
            return []
        block = lines[i + 1:j]
        has_af_heading = any(_ALLOWED_FILES_V1_HEADING_RE.match(ln) for ln in block)
        if has_af_heading:
            if ver not in _DLD_SUPPORTED_MARKER_VERSIONS:
                log.warning(
                    "ALLOWED_FILES: unknown marker version v%s → degrade-closed",
                    ver,
                )
                return []
            # Reuse v1 strict bullet matcher.
            paths = [
                bm.group(1)
                for ln in block
                if (bm := _ALLOWED_FILES_V1_BULLET_RE.match(ln))
            ]
            return paths  # may be [] (marker present, no bullets)
        i = j + 1  # block didn't contain Allowed Files; keep scanning
    return None  # no relevant marker blocks


def _parse_allowed_files_v1(spec_text: str) -> list[str] | None:
    """Strict canonical v1 parser. Returns:

        list[str]: \u22651 paths (success).
        []        : marker present but ZERO valid bullets \u2014 degrade-closed.
        None      : v1 marker not present (caller should try legacy fallback).
    """
    lines = spec_text.splitlines()

    # Locate the canonical heading (must be EXACT \u2014 case-sensitive, no suffix).
    heading_idxs = [i for i, ln in enumerate(lines)
                    if _ALLOWED_FILES_V1_HEADING_RE.match(ln)]
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

    # Strict mode: only canonical bullets count. No fenced blocks, no
    # backtick-paths outside bullets, no fallback to _ALLOWED_FILE_EXT_RE.
    paths: list[str] = []
    for ln in section:
        m = _ALLOWED_FILES_V1_BULLET_RE.match(ln)
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

    # TECH-175: marker-aware first
    marker = _parse_allowed_files_marker(text)
    if marker is not None:
        log.info(
            "ALLOWED_FILES: marker-aware parse for %s → %d path(s)",
            spec_path.name,
            len(marker),
        )
        return marker

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



def _append_blocked_reason(spec_path: Path, reason: str) -> bool:
    """Path-taking wrapper around _apply_blocked_reason — preserves the
    pre-TECH-167 helper signature used by existing unit tests.

    Reads spec_path, applies _apply_blocked_reason, writes back if changed.
    Idempotent: calling twice with the same reason produces only one
    `**Blocked Reason:**` line (re.subn count=1 ensures replacement, not
    append).
    """
    text = spec_path.read_text(errors="replace")
    changed, new_text = _apply_blocked_reason(text, reason)
    if changed and new_text != text:
        spec_path.write_text(new_text)
    return changed

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
        "git", "-C", project_path, "log", "--all",
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


def _has_implementation_commits(
    project_path: str,
    allowed: list[str] | None,
    started_at: str | None,
    branches: str = "all",
) -> bool:
    """True if any commit since `started_at` touched any path in `allowed`.

    `branches` (TECH-170):
        "all"     → `git log --all` — sees commits on feature branches
                    even when worktree hasn't merged back to develop yet.
                    Default; closes the false-negative gap behind ADR-009.
        "current" → no branch flag — pre-TECH-170 behavior.
        "develop" → `git log develop` — used by `is_merged_to_develop`.

    Degrade-open on missing data:
        allowed is None        → True  (no `## Allowed Files` section — back-compat)
        allowed == []          → False (explicit empty allowlist = no-impl)
        started_at is None     → True  (data-availability issue)
        subprocess error       → True  (don't block on tool failure)
    """
    if allowed is None:
        return True
    if started_at is None:
        return True
    if not allowed:
        return False
    cmd = ["git", "-C", project_path, "log"]
    if branches == "all":
        cmd.append("--all")
    elif branches == "develop":
        cmd.append("develop")
    # "current" → no extra flag
    cmd += [f"--since={started_at}", "--pretty=%H", "--", *allowed]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("IMPL_GUARD: git log failed (%s) — degrade open", exc)
        return True
    if result.returncode != 0:
        log.warning(
            "IMPL_GUARD: git log rc=%s stderr=%s — degrade open",
            result.returncode,
            result.stderr.strip()[:200],
        )
        return True
    return bool(result.stdout.strip())


def is_merged_to_develop(project_path: str, spec_id: str) -> bool:
    """Best-effort check: does `develop` contain a commit mentioning spec_id?

    Used only for diagnostic logging in `verify_status_sync`. Never blocks
    a transition. On any error returns False (silent — caller treats as
    "merge state unknown").

    TECH-170: pairs with `--all` guard. Together they let us tell apart:
        - work on feature/<spec> only (guard True, this False) — log warn
        - work merged to develop      (guard True, this True)  — happy path
    """
    if not spec_id:
        return False
    cmd = [
        "git", "-C", project_path, "log", "develop",
        "--grep", re.escape(spec_id),
        "--pretty=%H",
        "-n", "1",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("MERGE_CHECK: git log failed for %s: %s", spec_id, exc)
        return False
    if r.returncode != 0:
        return False
    return bool(r.stdout.strip())


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
        db.record_decision(project_id, spec_id, "circuit_open",
                           f"threshold_exceeded:{count}/{CIRCUIT_WINDOW_MIN}min",
                           demoted=False)
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
        event_writer.notify_circuit_event(action="reset", count=0,
                                          window_min=CIRCUIT_WINDOW_MIN)
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
    _write_audit(record)


def verify_status_sync(
    project_path: str,
    spec_id: str,
    target: str = "done",
    pueue_id: int | None = None,
) -> None:
    """Check that spec file and backlog both have target status. Auto-fix if not.

    Operates on HEAD content (not working tree) — operator's uncommitted edits
    in spec/backlog are preserved. Final commit goes through git plumbing
    (`update-index --cacheinfo`), so the working tree is never touched.

    TECH-166: when target='done' and pueue_id is provided, run an implementation
    guard — verify commits touching the spec's `## Allowed Files` since
    `started_at`. Missing section → demote with reason='missing_allowed_files_section'.
    No matching commits → demote with reason='no_implementation_commits'.
    """
    # TECH-171: audit anchors — capture before any work
    target_in = target
    start_wall = time.monotonic()
    project_id = Path(project_path).name

    # TECH-169: Circuit-breaker — refuse all status mutations when OPEN.
    if is_circuit_open():
        log.warning(
            "CIRCUIT_OPEN: skipping verify_status_sync(%s, target=%s) — circuit is open",
            spec_id, target,
        )
        try:
            db.record_decision(project_id, spec_id, "noop",
                               "circuit_open", demoted=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("CIRCUIT: record_decision(noop) failed: %s", exc)
        return

    p = Path(project_path)

    # Resolve spec path + read HEAD content
    spec_files = list(p.glob(f"ai/features/{spec_id}*.md"))
    spec_file = spec_files[0] if spec_files else None
    spec_rel = str(spec_file.relative_to(p)) if spec_file else None
    spec_head = _read_head_blob(project_path, spec_rel) if spec_rel else None
    if not spec_files:
        log.warning("STATUS_SYNC: spec file not found for %s", spec_id)

    # Backlog HEAD content
    backlog_path = p / "ai" / "backlog.md"
    backlog_rel = "ai/backlog.md"
    backlog_head = _read_head_blob(project_path, backlog_rel) if backlog_path.is_file() else None
    if backlog_head is None and not backlog_path.is_file():
        log.warning("STATUS_SYNC: backlog.md not found in %s", project_path)

    spec_text = spec_head
    backlog_text = backlog_head

    # TECH-171: stats collected once, reused in audit record
    allowed: list[str] | None = None
    started_at: str | None = None
    code_loc = 0
    test_loc = 0
    code_commits = 0
    guard_reason = ""

    # TECH-166: implementation guard — demote done→blocked if no commits touched
    # the spec's Allowed Files since task start, OR if the spec lacks the section.
    if target == "done" and spec_text is not None and pueue_id is not None and spec_file:
        allowed = _parse_allowed_files(spec_file)
        started_at = _get_started_at(int(pueue_id))
        code_loc, test_loc, code_commits = _commit_stats(project_path, allowed, started_at)
        if not _has_implementation_commits(project_path, allowed, started_at):
            guard_reason = (
                "missing_allowed_files_section" if allowed is None else "no_implementation_commits"
            )
            log.warning(
                "IMPL_GUARD: %s — demoting done → blocked (%s, started_at=%s)",
                spec_id,
                guard_reason,
                started_at,
            )
            _, spec_text = _apply_blocked_reason(spec_text, guard_reason)
            target = "blocked"
            # TECH-169: feed circuit-breaker
            try:
                db.record_decision(project_id, spec_id, "demote",
                                   guard_reason, demoted=True)
                count = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
                if count > CIRCUIT_THRESHOLD:
                    _trip_circuit(project_id, spec_id, count)
            except Exception as exc:  # noqa: BLE001
                log.warning("CIRCUIT: record/check failed: %s", exc)
        else:
            # TECH-170: positive path — tell apart "merged to develop" vs "feature-only"
            if is_merged_to_develop(project_path, spec_id):
                log.info("IMPL_GUARD: %s — commits found and merged to develop ✓", spec_id)
            else:
                log.warning(
                    "IMPL_GUARD: %s has commits on feature branch but NOT merged to develop yet "
                    "(allowing done; visible in dashboard)",
                    spec_id,
                )

    # Spec-authority guards (v3.15.5/6) — operate on HEAD, never on working tree.
    if target == "done" and spec_text is not None:
        if re.search(r"\*\*Status:\*\*\s*blocked", spec_text, re.IGNORECASE):
            log.info(
                "STATUS_SYNC: %s — spec is blocked at HEAD, skipping done; resync backlog",
                spec_id,
            )
            try:
                db.record_decision(project_id, spec_id, "sync",
                                   "spec_already_blocked", demoted=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("CIRCUIT: record_decision failed: %s", exc)
            _emit_audit(
                project_id, spec_id, pueue_id, target_in, "blocked",
                "spec_already_blocked",
                len(allowed) if allowed is not None else 0,
                code_loc, test_loc, code_commits, started_at, start_wall,
            )
            _resync_backlog_to_spec(project_path, spec_id, "blocked", backlog_path)
            return
    if target == "blocked" and spec_text is not None:
        if re.search(r"\*\*Status:\*\*\s*done", spec_text, re.IGNORECASE):
            log.info(
                "STATUS_SYNC: %s — spec already done at HEAD, skipping blocked "
                "(work likely on feature branch); resync backlog",
                spec_id,
            )
            try:
                db.record_decision(project_id, spec_id, "sync",
                                   "spec_already_done", demoted=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("CIRCUIT: record_decision failed: %s", exc)
            _emit_audit(
                project_id, spec_id, pueue_id, target_in, "done",
                "spec_already_done",
                len(allowed) if allowed is not None else 0,
                code_loc, test_loc, code_commits, started_at, start_wall,
            )
            _resync_backlog_to_spec(project_path, spec_id, "done", backlog_path)
            return

    # Compute desired final content for spec + backlog at HEAD.
    if spec_text is not None:
        ok_spec, spec_text = _apply_spec_status(spec_text, target)
        if not ok_spec:
            log.warning("STATUS_FIX: could not patch spec status for %s", spec_id)
    if backlog_text is not None:
        ok_bl, backlog_text = _apply_backlog_status(backlog_text, spec_id, target)
        if not ok_bl:
            log.warning("STATUS_FIX: could not patch backlog row for %s", spec_id)

    # Build commit set — only files whose HEAD content differs from desired.
    fixes: list[tuple[str, str]] = []
    if spec_rel and spec_head is not None and spec_text is not None and spec_text != spec_head:
        fixes.append((spec_rel, spec_text))
    if backlog_head is not None and backlog_text is not None and backlog_text != backlog_head:
        fixes.append((backlog_rel, backlog_text))

    final_reason = guard_reason if guard_reason else ("already_correct" if not fixes else "fixed")
    _emit_audit(
        project_id, spec_id, pueue_id, target_in, target,
        final_reason,
        len(allowed) if allowed is not None else 0,
        code_loc, test_loc, code_commits, started_at, start_wall,
    )
    try:
        db.record_decision(project_id, spec_id,
                           "sync" if fixes else "noop",
                           final_reason, demoted=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record_decision failed: %s", exc)

    if not fixes:
        log.info("STATUS_SYNC: %s — both spec and backlog are %s ✓", spec_id, target)
        return

    log.warning(
        "STATUS_SYNC: %s — auto-fixed %d file(s) → %s: %s",
        spec_id,
        len(fixes),
        target,
        ", ".join(rel for rel, _ in fixes),
    )
    _git_commit_push(project_path, spec_id, target, fixes)


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


def main() -> None:
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
            log.info("agent output: skill=%s preview_len=%d task_status=%s", skill, len(preview), task_status)
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
        if skill == "autopilot" and status == "done":
            try:
                state = db.get_project_state(project_id)
                if state:
                    project_path = state.get("path", "")
                    provider = state.get("provider", "claude") or "claude"
                    if project_path:
                        spec_id = resolve_spec_id(task_label, preview, project_path)
                        if spec_id:
                            dispatch_qa(project_id, project_path, spec_id, provider)
                        else:
                            log.info("skip QA: no spec_id resolved for %s", task_label)
                        dispatch_reflect(project_id, project_path, task_label, provider)
            except Exception as exc:
                log.warning("post-autopilot dispatch failed: %s", exc)

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
                        )
            except Exception as exc:
                log.warning("status_sync check failed: %s", exc)

    except Exception:
        log.exception("callback fatal error")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
