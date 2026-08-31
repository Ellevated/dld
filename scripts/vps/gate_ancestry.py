#!/usr/bin/env python3
"""
Module: gate_ancestry
Role: Branch-ancestry implementation gate (TECH-220) plus `find_implementation`,
      the single entry point all four gate call sites use.

The gate used to decide "this spec is implemented" from the *text* of a commit
subject on origin/develop. Nine of fifteen downstream projects write
`feat(managed): ...`, so 31 of 61 verdicts between 16-30.08 were false
`no_merged_implementation`. Git already knows the answer: autopilot is the only
thing that merges, it merges only from `<type>/<ID>`, only `--ff-only`, and only
after a green run (`.claude/skills/autopilot/finishing.md:51-61`). So
"origin/<type>/<ID> is an ancestor of origin/develop" IS the proof that the
finishing protocol ran.

Uses:
  - subprocess, logging, pathlib, sys: stdlib; every subprocess call is inside a
    function body (same discipline as gate_logic)
  - gate_logic: strip_bookkeeping_paths, find_implementation_commit

Used by:
  - callback_sync._decide_status
  - callback_dispatch._merge_confirmed
  - orchestrator_queue.reconcile_if_implemented / record_dispatch
  - gate-daemon._evaluate_project
  - orchestrator_queue.reconcile (branch_state)
  - callback_sync._decide_status (branch_state)

FF-09 invariant: ZERO imports from callback, lifecycle, db, orchestrator.
gate_logic is the single exception and is itself stdlib-only and import-safe.

Import direction is one-way: gate_ancestry -> gate_logic, never the reverse.
gate_logic must NOT import this module: it sits at 398 of its 400 LOC budget and
a back-import would be a cycle.

The subject fallback calls `gate_logic.find_implementation_commit(...)` as a
module ATTRIBUTE, positionally, with exactly three arguments. Two dozen tests in
files this spec may not edit monkeypatch that attribute; binding the name at
import time or passing keywords turns every one of them into a silent no-op.
"""

import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import gate_logic  # noqa: E402

log = logging.getLogger(__name__)

# L-derived-4: the same map lives as prose twice — the "Type mapping" table in
# `.claude/skills/autopilot/worktree-setup.md` and the bash `case` in
# `autopilot-git.md`. Both copies were missing GROWTH (the bash fell through to
# `task/`) until 2026-08-30; `tests/test_branch_prefix_parity.py` now binds all
# four prose copies to this dict, so a type added here without the prompts fails
# the suite instead of branching work somewhere the gate never looks.
_BRANCH_PREFIX = {
    "FTR": "feature",
    "BUG": "fix",
    "TECH": "tech",
    "ARCH": "arch",
    "GROWTH": "growth",
}

_GIT_TIMEOUT = 15


