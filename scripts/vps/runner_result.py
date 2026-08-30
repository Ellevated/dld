"""
Module: runner_result
Role: parse the agent's final ResultMessage text, roll per-model usage up into
      session-wide telemetry, and fold SDK message state into the run log.
Uses: json, os, re, logging

Used by:
  - claude-runner.py

The apply_* helpers below use getattr() only — never isinstance() against SDK
classes — so this module stays import-free of claude_agent_sdk. claude-runner.py
does the isinstance(message, AssistantMessage) etc. checks and calls these with
the already-typed message.
"""

import json
import logging
import os
import re

logger = logging.getLogger("claude-runner")

# Maps a run's exit_code to the salvage reason string (TECH-213: moved from
# claude-runner.py to hold its LOC budget — used by _salvage_if_needed).
_EXIT_REASONS = {
    124: "timeout",
    2: "cli_connection_error",
    3: "cli_process_error",
    4: "classifier_refusal",
    143: "sigterm",
}

# Autopilot's structured completion signal. The agent is told to emit a final
# JSON object with `task_status`, but Opus 4.x often wraps it in a markdown
# report (```json fence inside prose). Scan the full result text for the token
# so the callback gets the signal regardless of formatting / truncation.
_TASK_STATUS_RE = re.compile(r'"task_status"\s*:\s*"([a-z_]+)"')


def _extract_task_status(result_text: str) -> str:
    """Best-effort extraction of task_status from the agent's final text.

    Robust to the value being embedded in a markdown ```json fence rather than
    a bare top-level JSON object. Returns "" if not found. Lifted to a
    top-level log field so callback._parse_log_file never depends on the
    (truncated) result_preview being valid JSON.
    """
    if not result_text:
        return ""
    m = _TASK_STATUS_RE.search(result_text)
    return m.group(1) if m else ""


# Models this generation is supposed to use. Subagents resolve `opus`/`sonnet`
# aliases through the CLI, so a stale binary silently serves a previous
# generation to every subagent while the main loop's explicit pin looks correct.
# Production logs from 2026-07-16..18 show exactly that: main loop on
# claude-opus-4-8 with claude-opus-4-6 and claude-sonnet-4-6 subagents underneath.
_EXPECTED_MODELS = frozenset(
    m.strip()
    for m in os.environ.get(
        "AUTOPILOT_EXPECTED_MODELS",
        "claude-opus-5,claude-sonnet-5,claude-haiku-4-5-20251001",
    ).split(",")
    if m.strip()
)


def _usage_field(usage: dict, *names: str) -> int:
    """Read a usage counter under either camelCase or snake_case."""
    for n in names:
        if n in usage:
            try:
                return int(usage[n] or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _session_totals(model_usage: dict) -> dict:
    """Roll model_usage up into session-wide totals, and flag model drift.

    The top-level counters come from ResultMessage and describe the MAIN LOOP
    only, while cost_usd covers the whole session — main loop plus every
    subagent. Comparing them mixes scopes silently: production logs carry runs
    with `turns: 1` next to `cost_usd: 26.19`, because the main loop resumed,
    read a background result and stopped, while its subagents had already spent
    the money. State both scopes instead of leaving the reader to guess.
    """
    totals = {
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "session_cache_creation_input_tokens": 0,
        "session_cache_read_input_tokens": 0,
        "session_cache_hit_rate": 0.0,
        "cost_by_model": {},
        "model_drift": [],
    }
    if not isinstance(model_usage, dict):
        return totals

    for model, usage in model_usage.items():
        if not isinstance(usage, dict):
            usage = getattr(usage, "__dict__", {}) or {}
        totals["session_input_tokens"] += _usage_field(usage, "inputTokens", "input_tokens")
        totals["session_output_tokens"] += _usage_field(usage, "outputTokens", "output_tokens")
        totals["session_cache_creation_input_tokens"] += _usage_field(
            usage, "cacheCreationInputTokens", "cache_creation_input_tokens"
        )
        totals["session_cache_read_input_tokens"] += _usage_field(
            usage, "cacheReadInputTokens", "cache_read_input_tokens"
        )
        cost = usage.get("costUSD", usage.get("cost_usd", 0)) or 0
        try:
            totals["cost_by_model"][model] = round(float(cost), 4)
        except (TypeError, ValueError):
            totals["cost_by_model"][model] = 0.0
        if model not in _EXPECTED_MODELS:
            totals["model_drift"].append(model)

    denom = (
        totals["session_cache_read_input_tokens"]
        + totals["session_cache_creation_input_tokens"]
        + totals["session_input_tokens"]
    )
    if denom:
        totals["session_cache_hit_rate"] = round(
            totals["session_cache_read_input_tokens"] / denom, 4
        )
    return totals


# ---------------------------------------------------------------------------
# run_task state (TECH-213) — lifted verbatim from run_task's inline blocks.
# ---------------------------------------------------------------------------
def new_run_state() -> dict:
    """Fresh mutable state threaded through one run_task call's message loop.

    A plain dict (not a dataclass) so apply_* can mutate specific keys
    without claude-runner.py importing a class from this module.
    """
    return {
        "result_text": "",
        "last_assistant_text": "",
        "turns": 0,
        "cost_usd": 0.0,
        "exit_code": 0,
        "turn_count": 0,  # per AssistantMessage (available before ResultMessage)
        "last_tool_name": None,  # last tool used (for heartbeat + timeout report)
        "usage_metrics": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_1h_input_tokens": 0,
            "cache_creation_5m_input_tokens": 0,
        },
        "model_usage": {},
        "result_received": False,
        "result_is_error": False,
        # Classifier declines seen in-stream. Collected here rather than in
        # runner_refusal because the state dict is what survives a TimeoutError.
        "refusal_events": [],
    }


