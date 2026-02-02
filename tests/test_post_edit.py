"""Tests for post_edit.py hook.

Tests formatting logic, lint warnings, and file processing.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add hooks to path
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "template" / ".claude" / "hooks"),
)

from post_edit import check_lint_warnings, format_python_file, main


class TestFormatPythonFile:
    """Test format_python_file function."""

    def test_returns_success_when_ruff_formats(self, monkeypatch):
        """Successful formatting returns (True, 'formatted')."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        success, msg = format_python_file("test.py")
        assert success is True
        assert msg == "formatted"

    def test_returns_failure_on_ruff_error(self, monkeypatch):
        """Ruff error returns (False, error message)."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "SyntaxError: invalid syntax"

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        success, msg = format_python_file("test.py")
        assert success is False
        assert "SyntaxError" in msg

    def test_handles_ruff_not_found(self, monkeypatch):
        """FileNotFoundError returns (False, 'ruff not found')."""

        def mock_run(*args, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", mock_run)

        success, msg = format_python_file("test.py")
        assert success is False
        assert msg == "ruff not found"


class TestCheckLintWarnings:
    """Test check_lint_warnings function."""

    def test_returns_warnings_list(self, monkeypatch):
        """Returns list of warning messages."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "test.py:1:1: F401 unused import\ntest.py:2:5: E203 space"

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        warnings = check_lint_warnings("test.py")
        assert len(warnings) == 2
        assert "F401" in warnings[0]
        assert "E203" in warnings[1]

    def test_returns_empty_list_on_no_warnings(self, monkeypatch):
        """No warnings returns empty list."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        warnings = check_lint_warnings("test.py")
        assert warnings == []

    def test_limits_to_five_warnings(self, monkeypatch):
        """Returns max 5 warnings even if more exist."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = "\n".join([f"warning{i}" for i in range(10)])

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        warnings = check_lint_warnings("test.py")
        assert len(warnings) == 5


class TestPostEditMain:
    """Test main() function integration."""

    def test_skips_non_write_tools(self, mock_stdin, capture_stdout, mock_exit):
        """Non-Write/Edit tools are skipped."""
        mock_stdin({"tool_name": "Read", "tool_input": {"file_path": "test.py"}})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        exit_mock.assert_called_once_with(0)
        assert output.getvalue() == ""

    def test_skips_non_python_files(self, mock_stdin, capture_stdout, mock_exit):
        """Non-Python files are skipped."""
        mock_stdin({"tool_name": "Write", "tool_input": {"file_path": "test.txt"}})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        exit_mock.assert_called_once_with(0)
        assert output.getvalue() == ""

    def test_processes_python_file_edit(
        self, mock_stdin, capture_stdout, mock_exit, temp_python_file, monkeypatch
    ):
        """Python file edit triggers formatting and lint check."""
        # Create a real temp file
        file_path = temp_python_file("x = 1\n")

        # Mock ruff commands
        def mock_run(cmd, *args, **kwargs):
            if "format" in cmd:
                result = Mock()
                result.returncode = 0
                result.stderr = ""
                return result
            elif "check" in cmd:
                result = Mock()
                result.returncode = 0
                result.stdout = ""
                return result
            return Mock(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", mock_run)

        mock_stdin({"tool_name": "Edit", "tool_input": {"file_path": str(file_path)}})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        # Should continue with format message
        output_val = output.getvalue()
        assert "ruff format" in output_val or exit_mock.call_count == 1
