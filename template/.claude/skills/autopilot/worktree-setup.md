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
     # Only remove if branch is merged to develop
     if git branch --merged develop | grep -q "$wt_branch"; then
       rm -f "$wt/.claude" 2>/dev/null  # remove symlink first
       git worktree remove "$wt" --force 2>/dev/null || true
       git branch -d "$wt_branch" 2>/dev/null || true
       echo "SWEEP: removed orphan worktree $wt (branch $wt_branch)"
     fi
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

2. Save main repo path:
   MAIN_REPO="$(git rev-parse --show-toplevel)"

3. Directory selection:
   └─ .worktrees/ exists? → use it
   └─ worktrees/ exists? → use it
   └─ else → create .worktrees/

4. Safety verification:
   git check-ignore .worktrees/
   └─ not ignored? → add to .gitignore

5. Create worktree:
   git worktree add ".worktrees/{ID}" -b "{type}/{ID}"

   Type mapping:
   | Prefix | Branch Type |
   |--------|-------------|
   | FTR-   | feature/    |
   | BUG-   | fix/        |
   | TECH-  | tech/       |
   | ARCH-  | arch/       |

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

When `./scripts/ci-status.sh` returns exit code 2:

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
