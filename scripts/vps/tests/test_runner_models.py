"""Tests for runner_models and the two run settings that were invisible until 2026-09-23.

1. Frontmatter `model: opus` floated with the CLI. CLI 2.1.280 resolves it to
   claude-opus-5-5 while the main loop is pinned to claude-opus-5 — the same mixed
   generation the 2026-07-16..18 logs showed one generation back. The runner now pins
   the aliases through ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL.
2. The SDK turns an unset system_prompt into `--system-prompt ""`, so the main loop
   ran without the CLI's own prompt (EXP-009).
3. Prices were looked up by prefix, which priced claude-opus-5-5 as claude-opus-5, and
   newer CLIs key model_usage as `claude-opus-5[1m]`, which read as drift.

EC-1: canonical ids keep the version and drop the window tag and build date
EC-2: alias pins follow an Opus main loop and yield to explicit env values
EC-3: the expected set is the main loop plus the pins unless named explicitly
EC-4: Opus 5.5 and Fable 5.1 are priced at their own rates, cache reads included
EC-5: `[1m]` keys are not drift; a different generation is
EC-6: build_options sends the CLI preset, or nothing, and passes the pins in env
EC-7: the run log records which pins and which system prompt the run used
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import runner_cost  # noqa: E402
import runner_models  # noqa: E402
import runner_result  # noqa: E402

PINNED_5 = frozenset({"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"})


class TestCanonicalModel:
    def test_window_tag_is_dropped(self):
        """EC-1: CLI 2.1.280 reports subagent usage under `claude-opus-5[1m]`."""
        assert runner_models.canonical_model("claude-opus-5[1m]") == "claude-opus-5"

    def test_build_date_is_dropped(self):
        assert runner_models.canonical_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5"

    def test_version_is_kept(self):
        """EC-1: the prefix bug — a version is part of the identity."""
        assert runner_models.canonical_model("claude-opus-5-5") == "claude-opus-5-5"
        assert runner_models.canonical_model("claude-opus-5-5[1m]") == "claude-opus-5-5"

    def test_empty(self):
        assert runner_models.canonical_model("") == ""
        assert runner_models.canonical_model(None) == ""


class TestAliasPins:
    def test_defaults_hold_the_current_generation(self):
        assert runner_models.alias_pins("claude-opus-5", env={}) == {
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5",
            "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5-20251001",
        }

    def test_opus_alias_follows_an_opus_main_loop(self):
        """EC-2: moving AUTOPILOT_MODEL moves every `model: opus` agent with it."""
        pins = runner_models.alias_pins("claude-opus-5-5", env={})
        assert pins["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-opus-5-5"

    def test_non_opus_main_loop_leaves_the_opus_alias_on_the_default(self):
        """A Fable main loop must not turn every planner and reviewer into Fable."""
        pins = runner_models.alias_pins("claude-fable-5", env={})
        assert pins["ANTHROPIC_DEFAULT_OPUS_MODEL"] == runner_models.DEFAULT_MAIN_MODEL

    def test_explicit_env_wins(self):
        """EC-2: each variable can still be set on its own."""
        env = {"ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-opus-5-5"}
        pins = runner_models.alias_pins("claude-opus-5", env=env)
        assert pins["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-opus-5-5"
        assert pins["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-opus-5"


class TestExpectedModels:
    def test_default_is_main_loop_plus_pins(self):
        """EC-3: the same set the old hard-coded default named."""
        assert runner_models.expected_models(env={}) == PINNED_5

    def test_moving_the_main_loop_moves_the_expectation(self):
        expected = runner_models.expected_models(env={"AUTOPILOT_MODEL": "claude-opus-5-5"})
        assert "claude-opus-5-5" in expected
        assert "claude-opus-5" not in expected

    def test_explicit_list_wins(self):
        env = {"AUTOPILOT_EXPECTED_MODELS": "claude-opus-5-5, claude-sonnet-5"}
        assert runner_models.expected_models(env=env) == {"claude-opus-5-5", "claude-sonnet-5"}


class TestPrices:
    def test_opus_5_5_input_output(self):
        """EC-4: $4 / $20, not Opus 5's $5 / $25."""
        usage = {"claude-opus-5-5": {"input": 1_000_000, "output": 1_000_000}}
        assert runner_cost.estimate(usage) == 24.0

    def test_opus_5_5_cache_read_is_0_05x(self):
        """EC-4: $0.20 per million, against $0.50 under the old flat 0.1x."""
        assert runner_cost.estimate({"claude-opus-5-5": {"cache_read": 1_000_000}}) == 0.2

    def test_fable_5_1_cache_read_is_0_025x(self):
        assert runner_cost.estimate({"claude-fable-5-1": {"cache_read": 1_000_000}}) == 0.25

    def test_window_tagged_key_is_priced_as_its_model(self):
        tagged = runner_cost.estimate({"claude-opus-5-5[1m]": {"input": 1_000_000}})
        assert tagged == 4.0

    def test_opus_5_5_does_not_fall_into_the_opus_5_row(self, caplog):
        """The prefix bug, and no warning: a known model must not read as unknown."""
        with caplog.at_level("WARNING", logger="claude-runner"):
            runner_cost.estimate({"claude-opus-5-5": {"input": 1_000_000}})
        assert "not in the price table" not in caplog.text


