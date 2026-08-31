# Worktree Setup (PHASE 0)

Git worktree isolation for safe parallel development.

## When to Use

- **Default:** Always create worktree for task isolation
- **Skip (`--no-worktree`):** Only for tiny fixes (<5 LOC) in docs

## Setup Flow

```
0. Sweep old orphans (from previous crashed runs):

   # 0a. Remove orphaned worktrees (merged to develop)
   for wt in $(git worktree list --porcelain | grep '^worktree ' | awk '{print $2}'); do
     # Skip main repo worktree
     [[ "$wt" == "$(git rev-parse --show-toplevel)" ]] && continue
     wt_branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
     [[ -z "$wt_branch" ]] && continue
     # Skip protected branches
     [[ "$wt_branch" =~ ^(main|master|develop)$ ]] && continue
     # Safety: skip if uncommitted changes
     if [[ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]]; then
       echo "SWEEP SKIP: $wt has uncommitted changes"
       continue
     fi
     # A spec whose branch was pushed but never merged is WAITING to be
     # continued. `pushed=yes` is true for exactly that state, so the test below
     # would delete the worktree and then fail to delete the branch (`git branch -d`
     # refuses an unmerged branch), leaving the dangling local ref the next
     # `worktree add -b` trips over.
     wt_spec="$(basename "$wt")"
     if grep -q 'branch_pushed_not_merged' "ai/lifecycle/${wt_spec}.yaml" 2>/dev/null; then
       echo "SWEEP SKIP: $wt — branch pushed, not merged (re-dispatch continues it)"
       continue
     fi
     # Remove when the work is safe, by either test:
     #   (a) branch merged into develop — the classic case
     #   (b) every commit is reachable from some remote — covers harness-created
     #       worktrees (worktree-agent-*, worktree-BUG-*). Their work reaches
     #       develop through a feature branch, so the worktree branch itself is
     #       NEVER "--merged develop" and (a) alone leaks them forever.
     merged=""
     git branch --merged develop | grep -q "$wt_branch" && merged=yes
     pushed=""
     [[ -z "$(git -C "$wt" log --oneline HEAD --not --remotes 2>/dev/null)" ]] && pushed=yes
     if [[ -n "$merged" || -n "$pushed" ]]; then
       rm -f "$wt/.claude" 2>/dev/null  # remove symlink first
       git worktree remove "$wt" --force 2>/dev/null || true
       git branch -d "$wt_branch" 2>/dev/null || true
       echo "SWEEP: removed orphan worktree $wt (branch $wt_branch, merged=${merged:-no} pushed=${pushed:-no})"
     fi
   done

   # 0a-bis. Empty leftover dirs under both worktree roots. `git worktree remove`
   # leaves the parent behind, and a crashed run can leave a dir git never knew about.
   for root in .worktrees .claude/worktrees; do
     [[ -d "$root" ]] && find "$root" -mindepth 1 -maxdepth 1 -type d -empty -delete 2>/dev/null
   done

   # 0b. Prune merged local branches without worktrees
   for branch in $(git branch --merged develop | grep -E '^\s+(feature|fix|tech|arch)/' | tr -d ' '); do
     [[ "$branch" =~ ^(main|master|develop)$ ]] && continue
     git branch -d "$branch" 2>/dev/null || true
     echo "SWEEP: pruned merged branch $branch"
   done

   # 0c. Drop orphaned autopilot stashes
   git stash list | grep -E 'autopilot-(phase3|temp)' | \
     grep -oE 'stash@\{[0-9]+\}' | sort -t'{' -k2 -rn | \
     while read -r stash_ref; do
       git stash drop "$stash_ref" 2>/dev/null || true
       echo "SWEEP: dropped stash $stash_ref"
     done

   # 0d. Prune stale worktree references
   git worktree prune

1. CI health check: ./scripts/ci-status.sh
   └─ exit 0 → continue
   └─ exit 2 → DEPLOY ERROR PROTOCOL (see below)
   └─ script absent (127) → log CI_STATUS_UNAVAILABLE, continue
      (per-project artifact; dld has none. Absence is not a deploy failure)

2. Save main repo path:
   MAIN_REPO="$(git rev-parse --show-toplevel)"

3. Directory selection:
   └─ .worktrees/ exists? → use it
   └─ worktrees/ exists? → use it
   └─ else → create .worktrees/

4. Safety verification:
   git check-ignore .worktrees/
   └─ not ignored? → add to .gitignore

5. Create worktree — CONTINUE an existing pushed branch, else branch fresh from origin/develop:
   # Refresh remote first — base MUST be fresh origin/develop, not stale local ref
   git fetch origin develop

   if git ls-remote --exit-code --heads origin "{type}/{ID}" >/dev/null 2>&1; then
     # CONTINUATION: a previous run was killed by timeout and its salvage pushed
     # the commits. Starting fresh here burns them and makes the next salvage
     # push non-fast-forward.
     git fetch origin "{type}/{ID}"

     # A local ref may survive from a swept worktree. Drop it only when origin
     # already has everything it holds; otherwise STOP — never discard commits.
     if git show-ref --verify --quiet "refs/heads/{type}/{ID}"; then
       if [[ -z "$(git log --oneline "origin/{type}/{ID}..{type}/{ID}" 2>/dev/null)" ]]; then
         git branch -D "{type}/{ID}"
       else
         echo "LOCAL_BRANCH_AHEAD: {type}/{ID} has commits origin lacks — needs_review"
         exit 2
       fi
     fi

     # -b <branch> <start-point> is the only non-detached form: plain
     # `worktree add <path> <branch>` detaches HEAD unless the local branch
     # already exists (worktree.guessRemote is off by default).
     git worktree add ".worktrees/{ID}" -b "{type}/{ID}" "origin/{type}/{ID}"

     git -C ".worktrees/{ID}" rebase origin/develop || {
       git -C ".worktrees/{ID}" rebase --abort
       echo "REBASE_CONFLICT: {type}/{ID} vs origin/develop"
       # STOP. Emit task_status="needs_review". NEVER reset --hard: those
       # commits are the work this spec exists to save.
       exit 2
     }

     # Re-sync origin immediately: the rebase rewrote the salvaged commits, so
     # until this lands origin and local have diverged and the NEXT salvage
     # push would be rejected non-fast-forward — the exact loss this fixes.
     # --force-if-includes: a bare lease is satisfied by a BACKGROUND fetch that
     # never integrated the remote tip, and the gate-daemon fetches concurrently.
     git -C ".worktrees/{ID}" push --force-with-lease --force-if-includes origin "{type}/{ID}" || {
       echo "PUSH_REJECTED: origin/{type}/{ID} moved under us — someone else pushed to this branch"
       # STOP. Emit task_status="needs_review". NEVER retry with plain --force.
       exit 2
     }

     echo "CONTINUING {type}/{ID} — commits already done:"
     git -C ".worktrees/{ID}" log --oneline origin/develop..HEAD
     # Read that list before planning. Those tasks are DONE — do not redo them.
   else
     git worktree add ".worktrees/{ID}" -b "{type}/{ID}" origin/develop
   fi

   # WHY origin/develop explicit (not implicit HEAD):
   #   `git worktree add -b new-branch path` without a base ref branches off
   #   the CWD's current HEAD. If anything left cwd HEAD on main (broken prior
   #   worktree, manual `git checkout main`, recovery state, orchestrator
   #   improvisation) — the new branch inherits main and PHASE 3 merge into
   #   develop drags unrelated main-only commits (dependabot bumps, release
   #   merge-backs). Pin to origin/develop to guarantee base regardless of
   #   CWD state. This has bitten a real run — do not skip the check.

   Type mapping:
   | Prefix | Branch Type |
   |--------|-------------|
   | FTR-   | feature/    |
   | BUG-   | fix/        |
   | TECH-  | tech/       |
   | ARCH-  | arch/       |
   | GROWTH- | growth/    |

6. Link .claude directory (optional, improves performance):
   ln -s "$MAIN_REPO/.claude" ".worktrees/{ID}/.claude"
   (hooks work without symlink, but symlink avoids repeated root lookup)

7. Copy .env:
   cp "$MAIN_REPO/.env" ".worktrees/{ID}/.env"
   (gitignored, won't be in worktree by default)

8. Environment setup (spec-driven):
   └─ Python project? → uv sync / pip install
   └─ Node project? → npm install
   └─ Docker needed? → docker-compose up -d

9. Baseline verification:
   ./test fast
   └─ must pass before any work!

10. cd to worktree:
    cd ".worktrees/{ID}"
```

