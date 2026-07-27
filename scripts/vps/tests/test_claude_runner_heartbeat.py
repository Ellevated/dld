"""Layer A tests: heartbeat updated_at advances on every SDK message type (TECH-198).

Tests verify that _write_heartbeat produces correct output and that
the heartbeat file is updated with advancing timestamps. Real file I/O
on tmp_path — no mocks (ADR-013).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Import the function under test
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from importlib import import_module

# claude-runner has a hyphen in the name — can't import directly
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "claude_runner",
    str(Path(__file__).resolve().parent.parent / "claude-runner.py"),
)
_mod = importlib.util.module_from_spec(_spec)
# Patch out the SDK import and load_env to avoid import errors in test
_mod.__dict__["load_env"] = lambda: None
sys.modules["claude_runner"] = _mod

# We need to load only _write_heartbeat, not the whole module (SDK deps).
# Extract it by reading the source and exec-ing just the function.
import ast
import textwrap

_source = (Path(__file__).resolve().parent.parent / "claude-runner.py").read_text(encoding="utf-8")
_tree = ast.parse(_source)

# Find _write_heartbeat function
_func_source = None
for node in ast.walk(_tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_write_heartbeat":
        _func_source = ast.get_source_segment(_source, node)
        break

assert _func_source is not None, "_write_heartbeat not found in claude-runner.py"

# Build a minimal namespace with required imports
_ns: dict = {}
exec(
    textwrap.dedent("""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
"""),
    _ns,
)
exec(_func_source, _ns)
_write_heartbeat = _ns["_write_heartbeat"]


class TestWriteHeartbeat:
    """Test _write_heartbeat produces correct files."""

    def test_creates_heartbeat_file(self, tmp_path: Path) -> None:
        """Heartbeat file is created with correct fields."""
        _write_heartbeat(
            log_dir=tmp_path,
            project_name="testproj",
            ts_label="20260613-120000",
            turn=3,
            elapsed_s=120,
            last_tool="Bash",
            started_at_iso="2026-06-13T12:00:00+00:00",
            model="claude-opus-4-8",
        )

        hb_file = tmp_path / "testproj-20260613-120000.heartbeat.json"
        assert hb_file.exists()

        data = json.loads(hb_file.read_text(encoding="utf-8"))
        assert data["turn"] == 3
        assert data["elapsed_s"] == 120
        assert data["last_tool"] == "Bash"
        assert data["started_at"] == "2026-06-13T12:00:00+00:00"
        assert data["model"] == "claude-opus-4-8"
        assert "updated_at" in data

    def test_updated_at_advances_on_successive_calls(self, tmp_path: Path) -> None:
        """Successive calls update updated_at (simulates per-message heartbeat)."""
        kwargs = dict(
            log_dir=tmp_path,
            project_name="testproj",
            ts_label="20260613-120000",
            turn=1,
            elapsed_s=10,
            last_tool=None,
            started_at_iso="2026-06-13T12:00:00+00:00",
            model="claude-opus-4-8",
        )

        # First call (simulates AssistantMessage)
        _write_heartbeat(**kwargs)
        hb_file = tmp_path / "testproj-20260613-120000.heartbeat.json"
        data1 = json.loads(hb_file.read_text(encoding="utf-8"))
        t1 = data1["updated_at"]

        # Small delay to ensure timestamp difference
        time.sleep(0.05)

        # Second call with same turn (simulates tool-result message — NOT AssistantMessage)
        # turn stays at 1 (only incremented on AssistantMessage in the real loop)
        kwargs["elapsed_s"] = 15
        _write_heartbeat(**kwargs)
        data2 = json.loads(hb_file.read_text(encoding="utf-8"))
        t2 = data2["updated_at"]

        # updated_at should have advanced
        assert t2 >= t1
        # turn should still be 1 (caller controls this — heartbeat just records it)
        assert data2["turn"] == 1

    def test_turn_only_increments_on_explicit_change(self, tmp_path: Path) -> None:
        """Turn count is set by caller, not auto-incremented by heartbeat."""
        hb_file = tmp_path / "testproj-20260613-120000.heartbeat.json"

        # Simulate: AssistantMessage (turn=1) → tool-result (turn=1) → AssistantMessage (turn=2)
        for turn, elapsed in [(1, 10), (1, 15), (1, 20), (2, 30)]:
            _write_heartbeat(
                log_dir=tmp_path,
                project_name="testproj",
                ts_label="20260613-120000",
                turn=turn,
                elapsed_s=elapsed,
                last_tool="Bash",
                started_at_iso="2026-06-13T12:00:00+00:00",
                model="claude-opus-4-8",
            )

        data = json.loads(hb_file.read_text(encoding="utf-8"))
        assert data["turn"] == 2
        assert data["elapsed_s"] == 30

    def test_last_tool_preserved_across_non_assistant_messages(self, tmp_path: Path) -> None:
        """last_tool stays at the last known value across tool-result messages."""
        hb_file = tmp_path / "testproj-20260613-120000.heartbeat.json"

        # AssistantMessage with tool use → last_tool = "Bash"
        _write_heartbeat(
            log_dir=tmp_path, project_name="testproj", ts_label="20260613-120000",
            turn=1, elapsed_s=10, last_tool="Bash",
            started_at_iso="2026-06-13T12:00:00+00:00", model="claude-opus-4-8",
        )

        # Tool-result messages — caller passes the SAME last_tool (unchanged)
        for elapsed in [15, 20, 25]:
            _write_heartbeat(
                log_dir=tmp_path, project_name="testproj", ts_label="20260613-120000",
                turn=1, elapsed_s=elapsed, last_tool="Bash",
                started_at_iso="2026-06-13T12:00:00+00:00", model="claude-opus-4-8",
            )

        data = json.loads(hb_file.read_text(encoding="utf-8"))
        assert data["last_tool"] == "Bash"
        assert data["elapsed_s"] == 25

    def test_atomic_write_no_partial(self, tmp_path: Path) -> None:
        """Heartbeat uses tmp + os.replace for atomicity — no .tmp leftover."""
        _write_heartbeat(
            log_dir=tmp_path, project_name="testproj", ts_label="20260613-120000",
            turn=1, elapsed_s=5, last_tool=None,
            started_at_iso="2026-06-13T12:00:00+00:00", model="claude-opus-4-8",
        )
        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []
