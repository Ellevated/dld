# TECH-191 — Autopilot worktree: pin base to origin/develop (silent main-contamination bug)

**Status:** draft
**Priority:** P1
**Risk:** R2 (2 doc files, no code; reversible)
**Kind:** tech
**Date:** 2026-05-24
**Branch:** `tech/TECH-191-worktree-base-ref`
**Estimated execution:** ~15 min autopilot
**Compute estimate:** ~$1

---

## Problem

В `autopilot` skill команда создания worktree:

```bash
git worktree add ".worktrees/{ID}" -b "{type}/{ID}"
```

— **без явного base ref**. Git берёт current HEAD текущего CWD как базу. Implicit assumption: CWD HEAD = `develop`.

В 99% случаев это так и работает. В 1% (broken state, параллельная сессия, оператор checkoutнул main, орchestrator/Claude в импровизации передал `origin/main` явно, recovery state после крэша) — ветка оказывается основана на `main`. PHASE 3 потом мерджит её в develop, и весь diff между develop и main (включая dependabot bumps, релизные коммиты, merge-back артефакты) едет в develop как collateral.

## Real-world incident

**Awardybot, 2026-05-24, TECH-1063 autopilot run:**

1. Autopilot создал worktree через `git worktree add ".worktrees/TECH-1063" -b "tech/TECH-1063"`.
2. По неизвестной причине (branch стёрт Phase 3 cleanup, reflog пуст) база оказалась `origin/main`, а не `origin/develop`.
3. PHASE 3 merge в develop потащил PR #138 (`appleboy/scp-action 0.1.7 → 1.0.0`) и PR #139 (`actions/setup-node v4 → v6`) — оба ЖИВУТ ТОЛЬКО на main, в develop их не back-merged.
4. Recovery: `git reset --hard <pre-merge>` + cherry-pick трёх моих коммитов. ~30 минут потеряно на ручную чистку.

**Awardybot fix:** commit `833e5994 chore(autopilot): pin worktree base to origin/develop` — добавлен явный `origin/develop` + предварительный `git fetch`. См. https://github.com/EllevatedAI/AwardyBot/commit/833e5994 (приватный репо, фикс на develop).

## Why это баг в DLD, а не одноразовый incident

Это **anti-pattern класса "implicit assumption baked into tooling"** — тот же класс что:
- **ADR-021** (awardybot): pg_cron `current_setting('supabase.service_role_key', true)` silent-NULL → cron миграция применилась без cron-jobа, 12 дней молчания
- **L-FEEDBACK-CI-SECRETS** (awardybot reflect): GH Actions secrets ≠ local `.env` → env-drift между prod и dev несколько раз
- **TECH-182** (DLD): orchestrator rebase autostash data loss — implicit autostash behavior

Pattern: **«работает по умолчанию из-за окружения, тихо ломается когда окружение чуть другое»**. Не сегфолт, не bug-в-логике — bug-в-неявном-предположении. Гарантия должна быть в коде, а не в окружении.

## Scope

**In scope:**
- `template/.claude/skills/autopilot/worktree-setup.md` step 5 — добавить `git fetch origin develop` + `origin/develop` явный base ref
- `template/.claude/skills/autopilot/autopilot-git.md` §2.4 — то же
- `.claude/skills/autopilot/worktree-setup.md` — sync с template
- `.claude/skills/autopilot/autopilot-git.md` — sync с template
- Header-comment в обоих местах с объяснением WHY pinning явный

**Out of scope:**
- Аналогичный аудит других git-команд в DLD скриптах (`git checkout -b`, `git reset --hard`, `git rebase --onto`) — отдельным spec'ом если найдутся implicit refs
- Pre-commit hook / arch-test проверяющий `git worktree add` всегда с base ref — overkill для 2-х мест, но можно добавить если решим масштабировать на 10+ мест

## Allowed Files

ONLY the files listed below may be modified during implementation.

- `template/.claude/skills/autopilot/worktree-setup.md` — step 5 base ref pinning + WHY comment
- `template/.claude/skills/autopilot/autopilot-git.md` — §2.4 base ref pinning + WHY comment
- `.claude/skills/autopilot/worktree-setup.md` — sync с template
- `.claude/skills/autopilot/autopilot-git.md` — sync с template

