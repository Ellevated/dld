---
id: TECH-168
type: TECH
status: queued
priority: P0
risk: R0
created: 2026-05-02
---

# TECH-168 — Callback test suite (unit + integration + regression)

**Status:** queued
**Priority:** P0
**Risk:** R0 (irreversible — без тестов любой regex-tweak в callback.py = silent regression во всех 5 проектах)

---

## Problem

`scripts/vps/callback.py` — единственная точка enforcement статусов спек по всему orchestrator-парку (5 проектов, ~1000 спек). За последние 36 часов в нём было сделано 4 правки (TECH-166 деплой → hotfix regex → degrade-closed refactor → broaden parser), и каждая деплоилась без unit-тестов. Только manual smoke на 1-2 спеках. Это игра в рулетку: regex broaden может случайно начать матчить лишнее, plumbing-commit может ломаться на edge-case'ах git'а, status-sync race может проявиться при concurrent callback'ах.

**Боль уже материализовалась:**
- TECH-166 v1 deploy: heading regex был `\s*$` end-of-line — пропускал `(whitelist)` суффикс. Час silent false-positive done на awardybot.
- TECH-166 refactor: формально работает, но без тестов нельзя доказать что `verify_status_sync` корректно обрабатывает все 6+ guard-веток (blocked-overwrite-protection, done-overwrite-protection, demote-from-impl-guard, missing-allowed-section, no-impl-commits, idempotent-already-synced).

---

## Goal

Полное тестовое покрытие `callback.py` с двумя уровнями:

1. **Unit** (быстрые, изолированные, не трогают git/db):
   - `_parse_allowed_files` — все формы heading/marker, fenced blocks, multiple sections.
   - `_apply_spec_status` / `_apply_backlog_status` / `_apply_blocked_reason` — корректные in-place text mutations.
   - `_skill_from_pueue_command`, `resolve_label`, `map_result` — pure helpers.
   - `_has_implementation_commits` с mocked subprocess.

2. **Integration** (tmpdir git repo + sqlite, реальные subprocess, 2-5 сек на тест):
   - `_git_commit_push` plumbing — НЕ трогает working tree, коммит чистый, push retry.
   - `verify_status_sync` end-to-end сценарии:
     - happy path (commits есть, mark done)
     - no-impl demote (allowed=4, 0 commits → blocked + reason)
     - missing section (degrade-closed)
     - empty section (degrade-closed)
     - blocked-overwrite-protection (target=done но spec=blocked)
     - done-overwrite-protection (target=blocked но spec=done)
     - HEAD already synced (idempotent, no commit)
     - operator's uncommitted edits in spec/backlog preserved
   - `_resync_backlog_to_spec` — sync to spec authority, idempotent.
   - `_get_started_at` — чтение из task_log.

3. **Regression** corpus:
   - Снепшот 50 живых спек awardybot/dowry/gipotenuza/plpilot/wb с известным parser output.
   - Любая правка regex'а ломает регрессию → fail в CI.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/db.py`
- `tests/unit/test_callback_helpers.py`
- `tests/unit/test_callback_parser.py`
- `tests/integration/test_callback_status_sync.py`
- `tests/integration/test_callback_plumbing_commit.py`
- `tests/regression/test_callback_spec_corpus.py`
- `tests/regression/spec_corpus/`
- `tests/regression/spec_corpus/awardybot_FTR-897.md`
- `tests/regression/spec_corpus/dowry_BUG-394.md`
- `tests/regression/spec_corpus/gipotenuza_FTR-098.md`
- `tests/regression/spec_corpus/plpilot_BUG-326.md`
- `tests/regression/spec_corpus/wb_ARCH-176a.md`
- `.github/workflows/test.yml`

---

## Tasks

1. **Unit: parser** — все форматы heading + marker (TECH-167) + invariants на edge-cases (Unicode paths, paths с пробелом в backticks, многострочные секции).
2. **Unit: text mutators** — `_apply_*` functions с golden inputs/outputs.
3. **Unit: helpers** — `_skill_from_pueue_command`, `resolve_label`, `map_result`.
4. **Integration: plumbing-commit** — tmpdir repo, симуляция operator-uncommitted-edits, проверить что они survive.
5. **Integration: verify_status_sync** — 8 сценариев из Goal.
6. **Regression corpus** — отобрать 5 спек по проекту (canonical / heading-variant / fenced-block / no-section / multiple-sections), сохранить как fixtures.
7. **CI wiring** — `.github/workflows/test.yml`, запуск на каждый PR в `scripts/vps/`. pytest+pytest-xdist.
8. **README** в `tests/` — как добавлять новые fixture-спеки + что считается breaking change.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Все unit-тесты зелёные локально |
| EC-2 | deterministic | Все integration-тесты зелёные |
| EC-3 | deterministic | Regression corpus 25 спек (5×5 проектов) проходит парсер с ожидаемым output |
| EC-4 | integration | CI запускается на PR, fail blockирует merge |
| EC-5 | integration | Operator-uncommitted-edits preserved в plumbing-commit (smoke test из TECH-166) автоматизирован |
| EC-6 | deterministic | Coverage report — callback.py >= 85% line coverage |
