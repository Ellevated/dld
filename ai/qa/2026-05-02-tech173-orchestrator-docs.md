# QA Report: TECH-173 — Orchestrator docs rewrite

**Date:** 2026-05-02
**Environment:** локальные файлы документации (продукт = docs)
**Trigger:** `/qa TECH-173` — проверить что переписанная документация оркестратора соответствует Eval Criteria

## Pre-flight

- Deploy gate: N/A (документация, не runtime).
- CI gate: пропущен (изменения только в `~/.claude/projects/-root/memory/` + docs).
- Все Allowed Files существуют.

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 8     | 8    | 0    | 0       |

EC-6 (LLM-judge «может ли новый человек добавить feature без вопросов») — не выполнен автоматически, требует отдельного `/eval` прогона. Отмечен ниже как известный gap, но в скоп ручного QA не входит.

## Passed

| # | Сценарий | Проверка | Результат |
|---|---------|----------|-----------|
| 1 | EC-1: 10 разделов в `dld-orchestrator.md` | `grep "^## §"` | §1–§10 все на месте (lines 10, 21, 92, 156, 350, 477, 499, 514, 531, 553) |
| 2 | EC-2: каждый компонент в §4 имеет файл/путь + описание | Подразделы 4.1–4.6 | 6 подразделов: orchestrator.py, run-agent.sh, runners, callback.py, db.py+schema.sql, event_writer.py |
| 3 | EC-3: §5.3 описывает parser-конвенцию и degrade-closed | `grep "callback-allowlist v1\|degrade-closed"` | Маркер v1 описан (line 392), парсер на callback.py:582 упомянут, degrade-closed раскрыт |
| 4 | EC-4: §6 ADR list актуален (017-020 + TECH-166...172, 174) | Чтение ADR-таблицы lines 477-499 | Все 12 ADR/TECH-IDs присутствуют с описаниями и датами |
| 5 | EC-5: §7 Runbook покрывает 6 сценариев | Runbook вынесен в `orchestrator-runbook.md` (T3 решение) | 6 сценариев: blocked / stuck in_progress / parser misses / force done / disable guard / add project |
| 6 | EC-7: lint check проходит | `bash scripts/vps/check-doc-references.sh` | Exit 0, 17 OK checks (4 ADR + 8 TECH + 1 spec + 4 §-pointers) |
| 7 | Excalidraw диаграмма создана | `ls orchestrator-architecture.excalidraw` | 11713 байт, валидный Excalidraw JSON |
| 8 | Forward-pointers в `architecture.md` | Чтение `.claude/rules/architecture.md` ADR-секции | TECH-166...172, 174 строки добавлены, ссылаются на dld-orchestrator.md§6, дублирования verify_status_sync семантики нет |

## Cosmetic notes (не блокирующие)

### N1: Heading `## Allowed Files` внутри code-block § 5.3 ловится наивным `grep "^## "`

**Severity:** Cosmetic
**Где:** `dld-orchestrator.md:398` — это пример формата спеки внутри fenced code block.
**Симптом:** При парсинге секций через `grep "^## "` появляется лишняя «секция». На рендеринг markdown не влияет (внутри code-блока). EC-1 проходит — все 10 §-секций целы.
**User impact:** Никакого для читателя. Только при автоматическом подсчёте секций глупым grep'ом. Можно проигнорировать или заменить пример на `### Allowed Files` чтобы не путать tooling.

### N2: EC-6 (LLM-judge) не выполнен в рамках QA

**Severity:** Minor (out of QA scope)
**Что:** Eval criterion EC-6 требует LLM-judge прогон с rubric «может ли новый человек добавить feature без вопросов».
**User impact:** Документация выглядит полной по структуре, но субъективное качество «понятности для новичка» формально не измерено. Для полного закрытия — запустить `/eval` против EC-6 отдельно.

## Fixes Applied

Нет — все 8 проверок прошли, light fixes не потребовались.

## Handoff

TECH-173 со стороны deterministic eval criteria — реально done. Багов уровня Critical/Major не найдено, спеки на исправления не нужны.

Опционально: запустить `/eval` для EC-6, если хочется формально закрыть LLM-judge критерий.