**FORBIDDEN:** All other files.

## Implementation Plan

> **Plan validation (2026-05-24, planner pass):** All 4 Allowed Files read in worktree.
> Line numbers from spec confirmed accurate against current code. Both `.claude/` and
> `template/.claude/` copies are byte-identical for the 4 files in scope. No drift.
> Plan refined below with concrete per-file AFTER-state blocks (variable substitution
> differs between the two doc files — `{ID}` / `{type}` literals in worktree-setup.md
> vs `${TASK_ID}` / `${BRANCH_PREFIX}` shell vars in autopilot-git.md).

### Task 1: Patch `template/.claude/skills/autopilot/worktree-setup.md`

**File:** `template/.claude/skills/autopilot/worktree-setup.md`
**Location:** Step 5 of "Setup Flow" code block (currently line 71–72).

**BEFORE (lines 71–72):**
```
5. Create worktree:
   git worktree add ".worktrees/{ID}" -b "{type}/{ID}"
```

**AFTER:**
```
5. Create worktree (pin base to origin/develop — see WHY below):
   # Refresh remote first — base MUST be fresh origin/develop, not stale local ref
   git fetch origin develop
   git worktree add ".worktrees/{ID}" -b "{type}/{ID}" origin/develop

   # WHY origin/develop explicit (not implicit HEAD):
   #   `git worktree add -b new-branch path` without a base ref branches off
   #   the CWD's current HEAD. If anything left cwd HEAD on main (broken prior
   #   worktree, manual `git checkout main`, recovery state, orchestrator
   #   improvisation) — the new branch inherits main and PHASE 3 merge into
   #   develop drags unrelated main-only commits (dependabot bumps, release
   #   merge-backs). Pin to origin/develop to guarantee base regardless of
   #   CWD state. Reference: awardybot TECH-1063 incident, commit 833e5994.
```

Keep the existing Type-mapping table immediately after this block unchanged.

### Task 2: Patch `template/.claude/skills/autopilot/autopilot-git.md`

**File:** `template/.claude/skills/autopilot/autopilot-git.md`
**Location:** §2.4 "Create Worktree" bash block (currently line 102–109).

**BEFORE (lines 102–109):**
```bash
# Save for PHASE 3
MAIN_REPO="$(git rev-parse --show-toplevel)"
WORKTREE_PATH="${WORKTREE_DIR}/${TASK_ID}"

git worktree add "$WORKTREE_PATH" -b "${BRANCH_PREFIX}/${TASK_ID}"
cd "$WORKTREE_PATH"
```

**AFTER:**
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

### Task 3: Sync `.claude/` (DLD-specific copy)

**Files (both already byte-identical to template/ at planner-validation time):**
- `.claude/skills/autopilot/worktree-setup.md` — apply Task 1 edit verbatim (same line numbers: 71–72).
- `.claude/skills/autopilot/autopilot-git.md` — apply Task 2 edit verbatim (same line numbers: 102–109).

Rule reference: `.claude/rules/template-sync.md` — «Universal improvement → edit template first, then sync to .claude/».

Recommended mechanical step (avoids drift between copies):
```bash
cp template/.claude/skills/autopilot/worktree-setup.md .claude/skills/autopilot/worktree-setup.md
cp template/.claude/skills/autopilot/autopilot-git.md  .claude/skills/autopilot/autopilot-git.md
```

(Both files are pure docs with no DLD-specific overrides, so `cp` is safe per template-sync.md "Files in Both" list — these files are NOT on the protected-extensions list.)

### Task 4: Verify

