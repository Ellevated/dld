#!/usr/bin/env python3
"""
Module: runner_refusal
Role: detect and summarise classifier declines in the SDK message stream.
Uses: (stdlib only — duck-typed over SDK messages, never imports the SDK)
Used by: claude-runner.py (per-message check inside run_task)

A decline arrives inside a normal HTTP 200 with `stop_reason: "refusal"`, so nothing
raises and nothing fails. An empty security review reads exactly like a clean one —
which is why this lives in its own module with its own tests rather than inside the
usage parser: it owns the exit-code-4 decision, not a flavour of token counting.
See rules/model-capabilities.md, "Classifier refusals arrive as success".
"""

_REFUSAL_STOP_REASON = "refusal"
_REFUSAL_TEXT_LIMIT = 400
_REFUSAL_EVENT_LIMIT = 10


def _message_text(message) -> str:
    """Join the text blocks of a message. Empty string when it carries none."""
    parts = []
    for block in getattr(message, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts)


def _refusal_from_message(message) -> dict | None:
    """Recognise a classifier decline in one SDK message. None when there is none.

    Two shapes reach us and they mean different things:

    1. `stop_reason == "refusal"` on an AssistantMessage or on the ResultMessage
       — the raw decline. Content is empty or partial and must not be trusted.
    2. A `system` message with subtype `model_refusal_fallback` — the CLI arms
       server-side fallback (`server-side-fallback-2026-07-01`) and re-runs the
       declined request on the model Anthropic maps that refusal category to.
       The answer is real, but it came from a model we did not pin.

    `stop_details.category` never survives claude_agent_sdk's typed messages:
    `AssistantMessage`/`ResultMessage` are dataclasses with a `stop_reason`
    field and no `stop_details` one, so the parser drops it. The fallback
    system message is the only place the category reaches us, under
    `data["apiRefusalCategory"]` — SDK message parsing keeps unknown `system`
    subtypes whole as `SystemMessage(subtype=..., data=<raw dict>)`.

    Duck-typed rather than isinstance-based on purpose: it has to stay callable
    against a stub message in a test process with no Agent SDK installed.
    """
    subtype = getattr(message, "subtype", None)
    data = getattr(message, "data", None)
    if isinstance(subtype, str) and _REFUSAL_STOP_REASON in subtype and isinstance(data, dict):
        explanation = data.get("apiRefusalExplanation") or data.get("content") or None
        if isinstance(explanation, str):
            explanation = explanation[:_REFUSAL_TEXT_LIMIT]
        else:
            explanation = None
        return {
            "source": subtype,
            "category": data.get("apiRefusalCategory"),
            "explanation": explanation,
            "original_model": data.get("originalModel"),
            "fallback_model": data.get("fallbackModel"),
            "served_by_fallback": bool(data.get("fallbackModel")),
        }

    stop_reason = getattr(message, "stop_reason", None)
    if isinstance(stop_reason, str) and stop_reason.strip().lower() == _REFUSAL_STOP_REASON:
        return {
            "source": type(message).__name__,
            "category": None,
            "explanation": _message_text(message)[:_REFUSAL_TEXT_LIMIT] or None,
            "original_model": getattr(message, "model", None),
            "fallback_model": None,
            "served_by_fallback": False,
        }
    return None


def _refusal_summary(events: list) -> dict:
    """Fold refusal events into the run-log block and the pass/fail decision.

    A decline the CLI re-ran on a fallback model produced real output, so
    failing the run would re-execute a finished spec for nothing — the BUG-188
    lesson. It is still an unannounced model swap, so it is surfaced the same
    way `model_drift` is: loud in the log, telemetry row, exit code untouched.

    A decline with no fallback behind it produced nothing, and that is the case
    that must not read as a clean run.

    A recovered episode can emit both shapes (the partially streamed assistant
    turn is retracted, then the fallback notice arrives), so the count of
    fallbacks served cancels the count of declines rather than adding to it.
    """
    declines = sum(1 for e in events if not e.get("served_by_fallback"))
    served = sum(1 for e in events if e.get("served_by_fallback"))
    return {
        "detected": bool(events),
        "declines": declines,
        "fallbacks_served": served,
        "unrecovered": max(0, declines - served),
        "categories": sorted({str(e["category"]) for e in events if e.get("category")}),
        "events": events[:_REFUSAL_EVENT_LIMIT],
    }


# Models this generation is supposed to use. Subagents resolve `opus`/`sonnet`
# aliases through the CLI, so a stale binary silently serves a previous
# generation to every subagent while the main loop's explicit pin looks correct.
# Production logs from 2026-07-16..18 show exactly that: main loop on
# claude-opus-4-8 with claude-opus-4-6 and claude-sonnet-4-6 subagents underneath.
