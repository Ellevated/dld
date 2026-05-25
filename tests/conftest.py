"""Shared pytest fixtures for hook testing."""

import io
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for imports
HOOKS_DIR = Path(__file__).parent.parent / "template" / ".claude" / "hooks"


@pytest.fixture(autouse=True)
def _db_isolation(tmp_path, monkeypatch):
    """TECH-189 Task 2: Auto-isolate every test from the production DB.

    Overrides DB_PATH env var + db.DB_PATH attribute via monkeypatch so
    no test can accidentally write to a real DB file, even if the test
    doesn't explicitly request `isolated_db`. Tests in scripts/vps/tests/
    inherit this via the pytest conftest discovery chain.

    Gracefully skips when `db` module is not importable (hooks-only test
    runs where scripts/vps is not on sys.path).
    """
    db_path = tmp_path / "test_isolated.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    try:
        import db as db_mod  # noqa: PLC0415 — only available when scripts/vps in path
    except ImportError:
        return
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_path))


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
