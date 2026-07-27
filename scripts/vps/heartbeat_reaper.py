#!/usr/bin/env python3
"""
Module: heartbeat_reaper
Role: Cron-driven reaper for wedged claude-runner sessions (TECH-198 Layer B).
Uses: subprocess (pueue status/kill, /proc), json, datetime, pathlib, event_writer,
      reaper_pueue, reaper_liveness (TECH-211)
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
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "logs"
sys.path.insert(0, str(SCRIPT_DIR))

import reaper_liveness  # noqa: E402
import reaper_pueue  # noqa: E402

# Thresholds (seconds)
GRACE_SECONDS = 300        # 5 min — skip tasks younger than this
STALE_SECONDS = 1500       # 25 min — heartbeat older than this = candidate

# started_at tolerance for cross-check (seconds)
STARTED_AT_TOLERANCE = 10

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("heartbeat-reaper")


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
            hb_started = reaper_pueue._parse_iso(data.get("started_at", ""))
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
    tasks = reaper_pueue.get_running_claude_tasks()
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

        updated_at = reaper_pueue._parse_iso(hb_data.get("updated_at", ""))
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
        idle = reaper_liveness.is_process_idle(tid)
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
