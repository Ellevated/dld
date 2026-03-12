# Tech: [TECH-059] Unit Tests for Python Hooks

**Status:** done | **Priority:** P0 | **Date:** 2026-02-01

## Why

Python hooks (`utils.py`, `pre_edit.py`, `pre_bash.py`) have zero test coverage. For a project advocating "Test Safety" this is embarrassing. Critical for credibility before GitHub launch.

## Context

Current hooks:
- `utils.py` (349 LOC) — shared utilities
- `pre_edit.py` (147 LOC) — file protection
- `pre_bash.py` (128 LOC) — command blocking
- `post_edit.py` (121 LOC) — auto-formatting
- `prompt_guard.py` (92 LOC) — workflow suggestions

None have tests. Any regression goes unnoticed.

---

## Scope

**In scope:**
- Create tests/ directory with pytest structure
- Unit tests for all hooks
- CI integration (pytest in workflow)
- Coverage reporting

**Out of scope:**
- Integration tests with actual Claude Code
- E2E tests
- Performance benchmarks

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `tests/conftest.py` | create | Shared pytest fixtures |
| 2 | `tests/test_hooks_utils.py` | create | Test utils.py |
| 3 | `tests/test_pre_edit.py` | create | Test pre_edit.py |
| 4 | `tests/test_pre_bash.py` | create | Test pre_bash.py |
| 5 | `tests/test_post_edit.py` | create | Test post_edit.py |
| 6 | `tests/test_prompt_guard.py` | create | Test prompt_guard.py |
| 7 | `pyproject.toml` | create | Pytest config |
| 8 | `.github/workflows/ci.yml:44-60` | modify | Add pytest job |

**New files allowed:**
| # | File | Reason |
|---|------|--------|
| 1-6 | `tests/*.py` | Test files |
| 7 | `pyproject.toml` | Project config |

---

## Design

### Test Structure

```
tests/
├── conftest.py           # Fixtures
├── test_hooks_utils.py   # utils.py tests
├── test_pre_edit.py      # pre_edit.py tests
├── test_pre_bash.py      # pre_bash.py tests
├── test_post_edit.py     # post_edit.py tests
└── fixtures/
    ├── sample_spec.md    # Test spec file
    └── sample_code.py    # Test Python file
```

### Key Test Cases

**utils.py:**
- `test_extract_allowed_files_parses_markdown_table`
- `test_extract_allowed_files_handles_backtick_format`
- `test_is_file_allowed_matches_glob_patterns`
- `test_is_file_allowed_respects_always_allowed`
- `test_infer_spec_from_branch_extracts_task_id`

**pre_edit.py:**
- `test_blocks_protected_paths`
- `test_allows_files_in_spec`
- `test_blocks_files_not_in_spec`
- `test_warns_on_loc_limit_approach`
- `test_blocks_on_loc_limit_exceeded`

**pre_bash.py:**
- `test_blocks_push_to_main`
- `test_blocks_git_clean_fd`
- `test_blocks_git_reset_hard`
- `test_allows_git_clean_dry_run`
- `test_asks_confirmation_for_merge`
- `test_allows_merge_ff_only`

### pyproject.toml

```toml
[project]
name = "dld"
version = "3.4"
requires-python = ">=3.10"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
```

---

## Detailed Implementation Plan

### Task 1: Create pyproject.toml and conftest.py

**Files:**
- Create: `pyproject.toml`
- Create: `tests/conftest.py`

**Context:**
Set up pytest infrastructure with shared fixtures for mocking stdin, stdout, and sys.exit. All hooks read JSON from stdin and output JSON to stdout, so we need reusable fixtures.

**Step 1: Write failing test skeleton**