class TestDrift:
    def test_window_tag_is_not_drift(self, monkeypatch):
        """EC-5: the pinned model under a newer CLI's key spelling."""
        monkeypatch.setattr(runner_result, "_EXPECTED_MODELS", PINNED_5)
        t = runner_result._session_totals({"claude-opus-5[1m]": {}, "claude-sonnet-5[1m]": {}})
        assert t["model_drift"] == []

    def test_next_generation_under_a_floating_alias_is_drift(self, monkeypatch):
        """EC-5: exactly what an unpinned CLI 2.1.280 would have produced."""
        monkeypatch.setattr(runner_result, "_EXPECTED_MODELS", PINNED_5)
        t = runner_result._session_totals({"claude-opus-5": {}, "claude-opus-5-5[1m]": {}})
        assert t["model_drift"] == ["claude-opus-5-5[1m]"]


@pytest.fixture
def loop_module():
    """runner_loop against a fake SDK — the module binds SDK names at import."""
    fake_sdk = types.ModuleType("claude_agent_sdk")

    class FakeOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_sdk.ClaudeAgentOptions = FakeOptions
    for name in (
        "AssistantMessage",
        "ResultMessage",
        "SystemMessage",
        "TextBlock",
        "ToolUseBlock",
        "TaskNotificationMessage",
    ):
        setattr(fake_sdk, name, type(name, (), {}))

    async def _unused_query(**_kwargs):
        return
        yield  # pragma: no cover — makes this an async generator

    fake_sdk.query = _unused_query
    fake_sdk.CLIConnectionError = type("CLIConnectionError", (Exception,), {})
    fake_sdk.ProcessError = type("ProcessError", (Exception,), {})
    fake_errors = types.ModuleType("claude_agent_sdk._errors")
    fake_errors.CLIConnectionError = fake_sdk.CLIConnectionError
    fake_errors.ProcessError = fake_sdk.ProcessError

    saved = {n: sys.modules.get(n) for n in ("claude_agent_sdk", "claude_agent_sdk._errors")}
    sys.modules["claude_agent_sdk"] = fake_sdk
    sys.modules["claude_agent_sdk._errors"] = fake_errors
    sys.modules.pop("runner_loop", None)
    try:
        mod = importlib.import_module("runner_loop")
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev
    yield mod
    sys.modules.pop("runner_loop", None)


def _options(loop_module, tmp_path, **kwargs):
    return loop_module.build_options(
        tmp_path,
        None,
        model="claude-opus-5",
        effort="medium",
        cli_path=None,
        max_turns=10,
        **kwargs,
    )


class TestBuildOptions:
    def test_claude_code_preset_by_default(self, loop_module, tmp_path):
        """EC-6: a preset with no `append` makes the SDK pass no flag at all."""
        opts = _options(loop_module, tmp_path)
        assert opts.system_prompt == {"type": "preset", "preset": "claude_code"}

    def test_empty_restores_the_old_behaviour(self, loop_module, tmp_path):
        """EC-6: None is what the SDK turns into `--system-prompt ""` — the rollback."""
        opts = _options(loop_module, tmp_path, system_prompt="empty")
        assert opts.system_prompt is None

    def test_pins_reach_the_cli_env(self, loop_module, tmp_path):
        pins = runner_models.alias_pins("claude-opus-5", env={})
        opts = _options(loop_module, tmp_path, alias_pins=pins)
        assert opts.env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-opus-5"
        assert opts.env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "claude-haiku-4-5-20251001"
        assert opts.env["BASH_DEFAULT_TIMEOUT_MS"]  # the fixed keys are still there


def test_run_log_records_pins_and_system_prompt():
    """EC-7: an experiment has to be able to tell which configuration it measured."""
    pins = runner_models.alias_pins("claude-opus-5", env={})
    log = runner_result.build_log_data(
        runner_result.new_run_state(),
        project_name="p",
        skill="autopilot",
        task="TECH-1",
        prompt="/autopilot TECH-1",
        cli_path=None,
        cli_version="x",
        model="claude-opus-5",
        effort="medium",
        salvage_info=None,
        alias_pins=pins,
        system_prompt="claude_code",
    )
    assert log["alias_pins"] == pins
    assert log["system_prompt"] == "claude_code"
