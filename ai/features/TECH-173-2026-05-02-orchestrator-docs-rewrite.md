---
id: TECH-173
type: TECH
status: queued
priority: P1
risk: R2
created: 2026-05-02
---

# TECH-173 — Rewrite orchestrator documentation (single source of truth)

**Status:** queued
**Priority:** P1
**Risk:** R2

---

## Problem

Документация оркестратора фрагментирована и устарела:

| Источник | Что описывает | Состояние |
|---|---|---|
| `~/.claude/projects/-root/memory/dld-orchestrator.md` | Архитектура, команды, lifecycle | Last update ~ARCH-161 (март 2026), не отражает TECH-166/refactor 02.05 |
| `.claude/rules/architecture.md` (DLD root) | ADR list, anti-patterns | Актуален до ADR-020 |
| `.claude/rules/dependencies.md` | Dependency map scripts/vps/ | Актуален |
| `CLAUDE.md` (DLD project) | High-level, skill triggers | Не описывает callback flow |
| Inline docstrings в `callback.py`/`orchestrator.py` | Function-level | Частично актуальны |

Новый человек (или новая агентная итерация) повторит сегодняшние ошибки, потому что:
- Не понимает контракт callback ↔ verify_status_sync.
- Не знает про plumbing-commit (вернёт `git add`).
- Не знает про `## Allowed Files` parser конвенцию.
- Не знает про circuit-breaker (после TECH-169) и audit log (после TECH-171).

---

## Goal

Один **single source of truth** для оркестратора: `~/.claude/projects/-root/memory/dld-orchestrator.md`, переписан с нуля под текущее состояние и расширяем под будущее.

Структура нового документа:

```
1. Что такое DLD Orchestrator (1 параграф)
2. Архитектура — диаграмма (Excalidraw через /diagram) + текстовое описание
3. Поток задачи: Inbox → Spark → Backlog → Autopilot → Callback → QA → Reflect
4. Компоненты:
   4.1. orchestrator.py (main loop, диспатчер)
   4.2. run-agent.sh (provider router)
   4.3. claude-runner.py / codex-runner.sh / gemini-runner.sh
   4.4. callback.py (status enforcement) ← главный focus
   4.5. db.py + schema.sql (SQLite SoT)
   4.6. event_writer.py + OpenClaw integration
5. Контракт callback:
   5.1. Когда вызывается (pueue.yml callback config)
   5.2. Что делает (verify_status_sync flow)
   5.3. Guard semantics: ## Allowed Files marker, degrade-closed, mixed semantics
   5.4. Plumbing commit (почему через update-index, не git add)
   5.5. Status authority order: spec > backlog
6. ADR list для оркестратора (017, 018, 020, TECH-166, TECH-167...171)
7. Runbook:
   7.1. "N специй внезапно blocked" — diagnose + reset (через TECH-169)
   7.2. "Спека застряла in_progress" — manual recovery
   7.3. "Парсер не видит мою секцию ## Allowed Files" — debug
   7.4. "Хочу форсировать done вручную" — operator override
   7.5. "Хочу временно отключить guard" — emergency switch
   7.6. "Добавить новый проект в orchestrator" — projects.json + nexus
8. Manual verification protocol — линк на TECH-174
9. Тесты — линк на tests/{unit,integration,regression}/test_callback_*
10. Glossary (worktree, callback, slot, phase, etc.)
```

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `~/.claude/projects/-root/memory/dld-orchestrator.md`
- `~/.claude/projects/-root/memory/orchestrator-runbook.md`
- `~/.claude/projects/-root/memory/orchestrator-architecture.excalidraw`
- `.claude/rules/architecture.md`
- `CLAUDE.md`
- `template/CLAUDE.md`

---

## Tasks

1. **Excalidraw diagram** через `/diagram` — full orchestrator flow с подсветкой callback critical path.
2. **`dld-orchestrator.md` rewrite** — 10 секций per Goal.
3. **Runbook extract** в отдельный `orchestrator-runbook.md` (если 7й раздел становится длинным).
4. **CLAUDE.md** (DLD root + template) — короткая выжимка + линки. Не дублировать.
5. **architecture.md** — синхронизировать ADR list (170-175 после исполнения TECH-167...171).
6. **Cross-references** во всех файлах: `См. dld-orchestrator.md§5.3` вместо повторения.
7. **Lint check**: shell скрипт проверяет что все упомянутые ADR / TECH-IDs существуют. Запуск в CI.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | dld-orchestrator.md имеет все 10 разделов |
| EC-2 | deterministic | Каждый компонент в §4 имеет файл/путь + краткое описание |
| EC-3 | deterministic | §5.3 описывает текущую parser-конвенцию и degrade-closed (TECH-166/167) |
| EC-4 | deterministic | §6 ADR list актуален (включает 017-020 + TECH-166...171) |
| EC-5 | deterministic | §7 runbook покрывает 6 сценариев из Goal |
| EC-6 | integration | LLM-judge: «может ли новый человек после прочтения добавить feature без вопросов?» rubric: yes/no |
| EC-7 | deterministic | `lint check` cross-references проходит |
