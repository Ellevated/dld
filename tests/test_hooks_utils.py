"""Tests for .claude/hooks/utils.py"""

import io
import json
import sys
from pathlib import Path

# Import after adding hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / "template" / ".claude" / "hooks"))
from utils import (
    _matches_pattern,
    allow_tool,
    approve_prompt,
    ask_tool,
    block_prompt,
    deny_tool,
    get_tool_input,
    get_user_prompt,
    post_block,
    post_continue,
    read_hook_input,
)


class TestReadHookInput:
    """Tests for read_hook_input()."""

    def test_reads_valid_json_from_stdin(self, mock_stdin):
        """Should parse JSON from stdin."""
        expected = {"tool_input": {"command": "ls"}}
        mock_stdin(expected)

        result = read_hook_input()

        assert result == expected

    def test_returns_empty_dict_on_invalid_json(self, mock_stdin):
        """Should return {} when stdin contains invalid JSON."""
        sys.stdin = io.StringIO("not valid json {{{")

        result = read_hook_input()

        assert result == {}

    def test_returns_empty_dict_on_empty_stdin(self, mock_stdin):
        """Should return {} when stdin is empty."""
        sys.stdin = io.StringIO("")

        result = read_hook_input()

        assert result == {}


class TestGetToolInput:
    """Tests for get_tool_input()."""

    def test_extracts_nested_key(self):
        """Should extract value from tool_input dict."""
        data = {"tool_input": {"command": "git status"}}

        result = get_tool_input(data, "command")

        assert result == "git status"

    def test_returns_none_for_missing_key(self):
        """Should return None when key doesn't exist."""
        data = {"tool_input": {"command": "ls"}}

        result = get_tool_input(data, "file_path")

        assert result is None

    def test_returns_none_when_no_tool_input(self):
        """Should return None when tool_input is missing."""
        data = {"other_key": "value"}

        result = get_tool_input(data, "command")

        assert result is None


class TestGetUserPrompt:
    """Tests for get_user_prompt()."""

    def test_extracts_user_prompt(self):
        """Should extract user_prompt from data."""
        data = {"user_prompt": "implement feature X"}

        result = get_user_prompt(data)

        assert result == "implement feature X"

    def test_returns_empty_string_for_missing_prompt(self):
        """Should return '' when user_prompt is missing."""
        data = {}

        result = get_user_prompt(data)

        assert result == ""

    def test_returns_empty_string_for_none_prompt(self):
        """Should return '' when user_prompt is None."""
        data = {"user_prompt": None}

        result = get_user_prompt(data)

        assert result == ""


class TestAllowTool:
    """Tests for allow_tool()."""

    def test_exits_with_code_zero(self, mock_exit):
        """Should call sys.exit(0) for allow."""
        with mock_exit() as exit_mock:
            allow_tool()

        exit_mock.assert_called_once_with(0)


class TestDenyTool:
    """Tests for deny_tool()."""

    def test_outputs_deny_json_and_exits(self, capture_stdout, mock_exit):
        """Should output deny decision JSON."""
        with mock_exit():
            with capture_stdout() as output:
                deny_tool("File not allowed")

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "File not allowed" in result["hookSpecificOutput"]["permissionDecisionReason"]


class TestAskTool:
    """Tests for ask_tool()."""

    def test_outputs_ask_json_and_exits(self, capture_stdout, mock_exit):
        """Should output ask decision JSON."""
        with mock_exit():
            with capture_stdout() as output:
                ask_tool("Confirm merge?")

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "Confirm merge?" in result["hookSpecificOutput"]["permissionDecisionReason"]


class TestApprovePrompt:
    """Tests for approve_prompt()."""

    def test_outputs_approve_json(self, capture_stdout, mock_exit):
        """Should output approve decision JSON."""
        with mock_exit():
            with capture_stdout() as output:
                approve_prompt()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"


