"""TECH-166 — unit tests for callback.py implementation guard.

Covers EC-1..EC-7: parser variants, guard window/allowed-list semantics,
degrade-open behavior, and reason annotation idempotency.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


# --- _parse_allowed_files ----------------------------------------------------


def _spec(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "TECH-XXX.md"
    p.write_text(body)
    return p


def test_ec1_parser_typical_spec(tmp_path):
    """EC-1: standard ## Allowed Files with backticked paths → list of paths."""
    spec = _spec(tmp_path, """\
# TECH-XXX

## Allowed Files

1. `scripts/vps/callback.py` — modify
2. `tests/unit/test_x.py` — NEW
3. `ai/glossary/x.md` — touch
4. `db/schema.sql` — extend
5. `pueue.yml` — config

## Tests
""")
    out = callback._parse_allowed_files(spec)
    assert out == [
        "scripts/vps/callback.py",
        "tests/unit/test_x.py",
        "ai/glossary/x.md",
        "db/schema.sql",
        "pueue.yml",
    ]


def test_ec2_parser_no_allowed_files_section(tmp_path):
    """EC-2: legacy spec without section → None (degrade open sentinel)."""
    spec = _spec(tmp_path, "# Spec\n\n## Tests\n\n- foo\n")
    assert callback._parse_allowed_files(spec) is None


def test_ec3_parser_section_present_but_empty(tmp_path):
    """EC-3: section exists, no backticked paths → [] (explicit empty)."""
    spec = _spec(tmp_path, "# Spec\n\n## Allowed Files\n\nnone\n\n## Tests\n")
    assert callback._parse_allowed_files(spec) == []


# --- _has_implementation_commits ---------------------------------------------


@pytest.fixture
def git_repo(tmp_path):
    """Initialize a tmp git repo with one baseline commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (repo / "README.md").write_text("init\n")
    run("add", "README.md")
    run("commit", "-q", "-m", "init")
    return repo


def _commit(repo: Path, rel: str, content: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", msg],
        check=True, capture_output=True,
    )


def _now_iso() -> str:
    # Match git log --since acceptance and task_log default format.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def test_ec4_guard_commit_on_allowed_file(git_repo):
    """EC-4: commit touching allowed file after started_at → True."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(git_repo, "src/foo.py", "x=1\n", "feat: foo")
    assert callback._has_implementation_commits(
        str(git_repo), ["src/foo.py"], started_at
    ) is True


def test_ec5_guard_only_doc_commits(git_repo):
    """EC-5: commit only on non-allowed path → False (demote)."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(git_repo, "docs/x.md", "doc\n", "docs: x")
    assert callback._has_implementation_commits(
        str(git_repo), ["src/foo.py"], started_at
    ) is False


def test_ec6_guard_commit_before_started_at(git_repo):
    """EC-6: commit predates started_at → window excludes it → False."""
    _commit(git_repo, "src/foo.py", "x=1\n", "feat: foo (early)")
    time.sleep(1.1)
    started_at = _now_iso()
    assert callback._has_implementation_commits(
        str(git_repo), ["src/foo.py"], started_at
    ) is False


def test_ec7_guard_no_started_at_or_allowed(git_repo):
    """EC-7: missing started_at OR allowed=None → True (degrade open)."""
    assert callback._has_implementation_commits(
        str(git_repo), ["src/foo.py"], None
    ) is True
    assert callback._has_implementation_commits(
        str(git_repo), None, _now_iso()
    ) is True


def test_guard_explicit_empty_allowlist_blocks(git_repo):
    """EC-3 follow-through: empty allowed list → False (explicit no-impl)."""
    assert callback._has_implementation_commits(
        str(git_repo), [], _now_iso()
    ) is False


# --- _append_blocked_reason --------------------------------------------------


def test_append_blocked_reason_inserts_after_status(tmp_path):
    spec = _spec(tmp_path, "# T\n\n**Status:** blocked\n**Priority:** P1\n")
    callback._append_blocked_reason(spec, "no_implementation_commits")
    text = spec.read_text()
    assert "**Blocked Reason:** no_implementation_commits" in text
    # Inserted right after Status line.
    lines = text.splitlines()
    status_idx = next(i for i, l in enumerate(lines) if l.startswith("**Status:"))
    assert lines[status_idx + 1] == "**Blocked Reason:** no_implementation_commits"


def test_append_blocked_reason_idempotent(tmp_path):
    spec = _spec(tmp_path, "# T\n\n**Status:** blocked\n**Blocked Reason:** old_reason\n")
    callback._append_blocked_reason(spec, "no_implementation_commits")
    text = spec.read_text()
    assert text.count("**Blocked Reason:**") == 1
    assert "no_implementation_commits" in text
    assert "old_reason" not in text
