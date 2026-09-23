#!/usr/bin/env python3
"""
Module: event_writer
Role: Write OpenClaw pending-events JSON and wake the Hermes agent (`hermes -z`).
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


WAKE_LOG = Path(__file__).resolve().parent / "logs" / "hermes-wake.log"


def _notify_target() -> str:
    """Where Hermes sends an alert: HERMES_NOTIFY_TARGET from the environment or the
    sibling .env (cron callers do not load it), else Hermes' home Telegram channel."""
    target = os.environ.get("HERMES_NOTIFY_TARGET")
    env_file = Path(__file__).resolve().parent / ".env"
    if not target and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == "HERMES_NOTIFY_TARGET":
                target = value.strip().strip("'\"")
    return target or "telegram"


def wake_hermes(project_path: str, skill: str, status: str, event_file: Path | None = None) -> bool:
    """Wake Hermes via CLI in fire-and-forget mode. Returns True on dispatch.

    Hermes replaced OpenClaw (TECH-181) and is a chat agent. We spawn it detached so
    callback doesn't block on AI latency. Best-effort, non-critical.

    `hermes -z` (one-shot), not `-q`: Hermes 2026.8 dropped the top-level `-q`, and
    from 2026-08-13 to 2026-09-23 every wake died on an argparse error nobody saw,
    because output went to DEVNULL — no pipeline alert reached Telegram in that time.
    Output now goes to WAKE_LOG. The prompt names the one event file: pending-events/
    is never emptied (911 files in awardybot by then) and is history, not a queue.

    Binary path: $HERMES_BIN or ~/.local/bin/hermes.
    """
    hermes_bin = os.environ.get("HERMES_BIN") or os.path.expanduser("~/.local/bin/hermes")
    if not os.path.isfile(hermes_bin):
        log.debug("hermes binary not found at %s", hermes_bin)
        return False
    project_id = Path(project_path).name
    where = event_file or f"{project_path}/ai/openclaw/pending-events/"
    prompt = (
        f"Новое pipeline-событие DLD: project={project_id} skill={skill} status={status}. "
        f"Прочитай только {where} — остальные файлы в pending-events старые, их не трогай. "
        f"Если это сбой, блокировка или что-то, что требует решения Олега, отправь в "
        f"Telegram ({_notify_target()}) одно короткое сообщение: проект, спека, что "
        f"случилось, что сделать. Рядовое успешное завершение без проблем — не отправляй."
    )
    try:
        WAKE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with WAKE_LOG.open("a", encoding="utf-8") as out:
            out.write(
                f"--- {datetime.now(tz=timezone.utc).isoformat()} {project_id} {skill} {status}\n"
            )
            out.flush()
            subprocess.Popen(
                [hermes_bin, "-z", prompt],
                stdout=out,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        log.info("hermes wake dispatched: project=%s skill=%s", project_id, skill)
        return True
    except (FileNotFoundError, OSError) as exc:
        log.warning("hermes wake failed: %s", exc)
        return False


def notify(
    project_path: str,
    skill: str,
    status: str,
    message: str,
    artifact_rel: str = "",
) -> None:
    """Write event + wake Hermes. Main entry point for imports."""
    event_file = write_event(project_path, skill, status, message, artifact_rel)
    wake_hermes(project_path, skill, status, event_file)


def notify_circuit_event(action: str, count: int, window_min: int) -> None:
    """Emit a circuit-breaker event via the OpenClaw pipeline.

    TECH-169: distinct from regular notify() — uses skill='circuit_breaker'
    so OpenClaw can route to a dedicated alerts channel.

    Args:
        action: 'open' | 'reset' | 'heal'.
        count: Number of demotes that triggered (or 0 for reset/heal).
        window_min: Window minutes used in threshold calc.
    """
    # Use SCRIPT_DIR as project_path so the event lands in scripts/vps/
    # ai/openclaw/pending-events/ — separate from per-project pipelines.
    project_path = str(Path(__file__).resolve().parent)
    if action == "open":
        message = (
            f"CIRCUIT_OPEN: {count} demotes in {window_min} min — "
            f"callback halted, claude-runner paused. "
            f"Run `python3 callback.py --reset-circuit` to resume."
        )
        status = "failed"
    elif action == "reset":
        message = "CIRCUIT_RESET: operator reset — decisions cleared, claude-runner resumed."
        status = "done"
    elif action == "heal":
        message = f"CIRCUIT_HEAL: auto-closed after {window_min} min idle."
        status = "done"
    else:
        message = f"circuit event: {action}"
        status = "done"
    notify(project_path, "circuit_breaker", status, message, "")


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
