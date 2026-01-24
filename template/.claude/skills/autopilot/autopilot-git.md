# Autopilot: Git Workflow

SSOT for all Git operations in Autopilot.

---

## CRITICAL: Branch Protection

```
NEVER PUSH TO MAIN. EVER.

Target branch: develop (ONLY!)
Protected: main, master — FORBIDDEN for autopilot
```

If you see `git push origin main` in your plan — STOP. This is a bug.

---

## Quick Reference

```
PHASE 0: Setup
  worktree add → copy .env → baseline test

PHASE 2: Per Task
  code → test → review → COMMIT (no push!)

PHASE 3: Finish
  test → status done → push feature → merge develop → push → cleanup
```

**Key Rules:**
- ONE push per spec (CI cost optimization)
- NO COMMIT without reviewers approved
- NEVER push to `main`, only `develop`
- NEVER auto-resolve conflicts

---

## 1. Branch Naming

| Task Type | Branch | Worktree Path |
|-----------|--------|---------------|
| FTR-XXX | `feature/FTR-XXX` | `.worktrees/FTR-XXX/` |
| BUG-XXX | `fix/BUG-XXX` | `.worktrees/BUG-XXX/` |
| TECH-XXX | `tech/TECH-XXX` | `.worktrees/TECH-XXX/` |
| ARCH-XXX | `arch/ARCH-XXX` | `.worktrees/ARCH-XXX/` |

**Branch prefix by type:**
```bash
case $TASK_TYPE in
  FTR)  BRANCH_PREFIX="feature" ;;
  BUG)  BRANCH_PREFIX="fix" ;;
  TECH) BRANCH_PREFIX="tech" ;;
  ARCH) BRANCH_PREFIX="arch" ;;
  *)    BRANCH_PREFIX="task" ;;
esac
```

---

## 2. Worktree Setup (PHASE 0)

### 2.1 CI Health Check (FIRST!)

```bash
./scripts/ci-status.sh
```

| Exit | Meaning | Action |
|------|---------|--------|
| 0 | Green or CI-only failures | Continue |
| 2 | Deploy failure | DEPLOY ERROR PROTOCOL |

**Deploy failure → BLOCKING:**
1. Create BUG spec inline (next BUG-XXX)
2. Block current task: Status → blocked
3. Take BUG spec immediately
4. Blocked spec stays blocked until human resumes

### 2.2 Directory Selection

```bash
# Priority: .worktrees/ > worktrees/ > create .worktrees/
WORKTREE_DIR=$(ls -d .worktrees 2>/dev/null || ls -d worktrees 2>/dev/null || echo ".worktrees")
mkdir -p "$WORKTREE_DIR"
```

### 2.3 Safety Check

```bash
# Must be gitignored
git check-ignore -q "$WORKTREE_DIR" || {
  echo "$WORKTREE_DIR/" >> .gitignore
  git add .gitignore && git commit -m "chore: gitignore $WORKTREE_DIR"
}
```

### 2.4 Create Worktree

```bash
# Save for PHASE 3
MAIN_REPO="$(git rev-parse --show-toplevel)"
WORKTREE_PATH="${WORKTREE_DIR}/${TASK_ID}"

git worktree add "$WORKTREE_PATH" -b "${BRANCH_PREFIX}/${TASK_ID}"
cd "$WORKTREE_PATH"
```

### 2.5 Copy Environment

```bash
cp "${MAIN_REPO}/.env" .env 2>/dev/null || true
# Copy any gitignored config dirs your project needs
# cp -r "${MAIN_REPO}/.local-db" .local-db 2>/dev/null || true
```

### 2.6 Baseline Test

```bash
./test fast
# FAIL → STOP, don't proceed
```

### Skip Worktree (rare)

```bash
autopilot --no-worktree
```

Only for: hotfixes <5 LOC, doc-only, config tweaks.

---

## 3. Commit Rules

### 3.1 Commit Gate

```
NO COMMIT without BOTH:
  1. SPEC REVIEWER: approved
  2. CODE QUALITY REVIEWER: approved
```

### 3.2 Pre-Commit Checklist

