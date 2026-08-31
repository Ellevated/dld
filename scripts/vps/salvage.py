"""
Module: salvage
Role: Preserve autopilot work when a run dies before PHASE 3 can push it anywhere.

      Autopilot commits per task into a worktree branch and pushes exactly once,
      at the very end (autopilot-git.md §4, TECH-085 — one push per spec keeps CI
      cost down). Every abnormal end therefore lands in the same place: N finished
      task commits sitting on a local branch on the VPS, invisible from anywhere
      else, plus whatever the in-flight task had written but not committed.

      Measured 2026-07-26 on dowry-mc FTR-0082: two consecutive 90-minute timeouts,
      575 turns on the second, ~$58 of compute on the first — and nothing on origin
      either time. The work was not wrong, it was merely unreachable.

      This module runs after such a death: it snapshots the dirty working tree onto
      the branch and pushes the branch to origin. One push, on a path that only
      executes when a run has already failed, so TECH-085 is untouched.

Uses:
  - lifecycle: run_git (byte-level git I/O — never text=True, see its docstring)
  - subprocess/tempfile/os/re/pathlib: git plumbing, private index

Used by:
  - claude-runner.py: salvage_run() on non-zero exit and on SIGTERM

Glossary: ai/glossary/orchestrator.md
"""

import logging
import os
import re
import tempfile
from pathlib import Path

from lifecycle import run_git as _git

log = logging.getLogger(__name__)

# Branches that must never receive a salvage commit or a salvage push.
_PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "HEAD"})

_SPEC_ID_RE = re.compile(r"\b((?:FTR|BUG|TECH|ARCH|GROWTH)-\d+)\b")

# Never snapshot lifecycle state. ADR-023/ADR-025 make callback the only writer,
# and plumbing bypasses the pre-commit guard by construction — so the exclusion
# has to live here, in the tool that does the bypassing.
_EXCLUDE_PATHSPEC = ":(exclude)ai/lifecycle"

_GIT_TIMEOUT = 60
_PUSH_TIMEOUT = 180


def spec_id_from_path(spec_path: str) -> str | None:
    """Pull the spec ID out of a spec file path. None if there isn't one."""
    if not spec_path:
        return None
    m = _SPEC_ID_RE.search(Path(spec_path).name)
    return m.group(1) if m else None


def find_worktree(project_dir: str, spec_id: str) -> tuple[str, str] | None:
    """Locate the worktree autopilot created for this spec.

    Returns (worktree_path, branch) or None. Matches on the worktree directory
    name (autopilot names it after the spec ID) and, failing that, on a branch
    ending in the spec ID — the naming in autopilot-git.md §1 maps FTR-0082 to
    both `.worktrees/FTR-0082` and `feature/FTR-0082`.
    """
    r = _git(["git", "worktree", "list", "--porcelain"], cwd=project_dir, timeout=_GIT_TIMEOUT)
    if r.returncode != 0:
        log.warning("salvage: worktree list failed in %s: %s", project_dir, r.stderr.strip())
        return None

    path = ""
    branch = ""
    by_name: tuple[str, str] | None = None
    by_branch: tuple[str, str] | None = None
    for line in r.stdout.split("\n") + [""]:  # trailing blank flushes the last record
        if line.startswith("worktree "):
            path, branch = line[len("worktree ") :].strip(), ""
        elif line.startswith("branch "):
            branch = line[len("branch ") :].strip().replace("refs/heads/", "")
        elif not line.strip() and path:
            if Path(path).name == spec_id:
                by_name = by_name or (path, branch)
            elif branch.endswith(f"/{spec_id}"):
                by_branch = by_branch or (path, branch)
            path, branch = "", ""

    return by_name or by_branch