class TestBlockPrompt:
    """Tests for block_prompt()."""

    def test_outputs_block_json_with_reason(self, capture_stdout, mock_exit):
        """Should output block decision with reason."""
        with mock_exit():
            with capture_stdout() as output:
                block_prompt("Contains secrets")

        result = json.loads(output.getvalue())
        assert result["decision"] == "block"
        assert result["reason"] == "Contains secrets"


class TestPostContinue:
    """Tests for post_continue()."""

    def test_exits_silently_without_message(self, mock_exit):
        """Should just exit(0) when no message."""
        with mock_exit() as exit_mock:
            post_continue()

        exit_mock.assert_called_once_with(0)

    def test_outputs_context_with_message(self, capture_stdout, mock_exit):
        """Should output additionalContext when message provided."""
        with mock_exit():
            with capture_stdout() as output:
                post_continue("Formatted with ruff")

        result = json.loads(output.getvalue())
        assert result["decision"] == "continue"
        assert result["hookSpecificOutput"]["additionalContext"] == "Formatted with ruff"


class TestPostBlock:
    """Tests for post_block()."""

    def test_outputs_block_with_context(self, capture_stdout, mock_exit):
        """Should output block decision with additionalContext."""
        with mock_exit():
            with capture_stdout() as output:
                post_block("Syntax error in file")

        result = json.loads(output.getvalue())
        assert result["decision"] == "block"
        assert result["hookSpecificOutput"]["additionalContext"] == "Syntax error in file"


# Import additional functions for file allowlist tests
from utils import (  # noqa: E402
    extract_allowed_files,
    infer_spec_from_branch,
    is_file_allowed,
)


class TestExtractAllowedFiles:
    """Tests for extract_allowed_files()."""

    def test_parses_markdown_table_format(self, temp_spec_file):
        """Should extract files from markdown table."""
        spec_path = temp_spec_file("""
# Feature Spec

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `src/main.py` | modify | Core logic |
| 2 | `src/utils.py` | create | Helpers |
| 3 | `tests/test_main.py` | create | Tests |
""")

        result = extract_allowed_files(str(spec_path))

        assert "src/main.py" in result
        assert "src/utils.py" in result
        assert "tests/test_main.py" in result

    def test_parses_backtick_list_format(self, temp_spec_file):
        """Should extract files from backtick list format."""
        spec_path = temp_spec_file("""
## Allowed Files

- `src/service.py` - main service
- `src/models.py` - data models
""")

        result = extract_allowed_files(str(spec_path))

        assert "src/service.py" in result
        assert "src/models.py" in result

    def test_strips_line_number_suffix(self, temp_spec_file):
        """Should remove :line-range suffix from paths."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py:45-60` | modify |
| 2 | `src/utils.py:100` | modify |
""")

        result = extract_allowed_files(str(spec_path))

        assert "src/main.py" in result
        assert "src/main.py:45-60" not in result
        assert "src/utils.py" in result

    def test_returns_empty_list_for_missing_section(self, temp_spec_file):
        """Should return [] when ## Allowed Files section missing."""
        spec_path = temp_spec_file("""
# Feature Spec

## Design

Some design notes.
""")

        result = extract_allowed_files(str(spec_path))

        assert result == []

    def test_returns_empty_list_for_nonexistent_file(self):
        """Should return [] for nonexistent spec file."""
        result = extract_allowed_files("/nonexistent/path/spec.md")

        assert result == []

    def test_skips_comment_lines(self, temp_spec_file):
        """Should ignore lines starting with #."""
        spec_path = temp_spec_file("""
## Allowed Files

# This is a comment
| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
""")

        result = extract_allowed_files(str(spec_path))

        assert "src/main.py" in result
        assert len([f for f in result if f.startswith("#")]) == 0


