# Pattern Research — Automatic Git Worktree Cleanup

## Context

The autopilot pipeline creates git worktrees for isolation (`.worktrees/{ID}/`), then at PHASE 3 step 9 the LLM executes cleanup commands. Problem: if the agent crashes, compacts, or exits early before reaching step 9, the worktree and branch are orphaned. The external orchestrator (`autopilot-loop.sh`) has no cleanup mechanism — it just launches Claude and moves on.

Current failure vector: `autopilot-loop.sh` line 119 → `claude --print "autopilot $SPEC_ID"` exits → loop checks `$STATUS` → if `done` logs success. No cleanup verification. If Claude completed step 8 (merge) but crashed before step 9 (cleanup), the worktree stays forever.

Two cleanup targets:
1. Local `.worktrees/{ID}/` directories + local branches
2. Remote orphan branches (`feature/FTR-*`, `fix/BUG-*`, etc.)

---

## Approach 1: Post-Run Cleanup in autopilot-loop.sh

**Source:** [Loop Your Coding Agent for Hours — Ralph Loop pattern](https://www.sean-weldon.com/blog/2026-01-05-loop-your-coding-agent-for-hours) + [Deterministic AI Orchestration — Praetorian Platform](https://securityboulevard.com/2026/02/deterministic-ai-orchestration-a-platform-architecture-for-autonomous-development/)

### Description

After each `claude --print "autopilot $SPEC_ID"` call returns, `autopilot-loop.sh` deterministically runs a cleanup function that derives the expected worktree path and branch name from `$SPEC_ID`, checks for uncommitted changes, and removes if safe. The LLM never touches cleanup — the bash loop does it unconditionally after every iteration.

This is the "deterministic wrapper" pattern described in the Praetorian paper: "treating the LLM as a nondeterministic kernel process wrapped in a deterministic shell."

### Pros

- Runs regardless of LLM state (crash, compact, early exit — doesn't matter)
- Zero new infrastructure — adds ~30 lines to existing `autopilot-loop.sh`
- Cleanup is co-located with the failure point (same script, same loop iteration)
- SPEC_ID → branch name mapping is deterministic (already defined in `worktree-setup.md`)
- Handles the most common failure mode: agent finishes work but crashes before cleanup
- Safe by default: skips if worktree has uncommitted changes (no data loss)

### Cons

- Only cleans up the current iteration's worktree — does not catch orphans from prior crashes
- If the LLM never reached the merge step, cleanup here would delete unmerged work
- Requires checking merge status before deletion (not just uncommitted changes)
- Branch name derivation must stay in sync with `worktree-setup.md` mapping rules

### Complexity

**Estimate:** Easy — 1-2 hours

**Why:** The mapping from SPEC_ID to branch/path is already defined in `worktree-setup.md`. Adding a `cleanup_worktree()` function to `autopilot-loop.sh` after line 121 (after Claude exits) is a self-contained change. Safety check for uncommitted changes is a one-liner (`git diff-index --quiet HEAD`). Merge check adds ~5 lines.

### Example Source

```bash
# In autopilot-loop.sh, after line 121 (EXIT_CODE captured):

cleanup_worktree() {
  local spec_id="$1"
  local base_dir="${PROJECT_DIR:-.}"

  # Derive branch name (mirrors worktree-setup.md mapping)
  local prefix type
  prefix=$(echo "$spec_id" | grep -oE '^(FTR|BUG|TECH|ARCH)')
  case "$prefix" in
    FTR)  type="feature" ;;
    BUG)  type="fix"     ;;
    TECH) type="tech"    ;;
    ARCH) type="arch"    ;;
    *)    return 0        ;;
  esac

  local id_lower="${spec_id,,}"  # lowercase: FTR-123 → ftr-123
  local branch="${type}/${id_lower}"
  local wt_path="${base_dir}/.worktrees/${spec_id}"

  [[ -d "$wt_path" ]] || return 0  # Already clean

  # Safety: skip if uncommitted changes exist
  if ! git -C "$wt_path" diff-index --quiet HEAD -- 2>/dev/null; then
    echo "WARN: Worktree $spec_id has uncommitted changes — skipping cleanup"
    return 0
  fi

  # Safety: only delete if branch is merged into develop
  if ! git branch --merged develop 2>/dev/null | grep -qF "$branch"; then
    echo "WARN: Branch $branch not merged into develop — skipping cleanup"
    return 0
  fi

  git worktree remove "$wt_path" --force 2>/dev/null || true
  git branch -d "$branch" 2>/dev/null || true
  git worktree prune 2>/dev/null || true
  echo "Cleaned up worktree: $spec_id"
}

# Call after claude exits:
cleanup_worktree "$SPEC_ID"
```

---

## Approach 2: Standalone Cleanup Script (cron / manual / on-demand)

**Source:** [Bulk cleaning stale git worktrees and branches — brtkwr.com](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/) + [Git branch cleanup aliases for zsh — worktree-safe](https://gist.github.com/tomholford/0aa4cdb1340a9b5411ed6eaadabfcf37) + [Git Worktree Best Practices — ChristopherA](https://gist.github.com/ChristopherA/4643b2f5e024578606b9cd5d2e6815cc)

### Description

A standalone script (`scripts/cleanup-worktrees.sh`) scans the entire `.worktrees/` directory, uses `git worktree list --porcelain` to enumerate all linked worktrees, checks each branch against `git branch --merged develop`, verifies no uncommitted changes, and removes safe candidates. Also prunes remote orphan branches via `git push origin --delete`. Invoked on-demand, by cron, or at the start of each `autopilot-loop.sh` session.

This is the "garbage collector" pattern: a catch-all sweep that handles orphans from any source — crashed agents, manual abortions, stale experiments, partial runs.

### Pros

- Catches ALL orphans, not just the current run (historical debt from prior crashes)
- Also handles remote branch cleanup (Approach 1 does not)
- Can be run safely at any time (idempotent, read-before-delete)
- Can be integrated into multiple trigger points: cron, loop start, CI, git alias
- The `git branch --merged develop` check is the authoritative safety gate — Git itself decides
- Handles edge cases: squash merges (via `[gone]` detection), corrupted worktree metadata

### Cons

- Runs after-the-fact, not immediately after each iteration
- Remote branch deletion requires `git push --delete` — needs push access and network
- `git branch --merged` check does not detect squash-merged branches (need `[gone]` check too)
- Risk of false negatives: a worktree with unrelated uncommitted changes blocks otherwise-safe cleanup
- Cron-based means orphans persist for up to N minutes/hours before cleanup

### Complexity

**Estimate:** Medium — 3-5 hours

**Why:** The core logic is ~50 lines of bash. The complexity is in edge cases: handling squash merges (need `git fetch --prune` + `[gone]` detection), remote branch cleanup (need to filter protected branches), worktree metadata corruption (need fallback `rm -rf`). A dry-run mode should be included. Testing against real orphan scenarios takes most of the time.

### Example Source

Based on the brtkwr.com pattern + tomholford aliases:

```bash
#!/usr/bin/env bash
# cleanup-worktrees.sh — sweep orphaned worktrees and branches
set -euo pipefail

BASE_DIR="${PROJECT_DIR:-.}"
DRY_RUN="${DRY_RUN:-false}"
PROTECTED="main|develop|master"

cd "$BASE_DIR"

# Sync remote state
git fetch --prune --quiet

# 1. Remove worktrees whose branch is merged into develop
while IFS= read -r line; do
  [[ "$line" =~ ^worktree\ (.+)$ ]] && wt_path="${BASH_REMATCH[1]}" && continue
  [[ "$line" =~ ^branch\ refs/heads/(.+)$ ]] && branch="${BASH_REMATCH[1]}" || continue

  [[ -z "${wt_path:-}" ]] && continue
  [[ "$wt_path" == "$BASE_DIR" ]] && continue  # Skip main worktree

  # Safety: skip protected branches
  echo "$branch" | grep -qE "^($PROTECTED)$" && continue

  # Safety: skip if uncommitted changes
  if ! git -C "$wt_path" diff-index --quiet HEAD -- 2>/dev/null; then
    echo "SKIP (dirty): $branch"
    continue
  fi

  # Check merged
  if git branch --merged develop | grep -qF "$branch"; then
    echo "${DRY_RUN:+[DRY-RUN] }Removing: $wt_path ($branch)"
    [[ "$DRY_RUN" == "false" ]] && {
      git worktree remove "$wt_path" --force 2>/dev/null || rm -rf "$wt_path"
      git branch -d "$branch" 2>/dev/null || true
    }
  fi
done < <(git worktree list --porcelain)

git worktree prune

# 2. Delete local branches tracking gone remotes (squash-merge coverage)
git branch -vv | grep '\[gone\]' | grep -Ev "^\s*\*|$PROTECTED" | awk '{print $1}' | while read -r branch; do
  echo "${DRY_RUN:+[DRY-RUN] }Deleting gone branch: $branch"
  [[ "$DRY_RUN" == "false" ]] && git branch -D "$branch" 2>/dev/null || true
done

# 3. Remote orphan branches (autopilot naming pattern)
git branch -r --merged develop | grep -E 'origin/(feature|fix|tech|arch)/[A-Z]+-[0-9]+' \
  | sed 's|origin/||' | while read -r branch; do
  echo "${DRY_RUN:+[DRY-RUN] }Deleting remote: $branch"
  [[ "$DRY_RUN" == "false" ]] && git push origin --delete "$branch" 2>/dev/null || true
done
```

---

## Approach 3: git post-merge Hook

**Source:** [git hooks documentation — git-scm.com](https://git-scm.com/docs/githooks) + [Using a post-merge git hook to clean up old branches — Liquid Light](https://www.liquidlight.co.uk/blog/using-a-post-merge-git-hook-to-clean-up-old-branches/)

### Description

Install a `.git/hooks/post-merge` script that runs automatically after every `git merge`. After the merge of a feature branch into `develop`, the hook detects the just-merged branch name via `git reflog`, finds the associated worktree path, and removes it. No external orchestrator changes needed — the hook fires as a side-effect of the merge itself.

### Pros

- Fires automatically at the exact right moment — immediately after merge
- No changes to `autopilot-loop.sh` or any skill files
- Works for both manual and automated merges
- Clean separation of concerns: the merge command implies cleanup, no extra calls

### Cons

- **Critical flaw: `--ff-only` does NOT trigger `post-merge`** — the autopilot uses `git merge --ff-only`, which is a fast-forward and does not create a merge commit. Per git docs, `post-merge` fires only for `git merge` (creates a merge commit) and `git pull` (which calls merge). Fast-forward merges are commits-not-merges in git's model — confirmed in the git-scm docs and SO #32871655
- Hooks are not committed to the repo (`.git/hooks/` is gitignored) — not portable across machines, VPS, fresh clones
- Installing hooks requires manual setup per clone — fragile for multi-agent VPS deployments
- `post-merge` receives only a "squash flag" parameter, not the branch name — requires reflog parsing (fragile)
- Claude Code hooks are PreToolUse/PostToolUse, not git hooks — they see raw bash commands but cannot reliably detect a `git merge` within a multi-step LLM session

### Complexity

**Estimate:** Hard — if trying to make it work reliably: 6-8 hours

**Why:** The `--ff-only` blocker alone disqualifies this approach for the current pipeline without switching merge strategy. If the merge strategy were changed to `--no-ff`, the hook would work but would pollute git history with merge commits. The portability problem (hooks not in repo) adds operational complexity for VPS deployment. Net result: more fragile than the alternatives, not less.

### Example Source

For documentation purposes (not recommended given the `--ff-only` constraint):

```bash
# .git/hooks/post-merge — NOT triggered by --ff-only!
#!/bin/bash
# This only fires on true merge commits, not fast-forwards.

reflog_msg=$(git reflog -1)
merged_branch=$(echo "$reflog_msg" | grep -oE '(feature|fix|tech|arch)/[a-z]+-[0-9]+' | head -1)
[[ -z "$merged_branch" ]] && exit 0

# Derive worktree path from branch name (e.g., feature/ftr-123 → .worktrees/FTR-123)
id=$(echo "$merged_branch" | grep -oE '[A-Z]+-[0-9]+')
wt_path=".worktrees/${id}"

[[ -d "$wt_path" ]] || exit 0

if git -C "$wt_path" diff-index --quiet HEAD -- 2>/dev/null; then
  git worktree remove "$wt_path" --force 2>/dev/null
  git branch -d "$merged_branch" 2>/dev/null
fi
```

---

## Comparison Matrix

| Criteria | Approach 1: Post-Run in Loop | Approach 2: Standalone Script | Approach 3: git Hook |
|----------|------------------------------|-------------------------------|----------------------|
| Determinism | High — always runs after Claude exits | Medium — depends on trigger (cron lag) | Low — blocked by `--ff-only` |
| Safety (no data loss) | High — checks uncommitted + merged | High — same checks, more edge cases | Medium — reflog parsing fragile |
| Orphan coverage | Current run only | All orphans (historical + current) | Per-merge only |
| Remote branch cleanup | No (local only) | Yes (full remote pruning) | No |
| Infrastructure needed | None — modifies existing script | New script + optional cron | Hook install per clone |
| Portability (VPS, fresh clones) | High — part of tracked script | High — tracked script | Low — hooks not in repo |
| Implementation effort | Low (30 lines) | Medium (80 lines + edge cases) | High (fails for `--ff-only`) |
| Failure mode | Silent skip if unsafe | Same, plus dry-run mode | Silently does nothing (`--ff-only`) |
| Testability | Easy (local run) | Easy (dry-run flag) | Hard (must change merge strategy) |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 1 + Approach 2 in combination

### Rationale

Neither approach alone solves the full problem. The right answer is a two-layer defense:

**Layer 1 — Approach 1 (immediate, inline):** Add a `cleanup_worktree()` function to `autopilot-loop.sh` that runs after every `claude` invocation. This is the "fail-safe" layer — it catches the current iteration's orphan immediately, regardless of how or why Claude exited. Cost: ~30 lines in an already-tracked file. Zero new infrastructure.

**Layer 2 — Approach 2 (periodic sweep):** Add `scripts/cleanup-worktrees.sh` invoked at the start of each `autopilot-loop.sh` session (before the main loop). This sweeps historical orphans from prior crashes and also handles remote branches. The session-start trigger is better than cron because it runs in the right repo context and at the right frequency (once per overnight run).

Approach 3 is eliminated by the `--ff-only` constraint in `finishing.md` line 48. The autopilot explicitly uses `git merge --ff-only` — fast-forward merges do not trigger `post-merge`. Making it work would require either switching to `--no-ff` (pollutes history) or adding a separate `post-checkout` hook (fragile). The portability problem (hooks not tracked in repo) is a secondary disqualifier for the VPS deployment model.

Key factors:

1. **Fail-point proximity** — Approach 1 runs at the exact failure point. If Claude crashes during PHASE 3, cleanup fires 2 seconds later when the loop continues. No cron lag.
2. **Historical debt** — Approach 2 handles worktrees orphaned by prior runs (before this fix was deployed). Without it, existing orphans accumulate until someone notices.
3. **Zero new dependencies** — Both approaches are pure bash in tracked scripts. No hooks to install per clone, no cron to configure separately.

### Trade-off Accepted

By not using Approach 3 (git hook), we lose the elegance of "merge implies cleanup." The hook approach would be the cleanest mental model if the pipeline used `--no-ff` merges. We're accepting a slightly less automatic trigger in exchange for reliability under `--ff-only` and portability across machines.

By not running the standalone cleanup script after every iteration (only at session start), we accept a window where orphans from the current session persist until the next session starts. This is acceptable — orphans are storage waste, not data loss.

---

## Research Sources

- [Bulk cleaning stale git worktrees and branches — brtkwr.com (Mar 2026)](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/) — worktree prune + `[gone]` branch detection pattern
- [Git branch cleanup aliases for zsh — tomholford](https://gist.github.com/tomholford/0aa4cdb1340a9b5411ed6eaadabfcf37) — worktree-safe branch deletion, `cleanmerged` + `cleangone` + `cleansquashed` triple pattern
- [githooks documentation — git-scm.com](https://git-scm.com/docs/githooks) — `post-merge` fires only on `git merge` (true merge commit), not on fast-forward
- [Using a post-merge hook to clean up branches — Liquid Light](https://www.liquidlight.co.uk/blog/using-a-post-merge-git-hook-to-clean-up-old-branches/) — post-merge hook implementation reference
- [Deterministic AI Orchestration — Praetorian (Feb 2026)](https://securityboulevard.com/2026/02/deterministic-ai-orchestration-a-platform-architecture-for-autonomous-development/) — "LLM as nondeterministic kernel wrapped in deterministic shell" pattern
- [Loop Your Coding Agent for Hours — Sean Weldon](https://www.sean-weldon.com/blog/2026-01-05-loop-your-coding-agent-for-hours) — Ralph Loop: bash for-loop as deterministic wrapper around LLM calls, state via files not context
- [How to Delete All Git Branches That Have Been Merged Safely — TheLinuxCode (Feb 2026)](https://thelinuxcode.com/how-to-delete-all-git-branches-that-have-been-merged-safely-locally-and-remotely/) — `git branch --merged` vs `[gone]` distinction for squash merges
- [Parallel AI Coding with Git Worktrees and Custom Claude Code Commands — agentinterviews.com](https://docs.agentinterviews.com/blog/parallel-ai-coding-with-gitworktrees/) — real-world AI agent worktree lifecycle including cleanup patterns
