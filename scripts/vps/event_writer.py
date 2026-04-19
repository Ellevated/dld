#!/usr/bin/env python3
"""
Module: event_writer
Role: Write OpenClaw pending-events JSON and wake OpenClaw CLI.
Uses: json, subprocess (stdlib)
Used by: callback.py (import), night-reviewer.sh (CLI)

Replaces notify.py Telegram layer (ARCH-161).

CLI: python3 event_writer.py <project_path> <skill> <status> <message> [--artifact <path>]
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("event_writer")


def write_event(
    project_path: str,
    skill: str,
    status: str,
    message: str,
    artifact_rel: str = "",
) -> Path:
    """Write pending-event JSON to ai/openclaw/pending-events/.

    Args:
        project_path: Absolute path to project root.
        skill: Skill name (autopilot, qa, reflect, spark, night-review).
        status: Outcome status (done, failed).
        message: Human-readable description.
        artifact_rel: Relative path to artifact file (optional).

    Returns:
        Path to the written event JSON file.
    """
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    events_dir = Path(project_path) / "ai" / "openclaw" / "pending-events"
    events_dir.mkdir(parents=True, exist_ok=True)

    event = {
        "project_id": Path(project_path).name,
        "skill": skill,
        "status": status,
        "message": message,
        "artifact_rel": artifact_rel,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    event_file = events_dir / f"{ts}-{skill}.json"
    event_file.write_text(json.dumps(event, ensure_ascii=False, indent=2))
    log.info("event written: %s", event_file.name)
    return event_file


def wake_openclaw() -> bool:
    """Wake OpenClaw via CLI. Returns True on success.

    Looks for openclaw binary at ~/.npm-global/bin/openclaw.
    Timeout 5s. Best-effort wake, non-critical (BUG-163).
    """
    openclaw_bin = os.path.expanduser("~/.npm-global/bin/openclaw")
    if not os.path.isfile(openclaw_bin):
        log.debug("openclaw binary not found at %s", openclaw_bin)
        return False
    try:
        subprocess.run(
            [openclaw_bin, "system", "event", "--mode", "now", "--text", "pipeline event"],
            timeout=5,
            capture_output=True,
        )
        log.info("openclaw wake sent")
        return True
    except subprocess.TimeoutExpired:
        log.debug("openclaw wake timed out (non-critical)")
        return False
    except (FileNotFoundError, OSError) as exc:
        log.debug("openclaw wake failed (non-critical): %s", exc)
        return False


def notify(
    project_path: str,
    skill: str,
    status: str,
    message: str,
    artifact_rel: str = "",
) -> None:
    """Write event + wake OpenClaw. Main entry point for imports."""
    write_event(project_path, skill, status, message, artifact_rel)
    wake_openclaw()


def main() -> None:
    """CLI entrypoint for bash callers (night-reviewer.sh).

    Usage: python3 event_writer.py <project_path> <skill> <status> <message> [--artifact <path>]
    """
    if len(sys.argv) < 5:
        print(
            "Usage: event_writer.py <project_path> <skill> <status> <message> [--artifact <path>]",
            file=sys.stderr,
        )
        sys.exit(1)

    project_path = sys.argv[1]
    skill = sys.argv[2]
    status = sys.argv[3]
    message = sys.argv[4]
    artifact_rel = ""

    if "--artifact" in sys.argv:
        idx = sys.argv.index("--artifact")
        if idx + 1 < len(sys.argv):
            artifact_rel = sys.argv[idx + 1]

    notify(project_path, skill, status, message, artifact_rel)


if __name__ == "__main__":
    main()
