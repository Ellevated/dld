# Feature: [TECH-149] Deterministic Worktree Cleanup After Merge
**Status:** queued | **Priority:** P1 | **Date:** 2026-03-25

## Why
Autopilot's PHASE 3 describes worktree cleanup in `finishing.md` step 9 — but this is markdown that the LLM agent executes. When the agent crashes, times out, or gets context-compacted before reaching step 9, cleanup never happens. Result: orphaned worktree directories and stale branches accumulate.

**Evidence:**
- 2 local orphan branches: `feature/FTR-146`, `feature/FTR-147`
- 17 remote orphan branches on origin (BUG-084, BUG-094, FTR-137, etc.)
- `git push origin --delete` appears in ZERO files across entire codebase
- `finishing.md` step 9 is less complete than `worktree-setup.md` Cleanup section (missing `git worktree prune`)
- `autopilot-loop.sh` has no post-run cleanup guard
- `pueue-callback.sh` (VPS) has zero worktree awareness

**Root cause:** Relying on LLM to execute cleanup is an anti-pattern. Cleanup must be deterministic — in bash outside the LLM session.

## Context
- ADR-011 (Enforcement as Code) already establishes this principle
- The "deterministic wrapper" pattern: LLM = nondeterministic kernel, bash = deterministic shell
- Claude Code's own worktree cleanup had 3+ bugs (issue #35862) — confirms LLM-driven cleanup is unreliable
- Post-merge git hook (`post-merge`) eliminated: autopilot uses `--ff-only` which doesn't trigger hooks

---

## Scope
**In scope:**
- Layer 1: Post-run cleanup guard in `autopilot-loop.sh` (bash, outside LLM)
- Layer 2: Standalone `scripts/cleanup-worktrees.sh` for sweeping all orphans
- Fix existing inconsistencies in `finishing.md` and `autopilot-git.md`
- VPS integration: cleanup call in `pueue-callback.sh`
- Template sync (all changes are universal)

