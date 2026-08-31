#!/usr/bin/env python3
"""Orchestrator monitor — runs every 30 min via cron.

Checks:
  1. dld-orchestrator.service alive (systemctl --user is-active)
  2. claude-runner pueue group not paused (circuit breaker gate)
  3. Active tasks in pueue (running / queued count)
  4. Recent demotes in callback_decisions (last 35 min window)

Fires event_writer.notify on any anomaly. Idempotent — safe to run frequently.

Cron entry:
    */30 * * * * /path/to/venv/bin/python3 /path/to/orchestrator_monitor.py \
        >> /var/log/dld-orchestrator/orchestrator-monitor.log 2>&1
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FORMAT = "[%(asctime)s] %(levelname)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stderr)
log = logging.getLogger("orchestrator_monitor")

DLD_PROJECT_PATH = str(SCRIPT_DIR.parent.parent)  # projects/dld

DEMOTE_WINDOW_MINUTES = 35  # slightly wider than cron interval to avoid gaps

# pueue lives outside cron's PATH on this host.
EXTRA_PATH = "/usr/local/bin"


def _runtime_env() -> dict[str, str]:
    """Environment that lets `systemctl --user` and `pueue` reach the user session.

    cron starts with no XDG_RUNTIME_DIR and a PATH of /usr/bin:/bin. Without the
    former, `systemctl --user` fails with "Failed to connect to bus" and pueue
    falls back to a socket path the daemon does not listen on — both write to
    stderr and leave stdout EMPTY, so the checks below read a healthy host as a
    dead one. That misread fired ORCHESTRATOR_DOWN + CIRCUIT_BREAKER_TRIPPED
    every 30 min from 2026-05-28 (3910 alerts) while the orchestrator was up.
    """
    env = dict(os.environ)
    getuid = getattr(os, "getuid", None)  # absent on Windows, where dev tests run
    if not env.get("XDG_RUNTIME_DIR") and getuid is not None:
        candidate = Path(f"/run/user/{getuid()}")
        if candidate.is_dir():
            env["XDG_RUNTIME_DIR"] = str(candidate)
    path = env.get("PATH", "")
    if EXTRA_PATH not in path.split(os.pathsep):
        env["PATH"] = os.pathsep.join([p for p in (path, EXTRA_PATH) if p])
    return env


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """subprocess.run with the session environment and a 10s cap."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10,
        env=_runtime_env(),
    )


def check_orchestrator_service() -> tuple[bool, str]:
    """Returns (ok, detail)."""
    try:
        result = _run(["systemctl", "--user", "is-active", "dld-orchestrator.service"])
        state = result.stdout.strip()
        if not state:
            # Empty stdout means systemctl never reached the bus; report the
            # reason instead of an empty detail that reads as "service dead".
            return False, f"systemctl unreachable: {result.stderr.strip() or 'no output'}"
        return state == "active", state
    except Exception as exc:
        return False, f"systemctl error: {exc}"


class PueueUnreachable(RuntimeError):
    """The pueue daemon did not answer at all — distinct from a paused group."""


# pueue renders a failure as an "Error:" block of numbered causes, then a
# "Location:" block, then RUST_BACKTRACE boilerplate:
#
#   Error:
#      0: Failed to initialize client.
#      1: Failed to initialize stream.
#      2: I/O error at path ".../pueue_dld.socket" while connecting to daemon...
#   Location:
#      .../client.rs:85
#   Backtrace omitted. Run with RUST_BACKTRACE=1 ...
#   Run with RUST_BACKTRACE=full to include source snippets.
#
# Taking the last line (as this did until 2026-08-23) reported every daemon
# outage as "Run with RUST_BACKTRACE=full to include source snippets." — the one
# line that says nothing about what broke. The deepest numbered cause is the
# root cause, so prefer that.
_STDERR_NOISE = ("RUST_BACKTRACE", "Backtrace omitted")
_NUMBERED_CAUSE_RE = re.compile(r"^\d+:\s*(.+)$")


def _meaningful_stderr(stderr: str) -> str:
    """The stderr line that actually describes the failure."""
    lines = [ln.strip() for ln in stderr.strip().splitlines() if ln.strip()]
    if not lines:
        return "empty output"

    # Everything from "Location:" onward is call-site noise, including the
    # path line that follows it.
    body: list[str] = []
    for ln in lines:
        if ln.startswith("Location:"):
            break
        body.append(ln)

    causes = [m.group(1) for ln in body if (m := _NUMBERED_CAUSE_RE.match(ln))]
    if causes:
        return causes[-1][:300]

    signal = [ln for ln in body if ln != "Error:" and not any(n in ln for n in _STDERR_NOISE)]
    return (signal[-1] if signal else lines[-1])[:300]


