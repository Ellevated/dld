"""Tests for runner_cost — pricing a run the timeout killed before ResultMessage.

The defect being closed: `total_cost_usd` arrives only on ResultMessage, so every
timed-out run was logged as $0.00 while being the most expensive class of run there is
(6 of 12 runs on 2026-09-05, 370–630 turns each).

EC-1: usage streamed per turn is accumulated per model
EC-2: a billed ResultMessage figure always wins over the estimate
EC-3: no usage at all → cost stays 0 and says so, rather than inventing a number
EC-4: an unknown model is priced (as opus-5) instead of silently costing nothing
EC-5: cache tokens are priced at their own multipliers, not as plain input
EC-6: apply_assistant_message wires accumulation into the real run state
"""

import sys
from pathlib import Path

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import runner_cost  # noqa: E402
import runner_result  # noqa: E402


class FakeAssistantMessage:
    """Duck-typed stand-in — runner_cost never imports the SDK."""

    def __init__(self, model, usage):
        self.model = model
        self.usage = usage
        self.content = []


class TestAccumulate:
    def test_folds_usage_per_model(self):
        """EC-1: two turns on one model sum; a second model gets its own bucket."""
        state = runner_result.new_run_state()
        runner_cost.accumulate(
            state, FakeAssistantMessage("claude-opus-5", {"input_tokens": 100, "output_tokens": 20})
        )
        runner_cost.accumulate(
            state, FakeAssistantMessage("claude-opus-5", {"input_tokens": 50, "output_tokens": 10})
        )
        runner_cost.accumulate(
            state, FakeAssistantMessage("claude-sonnet-5", {"input_tokens": 7, "output_tokens": 3})
        )
        assert state["stream_usage"]["claude-opus-5"]["input"] == 150
        assert state["stream_usage"]["claude-opus-5"]["output"] == 30
        assert state["stream_usage"]["claude-sonnet-5"]["input"] == 7

    def test_missing_usage_is_not_an_error(self):
        """A message without usage must not raise — ADR-004, never crash the runner."""
        state = runner_result.new_run_state()
        runner_cost.accumulate(state, FakeAssistantMessage("claude-opus-5", None))
        assert state["stream_usage"] == {}

    def test_camel_case_usage_keys(self):
        state = runner_result.new_run_state()
        runner_cost.accumulate(
            state, FakeAssistantMessage("claude-opus-5", {"inputTokens": 10, "outputTokens": 5})
        )
        assert state["stream_usage"]["claude-opus-5"]["input"] == 10
        assert state["stream_usage"]["claude-opus-5"]["output"] == 5

    def test_nested_cache_creation_split_by_ttl(self):
        state = runner_result.new_run_state()
        runner_cost.accumulate(
            state,
            FakeAssistantMessage(
                "claude-opus-5",
                {
                    "input_tokens": 1,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 400,
                        "ephemeral_1h_input_tokens": 600,
                    },
                },
            ),
        )
        bucket = state["stream_usage"]["claude-opus-5"]
        assert bucket["cache_write_5m"] == 400
        assert bucket["cache_write_1h"] == 600

    def test_flat_cache_creation_priced_at_the_cheaper_rate(self):
        """Flat shape has no TTL — booked at 5m so the estimate stays a floor."""
        state = runner_result.new_run_state()
        runner_cost.accumulate(
            state,
            FakeAssistantMessage("claude-opus-5", {"cache_creation_input_tokens": 1000}),
        )
        assert state["stream_usage"]["claude-opus-5"]["cache_write_5m"] == 1000
        assert state["stream_usage"]["claude-opus-5"]["cache_write_1h"] == 0


