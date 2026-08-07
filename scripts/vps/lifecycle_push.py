"""
Module: lifecycle_push
Role: Push the lifecycle commit to origin and self-heal a non-fast-forward
      reject — fetch, verify the local-ahead commits are lifecycle/backlog-only,
      rebase onto origin, retry. Falls back to a best-effort failure counter.

Uses:
  - subprocess: TimeoutExpired
  - pathlib: Path (failure counter file)
  - lifecycle_git: _run
  - lifecycle_const: LIFECYCLE_DIR, _PUSH_REBASE_RETRIES

Used by:
  - lifecycle.py: write_file_atomic
  - lifecycle_cas.py: _cas_loop
"""

import logging
import subprocess
from pathlib import Path

import lifecycle_git
from lifecycle_const import _PUSH_REBASE_RETRIES, LIFECYCLE_DIR

log = logging.getLogger(__name__)


def _push_best_effort(repo_dir: str, branch: str) -> None:
    """Push the lifecycle commit to origin; self-heal a non-fast-forward reject.

    Failure mode (push-race divergence): while an agent runs, orchestrator skips
    git pull, so callback commits status on a STALE local develop. Meanwhile the
    agent's code commits land on origin. The plain push is then rejected
    non-fast-forward and the branches diverge — orchestrator's `merge --ff-only`
    can never heal it, so the done-commit is trapped locally and the status looks
    stuck at queued (9 manual rebases/day on awardybot, 2026-06-21).

    Recovery: fetch origin, verify the local-ahead commits touch ONLY lifecycle/
    backlog paths (callback is their sole writer → conflict-free by construction),
    rebase them onto origin/<branch> and retry the push. Bounded; on any surprise
    (dirty WT, a non-lifecycle local commit, rebase conflict) abort cleanly and
    fall back to the legacy best-effort counter — never worse than before.
    """
    if _try_push(repo_dir, branch):
        return
    for attempt in range(1, _PUSH_REBASE_RETRIES + 1):
        if not _rebase_onto_origin(repo_dir, branch):
            break
        if _try_push(repo_dir, branch):
            log.info(
                "lifecycle push recovered via rebase onto origin/%s (attempt %d)",
                branch,
                attempt,
            )
            return
        # push raced again (origin moved between fetch and push) — retry
    log.warning(
        "lifecycle push failed after rebase recovery (best-effort, not fatal): branch=%s",
        branch,
    )
    _bump_push_failure_counter(repo_dir)


def _try_push(repo_dir: str, branch: str) -> bool:
    """Single `git push origin <branch>`. True on success, False on any failure."""
    try:
        r = lifecycle_git._run(["git", "push", "origin", branch], cwd=repo_dir, timeout=60)
    except subprocess.TimeoutExpired as exc:
        log.warning("lifecycle push timeout: branch=%s cmd=%s", branch, exc.cmd)
        return False
    if r.returncode != 0:
        log.info(
            "lifecycle push rejected (will attempt rebase recovery): branch=%s stderr=%s",
            branch,
            r.stderr.strip()[:200],
        )
        return False
    return True


def _local_ahead_is_lifecycle_only(repo_dir: str, branch: str) -> bool:
    """True iff every commit in origin/<branch>..HEAD touches only lifecycle/backlog.

    This is the safety gate that makes auto-rebase sound: callback is the sole
    writer of ai/lifecycle/*.yaml (+ the folded ai/backlog.md render), and code
    commits never touch those paths, so replaying lifecycle-only commits onto
    origin is conflict-free by construction. Any other ahead-commit → bail.
    """
    rev = lifecycle_git._run(["git", "rev-list", f"origin/{branch}..HEAD"], cwd=repo_dir)
    if rev.returncode != 0:
        return False
    commits = rev.stdout.split()
    if not commits:
        # Nothing ahead — the rejection wasn't a divergence we created. Bail
        # (a plain behind-only state is not our recovery case).
        return False
    for sha in commits:
        files = lifecycle_git._run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
            cwd=repo_dir,
        )
        if files.returncode != 0:
            return False
        for path in files.stdout.splitlines():
            path = path.strip()
            if not path:
                continue
            if not (path.startswith(f"{LIFECYCLE_DIR}/") or path == "ai/backlog.md"):
                return False
    return True


def _rebase_onto_origin(repo_dir: str, branch: str) -> bool:
    """Fetch origin/<branch> and rebase local lifecycle-only commits onto it.

    Returns True only if the rebase succeeded and left a clean WT. Returns False
    (state restored) on any guard failure: fetch error, dirty WT, a non-lifecycle
    local-ahead commit, or a rebase conflict (which is aborted). On False the
    caller falls back to the legacy counter — never worse than the old behavior.
    """
    try:
        fetch = lifecycle_git._run(
            ["git", "fetch", "--quiet", "origin", branch], cwd=repo_dir, timeout=60
        )
    except subprocess.TimeoutExpired:
        log.warning("lifecycle rebase: fetch timeout branch=%s", branch)
        return False
    if fetch.returncode != 0:
        log.warning(
            "lifecycle rebase: fetch failed branch=%s stderr=%s",
            branch,
            fetch.stderr.strip()[:200],
        )
        return False

    # Guard 1: WT must be clean. rebase refuses on a dirty tree, and we must
    # never disturb uncommitted work. In the stuck case the WT is clean (just
    # behind origin) because _atomic_write synced only the yaml+backlog paths.
    status = lifecycle_git._run(["git", "status", "--porcelain"], cwd=repo_dir)
    if status.returncode != 0 or status.stdout.strip():
        log.warning("lifecycle rebase: WT not clean, skipping auto-rebase branch=%s", branch)
        return False

    # Guard 2: only auto-rebase when every ahead-commit is lifecycle/backlog-only.
    if not _local_ahead_is_lifecycle_only(repo_dir, branch):
        log.warning(
            "lifecycle rebase: local-ahead commits touch non-lifecycle files — "
            "refusing auto-rebase (manual heal) branch=%s",
            branch,
        )
        return False

    try:
        rebase = lifecycle_git._run(["git", "rebase", f"origin/{branch}"], cwd=repo_dir, timeout=60)
    except subprocess.TimeoutExpired:
        log.warning("lifecycle rebase: timeout branch=%s — aborting", branch)
        lifecycle_git._run(["git", "rebase", "--abort"], cwd=repo_dir)
        return False
    if rebase.returncode != 0:
        log.warning(
            "lifecycle rebase: conflict/failure, aborting branch=%s stderr=%s",
            branch,
            rebase.stderr.strip()[:200],
        )
        lifecycle_git._run(["git", "rebase", "--abort"], cwd=repo_dir)
        return False
    return True


def _bump_push_failure_counter(repo_dir: str) -> None:
    """Increment ai/.lifecycle-push-failures counter (best-effort)."""
    counter = Path(repo_dir) / "ai" / ".lifecycle-push-failures"
    try:
        prev = int(counter.read_text().strip()) if counter.is_file() else 0
        counter.write_text(str(prev + 1))
    except Exception:  # noqa: BLE001
        pass
