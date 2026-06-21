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
| 0 | Green (all CI checks pass) | Continue |
| 0 | CI-only red (lint, spec compliance, file size — not deploy) | Continue in **REGRESSION-ONLY mode**: record baseline red set. Merge gate (§5.4) requires no NEW failures vs this baseline. Log `CI_BASELINE_RED: {failing checks}`. |
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

# Refresh remote — branch base MUST be fresh origin/develop, not stale local ref
git fetch origin develop

# WHY origin/develop explicit (not implicit HEAD):
#   `git worktree add -b new-branch path` without a base ref branches off
#   the CWD's current HEAD. If anything left cwd HEAD on main (broken prior
#   worktree, manual `git checkout main`, recovery state, orchestrator
#   improvisation) — the new branch inherits main and PHASE 3 merge into
#   develop drags unrelated main-only commits (dependabot bumps, release
#   merge-backs). Pin to origin/develop to guarantee base regardless of
#   CWD state. Reference: awardybot TECH-1063 incident, commit 833e5994.
git worktree add "$WORKTREE_PATH" -b "${BRANCH_PREFIX}/${TASK_ID}" origin/develop
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
# FAIL → STOP. Quick smoke only — CI-parity gate is `./test ci` (§5.1, TECH-206).
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
./test ci
# FAIL → STOP, fix first. Mirrors project's GitHub CI exactly (TECH-206).
# No `./test ci` case? → see §5.6 CI_PARITY_UNAVAILABLE fallback.
```

### 5.2 Update Status — REMOVED (ARCH-187 / ADR-024 / ADR-025)

Status writes are exclusive to `callback.py` (ADR-023). Do **NOT** commit
spec / backlog / lifecycle status changes manually. Callback fires on
pueue task completion and atomically updates `ai/lifecycle/{spec}.yaml`
via git plumbing. See `finishing.md`.

**Autopilot has NO override path.** If callback fails to mark done, signal
`"task_status": "needs_review"` and stop. A human operator (NOT autopilot)
may then run:

```
python3 scripts/vps/spec_operator.py force-done <project> <SPEC_ID> "<reason>" --by=operator
```
#### task_status JSON contract (TECH-194 Layer E)

Autopilot's final JSON output MUST include `task_status`. Callback gates the
post-autopilot dispatch of QA + reflect on this field — without it (or with
an unknown value), callback falls back to "done" dispatch and burns ~$2.50
on QA+reflect for non-done tasks.

| value | semantics | callback action |
|-------|-----------|-----------------|
| `complete` | Spec finished, all tasks done | lifecycle → done, dispatch QA + reflect |
| `blocked` | Needs human (write `## ACTION REQUIRED` in spec) | lifecycle → blocked, SKIP QA + reflect |
| `needs_review` | Ambiguous result, human triage | lifecycle → blocked, SKIP QA + reflect |
| `skipped` | Pre-flight early-exit (already merged) | lifecycle untouched, SKIP QA + reflect |
| missing / unknown | (legacy) | lifecycle → done, dispatch QA + reflect (backward compat) |

Final JSON shape:
```json
{
  "task_status": "complete" | "blocked" | "needs_review" | "skipped",
  "result_preview": "..."
}
```


The `--by=autopilot` and `--by=spark` choices have been REMOVED (ADR-025).

NEVER `git add ai/lifecycle/*.yaml` — direct commits to lifecycle yaml are HARD-BLOCKED by
`.claude/hooks/pre-commit-lifecycle-guard.mjs` (no subject-allowlist exception).

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

# CI-parity merge gate (TECH-206): red → abort, no push, needs_review.
# REGRESSION-ONLY mode: only NEW failures vs PHASE-0 baseline count.
if ! ./test ci; then
  git reset --hard origin/develop   # abort: develop stays at origin state
  echo "BLOCKED: ./test ci red on merged develop — emitting needs_review"
  # Set task_status="needs_review" in final JSON. Do NOT push.
fi

# Push with retry — TECH-197: track success for push guard
PUSH_OK=false
git push origin develop && PUSH_OK=true || {
  git pull --rebase origin develop
  git push origin develop && PUSH_OK=true
}

# Restore stash
[ "$STASHED" = true ] && git stash pop

# TECH-197 PUSH GUARD: if develop push failed after retry,
# emit "needs_review" instead of "complete" in final JSON.
# Work is merged locally; callback push-local will attempt recovery.
if [ "$PUSH_OK" = false ]; then
  echo "WARNING: develop push failed — emitting needs_review"
  # Autopilot must set task_status="needs_review" in final JSON
fi
```

### 5.5 Cleanup

```bash
rm -f "${WORKTREE_DIR}/${TASK_ID}/.claude" 2>/dev/null  # remove symlink first
git worktree remove "${WORKTREE_DIR}/${TASK_ID}" --force
git branch -d ${BRANCH_PREFIX}/${TASK_ID}  # safe delete (-d not -D)
git worktree prune
```

### 5.6 CI-Parity Fallback (TECH-206)

If `./test ci` is absent (exit 127): log `CI_PARITY_UNAVAILABLE`, run `./test`
(full suite) or `./test fast`, emit `needs_review` on any red. **NEVER** silently
degrade to `./test fast` alone. Projects adopt `./test ci` via Wave 2 specs.

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
