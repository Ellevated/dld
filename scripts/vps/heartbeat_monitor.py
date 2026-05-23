#!/usr/bin/env python3
"""Heartbeat monitor — fires Hermes event if orchestrator heartbeat is stale.

Cron entry installed by setup-vps.sh:
    */5 * * * * python3 /path/to/scripts/vps/heartbeat_monitor.py

Reads scripts/vps/.orchestrator-heartbeat (written each cycle by orchestrator
main loop). If the timestamp is older than STALE_THRESHOLD_MINUTES, calls
event_writer.notify with ORCHESTRATOR_STALE.

Exit codes (consumed by cron log only):
    0 — heartbeat fresh OR alert fired successfully
    0 — also when heartbeat file missing/unparseable (best-effort, no spam)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HEARTBEAT_FILE = SCRIPT_DIR / ".orchestrator-heartbeat"
STALE_THRESHOLD_MINUTES = 10


def main() -> None:
    if not HEARTBEAT_FILE.is_file():
        print("WARN: no heartbeat file found", file=sys.stderr)
        return
    last_beat_str = HEARTBEAT_FILE.read_text().strip()
    try:
        last_beat = datetime.fromisoformat(last_beat_str.replace("Z", "+00:00"))
    except ValueError:
        print(f"WARN: unparseable heartbeat: {last_beat_str}", file=sys.stderr)
        return
    age = datetime.now(tz=timezone.utc) - last_beat
    if age > timedelta(minutes=STALE_THRESHOLD_MINUTES):
        print(f"ALERT: orchestrator heartbeat stale ({age})", file=sys.stderr)
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from event_writer import notify

            notify("dld", f"ORCHESTRATOR_STALE: last heartbeat {age} ago")
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: could not fire Hermes event: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