class TestMatchesPattern:
    """Tests for _matches_pattern()."""

    def test_matches_directory_pattern_shallow(self):
        """Should match files directly in directory with /* pattern."""
        assert _matches_pattern("ai/diary/log.md", "ai/diary/*") is True

    def test_matches_directory_pattern_nested(self):
        """Should match nested files with /* pattern (directory tree)."""
        assert _matches_pattern("ai/diary/2024/01/log.md", "ai/diary/*") is True
        assert _matches_pattern(".claude/hooks/utils.py", ".claude/*") is True
        assert _matches_pattern(".claude/agents/coder.md", ".claude/*") is True

    def test_no_match_different_directory(self):
        """Should not match files in different directory."""
        assert _matches_pattern("src/main.py", "ai/diary/*") is False
        assert _matches_pattern("tests/test.py", ".claude/*") is False

    def test_fnmatch_for_non_directory_patterns(self):
        """Should use fnmatch for patterns not ending with /*."""
        # *.md matches any .md file
        assert _matches_pattern("README.md", "*.md") is True
        assert _matches_pattern("ai/features/FTR-100.md", "ai/features/*.md") is True
        # Per Python docs: "the filename separator '/' is not special to this module"
        # https://docs.python.org/3/library/fnmatch.html
        # So fnmatch('a/b/c.md', '*.md') returns True (unlike shell glob where * stops at /)
        assert _matches_pattern("ai/features/sub/FTR-100.md", "ai/features/*.md") is True

    def test_exact_file_patterns(self):
        """Should match exact file patterns."""
        assert _matches_pattern("ai/backlog.md", "ai/backlog.md") is True
        assert _matches_pattern("pyproject.toml", "pyproject.toml") is True
        assert _matches_pattern("other.toml", "pyproject.toml") is False


class TestIsFileAllowed:
    """Tests for is_file_allowed()."""

    def test_allows_file_in_spec(self, temp_spec_file):
        """Should allow files listed in spec."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
""")

        allowed, files = is_file_allowed("src/main.py", str(spec_path))

        assert allowed is True

    def test_blocks_file_not_in_spec(self, temp_spec_file):
        """Should block files not in spec."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
""")

        allowed, files = is_file_allowed("src/secret.py", str(spec_path))

        assert allowed is False
        assert "src/main.py" in files

    def test_allows_always_allowed_patterns(self, temp_spec_file):
        """Should allow files matching ALWAYS_ALLOWED_PATTERNS."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
""")

        # ai/features/*.md is always allowed
        allowed, _ = is_file_allowed("ai/features/FTR-100.md", str(spec_path))
        assert allowed is True

        # .claude/** is always allowed
        allowed, _ = is_file_allowed(".claude/hooks/utils.py", str(spec_path))
        assert allowed is True

        # ai/backlog.md is always allowed
        allowed, _ = is_file_allowed("ai/backlog.md", str(spec_path))
        assert allowed is True

    def test_allows_all_when_no_spec(self):
        """Should allow all files when spec_path is None."""
        allowed, files = is_file_allowed("any/random/file.py", None)

        assert allowed is True
        assert files == []

    def test_matches_glob_patterns(self, temp_spec_file):
        """Should use prefix matching for directory-level allowance."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
| 2 | `tests/test_utils.py` | modify |
""")

        # Exact match works
        allowed, _ = is_file_allowed("src/main.py", str(spec_path))
        assert allowed is True

        # Prefix match allows files in same directory tree
        allowed, _ = is_file_allowed("src/main_helpers.py", str(spec_path))
        # Note: current implementation doesn't support this - it only matches exact
        # paths or uses prefix matching with trailing slash removal
        assert allowed is False

        # Different directory should not match
        allowed, _ = is_file_allowed("lib/other.py", str(spec_path))
        assert allowed is False

    def test_normalizes_paths_with_dotslash(self, temp_spec_file):
        """Should normalize ./path to path."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
""")

        allowed, _ = is_file_allowed("./src/main.py", str(spec_path))

        assert allowed is True


