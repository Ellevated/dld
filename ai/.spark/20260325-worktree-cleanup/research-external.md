# External Research — Automatic Git Worktree Cleanup After Merge

## Best Practices

### 1. Never Trust the LLM to Execute Cleanup — Enforce It in the Shell Layer

**Source:** [Worktree cleanup: three remaining data-loss paths after v2.1.76-77 fixes](https://github.com/anthropics/claude-code/issues/35862) (Anthropic/claude-code GitHub issue, March 2026)

**Summary:** Claude Code's own internal worktree cleanup (`cleanupStaleAgentWorktrees`) had at least three bugs as of v2.1.78, including using `git status --porcelain -uno` which hides untracked files, using wrong baselines for `rev-list`, and missing agent-owned worktrees entirely. The fix that worked was pushing the branch before reporting completion so `rev-list HEAD --not --remotes` always detects the work — i.e., ensuring deterministic state before cleanup.

**Why relevant:** Confirms that even Anthropic's own LLM-driven cleanup code gets it wrong repeatedly. The pattern that reliably works: make cleanup deterministic and run it from outside the LLM session, not inside it. The orchestrator shell (`autopilot-loop.sh`) is exactly the right layer.

---

### 2. Two-Layer Cleanup: Worktree Directories First, Then Branch Refs

**Source:** [Bulk cleaning stale git worktrees and branches](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/) (brtkwr.com, March 2026)

**Summary:** Worktrees and branches are independent objects that accumulate independently. One author ended up with 256 worktrees consuming 28 GB and 700+ stale branches. The correct cleanup sequence is: (1) `git fetch --prune` to sync remote state, (2) detect stale worktrees by checking if `refs/remotes/origin/<branch>` still exists, (3) remove worktree with `git worktree remove` (fallback to `--force` if needed), (4) prune orphaned local branch refs separately via `git branch -vv | grep ': gone]'`.

**Why relevant:** Our pipeline creates both worktree dirs and branches. The cleanup script must handle both objects separately in the correct order — removing the worktree directory first, then the branch ref.

---

### 3. Safe Removal Requires Three Checks Before Destroying Anything

**Source:** [cleanup-dangling-worktrees skill (bacchus-labs/wrangler)](https://lobehub.com/skills/bacchus-labs-wrangler-cleanup-dangling-worktrees) (LobeHub Marketplace, March 2026) + [Worktree cleanup data-loss paths](https://github.com/anthropics/claude-code/issues/35862)

**Summary:** The production-safe worktree cleanup pattern verifies three conditions before removal: (a) no uncommitted changes (`git status --porcelain` returns empty), (b) no unpushed commits (`git log @{upstream}..HEAD` returns empty, or `git rev-list HEAD --not --remotes --count` returns 0), (c) the associated PR/branch is confirmed merged (check via `gh pr list --state merged` or `git branch --merged develop`). A worktree with an open or closed-but-unmerged PR is preserved.

**Why relevant:** Our automation must not silently destroy work-in-progress. The three-check gate is the minimum safe bar. Note: `git status --porcelain -uno` (used by Claude Code's buggy version) hides untracked files — always use plain `git status --porcelain` or add `-uall`.

---

### 4. `git worktree prune` Handles Corrupted Metadata — Always Run It Last

**Source:** [How to Configure Git Worktrees](https://oneuptime.com/blog/post/2026-01-24-git-worktrees/view) (OneUptime, Jan 2026) + [Git Worktrees: The Complete Guide for 2026](https://devtoolbox.dedyn.io/blog/git-worktrees-complete-guide) (DevToolbox, Feb 2026)

**Summary:** If a worktree directory is deleted manually (e.g., `rm -rf`) rather than through `git worktree remove`, the git metadata entry persists under `.git/worktrees/`. Running `git worktree prune` removes these orphaned metadata entries. It should always be the last step after any batch removal operation. Use `--dry-run` first to preview. Use `git worktree repair` if metadata has become inconsistent.

**Why relevant:** In a pipeline where agents crash or get killed mid-run, the worktree directory may be gone but the `.git/worktrees/` entry remains. The cleanup script must run `git worktree prune` unconditionally as its final step to keep the repo in a consistent state.

---

### 5. Post-Merge Cleanup Belongs in the Orchestrator, Not a Git Hook

**Source:** [The Complete Guide to Git Worktrees with Claude Code](https://notes.muthu.co/2026/02/the-complete-guide-to-git-worktrees-with-claude-code/) (Feb 2026) + [Feature: Hook control over worktree removal](https://github.com/anthropics/claude-code/issues/31969) (Anthropic/claude-code, March 2026)

**Summary:** The Anthropic-endorsed pattern for multi-session agent workflows is: orchestrator creates worktree → agent works → orchestrator cleans up. Claude Code's `WorktreeRemove` hooks are currently informational (cannot block removal), and the "keep or remove?" prompt fires unreliably on session exit. A plugin author explicitly requested hook-level control over removal for exactly this reason. The working alternative: post-run cleanup in the calling shell layer.

**Why relevant:** Validates our architecture: `autopilot-loop.sh` (the caller) is the right place for cleanup, not inside the Claude session or a git hook. Git hooks run synchronously on git operations and cannot observe "did the merge happen upstream" — the orchestrator can.

---

## Libraries/Tools

| Library/Tool | Version | Pros | Cons | Use Case | Source |
|---|---|---|---|---|---|
| `git worktree remove` (native) | Git 2.5+ | Zero dependencies, exact semantics, safe by default (refuses dirty) | No batch mode, no branch cleanup | Single worktree removal in scripts | [Git docs](https://git-scm.com/docs/git-worktree) |
| `git worktree prune` (native) | Git 2.5+ | Cleans orphaned metadata, `--dry-run` safe | Does not remove directories, only metadata | Always-last cleanup step | [Git docs](https://git-scm.com/docs/git-worktree) |
| `grove` CLI | Latest (Go, 2026) | `grove prune --dry-run`, `--base develop`, `--older-than 30d`, handles dirty worktrees, cross-platform | External binary, overkill for CI script | Developer workstations, interactive use | [GitHub: captainsafia/grove](https://github.com/captainsafia/grove) |
| `git-wt` (ahmedelgabri) | Latest (Shell, Feb 2026) | Bare-repo pattern, `destroy` removes local+remote branch, dry-run, fzf multi-select | Interactive-first, not CI-friendly | Developer machines with bare repo setup | [GitHub: ahmedelgabri/git-wt](https://github.com/ahmedelgabri/git-wt) |
| `wt` (timvw) | Latest (Go, Feb 2026) | `wt cleanup` removes worktrees for merged branches, configurable strategies, lifecycle hooks | External binary, Go required | Developer workflow tool | [timvw.be](https://timvw.be/2026/02/13/wt-a-better-way-to-manage-git-worktrees/) |
| `stale-branch-action` (int128) | v1.33.0 (Mar 2026) | GitHub Actions native, `--dry-run`, expiration-days, exclude patterns | Requires GitHub Actions, remote branches only | CI/CD scheduled branch cleanup | [GitHub: int128/stale-branch-action](https://github.com/int128/stale-branch-action) |
| Custom bash script | N/A | No dependencies, fully controllable, embeddable in `autopilot-loop.sh` | Must be written and maintained | In-pipeline cleanup, cron job | This research |

**Recommendation:** For the autopilot pipeline, use native git commands (`git worktree remove`, `git worktree prune`, `git branch -d`) in a custom bash script. No external tools. External tools like `grove` are useful for developer workstations but add binary dependencies to the CI/VPS layer. For cron-based cleanup of accumulated worktrees, a standalone bash script based on the brtkwr.com pattern is the right choice.

---

## Production Patterns

### Pattern 1: Remote-Gone Detection (the `': gone]'` pattern)

**Source:** [Bulk cleaning stale git worktrees and branches](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/) (Bharat Kunwar, March 2026) — author ran 256 worktrees across 40+ repos for AI agent workflows

**Description:** After `git fetch --prune`, branches whose remote tracking ref was deleted show `[origin/branch: gone]` in `git branch -vv`. This is the canonical signal that a branch has been merged and deleted upstream. The cleanup sequence:

```bash
# Step 1: sync remote state
git fetch --prune --quiet

# Step 2: find stale worktrees (remote branch gone)
git worktree list --porcelain | grep '^worktree' | awk '{print $2}' | while read wt_path; do
  branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null) || continue
  git rev-parse --verify "refs/remotes/origin/$branch" &>/dev/null && continue
  # Remote branch is gone — safe to remove
  git worktree remove "$wt_path" 2>/dev/null || git worktree remove --force "$wt_path"
done

# Step 3: cleanup orphaned metadata
git worktree prune

# Step 4: cleanup local branch refs for gone remotes
git branch -vv | grep ': gone]' | awk '{print $1}' | xargs -r git branch -D
```

**Real-world use:** Used by the author across 40+ repos with 256 worktrees (AI agent workflows). Also matches the bacchus-labs/wrangler skill used in production agent setups.

**Fits us:** Yes — our worktrees are created with tracking branches pushed to `origin`. After merge to `develop`, the feature branch gets deleted. The `': gone]'` detection is exactly the right signal.

---

### Pattern 2: Pre-Removal Safety Gate (Three-Check Pattern)

**Source:** [bacchus-labs/wrangler cleanup-dangling-worktrees](https://lobehub.com/skills/bacchus-labs-wrangler-cleanup-dangling-worktrees) + [Claude Code issue #35862](https://github.com/anthropics/claude-code/issues/35862)

**Description:** Before removing any worktree, run three checks in sequence and abort on any failure:

```bash
is_safe_to_remove() {
  local wt_path="$1"

  # Check 1: no uncommitted changes (use -uall to catch untracked files too)
  if [ -n "$(git -C "$wt_path" status --porcelain 2>/dev/null)" ]; then
    echo "SKIP: $wt_path has uncommitted changes"
    return 1
  fi

  # Check 2: no unpushed commits
  if git -C "$wt_path" rev-parse --abbrev-ref --symbolic-full-name '@{u}' &>/dev/null; then
    local unpushed
    unpushed=$(git -C "$wt_path" rev-list HEAD --not --remotes --count 2>/dev/null || echo "1")
    if [ "$unpushed" -gt 0 ]; then
      echo "SKIP: $wt_path has $unpushed unpushed commits"
      return 1
    fi
  fi

  # Check 3: branch is merged into target (develop)
  local branch
  branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null)
  if ! git branch --merged develop 2>/dev/null | grep -q "^\s*${branch}$"; then
    echo "SKIP: $wt_path branch '$branch' not yet merged into develop"
    return 1
  fi

  return 0
}
```

**Real-world use:** bacchus-labs/wrangler uses this pattern for CI workspace pruning. Claude Code v2.1.76-77 added `rev-list` checking after the simpler `git status --porcelain` check missed committed-but-not-pushed work (data-loss bug).

**Fits us:** Yes — mandatory. Prevents destroying agent work that was committed but not yet pushed, or merged locally but upstream hasn't been updated yet.

---

### Pattern 3: Orchestrator Post-Run Cleanup with State File Guard

**Source:** [Graceful Shutdown Patterns for Long-Lived Services](https://zylos.ai/research/2026-02-25-graceful-shutdown-long-lived-services) (Zylos Research, Feb 2026) + [ADR-011: Enforcement as Code](/.claude/rules/architecture.md)

**Description:** The orchestrator writes a state file (e.g., `task-state.json`) before launching the agent. After the agent exits (for any reason — success, crash, timeout, SIGTERM), the orchestrator's cleanup runs in the `finally`/trap block. State file provides the worktree path and branch name regardless of agent memory:

```bash
# In autopilot-loop.sh
WORKTREE_PATH="..."
BRANCH_NAME="..."
STATE_FILE="$WORKTREE_PATH/.worktree-state.json"

# Write state before agent starts
echo "{\"branch\":\"$BRANCH_NAME\",\"created\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > "$STATE_FILE"

# Cleanup on any exit (trap covers crash/timeout/signal)
cleanup() {
  if is_safe_to_remove "$WORKTREE_PATH"; then
    git worktree remove "$WORKTREE_PATH" 2>/dev/null || true
    git branch -d "$BRANCH_NAME" 2>/dev/null || true
    git push origin --delete "$BRANCH_NAME" 2>/dev/null || true
    git worktree prune 2>/dev/null || true
  else
    echo "WARNING: Skipped cleanup for $WORKTREE_PATH — not safe to remove"
  fi
}
trap cleanup EXIT
```

**Real-world use:** Standard pattern for long-lived service teardown (PM2 `kill_timeout`, nginx `worker_shutdown_timeout`). Applied to agent pipelines by LangGraph (built-in checkpointing) and CrewAI (`output_file` pattern — ADR-007/008/010 in this project).

**Fits us:** Yes — this is the exact architecture we need. `trap cleanup EXIT` in `autopilot-loop.sh` runs cleanup regardless of how the agent exits. State file provides branch/path info without relying on LLM memory.

---

### Pattern 4: Cron-Based Sweeper for Accumulated Stale Worktrees

**Source:** [Bulk cleaning stale git worktrees and branches](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/) + [grove prune](https://github.com/captainsafia/grove) + GitHub Actions `stale-branch-action`

**Description:** Even with post-run cleanup in the orchestrator, worktrees can accumulate from crashes before state files were introduced, or from manual interruptions. A standalone sweeper script runs on cron (daily or per-deploy) to find and remove any worktrees whose remote branch is gone or merged:

```bash
#!/usr/bin/env bash
# git-worktree-sweep.sh — standalone sweeper, safe to run on cron
set -euo pipefail

REPO_DIR="${1:-$(git rev-parse --show-toplevel)}"
TARGET_BRANCH="${2:-develop}"
DRY_RUN="${DRY_RUN:-0}"

cd "$REPO_DIR"
git fetch --prune --quiet

git worktree list --porcelain | grep '^worktree ' | awk '{print $2}' | while read -r wt_path; do
  # Skip main worktree
  [ "$wt_path" = "$REPO_DIR" ] && continue

  branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null) || continue

  # Condition: remote branch gone OR merged into target
  remote_gone=0
  git rev-parse --verify "refs/remotes/origin/$branch" &>/dev/null || remote_gone=1

  merged=0
  git branch --merged "$TARGET_BRANCH" 2>/dev/null | grep -q "^\s*${branch}$" && merged=1

  [ "$remote_gone" -eq 1 ] || [ "$merged" -eq 1 ] || continue

  # Safety gate
  if [ -n "$(git -C "$wt_path" status --porcelain 2>/dev/null)" ]; then
    echo "SKIP (dirty): $wt_path"
    continue
  fi
  unpushed=$(git -C "$wt_path" rev-list HEAD --not --remotes --count 2>/dev/null || echo 99)
  if [ "$unpushed" -gt 0 ]; then
    echo "SKIP (unpushed=$unpushed): $wt_path"
    continue
  fi

  echo "REMOVING: $wt_path (branch=$branch, remote_gone=$remote_gone, merged=$merged)"
  if [ "$DRY_RUN" -eq 0 ]; then
    git worktree remove "$wt_path" 2>/dev/null || git worktree remove --force "$wt_path" 2>/dev/null || true
    git branch -d "$branch" 2>/dev/null || true
  fi
done

git worktree prune 2>/dev/null || true
```

**Real-world use:** GitHub's `stale-branch-action` (v1.33.0, 44 releases, actively maintained) applies the same pattern for remote branches. `grove prune --dry-run` uses the same logic for worktrees. Both are scheduled daily in production.

**Fits us:** Yes — deploy as `scripts/vps/git-worktree-sweep.sh` and schedule via cron in `setup-vps.sh`. Run with `DRY_RUN=1` first.

---

## Key Decisions Supported by Research

### 1. Decision: Cleanup in `autopilot-loop.sh` via `trap EXIT`, not in LLM instructions

**Evidence:** Claude Code's own team needed 3 separate hotfixes (v2.1.76, v2.1.77, v2.1.78 still has 3 known bugs) for LLM-driven worktree cleanup ([issue #35862](https://github.com/anthropics/claude-code/issues/35862)). The Graceful Shutdown research confirms that cleanup must run in the `finally`/trap block of the process manager, not in application logic. The community consensus (reddit/AI_Agents, March 2026): "A clean environment enables reliable evolution. Workspace entropy kills agents faster than model limits."

**Confidence:** High

---

### 2. Decision: Three-check safety gate before any removal (uncommitted + unpushed + merged)

**Evidence:** Claude Code v2.1.76 fixed the primary `hasWorktreeChanges` bug by adding `rev-list` after `git status --porcelain` missed committed-but-unpushed work ([issue #35862](https://github.com/anthropics/claude-code/issues/35862)). The bacchus-labs/wrangler skill adds the third check (PR merged via `gh pr list`). Skipping any of the three checks causes data loss in real production scenarios.

**Confidence:** High

---

### 3. Decision: Use `git branch --merged develop` as the primary merge signal, not remote branch deletion alone

**Evidence:** Remote branch deletion happens when the PR tool (GitHub) auto-deletes after merge — but in our pipeline merge is done by the autopilot locally (`git merge --no-ff`). The branch may still exist on remote until the sweep runs. `git branch --merged develop` is local, fast, no network call required, and is the correct signal for our merge-to-develop workflow. Remote gone (`refs/remotes/origin/<branch>` absent) is a secondary/sweep signal for already-merged+deleted branches.

**Confidence:** High

---

### 4. Decision: Also run a standalone cron sweeper — don't rely solely on in-loop cleanup

**Evidence:** Even with `trap EXIT`, worktrees accumulate from: pre-existing stale ones, runs where the state file wasn't written yet, SIGKILL (not catchable by trap), or system reboots. The brtkwr.com author accumulated 256 worktrees and 28 GB despite manual discipline. The `grove prune` tool and `stale-branch-action` exist precisely because in-operation cleanup is insufficient on its own. Two-layer defense (in-loop + periodic sweep) matches production patterns.

**Confidence:** High

---

### 5. Decision: `git worktree remove` over `rm -rf` — always use git's API for worktree removal

**Evidence:** `git worktree remove` both deletes the directory AND removes the `.git/worktrees/<name>` metadata entry. `rm -rf` only removes the directory, leaving the metadata entry that blocks git from reusing that worktree name. `git worktree prune` is the recovery for the `rm -rf` case but is a second command. The [OneUptime guide](https://oneuptime.com/blog/post/2026-01-24-git-worktrees/view) documents the `git worktree repair` command for corrupted metadata.

**Confidence:** High

---

## Research Sources

- [Worktree cleanup: three remaining data-loss paths after v2.1.76-77 fixes](https://github.com/anthropics/claude-code/issues/35862) — exact bugs in LLM-driven cleanup, `rev-list` vs `git status --porcelain -uno`, baseline drift
- [Bulk cleaning stale git worktrees and branches](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/) — production script for 256 worktrees + 700 branches, `': gone]'` detection pattern, two-layer cleanup
- [Worktree cleanup hangs when using --worktree --tmux](https://github.com/anthropics/claude-code/issues/27169) — confirmed: LLM-driven worktree cleanup fails on crash/forced exit, leaves orphaned worktrees
- [Feature: Hook control over worktree removal](https://github.com/anthropics/claude-code/issues/31969) — orchestrator-layer cleanup is the correct pattern; hooks cannot currently block removal
- [cleanup-dangling-worktrees skill (bacchus-labs/wrangler)](https://lobehub.com/skills/bacchus-labs-wrangler-cleanup-dangling-worktrees) — three-check safety gate pattern (uncommitted + unpushed + PR merged)
- [Git Worktrees: The Complete Guide for 2026](https://devtoolbox.dedyn.io/blog/git-worktrees-complete-guide) — `git worktree prune`, lock/unlock, pitfall documentation
- [How to Configure Git Worktrees](https://oneuptime.com/blog/post/2026-01-24-git-worktrees/view) — `git worktree repair`, cleaning up after failed operations
- [grove CLI: prune merged worktrees](https://github.com/captainsafia/grove) — production `grove prune --dry-run --base develop` pattern, `--older-than` for time-based cleanup
- [The Complete Guide to Git Worktrees with Claude Code](https://notes.muthu.co/2026/02/the-complete-guide-to-git-worktrees-with-claude-code/) — Anthropic-endorsed post-merge cleanup checklist, parallel agent patterns
- [Graceful Shutdown Patterns for Long-Lived Services](https://zylos.ai/research/2026-02-25-graceful-shutdown-long-lived-services) — `trap EXIT`, three-phase shutdown, agent task loop teardown
- [Delete Abandoned Branches GitHub Action](https://github.com/marketplace/actions/delete-abandoned-branches) — CI/CD scheduled branch cleanup pattern, protection rules
- [stale-branch-action](https://github.com/int128/stale-branch-action) — v1.33.0 production branch cleanup in GitHub Actions, expiration + dry-run
- [How to Delete All Git Branches That Have Been Merged (Safely)](https://thelinuxcode.com/how-to-delete-all-git-branches-that-have-been-merged-safely-locally-and-remotely/) — `git for-each-ref --merged`, protected branch patterns, remote cleanup
- [AI Agent Sandbox: Architecture Patterns to Enterprise Practice](https://wengjialin.com/blog/agent-sandbox/) — isolation + lifecycle management patterns, two-phase cleanup (detach → release)
- [Production Patterns: Hosting, Sandbox, and Compaction](https://agentfactory.panaversity.org/docs/Building-Custom-Agents/anthropic-agents-kit-development/production-patterns) — ephemeral agent lifecycle, `trap EXIT` equivalents in SDK
