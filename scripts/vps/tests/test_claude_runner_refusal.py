"""Safety-classifier refusal detection in claude-runner.

Why this exists: Opus 5 carries safety classifiers, and a decline arrives as
`stop_reason: "refusal"` inside a normal HTTP 200 with empty content. Nothing
raises, no error rate moves, and the run log reads exactly like a finished
answer. Two agents in this repo run on opus and are prompted for precisely the
`cyber` category — `council-security` and `bughunt-security-auditor` — so a
declined security review used to reach the callback as a clean one.

The SDK (claude_agent_sdk 0.1.81, the version `requirements.txt` resolves to)
exposes `stop_reason` on both `AssistantMessage` and `ResultMessage`, but drops
`stop_details` entirely — its dataclasses have no such field. The refusal
`category` survives only on the CLI's `system` / `model_refusal_fallback`
message, which the SDK keeps whole as `SystemMessage(subtype=..., data=...)`.
Both routes are covered below.

The messages are stubbed rather than mocked away: this file installs a fake
`claude_agent_sdk` module so the real `run_task` loop runs end to end and the
assertions are on the exit code and the run log it actually produces.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

RUNNER_PATH = VPS_DIR / "claude-runner.py"


# --- fake SDK ---------------------------------------------------------------
# Real classes, not Mocks: run_task branches on isinstance(), so a stub that is
# a bare `object` would match every branch at once.


class FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text
        self.name = None


class FakeAssistantMessage:
    def __init__(self, content=None, model="claude-opus-5", stop_reason=None, error=None):
        self.content = content or []
        self.model = model
        self.stop_reason = stop_reason
        self.error = error


class FakeLegacyAssistantMessage:
    """An assistant message from before the SDK carried `stop_reason` at all.

    Anything that reads the field with attribute access rather than getattr
    would raise here, taking the whole run down over a missing telemetry field.
    """

    def __init__(self, content=None, model="claude-opus-5"):
        self.content = content or []
        self.model = model


class FakeResultMessage:
    def __init__(
        self,
        subtype="success",
        is_error=False,
        result="",
        num_turns=1,
        total_cost_usd=0.0,
        usage=None,
        model_usage=None,
        stop_reason=None,
    ):
        self.subtype = subtype
        self.duration_ms = 0
        self.duration_api_ms = 0
        self.is_error = is_error
        self.result = result
        self.num_turns = num_turns
        self.total_cost_usd = total_cost_usd
        self.usage = usage or {}
        self.model_usage = model_usage or {}
        self.stop_reason = stop_reason
        self.session_id = "s"


class FakeSystemMessage:
    def __init__(self, subtype: str, data: dict) -> None:
        self.subtype = subtype
        self.data = data


class FakeTaskNotificationMessage(FakeSystemMessage):
    def __init__(self, summary: str = "") -> None:
        super().__init__("task_notification", {"summary": summary})
        self.summary = summary


class FakeCLIConnectionError(Exception):
    pass


class FakeProcessError(Exception):
    pass


def refusal_fallback_message(
    category: str | None = "cyber",
    fallback_model: str | None = "claude-opus-4-8",
) -> FakeSystemMessage:
    """The CLI's own notice that it re-ran a declined request elsewhere.

    Shape taken from the Claude Code CLI (2.1.220), which arms server-side
    fallback with the `server-side-fallback-2026-07-01` beta header and emits
    `{type: "system", subtype: "model_refusal_fallback", ...}` on retry.
    """
    return FakeSystemMessage(
        "model_refusal_fallback",
        {
            "direction": "retry",
            "trigger": "refusal",
            "level": "warning",
            "content": "Server refused; retrying on a fallback model.",
            "originalModel": "claude-opus-5",
            "fallbackModel": fallback_model,
            "apiRefusalCategory": category,
            "apiRefusalExplanation": None,
        },
    )


@pytest.fixture()
def runner(tmp_path, monkeypatch):
    """Load claude-runner.py against the fake SDK, isolated from disk and DB."""
    fake_sdk = types.ModuleType("claude_agent_sdk")
    fake_sdk.AssistantMessage = FakeAssistantMessage
    fake_sdk.ResultMessage = FakeResultMessage
    fake_sdk.TaskNotificationMessage = FakeTaskNotificationMessage

    class FakeOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_sdk.ClaudeAgentOptions = FakeOptions

    async def _unused_query(**_kwargs):  # replaced per test
        return
        yield  # pragma: no cover — makes this an async generator

    fake_sdk.query = _unused_query

    fake_errors = types.ModuleType("claude_agent_sdk._errors")
    fake_errors.CLIConnectionError = FakeCLIConnectionError
    fake_errors.ProcessError = FakeProcessError

    saved = {
        name: sys.modules.get(name) for name in ("claude_agent_sdk", "claude_agent_sdk._errors")
    }
    sys.modules["claude_agent_sdk"] = fake_sdk
    sys.modules["claude_agent_sdk._errors"] = fake_errors

    # Skip the PATH sweep + `--version` probe of every candidate CLI. This file
    # is not an executable, so the probe fails fast and returns version None.
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(Path(__file__).resolve()))
    monkeypatch.delenv("CLAUDE_CURRENT_SPEC_PATH", raising=False)

    try:
        spec = importlib.util.spec_from_file_location("claude_runner_refusal", RUNNER_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    mod.LOG_DIR = log_dir
    mod._salvage = None  # no git in unit tests
    mod._orch_db = None  # telemetry has its own test
    return mod


def run(mod, messages, project="proj", task="/autopilot TECH-1", skill="autopilot") -> dict:
    """Drive run_task over a fixed message sequence."""

    async def _query(**_kwargs):
        for m in messages:
            yield m

    mod.query = _query
    return asyncio.run(mod.run_task(str(Path.cwd()), task, skill))


def read_log(mod) -> dict:
    files = list(Path(mod.LOG_DIR).glob("*.log"))
    assert len(files) == 1, f"expected one run log, found {files}"
    return json.loads(files[0].read_text(encoding="utf-8"))


# --- _refusal_from_message --------------------------------------------------


class TestRefusalFromMessage:
    def test_assistant_stop_reason_refusal_is_a_decline(self, runner):
        msg = FakeAssistantMessage(
            content=[FakeTextBlock("Request declined.")],
            stop_reason="refusal",
        )
        event = runner._refusal_from_message(msg)
        assert event is not None
        assert event["served_by_fallback"] is False
        assert event["category"] is None  # SDK drops stop_details
        assert event["explanation"] == "Request declined."
        assert event["original_model"] == "claude-opus-5"

    def test_result_stop_reason_refusal_is_a_decline(self, runner):
        event = runner._refusal_from_message(FakeResultMessage(stop_reason="refusal"))
        assert event is not None
        assert event["source"] == "FakeResultMessage"
        assert event["served_by_fallback"] is False

    def test_system_fallback_message_carries_the_category(self, runner):
        event = runner._refusal_from_message(refusal_fallback_message("cyber"))
        assert event is not None
        assert event["category"] == "cyber"
        assert event["fallback_model"] == "claude-opus-4-8"
        assert event["served_by_fallback"] is True
        assert event["explanation"].startswith("Server refused")

    def test_system_fallback_with_null_category(self, runner):
        """Anthropic: `category` is null when the refusal maps to no named area."""
        event = runner._refusal_from_message(refusal_fallback_message(category=None))
        assert event is not None
        assert event["category"] is None
        assert event["served_by_fallback"] is True

    @pytest.mark.parametrize(
        "message",
        [
            FakeAssistantMessage(content=[FakeTextBlock("normal answer")]),
            FakeAssistantMessage(stop_reason="end_turn"),
            FakeAssistantMessage(stop_reason="tool_use"),
            FakeAssistantMessage(stop_reason="max_tokens"),
            FakeResultMessage(stop_reason="end_turn"),
            FakeResultMessage(),
            FakeTaskNotificationMessage("task done"),
            FakeSystemMessage("init", {"model": "claude-opus-5"}),
            FakeLegacyAssistantMessage(content=[FakeTextBlock("no stop_reason field")]),
        ],
    )
    def test_ordinary_messages_are_not_refusals(self, runner, message):
        assert runner._refusal_from_message(message) is None

    def test_missing_stop_reason_field_does_not_raise(self, runner):
        """Old SDK message shapes have no `stop_reason` attribute at all."""

        class Bare:
            pass

        assert runner._refusal_from_message(Bare()) is None

    def test_non_string_stop_reason_is_ignored(self, runner):
        msg = FakeAssistantMessage()
        msg.stop_reason = object()
        assert runner._refusal_from_message(msg) is None

    def test_explanation_is_truncated(self, runner):
        msg = FakeAssistantMessage(content=[FakeTextBlock("x" * 5000)], stop_reason="refusal")
        event = runner._refusal_from_message(msg)
        assert len(event["explanation"]) == runner._REFUSAL_TEXT_LIMIT


# --- _refusal_summary -------------------------------------------------------


class TestRefusalSummary:
    def test_empty_is_not_detected(self, runner):
        s = runner._refusal_summary([])
        assert s == {
            "detected": False,
            "declines": 0,
            "fallbacks_served": 0,
            "unrecovered": 0,
            "categories": [],
            "events": [],
        }

    def test_decline_without_fallback_is_unrecovered(self, runner):
        s = runner._refusal_summary([{"served_by_fallback": False, "category": "cyber"}])
        assert s["detected"] is True
        assert s["unrecovered"] == 1
        assert s["categories"] == ["cyber"]

    def test_fallback_cancels_the_decline_it_recovered(self, runner):
        """A recovered episode emits both shapes — the retracted turn, then the notice."""
        s = runner._refusal_summary(
            [
                {"served_by_fallback": False, "category": None},
                {"served_by_fallback": True, "category": "cyber"},
            ]
        )
        assert s["detected"] is True
        assert s["declines"] == 1
        assert s["fallbacks_served"] == 1
        assert s["unrecovered"] == 0

    def test_second_unrecovered_decline_still_counts(self, runner):
        """One recovery does not absolve a later decline that produced nothing."""
        s = runner._refusal_summary(
            [
                {"served_by_fallback": False, "category": None},
                {"served_by_fallback": True, "category": "cyber"},
                {"served_by_fallback": False, "category": None},
            ]
        )
        assert s["unrecovered"] == 1

    def test_fallback_without_a_streamed_decline_is_not_negative(self, runner):
        """A refusal before any output emits only the notice."""
        s = runner._refusal_summary([{"served_by_fallback": True, "category": "bio"}])
        assert s["unrecovered"] == 0
        assert s["detected"] is True

    def test_events_are_capped(self, runner):
        s = runner._refusal_summary([{"served_by_fallback": False}] * 50)
        assert len(s["events"]) == runner._REFUSAL_EVENT_LIMIT
        assert s["declines"] == 50  # counts are not capped, only the payload


# --- run_task end to end ----------------------------------------------------


class TestRunTaskExitCode:
    def test_clean_run_is_not_flagged(self, runner):
        out = run(
            runner,
            [
                FakeAssistantMessage(content=[FakeTextBlock("working")], stop_reason="tool_use"),
                FakeAssistantMessage(content=[FakeTextBlock("done")], stop_reason="end_turn"),
                FakeResultMessage(result='{"task_status": "complete"}', num_turns=2),
            ],
        )
        assert out["exit_code"] == 0
        assert out["refusal"]["detected"] is False
        assert out["refusal"]["unrecovered"] == 0
        assert read_log(runner)["refusal"]["detected"] is False

    def test_unrecovered_refusal_fails_the_run(self, runner):
        """The hole this closes: HTTP 200 + empty content used to exit 0."""
        out = run(
            runner,
            [
                FakeAssistantMessage(content=[], stop_reason="refusal"),
                FakeResultMessage(result="", num_turns=1),
            ],
        )
        assert out["exit_code"] == 4
        assert out["refusal"]["detected"] is True
        assert out["refusal"]["declines"] == 1
        assert out["refusal"]["unrecovered"] == 1
        assert runner._EXIT_REASONS[4] == "classifier_refusal"

    def test_refusal_on_the_result_message_fails_the_run(self, runner):
        out = run(runner, [FakeResultMessage(result="", stop_reason="refusal")])
        assert out["exit_code"] == 4

    def test_fallback_served_run_keeps_exit_zero_but_is_recorded(self, runner):
        """Model drift precedent: a real answer from an unpinned model — warn, do not fail.

        Failing here would re-run a finished spec, which is the BUG-188 mistake.
        """
        out = run(
            runner,
            [
                FakeAssistantMessage(content=[], stop_reason="refusal"),
                refusal_fallback_message("cyber"),
                FakeAssistantMessage(content=[FakeTextBlock("report")], stop_reason="end_turn"),
                FakeResultMessage(result='{"task_status": "complete"}', num_turns=3),
            ],
        )
        assert out["exit_code"] == 0
        assert out["refusal"]["detected"] is True
        assert out["refusal"]["fallbacks_served"] == 1
        assert out["refusal"]["unrecovered"] == 0
        assert out["refusal"]["categories"] == ["cyber"]

    def test_category_reaches_the_run_log(self, runner):
        run(
            runner,
            [
                refusal_fallback_message("cyber"),
                FakeResultMessage(result="ok"),
            ],
        )
        logged = read_log(runner)
        assert logged["refusal"]["categories"] == ["cyber"]
        assert logged["refusal"]["events"][0]["fallback_model"] == "claude-opus-4-8"
        assert logged["refusal"]["events"][0]["explanation"]

    def test_refusal_does_not_mask_a_more_specific_exit_code(self, runner):
        """A CLI process error keeps code 3 — the refusal is still reported."""

        async def _query(**_kwargs):
            yield FakeAssistantMessage(content=[], stop_reason="refusal")
            raise FakeProcessError("cli died")

        runner.query = _query
        out = asyncio.run(runner.run_task(str(Path.cwd()), "/autopilot T", "autopilot"))
        assert out["exit_code"] == 3
        assert out["refusal"]["unrecovered"] == 1

    def test_result_error_run_is_untouched_by_refusal_logic(self, runner):
        out = run(runner, [FakeResultMessage(is_error=True, result="boom")])
        assert out["exit_code"] == 1
        assert out["refusal"]["detected"] is False

    def test_legacy_messages_without_stop_reason_do_not_break_the_run(self, runner):
        out = run(
            runner,
            [
                FakeLegacyAssistantMessage(content=[FakeTextBlock("hello")]),
                FakeResultMessage(result="ok"),
            ],
        )
        assert out["exit_code"] == 0
        assert out["refusal"]["detected"] is False


class TestADR024Intact:
    """A post-ResultMessage SDK exception must still not turn exit 0 into a failure."""

    def test_post_result_exception_keeps_exit_zero(self, runner):
        async def _query(**_kwargs):
            yield FakeResultMessage(result='{"task_status": "complete"}', num_turns=2)
            raise RuntimeError("SDK threw after the result")

        runner.query = _query
        out = asyncio.run(runner.run_task(str(Path.cwd()), "/autopilot T", "autopilot"))
        assert out["exit_code"] == 0
        assert out["refusal"]["detected"] is False

    def test_post_result_exception_after_a_recovered_refusal_keeps_exit_zero(self, runner):
        async def _query(**_kwargs):
            yield FakeAssistantMessage(content=[], stop_reason="refusal")
            yield refusal_fallback_message("cyber")
            yield FakeResultMessage(result='{"task_status": "complete"}', num_turns=3)
            raise RuntimeError("SDK threw after the result")

        runner.query = _query
        out = asyncio.run(runner.run_task(str(Path.cwd()), "/autopilot T", "autopilot"))
        assert out["exit_code"] == 0
        assert out["refusal"]["fallbacks_served"] == 1

    def test_bug188_branch_does_not_assign_exit_code(self):
        """Source-level guard: the refusal upgrade lives outside the BUG-188 block."""
        source = RUNNER_PATH.read_text(encoding="utf-8")
        start = source.index("result_received and not result_is_error")
        end = source.index('elif "timeout"', start)
        block = source[start:end]
        assert "exit_code =" not in block and "exit_code=" not in block

    def test_refusal_upgrade_is_guarded_on_exit_code_zero(self):
        source = RUNNER_PATH.read_text(encoding="utf-8")
        assert 'if refusal["unrecovered"] and exit_code == 0:' in source


class TestTelemetry:
    def test_refusal_is_written_to_its_own_table(self, runner):
        calls = []

        class RecordingDB:
            def log_classifier_refusal(self, **kwargs):
                calls.append(kwargs)
                return 1

            def log_sdk_post_result_error(self, **kwargs):  # must not be used
                raise AssertionError("refusals must not land in sdk_post_result_errors")

        runner._orch_db = RecordingDB()
        run(
            runner,
            [
                FakeAssistantMessage(content=[], stop_reason="refusal"),
                FakeResultMessage(result=""),
            ],
            task="/autopilot TECH-9",
        )
        assert len(calls) == 1
        assert calls[0]["task"] == "/autopilot TECH-9"
        assert calls[0]["skill"] == "autopilot"
        assert calls[0]["unrecovered"] == 1
        assert calls[0]["exit_code"] == 4
        assert json.loads(calls[0]["detail"])[0]["source"] == "FakeAssistantMessage"

    def test_no_telemetry_on_a_clean_run(self, runner):
        class ExplodingDB:
            def log_classifier_refusal(self, **kwargs):
                raise AssertionError("no refusal happened")

        runner._orch_db = ExplodingDB()
        out = run(runner, [FakeResultMessage(result="ok")])
        assert out["exit_code"] == 0

    def test_telemetry_failure_never_breaks_the_run(self, runner):
        """ADR-004: telemetry is best-effort, the run's verdict is not."""

        class BrokenDB:
            def log_classifier_refusal(self, **kwargs):
                raise RuntimeError("db is down")

        runner._orch_db = BrokenDB()
        out = run(
            runner,
            [
                FakeAssistantMessage(content=[], stop_reason="refusal"),
                FakeResultMessage(result=""),
            ],
        )
        assert out["exit_code"] == 4
        assert read_log(runner)["refusal"]["unrecovered"] == 1
