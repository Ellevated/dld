# Codebase Research — Automatic Worktree Cleanup After Merge

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `fix-worktree-hooks.sh` | `fix-worktree-hooks.sh:1` | Iterates all worktrees via `git worktree list --porcelain`, applies fix | Pattern: same loop for cleanup |
| Cleanup block in `autopilot-git.md` | `.claude/skills/autopilot/autopilot-git.md:239-245` | 3-step cleanup: `worktree remove`, `branch -D`, `worktree list` verify | Exact commands to extract into script |
| Cleanup block in `worktree-setup.md` | `.claude/skills/autopilot/worktree-setup.md:88-112` | Same 3-step cleanup + `git worktree prune` as 5th step | More complete version — includes prune |
| Cleanup block in `finishing.md` | `.claude/skills/autopilot/finishing.md:58-71` | Step 9 with safety check (uncommitted diff gate) before `worktree remove` + `branch -d` | Copy safety check pattern |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| Safety check before force-removal | `.claude/skills/autopilot/finishing.md:61-67` | `git diff-index --quiet HEAD --` gate before cleanup | Exact pattern needed in cleanup script |
| `autopilot-loop.sh` post-run status check | `scripts/autopilot-loop.sh:127-138` | Reads backlog status after Claude exits, handles blocked/in_progress/done | Model for post-run cleanup hook after loop |
| `pueue-callback.sh` post-task logic | `scripts/vps/pueue-callback.sh:65-76` | Fires after task completion, updates DB + notifies | VPS equivalent of post-run hook |
| `git worktree prune` (only in worktree-setup) | `.claude/skills/autopilot/worktree-setup.md:111` | Prunes stale references after remove | Missing from `finishing.md` and `autopilot-git.md` — gap |

**Recommendation:** Extract the cleanup sequence from `worktree-setup.md:88-112` (the most complete version, includes `prune`) into a standalone `scripts/cleanup-worktree.sh`. Call it from `autopilot-loop.sh` after each iteration. VPS orchestrator has no cleanup hook — `pueue-callback.sh` is the injection point.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

The cleanup logic lives exclusively in markdown skill files (not imported by code). The relevant entry points that trigger the lifecycle:

| File | Line | Usage |
|------|------|-------|
| `scripts/autopilot-loop.sh` | 119 | Calls `claude --print "autopilot $SPEC_ID"` — Claude reads finishing.md internally |
| `scripts/vps/orchestrator.sh` | 236-241 | `pueue add ... run-agent.sh ... autopilot $task_cmd` |
| `scripts/vps/claude-runner.sh` | 31-38 | Executes `claude --print -p "/autopilot $TASK"` — Claude reads finishing.md internally |
| `scripts/vps/pueue-callback.sh` | 65-76 | Fires on pueue task completion — no cleanup logic |

Cleanup in markdown = only executed if Claude reads and follows finishing.md step 9 before crashing/timing out.

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| `git worktree` CLI | system | `add`, `remove`, `prune`, `list --porcelain` |
| `.worktrees/{ID}/` directory | `.gitignore:23` | Gitignored, created by PHASE 0 |
| feature branch `{type}/{ID}` | git local | Created in PHASE 0, merged in PHASE 3 |
| `MAIN_REPO` env var | `autopilot-git.md:104` | Set in PHASE 0 via `git rev-parse --show-toplevel` |

### Step 3: BY TERM — Grep key terms

**Term: `worktree remove`**

| File | Line | Context |
|------|------|---------|
| `.claude/skills/autopilot/finishing.md` | 70 | `git worktree remove ".worktrees/{ID}" --force` |
| `.claude/skills/autopilot/worktree-setup.md` | 105 | `git worktree remove ".worktrees/{ID}" --force` |
| `.claude/skills/autopilot/autopilot-git.md` | 242 | `git worktree remove "${WORKTREE_DIR}/${TASK_ID}" --force` |
| `template/.claude/skills/autopilot/finishing.md` | 70 | same (template mirror) |
| `template/.claude/skills/autopilot/worktree-setup.md` | 105 | same (template mirror) |
| `template/.claude/skills/autopilot/autopilot-git.md` | 242 | same (template mirror) |

**Term: `worktree prune`**

| File | Line | Context |
|------|------|---------|
| `.claude/skills/autopilot/worktree-setup.md` | 111 | `git worktree prune` — present ONLY in worktree-setup, missing from finishing.md |
| `template/.claude/skills/autopilot/worktree-setup.md` | 111 | same (template mirror) |