```python
# tests/conftest.py

"""Shared pytest fixtures for hook testing."""

import io
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add hooks directory to path for imports
HOOKS_DIR = Path(__file__).parent.parent / ".claude" / "hooks"


@pytest.fixture
def mock_stdin():
    """Create a mock stdin with JSON data.

    Usage:
        def test_something(mock_stdin):
            mock_stdin({"tool_input": {"command": "git push"}})
            # Now sys.stdin.read() returns the JSON
    """
    original_stdin = sys.stdin

    def _mock_stdin(data: dict) -> io.StringIO:
        json_str = json.dumps(data)
        mock = io.StringIO(json_str)
        sys.stdin = mock
        return mock

    yield _mock_stdin
    sys.stdin = original_stdin


@pytest.fixture
def capture_stdout():
    """Capture stdout output from hooks.

    Usage:
        def test_something(capture_stdout):
            with capture_stdout() as output:
                deny_tool("reason")
            assert "deny" in output.getvalue()
    """
    from contextlib import contextmanager

    @contextmanager
    def _capture():
        original = sys.stdout
        sys.stdout = io.StringIO()
        try:
            yield sys.stdout
        finally:
            sys.stdout = original

    return _capture


@pytest.fixture
def mock_exit():
    """Mock sys.exit to capture exit codes without exiting.

    Usage:
        def test_something(mock_exit):
            with mock_exit() as exit_mock:
                allow_tool()
            exit_mock.assert_called_once_with(0)
    """
    from contextlib import contextmanager

    @contextmanager
    def _mock():
        with patch("sys.exit") as mock:
            yield mock

    return _mock


@pytest.fixture
def temp_spec_file(tmp_path):
    """Create a temporary spec file with Allowed Files section.

    Usage:
        def test_something(temp_spec_file):
            spec_path = temp_spec_file('''
            ## Allowed Files
            | # | File | Action |
            |---|------|--------|
            | 1 | `src/main.py` | modify |
            ''')
    """
    def _create(content: str) -> Path:
        spec = tmp_path / "test-spec.md"
        spec.write_text(content)
        return spec

    return _create


@pytest.fixture
def temp_python_file(tmp_path):
    """Create a temporary Python file with specified content.

    Usage:
        def test_loc_limit(temp_python_file):
            file_path = temp_python_file("x = 1\\n" * 500)
            assert count_lines(str(file_path)) == 500
    """
    def _create(content: str, name: str = "test_file.py") -> Path:
        file = tmp_path / name
        file.write_text(content)
        return file

    return _create


@pytest.fixture
def hooks_path():
    """Return path to hooks directory."""
    return HOOKS_DIR
```

**Step 2: Create pyproject.toml**

```toml
# pyproject.toml

[project]
name = "dld"
version = "3.4"
requires-python = ">=3.10"
description = "Deep Learning Development Framework"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "ruff>=0.4",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]  # Line length handled by formatter

[tool.coverage.run]
source = [".claude/hooks"]
omit = ["tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.:",
    "pass  # nosec",
]
```

**Step 3: Verify setup**

```bash
cd /Users/desperado/dev/dld/.worktrees/TECH-059
pip install -e ".[dev]"
pytest --collect-only
```

Expected:
```
collected 0 items (no tests yet)
```

**Acceptance Criteria:**
- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `pytest --collect-only` runs without error
- [ ] conftest.py fixtures are importable

---

### Task 2: Test utils.py Core Functions

**Files:**
- Create: `tests/test_hooks_utils.py`

**Context:**
Test the core utility functions: `read_hook_input`, `get_tool_input`, `get_user_prompt`, and the output functions (`allow_tool`, `deny_tool`, `ask_tool`, etc.). These are the building blocks used by all hooks.

**Step 1: Write failing tests**

```python
# tests/test_hooks_utils.py

"""Tests for .claude/hooks/utils.py"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import after adding hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks"))
from utils import (
    allow_tool,
    ask_tool,
    deny_tool,
    approve_prompt,
    block_prompt,
    post_continue,
    post_block,
    get_tool_input,
    get_user_prompt,
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
```

**Step 2: Verify tests fail**

```bash
pytest tests/test_hooks_utils.py -v
```

