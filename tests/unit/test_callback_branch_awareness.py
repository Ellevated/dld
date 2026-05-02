"""TECH-170 — unit tests for callback feature-branch awareness.

EC-1: --all flag sees commits on feature/<spec> when develop is empty.
EC-3: empty repo / no relevant commits → guard False.
EC-5: branches='current' reproduces pre-TECH-170 command shape.
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


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _commit(repo: Path, rel: str, body: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@pytest.fixture
def feature_repo(tmp_path):
    """Repo on develop with empty develop and a commit on feature/TECH-170."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _commit(repo, "README.md", "init\n", "chore: init")
    _git(repo, "checkout", "-q", "-b", "feature/TECH-170")
    return repo


# --- EC-1: feature-branch commit visible via --all -------------------------


def test_ec1_all_sees_feature_branch_commit(feature_repo):
    """Commit lands on feature/TECH-170; develop is unchanged.
    Default branches='all' → guard returns True."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(feature_repo, "src/x.py", "y=1\n", "feat: TECH-170 work")
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at
    ) is True


def test_ec1_current_misses_feature_branch_commit_from_develop(feature_repo):
    """Same commit, but branches='current' while we're checked out on develop.
    Reproduces pre-TECH-170 false-negative."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(feature_repo, "src/x.py", "y=1\n", "feat: TECH-170 work")
    _git(feature_repo, "checkout", "-q", "develop")
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at, branches="current"
    ) is False
    # Sanity: --all still finds it from develop checkout.
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at, branches="all"
    ) is True


# --- EC-3: no commits anywhere ---------------------------------------------


def test_ec3_no_commits_anywhere_returns_false(feature_repo):
    """No commits in window on any branch → False (degrade closed for content)."""
    time.sleep(1.1)
    started_at = _now_iso()
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at
    ) is False


# --- EC-5: regression — branches='current' is the pre-TECH-170 command -----


def test_ec5_current_branch_matches_legacy_behavior(feature_repo, monkeypatch):
    """Capture the exact subprocess.run argv to verify backwards compat."""
    captured: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *a, **kw):
        if isinstance(cmd, list) and len(cmd) >= 4 and cmd[:3] == ["git", "-C", str(feature_repo)] and cmd[3] == "log":
            captured.append(list(cmd))
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", spy)
    callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], _now_iso(), branches="current"
    )
    assert captured, "git log was not invoked"
    argv = captured[0]
    # No --all and no explicit ref between 'log' and '--since'
    assert "--all" not in argv
    assert not any(a == "develop" for a in argv[4:5])  # 4th token after 'log' is not 'develop'


# --- is_merged_to_develop --------------------------------------------------


def test_is_merged_to_develop_finds_commit_on_develop(feature_repo):
    _git(feature_repo, "checkout", "-q", "develop")
    _commit(feature_repo, "src/y.py", "z=1\n", "feat: TECH-170 merge")
    assert callback.is_merged_to_develop(str(feature_repo), "TECH-170") is True


def test_is_merged_to_develop_false_when_only_on_feature(feature_repo):
    # Commit lands on feature/TECH-170 only.
    _commit(feature_repo, "src/x.py", "y=1\n", "feat: TECH-170 work")
    assert callback.is_merged_to_develop(str(feature_repo), "TECH-170") is False


def test_is_merged_to_develop_handles_missing_branch(tmp_path):
    """Repo without develop branch → graceful False, no exception."""
    repo = tmp_path / "norepo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"],
                   check=True, capture_output=True)
    assert callback.is_merged_to_develop(str(repo), "TECH-170") is False
