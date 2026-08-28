"""BUG-1039 regression — unit tests for gate_logic.find_implementation_commit.

Replaces the old TECH-170 tests (_has_implementation_commits / is_merged_to_develop)
which tested a deleted implementation. TECH-210: retargeted from
callback._is_done_on_develop (bool) to gate_logic.find_implementation_commit
(str | None, the single source callback.py now calls) — sha-truthy/None replaces
is True/is False.

EC-1: commit on origin/develop with spec_id in subject + allowed file → sha
EC-2: commit only on feature branch (not on origin/develop) → None  ← BUG-1039 regression
EC-3: spec_id in subject but file NOT in allowed list → None
EC-4: wrong spec_id in subject, allowed file matches → None
EC-5: no origin/develop (branch never pushed) → graceful None
EC-6: empty allowed list → None
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import gate_logic  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _commit_on(repo: Path, rel: str, body: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


@pytest.fixture
def repo_with_remote(tmp_path):
    """Local repo with bare remote (origin/develop tracking ref set via push)."""
    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(
        ["git", "init", "--bare", "-q", "-b", "develop", str(bare)], check=True, capture_output=True
    )

    local = tmp_path / "local"
    local.mkdir()
    _git(local, "init", "-q", "-b", "develop")
    _git(local, "config", "user.email", "t@t")
    _git(local, "config", "user.name", "t")
    _git(local, "remote", "add", "origin", str(bare))

    (local / "README.md").write_text("init\n")
    _git(local, "add", "README.md")
    _git(local, "commit", "-q", "-m", "init")
    _git(local, "push", "-q", "-u", "origin", "develop")

    return local


# --- EC-1: commit on origin/develop → True ----------------------------------


def test_ec1_commit_on_origin_develop_true(repo_with_remote):
    """Commit on origin/develop with spec_id in subject + allowed file → sha."""
    _commit_on(repo_with_remote, "src/x.py", "y=1\n", "feat(TECH-170): real work")
    _git(repo_with_remote, "push", "-q", "origin", "develop")
    _git(repo_with_remote, "fetch", "-q", "origin", "develop")

    assert (
        gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", ["src/x.py"])
        is not None
    )


# --- EC-2: feature-branch commit NOT on origin/develop → False (BUG-1039) ---


def test_ec2_feature_branch_only_is_false(repo_with_remote):
    """BUG-1039 regression: commit on feature branch but NOT on origin/develop → None.

    Old --all flag saw this commit and returned True (false-done).
    New gate reads only origin/develop → None.
    """
    _git(repo_with_remote, "checkout", "-q", "-b", "feature/TECH-170")
    _commit_on(repo_with_remote, "src/x.py", "y=1\n", "feat(TECH-170): work on feature")
    # NOT pushing to origin/develop — stays on feature branch only

    # Ensure origin/develop is at the initial commit (no TECH-170 work)
    _git(repo_with_remote, "checkout", "-q", "develop")

    assert gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", ["src/x.py"]) is None


# --- EC-3: spec_id in subject but file not in allowed list → False -----------


def test_ec3_allowed_file_filter(repo_with_remote):
    """Subject matches but touched file is NOT in allowed list → None."""
    _commit_on(repo_with_remote, "docs/note.md", "n\n", "feat(TECH-170): touch only docs")
    _git(repo_with_remote, "push", "-q", "origin", "develop")
    _git(repo_with_remote, "fetch", "-q", "origin", "develop")

    assert gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", ["src/x.py"]) is None


# --- EC-4: wrong spec_id in commit subject → False --------------------------


def test_ec4_wrong_spec_id(repo_with_remote):
    """Subject mentions a different spec_id → None."""
    _commit_on(repo_with_remote, "src/x.py", "y=1\n", "feat(TECH-999): unrelated work")
    _git(repo_with_remote, "push", "-q", "origin", "develop")
    _git(repo_with_remote, "fetch", "-q", "origin", "develop")

    assert gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", ["src/x.py"]) is None


# --- EC-5: no origin/develop → graceful False --------------------------------


def test_ec5_no_origin_develop_graceful(tmp_path):
    """Repo without origin → git log origin/develop fails → graceful None, no exception."""
    repo = tmp_path / "norepo"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "develop"], check=True, capture_output=True
    )
    # No remote set → origin/develop doesn't exist
    assert gate_logic.find_implementation_commit(str(repo), "TECH-170", ["src/x.py"]) is None


# --- EC-6: empty allowed list → False ----------------------------------------


def test_ec6_empty_allowed_list(repo_with_remote):
    """Empty allowed list → None (no files to match against)."""
    _commit_on(repo_with_remote, "src/x.py", "y=1\n", "feat(TECH-170): work")
    _git(repo_with_remote, "push", "-q", "origin", "develop")
    _git(repo_with_remote, "fetch", "-q", "origin", "develop")

    assert gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", []) is None
