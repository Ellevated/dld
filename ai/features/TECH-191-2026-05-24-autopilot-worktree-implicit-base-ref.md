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

### Task 1: Patch template/ (universal)

Заменить в `template/.claude/skills/autopilot/worktree-setup.md` step 5:

```bash
# BEFORE:
git worktree add ".worktrees/{ID}" -b "{type}/{ID}"

# AFTER:
# Refresh remote first — branch base MUST be fresh origin/develop, not stale local ref
git fetch origin develop
git worktree add ".worktrees/{ID}" -b "{type}/{ID}" origin/develop

# Why origin/develop explicit (not implicit HEAD):
#   `git worktree add -b new-branch path` without a base ref branches off
#   the CWD's current HEAD. If anything left cwd HEAD on main (broken prior
#   worktree, manual `git checkout main`, recovery state, orchestrator
#   improvisation) — the new branch inherits main and PHASE 3 merge into
#   develop drags unrelated main-only commits (dependabot bumps, release
#   merge-backs). Pin to origin/develop to guarantee base regardless of
#   CWD state. Reference: awardybot TECH-1063 incident, commit 833e5994.
```

То же изменение в `template/.claude/skills/autopilot/autopilot-git.md` §2.4 (line 107).

### Task 2: Sync .claude/ (DLD-specific copy)

Cherry-pick те же изменения из `template/.claude/skills/autopilot/*` в `.claude/skills/autopilot/*`.

Соответствует rule `template-sync.md`: «Universal improvement → edit template first, then sync to .claude/».

### Task 3: Verify

- `grep -rn "git worktree add" template/.claude/ .claude/` → каждая строчка должна содержать `origin/develop`
- Запустить мини-симуляцию (опционально): `git checkout main && bash -c '<строка из worktree-setup.md step 5>'` в test repo → проверить что worktree всё равно от develop

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
