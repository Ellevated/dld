"""
Unit tests for scripts/vps/lifecycle.py.

Tests 1, 2 (concurrent + private index) run unconditionally.
Test 3 (BUG-185 regression) is skipped pending Task 3 (ff-only pull rewrite).

Note: read_lifecycle and list_by_status read from HEAD (git object store), so
      working tree sync is not needed for read operations.
      assert_clean_lifecycle_tree checks working tree — tests that exercise
      dirty-WT detection write files to WT directly.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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
            cwd=str(repo), capture_output=True, text=True, check=False,
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
    (lc_dir / ".gitkeep").write_text("")
    git("add", ".")
    git("commit", "-m", "init")

    return repo


# ---------------------------------------------------------------------------
# Test 1 (spec line 601): atomic write under concurrency
# ---------------------------------------------------------------------------

def test_concurrent_writes_no_loss(tmp_git_repo):
    """10 parallel write_lifecycle() for different specs — all land in HEAD."""
    import concurrent.futures as cf

    def write_one(i):
        lifecycle.write_lifecycle(tmp_git_repo, f"TECH-{i}", "queued")

    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(write_one, i) for i in range(10)]
        for f in futures:
            f.result()  # propagate any exceptions

    for i in range(10):
        data = lifecycle.read_lifecycle(tmp_git_repo, f"TECH-{i}")
        assert data is not None, f"TECH-{i} missing from HEAD"
        assert data["status"] == "queued"
        assert data["version"] >= 1


# ---------------------------------------------------------------------------
# Test 2 (spec line 618): private GIT_INDEX_FILE — operator-staged files don't leak
# ---------------------------------------------------------------------------

def test_operator_staged_file_does_not_leak(tmp_git_repo):
    """Operator does git add some-other-file. Callback writes lifecycle.
    Commit contains ONLY lifecycle, not some-other-file."""
    wip = tmp_git_repo / "operator-wip.txt"
    wip.write_text("wip")
    subprocess.run(["git", "add", "operator-wip.txt"],
                   cwd=str(tmp_git_repo), check=True)

    lifecycle.write_lifecycle(tmp_git_repo, "TECH-100", "done")

    # Last commit should only contain the lifecycle yaml
    r = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=str(tmp_git_repo), capture_output=True, text=True,
    )
    changed_files = r.stdout.strip()
    assert "ai/lifecycle/TECH-100.yaml" in changed_files
    assert "operator-wip.txt" not in changed_files

    # operator-wip.txt still staged, not lost
    r2 = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(tmp_git_repo), capture_output=True, text=True,
    )
    assert "operator-wip.txt" in r2.stdout


# ---------------------------------------------------------------------------
# Test 3 (spec line 633, BUG-185 regression): skipped pending Task 3
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="awaits Task 3 ff-only rename")
def test_dirty_wt_does_not_revert_callback_write(tmp_git_repo):
    """Simulate BUG-185: dirty WT + callback write. Lifecycle.yaml in HEAD
    remains 'done' even after next scan."""
    import orchestrator  # noqa: F401 — not yet refactored

    lifecycle.create_initial(tmp_git_repo, "TECH-200", "p1", "tech")
    (tmp_git_repo / "ai" / "qa").mkdir(parents=True, exist_ok=True)
    (tmp_git_repo / "ai" / "qa" / "garbage.md").write_text("untracked")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-200", "done")

    # Orchestrator next cycle (no autostash dance after Task 3)
    orchestrator.git_pull_ff_only(tmp_git_repo)  # no-op if up-to-date

    queued = lifecycle.list_by_status(tmp_git_repo, "queued")
    assert "TECH-200" not in [s["spec_id"] for s in queued]


# ---------------------------------------------------------------------------
# Additional unit tests
# ---------------------------------------------------------------------------

def test_create_initial_then_read(tmp_git_repo):
    """Round-trip: create_initial → read_lifecycle returns correct data."""
    lifecycle.create_initial(tmp_git_repo, "TECH-501", "p0", "ftr")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-501")
    assert data is not None
    assert data["spec_id"] == "TECH-501"
    assert data["status"] == "queued"
    assert data["priority"] == "p0"
    assert data["kind"] == "ftr"
    assert data["version"] == 1
    assert data["transitions"] == []


def test_version_monotonic(tmp_git_repo):
    """Two writes must increment version each time."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-502", "queued")
    d1 = lifecycle.read_lifecycle(tmp_git_repo, "TECH-502")
    assert d1["version"] == 1

    lifecycle.write_lifecycle(tmp_git_repo, "TECH-502", "in_progress")
    d2 = lifecycle.read_lifecycle(tmp_git_repo, "TECH-502")
    assert d2["version"] == 2
    assert d2["status"] == "in_progress"