def apply_assistant_message(state: dict, message) -> dict:
    """Fold one AssistantMessage into state. Caller does the isinstance check."""
    state["turn_count"] += 1
    text_parts = []
    for block in getattr(message, "content", []):
        if hasattr(block, "text"):
            text_parts.append(block.text)
        if getattr(block, "name", None):  # tool use block
            state["last_tool_name"] = block.name
    if text_parts:
        state["last_assistant_text"] = "\n".join(text_parts)
    return state


def apply_task_notification(state: dict, message) -> dict:
    """Fold one TaskNotificationMessage into state (autopilot Agent tool → Tasks)."""
    summary = getattr(message, "summary", "")
    if summary:
        state["result_text"] = summary
    return state


def apply_result_message(state: dict, message) -> dict:
    """Fold the final ResultMessage into state — sets the ADR-024 gate fields."""
    state["result_received"] = True
    state["result_is_error"] = bool(getattr(message, "is_error", False))
    state["result_text"] = getattr(message, "result", "") or state["result_text"]
    state["turns"] = getattr(message, "num_turns", 0)
    state["cost_usd"] = getattr(message, "total_cost_usd", 0.0) or 0.0
    if state["result_is_error"]:
        state["exit_code"] = 1
    usage = getattr(message, "usage", None) or {}
    if not isinstance(usage, dict):
        usage = getattr(usage, "__dict__", {}) or {}
    # Flat keys (Anthropic API contract: input_tokens, output_tokens,
    # cache_read_input_tokens). cache_creation is nested — see below.
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
        state["usage_metrics"][key] = int(usage.get(key, 0) or 0)
    # cache_creation moved to nested dict in 2026 API revision:
    # usage.cache_creation.ephemeral_{1h,5m}_input_tokens
    cc = usage.get("cache_creation", {}) if isinstance(usage, dict) else {}
    if isinstance(cc, dict):
        h1 = int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
        m5 = int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
        state["usage_metrics"]["cache_creation_1h_input_tokens"] = h1
        state["usage_metrics"]["cache_creation_5m_input_tokens"] = m5
        state["usage_metrics"]["cache_creation_input_tokens"] = h1 + m5
    # Per-model breakdown (Opus vs Sonnet vs Haiku in one run)
    mu = getattr(message, "model_usage", None)
    if isinstance(mu, dict):
        state["model_usage"] = mu
    return state


