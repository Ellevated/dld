#!/usr/bin/env python3
"""
Module: orchestrator_slots
Role: pueue primitives — liveness probe, duplicate-dispatch guards, slot watchdog,
      task submission, projects.json hot-reload.
Uses: db (import), subprocess (pueue CLI)
Used by: orchestrator (facade re-export), orchestrator_inbox
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402

log = logging.getLogger("orchestrator")

_projects_mtime: float = 0.0


def sync_projects() -> None:
    """Hot-reload projects.json into SQLite when mtime changes."""
    global _projects_mtime
    projects_json = os.environ.get("PROJECTS_JSON", str(SCRIPT_DIR / "projects.json"))
    if not os.path.isfile(projects_json):
        log.warning("projects.json not found: %s", projects_json)
        return
    mtime = os.path.getmtime(projects_json)
    if mtime == _projects_mtime:
        return
    _projects_mtime = mtime
    with open(projects_json) as f:
        projects = json.load(f)
    db.seed_projects_from_json(projects)
    log.info("synced %d projects from %s", len(projects), projects_json)


_LIVE_PUEUE_STATES = frozenset({"Running", "Locked", "Queued", "Stashed", "Paused"})


def get_live_pueue_ids() -> set[int] | None:
    """Return live pueue task IDs. None on failure (skip watchdog, no false release).

    Modern pueue versions return `status` as a dict like `{"Queued": {...}}` or
    `{"Running": {...}}`. Older versions may return a bare string. We handle both.
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            log.warning("pueue status exit %d: %s", r.returncode, r.stderr[:200])
            return None
        data = json.loads(r.stdout)
        live: set[int] = set()
        for tid_str, task in data.get("tasks", {}).items():
            st = task.get("status", "")
            state_name: str = ""
            if isinstance(st, dict):
                state_name = next(iter(st.keys()), "")
            elif isinstance(st, str):
                state_name = st
            if state_name in _LIVE_PUEUE_STATES:
                live.add(int(tid_str))
        return live
    except Exception as exc:
        log.warning("get_live_pueue_ids failed: %s", exc)
        return None


def pueue_has_active_label(label: str) -> bool:
    """Return True if pueue already has a Running/Queued task with this label.

    Belt-and-suspenders guard against duplicate dispatch — even if the slot
    table is stale or out-of-sync, this catches the dup at the pueue layer.
    On failure returns False (fail-open — better to risk a duplicate than
    block all dispatches).
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        for _tid, task in data.get("tasks", {}).items():
            if task.get("label") != label:
                continue
            st = task.get("status", "")
            state_name = next(iter(st.keys()), "") if isinstance(st, dict) else st
            if state_name in _LIVE_PUEUE_STATES:
                return True
        return False
    except Exception as exc:
        log.warning("pueue_has_active_label check failed: %s", exc)
        return False


def pueue_has_active_spec(spec_id: str) -> bool:
    """Rule 8: True if any live pueue task has label ending with ':<spec_id>' (any project).

    Prevents cross-project double-dispatch of the same spec_id.
    Fail-open (returns False) so a pueue outage doesn't block all dispatches.
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        suffix = f":{spec_id}"
        for _tid, task in data.get("tasks", {}).items():
            label = task.get("label", "")
            if not label.endswith(suffix):
                continue
            st = task.get("status", "")
            state_name = next(iter(st.keys()), "") if isinstance(st, dict) else st
            if state_name in _LIVE_PUEUE_STATES:
                return True
        return False
    except Exception as exc:
        log.warning("pueue_has_active_spec check failed: %s", exc)
        return False


def release_orphan_slots() -> int:
    """Release slots whose pueue tasks are gone. 0 if pueue unreachable (BUG-162)."""
    live_ids = get_live_pueue_ids()
    if live_ids is None:
        return 0
    occupied = db.get_occupied_slots()
    if not occupied:
        return 0
    released = 0
    for slot in occupied:
        pueue_id = slot["pueue_id"]
        if pueue_id not in live_ids:
            pid = db.release_slot(pueue_id)
            log.warning(
                "watchdog: released orphan slot=%d project=%s pueue_id=%d acquired_at=%s",
                slot["slot_number"],
                pid or slot.get("project_id"),
                pueue_id,
                slot.get("acquired_at", "unknown"),
            )
            released += 1
    if released:
        log.info("watchdog: released %d orphan slot(s) total", released)
    return released


def is_agent_running(project_id: str) -> bool:
    """Return True if a pueue task with this project's label prefix is Running."""
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(r.stdout)
        for task in data.get("tasks", {}).values():
            label = task.get("label", "")
            status = task.get("status", "")
            if (
                label.startswith(f"{project_id}:")
                and isinstance(status, dict)
                and "Running" in status
            ):
                return True
    except Exception:
        pass
    return False


def _pueue_add(group: str, label: str, cmd: list, env: dict | None = None) -> int | None:
    """Submit task to pueue group. Returns pueue task ID or None."""
    pueue_cmd = ["pueue", "add", "--group", group, "--label", label, "--print-task-id", "--"] + cmd
    run_env = {**os.environ, **env} if env else None
    try:
        r = subprocess.run(pueue_cmd, capture_output=True, text=True, timeout=30, env=run_env)
        for ln in r.stdout.strip().splitlines():
            ln = ln.strip()
            if ln.isdigit():
                return int(ln)
            m = re.search(r"(\d+)", ln)
            if m:
                return int(m.group(1))
        log.warning("pueue add: no task ID in output: %s", r.stdout[:200])
    except Exception as exc:
        log.error("pueue add failed: %s", exc)
    return None
