"""Tests for claude-runner timeout path and heartbeat (TECH-197).

EC-1: Timeout writes telemetry
EC-2: BUG-188 guard intact
EC-3: Heartbeat per turn
EC-5: Variant-C never introduced (grep test)

Note: SDK query() loop cannot be tested end-to-end without the actual
Claude CLI. These tests verify structural properties: imports, heartbeat
writer, module compilation, and code invariants.
"""

import ast
import json
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)


class TestModuleCompiles:
    """AV-S1: claude-runner compiles without errors."""

    def test_py_compile(self):
        import py_compile

        py_compile.compile(
            str(Path(VPS_DIR) / "claude-runner.py"),
            doraise=True,
        )


class TestAsyncioTimeoutStructure:
    """EC-1 structural: asyncio.timeout is used, not asyncio.wait_for."""

    def test_no_wait_for_in_source(self):
        source = (Path(VPS_DIR) / "claude-runner.py").read_text(encoding="utf-8")
        assert "asyncio.wait_for" not in source, (
            "asyncio.wait_for should be replaced by asyncio.timeout"
        )

    def test_asyncio_timeout_present(self):
        source = (Path(VPS_DIR) / "claude-runner.py").read_text(encoding="utf-8")
        assert "asyncio.timeout" in source, "asyncio.timeout context manager must be present"

    def test_exit_code_124_on_timeout(self):
        """Parse AST to verify exit_code=124 is assigned in a TimeoutError handler."""
        source = (Path(VPS_DIR) / "claude-runner.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                handler_name = None
                if isinstance(node.type, ast.Name):
                    handler_name = node.type.id
                if handler_name == "TimeoutError":
                    for child in ast.walk(node):
                        if isinstance(child, ast.Assign):
                            for target in child.targets:
                                # TECH-213 moved the run loop's counters into `state`, so
                                # the assignment reads state["exit_code"] = 124 rather than
                                # a bare name. Both shapes satisfy the property under test:
                                # a TimeoutError handler sets 124.
                                is_name = isinstance(target, ast.Name) and target.id == "exit_code"
                                is_state = (
                                    isinstance(target, ast.Subscript)
                                    and isinstance(target.value, ast.Name)
                                    and target.value.id == "state"
                                    and isinstance(target.slice, ast.Constant)
                                    and target.slice.value == "exit_code"
                                )
                                if is_name or is_state:
                                    if (
                                        isinstance(child.value, ast.Constant)
                                        and child.value.value == 124
                                    ):
                                        found = True
        assert found, "except TimeoutError must set exit_code = 124"


class TestBUG188GuardIntact:
    """EC-2: result_received and not result_is_error → exit_code stays 0."""

    def test_bug188_guard_present_in_source(self):
        # TECH-213: the loop and its exception mapping live in runner_loop.py.
        source = (Path(VPS_DIR) / "runner_loop.py").read_text(encoding="utf-8")
        assert "result_received and not result_is_error" in source, "BUG-188 guard must be present"

    def test_bug188_exit_code_stays_zero(self):
        """Verify the guard does NOT reassign exit_code in the BUG-188 branch."""
        # TECH-213: the loop and its exception mapping live in runner_loop.py.
        source = (Path(VPS_DIR) / "runner_loop.py").read_text(encoding="utf-8")
        # Find the BUG-188 block: between 'result_received and not result_is_error'
        # and 'elif "timeout"' — exit_code must NOT be reassigned
        idx_start = source.index("result_received and not result_is_error")
        idx_end = source.index('elif "timeout"', idx_start)
        block = source[idx_start:idx_end]
        assert "exit_code =" not in block and "exit_code=" not in block, (
            "BUG-188 guard block must NOT reassign exit_code"
        )


class TestHeartbeatWriter:
    """EC-3: heartbeat file updated per turn, atomic write."""

    def _load_module(self):
        """Load claude-runner module with stubbed SDK deps."""
        import importlib
        import importlib.util

        # Create a minimal fake SDK if not present
        fake_sdk = type(sys)("claude_agent_sdk")
        fake_sdk.AssistantMessage = object
        fake_sdk.ClaudeAgentOptions = object
        fake_sdk.ResultMessage = object
        fake_sdk.TaskNotificationMessage = object

        async def _fake_query(**kwargs):
            return
            yield  # unreachable, but its presence makes this an async generator

        fake_sdk.query = _fake_query
        sys.modules.setdefault("claude_agent_sdk", fake_sdk)

        fake_errors = type(sys)("claude_agent_sdk._errors")
        fake_errors.CLIConnectionError = Exception
        fake_errors.ProcessError = Exception
        sys.modules.setdefault("claude_agent_sdk._errors", fake_errors)

        # runner_loop binds SDK names at import; reload it with the fake too.
        sys.modules.pop("runner_loop", None)
        spec = importlib.util.spec_from_file_location(
            f"claude_runner_{id(self)}",
            str(Path(VPS_DIR) / "claude-runner.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pytest.skip("Module exited during import (no SDK)")
        return mod

    def test_write_heartbeat_creates_file(self, tmp_path):
        mod = self._load_module()

        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        mod._write_heartbeat(
            log_dir=log_dir,
            project_name="test-proj",
            ts_label="20260606-120000",
            turn=3,
            elapsed_s=42,
            last_tool="Bash",
            started_at_iso="2026-06-06T12:00:00Z",
            model="claude-opus-4-8",
        )
        hb = log_dir / "test-proj-20260606-120000.heartbeat.json"
        assert hb.exists(), "heartbeat file must be created"
        data = json.loads(hb.read_text(encoding="utf-8"))
        assert data["turn"] == 3
        assert data["elapsed_s"] == 42
        assert data["last_tool"] == "Bash"
        assert data["model"] == "claude-opus-4-8"
        assert "updated_at" in data

    def test_heartbeat_no_tmp_left(self, tmp_path):
        """Atomic write: no .tmp file left after success."""
        mod = self._load_module()

        log_dir = tmp_path / "logs2"
        log_dir.mkdir()
        mod._write_heartbeat(log_dir, "p", "ts", 1, 0, None, "iso", "m")
        tmp_files = list(log_dir.glob("*.tmp"))
        assert len(tmp_files) == 0, "no .tmp file should remain"

    def test_heartbeat_overwrites_on_second_call(self, tmp_path):
        """Second call updates the same file (idempotent path)."""
        mod = self._load_module()

        log_dir = tmp_path / "logs3"
        log_dir.mkdir()
        mod._write_heartbeat(log_dir, "proj", "label", 1, 10, "Read", "iso", "model")
        mod._write_heartbeat(log_dir, "proj", "label", 2, 20, "Write", "iso", "model")
        hb = log_dir / "proj-label.heartbeat.json"
        data = json.loads(hb.read_text(encoding="utf-8"))
        assert data["turn"] == 2, "second write must overwrite first"
        assert data["last_tool"] == "Write"

    def test_heartbeat_called_per_message_in_source(self):
        """Verify _write_heartbeat is called for every SDK message (TECH-198).

        Post-TECH-198: heartbeat fires at the top of `async for message`,
        BEFORE the isinstance(AssistantMessage) branch, so updated_at stays
        fresh during long tool-execution phases.
        """
        # TECH-213: the loop and its exception mapping live in runner_loop.py.
        source = (Path(VPS_DIR) / "runner_loop.py").read_text(encoding="utf-8")
        # The heartbeat call must appear inside the async for loop,
        # BEFORE the AssistantMessage check (TECH-198 Layer A)
        idx_hb = source.index("_write_heartbeat(")
        idx_assistant = source.index("isinstance(message, AssistantMessage)")
        assert idx_hb < idx_assistant, (
            "_write_heartbeat must be called before AssistantMessage check (per-message)"
        )


class TestVariantCNeverIntroduced:
    """EC-5: callback gate NEVER returns done from local-only develop."""

    def test_no_local_develop_gate_path(self):
        """find_implementation_commit must check origin/develop, never just 'develop'."""
        source = (Path(VPS_DIR) / "gate_logic.py").read_text(encoding="utf-8")
        import re

        fn_match = re.search(
            r"def find_implementation_commit\(.*?\).*?(?=\ndef |\Z)", source, re.DOTALL
        )
        assert fn_match, "find_implementation_commit function not found"
        fn_body = fn_match.group()
        assert "origin/develop" in fn_body, "find_implementation_commit must check origin/develop"
        # Verify no bare "develop" (without origin/) as a git ref
        lines_with_bare_develop = [
            line
            for line in fn_body.split("\n")
            if '"develop"' in line and "origin/develop" not in line and "fetch" not in line.lower()
        ]
        assert len(lines_with_bare_develop) == 0, (
            f"find_implementation_commit must not use bare 'develop' ref: {lines_with_bare_develop}"
        )

    def test_push_local_is_best_effort_not_gate(self):
        """push-local is a flush helper, NOT a gate — gate must still check origin."""
        # TECH-216: the gate moved from callback.py into callback_sync.py
        # TECH-220: the gate entry point moved from gate_logic.find_implementation_commit
        # to gate_ancestry.find_implementation (ancestry first, that same subject call
        # as the fallback). The invariant under test is unchanged: push-local must not
        # replace the gate, and the gate must still resolve against origin.
        source = (Path(VPS_DIR) / "callback_sync.py").read_text(encoding="utf-8")
        # push-local block must NOT skip the gate calls
        assert "gate_logic.fetch_develop(" in source, (
            "gate_logic.fetch_develop must still be called"
        )
        assert "gate_ancestry.find_implementation(" in source, (
            "gate_ancestry.find_implementation must still be the gate"
        )

    def test_ancestry_gate_resolves_against_origin(self):
        """TECH-220: the ancestry path must compare against origin/develop, never bare 'develop'."""
        source = (Path(VPS_DIR) / "gate_ancestry.py").read_text(encoding="utf-8")
        assert "origin/develop" in source, "ancestry gate must check origin/develop"
        bare = [
            line
            for line in source.split("\n")
            if '"develop"' in line and "origin/develop" not in line and "fetch" not in line.lower()
        ]
        assert bare == [], f"ancestry gate must not use a bare 'develop' ref: {bare}"