```bash
# All 4 git worktree add invocations must contain origin/develop
grep -rn "git worktree add" template/.claude/skills/autopilot/ .claude/skills/autopilot/
# Expected: 4 lines, every one ending with `origin/develop`
# (2 in worktree-setup.md step 5 step-list form,
#  2 in autopilot-git.md §2.4 bash form)

# All 4 must also have a preceding git fetch origin develop
grep -rn "git fetch origin develop" template/.claude/skills/autopilot/ .claude/skills/autopilot/
# Expected: 4 lines

# Diff between template/ and .claude/ for both files must be empty
diff template/.claude/skills/autopilot/worktree-setup.md .claude/skills/autopilot/worktree-setup.md
diff template/.claude/skills/autopilot/autopilot-git.md  .claude/skills/autopilot/autopilot-git.md
# Expected: no output (identical)

# WHY-comment present in all 4 places
grep -rn "TECH-1063" template/.claude/skills/autopilot/ .claude/skills/autopilot/
# Expected: 4 lines mentioning the awardybot reference
```

### Execution Order

Task 1 → Task 2 → Task 3 → Task 4

Tasks 1 and 2 edit independent files in `template/` and can be done in either order, but
Task 3 must run AFTER both Task 1 and Task 2 because it copies template/ → .claude/.
Task 4 is the final acceptance check.

### Dependencies

- Task 3 depends on Task 1 AND Task 2 (sync = `cp` from template).
- Task 4 depends on Tasks 1, 2, 3 (verifies all 4 files).

### No Tests / No Code

This spec touches doc-only files inside `.claude/skills/autopilot/`. No unit tests,
integration tests, or scripts are involved. TDD steps are intentionally omitted —
the acceptance contract is the `grep` / `diff` checks in Task 4.

## Definition of Done

- [ ] `template/.claude/skills/autopilot/worktree-setup.md` step 5 содержит `git fetch origin develop` + `origin/develop` explicit base
- [ ] `template/.claude/skills/autopilot/autopilot-git.md` §2.4 — то же
- [ ] `.claude/skills/autopilot/*` оба файла sync'нуты с template
- [ ] WHY-комментарий в каждом из 4 мест с reference на awardybot TECH-1063
- [ ] Тестовый запуск `autopilot SPEC_ID` в любом DLD-репо (на dummy spec) — worktree создаётся от develop, PHASE 3 merge — ff-only

## Risk Assessment

**R2 (контейн):**
- 2 doc файла × 2 копии = 4 файла. Никакого кода, тестов, миграций.
- Полностью обратимо (revert commit).
- Не меняет существующее поведение для случая «cwd HEAD уже на develop» — добавляет гарантию для случая «cwd HEAD не на develop».
- Не влияет на пользователей DLD, которые ещё не пуллили template (фикс при следующем pull/setup-vps.sh).

## References

- **Awardybot incident:** TECH-1063 autopilot run (2026-05-24), commit `833e5994`
- **Awardybot memory:** `feedback_no_implicit_git_refs.md` — anti-pattern class
- **Related ADR-pattern:** ADR-021 (awardybot, pg_cron silent-skip), TECH-182 (DLD, orchestrator rebase autostash)
- **Template-sync rule:** `template/.claude/rules/template-sync.md`

## Drift Log

**Checked:** 2026-05-24 (planner pass, worktree `.worktrees/TECH-191/`)
**Result:** no_drift

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| `template/.claude/skills/autopilot/worktree-setup.md` | none (line 71–72 matches spec assumption) | none |
| `template/.claude/skills/autopilot/autopilot-git.md` | none (line 107 matches spec assumption; full block 102–109) | none |
| `.claude/skills/autopilot/worktree-setup.md` | none (byte-identical to template/) | none |
| `.claude/skills/autopilot/autopilot-git.md` | none (byte-identical to template/) | none |

### References Updated

None — spec was authored same day (2026-05-24), no time for drift.

### Plan Refinements

- Original 3-task plan → upgraded to 4 tasks for explicit per-file AFTER-state blocks.
- Added Task 2 explicit BEFORE/AFTER for `autopilot-git.md` (spec previously said "то же изменение" — required interpretation of variable substitution from `{ID}/{type}` to `${TASK_ID}/${BRANCH_PREFIX}`).
- Added `cp` mechanical sync recipe in Task 3 (safe because docs are not on `template-sync.md` "Files with DLD-specific extensions" list).
- Expanded Task 4 verification: 4 separate grep/diff checks instead of a single hand-wave.
- Documented "no tests" decision explicitly (R2 doc-only — TDD inapplicable).