def _pueue_status() -> dict:
    """Parsed `pueue status --json`. Raises PueueUnreachable when the client fails."""
    result = _run(["pueue", "status", "--json"])
    if not result.stdout.strip():
        raise PueueUnreachable(_meaningful_stderr(result.stderr))
    return json.loads(result.stdout)


def check_pueue_group() -> tuple[bool, str, bool]:
    """Returns (ok, detail, daemon_reachable).

    A dead daemon and a tripped circuit breaker both stop all work, but they are
    different incidents with different fixes — `systemctl --user start pueued`
    versus `pueue start --group claude-runner`. Reporting both as
    CIRCUIT_BREAKER_TRIPPED is why the real outage of 2026-08-23 was invisible:
    it read identically to the 3910 false alarms fired between 2026-05-28 and
    the cron-environment fix, so the message carried no information by then.
    """
    try:
        data = _pueue_status()
    except PueueUnreachable as exc:
        return False, f"daemon unreachable: {exc}", False
    except Exception as exc:
        return False, f"pueue error: {exc}", False
    groups = data.get("groups", {})
    cr = groups.get("claude-runner", {})
    status = cr.get("status", "unknown")
    paused = isinstance(status, dict) and "Paused" in status or status == "Paused"
    return not paused, f"claude-runner={status}", True


def count_active_tasks() -> tuple[int, int]:
    """Returns (running_count, queued_count), or (-1, -1) when pueue is unreadable."""
    try:
        tasks = _pueue_status().get("tasks", {})
        running = sum(1 for t in tasks.values() if "Running" in str(t.get("status", "")))
        queued = sum(1 for t in tasks.values() if "Queued" in str(t.get("status", "")))
        return running, queued
    except Exception as exc:
        log.warning("pueue task count failed: %s", exc)
        return -1, -1


def check_recent_demotes() -> tuple[int, list[dict]]:
    """Returns (count, rows) for demotes in last DEMOTE_WINDOW_MINUTES."""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import os

        os.environ.setdefault("DB_PATH", str(SCRIPT_DIR / "orchestrator.db"))
        from db import get_db

        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(minutes=DEMOTE_WINDOW_MINUTES)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT project_id, spec_id, reason, ts
                FROM callback_decisions
                WHERE demoted=1 AND ts > ?
                ORDER BY ts DESC
                """,
                (cutoff,),
            ).fetchall()
        return len(rows), [dict(r) for r in rows]
    except Exception as exc:
        log.warning("DB check failed: %s", exc)
        return -1, []


def main() -> None:
    issues: list[str] = []

    # 1. Service alive?
    svc_ok, svc_detail = check_orchestrator_service()
    if not svc_ok:
        issues.append(f"ORCHESTRATOR_DOWN: {svc_detail}")
        log.error("orchestrator service: %s", svc_detail)
    else:
        log.info("orchestrator service: %s", svc_detail)

    # 2. Queue daemon alive, and circuit breaker not tripped?
    pueue_ok, pueue_detail, daemon_reachable = check_pueue_group()
    if not daemon_reachable:
        issues.append(
            f"PUEUE_DAEMON_DOWN: {pueue_detail} — nothing dispatches; "
            f"fix: systemctl --user start pueued"
        )
        log.error("pueue daemon: %s", pueue_detail)
    elif not pueue_ok:
        issues.append(f"CIRCUIT_BREAKER_TRIPPED: {pueue_detail}")
        log.error("pueue group: %s", pueue_detail)
    else:
        log.info("pueue group: %s", pueue_detail)

    # 3. Active tasks
    running, queued = count_active_tasks()
    log.info("tasks: running=%d queued=%d", running, queued)

    # 4. Recent demotes
    demote_count, demote_rows = check_recent_demotes()
    if demote_count > 0:
        projects = {r["project_id"] for r in demote_rows}
        log.warning("recent demotes=%d projects=%s", demote_count, projects)
        if demote_count >= 3:
            issues.append(
                f"DEMOTE_BURST: {demote_count} demotes in {DEMOTE_WINDOW_MINUTES}min "
                f"({', '.join(sorted(projects))})"
            )
    else:
        log.info("recent demotes=%d", demote_count)

    # Fire notification on any issue
    if issues:
        try:
            from event_writer import notify

            msg = "; ".join(issues) + f" | tasks: running={running} queued={queued}"
            notify(DLD_PROJECT_PATH, "orchestrator_monitor", "failed", msg)
            log.error("alert sent: %s", msg)
        except Exception as exc:
            log.error("could not send alert: %s", exc)
    else:
        log.info("all checks OK (running=%d queued=%d)", running, queued)


if __name__ == "__main__":
    main()
