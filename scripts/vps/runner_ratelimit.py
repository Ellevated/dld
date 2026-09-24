#!/usr/bin/env python3
"""
Module: runner_ratelimit
Role: detect a subscription rate-limit rejection in the SDK message stream, fold
      events into a run-log summary, decide whether the run's exit code should
      become 5 (`rate_limited`), and — on exit 5 — open the fleet-wide pause
      window and send the one alert for it (TECH-226).
Uses: datetime, logging, time (stdlib); event_writer.notify, fleet_pause.set_pause
      (both stdlib-only siblings — this module still never imports the SDK)
Used by: runner_loop.py (from_message, per message in consume),
         claude-runner.py (summary + decide_exit after the run; on_rejected from
         main(), after asyncio.run — TECH-226 Task 2)

23.09 the fleet hit the 5h Max subscription window mid-run. The CLI sends a
synthetic `AssistantMessage` (`error: "rate_limit"`) and, when the server includes
one, a `RateLimitEvent` — but nothing raises, so the run finished as a plain
`exit_code: 1` with an empty stderr and the reason was found only by reading the
session transcript by hand. This module owns the exit-5 decision the same way
`runner_refusal` owns exit-4: its own module, its own tests, ADR-024 respected.
See TECH-225 Design.

TECH-226 adds `on_rejected`: the fleet must stop hammering a closed window and
the founder must hear about it exactly once, regardless of how many parallel
runs hit exit 5 in the same window.
"""

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import event_writer
import fleet_pause

logger = logging.getLogger("claude-runner")

_RATE_LIMIT_EVENT_LIMIT = 10
_UNKNOWN_RESET_GRACE = 3600
_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
_HELSINKI = "Europe/Helsinki"


def from_message(message) -> dict | None:
    """Recognise a rate-limit signal in one SDK message. None when there is none.

    Two shapes reach us:

    1. A `RateLimitEvent` — duck-typed by the presence of `rate_limit_info`, not
       isinstance (the module never imports the SDK). Any status is recorded,
       `allowed_warning` included, for a future proactive throttle (TECH-226).
    2. `AssistantMessage.error == "rate_limit"` — the synthetic decline the CLI
       sends when the server rejects the request outright. No `rate_limit_info`
       accompanies it, so the status is always `rejected`.

    The assistant's own text is never read — an agent talking about limits (the
    TECH-225 spec itself, for instance) must not trigger it.
    """
    info = getattr(message, "rate_limit_info", None)
    if info is not None:
        return {
            "source": "event",
            "status": getattr(info, "status", None),
            "resets_at": getattr(info, "resets_at", None),
            "rate_limit_type": getattr(info, "rate_limit_type", None),
            "utilization": getattr(info, "utilization", None),
            "overage_status": getattr(info, "overage_status", None),
        }
    if getattr(message, "error", None) == "rate_limit":
        return {"source": "assistant_error", "status": "rejected"}
    return None


def summary(events: list) -> dict:
    """Fold rate-limit events into the run-log block. Always all eight keys."""
    rejected = any(e.get("status") == "rejected" for e in events)
    resets_at = None
    rate_limit_type = None
    utilizations = []
    sources = set()
    for event in events:
        sources.add(event["source"])
        if event.get("resets_at") is not None:
            resets_at = event["resets_at"]
        if event.get("rate_limit_type") is not None:
            rate_limit_type = event["rate_limit_type"]
        if event.get("utilization") is not None:
            utilizations.append(event["utilization"])
    resets_at_iso = (
        datetime.fromtimestamp(resets_at, tz=timezone.utc).isoformat()
        if resets_at is not None
        else None
    )
    return {
        "detected": bool(events),
        "rejected": rejected,
        "rate_limit_type": rate_limit_type,
        "resets_at": resets_at,
        "resets_at_iso": resets_at_iso,
        "utilization_max": max(utilizations) if utilizations else None,
        "sources": sorted(sources),
        "events": events[:_RATE_LIMIT_EVENT_LIMIT],
    }


def decide_exit(state: dict, rl: dict) -> int:
    """5 on a rejected rate limit with no successful result (ADR-024), else unchanged.

    Only upgrades exit codes 0/1/2/3 — 124 (timeout), 4 (refusal) and 143
    (sigterm) are more specific and must not be overwritten. `state` is read-only.
    """
    result_ok = state["result_received"] and not state["result_is_error"]
    if rl["rejected"] and not result_ok and state["exit_code"] in (0, 1, 2, 3):
        logger.warning(
            "RATE_LIMITED type=%s resets_at=%s exit %d->5",
            rl.get("rate_limit_type"),
            rl.get("resets_at"),
            state["exit_code"],
        )
        return 5
    return state["exit_code"]


def _local_dt(ts: float) -> datetime:
    """`ts` in Europe/Helsinki, falling back to UTC when tzdata is unavailable."""
    try:
        tz = ZoneInfo(_HELSINKI)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    return datetime.fromtimestamp(ts, tz=tz)


def _duration_words(seconds: float) -> str:
    total = max(int(seconds), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days >= 1:
        return f"{days} д {hours} ч"
    if hours >= 1:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"


def _alert_text(until: float, rate_limit_type: str, known: bool, now: float) -> str:
    """Russian alert text for the one Hermes event a pause opens. See TECH-226 Scope item 8."""
    if not known:
        return (
            f"Флот на паузе по лимиту подписки ({rate_limit_type}): время сброса "
            "неизвестно, повторная проверка через 60 мин. "
            "Снять вручную: rm scripts/vps/.rate-limited-until"
        )
    now_dt = _local_dt(now)
    until_dt = _local_dt(until)
    duration = _duration_words(until - now)
    if now_dt.date() == until_dt.date():
        when = f"до {until_dt:%H:%M} (через {duration})"
    else:
        weekday = _WEEKDAYS[until_dt.weekday()]
        when = f"до {weekday} {until_dt:%d.%m %H:%M} ({duration})"
    return (
        f"Флот на паузе по лимиту подписки ({rate_limit_type}) {when}. "
        "Снять вручную: rm scripts/vps/.rate-limited-until"
    )


def on_rejected(rl: dict, source: str, now: float | None = None) -> None:
    """Open the fleet pause window on a rejected rate limit, alerting once.

    Called from `claude-runner.py:main()` after the process exits 5. `rl` is the
    run's `rate_limit` summary block. The whole body is best-effort: a failed
    alert must never turn a clean exit 5 into a crashed `main()` (which callback
    would read as `blocked`).
    """
    try:
        if now is None:
            now = time.time()
        until = rl.get("resets_at") or now + _UNKNOWN_RESET_GRACE
        known = rl.get("resets_at") is not None
        rate_limit_type = rl.get("rate_limit_type") or "unknown"
        opened = fleet_pause.set_pause(until, rate_limit_type, source, now=now)
        if opened:
            event_writer.notify(
                str(fleet_pause.SCRIPT_DIR),
                "rate_limit",
                "failed",
                _alert_text(until, rate_limit_type, known, now),
            )
    except Exception as exc:  # noqa: BLE001 — a failed alert must not crash the runner
        logger.warning("on_rejected failed: %s", exc)