Expected: All tests should fail initially (ModuleNotFoundError or similar).

**Step 3: No implementation needed - testing existing code**

The tests verify the existing `utils.py` implementation.

**Step 4: Verify tests pass**

```bash
pytest tests/test_hooks_utils.py -v
```

Expected:
```
PASSED test_reads_valid_json_from_stdin
PASSED test_returns_empty_dict_on_invalid_json
...
```

**Acceptance Criteria:**
- [ ] All 15 tests pass
- [ ] Core hook utilities verified
- [ ] Edge cases for empty/invalid input covered

---

### Task 3: Test utils.py File Allowlist Functions

**Files:**
- Modify: `tests/test_hooks_utils.py` (append)

**Context:**
Test the file allowlist functions: `extract_allowed_files`, `is_file_allowed`, and `infer_spec_from_branch`. These are critical for the pre_edit hook's security.

**Step 1: Write failing tests**

```python
# Append to tests/test_hooks_utils.py

from utils import (
    extract_allowed_files,
    is_file_allowed,
    infer_spec_from_branch,
    ALWAYS_ALLOWED_PATTERNS,
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

    def test_allows_all_when_no_allowed_files_section(self, temp_spec_file):
        """Should allow all when spec has no Allowed Files section."""
        spec_path = temp_spec_file("""
# Feature Spec

## Design

Just some design notes.
""")

        allowed, files = is_file_allowed("any/file.py", str(spec_path))

        assert allowed is True

    def test_matches_glob_patterns(self, temp_spec_file):
        """Should match glob patterns like *.py."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/*.py` | modify |
""")

        allowed, _ = is_file_allowed("src/main.py", str(spec_path))
        assert allowed is True

        allowed, _ = is_file_allowed("src/deep/nested.py", str(spec_path))
        # src/*.py should NOT match src/deep/nested.py (single *)
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
```

**Step 2: Verify tests fail then pass**

```bash
pytest tests/test_hooks_utils.py::TestExtractAllowedFiles -v
pytest tests/test_hooks_utils.py::TestIsFileAllowed -v
pytest tests/test_hooks_utils.py::TestInferSpecFromBranch -v
```

**Acceptance Criteria:**
- [ ] All 16 new tests pass
- [ ] File allowlist parsing verified
- [ ] Glob pattern matching verified
- [ ] Branch-to-spec inference verified

---

### Task 4: Test pre_edit.py

**Files:**
- Create: `tests/test_pre_edit.py`

**Context:**
Test the pre_edit hook's protection logic: protected paths, LOC limits, and Allowed Files integration. This hook is critical for preventing unauthorized file modifications.

**Step 1: Write failing tests**

```python
# tests/test_pre_edit.py

"""Tests for .claude/hooks/pre_edit.py"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks"))
from pre_edit import (
    count_lines,
    is_test_file,
    normalize_path,
    main,
    PROTECTED_PATHS,
    MAX_LOC_CODE,
    MAX_LOC_TEST,
    WARN_THRESHOLD,
)


class TestCountLines:
    """Tests for count_lines()."""

    def test_counts_lines_in_file(self, temp_python_file):
        """Should return correct line count."""
        content = "line1\nline2\nline3\n"
        file_path = temp_python_file(content)

        result = count_lines(str(file_path))

        assert result == 3

    def test_returns_zero_for_empty_file(self, temp_python_file):
        """Should return 0 for empty file."""
        file_path = temp_python_file("")

        result = count_lines(str(file_path))

        assert result == 0

    def test_returns_zero_for_nonexistent_file(self):
        """Should return 0 for nonexistent file."""
        result = count_lines("/nonexistent/file.py")

        assert result == 0


