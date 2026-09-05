"""Cost estimate for runs that never reach a ResultMessage.

`total_cost_usd` arrives only on the final `ResultMessage`. A run killed by the
wall-clock timeout never gets one, so it is logged as **$0.00** — and those are the
most expensive runs there are. Measured 2026-09-05 over the first 12 autopilot runs on
the new prompts: 6 timed out, at 370–630 turns each against 50–120 for a normal run,
and every one of them recorded as costing nothing. A third of the spend was invisible,
which is why "timeouts are cheap, they just take wall-clock" survived as long as it did.

`AssistantMessage.usage` is streamed per turn (`claude_agent_sdk` 0.1.81 — the field is
on the dataclass), so the tokens are already in hand when the timeout fires. This module
prices them.

**The number is a floor, not a bill.** It counts the usage the SDK actually streamed to
this process; anything the CLI did not report is not in it. Runs that end normally keep
using the ResultMessage figure — `cost_source` in the run log says which one you are
reading. Never sum an estimated cost with a billed one and present the total as spend.

stdlib only, no SDK import: the runner's tests load these modules with a fake SDK in
`sys.modules`, and duck-typing keeps this one out of that dance.
"""

import logging

logger = logging.getLogger("claude-runner")

# USD per million tokens: (input, output). Source: rules/model-capabilities.md,
# which is checked against platform.claude.com rather than from memory.
# Sonnet's introductory $2/$10 expired 2026-08-31 — this is the standard rate.
_PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
}
_DEFAULT_PRICE = _PRICES["claude-opus-5"]  # the pinned main-loop model

# Anthropic cache multipliers against the model's base input rate.
_CACHE_WRITE_5M = 1.25
_CACHE_WRITE_1H = 2.0
_CACHE_READ = 0.1


def _price_for(model: str) -> tuple[float, float]:
    """Match a reported model id to a price row by longest-prefix, never by equality.

    Reported ids carry build suffixes (`claude-haiku-4-5-20251001`), and an unknown
    model must not silently price at zero — an unpriced model would reintroduce the
    exact blind spot this module exists to close, just one generation later.
    """
    if not model:
        return _DEFAULT_PRICE
    for known in sorted(_PRICES, key=len, reverse=True):
        if model.startswith(known):
            return _PRICES[known]
    logger.warning(
        "COST ESTIMATE: model %r is not in the price table — pricing it as opus-5. "
        "Add it to runner_cost._PRICES (source: rules/model-capabilities.md).",
        model,
    )
    return _DEFAULT_PRICE


def _field(usage: dict, *names: str) -> int:
    """Read a usage counter under either camelCase or snake_case."""
    for n in names:
        if n in usage:
            try:
                return int(usage[n] or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def accumulate(state: dict, message) -> None:
    """Fold one AssistantMessage's usage into `state["stream_usage"]`, keyed by model.

    Caller does the isinstance check. Best-effort by construction (ADR-004): a shape
    the SDK changes under us must not turn a finished run into a crashed runner.
    """
    usage = getattr(message, "usage", None)
    if not usage:
        return
    if not isinstance(usage, dict):
        usage = getattr(usage, "__dict__", {}) or {}
    model = getattr(message, "model", "") or ""
    bucket = state.setdefault("stream_usage", {}).setdefault(
        model,
        {"input": 0, "output": 0, "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0},
    )
    bucket["input"] += _field(usage, "input_tokens", "inputTokens")
    bucket["output"] += _field(usage, "output_tokens", "outputTokens")
    bucket["cache_read"] += _field(usage, "cache_read_input_tokens", "cacheReadInputTokens")

    # cache_creation is nested when the API splits it by TTL, flat otherwise.
    # Both shapes appear; the flat one is priced at the 5m rate, which is the
    # cheaper of the two — this stays a floor.
    cc = usage.get("cache_creation")
    if isinstance(cc, dict):
        bucket["cache_write_5m"] += _field(cc, "ephemeral_5m_input_tokens")
        bucket["cache_write_1h"] += _field(cc, "ephemeral_1h_input_tokens")
    else:
        bucket["cache_write_5m"] += _field(
            usage, "cache_creation_input_tokens", "cacheCreationInputTokens"
        )


def estimate(stream_usage: dict) -> float:
    """Price accumulated per-model usage. Returns USD, rounded to 4 decimals."""
    total = 0.0
    for model, u in (stream_usage or {}).items():
        price_in, price_out = _price_for(model)
        total += (
            u.get("input", 0) * price_in
            + u.get("output", 0) * price_out
            + u.get("cache_write_5m", 0) * price_in * _CACHE_WRITE_5M
            + u.get("cache_write_1h", 0) * price_in * _CACHE_WRITE_1H
            + u.get("cache_read", 0) * price_in * _CACHE_READ
        ) / 1_000_000
    return round(total, 4)


def apply_to_state(state: dict) -> float:
    """Fill in `cost_usd` from streamed usage when the run produced no billed figure.

    Returns the cost now in `state`. Leaves a billed figure untouched: a ResultMessage
    arrived means the CLI priced the whole session, including subagent turns this
    process may never have seen.
    """
    if state.get("cost_usd"):
        state["cost_source"] = "result_message"
        return state["cost_usd"]
    est = estimate(state.get("stream_usage") or {})
    if est <= 0:
        state["cost_source"] = "unavailable"
        return state.get("cost_usd", 0.0)
    state["cost_usd"] = est
    state["cost_source"] = "estimated_from_stream"
    return est
