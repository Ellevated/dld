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
import os
import re
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

    # Guard 1: a dirty WT is survivable, an OVERLAPPING dirty WT is not.
    # The old rule ("clean or bail") sounded safe and cost dowry 16 hours and
    # memyselfandi 17 days of a frozen orchestrator on 2026-08-24: the human's
    # own unrelated edits (9 files under _Dowry/) were enough to disarm the
    # self-heal forever. rebase --autostash puts them back on both paths —
    # success and abort — so uncommitted work is still never disturbed.
    # What we do refuse is a dirty file the rebase itself will rewrite: there
    # the autostash pop would land in a conflict and leave a mess behind.
    if _dirty_overlaps_lifecycle(repo_dir):
        log.warning(
            "lifecycle rebase: uncommitted changes in lifecycle/backlog paths — "
            "refusing auto-rebase (manual heal) branch=%s",
            branch,
        )
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
        rebase = lifecycle_git._run(
            ["git", "rebase", "--autostash", f"origin/{branch}"], cwd=repo_dir, timeout=60
        )
    except subprocess.TimeoutExpired:
        log.warning("lifecycle rebase: timeout branch=%s — aborting", branch)
        lifecycle_git._run(["git", "rebase", "--abort"], cwd=repo_dir)
        return False
    if rebase.returncode != 0:
        # The module header calls lifecycle replay "conflict-free by
        # construction — callback is the sole writer". backlog.md broke that
        # claim on 2026-08-24: spark added an FTR-480 row on origin while
        # callback flipped BUG-479 to blocked locally, both inside the same
        # table. Two writers, one file, guaranteed conflict.
        if _resolve_backlog_only_conflict(repo_dir) and _rebase_continue(repo_dir):
            log.info("lifecycle rebase: backlog.md conflict merged row-wise branch=%s", branch)
            return True
        log.warning(
            "lifecycle rebase: conflict/failure, aborting branch=%s stderr=%s",
            branch,
            rebase.stderr.strip()[:200],
        )
        lifecycle_git._run(["git", "rebase", "--abort"], cwd=repo_dir)
        return False
    return True


def _dirty_overlaps_lifecycle(repo_dir: str) -> bool:
    """True iff uncommitted changes touch the paths the rebase will rewrite."""
    status = lifecycle_git._run(["git", "status", "--porcelain"], cwd=repo_dir)
    if status.returncode != 0:
        return True  # cannot tell → treat as unsafe
    for line in status.stdout.splitlines():
        path = line[3:].strip().strip('"')
        if " -> " in path:  # rename: the destination is what gets written
            path = path.split(" -> ", 1)[1]
        if path.startswith(LIFECYCLE_DIR) or path == "ai/backlog.md":
            return True
    return False


_BACKLOG_ROW = re.compile(r"^\|\s*((?:TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*)\s*\|")


def merge_backlog_conflict(text: str) -> str | None:
    """Resolve conflict markers in ai/backlog.md row-wise, or None if unsure.

    Both sides are rows of one table keyed by spec id, so the merge is defined:
    our side wins for the ids it mentions (callback just moved that spec), and
    rows only origin knows about (a spec filed while we were busy) are carried
    over. Anything inside a conflict block that is not a spec row → give up and
    let the caller abort, rather than inventing a merge for prose.
    """
    lines = text.split("\n")
    out: list[str] = []
    resolved = 0
    i = 0
    while i < len(lines):
        if not lines[i].startswith("<<<<<<<"):
            out.append(lines[i])
            i += 1
            continue
        ours: list[str] = []
        theirs: list[str] = []
        i += 1
        while i < len(lines) and not lines[i].startswith("======="):
            ours.append(lines[i])
            i += 1
        if i >= len(lines):
            return None  # truncated block
        i += 1
        while i < len(lines) and not lines[i].startswith(">>>>>>>"):
            theirs.append(lines[i])
            i += 1
        if i >= len(lines):
            return None
        i += 1
        block = [ln for ln in ours + theirs if ln.strip()]
        if not block or any(not _BACKLOG_ROW.match(ln) for ln in block):
            return None  # not a pure table conflict — not ours to resolve
        # During a rebase "ours" is the upstream being replayed onto (origin)
        # and "theirs" is the commit being replayed (our status change).
        mine = {_BACKLOG_ROW.match(ln).group(1) for ln in theirs if ln.strip()}
        out.extend(ln for ln in theirs if ln.strip())
        out.extend(
            ln
            for ln in ours
            if ln.strip() and _BACKLOG_ROW.match(ln).group(1) not in mine
        )
        resolved += 1
    return "\n".join(out) if resolved else None


def _resolve_backlog_only_conflict(repo_dir: str) -> bool:
    """Merge the conflict when ai/backlog.md is the ONLY unmerged file."""
    unmerged = lifecycle_git._run(
        ["git", "diff", "--name-only", "--diff-filter=U"], cwd=repo_dir
    )
    if unmerged.returncode != 0:
        return False
    if [f for f in unmerged.stdout.split() if f] != ["ai/backlog.md"]:
        return False
    path = Path(repo_dir) / "ai" / "backlog.md"
    try:
        merged = merge_backlog_conflict(path.read_text(encoding="utf-8"))
        if merged is None:
            return False
        path.write_text(merged, encoding="utf-8")
    except OSError:
        return False
    return lifecycle_git._run(["git", "add", "ai/backlog.md"], cwd=repo_dir).returncode == 0


def _rebase_continue(repo_dir: str) -> bool:
    """`git rebase --continue` with the editor disabled (message kept as-is)."""
    try:
        r = lifecycle_git._run(
            ["git", "-c", "core.editor=true", "rebase", "--continue"],
            cwd=repo_dir,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0


def _bump_push_failure_counter(repo_dir: str) -> None:
    """Increment ai/.lifecycle-push-failures counter, then wake a human."""
    counter = Path(repo_dir) / "ai" / ".lifecycle-push-failures"
    total = None
    try:
        prev = int(counter.read_text().strip()) if counter.is_file() else 0
        total = prev + 1
        counter.write_text(str(total))
    except Exception:  # noqa: BLE001
        pass
    _alert_push_failure(repo_dir, total)


def _alert_push_failure(repo_dir: str, total: int | None) -> None:
    """Tell a human. A counter nobody reads is not a signal.

    awardybot stood at 38 failures, dowry at 2, memyselfandi at 1 before
    anyone looked — and the two SMALL numbers were the ones that had frozen
    their orchestrators for days. Best-effort by design: no notifier → no
    noise, and never an exception back into the push path.
    """
    notify = Path.home() / "ops" / "notify.sh"
    if not os.access(notify, os.X_OK):
        return
    project = Path(repo_dir).name
    count = f"{total}-й раз" if total else "счётчик не прочитался"
    body = (
        f"Статус спеки закоммичен локально, но не уехал в origin ({count}).\n\n"
        "Пока это так, оркестратор по проекту стоит: его git merge --ff-only\n"
        "падает на разошедшихся ветках, спеки не двигаются.\n\n"
        f"Лечение: cd ~/projects/{project} && git fetch origin && "
        "git rebase origin/develop && git push origin develop"
    )
    try:
        subprocess.run(
            [str(notify), f"⚠️ lifecycle push не прошёл: {project}", body],
            timeout=30,
            check=False,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001
        pass
