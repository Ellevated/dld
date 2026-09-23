#!/usr/bin/env python3
"""
Module: runner_ratelimit
Role: detect a subscription rate-limit rejection in the SDK message stream, fold
      events into a run-log summary, and decide whether the run's exit code should
      become 5 (`rate_limited`).
Uses: datetime (stdlib only — duck-typed over SDK messages, never imports the SDK)
Used by: runner_loop.py (from_message, per message in consume),
         claude-runner.py (summary + decide_exit after the run)

23.09 the fleet hit the 5h Max subscription window mid-run. The CLI sends a
synthetic `AssistantMessage` (`error: "rate_limit"`) and, when the server includes
one, a `RateLimitEvent` — but nothing raises, so the run finished as a plain
`exit_code: 1` with an empty stderr and the reason was found only by reading the
session transcript by hand. This module owns the exit-5 decision the same way
`runner_refusal` owns exit-4: its own module, its own tests, ADR-024 respected.
See TECH-225 Design.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("claude-runner")

_RATE_LIMIT_EVENT_LIMIT = 10


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
