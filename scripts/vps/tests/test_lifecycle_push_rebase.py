"""
Regression suite for the lifecycle push-race divergence fix.

Failure mode: while an agent runs, orchestrator skips git pull, so callback
commits a status on a STALE local develop. Meanwhile the agent's code commits
land on origin. The plain `git push` is rejected non-fast-forward → branches
diverge → orchestrator's `merge --ff-only` can never heal it → the done-commit
is trapped locally and the status looks stuck at queued (9 manual rebases/day
on awardybot, 2026-06-21).

Fix: _push_best_effort fetches origin, verifies the local-ahead commits are
lifecycle/backlog-only (conflict-free by construction), rebases them onto
origin and retries the push. Guards: clean WT + lifecycle-only ahead-commits;
otherwise bail to the legacy counter (never worse than before).

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

import lifecycle_push  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {args} in {repo} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _config_identity(repo: Path) -> None:
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")


def _commit_file(repo: Path, rel: str, content: str, msg: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", msg)


def _origin_files(origin: Path, branch: str = "main") -> set:
    out = _git(origin, "ls-tree", "-r", "--name-only", branch)
    return set(out.splitlines())


def _push_failures(repo: Path) -> int:
    counter = repo / "ai" / ".lifecycle-push-failures"
    return int(counter.read_text(encoding="utf-8").strip()) if counter.is_file() else 0


# ---------------------------------------------------------------------------
# Fixture: bare origin + local clone + a second clone to move origin
# ---------------------------------------------------------------------------


@pytest.fixture()
def repos(tmp_path):
    """(origin bare, local clone, other clone) seeded with one shared commit."""
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        capture_output=True,
        text=True,
        check=True,
    )

    # Seed via the local clone
    local = tmp_path / "local"
    subprocess.run(
        ["git", "clone", str(origin), str(local)],
        capture_output=True,
        text=True,
        check=True,
    )
    _config_identity(local)
    (local / "ai" / "lifecycle").mkdir(parents=True)
    (local / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    (local / "ai" / "backlog.md").write_text("# Backlog\n", encoding="utf-8")
    (local / "src.py").write_text("x = 0\n", encoding="utf-8")
    _git(local, "add", ".")
    _git(local, "commit", "-m", "init")
    _git(local, "push", "-u", "origin", "main")

    # Independent clone used to advance origin (simulates the agent's worktree push)
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", str(origin), str(other)],
        capture_output=True,
        text=True,
        check=True,
    )
    _config_identity(other)

    return origin, local, other


# ---------------------------------------------------------------------------
# Test 1: happy path — push succeeds first try, no rebase needed
# ---------------------------------------------------------------------------


def test_push_succeeds_without_divergence(repos):
    origin, local, _other = repos
    _commit_file(local, "ai/lifecycle/TEST-1.yaml", "status: done\n", "lifecycle(TEST-1): done")

    lifecycle_push._push_best_effort(str(local), "main")

    assert "ai/lifecycle/TEST-1.yaml" in _origin_files(origin)
    assert _push_failures(local) == 0


# ---------------------------------------------------------------------------
# Test 2: push-race divergence — recovered via rebase (the core fix)
# ---------------------------------------------------------------------------


def test_push_race_divergence_recovered(repos):
    origin, local, other = repos

    # Agent's code commit lands on origin first (local does NOT have it yet).
    _git(other, "pull", "--ff-only", "origin", "main")
    _commit_file(other, "src.py", "x = 99\n", "fix(BUG-1): agent code")
    _git(other, "push", "origin", "main")

    # callback commits status on the STALE local develop (origin/main tracking
    # ref in `local` is still the seed commit — orchestrator skipped the pull).
    _commit_file(local, "ai/lifecycle/BUG-1.yaml", "status: done\n", "lifecycle(BUG-1): done")

    lifecycle_push._push_best_effort(str(local), "main")

    # Both the agent's code AND the lifecycle status must be on origin now.
    files = _origin_files(origin)
    assert "ai/lifecycle/BUG-1.yaml" in files
    origin_src = _git(origin, "show", "main:src.py")
    assert origin_src == "x = 99", "agent code commit was clobbered"

    # Local must be in sync with origin (no lingering divergence).
    assert _git(local, "rev-parse", "main") == _git(origin, "rev-parse", "main")
    assert _push_failures(local) == 0, "recovery must not bump the failure counter"


# ---------------------------------------------------------------------------
# Test 3: backlog.md ahead-commit is allowed (folded render is lifecycle-owned)
# ---------------------------------------------------------------------------


def test_backlog_ahead_commit_is_rebased(repos):
    origin, local, other = repos

    _git(other, "pull", "--ff-only", "origin", "main")
    _commit_file(other, "src.py", "x = 7\n", "fix: code")
    _git(other, "push", "origin", "main")

    # Lifecycle commit that also touches the backlog render (the real shape).
    (local / "ai" / "lifecycle" / "BUG-2.yaml").write_text("status: done\n", encoding="utf-8")
    (local / "ai" / "backlog.md").write_text("# Backlog\n\nBUG-2 done\n", encoding="utf-8")
    _git(local, "add", "ai/lifecycle/BUG-2.yaml", "ai/backlog.md")
    _git(local, "commit", "-m", "lifecycle(BUG-2): done")

    lifecycle_push._push_best_effort(str(local), "main")

    files = _origin_files(origin)
    assert "ai/lifecycle/BUG-2.yaml" in files
    assert _git(origin, "show", "main:src.py") == "x = 7"
    assert _push_failures(local) == 0


# ---------------------------------------------------------------------------
# Test 4: guard — a non-lifecycle local commit must NOT be auto-rebased
# ---------------------------------------------------------------------------


def test_non_lifecycle_ahead_commit_bails(repos):
    origin, local, other = repos

    _git(other, "pull", "--ff-only", "origin", "main")
    _commit_file(other, "src.py", "x = 1\n", "fix: origin code")
    _git(other, "push", "origin", "main")

    # Local is ahead by a CODE commit (not lifecycle) → divergence we must not touch.
    _commit_file(local, "other.py", "y = 2\n", "feat: unexpected local code")

    lifecycle_push._push_best_effort(str(local), "main")

    # The unexpected local commit must NOT have been force-rebased onto origin.
    assert "other.py" not in _origin_files(origin)
    assert _push_failures(local) == 1, "unrecoverable divergence must bump the counter"


# ---------------------------------------------------------------------------
# Test 5: guard — dirty WT blocks the auto-rebase
# ---------------------------------------------------------------------------


def test_dirty_wt_blocks_rebase(repos):
    origin, local, other = repos

    _git(other, "pull", "--ff-only", "origin", "main")
    _commit_file(other, "src.py", "x = 5\n", "fix: code")
    _git(other, "push", "origin", "main")

    _commit_file(local, "ai/lifecycle/BUG-3.yaml", "status: done\n", "lifecycle(BUG-3): done")

    # Make the WT dirty — rebase must refuse.
    (local / "src.py").write_text("x = DIRTY\n", encoding="utf-8")

    ok = lifecycle_push._rebase_onto_origin(str(local), "main")
    assert ok is False
    # WT untouched, no rebase-in-progress left behind.
    assert (local / "src.py").read_text(encoding="utf-8") == "x = DIRTY\n"
    assert not (local / ".git" / "rebase-merge").exists()
    assert not (local / ".git" / "rebase-apply").exists()


# ---------------------------------------------------------------------------
# Test 6: _local_ahead_is_lifecycle_only classification
# ---------------------------------------------------------------------------


def test_local_ahead_classification(repos):
    origin, local, _other = repos

    # Nothing ahead → False
    _git(local, "fetch", "origin", "main")
    assert lifecycle_push._local_ahead_is_lifecycle_only(str(local), "main") is False

    # Lifecycle-only ahead → True
    _commit_file(local, "ai/lifecycle/BUG-9.yaml", "status: done\n", "lifecycle(BUG-9): done")
    assert lifecycle_push._local_ahead_is_lifecycle_only(str(local), "main") is True

    # Add a code commit on top → mixed → False
    _commit_file(local, "src.py", "x = 2\n", "fix: code on top")
    assert lifecycle_push._local_ahead_is_lifecycle_only(str(local), "main") is False


# ---------------------------------------------------------------------------
# Test 7: guard — an unrelated dirty file must NOT disarm the rebase
# ---------------------------------------------------------------------------


def test_unrelated_dirty_file_still_rebases(repos):
    """The 2026-08-24 freeze: a human's edit outside the rebase path is survivable.

    Widening the guard to "any file the rebase rewrites" must not walk that fix
    back — origin never touched notes.md, so it stays out of the way.
    """
    origin, local, other = repos

    _git(other, "pull", "--ff-only", "origin", "main")
    _commit_file(other, "src.py", "x = 5\n", "fix: code")
    _git(other, "push", "origin", "main")

    _commit_file(local, "ai/lifecycle/BUG-7.yaml", "status: done\n", "lifecycle(BUG-7): done")
    (local / "notes.md").write_text("человеческий черновик\n", encoding="utf-8")

    assert lifecycle_push._rebase_onto_origin(str(local), "main") is True
    assert (local / "notes.md").read_text(encoding="utf-8") == "человеческий черновик\n"
    assert "<<<<<<<" not in (local / "src.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 8: a conflicted autostash pop leaves no markers behind
# ---------------------------------------------------------------------------


def test_conflicted_autostash_pop_is_cleared(repos):
    """`git rebase --autostash` exits 0 on a conflicted pop — the net must clean it.

    Reachable only as a race (origin moving between fetch and rebase), so the
    rebase is driven by hand here to produce exactly that state.
    """
    origin, local, other = repos

    _git(other, "pull", "--ff-only", "origin", "main")
    _commit_file(other, "src.py", "x = 5\n", "fix: code")
    _git(other, "push", "origin", "main")

    _commit_file(local, "ai/lifecycle/BUG-8.yaml", "status: done\n", "lifecycle(BUG-8): done")
    (local / "src.py").write_text("x = DIRTY\n", encoding="utf-8")

    _git(local, "fetch", "origin", "main")
    subprocess.run(
        ["git", "-C", str(local), "rebase", "--autostash", "origin/main"],
        capture_output=True,
        text=True,
        check=False,
    )
    # Precondition: git called this a success and still left the mess.
    assert "<<<<<<<" in (local / "src.py").read_text(encoding="utf-8")

    lifecycle_push._clear_autostash_conflict(str(local))

    assert (local / "src.py").read_text(encoding="utf-8") == "x = 5\n"
    assert _git(local, "diff", "--name-only", "--diff-filter=U") == ""
    assert "autostash" in _git(local, "stash", "list"), "работа человека обязана остаться в стеше"
