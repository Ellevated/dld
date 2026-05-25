"""
Integration tests for orchestrator.py post-ARCH-186 lifecycle changes.

Test 4: startup_reconcile demotes orphaned in_progress specs.
Test 5: assert_clean_lifecycle_tree aborts on dirty lifecycle/ WT.
Test 6: bootstrap_new_specs creates lifecycle.yaml for spec.md missing one.
Bonus:  bootstrap_new_specs is idempotent.
"""

import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import orchestrator  # noqa: E402


@pytest.fixture()
def tmp_git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("")
    (repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
    git("add", ".")
    git("commit", "-m", "init")
    return repo


# Test 4: orphan demotion
def test_orphaned_in_progress_demoted_on_restart(tmp_git_repo):
    """Lifecycle says in_progress, no live pueue task → reconcile demotes to queued."""
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-300", "in_progress", pueue_id=999)
    reconciled = lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids=set())
    assert "TECH-300" in reconciled
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-300")
    assert data["status"] == "queued"
    assert data.get("blocked_reason") == "orphaned from crash"


# Test 5: dirty WT abort
def test_dirty_lifecycle_aborts_orchestrator_startup(tmp_git_repo):
    """Manual edit to ai/lifecycle/TECH-X.yaml → startup raises RuntimeError."""
    lifecycle.create_initial(tmp_git_repo, "TECH-400", "p1", "tech")
    # Sync HEAD → WT then dirty it
    subprocess.run(
        ["git", "checkout", "HEAD", "--", "ai/lifecycle/"],
        cwd=str(tmp_git_repo),
        check=True,
    )
    (tmp_git_repo / "ai" / "lifecycle" / "TECH-400.yaml").write_text("manually corrupted\n")
    with pytest.raises(RuntimeError, match="Dirty lifecycle"):
        lifecycle.assert_clean_lifecycle_tree(tmp_git_repo)


# Test 6: bootstrap from spec.md
def test_bootstrap_creates_lifecycle_for_new_spec(tmp_git_repo):
    """Spark created spec.md without lifecycle.yaml → orchestrator creates initial."""
    spec = tmp_git_repo / "ai" / "features" / "TECH-500-foo.md"
    spec.write_text("# TECH-500\n**Priority:** P1\n**Kind:** tech\n")
    # bootstrap_new_specs requires backlog.md to guard against orphan spec.md files
    (tmp_git_repo / "ai").mkdir(parents=True, exist_ok=True)
    (tmp_git_repo / "ai" / "backlog.md").write_text(
        "| ID | Title | Status | P |\n|---|---|---|---|\n| TECH-500 | foo | queued | P1 |\n"
    )
    assert not (tmp_git_repo / "ai" / "lifecycle" / "TECH-500.yaml").exists()
    orchestrator.bootstrap_new_specs(str(tmp_git_repo))
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-500")
    assert data is not None
    assert data["status"] == "queued"
    assert data["priority"] == "p1"
    assert data["kind"] == "tech"


# Bonus: bootstrap is idempotent
def test_bootstrap_idempotent_when_lifecycle_exists(tmp_git_repo):
    """Lifecycle already exists → bootstrap_new_specs does not overwrite it."""
    lifecycle.create_initial(tmp_git_repo, "TECH-501", "p0", "ftr")
    spec = tmp_git_repo / "ai" / "features" / "TECH-501-bar.md"
    spec.write_text("# TECH-501\n**Priority:** P2\n**Kind:** bug\n")
    orchestrator.bootstrap_new_specs(str(tmp_git_repo))  # no-op expected
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-501")
    # Original priority p0/kind ftr preserved, NOT overwritten with spec.md's p2/bug
    assert data["priority"] == "p0"
    assert data["kind"] == "ftr"
