#!/usr/bin/env python3
"""
Module: heartbeat_reaper
Role: Cron-driven reaper for wedged claude-runner sessions (TECH-198 Layer B).
Uses: subprocess (pueue status/kill, /proc), json, datetime, pathlib, event_writer
Used by: cron (setup-vps.sh section 8d)

Enumerates Running claude-runner pueue tasks, matches each to a per-session
heartbeat file, and kills sessions that are stale beyond threshold AND idle
(no active child processes / near-zero CPU). Fail-open on any ambiguity.

Exit codes:
    0 — normal (reaped or no action)
    0 — also on pueue/heartbeat parse failures (best-effort, no spam)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "logs"

# Thresholds (seconds)
GRACE_SECONDS = 300        # 5 min — skip tasks younger than this
STALE_SECONDS = 1500       # 25 min — heartbeat older than this = candidate
CPU_SAMPLE_SECONDS = 2     # CPU sampling window for idle check
CPU_IDLE_THRESHOLD = 1.0   # % — below this = idle

# started_at tolerance for cross-check (seconds)
STARTED_AT_TOLERANCE = 10

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("heartbeat-reaper")


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


# ---------------------------------------------------------------------------
# Heartbeat helpers
# ---------------------------------------------------------------------------

def find_heartbeat_file(
    project: str, task_start_dt: datetime | None
) -> Path | None:
    """Find the heartbeat file for a project, cross-checking started_at.

    Returns None if no unambiguous match (fail-open).
    """
    if not project or not LOG_DIR.is_dir():
        return None

    # Glob for heartbeat files matching project name
    candidates = sorted(
        LOG_DIR.glob(f"{project}-*.heartbeat.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,  # newest first
    )

    if not candidates:
        return None

    # If we can't cross-check start time, only return if there's exactly one
    if task_start_dt is None:
        if len(candidates) == 1:
            return candidates[0]
        log.debug("Multiple heartbeat files for %s, no start_dt to disambiguate", project)
        return None

    # Cross-check started_at in each candidate
    matched: list[Path] = []
    for hb_path in candidates:
        try:
            data = json.loads(hb_path.read_text())
            hb_started = _parse_iso(data.get("started_at", ""))
            if hb_started is None:
                continue
            delta = abs((hb_started - task_start_dt).total_seconds())
            if delta <= STARTED_AT_TOLERANCE:
                matched.append(hb_path)
        except (json.JSONDecodeError, OSError):
            continue

    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        log.warning(
            "Ambiguous: %d heartbeat files match project=%s start_dt=%s — fail-open",
            len(matched), project, task_start_dt,
        )
    return None


def read_heartbeat(hb_path: Path) -> dict | None:
    """Read and parse heartbeat JSON. Returns None on failure."""
    try:
        return json.loads(hb_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Process liveness check
# ---------------------------------------------------------------------------

def _find_claude_pid(pueue_task_id: int) -> int | None:
    """Find the PID of the claude process for a pueue task.

    Pueue spawns a shell which runs run-agent.sh → claude-runner.py → claude CLI.
    We look for a process whose cmdline contains 'claude' and whose ancestor
    chain includes a process started by pueue.

    Returns the claude CLI PID, or None if not found.
    """
    try:
        # Use pueue log to get PID info — not reliable; instead scan /proc
        # for processes whose cmdline matches the claude pattern and whose
        # parent chain includes pueue-managed shell
        r = subprocess.run(
            ["pgrep", "-f", f"claude.*--max-turns"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        # Return first match — if multiple, we'll check children anyway
        pids = [int(p) for p in r.stdout.strip().split("\n") if p.strip()]
        return pids[0] if pids else None
    except Exception:
        return None


def is_process_idle(pueue_task_id: int) -> bool | None:
    """Check if the claude process for a pueue task is idle.

    Returns True if idle (safe to reap), False if busy, None if unable to determine.
    On None, caller should fail-open (not kill).
    """
    claude_pid = _find_claude_pid(pueue_task_id)
    if claude_pid is None:
        # Can't find the process — could be already dead or pgrep failed
        # Check if the pueue task itself has children
        return _check_pueue_children_idle(pueue_task_id)

    # Check 1: Does the claude process have active children?
    # Active children = tool execution in progress
    try:
        r = subprocess.run(
            ["pgrep", "-P", str(claude_pid)],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            # Has children — tool may be running
            child_pids = r.stdout.strip().split("\n")
            log.debug("claude pid=%d has %d children — checking CPU", claude_pid, len(child_pids))
            # Check CPU of children over sample window
            return _sample_cpu_idle(child_pids)
    except Exception:
        pass

    # Check 2: CPU of claude process itself
    return _sample_cpu_idle([str(claude_pid)])


def _check_pueue_children_idle(pueue_task_id: int) -> bool | None:
    """Fallback: check if pueue task's process tree has any CPU activity."""
    try:
        # pgrep for processes with pueue in ancestry is unreliable;
        # just return None (fail-open)
        return None
    except Exception:
        return None