Before `git commit`, verify ALL:

```
[ ] CODER completed — files created/modified
[ ] TESTER completed — tests passed
[ ] DOCUMENTER completed — docs updated (if needed)
[ ] SPEC REVIEWER — approved
[ ] CODE QUALITY REVIEWER — approved
```

**Any missing → STOP → complete step first!**

### 3.3 Pre-Commit Self-Check (BUG-358)

Say out loud before commit:

```
"Coder: completed — files: [list]"
"Tester: passed"
"Spec Reviewer: approved"
"Code Quality: approved"
```

Creates explicit checkpoint in conversation.

---

## 4. Push Strategy (TECH-085)

**Rule:** Minimize pushes. ONE push per spec = 80% CI cost reduction.

```
Per-task: COMMIT only, NO PUSH
End of spec: Push feature → Merge develop → Push develop
```

---

## 5. Finishing Workflow (PHASE 3)

### 5.1 Final Test

```bash
./test fast
# FAIL → STOP, fix first
```

### 5.2 Update Status

```bash
# Update spec: **Status:** done
# Update backlog: done
git add ai/features/${TASK_ID}*.md ai/backlog.md
git commit -m "docs: mark ${TASK_ID} as done"
```

### 5.3 Push Feature Branch (backup)

```bash
git push -u origin ${BRANCH_PREFIX}/${TASK_ID}
```

### 5.4 Merge to Develop

```bash
cd "${MAIN_REPO}"
git checkout develop

# Stash uncommitted (parallel agents may have files)
STASHED=false
if [ -n "$(git status --porcelain)" ]; then
  git stash -u -m "autopilot-phase3-$(date +%s)"
  STASHED=true
fi

# Sync with remote
git pull --rebase origin develop

# Fast-forward merge
git merge --ff-only ${BRANCH_PREFIX}/${TASK_ID}

# Push with retry
git push origin develop || {
  git pull --rebase origin develop
  git push origin develop
}

# Restore stash
[ "$STASHED" = true ] && git stash pop
```

### 5.5 Cleanup

```bash
git worktree remove "${WORKTREE_DIR}/${TASK_ID}" --force
git branch -D ${BRANCH_PREFIX}/${TASK_ID}
git worktree list  # verify
```

---

## 6. Git Safety

### 6.1 Branch Protection

| Rule | Reason |
|------|--------|
| **NEVER push to `main`** | FORBIDDEN. Only `develop`. |
| NEVER force push `develop`/`main` | Protected branches |
| Force push feature OK | After rebase, before merge |

**BLOCKING CHECK before any push:**
```bash
# Verify target is NOT main/master
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
  echo "BLOCKED: Cannot push to $BRANCH"
  exit 1
fi
```

### 6.2 Conflict Handling

```
git pull --rebase → conflict?
  → STOP immediately
  → STATUS: blocked
  → ACTION: "Git conflict. Files: [list]. Need human."
  → NO auto-resolution
```

### 6.3 Multi-Agent Safety (BUG-314)

Multiple agents work in parallel (spark, autopilot, background tasks).

**FORBIDDEN in main repo:**
```bash
git clean -fd      # destroys untracked files from other agents
git reset --hard   # wipes uncommitted work
```

**SAFE alternatives:**
```bash
git checkout -- .  # only tracked files
git stash -u       # recoverable
git clean -fdn     # dry-run first
```

### 6.4 Parallel Safety

```
NEVER take task with status `in_progress` — another autopilot owns it!
ONLY take: queued | resumed
```

---

## 7. Resumed Tasks

When `status: resumed`:

```bash
# Delete stale worktree
[ -d "${WORKTREE_DIR}/${TASK_ID}" ] && \
  git worktree remove "${WORKTREE_DIR}/${TASK_ID}" --force

# Start fresh (full PHASE 0)
# Re-read spec (plan may have changed)
```

Fresh start safer than resuming corrupted state.

---

## 8. Autopilot Permissions

**Exception to CLAUDE.md rules:**
- Autopilot CAN push to `develop` without asking
- Autopilot CAN force push feature branches after rebase

These are explicit permissions for autonomous operation.