## Deploy Error Protocol

When `./scripts/ci-status.sh` returns exit code 2 — **only** 2. A missing script exits
127 and means the project ships no CI probe, which says nothing about the deploy.

⛔ **DO NOT attempt to fix directly!**

```
1. Create BUG spec inline:
   - ID: next BUG-XXX from backlog
   - Title: "Deploy failure: {workflow_name}"
   - Copy error output to spec
   - Status: queued

2. Block current task:
   - Spec: Status → blocked
   - Add: "Blocked by: BUG-XXX (deploy failure)"
   - Backlog: Status → blocked

3. Take BUG spec immediately:
   - Continue autopilot with BUG-XXX
   - After fix → return to queue

4. Blocked spec stays blocked:
   - Human decides when to resume
```

## Cleanup (PHASE 3)

After successful merge to develop:

```bash
# 1. Return to main repo
cd "$MAIN_REPO"

# 2. Safety check: verify no uncommitted changes before force-removal
cd ".worktrees/{ID}"
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  echo "ERROR: Worktree has uncommitted changes! Aborting cleanup."
  git status --short
  exit 1
fi
cd -

# 3. Remove worktree
git worktree remove ".worktrees/{ID}" --force

# 4. Delete local branch (already merged)
git branch -d "{type}/{ID}"

# 5. Prune stale worktree references
git worktree prune
```

## Safety Rules

- ⛔ **NEVER** `git clean -fd` in worktree — destroys parallel work
- ⛔ **NEVER** `git reset --hard` — loses uncommitted changes
- ⛔ **NEVER** delete worktree with uncommitted changes
- ✅ Always verify clean state before cleanup: `git status`
