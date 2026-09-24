#!/usr/bin/env python3
"""
Module: fleet_pause
Role: single source of "closed until X" — a rate-limit pause window the whole
      fleet respects. `run-agent.sh` checks it before every claude launch, so
      this module stays stdlib-only (no `db`, no SDK import).
Source of Truth: scripts/vps/.rate-limited-until (JSON marker file)

Uses: json, logging, os, sys, time, pathlib, datetime (all stdlib)

Used by:
  - run-agent.sh: `--check` guard before exec, exit 75 = EX_TEMPFAIL
  - runner_ratelimit.py: set_pause() on exit 5 (TECH-226 Task 2)
  - dispatch_one.py, orchestrator_queue.py: active_pause() gates dispatch
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("fleet_pause")

SCRIPT_DIR = Path(__file__).resolve().parent
MARKER = SCRIPT_DIR / ".rate-limited-until"
EX_TEMPFAIL = 75

_LOCK_TIMEOUT = 2.0
_LOCK_POLL = 0.02
_LOCK_STALE = 30.0


def active_pause(now: float | None = None) -> dict | None:
    """Return the active pause marker, or None when absent, expired, or corrupt."""
    if now is None:
        now = time.time()
    try:
        data = json.loads(MARKER.read_text())
        if data["until"] <= now:
            return None
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        log.warning("bad marker %s: %s", MARKER, exc)
        return None
    return data


def _acquire_lock(lock_path: Path) -> bool:
    deadline = time.monotonic() + _LOCK_TIMEOUT
    while time.monotonic() < deadline:
        try:
            os.close(os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > _LOCK_STALE:
                    lock_path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            time.sleep(_LOCK_POLL)
    return False


def _write(until: float, rate_limit_type: str, source: str) -> None:
    data = {
        "until": until,
        "until_iso": datetime.fromtimestamp(until, tz=timezone.utc).isoformat(),
        "rate_limit_type": rate_limit_type,
        "set_at": time.time(),
        "source": source,
    }
    tmp = MARKER.parent / (MARKER.name + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, MARKER)


def set_pause(until: float, rate_limit_type: str, source: str, now: float | None = None) -> bool:
    """Open or extend the pause window. Returns True iff this call opened it."""
    if now is None:
        now = time.time()
    if until <= now:
        return False
    lock_path = MARKER.parent / (MARKER.name + ".lock")
    if not _acquire_lock(lock_path):
        log.warning("could not acquire lock %s", lock_path)
        return False
    try:
        cur = active_pause(now)
        if cur is not None:
            if until > cur["until"]:
                _write(until, rate_limit_type, source)
            return False
        _write(until, rate_limit_type, source)
        return True
    finally:
        lock_path.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "--check":
        return 0
    pause = active_pause()
    if pause is None:
        return 0
    print(json.dumps({"skipped": "fleet_paused", **pause}))
    return EX_TEMPFAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
