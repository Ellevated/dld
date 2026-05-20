"""BUG-188 — regression tests for claude-runner post-ResultMessage exception handling.

Verifies that exit_code=0 is preserved when SDK throws AFTER a successful
ResultMessage(is_error=False) was already received.

The external claude_agent_sdk boundary is patched via monkeypatch (no
unittest.mock) — the planner approved patching this boundary since the
SDK is an external process wrapper, not business logic.

Test plan:
  1. test_post_result_exception_preserves_success
  2. test_pre_result_exception_marks_failure
  3. test_result_message_is_error_true_marks_failure
  4. test_timeout_exception_uses_exit_124
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# ---------------------------------------------------------------------------
# SDK site-packages must be in sys.path BEFORE loading claude-runner module
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
_VENV_SITE = str(SCRIPT_DIR / "venv" / "lib" / "python3.12" / "site-packages")
if _VENV_SITE not in sys.path:
    sys.path.insert(0, _VENV_SITE)

# ---------------------------------------------------------------------------
# SDK message helpers — use real SDK types to match isinstance() checks
# ---------------------------------------------------------------------------
from claude_agent_sdk import AssistantMessage, ResultMessage  # noqa: E402
from claude_agent_sdk.types import TextBlock  # noqa: E402

# ---------------------------------------------------------------------------
# Load claude-runner module (hyphenated filename — cannot plain-import)
# ---------------------------------------------------------------------------
_runner_path = SCRIPT_DIR / "claude-runner.py"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_spec = importlib.util.spec_from_file_location("claude_runner", str(_runner_path))
claude_runner = importlib.util.module_from_spec(_spec)
sys.modules["claude_runner"] = claude_runner
_spec.loader.exec_module(claude_runner)


def _make_result(is_error: bool, turns: int = 43, cost: float = 6.32, result: str = "DONE") -> ResultMessage:
    return ResultMessage(
        subtype="result",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=is_error,
        num_turns=turns,
        session_id="test-session",
        total_cost_usd=cost,
        result=result,
        usage={"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 0},
    )


def _make_assistant(text: str = "ok") -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=text)], model="claude-opus-4-7")


# ---------------------------------------------------------------------------
# Helper to run a task with a fake query function
# ---------------------------------------------------------------------------
def _run(fake_query, project_dir: str, monkeypatch, tmp_path) -> dict:
    """Patch claude_runner.query with fake_query and run run_task."""
    monkeypatch.setattr(claude_runner, "LOG_DIR", tmp_path)
    monkeypatch.setattr(claude_runner, "query", fake_query)
    return asyncio.run(claude_runner.run_task(str(project_dir), "TEST-001", "autopilot"))


# ---------------------------------------------------------------------------
# Test 1: SDK throws AFTER successful ResultMessage → exit_code must stay 0
# ---------------------------------------------------------------------------
def test_post_result_exception_preserves_success(monkeypatch, tmp_path):
    """Regression for BUG-188: SDK throws after ResultMessage(is_error=False)."""

    async def fake_query(prompt, options):
        yield _make_assistant("ok")
        yield _make_result(is_error=False, turns=43, cost=6.32, result="DONE")
        raise Exception("Command failed with exit code 1")

    log_data = _run(fake_query, tmp_path, monkeypatch, tmp_path)

    assert log_data["exit_code"] == 0, (
        f"Expected exit_code=0 after post-ResultMessage exception, got {log_data['exit_code']}"
    )
    assert log_data["turns"] == 43
    assert abs(log_data["cost_usd"] - 6.32) < 0.001
    assert log_data["result_preview"], "result_preview must be non-empty (from ResultMessage)"


# ---------------------------------------------------------------------------
# Test 2: Exception BEFORE any ResultMessage → exit_code must be 1
# ---------------------------------------------------------------------------
def test_pre_result_exception_marks_failure(monkeypatch, tmp_path):
    """SDK fails immediately without yielding ResultMessage → genuine failure."""

    async def fake_query(prompt, options):
        raise Exception("init failure")
        yield  # make it an async generator  # noqa: unreachable

    log_data = _run(fake_query, tmp_path, monkeypatch, tmp_path)

    assert log_data["exit_code"] == 1, (
        f"Expected exit_code=1 for pre-ResultMessage exception, got {log_data['exit_code']}"
    )
    assert log_data["turns"] == 0


# ---------------------------------------------------------------------------
# Test 3: ResultMessage(is_error=True) → exit_code must be 1
# ---------------------------------------------------------------------------
def test_result_message_is_error_true_marks_failure(monkeypatch, tmp_path):
    """Genuine failure: SDK returns ResultMessage with is_error=True."""

    async def fake_query(prompt, options):
        yield _make_result(is_error=True, turns=5, cost=0.1, result="oops")

    log_data = _run(fake_query, tmp_path, monkeypatch, tmp_path)

    assert log_data["exit_code"] == 1, (
        f"Expected exit_code=1 for ResultMessage(is_error=True), got {log_data['exit_code']}"
    )
    assert log_data["turns"] == 5


# ---------------------------------------------------------------------------
# Test 4: Timeout exception before ResultMessage → exit_code must be 124
# ---------------------------------------------------------------------------
def test_timeout_exception_uses_exit_124(monkeypatch, tmp_path):
    """SDK timeout before ResultMessage → exit_code=124 (standard timeout code)."""

    async def fake_query(prompt, options):
        raise Exception("Control request timeout: initialize")
        yield  # make it an async generator  # noqa: unreachable

    log_data = _run(fake_query, tmp_path, monkeypatch, tmp_path)

    assert log_data["exit_code"] == 124, (
        f"Expected exit_code=124 for timeout exception, got {log_data['exit_code']}"
    )
