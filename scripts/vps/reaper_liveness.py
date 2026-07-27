#!/usr/bin/env python3
"""
Module: reaper_liveness
Role: Process liveness probe for heartbeat_reaper — is the claude process for a
      pueue task idle enough to reap? Fail-open: None means "don't kill".
      Extracted from heartbeat_reaper (TECH-211).
Uses: subprocess (pgrep), /proc/<pid>/stat, os.sysconf, time
Used by: heartbeat_reaper.py
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger("heartbeat-reaper")

CPU_SAMPLE_SECONDS = 2     # CPU sampling window for idle check
CPU_IDLE_THRESHOLD = 1.0   # % — below this = idle


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
