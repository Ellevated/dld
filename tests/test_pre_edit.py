"""Tests for .claude/hooks/pre_edit.py"""

import json
import sys
from pathlib import Path

# Import after adding hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / "template" / ".claude" / "hooks"))
from pre_edit import (
    MAX_LOC_CODE,
    WARN_THRESHOLD,
    count_lines,
    is_test_file,
    normalize_path,
)


class TestCountLines:
    """Tests for count_lines()."""

    def test_counts_lines_in_file(self, temp_python_file):
        """Should count lines correctly in a file."""
        file_path = temp_python_file("line1\nline2\nline3\n")

        result = count_lines(str(file_path))

        assert result == 3

    def test_returns_zero_for_empty_file(self, temp_python_file):
        """Should return 0 for empty file."""
        file_path = temp_python_file("")

        result = count_lines(str(file_path))

        assert result == 0

    def test_returns_zero_for_nonexistent_file(self):
        """Should return 0 for nonexistent file."""
        result = count_lines("/nonexistent/path/file.py")

        assert result == 0


class TestIsTestFile:
    """Tests for is_test_file()."""

    def test_detects_test_suffix(self):
        """Should detect _test.py suffix."""
        assert is_test_file("src/module_test.py") is True

    def test_detects_tests_directory(self):
        """Should detect files in /tests/ directory."""
        assert is_test_file("path/tests/test_module.py") is True
        assert is_test_file("root/tests/unit/test_something.py") is True

    def test_returns_false_for_regular_files(self):
        """Should return False for regular files."""
        assert is_test_file("src/module.py") is False
        assert is_test_file("src/service.py") is False