def build_log_data(
    state: dict,
    *,
    project_name: str,
    skill: str,
    task: str,
    prompt: str,
    cli_path: str | None,
    cli_version: str,
    model: str,
    effort: str,
    salvage_info: dict | None,
    refusal: dict | None = None,
) -> dict:
    """Assemble the run-log dict written to logs/<project>-<ts>.log.

    Key set is a contract — callback._parse_log_file reads these fields.
    """
    usage_metrics = state["usage_metrics"]
    # Cache hit rate: fraction of total input that came from cache read.
    # Denominator = direct input + cache creation + cache read (total paid input-ish).
    cache_read = usage_metrics["cache_read_input_tokens"]
    cache_total = (
        cache_read + usage_metrics["cache_creation_input_tokens"] + usage_metrics["input_tokens"]
    )
    cache_hit_rate = round(cache_read / cache_total, 4) if cache_total > 0 else 0.0
    result_text = state["result_text"]
    log_data = {
        "exit_code": state["exit_code"],
        "project": project_name,
        "skill": skill,
        "task": task,
        "prompt": prompt,
        "turns": state["turns"],
        "cost_usd": round(state["cost_usd"], 4),
        # Drift telemetry: which binary actually ran, and what we asked it for.
        # A run whose model_usage disagrees with `model` means the CLI ignored
        # the pin (see runner_cli._resolve_cli_path).
        "cli_path": cli_path,
        "cli_version": cli_version,
        "model": model,
        "effort": effort,
        "input_tokens": usage_metrics["input_tokens"],
        "output_tokens": usage_metrics["output_tokens"],
        "cache_creation_input_tokens": usage_metrics["cache_creation_input_tokens"],
        "cache_creation_1h_input_tokens": usage_metrics["cache_creation_1h_input_tokens"],
        "cache_creation_5m_input_tokens": usage_metrics["cache_creation_5m_input_tokens"],
        "cache_read_input_tokens": usage_metrics["cache_read_input_tokens"],
        "cache_hit_rate": cache_hit_rate,
        "model_usage": state["model_usage"],
        "task_status": _extract_task_status(result_text),
        "salvage": salvage_info,
        "result_preview": result_text[:1000] if result_text else "",
        # Always present, even when nothing was declined: an absent key cannot
        # be told apart from a runner that predates the check.
        "refusal": refusal if refusal is not None else {"detected": False},
    }
    # `turns` and the counters above are MAIN-LOOP scope; cost_usd is session
    # scope. Publish the session scope explicitly rather than leaving the two
    # to be compared as if they matched.
    log_data.update(_session_totals(state["model_usage"]))
    if log_data["model_drift"]:
        logger.warning(
            "MODEL DRIFT: subagents ran %s — expected %s. A CLI that predates the "
            "pinned generation resolves `opus`/`sonnet` aliases to its own era, so "
            "the main loop's pin can look correct while every subagent is a "
            "generation behind.",
            ", ".join(sorted(log_data["model_drift"])),
            ", ".join(sorted(_EXPECTED_MODELS)),
        )
    return log_data


def write_run_log(log_file, log_data: dict) -> None:
    """Write the run-log JSON file and emit the summary "done" log line."""
    log_file.write_text(json.dumps(log_data, ensure_ascii=False, indent=2))
    logger.info(
        "done project=%s exit=%d turns=%d cost=$%.4f in=%d out=%d cache_read=%d cache_hit=%.2f",
        log_data["project"],
        log_data["exit_code"],
        log_data["turns"],
        log_data["cost_usd"],
        log_data["input_tokens"],
        log_data["output_tokens"],
        log_data["cache_read_input_tokens"],
        log_data["cache_hit_rate"],
    )


def log_post_result_error(
    exc: Exception,
    state: dict,
    *,
    db,
    task: str,
    project_name: str,
    stderr_lines: list | None = None,
) -> None:
    """BUG-188 Layer 4: record an SDK exception raised after a good ResultMessage.

    The run stays a success (ADR-024); this only measures how often the SDK does it.
    """
    if db is None:
        return
    try:
        captured_stderr = "\n".join(stderr_lines[-100:]) if stderr_lines else None
        db.log_sdk_post_result_error(
            project_id=project_name,
            task=task,
            turns=state["turns"],
            cost_usd=state["cost_usd"],
            error_msg=str(exc)[:2000],
            stderr=captured_stderr,
        )
    except Exception as log_exc:  # noqa: BLE001 — telemetry must never break the runner
        logger.warning("Failed to log sdk_post_result_error: %s", log_exc)


def log_refusal_telemetry(
    refusal: dict, *, db, task: str, skill: str, project_name: str, model: str, exit_code: int
) -> None:
    """Record a classifier decline in its own table.

    Not `sdk_post_result_errors`: that table measures post-ResultMessage SDK drift
    (BUG-188) and has no columns for category or fallback model, so mixing the two
    signals would corrupt both counts. A refused request is not billed and raises
    nothing, so this row is the only counter it lands in.
    """
    if not refusal.get("detected"):
        return
    if db is None:
        return
    try:
        db.log_classifier_refusal(
            project_id=project_name,
            task=task,
            skill=skill,
            model=model,
            category=", ".join(refusal["categories"]) or None,
            declines=refusal["declines"],
            fallbacks_served=refusal["fallbacks_served"],
            unrecovered=refusal["unrecovered"],
            exit_code=exit_code,
            detail=json.dumps(refusal["events"], ensure_ascii=False)[:2000],
        )
    except Exception as log_exc:  # noqa: BLE001 — telemetry must never break the runner
        logger.warning("Failed to log classifier_refusal: %s", log_exc)