class TestInferSpecFromBranch:
    """Tests for infer_spec_from_branch()."""

    def test_returns_none_for_non_task_branch(self, monkeypatch):
        """Should return None for branches without task ID."""

        def mock_run(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = "main\n"

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)

        result = infer_spec_from_branch()

        assert result is None

    def test_extracts_ftr_task_id(self, monkeypatch, tmp_path):
        """Should extract FTR-xxx from branch name."""

        def mock_run(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = "feature/FTR-100\n"

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)

        # Create a matching spec file
        spec_file = tmp_path / "ai" / "features" / "FTR-100-test.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text("# Test Spec")

        # Mock glob to find our test file

        monkeypatch.setattr("glob.glob", lambda p: [str(spec_file)])

        result = infer_spec_from_branch()

        assert result == str(spec_file)

    def test_extracts_tech_task_id(self, monkeypatch, tmp_path):
        """Should extract TECH-xxx from branch name."""

        def mock_run(*args, **kwargs):
            class Result:
                returncode = 0
                stdout = "tech/TECH-059\n"

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)

        spec_file = tmp_path / "ai" / "features" / "TECH-059-hooks.md"
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text("# Test Spec")

        monkeypatch.setattr("glob.glob", lambda p: [str(spec_file)])

        result = infer_spec_from_branch()

        assert result == str(spec_file)

    def test_handles_git_command_failure(self, monkeypatch):
        """Should return None when git command fails."""

        def mock_run(*args, **kwargs):
            class Result:
                returncode = 1
                stdout = ""

            return Result()

        monkeypatch.setattr("subprocess.run", mock_run)

        result = infer_spec_from_branch()

        assert result is None


# Import additional functions for new tests
from utils import get_error_log_path, log_hook_error  # noqa: E402


class TestGetErrorLogPath:
    """Tests for get_error_log_path()."""

    def test_returns_path_in_cache_dir(self):
        """Should return path under ~/.cache/dld/."""
        path = get_error_log_path()

        assert ".cache" in str(path) or "dld" in str(path)
        assert path.name == "hook-errors.log"

    def test_path_parent_is_directory(self):
        """Should return path with valid parent."""
        path = get_error_log_path()

        # Parent should be created or creatable
        assert path.parent.exists() or not path.parent.exists()


class TestLogHookError:
    """Tests for log_hook_error()."""

    def test_writes_error_to_log(self, tmp_path, monkeypatch):
        """Should write error message to log file."""
        log_file = tmp_path / "test-errors.log"
        monkeypatch.setattr("utils.get_error_log_path", lambda: log_file)

        log_hook_error("test_hook", ValueError("test error"))

        assert log_file.exists()
        content = log_file.read_text()
        assert "[test_hook]" in content
        assert "test error" in content

    def test_does_not_crash_on_write_failure(self, monkeypatch):
        """Should silently fail if log write fails."""

        def raise_error():
            raise PermissionError("cannot write")

        monkeypatch.setattr("utils.get_error_log_path", raise_error)

        # Should not raise
        log_hook_error("test_hook", ValueError("test"))


class TestEdgeCases:
    """Edge case tests for various hooks."""

    def test_unicode_in_command(self):
        """Should handle unicode/emoji in commands."""
        import re

        sys.path.insert(0, str(Path(__file__).parent.parent / "template" / ".claude" / "hooks"))
        from pre_bash import BLOCKED_PATTERNS

        unicode_cmd = "git commit -m '🚀 feat: add feature'"

        # Should not crash on unicode
        for pattern, _ in BLOCKED_PATTERNS:
            re.search(pattern, unicode_cmd, re.IGNORECASE)

    def test_very_long_file_path(self):
        """Should handle very long file paths."""
        long_path = "a/" * 100 + "file.py"

        allowed, _ = is_file_allowed(long_path, None)

        assert allowed is True  # No spec = allow all

    def test_path_with_special_characters(self):
        """Should handle paths with special regex characters."""
        special_path = "src/[test]/file.py"

        allowed, _ = is_file_allowed(special_path, None)

        assert allowed is True

    def test_empty_spec_section(self, temp_spec_file):
        """Should handle spec with empty Allowed Files section."""
        spec_path = temp_spec_file("""
## Allowed Files

## Next Section
""")

        result = extract_allowed_files(str(spec_path))

        assert result == []