class TestNormalizePath:
    """Tests for normalize_path()."""

    def test_converts_absolute_to_relative(self, monkeypatch, tmp_path):
        """Should convert absolute path to relative."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        abs_path = str(tmp_path / "src" / "main.py")

        result = normalize_path(abs_path)

        assert result == "src/main.py"

    def test_keeps_relative_path_unchanged(self):
        """Should keep relative path as-is."""
        result = normalize_path("src/module.py")

        assert result == "src/module.py"

    def test_returns_empty_for_empty_input(self):
        """Should return empty string for empty input."""
        result = normalize_path("")

        assert result == ""


class TestProtectedPaths:
    """Tests for protected paths blocking."""

    def test_blocks_contracts_directory(self, mock_stdin, capture_stdout, mock_exit):
        """Should block files in tests/contracts/."""
        mock_stdin({"tool_input": {"file_path": "tests/contracts/test_api.py"}})

        with mock_exit():
            with capture_stdout() as output:
                from pre_edit import main

                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Protected test file" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "tests/contracts/" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_regression_directory(self, mock_stdin, capture_stdout, mock_exit):
        """Should block files in tests/regression/."""
        mock_stdin({"tool_input": {"file_path": "tests/regression/test_regression.py"}})

        with mock_exit():
            with capture_stdout() as output:
                from pre_edit import main

                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Protected test file" in result["hookSpecificOutput"]["permissionDecisionReason"]


class TestLocLimits:
    """Tests for LOC limit checks."""

    def test_asks_confirmation_when_exceeds_code_limit(
        self, mock_stdin, capture_stdout, mock_exit, temp_python_file, monkeypatch
    ):
        """Should ask confirmation when file exceeds 400 LOC."""
        # Create file with >400 lines
        file_path = temp_python_file("x = 1\n" * 450, "exceeds_limit.py")

        # Set project dir to tmp_path so normalize_path works correctly
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(file_path.parent))

        # Mock spec to allow this file (use just filename since we set PROJECT_DIR)
        spec_content = """
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `exceeds_limit.py` | modify |
"""
        spec_path = Path(file_path).parent / "test-spec.md"
        spec_path.write_text(spec_content)
        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        mock_stdin({"tool_input": {"file_path": str(file_path)}})

        with mock_exit():
            with capture_stdout() as output:
                from pre_edit import main

                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "File exceeds LOC limit" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "450 lines" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert f"limit: {MAX_LOC_CODE}" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_asks_confirmation_when_approaching_limit(
        self, mock_stdin, capture_stdout, mock_exit, temp_python_file, monkeypatch
    ):
        """Should ask confirmation when file approaches limit (>350 LOC)."""
        # Create file with >350 but <400 lines (7/8 * 400 = 350)
        warn_loc = int(MAX_LOC_CODE * WARN_THRESHOLD)  # 350
        file_path = temp_python_file("x = 1\n" * (warn_loc + 10), "approaching_limit.py")

        # Set project dir to tmp_path so normalize_path works correctly
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(file_path.parent))

        # Mock spec to allow this file
        spec_content = """
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `approaching_limit.py` | modify |
"""
        spec_path = Path(file_path).parent / "test-spec.md"
        spec_path.write_text(spec_content)
        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        mock_stdin({"tool_input": {"file_path": str(file_path)}})

        with mock_exit():
            with capture_stdout() as output:
                from pre_edit import main

                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "approaching LOC limit" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_file_under_limit(self, mock_stdin, mock_exit, temp_python_file, monkeypatch):
        """Should allow files under LOC limit."""
        # Create file with <350 lines
        file_path = temp_python_file("x = 1\n" * 300, "under_limit.py")

        # Set project dir to tmp_path so normalize_path works correctly
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(file_path.parent))

        # Mock spec to allow this file
        spec_content = """
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `under_limit.py` | modify |
"""
        spec_path = Path(file_path).parent / "test-spec.md"
        spec_path.write_text(spec_content)
        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        mock_stdin({"tool_input": {"file_path": str(file_path)}})

        with mock_exit() as exit_mock:
            from pre_edit import main

            main()

        # Should exit with 0 (allow)
        exit_mock.assert_called_once_with(0)

    def test_uses_higher_limit_for_test_files(
        self, mock_stdin, mock_exit, temp_python_file, monkeypatch
    ):
        """Should use 600 LOC limit for test files."""
        # Create test file with 550 lines (>400 but <600)
        file_path = temp_python_file("def test_x(): pass\n" * 550, "module_test.py")

        # Set project dir to tmp_path so normalize_path works correctly
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(file_path.parent))

        # Mock spec to allow this file
        spec_content = """
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `module_test.py` | modify |
"""
        spec_path = Path(file_path).parent / "test-spec.md"
        spec_path.write_text(spec_content)
        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        mock_stdin({"tool_input": {"file_path": str(file_path)}})

        with mock_exit() as exit_mock:
            from pre_edit import main

            main()

        # Should exit with 0 (allow) because test file limit is 600
        exit_mock.assert_called_once_with(0)


class TestAllowedFilesIntegration:
    """Tests for Allowed Files integration."""

    def test_blocks_file_not_in_spec(
        self, mock_stdin, capture_stdout, mock_exit, temp_spec_file, monkeypatch
    ):
        """Should block file not in spec's Allowed Files."""
        spec_path = temp_spec_file("""
# Feature Spec

## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
| 2 | `src/utils.py` | create |
""")
        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        mock_stdin({"tool_input": {"file_path": "src/secret.py"}})

        with mock_exit():
            with capture_stdout() as output:
                from pre_edit import main

                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert (
            "File not in Allowed Files" in result["hookSpecificOutput"]["permissionDecisionReason"]
        )
        assert "src/secret.py" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "src/main.py" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_file_in_spec(self, mock_stdin, mock_exit, temp_spec_file, monkeypatch):
        """Should allow file in spec's Allowed Files."""
        spec_path = temp_spec_file("""
# Feature Spec

## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
| 2 | `src/utils.py` | create |
""")
        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        mock_stdin({"tool_input": {"file_path": "src/main.py"}})

        with mock_exit() as exit_mock:
            from pre_edit import main

            main()

        # Should exit with 0 (allow)
        exit_mock.assert_called_once_with(0)