def _snapshot_dirty_tree(worktree: str, branch: str, message: str) -> str | None:
    """Commit the working tree onto `branch` via plumbing. None if it was clean.

    Plumbing, not `git commit`, for two reasons that both matter here:

    1. A salvage that can fail is not a salvage. `git commit` runs pre-commit
       hooks, and this code path exists precisely for runs that died mid-task —
       whose tree is likely to be exactly what a linter rejects.
    2. The default index and the working tree are left alone until the ref has
       actually moved, so a failure anywhere leaves no half-applied state.

    `ai/lifecycle/` is excluded (see _EXCLUDE_PATHSPEC).
    """
    head = _git(["git", "rev-parse", "HEAD"], cwd=worktree, timeout=_GIT_TIMEOUT)
    if head.returncode != 0:
        raise RuntimeError(f"rev-parse HEAD: {head.stderr.strip()}")
    head_sha = head.stdout.strip()

    fd, index_path = tempfile.mkstemp(prefix="salvage-index-")
    os.close(fd)
    os.unlink(index_path)  # git wants to create it itself
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = index_path
    # Identity: make the snapshot obviously machine-made in `git log`.
    env.setdefault("GIT_AUTHOR_NAME", "dld-salvage")
    env.setdefault("GIT_AUTHOR_EMAIL", "salvage@dld.local")
    env["GIT_COMMITTER_NAME"] = env["GIT_AUTHOR_NAME"]
    env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]

    try:
        r = _git(["git", "read-tree", head_sha], cwd=worktree, env=env, timeout=_GIT_TIMEOUT)
        if r.returncode != 0:
            raise RuntimeError(f"read-tree: {r.stderr.strip()}")

        r = _git(
            ["git", "add", "-A", "--", ".", _EXCLUDE_PATHSPEC],
            cwd=worktree,
            env=env,
            timeout=_GIT_TIMEOUT,
        )
        if r.returncode != 0:
            raise RuntimeError(f"add: {r.stderr.strip()}")

        r = _git(["git", "write-tree"], cwd=worktree, env=env, timeout=_GIT_TIMEOUT)
        if r.returncode != 0:
            raise RuntimeError(f"write-tree: {r.stderr.strip()}")
        tree = r.stdout.strip()

        head_tree = _git(
            ["git", "rev-parse", f"{head_sha}^{{tree}}"], cwd=worktree, timeout=_GIT_TIMEOUT
        ).stdout.strip()
        if tree == head_tree:
            return None  # nothing uncommitted worth keeping

        r = _git(
            ["git", "commit-tree", tree, "-p", head_sha, "-m", message],
            cwd=worktree,
            env=env,
            timeout=_GIT_TIMEOUT,
        )
        if r.returncode != 0:
            raise RuntimeError(f"commit-tree: {r.stderr.strip()}")
        new_sha = r.stdout.strip()

        # CAS: refuse to move the branch if anything else advanced it meanwhile.
        r = _git(
            ["git", "update-ref", f"refs/heads/{branch}", new_sha, head_sha],
            cwd=worktree,
            timeout=_GIT_TIMEOUT,
        )
        if r.returncode != 0:
            raise RuntimeError(f"update-ref: {r.stderr.strip()}")

        # The branch moved under a private index, so the default one is now stale
        # against the new HEAD — the same trap TECH-194 Layer D hit in lifecycle.
        # `reset --mixed` rewrites the index from HEAD and leaves files untouched.
        _git(["git", "reset", "--mixed", "HEAD"], cwd=worktree, timeout=_GIT_TIMEOUT)
        return new_sha
    finally:
        try:
            os.unlink(index_path)
        except OSError:
            pass


def salvage_run(project_dir: str, spec_id: str, reason: str) -> dict:
    """Snapshot and push whatever a dead autopilot run left in its worktree.

    Returns a telemetry dict; never raises. `pushed` is the field that matters —
    it is the difference between work that survives the run and work that does not.
    """
    info: dict = {
        "attempted": True,
        "reason": reason,
        "spec_id": spec_id,
        "worktree": None,
        "branch": None,
        "snapshot": None,
        "commits_ahead": 0,
        "pushed": False,
        "error": None,
    }

    found = find_worktree(project_dir, spec_id)
    if not found:
        info["error"] = "no_worktree"
        return info
    worktree, branch = found
    info["worktree"], info["branch"] = worktree, branch

    if not branch or branch in _PROTECTED_BRANCHES:
        info["error"] = f"refusing to salvage protected branch {branch!r}"
        return info

    try:
        info["snapshot"] = _snapshot_dirty_tree(
            worktree, branch, f"wip({spec_id}): salvaged after {reason} — not reviewed, not tested"
        )
    except Exception as e:  # ADR-004: salvage must never become a second failure
        info["error"] = f"snapshot failed: {e}"
        log.warning("salvage: snapshot failed for %s: %s", spec_id, e)

    r = _git(
        ["git", "rev-list", "--count", "origin/develop..HEAD"],
        cwd=worktree,
        timeout=_GIT_TIMEOUT,
    )
    if r.returncode == 0 and r.stdout.strip().isdigit():
        info["commits_ahead"] = int(r.stdout.strip())

    if info["commits_ahead"] == 0:
        info["error"] = info["error"] or "nothing_to_salvage"
        return info

    push = _git(["git", "push", "-u", "origin", branch], cwd=worktree, timeout=_PUSH_TIMEOUT)
    if push.returncode == 0:
        info["pushed"] = True
        log.info(
            "salvage: pushed %s (%d commit(s)) after %s", branch, info["commits_ahead"], reason
        )
    else:
        info["error"] = f"push failed: {push.stderr.strip()[:300]}"
        log.warning("salvage: push failed for %s: %s", branch, push.stderr.strip()[:300])

    return info
