# QA Report: TECH-973 Hermes intake contract

**Date:** 2026-05-14
**Environment:** local repo (документационная задача)
**Trigger:** /qa TECH-973
**Spec status:** `queued` (не запускался autopilot)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 5     | 3    | 2    | 0       |

Спека частично реализована вручную (README + тесты есть), но **Task 2 (ADR-022)** и **Task 3 (OpenClaw → Hermes rename в 4 файлах)** не выполнены. При этом статус в backlog по-прежнему `queued`, callback не закрывал.

## Failures

### F1: ADR-022 отсутствует в architecture.md
**Severity:** Major
**Reproducibility:** Always
**Expected (Task 2, DoD):** строка `| ADR-022 | Hermes intake supervisor; QA/reflect не self-loop в inbox=queued | 2026-05 | ... |` в таблице ADR.
**Actual:** `grep -n "ADR-022" .claude/rules/architecture.md` → пусто. Последний ADR в файле — ADR-021.
**Steps to reproduce:**
1. `grep -n "ADR-022" .claude/rules/architecture.md`
2. Видим: 0 hits.

**User impact:** Агенты при context-load не видят канонического правила «только Hermes пишет `queued`». Регрессия источника снова приведёт к тому, что Spark получит сырой intake.
**Hint for developers:** Дописать ADR-022 в таблицу `.claude/rules/architecture.md` (после ADR-021), формулировка готова в спеке §Design/ADR-022.

### F2: OpenClaw → Hermes rename не выполнен
**Severity:** Major
**Reproducibility:** Always
**Expected (Task 3, AV-F2):** `grep -rn "OpenClaw" .claude/` = 0 hits (или одна сноска).
**Actual:** 11 живых упоминаний в 4 целевых файлах:

| Файл | Hits |
|------|------|
| `.claude/skills/reflect/SKILL.md` | 6 (строки 110, 131, 169, 178, 179, 182) |
| `.claude/skills/bughunt/completion.md` | 3 (10, 22, 60) |
| `.claude/skills/audit/night-mode.md` | 1 (91) |
| `.claude/rules/dependencies.md` | 1 (191) |

Дополнительно: в `ai/inbox/done/*.md` ещё ~4 файла с OpenClaw — это исторические inbox-айтемы, по Scope не трогаем (но стоит уточнить).

**Steps to reproduce:**
1. `grep -rn "OpenClaw" .claude/`
2. Видим 11 hits в 4 файлах из Scope.

**User impact:** Документация и инструкции агентов всё ещё ссылаются на удалённую систему. Новый contributor / LLM-агент при чтении правил получает неконсистентную модель (OpenClaw в reflect/SKILL.md vs Hermes в README.md).
**Hint for developers:** Текстовая замена «OpenClaw» → «Hermes» в 4 файлах. Семантика идентична (supervisor над inbox).

## Passed

| # | Check | Notes |
|---|-------|-------|
| 1 | AV-S1: `ai/inbox/README.md` существует | Task 1 ✓, файл создан, содержит таблицу статусов и ссылку «formerly known as OpenClaw» (строка 8) |
| 2 | AV-S2 / AV-F1: regression-тесты scan_inbox зелёные | `pytest -k scan_inbox` → **7 passed**, 0 failed. Task 4 ✓ |
| 3 | EC-5: README содержит таблицу со статусом `queued` | grep `\| queued \|` → hit |

## Blocked

Нет — все проверки удалось выполнить.

## Fixes Applied

Не вносил (выходит за Light Fix scope — это 2 непочатые задачи спеки, не trivial-typo).

## Definition of Done — текущий статус

- [x] `ai/inbox/README.md` создан
- [ ] **ADR-022 добавлен** — НЕ выполнено (F1)
- [ ] **OpenClaw → Hermes rename** — НЕ выполнено (F2)
- [x] 3 regression-теста зелёные
- [x] AV-S1, AV-S2, AV-F1 проходят
- [ ] **AV-F2 (grep OpenClaw = 0)** — FAIL

## Recommendation

Спека не готова к закрытию. 2 из 4 задач не выполнены. Варианты:
1. Запустить `/autopilot TECH-973` на остаток (ADR-022 + rename) — обе задачи doc-only, ~10 минут.
2. Сделать вручную (Edit на 4 файла + 1 строка в architecture.md). LOC < 30.

Статус в backlog/спеке оставлен `queued` — корректно, callback тут не при чём.
