# QA Report: TECH-973 — Hermes intake contract

**Date:** 2026-05-14
**Environment:** local-only (doc + regression tests)
**Trigger:** `/qa TECH-973` — verify deliverables of Hermes intake contract spec

## Pre-flight

- Spec status в backlog: `queued` (spec ещё не закрыт автопилотом).
- Deploy: N/A (DEPLOY_URL=local-only).
- CI: пропущена (локальная проверка).

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 5     | 3    | 2    | 0       |

Acceptance criteria из спека (EC-1..EC-5 + AV-S1..AV-F2):

| ID | Check | Result |
|----|-------|--------|
| EC-1 | `scan_inbox` игнорирует `draft` | ✓ PASS (test_scan_inbox_ignores_draft) |
| EC-2 | `scan_inbox` игнорирует clarifying/stale/rejected | ✓ PASS (test_scan_inbox_ignores_clarifying_stale_rejected, 3 параметризации) |
| EC-3 | `scan_inbox` диспатчит `queued` | ✓ PASS (test_scan_inbox_dispatches_queued) |
| EC-4 | `grep -rn "OpenClaw" .claude/` == 0 | ✗ FAIL — 11 hits в 4 файлах |
| EC-5 | `ai/inbox/README.md` существует и содержит таблицу со статусом `queued` | ✓ PASS |
| AV-F2 | `grep -rn "OpenClaw" .claude/` == 0 hits | ✗ FAIL — те же 11 hits |
| ADR-022 | строка `ADR-022` в `.claude/rules/architecture.md` | ✗ FAIL — 0 hits |

Pytest:
```
7 passed, 26 deselected in 0.73s
```

## Failures

### F1: OpenClaw → Hermes rename не выполнен

**Severity:** Major
**Reproducibility:** Always
**Expected (Task 3 / EC-4 / AV-F2):** `grep -rn "OpenClaw" .claude/` = 0 hits (или одна явная строка-сноска «бывший OpenClaw»).
**Actual:** 11 упоминаний OpenClaw в 4 файлах из Allowed Files:

| Файл | Кол-во упоминаний |
|------|-------------------|
| `.claude/skills/reflect/SKILL.md` | 5 (строки 110, 131, 169, 178, 179, 182) |
| `.claude/skills/bughunt/completion.md` | 3 (строки 10, 22, 60) |
| `.claude/skills/audit/night-mode.md` | 1 (строка 91) |
| `.claude/rules/dependencies.md` | 1 (строка 191, «notify() — send OpenClaw event») |

**Steps to reproduce:** `grep -rn "OpenClaw" .claude/`
**User impact:** Агенты (reflect, bughunt, audit) продолжают ссылаться на несуществующий OpenClaw — LLM-агенты получают противоречивый сигнал: README говорит «Hermes (formerly OpenClaw)», а оперативные инструкции скиллов говорят «OpenClaw reviews…». Это ровно тот failure-mode, ради которого писался спек.
**Hint:** Task 3 спека прямо требует rename в этих 4 файлах. `ai/inbox/README.md` содержит явную привязку «formerly known as OpenClaw», поэтому в инструкциях скиллов можно делать чистый replace `OpenClaw` → `Hermes`.

### F2: ADR-022 не добавлен в architecture.md

**Severity:** Major
**Reproducibility:** Always
**Expected (Task 2 / Design):** Строка `| ADR-022 | Hermes intake supervisor… | 2026-05 | … |` в ADR-таблице.
**Actual:** `grep -c "ADR-022" .claude/rules/architecture.md` = 0.
**Steps to reproduce:** open `.claude/rules/architecture.md`, scroll to ADR table — последняя запись ADR-021.
**User impact:** Hermes-контракт не зафиксирован в SSOT архитектурных решений. Context-loader агентов не подтянет инвариант «QA/reflect не пишут queued в inbox» как ADR — он остаётся только в README, который читают не все агенты.
**Hint:** добавить строку после ADR-021, дата 2026-05, формулировка из Design-секции спека.

## Blocked

Нет.

## Fixes Applied

Не применялись — изменения выходят за рамки «<5 LOC light fix» (rename в 4 файлах + ADR).

## Passed

| # | Сценарий | Заметка |
|---|----------|---------|
| 1 | `ai/inbox/README.md` существует, таблица статусов на месте, ссылается на `scan_inbox` и `_VALID_STATUSES`. | EC-5/AV-S1 |
| 2 | Pytest `scan_inbox` suite: 7/7 зелёные. | EC-1/EC-2/EC-3/AV-F1 |
| 3 | Backlog содержит TECH-973 в статусе `queued`. | sanity |

## Verdict

Спек TECH-973 **частично доставлен**:
- Task 1 (README) — ✓ done.
- Task 4 (regression tests) — ✓ done, 7 тестов зелёные.
- Task 2 (ADR-022) — ✗ **не сделан**.
- Task 3 (OpenClaw → Hermes rename) — ✗ **не сделан**, 11 упоминаний в 4 файлах.

Статус `queued` в backlog корректен — автопилот не закрывал задачу, и закрывать пока нельзя: 2 из 4 задач спека не выполнены.

## Recommendation

Дать автопилоту доделать Task 2 + Task 3 (это чистый текстовый rename + одна строка в таблице ADR). После этого `grep -rn "OpenClaw" .claude/` должно вернуть 0, и AV-F2 проходит.
