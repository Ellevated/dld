"""
Tests for claude-runner session-scope telemetry (_session_totals).

Why this exists: the top-level run-log counters come from ResultMessage and cover
the MAIN LOOP only, while cost_usd covers the whole session. Production logs
carry runs with `turns: 1` next to `cost_usd: 26.19` — the main loop resumed,
read a background result and stopped, while its subagents had already spent the
money. Any before/after measurement that compares those two fields is measuring
nothing.

The drift check is the second half: subagents resolve `opus`/`sonnet` aliases
through the CLI, so a stale binary serves a previous generation to every
subagent while the main loop's explicit pin still reads correct. Logs from
2026-07-16..18 show a claude-opus-4-8 main loop with claude-opus-4-6 and
claude-sonnet-4-6 subagents underneath, for weeks, unnoticed.
"""

from __future__ import annotations

import sys
from pathlib import Path

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import runner_result as cr


# --- rollup -----------------------------------------------------------------


def test_totals_sum_across_models_camel_case():
    usage = {
        "claude-opus-5": {
            "inputTokens": 100,
            "outputTokens": 200,
            "cacheCreationInputTokens": 1_000,
            "cacheReadInputTokens": 9_000,
            "costUSD": 13.45,
        },
        "claude-sonnet-5": {
            "inputTokens": 50,
            "outputTokens": 60,
            "cacheCreationInputTokens": 500,
            "cacheReadInputTokens": 1_000,
            "costUSD": 6.69,
        },
    }
    t = cr._session_totals(usage)

    assert t["session_input_tokens"] == 150
    assert t["session_output_tokens"] == 260
    assert t["session_cache_creation_input_tokens"] == 1_500
    assert t["session_cache_read_input_tokens"] == 10_000
    assert t["cost_by_model"] == {"claude-opus-5": 13.45, "claude-sonnet-5": 6.69}


def test_totals_accept_snake_case():
    """The SDK has shipped both spellings; neither may silently read as zero."""
    t = cr._session_totals(
        {
            "claude-opus-5": {
                "input_tokens": 7,
                "output_tokens": 8,
                "cache_creation_input_tokens": 9,
                "cache_read_input_tokens": 10,
                "cost_usd": 1.5,
            }
        }
    )
    assert t["session_input_tokens"] == 7
    assert t["session_output_tokens"] == 8
    assert t["session_cache_creation_input_tokens"] == 9
    assert t["session_cache_read_input_tokens"] == 10
    assert t["cost_by_model"]["claude-opus-5"] == 1.5


def test_hit_rate_includes_cache_creation_in_denominator():
    """Cache creation is paid input. Leaving it out flatters a thrashing run."""
    t = cr._session_totals(
        {
            "claude-opus-5": {
                "inputTokens": 0,
                "cacheCreationInputTokens": 6_000_000,
                "cacheReadInputTokens": 6_000_000,
            }
        }
    )
    assert t["session_cache_hit_rate"] == 0.5


def test_healthy_and_thrashing_runs_are_distinguishable():
    """The whole point: the $58 timeout must not look like a healthy run."""
    healthy = cr._session_totals(
        {"claude-opus-5": {"cacheCreationInputTokens": 125_000, "cacheReadInputTokens": 2_100_000}}
    )
    thrashing = cr._session_totals(
        {
            "claude-opus-5": {
                "cacheCreationInputTokens": 6_244_651,
                "cacheReadInputTokens": 6_303_845,
            }
        }
    )
    assert healthy["session_cache_hit_rate"] > 0.9
    assert thrashing["session_cache_hit_rate"] < 0.55


def test_empty_and_malformed_usage_do_not_raise():
    for bad in ({}, None, "not a dict", {"m": None}, {"m": "junk"}):
        t = cr._session_totals(bad)
        assert t["session_cache_hit_rate"] == 0.0
        assert t["session_input_tokens"] == 0


def test_non_numeric_cost_does_not_raise():
    t = cr._session_totals({"claude-opus-5": {"costUSD": "n/a"}})
    assert t["cost_by_model"]["claude-opus-5"] == 0.0


# --- drift ------------------------------------------------------------------


def test_no_drift_for_expected_generation():
    t = cr._session_totals({m: {} for m in cr._EXPECTED_MODELS})
    assert t["model_drift"] == []


def test_previous_generation_subagents_are_flagged(monkeypatch):
    """The real incident: a 4-8 main loop with 4-6 subagents underneath.

    Pinned: _EXPECTED_MODELS is computed from AUTOPILOT_EXPECTED_MODELS at
    import time, so an ambient env value could silently invert this test.
    """
    monkeypatch.setattr(
        cr,
        "_EXPECTED_MODELS",
        frozenset({"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"}),
    )
    t = cr._session_totals(
        {
            "claude-opus-4-8": {"costUSD": 19.49},
            "claude-opus-4-6": {"costUSD": 6.89},
            "claude-sonnet-4-6": {"costUSD": 12.22},
        }
    )
    assert sorted(t["model_drift"]) == [
        "claude-opus-4-6",
        "claude-opus-4-8",
        "claude-sonnet-4-6",
    ]


def test_drift_lists_only_the_unexpected_model(monkeypatch):
    """Pinned: see test_previous_generation_subagents_are_flagged."""
    monkeypatch.setattr(
        cr,
        "_EXPECTED_MODELS",
        frozenset({"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"}),
    )
    t = cr._session_totals({"claude-opus-5": {}, "claude-sonnet-4-6": {}})
    assert t["model_drift"] == ["claude-sonnet-4-6"]
