"""
Tests for Layer D fix: env=env propagation in checkout-index calls.

Regression suite for TECH-194 — verifies that after any lifecycle write
the working tree is synced to HEAD (no WT drift).

All tests use real git repos via tmp_path (ADR-013 — no mocks).
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Make scripts/vps importable
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Minimal git repo with one initial commit and ai/lifecycle/ dir."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")

    # Create ai/lifecycle/ with a .gitkeep so HEAD exists
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "init")

    return repo


def _git_show(repo: Path, path: str) -> str:
    """Read a file's content from HEAD (git object store)."""
    r = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout


def _git_status_lifecycle(repo: Path) -> str:
    """Return porcelain status of ai/lifecycle/ (empty string = clean)."""
    r = subprocess.run(
        ["git", "status", "--porcelain", "ai/lifecycle/"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# Test 1: write_lifecycle syncs WT to HEAD
# ---------------------------------------------------------------------------


def test_wt_synced_after_write_lifecycle(tmp_git_repo):
    """After write_lifecycle the WT file content must equal HEAD blob.

    Regression for Layer D bug: checkout-index without env=env used the
    default .git/index (which didn't contain the new blob) → WT stayed stale.
    """
    repo = tmp_git_repo

    # Bootstrap initial state
    lifecycle.create_initial(repo, "TEST-1", priority="p1", kind="tech")

    # Update status via write_lifecycle
    lifecycle.write_lifecycle(repo, "TEST-1", status="blocked", by="callback")

    yaml_path = "ai/lifecycle/TEST-1.yaml"
    wt_file = repo / yaml_path

    # WT file must exist after the write
    assert wt_file.exists(), f"WT file missing: {wt_file}"

    # WT content must match HEAD blob
    head_content = _git_show(repo, yaml_path)
    wt_content = wt_file.read_text(encoding="utf-8")
    assert wt_content == head_content, (
        f"WT content diverged from HEAD:\n"
        f"HEAD:\n{head_content}\n"
        f"WT:\n{wt_content}"
    )

    # git status must show clean lifecycle dir
    status = _git_status_lifecycle(repo)
    assert status == "", f"Dirty lifecycle after write_lifecycle: {status!r}"


# ---------------------------------------------------------------------------
# Test 2: create_initial creates file in WT (CRITICAL — catches the D bug)
# ---------------------------------------------------------------------------


def test_wt_created_after_create_initial(tmp_git_repo):
    """After create_initial the yaml must exist in WT, not only in HEAD.

    Regression for Layer D bug: checkout-index without env=env failed silently
    (the file wasn't in default .git/index) → WT showed ' D' (deleted) for
    the newly created spec. This caused TECH-446 and TECH-447 in prod.
    """
    repo = tmp_git_repo

    lifecycle.create_initial(repo, "TEST-2", priority="p1", kind="tech")

    yaml_path = "ai/lifecycle/TEST-2.yaml"
    wt_file = repo / yaml_path

    # CRITICAL: file must exist in WT (not just in HEAD)
    assert wt_file.exists(), (
        f"WT file does not exist after create_initial: {wt_file}\n"
        f"HEAD has it: {_git_show(repo, yaml_path)[:100]!r}"
    )

    # WT content must match HEAD blob
    head_content = _git_show(repo, yaml_path)
    wt_content = wt_file.read_text(encoding="utf-8")
    assert wt_content == head_content, (
        f"WT content diverged from HEAD after create_initial:\n"
        f"HEAD:\n{head_content}\n"
        f"WT:\n{wt_content}"
    )

    # git status must show clean lifecycle dir
    status = _git_status_lifecycle(repo)
    assert status == "", (
        f"Dirty lifecycle after create_initial: {status!r}\n"
        f"(expected empty — no ' D' entries)"
    )


# ---------------------------------------------------------------------------
# Test 3: write_file_atomic syncs WT to HEAD
# ---------------------------------------------------------------------------


def test_wt_synced_after_write_file_atomic(tmp_git_repo):
    """After write_file_atomic the WT file content must equal HEAD blob.

    Regression for Layer D bug in _atomic_write_file: checkout-index
    without env=env used the default .git/index → WT not updated.
    """
    repo = tmp_git_repo

    rel_path = "ai/backlog.md"
    content = "# Backlog\n\ntest content for WT sync\n"

    result = lifecycle.write_file_atomic(
        repo, rel_path, content, "chore: test backlog write"
    )
    assert result is True, "write_file_atomic returned False — write failed"

    wt_file = repo / rel_path

    # WT file must exist
    assert wt_file.exists(), f"WT file missing after write_file_atomic: {wt_file}"

    # WT content must match HEAD blob
    head_content = _git_show(repo, rel_path)
    wt_content = wt_file.read_text(encoding="utf-8")
    assert wt_content == head_content, (
        f"WT content diverged from HEAD after write_file_atomic:\n"
        f"HEAD:\n{head_content}\n"
        f"WT:\n{wt_content}"
    )

    # git status for the file must be clean
    r = subprocess.run(
        ["git", "status", "--porcelain", rel_path],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    assert r.stdout.strip() == "", (
        f"Dirty WT after write_file_atomic: {r.stdout.strip()!r}"
    )