def _git(project_path: str, *args: str, timeout: int = _GIT_TIMEOUT) -> str | None:
    """Run one git command. Return stripped stdout, or None on ANY failure.

    Fail-closed by construction: every caller treats None as "no evidence",
    which routes to blocked, never to done.
    """
    try:
        r = subprocess.run(
            ["git", "-C", project_path, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("ANCESTRY: git %s failed in %s: %s", args[0], project_path, exc)
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def branch_ref_for(spec_id: str) -> str:
    """`BUG-9` -> `fix/BUG-9`. Raises ValueError on an unknown prefix."""
    prefix = spec_id.split("-")[0].upper()
    if prefix not in _BRANCH_PREFIX:
        raise ValueError(f"no branch prefix for spec id {spec_id!r}")
    return f"{_BRANCH_PREFIX[prefix]}/{spec_id}"


def fetch_branch(project_path: str, spec_id: str, timeout: int = 15) -> bool:
    """Refresh refs/remotes/origin/<type>/<ID>. Best-effort, like fetch_develop.

    Deliberately as narrow as gate_logic.fetch_develop: one exact refspec, never
    `--all`. A branch that does not exist on origin is a normal outcome, not an
    error — the caller falls back to the subject gate.
    """
    try:
        branch = branch_ref_for(spec_id)
    except ValueError:
        return False
    refspec = f"refs/heads/{branch}:refs/remotes/origin/{branch}"
    return _git(project_path, "fetch", "origin", refspec, "--quiet", timeout=timeout) is not None


@dataclass(frozen=True)
class BranchState:
    """What origin knows about <type>/<ID> right now (TECH-221).

    ref     — "fix/BUG-9"; "" when the spec id carries no known prefix
    exists  — refs/remotes/origin/<ref> resolves (call fetch_branch first)
    merged  — <ref> is an ancestor of origin/develop
    ahead   — commits on <ref> that origin/develop does not have
    behind  — commits on origin/develop that <ref> does not have
    """

    ref: str
    exists: bool
    merged: bool
    ahead: int
    behind: int


def branch_state(project_path: str, spec_id: str) -> BranchState:
    """Read-only verdict on origin/<type>/<ID>. Never raises.

    Deliberately does NOT fetch: every caller runs fetch_branch as part of the
    gate a few lines earlier, and a second fetch would double the cost of the
    hot path. Fail-closed by construction — any git failure collapses to
    exists=False, which routes back to the old no_merged_implementation
    verdict rather than to a continuation that has nothing to continue.

    Exact remote ref, never a glob, and never a LOCAL branch: a stale
    refs/heads/<ref> left behind by a swept worktree is precisely the state
    this spec exists to survive, and treating it as evidence would re-create
    the bug (devil DA-8, and the same rule find_merged_branch follows).
    """
    try:
        ref = branch_ref_for(spec_id)
    except ValueError:
        return BranchState(ref="", exists=False, merged=False, ahead=0, behind=0)
    remote = f"refs/remotes/origin/{ref}"
    if not _git(project_path, "rev-parse", "--verify", "--quiet", remote):
        return BranchState(ref=ref, exists=False, merged=False, ahead=0, behind=0)
    # rc 0 = ancestor -> "" (not None); rc 1 / error -> None. Same reading as
    # find_merged_branch: only an explicit rc 0 counts as merged.
    merged = _git(project_path, "merge-base", "--is-ancestor", remote, "origin/develop") is not None
    ahead = behind = 0
    counts = _git(project_path, "rev-list", "--left-right", "--count", f"origin/develop...{remote}")
    if counts:
        parts = counts.split()
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            behind, ahead = int(parts[0]), int(parts[1])
    return BranchState(ref=ref, exists=True, merged=merged, ahead=ahead, behind=behind)


def _base_for_diff(project_path: str, ref: str, tip: str, spec_id: str) -> str | None:
    """Lower bound for "what this branch introduced".

    Two shapes reach us. A `--no-ff` merge leaves develop with commits the branch
    never had, so `merge-base` IS the fork point. A `--ff-only` merge — what
    finishing.md:51-54 actually does, after rebasing develop — replays develop
    onto the branch tip, so `merge-base(ref, origin/develop) == ref` and a diff
    against it is always empty. For that case the spec's own birth commit is the
    usable bound: Spark commits `ai/features/<ID>-*.md` to develop before the
    branch is ever cut, so the oldest commit reachable from the tip that ADDS the
    spec file always sits on the develop side of the fork.

    ponytail: the ff bound is wider than the true fork point — another spec
    landing on develop inside that window and touching one of THIS spec's allowed
    files would count as evidence. Ceiling accepted because a branch literally
    named <type>/<ID> still has to have been merged to get here. Upgrade path: a
    merge trailer recording the fork sha.
    """
    base = _git(project_path, "merge-base", ref, "origin/develop")
    if base is None:
        return None
    if base != tip:
        return base
    birth = _git(
        project_path,
        "log",
        tip,
        "--reverse",
        "--diff-filter=A",
        "--pretty=%H",
        "--",
        f"ai/features/{spec_id}-*.md",
    )
    if not birth:
        log.info(
            "ANCESTRY: %s — ff-merged branch but no spec birth commit; failing closed", spec_id
        )
        return None
    return birth.splitlines()[0].strip()


def find_merged_branch(project_path: str, spec_id: str, allowed_files: list[str]) -> str | None:
    """Tip sha of origin/<type>/<ID> iff that branch is merged into
    origin/develop AND carried at least one non-bookkeeping allowed file.

    Exact ref name, never a glob: ARCH-176 must not match ARCH-176a (devil DA-8).
    """
    if not spec_id or not allowed_files:
        return None
    impl_files = gate_logic.strip_bookkeeping_paths(allowed_files)
    if not impl_files:
        return None
    try:
        branch = branch_ref_for(spec_id)
    except ValueError:
        return None
    ref = f"refs/remotes/origin/{branch}"
    tip = _git(project_path, "rev-parse", "--verify", "--quiet", ref)
    if not tip:
        return None
    # rc 0 = ancestor, rc 1 = not, anything else = error. _git collapses the
    # last two into None, which is exactly the fail-closed reading we want.
    if _git(project_path, "merge-base", "--is-ancestor", ref, "origin/develop") is None:
        return None
    base = _base_for_diff(project_path, ref, tip, spec_id)
    if base is None:
        return None
    changed = _git(project_path, "diff", "--name-only", base, tip)
    if changed is None:
        return None
    # Same normalisation gate_logic.strip_bookkeeping_paths applies (backslash → slash,
    # leading ./ dropped), so the two sides of the intersection are comparable.
    touched = {ln.strip().replace("\\", "/") for ln in changed.splitlines() if ln.strip()}
    wanted = {p.strip().lstrip("./").replace("\\", "/") for p in impl_files}
    if not touched & wanted:
        log.info("ANCESTRY: %s — %s is merged but touched no impl file", spec_id, branch)
        return None
    log.info("ANCESTRY: %s — %s merged into origin/develop at %s", spec_id, branch, tip[:12])
    return tip


def find_implementation(
    project_path: str,
    spec_id: str,
    allowed_files: list[str],
) -> tuple[str | None, str]:
    """THE gate. ("<sha>", "ancestry") | ("<sha>", "subject") | (None, "none").

    Ancestry first — git knows who merged what. The subject regex is the
    deprecated second pass, kept until 30 days of `gate_via` telemetry show it
    never fires; then it and match_subject go in their own TECH.
    """
    sha = find_merged_branch(project_path, spec_id, allowed_files)
    if sha:
        return sha, "ancestry"
    # Module attribute, positional, three args — see the module docstring.
    sha = gate_logic.find_implementation_commit(project_path, spec_id, allowed_files)
    if sha:
        return sha, "subject"
    return None, "none"
