#!/usr/bin/env python3
"""
Module: callback_logs
Role: Agent output extraction — find the run's log file, parse it, and resolve
      (skill, result_preview, task_status) with a four-layer fallback.

Uses:
  - db: get_project_state, get_task_by_pueue_id
  - subprocess: `pueue status --json`, `pueue log --json`

Used by:
  - callback.main: Step 4 (extract_agent_output)

Extracted from callback.py by TECH-216. Callers reach these names through the
module attribute (`callback_logs.extract_agent_output`) so that
`monkeypatch.setattr(callback_logs, ...)` intercepts them.
"""

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402

log = logging.getLogger("callback")


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
        #      markdown json fence (Opus 4.x). Scans full_preview (up to
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
