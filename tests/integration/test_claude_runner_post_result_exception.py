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
  5. test_stderr_callback_captures_lines
  6. test_process_error_stderr_takes_precedence
"""

from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
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
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage  # noqa: E402
from claude_agent_sdk._errors import ProcessError  # noqa: E402
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


# ---------------------------------------------------------------------------
# Test 5: stderr callback captures lines and includes them in result_preview
# ---------------------------------------------------------------------------
def test_stderr_callback_captures_lines(monkeypatch, tmp_path):
    """BUG-188 Layer 2: CLI stderr lines captured via SDK callback appear in result_preview.

    The trick: ClaudeAgentOptions is constructed inside run_task, so we
    wrap it to intercept the stderr= kwarg and store the callback, then
    the fake_query closure calls it before raising.
    """
    captured_cb_holder: list = []

    def wrap_options(*args, **kwargs):
        cb = kwargs.get("stderr")
        if cb is not None:
            captured_cb_holder.append(cb)
        return ClaudeAgentOptions(*args, **kwargs)

    monkeypatch.setattr(claude_runner, "ClaudeAgentOptions", wrap_options)
    monkeypatch.setattr(claude_runner, "LOG_DIR", tmp_path)

    async def fake_query(prompt, options):
        # Push stderr lines via the captured callback before raising
        cb = captured_cb_holder[0]
        cb("CLI fatal: rate limit exceeded\n")
        cb("see https://example.com\n")
        raise Exception("Command failed with exit code 1")
        yield  # make this an async generator  # noqa: unreachable

    monkeypatch.setattr(claude_runner, "query", fake_query)
    log_data = asyncio.run(claude_runner.run_task(str(tmp_path), "/autopilot demo", "autopilot"))

    # No ResultMessage was received → genuine failure
    assert log_data["exit_code"] == 1, (
        f"Expected exit_code=1 (no ResultMessage), got {log_data['exit_code']}"
    )
    assert "STDERR (captured)" in log_data["result_preview"], (
        f"Expected 'STDERR (captured)' in result_preview, got: {log_data['result_preview']!r}"
    )
    assert "rate limit exceeded" in log_data["result_preview"], (
        f"Expected 'rate limit exceeded' in result_preview, got: {log_data['result_preview']!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: ProcessError.stderr takes precedence over captured stderr_lines
# ---------------------------------------------------------------------------
def test_process_error_stderr_takes_precedence(monkeypatch, tmp_path):
    """BUG-188 Layer 2: when ProcessError carries its own stderr, it wins over captured lines.

    Captured lines should NOT appear in result_preview when e.stderr is set.
    """
    captured_cb_holder: list = []

    def wrap_options(*args, **kwargs):
        cb = kwargs.get("stderr")
        if cb is not None:
            captured_cb_holder.append(cb)
        return ClaudeAgentOptions(*args, **kwargs)

    monkeypatch.setattr(claude_runner, "ClaudeAgentOptions", wrap_options)
    monkeypatch.setattr(claude_runner, "LOG_DIR", tmp_path)

    async def fake_query(prompt, options):
        # Push a captured line first
        cb = captured_cb_holder[0]
        cb("captured line\n")
        # Raise ProcessError with its own stderr attribute
        err = ProcessError("boom", exit_code=1, stderr="real-stderr-from-exc")
        raise err
        yield  # make this an async generator  # noqa: unreachable

    monkeypatch.setattr(claude_runner, "query", fake_query)
    log_data = asyncio.run(claude_runner.run_task(str(tmp_path), "/autopilot demo", "autopilot"))

    assert log_data["exit_code"] == 3, (
        f"Expected exit_code=3 (ProcessError), got {log_data['exit_code']}"
    )
    assert "real-stderr-from-exc" in log_data["result_preview"], (
        f"Expected real-stderr-from-exc in result_preview, got: {log_data['result_preview']!r}"
    )
    assert "STDERR (captured)" not in log_data["result_preview"], (
        f"'STDERR (captured)' must NOT appear when ProcessError.stderr is set; "
        f"got: {log_data['result_preview']!r}"
    )


# ---------------------------------------------------------------------------
# Test 7: BUG-188 Layer 4 — post-result exception inserts telemetry row
# ---------------------------------------------------------------------------
def test_post_result_exception_logs_telemetry_row(monkeypatch, tmp_path):
    """BUG-188 Layer 4: SDK throws after ResultMessage → telemetry row inserted, exit_code=0."""
    # Set DB_PATH first, before db module loads
    db_path = tmp_path / "orchestrator.db"
    schema_sql = (SCRIPT_DIR / "schema.sql").read_text()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_sql)
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db_path))

    # Reload db so it picks up the new DB_PATH
    if "db" in sys.modules:
        del sys.modules["db"]
    import db  # noqa: PLC0415
    db._MIGRATIONS_APPLIED = False
    monkeypatch.setattr(claude_runner, "_orch_db", db)
    monkeypatch.setattr(claude_runner, "LOG_DIR", tmp_path)

    async def fake_query(*, prompt, options):
        yield _make_assistant("ok")
        yield _make_result(is_error=False, turns=43, cost=6.32, result="DONE")
        raise Exception("post-cleanup error")

    monkeypatch.setattr(claude_runner, "query", fake_query)
    log_data = asyncio.run(claude_runner.run_task(str(tmp_path), "/autopilot demo-task", "autopilot"))

    assert log_data["exit_code"] == 0  # Layer 1 still holds
    # Telemetry row inserted
    with db.get_db() as conn:
        rows = list(conn.execute("SELECT * FROM sdk_post_result_errors").fetchall())
    assert len(rows) == 1
    row = rows[0]
    assert row["project_id"] == tmp_path.name  # project_name = Path(project_dir).name
    assert row["task"] == "/autopilot demo-task"
    assert row["turns"] == 43
    assert abs(row["cost_usd"] - 6.32) < 0.001
    assert "post-cleanup error" in row["error_msg"]
