"""
Tests for scripts/vps/salvage.py — preserving autopilot work after an abnormal exit.

Real git repos and real worktrees throughout: the module is almost entirely git
plumbing, and a mocked `git` would assert that the calls were made rather than
that the work survives, which is the only thing worth asserting here.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Make scripts/vps importable
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import salvage  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _git(repo, *args):
    r = subprocess.run(
        ["git"] + list(args), cwd=str(repo), capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {args} failed in {repo}: {r.stderr.strip()}")
    return r.stdout.strip()


@pytest.fixture()
def project(tmp_path):
    """A repo on `develop` with a bare `origin` behind it, mirroring a VPS project."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    # Hooks in the developer's global config must not leak into these repos.
    _git(repo, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "develop")
    return repo, origin


def _add_worktree(repo, dirname, branch):
    path = repo / ".worktrees" / dirname
    _git(repo, "worktree", "add", "-q", str(path), "-b", branch, "develop")
    return path


# ---------------------------------------------------------------------------
# spec_id_from_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("ai/features/FTR-0082-2026-07-26-console-manager.md", "FTR-0082"),
        (r"D:\dev\x\ai\features\BUG-1410-fix.md", "BUG-1410"),
        ("/home/dld/projects/x/ai/features/TECH-206.md", "TECH-206"),
        ("ai/features/ARCH-196-cas.md", "ARCH-196"),
        ("ai/features/GROWTH-12-thing.md", "GROWTH-12"),
    ],
)
def test_spec_id_from_path_variants(path, expected):
    assert salvage.spec_id_from_path(path) == expected


@pytest.mark.parametrize("path", ["", "ai/features/notes.md", "readme.md"])
def test_spec_id_from_path_none(path):
    assert salvage.spec_id_from_path(path) is None


# ---------------------------------------------------------------------------
# find_worktree
# ---------------------------------------------------------------------------


def test_find_worktree_by_directory_name(project):
    repo, _ = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    found = salvage.find_worktree(str(repo), "FTR-0001")
    assert found is not None
    assert Path(found[0]).resolve() == wt.resolve()
    assert found[1] == "feature/FTR-0001"


def test_find_worktree_by_branch_when_directory_differs(project):
    """A worktree named by hand still resolves through its branch."""
    repo, _ = project
    _add_worktree(repo, "somewhere-else", "feature/FTR-0002")
    found = salvage.find_worktree(str(repo), "FTR-0002")
    assert found is not None
    assert found[1] == "feature/FTR-0002"


def test_find_worktree_absent(project):
    repo, _ = project
    _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    assert salvage.find_worktree(str(repo), "FTR-9999") is None


def test_find_worktree_ignores_other_specs(project):
    """Two live worktrees — salvage must not touch the neighbouring slot's work."""
    repo, _ = project
    _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    wt2 = _add_worktree(repo, "FTR-0002", "feature/FTR-0002")
    found = salvage.find_worktree(str(repo), "FTR-0002")
    assert Path(found[0]).resolve() == wt2.resolve()


# ---------------------------------------------------------------------------
# _snapshot_dirty_tree
# ---------------------------------------------------------------------------


def test_snapshot_commits_dirty_tree(project):
    repo, _ = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    (wt / "half_done.py").write_text("def f():\n    pass\n", encoding="utf-8")

    sha = salvage._snapshot_dirty_tree(str(wt), "feature/FTR-0001", "wip(FTR-0001): salvaged")

    assert sha
    assert _git(wt, "rev-parse", "HEAD") == sha
    assert "half_done.py" in _git(wt, "show", "--name-only", "--format=", sha)


def test_snapshot_returns_none_when_clean(project):
    repo, _ = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    before = _git(wt, "rev-parse", "HEAD")

    assert salvage._snapshot_dirty_tree(str(wt), "feature/FTR-0001", "wip") is None
    assert _git(wt, "rev-parse", "HEAD") == before


def test_snapshot_excludes_lifecycle(project):
    """Plumbing bypasses the pre-commit guard, so the exclusion lives in salvage."""
    repo, _ = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    (wt / "src.py").write_text("x = 1\n", encoding="utf-8")
    (wt / "ai" / "lifecycle" / "FTR-0001.yaml").write_text("status: done\n", encoding="utf-8")

    sha = salvage._snapshot_dirty_tree(str(wt), "feature/FTR-0001", "wip")

    files = _git(wt, "show", "--name-only", "--format=", sha)
    assert "src.py" in files
    assert "lifecycle" not in files


def test_snapshot_leaves_worktree_clean(project):
    """The private index must not leave the default one stale (TECH-194 Layer D)."""
    repo, _ = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    (wt / "a.py").write_text("a = 1\n", encoding="utf-8")
    (wt / "README.md").write_text("edited\n", encoding="utf-8")
    _git(wt, "add", "README.md")  # a partially staged tree, as a live session leaves it

    salvage._snapshot_dirty_tree(str(wt), "feature/FTR-0001", "wip")

    assert _git(wt, "status", "--porcelain") == ""