**Out of scope:**
- Automatic remote branch deletion (opt-in flag only, per devil's advocate)
- Cron-based scheduled cleanup (can be added later)
- `trap EXIT` signal handler (overkill for current needs)
- Changing merge strategy from `--ff-only` to `--no-ff`

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `scripts/autopilot-loop.sh` — local loop runner
- `scripts/vps/orchestrator.sh` — VPS dispatcher
- `scripts/vps/pueue-callback.sh` — VPS post-task callback
- `scripts/vps/claude-runner.sh` — VPS Claude executor

### Step 2: DOWN — what depends on?
- `git worktree` CLI (add, remove, prune, list)
- `.worktrees/` directory (gitignored)
- Branch naming convention: `{type}/{SPEC_ID}`
- `MAIN_REPO` / `PROJECT_DIR` env vars

### Step 3: BY TERM — grep entire project
- `worktree remove`: 6 files (3 root + 3 template mirrors)
- `worktree prune`: 2 files (only in worktree-setup.md + template)
- `git push origin --delete`: 0 files (completely absent)
- `branch -d` vs `branch -D`: inconsistency between finishing.md (-d) and autopilot-git.md (-D)

### Step 4: CHECKLIST — mandatory folders
- [x] `tests/**` — no existing tests for this lifecycle
- [x] `template/.claude/skills/autopilot/` — ALL changes must sync (universal improvement)
- [x] `scripts/` — new cleanup script here

### Verification
- [x] All found files added to Allowed Files
- [x] Template sync required for 3 files

---

## Allowed Files
**ONLY these files may be modified during implementation:**

1. `template/.claude/skills/autopilot/finishing.md` — add `git worktree prune`, fix safety check, add remote branch note
2. `template/.claude/skills/autopilot/autopilot-git.md` — fix `-D` to `-d`, add `worktree prune`, add remote branch note
3. `template/.claude/skills/autopilot/worktree-setup.md` — upgrade safety check to `git status --porcelain`
4. `.claude/skills/autopilot/finishing.md` — sync from template
5. `.claude/skills/autopilot/autopilot-git.md` — sync from template
6. `.claude/skills/autopilot/worktree-setup.md` — sync from template
7. `template/scripts/autopilot-loop.sh` — add `cleanup_worktree()` function
8. `scripts/autopilot-loop.sh` — sync from template
9. `scripts/vps/pueue-callback.sh` — add worktree cleanup call (DLD-specific)

**New files allowed:**
- `template/scripts/cleanup-worktrees.sh` — standalone sweep script
- `scripts/cleanup-worktrees.sh` — sync from template

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** Infrastructure / Tooling (no business domain)
**Cross-cutting:** Git workflow, CI/CD
**Data model:** N/A

---

## Approaches

### Approach 1: Minimal — Loop Guard Only (~20 LOC)
**Source:** [Patterns scout — Approach 1](research-patterns.md)
**Summary:** Add `cleanup_worktree()` to `autopilot-loop.sh` only. Fix doc inconsistencies.
**Pros:** Minimal changes, solves 90%
**Cons:** Doesn't clean historical orphans (17 remote branches stay), no standalone tool

### Approach 2: Two-Layer Defense (~100 LOC)
**Source:** [Patterns scout](research-patterns.md) + [External scout](research-external.md)
**Summary:** Layer 1 (loop guard) + Layer 2 (standalone sweep script) + doc fixes + VPS integration
**Pros:** Full coverage (current + historical + remote opt-in), works everywhere
**Cons:** More files to create/modify (but still simple bash)

### Approach 3: Full Enforcement + Cron (~150 LOC)
**Source:** [External scout — Pattern 3/4](research-external.md)
**Summary:** Everything in Approach 2 + `trap EXIT` + cron job + VPS orchestrator integration
**Pros:** Maximum reliability, production-grade
**Cons:** Cron dependency, over-engineering for current scale

### Selected: 2
**Rationale:** All 4 scouts converged on two-layer defense. Approach 1 doesn't handle the 17 existing remote orphans. Approach 3 adds cron/trap complexity without proportional value. Approach 2 is the sweet spot: full coverage with ~100 lines of simple bash.

---

## Design

### User Flow
1. Autopilot runs spec → creates worktree → does work → merges to develop
2. Claude exits (crash/success/timeout — doesn't matter)
3. `autopilot-loop.sh` cleanup guard runs → removes worktree + branch for this SPEC_ID
4. Next session start → `cleanup-worktrees.sh` sweeps any remaining orphans
5. Manual use: `scripts/cleanup-worktrees.sh` or `DRY_RUN=1 scripts/cleanup-worktrees.sh`

### Architecture

```
Layer 1 (per-run, inline):
  autopilot-loop.sh
  └─ cleanup_worktree($SPEC_ID)
     ├─ derive branch name from SPEC_ID
     ├─ safety: git status --porcelain (clean?)
     ├─ safety: git branch --merged develop (merged?)
     ├─ git worktree remove --force
     ├─ git branch -d (safe delete)
     └─ git worktree prune

Layer 2 (sweep, standalone):
  scripts/cleanup-worktrees.sh [--remote] [--dry-run]
  ├─ git fetch --prune
  ├─ enumerate all worktrees via git worktree list --porcelain
  ├─ for each: safety check → remove if merged
  ├─ prune local branches tracking [gone] remotes
  ├─ [--remote] prune merged remote branches
  └─ git worktree prune

VPS (post-task):
  pueue-callback.sh
  └─ cleanup_worktree() (same logic as Layer 1)
```

### Key Safety Gates (from devil's advocate)

| Gate | Check | Consequence if fails |
|------|-------|---------------------|
| Uncommitted changes | `git status --porcelain` | Skip cleanup, log warning |
| Branch merged | `git branch --merged develop` | Skip cleanup, log warning |
| Protected branch | `main\|develop\|master` filter | Never delete |
| Symlink removal | `rm -f .worktrees/{ID}/.claude` | Prevent hook resolution race |
| Idempotent | `2>/dev/null \|\| true` | No error on second run |

---

## Implementation Plan

### Research Sources
- [Bulk cleaning stale git worktrees — brtkwr.com](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/) — worktree sweep pattern
- [Claude Code worktree cleanup bugs — issue #35862](https://github.com/anthropics/claude-code/issues/35862) — safety check improvements
- [Deterministic AI Orchestration — Praetorian](https://securityboulevard.com/2026/02/deterministic-ai-orchestration-a-platform-architecture-for-autonomous-development/) — LLM as nondeterministic kernel

### Task 1: Create standalone cleanup script
**Type:** code
**Files:**
  - create: `template/scripts/cleanup-worktrees.sh`
  - create: `scripts/cleanup-worktrees.sh` (sync copy)
**Pattern:** [brtkwr.com sweep pattern](https://brtkwr.com/posts/2026-03-06-bulk-cleaning-stale-git-worktrees/)
**Acceptance:**
  - Script is executable (`chmod +x`)
  - `DRY_RUN=1 scripts/cleanup-worktrees.sh` lists orphans without deleting
  - `scripts/cleanup-worktrees.sh` removes merged worktrees + branches
  - `scripts/cleanup-worktrees.sh --remote` also removes remote branches
  - Protected branches (main, develop, master) are never deleted
  - Script is idempotent (running twice = no errors)
  - Has `set -euo pipefail` and proper error handling

### Task 2: Add cleanup guard to autopilot-loop.sh
**Type:** code
**Files:**
  - modify: `template/scripts/autopilot-loop.sh`
  - modify: `scripts/autopilot-loop.sh` (sync copy)
**Pattern:** [Patterns scout — Approach 1](research-patterns.md)
**Acceptance:**
  - `cleanup_worktree()` function added
  - Called after each Claude invocation (after EXIT_CODE capture)
  - Sweep call at session start (before main loop)
  - Uses `git status --porcelain` for safety check
  - Uses `git branch --merged develop` for merge verification
  - Removes `.claude` symlink before `git worktree remove`
  - All cleanup operations use `|| true` (never blocks loop)

### Task 3: Fix doc inconsistencies + add VPS cleanup
**Type:** code
**Files:**
  - modify: `template/.claude/skills/autopilot/finishing.md`
  - modify: `template/.claude/skills/autopilot/autopilot-git.md`
  - modify: `template/.claude/skills/autopilot/worktree-setup.md`
  - modify: `.claude/skills/autopilot/finishing.md` (sync)
  - modify: `.claude/skills/autopilot/autopilot-git.md` (sync)
  - modify: `.claude/skills/autopilot/worktree-setup.md` (sync)
  - modify: `scripts/vps/pueue-callback.sh`
**Acceptance:**
  - `finishing.md` step 9: add `git worktree prune`, upgrade safety check to `git status --porcelain`, add comment about remote cleanup
  - `autopilot-git.md` section 5.5: fix `branch -D` → `branch -d`, add `worktree prune`
  - `worktree-setup.md` Cleanup section: upgrade safety check to `git status --porcelain`
  - `pueue-callback.sh`: add worktree cleanup call after DB update (fail-safe, `|| true`)
  - All template files synced to root `.claude/`

### Execution Order
1 → 2 → 3

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Autopilot creates worktree | - | existing |
| 2 | Autopilot works in worktree | - | existing |
| 3 | Autopilot merges to develop | - | existing |
| 4 | Agent crashes before cleanup | Task 2 (loop guard catches) | new |
| 5 | Agent completes cleanup successfully | Task 3 (improved docs) | fix |
| 6 | Historical orphans exist from prior runs | Task 1 (standalone sweep) | new |
| 7 | Manual cleanup needed | Task 1 (--dry-run mode) | new |
| 8 | Remote branch orphans | Task 1 (--remote flag) | new |
| 9 | VPS task completion | Task 3 (pueue-callback) | new |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | LLM crashes mid-PHASE-3, worktree orphaned | `.worktrees/FTR-XXX/` exists, branch merged to develop | Loop guard removes worktree + branch, logs "Cleaned up" | deterministic | devil | P0 |
| EC-2 | Worktree has uncommitted changes | `git status --porcelain` returns `?? file.txt` | Cleanup skips, logs "uncommitted changes" warning | deterministic | devil | P0 |
| EC-3 | Branch not merged to develop | `git branch --merged develop` doesn't contain branch | Cleanup skips, logs "not merged" warning | deterministic | devil | P0 |
| EC-4 | Cleanup runs twice for same SPEC_ID | First run removes, second run finds nothing | Second run exits 0 silently, no error | deterministic | devil | P1 |
| EC-5 | Protected branch (develop, main) passed to cleanup | Branch name = "develop" | Never deleted, filtered by PROTECTED pattern | deterministic | devil | P0 |
| EC-6 | Standalone sweep finds multiple orphans | 3 merged worktrees in `.worktrees/` | All 3 removed, `git worktree prune` runs once at end | deterministic | external | P1 |
| EC-7 | `--dry-run` mode | `DRY_RUN=1 scripts/cleanup-worktrees.sh` | Lists what would be removed, removes nothing | deterministic | patterns | P1 |
| EC-8 | `--remote` flag removes remote branches | Merged remote branch `origin/feature/FTR-XXX` exists | `git push origin --delete` executed only with --remote flag | deterministic | devil | P1 |
| EC-9 | `.claude` symlink removed before worktree removal | Symlink exists at `.worktrees/{ID}/.claude` | `rm -f` removes symlink before `git worktree remove` | deterministic | devil | P1 |
| EC-10 | VPS pueue-callback triggers cleanup | Task completes in pueue, callback fires | Cleanup function called, never blocks slot release (`\|\| true`) | deterministic | codebase | P1 |

### Coverage Summary
- Deterministic: 10 | Integration: 0 | LLM-Judge: 0 | Total: 10 (min 3)

### TDD Order
1. EC-1 (core: crash → cleanup)
2. EC-2 (safety: uncommitted)
3. EC-3 (safety: unmerged)
4. EC-5 (safety: protected)
5. EC-4 (idempotent)
6. EC-6, EC-7 (sweep)
7. EC-8 (remote opt-in)
8. EC-9 (symlink)
9. EC-10 (VPS)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Cleanup script is executable | `test -x scripts/cleanup-worktrees.sh && echo OK` | OK | 5s |
| AV-S2 | Dry-run mode works | `DRY_RUN=1 scripts/cleanup-worktrees.sh` | exit 0, no deletions | 10s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Cleanup removes merged worktree | Create worktree, merge branch to develop | Run `scripts/cleanup-worktrees.sh` | Worktree dir removed, branch deleted |
| AV-F2 | Cleanup skips dirty worktree | Create worktree with uncommitted file | Run `scripts/cleanup-worktrees.sh` | Worktree preserved, warning logged |
| AV-F3 | Loop guard cleans after mock crash | Create worktree for FTR-TEST, merge to develop | Call `cleanup_worktree FTR-TEST` from autopilot-loop.sh | Worktree + branch removed |

### Verify Command (copy-paste ready)

```bash
# Smoke
test -x scripts/cleanup-worktrees.sh && echo "S1: OK"
DRY_RUN=1 scripts/cleanup-worktrees.sh && echo "S2: OK"

# Functional — create test worktree, merge, cleanup
git worktree add .worktrees/TEST-CLEANUP -b feature/TEST-CLEANUP 2>/dev/null
git checkout develop && git merge --ff-only feature/TEST-CLEANUP 2>/dev/null
scripts/cleanup-worktrees.sh
test ! -d .worktrees/TEST-CLEANUP && echo "F1: Worktree removed OK"
git branch | grep -q feature/TEST-CLEANUP || echo "F1: Branch removed OK"
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `scripts/cleanup-worktrees.sh` removes merged worktrees and branches
- [ ] `scripts/cleanup-worktrees.sh --remote` removes remote orphan branches
- [ ] `DRY_RUN=1` mode lists without deleting
- [ ] `autopilot-loop.sh` cleanup guard runs after each Claude invocation
- [ ] `autopilot-loop.sh` sweep runs at session start
- [ ] `pueue-callback.sh` calls cleanup after task completion

### Tests
- [ ] All eval criteria from ## Eval Criteria section pass
- [ ] Coverage not decreased

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions
- [ ] Template files synced to root (template-sync.md)
- [ ] Doc inconsistencies fixed (finishing.md, autopilot-git.md, worktree-setup.md)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
