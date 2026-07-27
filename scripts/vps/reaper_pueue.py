#!/usr/bin/env python3
"""
Module: reaper_pueue
Role: Pueue inventory for heartbeat_reaper — enumerate Running claude-runner
      tasks and parse their metadata. Extracted from heartbeat_reaper (TECH-211).
Uses: subprocess (pueue status --json), json, re, datetime, pathlib
Used by: heartbeat_reaper.py
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

log = logging.getLogger("heartbeat-reaper")   # то же имя — вывод не меняется


# ---------------------------------------------------------------------------
# Pueue helpers
# ---------------------------------------------------------------------------

def get_running_claude_tasks() -> list[dict]:
    """Return Running tasks in the claude-runner group with parsed metadata.

    Each dict: {id, label, group, command, start_iso, start_dt, project}.
    Returns empty list on any failure (fail-open).
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            log.warning("pueue status exit %d: %s", r.returncode, r.stderr[:200])
            return []
        data = json.loads(r.stdout)
    except Exception as exc:
        log.warning("pueue status failed: %s", exc)
        return []

    tasks: list[dict] = []
    for tid_str, task in data.get("tasks", {}).items():
        st = task.get("status", "")
        # Modern pueue: status is {"Running": {"start": "..."}} or similar
        if not isinstance(st, dict):
            continue
        if "Running" not in st:
            continue

        group = task.get("group", "")
        if group != "claude-runner":
            continue

        # Extract start time from Running status
        running_data = st["Running"]
        start_iso = ""
        if isinstance(running_data, dict):
            start_iso = running_data.get("start", "")
        elif isinstance(running_data, str):
            start_iso = running_data

        start_dt = _parse_iso(start_iso)

        # Extract project from label (format: "project_id:SPEC-ID")
        label = task.get("label", "") or ""
        project = label.split(":")[0] if ":" in label else ""

        # Fallback: extract project from command (run-agent.sh <project_dir> ...)
        if not project:
            cmd = task.get("command", "") or task.get("original_command", "")
            project = _project_from_command(cmd)

        tasks.append({
            "id": int(tid_str),
            "label": label,
            "group": group,
            "command": task.get("command", ""),
            "start_iso": start_iso,
            "start_dt": start_dt,
            "project": project,
        })
    return tasks


def _project_from_command(cmd: str) -> str:
    """Extract project name from run-agent.sh command string."""
    # Pattern: run-agent.sh <project_dir> <provider> <skill> <task>
    # project_dir could be /home/dld/projects/awardybot etc.
    match = re.search(r"run-agent\.sh\s+(\S+)", cmd)
    if match:
        return Path(match.group(1)).name
    return ""


def _parse_iso(s: str) -> datetime | None:
    """Parse ISO datetime string, return None on failure."""
    if not s:
        return None
    try:
        # Handle Z suffix and various ISO formats
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
