# Worktree Setup (PHASE 0)

Git worktree isolation for safe parallel development.

## When to Use

- **Default:** Always create worktree for task isolation
- **Skip (`--no-worktree`):** Only for tiny fixes (<5 LOC) in docs

## Setup Flow

```
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

# 2. Remove worktree
git worktree remove ".worktrees/{ID}" --force

# 3. Delete local branch (already merged)
git branch -d "{type}/{ID}"

# 4. Prune stale worktree references
git worktree prune
```

## Safety Rules

- ⛔ **NEVER** `git clean -fd` in worktree — destroys parallel work
- ⛔ **NEVER** `git reset --hard` — loses uncommitted changes
- ⛔ **NEVER** delete worktree with uncommitted changes
- ✅ Always verify clean state before cleanup: `git status`