def _sample_cpu_idle(pids: list[str]) -> bool | None:
    """Sample CPU usage of PIDs over a short window. True = idle."""
    try:
        # Read /proc/<pid>/stat for utime+stime, wait, read again
        samples_before: dict[str, int] = {}
        for pid in pids:
            stat_path = Path(f"/proc/{pid}/stat")
            if not stat_path.exists():
                continue
            fields = stat_path.read_text().split()
            if len(fields) < 15:
                continue
            # utime (field 14) + stime (field 15) in clock ticks
            samples_before[pid] = int(fields[13]) + int(fields[14])

        if not samples_before:
            return None

        time.sleep(CPU_SAMPLE_SECONDS)

        total_delta = 0
        for pid, before in samples_before.items():
            stat_path = Path(f"/proc/{pid}/stat")
            if not stat_path.exists():
                continue
            fields = stat_path.read_text().split()
            if len(fields) < 15:
                continue
            after = int(fields[13]) + int(fields[14])
            total_delta += after - before

        # Convert clock ticks to CPU percentage
        clk_tck = os.sysconf("SC_CLK_TCK")
        cpu_seconds = total_delta / clk_tck
        cpu_percent = (cpu_seconds / CPU_SAMPLE_SECONDS) * 100

        log.debug("CPU sample: %.1f%% over %ds (pids=%s)", cpu_percent, CPU_SAMPLE_SECONDS, pids)
        return cpu_percent < CPU_IDLE_THRESHOLD

    except Exception as exc:
        log.debug("CPU sampling failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Kill + notify
# ---------------------------------------------------------------------------

def kill_task(pueue_id: int) -> bool:
    """Kill a pueue task. Returns True on success."""
    try:
        r = subprocess.run(
            ["pueue", "kill", str(pueue_id)],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            log.info("Killed pueue task %d", pueue_id)
            return True
        log.warning("pueue kill %d exit %d: %s", pueue_id, r.returncode, r.stderr[:200])
        return False
    except Exception as exc:
        log.warning("pueue kill %d failed: %s", pueue_id, exc)
        return False


def notify_reap(project: str, pueue_id: int, stale_minutes: float) -> None:
    """Fire Hermes event about reaped session."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from event_writer import notify
        # event_writer.notify(project_path, skill, status, message, artifact_rel)
        # Use SCRIPT_DIR as project_path (infra event, not per-project)
        notify(
            str(SCRIPT_DIR),
            "heartbeat_reaper",
            "failed",
            (
                f"SESSION_REAPED: pueue#{pueue_id} project={project} "
                f"stale {stale_minutes:.0f}min — killed wedged session"
            ),
        )
    except Exception as exc:
        log.warning("Failed to notify about reap: %s", exc)


# ---------------------------------------------------------------------------
# Main reaper logic
# ---------------------------------------------------------------------------

def reap_stale_sessions() -> int:
    """Scan Running claude-runner tasks and kill wedged ones.

    Returns count of reaped sessions.
    """
    now = datetime.now(tz=timezone.utc)
    tasks = get_running_claude_tasks()
    if not tasks:
        log.debug("No running claude-runner tasks")
        return 0

    reaped = 0
    for task in tasks:
        tid = task["id"]
        project = task["project"]
        start_dt = task["start_dt"]

        # Grace period: skip young tasks
        if start_dt is not None:
            age = (now - start_dt).total_seconds()
            if age < GRACE_SECONDS:
                log.debug("Task %d project=%s too young (%.0fs) — skip", tid, project, age)
                continue
        else:
            # Can't determine age — skip (fail-open)
            log.debug("Task %d project=%s no start_dt — skip", tid, project)
            continue

        # Find heartbeat file
        hb_path = find_heartbeat_file(project, start_dt)
        if hb_path is None:
            # No heartbeat yet — could be still initializing within grace,
            # or ambiguous collision — fail-open
            if age < GRACE_SECONDS + 120:
                log.debug("Task %d project=%s no heartbeat, still in extended grace — skip", tid, project)
            else:
                log.warning("Task %d project=%s no heartbeat after %.0fs — skip (fail-open)", tid, project, age)
            continue

        # Read heartbeat
        hb_data = read_heartbeat(hb_path)
        if hb_data is None:
            log.warning("Task %d project=%s unreadable heartbeat — skip", tid, project)
            continue

        updated_at = _parse_iso(hb_data.get("updated_at", ""))
        if updated_at is None:
            log.warning("Task %d project=%s heartbeat missing updated_at — skip", tid, project)
            continue

        # Check staleness
        stale_seconds = (now - updated_at).total_seconds()
        if stale_seconds < STALE_SECONDS:
            log.debug(
                "Task %d project=%s heartbeat fresh (%.0fs ago) — ok",
                tid, project, stale_seconds,
            )
            continue

        stale_minutes = stale_seconds / 60
        log.info(
            "Task %d project=%s heartbeat STALE (%.1f min) — checking process liveness",
            tid, project, stale_minutes,
        )

        # Process liveness cross-check
        idle = is_process_idle(tid)
        if idle is None:
            log.warning(
                "Task %d project=%s stale %.1fmin but liveness check inconclusive — skip (fail-open)",
                tid, project, stale_minutes,
            )
            continue
        if not idle:
            log.info(
                "Task %d project=%s stale %.1fmin but process is BUSY — skip (long tool?)",
                tid, project, stale_minutes,
            )
            continue

        # STALE + IDLE → kill
        log.warning(
            "REAPING task %d project=%s — stale %.1fmin + idle process",
            tid, project, stale_minutes,
        )
        if kill_task(tid):
            notify_reap(project, tid, stale_minutes)
            reaped += 1

    return reaped


def main() -> None:
    reaped = reap_stale_sessions()
    if reaped > 0:
        log.info("Reaped %d wedged session(s)", reaped)


if __name__ == "__main__":
    main()