**Discrepancy found:** `finishing.md` step 9 omits `git worktree prune`. `worktree-setup.md` has it. This means stale references accumulate even when Claude does execute cleanup.

**Term: remote branch deletion**

Zero results across all skill files and scripts. Remote branch `git push origin --delete {branch}` is NOWHERE in the codebase. This explains the 17 orphaned remote branches.

### Step 4: CHECKLIST — Mandatory folders

- [x] `tests/**` — 0 files found for worktree/cleanup (no test coverage for this lifecycle)
- [x] `db/migrations/**` — N/A, no migrations involved
- [x] `ai/glossary/**` — not checked; worktree lifecycle not documented there
- [x] `template/.claude/skills/autopilot/` — mirror of `.claude/skills/autopilot/` — ALL changes must be synced per `template-sync.md` rule (universal improvement = edit template first)

**Critical:** Per `.claude/rules/template-sync.md`, cleanup improvements are universal — must edit `template/.claude/skills/autopilot/` first, then sync to `.claude/skills/autopilot/`.

### Step 5: DUAL SYSTEM check

Two parallel execution paths create worktrees:

**Local (Mac):** `autopilot-loop.sh` → `claude --print "autopilot $SPEC_ID"` → Claude reads `finishing.md` → cleanup in PHASE 3 (step 9).

**VPS:** `orchestrator.sh` → `pueue add ... run-agent.sh` → `claude-runner.sh` → `claude -p "/autopilot $TASK"` → same `finishing.md` → same cleanup logic.

Both paths depend on Claude successfully reaching and executing finishing.md step 9. Neither path has external cleanup enforcement. The VPS path adds a third observer (`pueue-callback.sh`) that fires after Claude exits but does ZERO worktree cleanup.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `.claude/skills/autopilot/finishing.md` | 235 | PHASE 3 instructions — step 9 cleanup | modify (add `git worktree prune` + remote branch delete) |
| `template/.claude/skills/autopilot/finishing.md` | 235 | Template mirror of above | modify (sync — template-sync.md rule) |
| `.claude/skills/autopilot/worktree-setup.md` | 119 | Cleanup reference section already complete | read-only (reference) |
| `template/.claude/skills/autopilot/worktree-setup.md` | 119 | Template mirror | read-only |
| `.claude/skills/autopilot/autopilot-git.md` | 328 | Git workflow SSOT — section 5.5 Cleanup | modify (add prune + remote delete) |
| `template/.claude/skills/autopilot/autopilot-git.md` | 328 | Template mirror | modify (sync) |
| `scripts/autopilot-loop.sh` | 167 | Local loop runner — no post-run cleanup | modify (add cleanup guard after each iteration) |
| `scripts/vps/pueue-callback.sh` | 116 | VPS post-task callback — no cleanup | modify (add worktree cleanup call) |
| `scripts/cleanup-worktree.sh` | 0 | Does not exist | create (new standalone script) |
| `.gitignore` | 30 | `.worktrees/` gitignored at line 23 | read-only (correct) |

**Total:** 9 files affected (7 modify/create, 2 read-only), ~1,553 LOC

---

## Reuse Opportunities

### Import (use as-is)
- `fix-worktree-hooks.sh:7-15` — `git worktree list --porcelain | grep "^worktree "` pattern for iterating all orphaned worktrees in a cleanup sweep script

### Extend (copy structure, not code)
- `scripts/autopilot-loop.sh:118-155` — the post-Claude-exit status check block (lines 118-155) is the right model for where to inject cleanup: after `OUTPUT=$(claude ...)` returns and status is `done`

### Pattern (copy structure, not code)
- `.claude/skills/autopilot/finishing.md:61-67` — the safety check pattern (`git diff-index --quiet HEAD --` before force-remove) must be replicated in any cleanup script
- `scripts/vps/pueue-callback.sh` fail-safe `|| true` pattern — cleanup script must follow same fail-safe design (never crash the callback)

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -10 -- .claude/skills/autopilot/finishing.md .claude/skills/autopilot/autopilot-git.md scripts/autopilot-loop.sh scripts/vps/orchestrator.sh scripts/vps/pueue-callback.sh
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-11 | 1690292 | Ellevated | feat: open-source full project structure (.claude/ + ai/) |
| 2026-03-10 | ba368fa | Ellevated | feat(autopilot): add PROJECT_DIR env var support for multi-project VPS |
| 2026-02-02 | db87ec9 | Ellevated | refactor: rename ralph-autopilot to autopilot-loop |
| 2026-03-10 | 267b9c5 | Ellevated | fix(vps): reorder run-agent.sh args + git pull --rebase |
| 2026-03-10 | 9d6d7f9 | Ellevated | fix(orchestrator): remove local outside function scope |
| 2026-03-10 | ec47ed4 | Ellevated | feat(vps): add Pueue callback with parameterized DB operations |

