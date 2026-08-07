# ADR Archive

Полные тексты записей из таблицы ADR в `.claude/rules/architecture.md`, помеченных
`[SUPERSEDED ...]` и вынесенных сюда 2026-07-30, чтобы не грузить контекст сессии
неактуальными решениями. `docs/` не попадает под `paths:` этого правила
(`packages/**`, `scripts/**`, `tests/**`, `test/**`), поэтому этот файл не подключается
автоматически. Ничего не удалено — таблица в `architecture.md` оставляет по одной
строке-указателю на каждую запись ниже.

Записи, помеченные `[AMENDED ...]` (например ADR-023), в архив **не** переносились —
они описывают действующую архитектуру в изменённой форме и остаются в основном файле.

## ADR-018 — Callback status enforcement via markdown editing

**Статус:** SUPERSEDED by ADR-023

> Callback status enforcement via markdown editing. Worked but suffered from autostash
> race (BUG-185 = formerly BUG-974). Replaced by ADR-023 lifecycle SoT. Historical: LLM
> status updates unreliable, callback auto-fixed spec+backlog with implementation guard
> (TECH-166), auto-close path (TECH-176). Degrades open. См. dld-orchestrator.md§5

## TECH-170 — Implementation guard sees feature-branch commits

**Статус:** SUPERSEDED ~2026-05-21

> Implementation guard sees feature-branch commits (`--all`). Guard переписан на чистый
> origin/develop-gate `_is_done_on_develop` — без `--all`, done только при коммите на
> origin/develop. См. `docs/orchestrator/status-model.md#guard`

## TECH-176 — Guard auto-close path

**Статус:** SUPERSEDED ~2026-05-21

> Guard auto-close path: detect "already merged before started_at" via
> `_spec_has_merged_implementation`. Auto-close + `_spec_has_merged_implementation`
> убраны при редизайне guard на origin/develop-gate. См.
> `docs/orchestrator/status-model.md#guard`