class TestEstimate:
    def test_opus_input_output(self):
        """EC-5 baseline: 1M in + 1M out on opus-5 = $5 + $25."""
        usage = {"claude-opus-5": {"input": 1_000_000, "output": 1_000_000}}
        assert runner_cost.estimate(usage) == 30.0

    def test_cache_multipliers(self):
        """EC-5: cache read is 0.1x input, 5m write 1.25x, 1h write 2x."""
        usage = {
            "claude-opus-5": {
                "cache_read": 1_000_000,
                "cache_write_5m": 1_000_000,
                "cache_write_1h": 1_000_000,
            }
        }
        # 5 * 0.1 + 5 * 1.25 + 5 * 2 = 0.5 + 6.25 + 10
        assert runner_cost.estimate(usage) == 16.75

    def test_sonnet_priced_below_opus(self):
        opus = runner_cost.estimate({"claude-opus-5": {"input": 1_000_000}})
        sonnet = runner_cost.estimate({"claude-sonnet-5": {"input": 1_000_000}})
        assert sonnet < opus

    def test_build_suffix_still_matches_its_price_row(self):
        """Reported ids carry build dates: claude-haiku-4-5-20251001."""
        assert runner_cost.estimate({"claude-haiku-4-5-20251001": {"input": 1_000_000}}) == 1.0

    def test_unknown_model_is_priced_not_zeroed(self):
        """EC-4: an unpriced model would reopen the exact blind spot being closed."""
        assert runner_cost.estimate({"claude-something-6": {"input": 1_000_000}}) == 5.0

    def test_empty_usage(self):
        assert runner_cost.estimate({}) == 0.0


class TestApplyToState:
    def test_estimates_when_no_billed_figure(self):
        """EC-1 end to end: timeout path gets a number instead of $0.00."""
        state = runner_result.new_run_state()
        runner_cost.accumulate(
            state,
            FakeAssistantMessage(
                "claude-opus-5", {"input_tokens": 2_000_000, "output_tokens": 100_000}
            ),
        )
        cost = runner_cost.apply_to_state(state)
        assert cost == 12.5  # 2M * $5 + 0.1M * $25
        assert state["cost_usd"] == 12.5
        assert state["cost_source"] == "estimated_from_stream"

    def test_billed_figure_wins(self):
        """EC-2: the CLI prices the whole session, including subagents we never saw."""
        state = runner_result.new_run_state()
        state["cost_usd"] = 19.54
        runner_cost.accumulate(
            state, FakeAssistantMessage("claude-opus-5", {"input_tokens": 2_000_000})
        )
        assert runner_cost.apply_to_state(state) == 19.54
        assert state["cost_source"] == "result_message"

    def test_no_usage_reports_unavailable(self):
        """EC-3: a run that streamed nothing must say so, not invent a number."""
        state = runner_result.new_run_state()
        assert runner_cost.apply_to_state(state) == 0.0
        assert state["cost_source"] == "unavailable"


class TestWiredIntoRunState:
    def test_apply_assistant_message_accumulates(self):
        """EC-6: the real fold path, not just the helper called directly."""
        state = runner_result.new_run_state()
        runner_result.apply_assistant_message(
            state, FakeAssistantMessage("claude-opus-5", {"input_tokens": 42})
        )
        assert state["turn_count"] == 1
        assert state["stream_usage"]["claude-opus-5"]["input"] == 42

    def test_run_log_carries_cost_source(self):
        log = runner_result.build_log_data(
            runner_result.new_run_state(),
            project_name="p",
            skill="autopilot",
            task="TECH-1",
            prompt="/autopilot TECH-1",
            cli_path=None,
            cli_version="x",
            model="claude-opus-5",
            effort="high",
            salvage_info=None,
        )
        assert log["cost_source"] == "unavailable"

    def test_runner_prices_before_reporting_the_timeout(self):
        """The log line itself must not print $0.0000 on a timed-out run."""
        source = (Path(VPS_DIR) / "claude-runner.py").read_text(encoding="utf-8")
        timeout_block = source.split("except TimeoutError:")[1].split("except Exception")[0]
        assert "runner_cost.apply_to_state(state)" in timeout_block
        assert timeout_block.index("runner_cost.apply_to_state(state)") < timeout_block.index(
            "logger.error"
        )