**Observation:** VPS orchestrator was last changed 2026-03-10 — no cleanup logic has ever been added. The `finishing.md` cleanup has been static since open-source (1690292). No recent refactoring conflicts.

---

## Findings

### Finding 1: Three cleanup gaps in the markdown instructions

**`finishing.md` step 9 vs `worktree-setup.md` Cleanup section:**
- `finishing.md`: `worktree remove` + `branch -d` — missing `git worktree prune`
- `worktree-setup.md`: `worktree remove` + `branch -d` + `git worktree prune` — complete
- **Gap:** `finishing.md` (the actual execution path) is less complete than the reference docs

**Both `finishing.md` and `autopilot-git.md`:**
- No `git push origin --delete {branch}` — remote branches are NEVER deleted
- This explains all 17 remote orphans (`feature/BUG-084`, `fix/BUG-094`, etc.)

**`finishing.md` uses `branch -d` (safe delete), `autopilot-git.md` section 5.5 uses `branch -D` (force delete):**
- Inconsistency: `-d` will fail if branch is not fully merged; `-D` always succeeds
- Post-merge context = `-D` is correct (branch IS merged); `-d` can fail if ff-only merge didn't update ref tracking

### Finding 2: autopilot-loop.sh has no post-run cleanup guard

After `claude --print "autopilot $SPEC_ID"` exits (line 119), the loop only checks backlog status (lines 127-138). If Claude crashed mid-PHASE-3 (after merge but before step 9), the loop:
- Sees `status=done` in backlog (Claude updated it before crashing)
- Moves to next spec
- Leaves orphaned worktree + local branch + remote branch

No code outside Claude's context can see or clean this up.

### Finding 3: VPS pueue-callback.sh has zero worktree awareness

`pueue-callback.sh` fires after `claude-runner.sh` exits. It knows `project_id` and `task_label` (format: `project_id:SPEC-ID`). From `SPEC-ID` it can derive branch name and worktree path. It currently does: DB update + Telegram notify. It does NOT attempt any git cleanup.

This is the natural VPS injection point for cleanup.

### Finding 4: Remote branch deletion is completely absent

No file in the codebase — skills, scripts, hooks — deletes remote branches after merge. The feature branch is pushed to origin in PHASE 3 step 7 (`git push -u origin {type}/{ID}`) as a "backup" but is never deleted. Over time this accumulates: currently 17 orphaned remote branches confirmed.

---

## Risks

1. **Risk:** Cleanup script runs on wrong worktree (path derivation bug)
   **Impact:** `git worktree remove --force` on wrong directory destroys in-progress work
   **Mitigation:** Always verify branch is merged to develop before cleanup (`git branch --merged develop | grep {branch}`); safety check from `finishing.md:61-67` mandatory

2. **Risk:** `pueue-callback.sh` cleanup failure blocks slot release
   **Impact:** Compute slot permanently locked, no new tasks dispatched
   **Mitigation:** All cleanup in callback MUST follow existing `|| true` fail-safe pattern — never exit non-zero

3. **Risk:** Template sync miss — `template/.claude/` diverges from `.claude/`
   **Impact:** Users who install fresh DLD get broken cleanup; DLD repo has working cleanup but template doesn't
   **Mitigation:** Per `template-sync.md` rule — ALL changes to skill files are universal, edit template first and sync

4. **Risk:** `autopilot-loop.sh` cleanup runs before Claude has finished writing files
   **Impact:** Race condition: cleanup removes worktree while Claude (on VPS) is still writing
   **Mitigation:** In `autopilot-loop.sh` (local), Claude runs synchronously — safe to clean after exit. On VPS, cleanup belongs in `pueue-callback.sh` which fires after process exit.

5. **Risk:** `branch -d` vs `branch -D` inconsistency causes cleanup to fail silently
   **Impact:** Local branch not deleted, appears as orphan
   **Mitigation:** Use `branch -D` in cleanup script (post-merge context, forced delete is safe and correct per `autopilot-git.md:243`)
