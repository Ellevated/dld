"""Rate-limit detection and the exit-5 decision (TECH-225).

Why this exists: 23.09 the fleet hit the 5h Max subscription window mid-run and
the runner recorded a plain `exit_code: 1` with empty stderr — the reason was
found only by reading the session transcript by hand. This module recognises the
two structural signals the SDK already parses (`AssistantMessage.error ==
"rate_limit"`, `RateLimitEvent.rate_limit_info.status == "rejected"`) and owns
the exit-5 decision, the same way `runner_refusal` owns exit-4.

Stubs are `types.SimpleNamespace` — no runner fixture, no fake SDK module: this
file tests `runner_ratelimit` directly, which never imports `claude_agent_sdk`.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import runner_ratelimit as rl  # noqa: E402


def _state(exit_code=1, result_received=False, result_is_error=False):
    return {
        "exit_code": exit_code,
        "result_received": result_received,
        "result_is_error": result_is_error,
    }


class TestFromMessage:
    def test_synthetic_message_is_rejected(self):
        msg = NS(content=[NS(text="declined")], model="<synthetic>", error="rate_limit")
        assert rl.from_message(msg) == {"source": "assistant_error", "status": "rejected"}

    def test_rejected_event_is_recognised(self):
        info = NS(status="rejected", resets_at=1790161200, rate_limit_type="five_hour")
        msg = NS(rate_limit_info=info)
        event = rl.from_message(msg)
        assert event == {
            "source": "event",
            "status": "rejected",
            "resets_at": 1790161200,
            "rate_limit_type": "five_hour",
            "utilization": None,
            "overage_status": None,
        }

    @pytest.mark.parametrize(
        "message",
        [
            NS(content=[NS(text="You've hit your session limit · resets 2pm")], error=None),
            NS(subtype="success", is_error=False, result="ok"),
            NS(subtype="init", data={}),
        ],
    )
    def test_agent_text_about_limits_is_not_detected(self, message):
        assert rl.from_message(message) is None

    def test_allowed_warning_is_detected_not_rejected(self):
        info = NS(status="allowed_warning", utilization=0.91)
        events = [rl.from_message(NS(rate_limit_info=info))]
        s = rl.summary(events)
        assert s["detected"] is True
        assert s["rejected"] is False
        assert s["utilization_max"] == 0.91


class TestRealSDKTypes:
    def test_real_sdk_types(self):
        sdk = pytest.importorskip("claude_agent_sdk")
        msg = sdk.AssistantMessage(content=[], model="<synthetic>", error="rate_limit")
        assert rl.from_message(msg) == {"source": "assistant_error", "status": "rejected"}

        info = sdk.RateLimitInfo(
            status="rejected", resets_at=1790161200, rate_limit_type="five_hour"
        )
        event = sdk.RateLimitEvent(rate_limit_info=info, uuid="u", session_id="s")
        parsed = rl.from_message(event)
        assert parsed["source"] == "event"
        assert parsed["status"] == "rejected"
        assert parsed["resets_at"] == 1790161200
        assert parsed["rate_limit_type"] == "five_hour"


class TestSummary:
    def test_rejected_event_summary(self):
        info = NS(status="rejected", resets_at=1790161200, rate_limit_type="five_hour")
        s = rl.summary([rl.from_message(NS(rate_limit_info=info))])
        assert s["rejected"] is True
        assert s["resets_at"] == 1790161200
        assert s["resets_at_iso"] == "2026-09-23T11:00:00+00:00"
        assert s["rate_limit_type"] == "five_hour"
        assert s["resets_at_iso"] == datetime.fromtimestamp(1790161200, tz=timezone.utc).isoformat()

    def test_empty_summary_has_every_key(self):
        s = rl.summary([])
        assert s == {
            "detected": False,
            "rejected": False,
            "rate_limit_type": None,
            "resets_at": None,
            "resets_at_iso": None,
            "utilization_max": None,
            "sources": [],
            "events": [],
        }


class TestDecideExit:
    def test_rejected_without_result_upgrades_to_5(self):
        s = rl.summary([{"source": "assistant_error", "status": "rejected"}])
        assert rl.decide_exit(_state(exit_code=1), s) == 5

    def test_rejected_after_successful_result_keeps_exit_unchanged(self):
        s = rl.summary([{"source": "assistant_error", "status": "rejected"}])
        state = _state(exit_code=0, result_received=True, result_is_error=False)
        assert rl.decide_exit(state, s) == 0

    @pytest.mark.parametrize("exit_code", [124, 4, 143])
    def test_more_specific_exit_codes_are_not_overwritten(self, exit_code):
        s = rl.summary([{"source": "assistant_error", "status": "rejected"}])
        assert rl.decide_exit(_state(exit_code=exit_code), s) == exit_code

    def test_not_rejected_keeps_exit_unchanged(self):
        s = rl.summary([{"source": "event", "status": "allowed_warning"}])
        assert rl.decide_exit(_state(exit_code=1), s) == 1

    def test_state_is_not_mutated(self):
        s = rl.summary([{"source": "assistant_error", "status": "rejected"}])
        state = _state(exit_code=1)
        before = dict(state)
        rl.decide_exit(state, s)
        assert state == before
