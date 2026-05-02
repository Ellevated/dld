---
id: TECH-170
type: TECH
status: queued
priority: P1
risk: R1
created: 2026-05-02
---

# TECH-170 — Implementation guard sees feature-branch commits, not just develop

**Status:** queued
**Priority:** P1
**Risk:** R1

---

## Problem

`_has_implementation_commits` запускает `git log --since=<started_at> -- <allowed>` в working directory проекта. Этот лог по умолчанию = **текущая ветка** (обычно `develop`). Если autopilot работал в `feature/FTR-XXX` worktree (per ADR-009: deterministic worktree cleanup) и ещё **не смержил** ветку обратно — guard видит 0 коммитов и демоутит спеку, хотя код реально написан.

**Live precedent:**
- awardybot/FTR-898 (02.05): по QA-логу "миграции wave 4+5 только в `feature/FTR-898`, не смержены, Tasks 3-17 не сделаны". Часть работы реально была — в feature-branch. Guard её не увидел.
- wb/ARCH-176a/b/c/d: похожий паттерн.

---

## Goal

Guard смотрит **во все ветки**, не только в текущую. Реализация:

1. **Расширить `git log` до `--all`**: `git log --all --since=<started_at> -- <allowed>`. Видны коммиты на любой ref, включая feature-branch'и worktree'ев.

2. **Хранить `branch_name` в `task_log`** для будущей точной фильтрации (опционально):
   - autopilot сейчас работает в `feature/<spec_id>` ветке (ADR-009).
   - При диспатче в pueue label содержит `<project_id>:<spec_id>`. Можем извлекать.
   - В `task_log` добавить колонку `branch` (nullable), записываем при диспатче.

3. **Различать "merged в develop" vs "только в feature"** — отдельная информация в callback log:
   - Если коммиты в feature-ветке но НЕ в develop → log warning `IMPL_GUARD: <spec> has commits on feature/<spec> but NOT merged to develop yet`.
   - Это **не блокирует mark-done** (работа есть), но видно в Telegram digest.

4. **Очищение**: после merge'а через `git merge --ff-only` от orchestrator'а — статус "merged", в callback log пишем `merged_at`. Не критично для mark-done, но важно для дашборда.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/orchestrator.py`
- `scripts/vps/db.py`
- `scripts/vps/schema.sql`
- `tests/unit/test_callback_branch_awareness.py`
- `tests/integration/test_callback_feature_branch.py`

---

## Tasks

1. **`_has_implementation_commits`**: добавить флаг `--all` в git log. Сохранить старое поведение через kwarg `branches="all"` для тестируемости.
2. **`task_log.branch`**: ALTER TABLE add column. Migration в `db.py::init_schema()` (idempotent). orchestrator.py при диспатче пишет `branch=feature/<spec_id>` (если применимо).
3. **`is_merged_to_develop(spec_id)`**: helper в callback.py — `git log develop --grep=<spec_id>` либо `git branch --merged develop`. Используется только для логов/dashboard.
4. **Tests** (integration): tmpdir-repo с feature-branch'ем, проверить что guard видит коммит на feature-branch'е и пропускает spec в done; merge → log "merged_at" обновляется.
5. **Update ADR**: ADR-018 (callback enforcement) — пометка о --all + feature-branch awareness.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | integration | Коммит в `feature/FTR-001`, develop пуст — guard returns True (allows done) |
| EC-2 | integration | Коммит в `feature/FTR-001`, спека merged в develop — guard True, log "merged_to_develop" |
| EC-3 | integration | Нет коммитов нигде — guard False (blocks done) |
| EC-4 | deterministic | task_log.branch заполняется при autopilot dispatch |
| EC-5 | regression | Существующие тесты TECH-168 не сломаны новым флагом --all |
