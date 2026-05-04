---
id: TECH-176
type: TECH
status: queued
priority: P1
risk: R1
created: 2026-05-04
---

# TECH-176 — IMPL_GUARD: detect "already merged before started_at" instead of demoting

**Status:** queued
**Priority:** P1
**Risk:** R1 (затрагивает callback decision flow для всех проектов)

---

## Problem

`_has_implementation_commits` в `callback.py` запускает `git log --all --since=<started_at> -- <allowed_files>`. Если работа по спеке **уже была смержена в `develop` ДО** `started_at` текущего autopilot-прогона, лог пуст → guard демоутит `done → blocked` с reason `no_implementation_commits`. Autopilot ничего не пишет, потому что писать нечего → следующий dispatch повторяет цикл.

**Live precedent (2026-05-03):**
- `TECH-169` (circuit-breaker): merged `8d8756a` + merge `66e3800` 02.05. Spec осциллировал `queued ↔ blocked` 4+ цикла, пока его не закрыли руками коммитом `97cf05c` (04.05). Оператор делал `--reset-circuit` 8 раз.
- TECH-170 добавил `git log --all` (видит feature-branches), но `--since=started_at` остался — поэтому случай "merged до started_at" не покрыт.

**Almost-detection уже есть:** callback логирует `STATUS_SYNC: <spec> — spec already done at HEAD, skipping blocked (work likely on feature branch); resync backlog`. Эта ветка срабатывает только если `**Status:**` в `develop:HEAD` уже `done`. Когда оператор флипает `blocked → queued` (для повторного прогона), статус в HEAD = `queued`, и логика проваливается в обычный demote.

---

## Goal

Guard различает три состояния, не два:

| Состояние | Текущая логика | Должно быть |
|---|---|---|
| Коммиты есть в окне `started_at`-now | `done` ✓ | `done` ✓ |
| Коммиты в Allowed Files есть в `develop` целиком, помечены `<spec_id>` в subject/merge | `blocked` (demote) | `done` (auto-close, не demote) |
| Коммитов нет вообще | `blocked` (demote) | `blocked` (demote) ✓ |

**Принцип:** `_has_implementation_commits` отвечает на вопрос «была ли реальная реализация этой спеки», а не «делал ли что-то autopilot за последний прогон».

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `tests/integration/test_callback_already_merged.py`
- `.claude/rules/architecture.md`

---

## Tasks

1. **Добавить helper `_spec_has_merged_implementation(project_path, spec_id, allowed_files) -> bool`** в `callback.py`:
   - `git log --all --oneline --grep="<spec_id>" -- <allowed_files>` — non-empty → `True`.
   - Дополнительно ищет merge-коммиты по pattern `Merge <spec_id>` в subject (для merge-only веток).
   - Возвращает `False` если grep пустой ИЛИ если allowed_files пуст.

2. **Wire в `verify_status_sync`:** перед `_trip_circuit + demote` развилкой — если `_has_implementation_commits` вернул `False` (no commits since started_at), но `_spec_has_merged_implementation` вернул `True` — это **auto-close**:
   - `verdict = "auto_close"` в callback_decisions (новый verdict, `demoted=0`).
   - Спека → `done` (через `_apply_spec_status` + `_apply_backlog_status`).
   - Лог: `IMPL_GUARD: <spec> — already merged in develop (commits: <hashes>) → auto-close to done`.
   - НЕ trip circuit, НЕ записывать demote.

3. **ADR update:** дополнить ADR-018 / TECH-166 примечанием о двух модах guard'а: "implementation activity check" vs "implementation existence check".

4. **Tests** (`tests/integration/test_callback_already_merged.py`):
   - EC-1: tmpdir repo, commit с subject `feat(TECH-XXX): foo` в Allowed Files до `started_at`, autopilot ничего не пишет → spec auto-close to `done`.
   - EC-2: только обычные коммиты без grep-match → demote (текущее поведение).
   - EC-3: merge-коммит `Merge TECH-XXX: ...` → auto-close to `done`.
   - EC-4: regression — TECH-168 test corpus не падает.
   - EC-5: deterministic — verdict='auto_close' пишется в callback_decisions, NOT counted в circuit-breaker threshold.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | integration | spec_id в commit subject + 0 коммитов с started_at → auto-close to done |
| EC-2 | integration | merge `Merge TECH-XXX` без других коммитов в Allowed Files → auto-close |
| EC-3 | integration | 0 коммитов вообще + 0 merge → demote (старое поведение) |
| EC-4 | regression | TECH-168 callback test suite зелёный |
| EC-5 | deterministic | verdict='auto_close' в callback_decisions, demoted=0, не triggers circuit |

---

## Out of Scope

- Не меняем `_has_implementation_commits` — он остаётся "activity since started_at".
- Не строим merge-graph аналитику (это отдельный dashboard).
- `--grep="<spec_id>"` использует case-sensitive match; если в кодовой базе пишут `tech-176` lowercase — проблема владельца спеки. Документируем.

---

## Notes

Эта дыра — прямой триггер инцидента 03-04.05.2026, где TECH-169 (сам circuit-breaker) бесконечно демоутился petlей и блокировал claude-runner на 33 часа. Closing this gap делает orchestrator идемпотентным относительно повторных запусков уже-сделанных спек.