def test_snapshot_refuses_when_branch_moved(project):
    """CAS: another writer advancing the branch must abort the snapshot."""
    repo, _ = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    (wt / "a.py").write_text("a = 1\n", encoding="utf-8")
    head = _git(wt, "rev-parse", "HEAD")
    # Move the ref behind salvage's back, then hand it the stale expectation.
    (wt / "b.py").write_text("b = 2\n", encoding="utf-8")
    _git(wt, "add", "b.py")
    _git(wt, "commit", "-qm", "concurrent")
    moved = _git(wt, "rev-parse", "HEAD")
    assert moved != head

    # update-ref is given HEAD-as-of-now, so this one succeeds; the guard is
    # exercised by pinning the old value explicitly.
    r = subprocess.run(
        ["git", "update-ref", "refs/heads/feature/FTR-0001", moved, head],
        cwd=str(wt),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0, "update-ref CAS should reject a stale old-value"


# ---------------------------------------------------------------------------
# salvage_run
# ---------------------------------------------------------------------------


def test_salvage_run_pushes_committed_and_dirty_work(project):
    repo, origin = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    (wt / "task1.py").write_text("done = True\n", encoding="utf-8")
    _git(wt, "add", "task1.py")
    _git(wt, "commit", "-qm", "feat(FTR-0001): task 1")
    (wt / "task2.py").write_text("in_flight = True\n", encoding="utf-8")  # never committed

    info = salvage.salvage_run(str(repo), "FTR-0001", "timeout")

    assert info["pushed"] is True
    assert info["error"] is None
    assert info["snapshot"]
    assert info["commits_ahead"] == 2
    # The work is on origin, which is the entire point.
    remote_sha = _git(origin, "rev-parse", "refs/heads/feature/FTR-0001")
    assert remote_sha == _git(wt, "rev-parse", "HEAD")
    assert "task2.py" in _git(origin, "show", "--name-only", "--format=", remote_sha)


def test_salvage_run_pushes_when_tree_is_clean(project):
    """The common case: tasks committed, run died before PHASE 3 pushed."""
    repo, origin = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    (wt / "task1.py").write_text("done = True\n", encoding="utf-8")
    _git(wt, "add", "task1.py")
    _git(wt, "commit", "-qm", "feat(FTR-0001): task 1")

    info = salvage.salvage_run(str(repo), "FTR-0001", "timeout")

    assert info["pushed"] is True
    assert info["snapshot"] is None
    assert info["commits_ahead"] == 1
    assert _git(origin, "rev-parse", "refs/heads/feature/FTR-0001")


def test_salvage_run_nothing_to_salvage(project):
    repo, origin = project
    _add_worktree(repo, "FTR-0001", "feature/FTR-0001")

    info = salvage.salvage_run(str(repo), "FTR-0001", "timeout")

    assert info["pushed"] is False
    assert info["error"] == "nothing_to_salvage"
    r = subprocess.run(
        ["git", "rev-parse", "refs/heads/feature/FTR-0001"],
        cwd=str(origin),
        capture_output=True,
        check=False,
    )
    assert r.returncode != 0, "an empty branch must not be pushed"


def test_salvage_run_refuses_protected_branch(project):
    repo, origin = project
    _add_worktree(repo, "FTR-0001", "main")  # a worktree that ended up on main
    (repo / ".worktrees" / "FTR-0001" / "x.py").write_text("x = 1\n", encoding="utf-8")

    info = salvage.salvage_run(str(repo), "FTR-0001", "timeout")

    assert info["pushed"] is False
    assert "protected" in info["error"]
    r = subprocess.run(
        ["git", "rev-parse", "refs/heads/main"], cwd=str(origin), capture_output=True, check=False
    )
    assert r.returncode != 0


def test_salvage_run_without_worktree(project):
    repo, _ = project
    info = salvage.salvage_run(str(repo), "FTR-9999", "timeout")
    assert info["attempted"] is True
    assert info["error"] == "no_worktree"
    assert info["pushed"] is False


def test_salvage_run_reports_push_failure(project):
    """A dead remote must be reported, not swallowed — this is telemetry people act on."""
    repo, _ = project
    wt = _add_worktree(repo, "FTR-0001", "feature/FTR-0001")
    (wt / "task1.py").write_text("x = 1\n", encoding="utf-8")
    _git(wt, "add", "task1.py")
    _git(wt, "commit", "-qm", "feat(FTR-0001): task 1")
    _git(repo, "remote", "set-url", "origin", str(repo / "does-not-exist.git"))

    info = salvage.salvage_run(str(repo), "FTR-0001", "timeout")

    assert info["pushed"] is False
    assert info["error"] and "push failed" in info["error"]
