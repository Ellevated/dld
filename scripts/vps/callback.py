#!/usr/bin/env python3
"""
Module: callback
Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect.
Uses: db, event_writer, subprocess (pueue CLI fallback)
Used by: Pueue daemon (pueue.yml callback config)
CLI: python3 callback.py <pueue_id> '<group>' '<result>'
INVARIANT: Always exit 0. Every step in try/except.
"""

import json
import logging
import os
import re
import subprocess
import sys
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
    """Parse JSON log file → (skill, result_preview). Logs cache metrics."""
    try:
        data = json.loads(log_path.read_text())
        skill = data.get("skill", "")
        preview = str(data.get("result_preview", ""))[:500]

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

        return skill, preview
    except Exception:
        return "", ""


def extract_agent_output(pueue_id: str, project_id: str = "") -> tuple:
    """Extract skill and result_preview.

    Resolution order (skill first, preview second):
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
                        skill, preview = _parse_log_file(log_path)
                        # If pueue gave us a skill, trust it over the log file's
                        # (covers edge case of a still-stale log slipping through).
                        if pueue_skill:
                            skill = pueue_skill
                        if skill:
                            log.info("extract_agent_output from log: %s", log_path.name)
                            return skill, preview
        except Exception as exc:
            log.warning("extract_agent_output log file failed: %s", exc)

    # If log file missing/stale but pueue knew the skill — return it now.
    if pueue_skill:
        log.info("extract_agent_output skill from pueue command: %s", pueue_skill)
        return pueue_skill, ""

    # Layer 1b: Try DB task_log for skill (if no log file found)
    try:
        row = db.get_task_by_pueue_id(int(pueue_id))
        if row and row.get("skill"):
            log.info("extract_agent_output skill from DB: %s", row["skill"])
            return row["skill"], ""
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
                    return skill, preview
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return "", ""


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


def _fix_spec_status(spec_path: Path, spec_id: str, target: str) -> bool:
    """Replace **Status:** <anything> with **Status:** <target> in spec file."""
    if target not in _VALID_STATUSES:
        log.warning("STATUS_FIX: invalid target status '%s' for %s", target, spec_id)
        return False
    text = spec_path.read_text(errors="replace")
    new_text, count = re.subn(
        r"(\*\*Status:\*\*)\s*\S+",
        rf"\1 {target}",
        text,
        count=1,
    )
    if count:
        spec_path.write_text(new_text)
        log.info("STATUS_FIX: spec %s → %s in %s", spec_id, target, spec_path.name)
        return True
    return False


def _fix_backlog_status(backlog_path: Path, spec_id: str, target: str) -> bool:
    """Replace status column for spec_id row in backlog.md."""
    if target not in _VALID_STATUSES:
        log.warning("STATUS_FIX: invalid target status '%s' for %s", target, spec_id)
        return False
    text = backlog_path.read_text(errors="replace")
    pattern = rf"(\|\s*{re.escape(spec_id)}\s*\|.*?\|)\s*\S+\s*(\|)"
    new_text, count = re.subn(pattern, rf"\1 {target} \2", text, count=1)
    if count:
        backlog_path.write_text(new_text)
        log.info("STATUS_FIX: backlog %s → %s", spec_id, target)
        return True
    return False


def _git_commit_push(project_path: str, spec_id: str, target: str, files: list) -> None:
    """Stage, commit, and push status fix."""
    git = ["git", "-C", project_path]
    subprocess.run(git + ["add"] + files, capture_output=True, timeout=10)
    subprocess.run(
        git + ["commit", "-m", f"docs: mark {spec_id} as {target} (callback auto-fix)"],
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        git + ["push", "origin", "develop"],
        capture_output=True,
        timeout=60,
    )
    log.info("STATUS_FIX: committed and pushed %s → %s", spec_id, target)


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
    backlog_re = re.compile(
        rf"\|\s*{re.escape(spec_id)}\s*\|.*?\|\s*{re.escape(spec_status)}\s*\|",
        re.IGNORECASE,
    )
    text = backlog_path.read_text(errors="replace")
    if backlog_re.search(text):
        return  # already in sync
    if _fix_backlog_status(backlog_path, spec_id, spec_status):
        log.warning(
            "STATUS_SYNC: %s — resynced backlog to spec authority (%s) to break dispatch loop",
            spec_id,
            spec_status,
        )
        _git_commit_push(project_path, spec_id, spec_status, ["ai/backlog.md"])


# --- TECH-166: Implementation guard helpers ----------------------------------

# Path-extension allowlist for `## Allowed Files` parser.
_ALLOWED_FILE_EXT_RE = re.compile(
    r"`([^`\n]+\.(?:py|sh|md|sql|yml|yaml|json|toml|js|ts|tsx|jsx|html|css))`"
)
_ALLOWED_FILES_HEADING_RE = re.compile(r"^##\s+Allowed\s+Files\s*$", re.IGNORECASE)
_NEXT_H2_RE = re.compile(r"^##\s+\S")


def _parse_allowed_files(spec_path: Path) -> list[str] | None:
    """Extract relative paths listed in spec's `## Allowed Files` section.

    Returns:
        list[str]: explicit list (may be empty if section is present but lists no paths)
        None: section absent (degrade-open: legacy specs without allowlist)
    """
    try:
        text = spec_path.read_text(errors="replace")
    except OSError as exc:
        log.warning("ALLOWED_FILES: read failed for %s: %s", spec_path, exc)
        return None

    lines = text.splitlines()
    in_section = False
    section_buf: list[str] = []
    for line in lines:
        if not in_section:
            if _ALLOWED_FILES_HEADING_RE.match(line):
                in_section = True
            continue
        # Already inside section — stop on next H2.
        if _NEXT_H2_RE.match(line):
            break
        section_buf.append(line)

    if not in_section:
        return None
    section_text = "\n".join(section_buf)
    return _ALLOWED_FILE_EXT_RE.findall(section_text)


def _get_started_at(pueue_id: int) -> str | None:
    """Read started_at for a pueue task from task_log (read-only db access)."""
    try:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT started_at FROM task_log WHERE pueue_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (pueue_id,),
            ).fetchone()
            if row is None:
                return None
            return row[0] if not hasattr(row, "keys") else row["started_at"]
    except Exception as exc:  # noqa: BLE001 — defensive (callback must not crash)
        log.warning("ALLOWED_FILES: started_at lookup failed for %s: %s", pueue_id, exc)
        return None


def _has_implementation_commits(
    project_path: str,
    allowed: list[str] | None,
    started_at: str | None,
) -> bool:
    """True if any commit since `started_at` touched any path in `allowed`.

    Degrade-open semantics:
        allowed is None        → True  (no allowlist in spec; can't enforce)
        started_at is None     → True  (no time window; can't enforce)
        allowed == []          → False (explicit empty allowlist = no-impl by definition)
        subprocess error       → True  (don't block on tool failure)
    """
    if allowed is None or started_at is None:
        return True
    if not allowed:
        return False
    cmd = [
        "git", "-C", project_path, "log",
        f"--since={started_at}",
        "--pretty=%H",
        "--",
        *allowed,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("IMPL_GUARD: git log failed (%s) — degrade open", exc)
        return True
    if result.returncode != 0:
        log.warning(
            "IMPL_GUARD: git log rc=%s stderr=%s — degrade open",
            result.returncode, result.stderr.strip()[:200],
        )
        return True
    return bool(result.stdout.strip())


def _append_blocked_reason(spec_file: Path, reason: str) -> None:
    """Idempotently set `**Blocked Reason:** <reason>` near the **Status:** line."""
    try:
        text = spec_file.read_text(errors="replace")
    except OSError as exc:
        log.warning("BLOCKED_REASON: read failed for %s: %s", spec_file, exc)
        return
    line = f"**Blocked Reason:** {reason}"
    new_text, n = re.subn(
        r"\*\*Blocked Reason:\*\*\s*[^\n]*", line, text, count=1
    )
    if n == 0:
        # Insert right after first **Status:** line.
        new_text, n = re.subn(
            r"(\*\*Status:\*\*[^\n]*\n)",
            rf"\1{line}\n",
            text,
            count=1,
        )
    if n == 0:
        log.warning("BLOCKED_REASON: no Status anchor in %s", spec_file)
        return
    if new_text != text:
        try:
            spec_file.write_text(new_text)
        except OSError as exc:
            log.warning("BLOCKED_REASON: write failed for %s: %s", spec_file, exc)


# -----------------------------------------------------------------------------


def verify_status_sync(
    project_path: str,
    spec_id: str,
    target: str = "done",
    pueue_id: int | None = None,
) -> None:
    """Check that spec file and backlog both have target status. Auto-fix if not.

    TECH-166: when target='done' and pueue_id is provided, run an implementation
    guard — verify that commits touching the spec's `## Allowed Files` exist
    since the task's `started_at`. If not, demote target to 'blocked' and append
    a Blocked Reason. Degrades open on missing data (legacy specs / no pueue_id
    / git errors) — see `_has_implementation_commits` docstring.
    """
    p = Path(project_path)
    spec_re = re.compile(rf"\*\*Status:\*\*\s*{re.escape(target)}", re.IGNORECASE)
    backlog_re = re.compile(
        rf"\|\s*{re.escape(spec_id)}\s*\|.*?\|\s*{re.escape(target)}\s*\|",
        re.IGNORECASE,
    )

    # Check spec file
    spec_ok = False
    spec_file = None
    spec_files = list(p.glob(f"ai/features/{spec_id}*.md"))
    if not spec_files:
        log.warning("STATUS_SYNC: spec file not found for %s", spec_id)
    else:
        spec_file = spec_files[0]
        text = spec_file.read_text(errors="replace")
        if spec_re.search(text):
            spec_ok = True

    # Check backlog
    backlog_ok = False
    backlog_path = p / "ai" / "backlog.md"
    if not backlog_path.is_file():
        log.warning("STATUS_SYNC: backlog.md not found in %s", project_path)
    else:
        text = backlog_path.read_text(errors="replace")
        if backlog_re.search(text):
            backlog_ok = True

    # TECH-166: implementation guard — demote done→blocked if no commits
    # touched the spec's Allowed Files since task start. Runs BEFORE the
    # spec-blocked / spec-done guards so demotion semantics are: (a) write
    # blocked into the spec via _append_blocked_reason + later auto-fix,
    # (b) flow through the rest of verify_status_sync as target='blocked'.
    if target == "done" and spec_file and pueue_id is not None:
        allowed = _parse_allowed_files(spec_file)
        started_at = _get_started_at(int(pueue_id))
        if not _has_implementation_commits(project_path, allowed, started_at):
            log.warning(
                "IMPL_GUARD: %s — no commits touching allowed files since %s, "
                "demoting done → blocked (no_implementation_commits)",
                spec_id, started_at,
            )
            _append_blocked_reason(spec_file, "no_implementation_commits")
            target = "blocked"
            # Recompute spec_ok / backlog_ok against the new target.
            spec_re = re.compile(rf"\*\*Status:\*\*\s*{re.escape(target)}", re.IGNORECASE)
            backlog_re = re.compile(
                rf"\|\s*{re.escape(spec_id)}\s*\|.*?\|\s*{re.escape(target)}\s*\|",
                re.IGNORECASE,
            )
            spec_ok = bool(spec_re.search(spec_file.read_text(errors="replace")))
            backlog_ok = (
                backlog_path.is_file()
                and bool(backlog_re.search(backlog_path.read_text(errors="replace")))
            )

    if spec_ok and backlog_ok:
        log.info("STATUS_SYNC: %s — both spec and backlog are %s ✓", spec_id, target)
        return

    # Guard: if target is "done" but autopilot set "blocked", respect it.
    # Spec is the authority — if it says blocked, backlog must follow it
    # (resync loop-stopper, see v3.15.6).
    if target == "done" and spec_file:
        blocked_re = re.compile(r"\*\*Status:\*\*\s*blocked", re.IGNORECASE)
        text = spec_file.read_text(errors="replace")
        if blocked_re.search(text):
            log.info("STATUS_SYNC: %s — spec is blocked, skipping auto-fix to done", spec_id)
            _resync_backlog_to_spec(project_path, spec_id, "blocked", backlog_path)
            return

    # Symmetric guard: don't blank-stamp "blocked" over an already-done spec.
    # Autopilot writes done only after committing all per-task code. If the
    # final push/merge step then fails (timeout, conflict, ceiling),
    # status="failed" arrives here with target="blocked" — but the work is
    # already on a feature branch and can be merged manually. Wiping the done
    # status loses that signal and forces a full re-run.
    if target == "blocked" and spec_file:
        done_re = re.compile(r"\*\*Status:\*\*\s*done", re.IGNORECASE)
        text = spec_file.read_text(errors="replace")
        if done_re.search(text):
            log.info(
                "STATUS_SYNC: %s — spec already done, skipping auto-fix to blocked "
                "(work likely on feature branch; operator should merge or resume)",
                spec_id,
            )
            _resync_backlog_to_spec(project_path, spec_id, "done", backlog_path)
            return

    # Auto-fix
    fixed_files = []
    if not spec_ok and spec_file:
        if _fix_spec_status(spec_file, spec_id, target):
            fixed_files.append(str(spec_file.relative_to(p)))
        else:
            log.warning("STATUS_FIX: could not fix spec %s", spec_id)

    if not backlog_ok and backlog_path.is_file():
        if _fix_backlog_status(backlog_path, spec_id, target):
            fixed_files.append("ai/backlog.md")
        else:
            log.warning("STATUS_FIX: could not fix backlog for %s", spec_id)

    if fixed_files:
        log.warning(
            "STATUS_SYNC: %s — auto-fixed %d file(s) → %s: %s",
            spec_id,
            len(fixed_files),
            target,
            ", ".join(fixed_files),
        )
        _git_commit_push(project_path, spec_id, target, fixed_files)


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
    """Main callback entry point. ALWAYS exits 0."""
    try:
        _load_env()
        _setup_logging()

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
        skill, preview = "", ""
        try:
            skill, preview = extract_agent_output(pueue_id, project_id)
            log.info("agent output: skill=%s preview_len=%d", skill, len(preview))
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
                        target = "done" if status == "done" else "blocked"
                        verify_status_sync(
                            project_path, sid, target,
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