def test_started_at_set_on_in_progress(tmp_git_repo):
    """started_at should be set when transitioning queued→in_progress."""
    lifecycle.create_initial(tmp_git_repo, "TECH-503", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-503", "in_progress")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-503")
    assert data["started_at"] is not None


def test_finished_at_set_on_done(tmp_git_repo):
    """finished_at should be set when transitioning to done."""
    lifecycle.create_initial(tmp_git_repo, "TECH-504", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-504", "in_progress")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-504", "done")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-504")
    assert data["finished_at"] is not None
    assert data["status"] == "done"


def test_list_by_status_filters(tmp_git_repo):
    """Write 3 specs with mixed statuses, list_by_status filters correctly."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-510", "queued")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-511", "in_progress")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-512", "done")

    queued = lifecycle.list_by_status(tmp_git_repo, "queued")
    spec_ids = [d["spec_id"] for d in queued]
    assert "TECH-510" in spec_ids
    assert "TECH-511" not in spec_ids
    assert "TECH-512" not in spec_ids

    # Multi-status filter
    active = lifecycle.list_by_status(tmp_git_repo, {"queued", "in_progress"})
    active_ids = [d["spec_id"] for d in active]
    assert "TECH-510" in active_ids
    assert "TECH-511" in active_ids
    assert "TECH-512" not in active_ids


def test_assert_clean_lifecycle_tree_raises_on_dirty(tmp_git_repo):
    """Manually writing a lifecycle yaml without committing → raises RuntimeError."""
    lc_dir = tmp_git_repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True, exist_ok=True)
    (lc_dir / "TECH-520.yaml").write_text("spec_id: TECH-520\nstatus: queued\n")

    with pytest.raises(RuntimeError, match="Dirty lifecycle"):
        lifecycle.assert_clean_lifecycle_tree(tmp_git_repo)


def test_assert_clean_lifecycle_tree_passes_when_clean(tmp_git_repo):
    """assert_clean_lifecycle_tree passes when lifecycle/ WT matches HEAD."""
    lifecycle.create_initial(tmp_git_repo, "TECH-521", "p2", "bug")
    # Plumbing write adds the file to HEAD but NOT to WT.
    # In production the orchestrator calls git pull to sync WT.
    # Here we simulate that sync explicitly:
    subprocess.run(
        ["git", "checkout", "HEAD", "--", "ai/lifecycle/"],
        cwd=str(tmp_git_repo), check=True,
    )
    lifecycle.assert_clean_lifecycle_tree(tmp_git_repo)  # should not raise


def test_reconcile_orphans_demotes_in_progress(tmp_git_repo):
    """write in_progress with pueue_id=999, pass empty alive set → reconciled."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-530", "in_progress", pueue_id=999)

    reconciled = lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids=set())
    assert "TECH-530" in reconciled

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-530")
    assert data["status"] == "queued"
    assert data.get("blocked_reason") == "orphaned from crash"


def test_reconcile_orphans_skips_alive_tasks(tmp_git_repo):
    """pueue_id=888 is alive — should not be reconciled."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-531", "in_progress", pueue_id=888)

    reconciled = lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids={888})
    assert "TECH-531" not in reconciled


def test_read_lifecycle_returns_none_for_missing(tmp_git_repo):
    """read_lifecycle returns None for a spec that doesn't exist."""
    result = lifecycle.read_lifecycle(tmp_git_repo, "TECH-NONEXISTENT")
    assert result is None


def test_blocked_reason_stored(tmp_git_repo):
    """write_lifecycle with reason= stores it as blocked_reason."""
    lifecycle.create_initial(tmp_git_repo, "TECH-540", "p1", "tech")
    lifecycle.write_lifecycle(
        tmp_git_repo, "TECH-540", "blocked",
        reason="no implementation commits",
    )
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-540")
    assert data["status"] == "blocked"
    assert data["blocked_reason"] == "no implementation commits"


def test_transitions_list_grows(tmp_git_repo):
    """Each write appends to transitions list."""
    lifecycle.create_initial(tmp_git_repo, "TECH-550", "p1", "tech")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-550", "in_progress")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-550", "done")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-550")
    # create_initial doesn't add transition; 2 writes add 2 transitions
    assert len(data["transitions"]) == 2
    assert data["transitions"][0]["from"] == "queued"
    assert data["transitions"][0]["to"] == "in_progress"
    assert data["transitions"][1]["from"] == "in_progress"
    assert data["transitions"][1]["to"] == "done"