class TestIsTestFile:
    """Tests for is_test_file()."""

    def test_detects_test_suffix(self):
        """Should detect _test.py files."""
        assert is_test_file("src/main_test.py") is True
        assert is_test_file("test_main.py") is False  # Prefix not suffix

    def test_detects_tests_directory(self):
        """Should detect files in /tests/ directory."""
        assert is_test_file("tests/test_main.py") is True
        assert is_test_file("src/tests/helpers.py") is True

    def test_returns_false_for_regular_files(self):
        """Should return False for regular Python files."""
        assert is_test_file("src/main.py") is False
        assert is_test_file("src/utils.py") is False


class TestNormalizePath:
    """Tests for normalize_path()."""

    def test_converts_absolute_to_relative(self, monkeypatch):
        """Should strip project directory prefix."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/home/user/project")

        result = normalize_path("/home/user/project/src/main.py")

        assert result == "src/main.py"

    def test_keeps_relative_path_unchanged(self, monkeypatch):
        """Should not modify already relative paths."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/home/user/project")

        result = normalize_path("src/main.py")

        assert result == "src/main.py"

    def test_returns_empty_for_empty_input(self):
        """Should return empty string for empty input."""
        result = normalize_path("")

        assert result == ""


class TestProtectedPaths:
    """Tests for protected path blocking."""

    def test_blocks_contracts_directory(self, mock_stdin, capture_stdout, mock_exit):
        """Should block edits to tests/contracts/."""
        mock_stdin({
            "tool_input": {"file_path": "tests/contracts/api_test.py"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Protected test file" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_regression_directory(self, mock_stdin, capture_stdout, mock_exit):
        """Should block edits to tests/regression/."""
        mock_stdin({
            "tool_input": {"file_path": "tests/regression/bug_123.py"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestLocLimits:
    """Tests for LOC limit enforcement."""

    def test_asks_confirmation_when_exceeds_code_limit(
        self, mock_stdin, capture_stdout, mock_exit, temp_python_file, monkeypatch
    ):
        """Should ask confirmation when file exceeds 400 LOC."""
        # Create file with 450 lines
        content = "x = 1\n" * 450
        file_path = temp_python_file(content)

        mock_stdin({
            "tool_input": {"file_path": str(file_path)}
        })
        # Clear spec path env
        monkeypatch.delenv("CLAUDE_CURRENT_SPEC_PATH", raising=False)

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "exceeds LOC limit" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "450 lines" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_asks_confirmation_when_approaching_limit(
        self, mock_stdin, capture_stdout, mock_exit, temp_python_file, monkeypatch
    ):
        """Should ask confirmation when file is near limit (87.5%)."""
        # Create file with 360 lines (above 350 warn threshold)
        content = "x = 1\n" * 360
        file_path = temp_python_file(content)

        mock_stdin({
            "tool_input": {"file_path": str(file_path)}
        })
        monkeypatch.delenv("CLAUDE_CURRENT_SPEC_PATH", raising=False)

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "approaching LOC limit" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_file_under_limit(
        self, mock_stdin, mock_exit, temp_python_file, monkeypatch
    ):
        """Should allow files under the limit."""
        content = "x = 1\n" * 100
        file_path = temp_python_file(content)

        mock_stdin({
            "tool_input": {"file_path": str(file_path)}
        })
        monkeypatch.delenv("CLAUDE_CURRENT_SPEC_PATH", raising=False)

        with mock_exit() as exit_mock:
            main()

        # Should exit with 0 (allow)
        exit_mock.assert_called_with(0)

    def test_uses_higher_limit_for_test_files(
        self, mock_stdin, mock_exit, temp_python_file, monkeypatch
    ):
        """Should use 600 LOC limit for test files."""
        # 450 lines - over code limit but under test limit
        content = "x = 1\n" * 450
        file_path = temp_python_file(content, name="main_test.py")

        mock_stdin({
            "tool_input": {"file_path": str(file_path)}
        })
        monkeypatch.delenv("CLAUDE_CURRENT_SPEC_PATH", raising=False)

        with mock_exit() as exit_mock:
            main()

        # Should allow (under 600 limit for tests)
        exit_mock.assert_called_with(0)


class TestAllowedFilesIntegration:
    """Tests for Allowed Files enforcement in pre_edit."""

    def test_blocks_file_not_in_spec(
        self, mock_stdin, capture_stdout, mock_exit, temp_spec_file, monkeypatch
    ):
        """Should block files not in spec's Allowed Files."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
""")
        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        mock_stdin({
            "tool_input": {"file_path": "src/secret.py"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "not in Allowed Files" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_file_in_spec(
        self, mock_stdin, mock_exit, temp_spec_file, temp_python_file, monkeypatch
    ):
        """Should allow files listed in spec."""
        spec_path = temp_spec_file("""
## Allowed Files

| # | File | Action |
|---|------|--------|
| 1 | `src/main.py` | modify |
""")
        # Create the actual file so LOC check works
        file_path = temp_python_file("x = 1\n" * 10, name="main.py")

        monkeypatch.setenv("CLAUDE_CURRENT_SPEC_PATH", str(spec_path))

        # Mock the path to match spec
        mock_stdin({
            "tool_input": {"file_path": "src/main.py"}
        })

        with mock_exit() as exit_mock:
            main()

        # File is in spec, should be allowed (exits 0)
        exit_mock.assert_called_with(0)
```

**Step 2: Verify tests fail then pass**

```bash
pytest tests/test_pre_edit.py -v
```

**Acceptance Criteria:**
- [ ] All 14 tests pass
- [ ] Protected path blocking verified
- [ ] LOC limit warnings verified
- [ ] Allowed Files integration verified

---

### Task 5: Test pre_bash.py

**Files:**
- Create: `tests/test_pre_bash.py`

**Context:**
Test the pre_bash hook's command blocking: push to main, destructive git operations, force push protection, and merge workflow enforcement.

**Step 1: Write failing tests**

```python
# tests/test_pre_bash.py

"""Tests for .claude/hooks/pre_bash.py"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks"))
from pre_bash import main, BLOCKED_PATTERNS, MERGE_PATTERNS


class TestBlockedPatterns:
    """Tests for hard-blocked command patterns."""

    def test_blocks_push_to_main(self, mock_stdin, capture_stdout, mock_exit):
        """Should block git push to main branch."""
        mock_stdin({
            "tool_input": {"command": "git push origin main"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Push to main blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_push_main_different_format(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git push main' without origin."""
        mock_stdin({
            "tool_input": {"command": "git push main"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_blocks_git_clean_fd(self, mock_stdin, capture_stdout, mock_exit):
        """Should block git clean -fd."""
        mock_stdin({
            "tool_input": {"command": "git clean -fd"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "git clean -fd blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_git_clean_df(self, mock_stdin, capture_stdout, mock_exit):
        """Should block git clean -df (reversed flags)."""
        mock_stdin({
            "tool_input": {"command": "git clean -df"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_allows_git_clean_dry_run(self, mock_stdin, mock_exit):
        """Should allow git clean -fdn (dry-run)."""
        mock_stdin({
            "tool_input": {"command": "git clean -fdn"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_allows_git_clean_dfn(self, mock_stdin, mock_exit):
        """Should allow git clean -dfn (dry-run variant)."""
        mock_stdin({
            "tool_input": {"command": "git clean -dfn"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_blocks_git_reset_hard(self, mock_stdin, capture_stdout, mock_exit):
        """Should block git reset --hard."""
        mock_stdin({
            "tool_input": {"command": "git reset --hard HEAD~1"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "git reset --hard blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_force_push_to_develop(self, mock_stdin, capture_stdout, mock_exit):
        """Should block force push to develop branch."""
        mock_stdin({
            "tool_input": {"command": "git push -f origin develop"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Force push to protected branch blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_force_push_to_main(self, mock_stdin, capture_stdout, mock_exit):
        """Should block force push to main branch."""
        mock_stdin({
            "tool_input": {"command": "git push --force origin main"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_allows_force_push_to_feature_branch(self, mock_stdin, mock_exit):
        """Should allow force push to feature branches."""
        mock_stdin({
            "tool_input": {"command": "git push -f origin feature/FTR-100"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)


class TestMergePatterns:
    """Tests for merge workflow enforcement."""

    def test_asks_confirmation_for_merge_without_ff_only(
        self, mock_stdin, capture_stdout, mock_exit
    ):
        """Should ask confirmation for merge without --ff-only."""
        mock_stdin({
            "tool_input": {"command": "git merge feature/FTR-100"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "--ff-only" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_merge_with_ff_only(self, mock_stdin, mock_exit):
        """Should allow merge with --ff-only flag."""
        mock_stdin({
            "tool_input": {"command": "git merge --ff-only feature/FTR-100"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)


class TestAllowedCommands:
    """Tests for commands that should be allowed."""

    def test_allows_git_status(self, mock_stdin, mock_exit):
        """Should allow git status."""
        mock_stdin({
            "tool_input": {"command": "git status"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_allows_git_diff(self, mock_stdin, mock_exit):
        """Should allow git diff."""
        mock_stdin({
            "tool_input": {"command": "git diff HEAD"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_allows_git_push_to_develop(self, mock_stdin, mock_exit):
        """Should allow regular push to develop (not force)."""
        mock_stdin({
            "tool_input": {"command": "git push origin develop"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_allows_git_checkout(self, mock_stdin, mock_exit):
        """Should allow git checkout."""
        mock_stdin({
            "tool_input": {"command": "git checkout -- ."}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_allows_non_git_commands(self, mock_stdin, mock_exit):
        """Should allow non-git commands."""
        mock_stdin({
            "tool_input": {"command": "ls -la"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_allows_pytest(self, mock_stdin, mock_exit):
        """Should allow pytest commands."""
        mock_stdin({
            "tool_input": {"command": "pytest tests/ -v"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_command(self, mock_stdin, mock_exit):
        """Should handle empty command gracefully."""
        mock_stdin({
            "tool_input": {"command": ""}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_handles_missing_command(self, mock_stdin, mock_exit):
        """Should handle missing command key."""
        mock_stdin({
            "tool_input": {}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_case_insensitive_matching(self, mock_stdin, capture_stdout, mock_exit):
        """Should match patterns case-insensitively."""
        mock_stdin({
            "tool_input": {"command": "GIT PUSH ORIGIN MAIN"}
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
```

**Step 2: Verify tests fail then pass**

```bash
pytest tests/test_pre_bash.py -v
```

**Acceptance Criteria:**
- [ ] All 20 tests pass
- [ ] All blocked patterns verified
- [ ] Merge workflow enforcement verified
- [ ] Allowed commands pass through

---

### Task 6: Test post_edit.py and prompt_guard.py

**Files:**
- Create: `tests/test_post_edit.py`
- Create: `tests/test_prompt_guard.py`

**Context:**
Test post_edit hook (auto-formatting) and prompt_guard hook (spark suggestions). These are lower priority but needed for complete coverage.

**Step 1: Write failing tests for post_edit.py**

```python
# tests/test_post_edit.py

"""Tests for .claude/hooks/post_edit.py"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks"))
from post_edit import (
    format_python_file,
    check_lint_warnings,
    main,
)


class TestFormatPythonFile:
    """Tests for format_python_file()."""

    def test_returns_success_when_ruff_formats(self, monkeypatch):
        """Should return (True, 'formatted') on success."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        success, msg = format_python_file("/path/to/file.py")

        assert success is True
        assert msg == "formatted"

    def test_returns_failure_on_ruff_error(self, monkeypatch):
        """Should return (False, stderr) on error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "syntax error"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        success, msg = format_python_file("/path/to/file.py")

        assert success is False
        assert "syntax error" in msg

    def test_handles_ruff_not_found(self, monkeypatch):
        """Should return (False, 'ruff not found') when ruff missing."""
        def raise_fnf(*a, **kw):
            raise FileNotFoundError("ruff")
        monkeypatch.setattr("subprocess.run", raise_fnf)

        success, msg = format_python_file("/path/to/file.py")

        assert success is False
        assert "ruff not found" in msg


class TestCheckLintWarnings:
    """Tests for check_lint_warnings()."""

    def test_returns_warnings_list(self, monkeypatch):
        """Should return list of warning strings."""
        mock_result = MagicMock()
        mock_result.stdout = "file.py:1:1: E501 line too long\nfile.py:2:1: W291 trailing whitespace"
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        warnings = check_lint_warnings("/path/to/file.py")

        assert len(warnings) == 2
        assert "E501" in warnings[0]

    def test_returns_empty_list_on_no_warnings(self, monkeypatch):
        """Should return [] when no warnings."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        warnings = check_lint_warnings("/path/to/file.py")

        assert warnings == []

    def test_limits_to_five_warnings(self, monkeypatch):
        """Should return max 5 warnings."""
        mock_result = MagicMock()
        mock_result.stdout = "\n".join([f"warning {i}" for i in range(10)])
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        warnings = check_lint_warnings("/path/to/file.py")

        assert len(warnings) == 5


class TestPostEditMain:
    """Tests for main() orchestration."""

    def test_skips_non_write_tools(self, mock_stdin, mock_exit):
        """Should continue without action for non-write tools."""
        mock_stdin({
            "tool_name": "Read",
            "tool_input": {"file_path": "test.py"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_skips_non_python_files(self, mock_stdin, mock_exit):
        """Should continue without action for non-.py files."""
        mock_stdin({
            "tool_name": "Edit",
            "tool_input": {"file_path": "README.md"}
        })

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_with(0)

    def test_processes_python_file_edit(
        self, mock_stdin, capture_stdout, mock_exit, temp_python_file, monkeypatch
    ):
        """Should format Python files on Edit."""
        file_path = temp_python_file("x=1\n")

        mock_stdin({
            "tool_name": "Edit",
            "tool_input": {"file_path": str(file_path)}
        })

        # Mock ruff to succeed
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: mock_result)

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert "ruff format" in result["hookSpecificOutput"]["additionalContext"]
```

**Step 2: Write failing tests for prompt_guard.py**

```python
# tests/test_prompt_guard.py

"""Tests for .claude/hooks/prompt_guard.py"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks"))
from prompt_guard import main, COMPLEXITY_PATTERNS, SKILL_INDICATORS


class TestComplexityDetection:
    """Tests for detecting complex task prompts."""

    def test_detects_implement_feature(self, mock_stdin, capture_stdout, mock_exit):
        """Should detect 'implement feature' as complex."""
        mock_stdin({
            "user_prompt": "implement a new feature for user authentication"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "Complex task detected" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_detects_create_endpoint(self, mock_stdin, capture_stdout, mock_exit):
        """Should detect 'create endpoint' as complex."""
        mock_stdin({
            "user_prompt": "create a new endpoint for user registration"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_detects_write_function(self, mock_stdin, capture_stdout, mock_exit):
        """Should detect 'write a function' as complex."""
        mock_stdin({
            "user_prompt": "write a function to calculate discounts"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_detects_add_api(self, mock_stdin, capture_stdout, mock_exit):
        """Should detect 'add an api' as complex."""
        mock_stdin({
            "user_prompt": "add an api for payment processing"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"


class TestSkillIndicators:
    """Tests for skipping when skills are already used."""

    def test_skips_when_spark_mentioned(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve when /spark is in prompt."""
        mock_stdin({
            "user_prompt": "/spark implement a new feature"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"

    def test_skips_when_autopilot_mentioned(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve when /autopilot is in prompt."""
        mock_stdin({
            "user_prompt": "/autopilot create new endpoint"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"

    def test_skips_when_audit_mentioned(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve when /audit is in prompt."""
        mock_stdin({
            "user_prompt": "/audit the billing service"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"


class TestSimplePrompts:
    """Tests for simple prompts that should be approved."""

    def test_approves_simple_question(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve simple questions."""
        mock_stdin({
            "user_prompt": "what does this function do?"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"

    def test_approves_fix_request(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve fix requests (not complex creation)."""
        mock_stdin({
            "user_prompt": "fix the bug in utils.py"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"

    def test_approves_read_request(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve read/analysis requests."""
        mock_stdin({
            "user_prompt": "read main.py and explain the architecture"
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"


class TestEdgeCases:
    """Tests for edge cases."""

    def test_handles_empty_prompt(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve empty prompt."""
        mock_stdin({
            "user_prompt": ""
        })

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"

    def test_handles_missing_prompt(self, mock_stdin, capture_stdout, mock_exit):
        """Should approve when user_prompt key is missing."""
        mock_stdin({})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["decision"] == "approve"
```

**Step 3: Verify tests pass**

```bash
pytest tests/test_post_edit.py tests/test_prompt_guard.py -v
```

**Acceptance Criteria:**
- [ ] All 18 tests pass
- [ ] post_edit formatting logic verified
- [ ] prompt_guard detection patterns verified
- [ ] Skill indicator bypass verified

---

### Task 7: Add CI Integration

**Files:**
- Modify: `.github/workflows/ci.yml`

**Context:**
Add pytest job to CI workflow with coverage reporting. Tests should run on push and PR.

**Step 1: Add pytest job to ci.yml**

After the `python-lint:` job (line 53), add:

```yaml
  python-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install pytest pytest-cov ruff
      - name: Run tests with coverage
        run: |
          pytest tests/ -v --cov=.claude/hooks --cov-report=term-missing --cov-fail-under=80
```

**Step 2: Verify CI workflow syntax**

```bash
yamllint .github/workflows/ci.yml
```

**Step 3: Test locally**

```bash
pytest tests/ -v --cov=.claude/hooks --cov-report=term-missing
```

Expected:
```
Name                            Stmts   Miss  Cover
---------------------------------------------------
.claude/hooks/post_edit.py        XX     X    XX%
.claude/hooks/pre_bash.py         XX     X    XX%
.claude/hooks/pre_edit.py         XX     X    XX%
.claude/hooks/prompt_guard.py     XX     X    XX%
.claude/hooks/utils.py            XX     X    XX%
---------------------------------------------------
TOTAL                            XXX    XX    >80%
```

**Acceptance Criteria:**
- [ ] CI workflow passes yamllint
- [ ] pytest job runs tests
- [ ] Coverage threshold enforced (80%)
- [ ] Tests pass in CI

---

### Execution Order

```
Task 1 (pyproject + conftest)
    |
    v
Task 2 (utils core) ---> Task 3 (utils files) ---> Task 4 (pre_edit)
                                                        |
                                                        v
                                              Task 5 (pre_bash) ---> Task 6 (post_edit + prompt_guard)
                                                                            |
                                                                            v
                                                                      Task 7 (CI)
```

### Dependencies

- Task 2 depends on Task 1 (needs conftest fixtures)
- Task 3 depends on Task 2 (imports same module)
- Task 4 depends on Task 1 (needs fixtures)
- Task 5 depends on Task 1 (needs fixtures)
- Task 6 depends on Task 1 (needs fixtures)
- Task 7 depends on Tasks 2-6 (needs all tests to exist)

### Research Sources

- [pytest fixtures documentation](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) - monkeypatch for mocking stdin/subprocess
- [pytest capsys fixture](https://docs.pytest.org/en/stable/reference/reference.html#capsys) - capturing stdout

---

## Definition of Done

### Functional
- [ ] All hook functions have tests
- [ ] Tests pass locally
- [ ] Tests pass in CI

### Technical
- [ ] Coverage > 80%
- [ ] No flaky tests
- [ ] Fast execution (<10s)

### Documentation
- [ ] README mentions how to run tests

---

## Autopilot Log

*(Filled by Autopilot during execution)*
