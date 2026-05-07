---
id: TECH-173
type: TECH
status: queued
priority: P1
risk: R2
created: 2026-05-02
---

# TECH-173 — Rewrite orchestrator documentation (single source of truth)

**Status:** done
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
- `scripts/vps/check-doc-references.sh`

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

---

## Drift Log

**Checked:** 2026-05-02 UTC
**Result:** no_drift

Spec was created today (2026-05-02). All Allowed Files exist or are intentionally to-be-created:
- `~/.claude/projects/-root/memory/dld-orchestrator.md` — exists (162 lines, last meaningful update ~ARCH-161). To be REWRITTEN from scratch.
- `~/.claude/projects/-root/memory/orchestrator-runbook.md` — does not exist yet (T3 decides whether to create).
- `~/.claude/projects/-root/memory/orchestrator-architecture.excalidraw` — does not exist yet (T1 creates).
- `.claude/rules/architecture.md` — exists, ADR list current up to ADR-020.
- `CLAUDE.md`, `template/CLAUDE.md` — both exist.

Source-of-truth modules confirmed present and feature-complete per latest commits:
- `scripts/vps/callback.py` (1250 LOC) — contains `verify_status_sync`, `_parse_allowed_files_marker` (line ~582), plumbing commit via `update-index --cacheinfo` (line ~498), `_write_audit`/`_emit_audit` (lines 743, 913), `<!-- callback-allowlist v1 -->` marker convention.
- `scripts/vps/orchestrator.py` (493 LOC) — main loop, signal handling, project hot-reload.
- TECH-169 circuit breaker, TECH-171 audit log, TECH-172 single-status-write-path all merged on develop.

No solution-verification research needed: this is a pure documentation task. Sources of truth are the code modules listed above plus existing ADRs.

---

## Implementation Plan

Each task is a discrete write/edit operation on a documentation artifact. No source code is modified. Tasks T1, T4, T5, T6, T8 can run in parallel; T2 must precede T3 and T7.

### Task 1: Generate Excalidraw architecture diagram

**File:** Create `~/.claude/projects/-root/memory/orchestrator-architecture.excalidraw`

**Method:** Invoke `/diagram` skill with description:
"DLD Orchestrator full task lifecycle. Show flow: Founder (Telegram/inbox/git push) → orchestrator.py poll loop (5min) → DB (project_state, compute_slots, task_log) → pueue queue → run-agent.sh dispatcher → claude-runner.py / codex-runner.sh / gemini-runner.sh → Skill execution (spark/autopilot/qa/reflect) → git commit+push → pueue completion → callback.py → verify_status_sync (parse Allowed Files marker, git log guard, plumbing commit) → spec+backlog status fix → event_writer → OpenClaw notification. Highlight callback critical path in red. Show circuit breaker (TECH-169) and audit log (TECH-171) as side annotations on callback box."

**Deliverable:** Excalidraw JSON file with named groups: `inbox`, `orchestrator-loop`, `pueue`, `runners`, `callback (critical)`, `notifications`. Embedded as image reference in §2 of `dld-orchestrator.md`.

**Acceptance:** File exists, opens in Excalidraw, callback path visually distinct (red/bold).

---

### Task 2: Rewrite `dld-orchestrator.md` from scratch (10 sections)

**File:** Overwrite `~/.claude/projects/-root/memory/dld-orchestrator.md`

**Outline per section** (target ~600-900 lines total before runbook decision):

- **§1 What is DLD Orchestrator** (1 paragraph, ~5 lines): per-VPS daemon coordinating multiple AI projects through pueue with SQLite SoT and pueue-callback status enforcement.
- **§2 Architecture** (~30 lines): embedded Excalidraw reference + textual ASCII fallback diagram + box descriptions. Mention layers: Entry (TG/inbox/git) → Loop (orchestrator.py) → Queue (pueue) → Runners → Callback → Notifications.
- **§3 Task Flow** (~40 lines): step-by-step Inbox → Spark → Backlog → Autopilot → Callback → QA → Reflect with state transitions per ADR-018. Reference Task Statuses table.
- **§4 Components** (~150 lines, one subsection per file with: path, role, key functions, dependencies, used-by):
  - 4.1 `orchestrator.py` (poll loop, hot-reload, slot acquisition, dispatch, orphan watchdog BUG-162)
  - 4.2 `run-agent.sh` (provider router, RAM floor)
  - 4.3 `claude-runner.py` (Agent SDK), `codex-runner.sh`, `gemini-runner.sh`
  - 4.4 `callback.py` — main focus, expand: resolve_label, parse_label, verify_status_sync, _parse_allowed_files_marker, plumbing commit, circuit breaker, audit log
  - 4.5 `db.py` + `schema.sql` (project_state, compute_slots, task_log, night_findings)
  - 4.6 `event_writer.py` + OpenClaw integration
- **§5 Callback contract** (~120 lines, the critical section):
  - 5.1 When invoked (pueue.yml callback config, arg order `id group result`)
  - 5.2 What it does (verify_status_sync flow: read spec → read backlog → resolve authority → optional guard → plumbing commit → audit emit)
  - 5.3 Guard semantics: `<!-- callback-allowlist v1 -->` marker convention (TECH-167), parser at `callback.py:582`, degrade-closed when marker missing/malformed (TECH-166), mixed-semantics rules
  - 5.4 Plumbing commit: explain `git hash-object -w` + `git update-index --cacheinfo` at `callback.py:498`. Why NOT `git add` (working tree contamination, race vs autopilot).
  - 5.5 Status authority order: spec `**Status:**` field > backlog table > DB. Spec wins ties.
- **§6 ADR list for orchestrator** (~25 lines): table of ADR-017 (SQL via parameterized queries), ADR-018 (callback status enforcement, extended TECH-166), ADR-019 (model routing), ADR-020 (no headless wrapper); plus TECH-166, TECH-167, TECH-168 (test suite), TECH-169 (circuit breaker), TECH-170 (guard feature branch), TECH-171 (audit log), TECH-172 (single status write path), TECH-174 (manual verification).
- **§7 Runbook** (~150 lines if inline, or pointer to extracted file per T3): 6 scenarios per Goal — N specs blocked / spec stuck in_progress / parser misses Allowed Files / force done manually / disable guard temporarily / add new project.
- **§8 Manual verification protocol** (~10 lines): pointer to `ai/features/TECH-174-*.md` with quick-reference of the steps.
- **§9 Tests** (~15 lines): pointer to `tests/unit/test_callback_*`, `tests/integration/test_callback_*`, `tests/regression/test_callback_*` with one-line description per file.
- **§10 Glossary** (~30 lines): worktree, callback, slot, phase, plumbing-commit, allowlist marker, degrade-closed, circuit breaker, audit log, OpenClaw, Agent SDK.

**Acceptance:** EC-1 (10 sections present), EC-2, EC-3, EC-4 all pass. Document opens cleanly in Markdown.

---

### Task 3: Decide runbook extraction

**File:** Conditionally create `~/.claude/projects/-root/memory/orchestrator-runbook.md`

**Decision rule:** If §7 in T2 exceeds ~150 lines, EXTRACT to standalone file:
- Move all six scenarios to `orchestrator-runbook.md` with same headings.
- Replace §7 in `dld-orchestrator.md` with a 10-line index: scenario titles + link `См. orchestrator-runbook.md`.
- Add header to runbook: "Companion to dld-orchestrator.md §7. Each scenario: symptom → diagnose → fix → verify."

**If §7 ≤ 150 lines:** keep inline, do NOT create separate file. Document decision in T2 commit message.

**Acceptance:** Either both files exist with cross-link, or only `dld-orchestrator.md` with full inline §7. EC-5 still passes (6 scenarios documented).

---

### Task 4: Update DLD root `CLAUDE.md` — short orchestrator pointer

**File:** Edit `/home/dld/projects/dld/CLAUDE.md`

**Change:** The existing block titled "DLD Orchestrator Reference" already points to `~/.claude/projects/-root/memory/dld-orchestrator.md`. Verify pointer line is present and add a 3-5 line summary above it:

```markdown
## DLD Orchestrator Reference

VPS daemon coordinating multi-project AI execution via pueue + SQLite SoT.
Callback enforces spec/backlog status atomically (ADR-018). Critical path:
pueue completion → callback.py → verify_status_sync → plumbing commit.

Full docs: ~/.claude/projects/-root/memory/dld-orchestrator.md
Runbook:   ~/.claude/projects/-root/memory/orchestrator-runbook.md (if extracted in T3)
```

**Do NOT duplicate** architecture, command tables, ADR lists. Keep block under 15 lines.

**Acceptance:** Block exists, ≤15 lines, no duplication of §4/§5/§7 content.

---

### Task 5: Update `template/CLAUDE.md` — same pointer (universal)

**File:** Edit `/home/dld/projects/dld/template/CLAUDE.md`

**Change:** Mirror Task 4 exactly. Template version uses identical wording so new DLD-cloned projects get the same pointer. Per `template-sync.md` policy: edit template first if change is universal — this one is universal (every DLD instance has the orchestrator), so T5 should actually be authored before T4 if order matters. In practice both can be done in same task block.

**Acceptance:** `diff CLAUDE.md template/CLAUDE.md` shows only project-specific lines (project name, stack), not orchestrator block.

---

### Task 6: Update `.claude/rules/architecture.md` — forward-pointer ADRs

**File:** Edit `/home/dld/projects/dld/.claude/rules/architecture.md`

**Changes:**
1. In ADR table, after ADR-020, append rows for TECH-166...172 as "Forward-pointer ADRs" — short one-line entries that say e.g. `TECH-166 | Callback guard: implementation commit verification | 2026-04 | See dld-orchestrator.md§6`.
2. Update ADR-018 row description to include reference: "...See dld-orchestrator.md§5 for full callback contract."
3. Add note at top of ADR section: "Orchestrator-specific decisions (callback contract, guard, audit log) are documented in `~/.claude/projects/-root/memory/dld-orchestrator.md` §6. This file lists project-wide ADRs only; orchestrator details are forward-pointed."

**Do NOT** copy verify_status_sync semantics or plumbing-commit rationale into this file — keep it as a pointer.

**Acceptance:** ADR table includes TECH-166...172 rows, all pointing to dld-orchestrator.md§6. EC-4 passes (ADR list complete).

---

### Task 7: Cross-references — replace duplicate content with pointers

**Files:** Sweep all files in Allowed Files plus `.claude/rules/dependencies.md` (read-only check, no edit unless duplication found).

**Action per file:**
- Search for paragraphs that re-explain callback flow, guard semantics, plumbing commit, or status authority order.
- Replace with: `См. dld-orchestrator.md§N` (Russian, matching project language convention) where N is the matching section.
- Preserve dependencies.md tables (those are SoT for dependency direction, not duplicates).

**Specific spots to check:**
- `CLAUDE.md` — "Callback Enforcement (DLD-specific)" block currently has 5 lines of detail. Replace verbose detail with one line + pointer to §5.
- `template/CLAUDE.md` — same as above.
- `.claude/rules/architecture.md` — ADR-018 row description (already done in T6).

**Acceptance:** No paragraph longer than 3 lines duplicates content from `dld-orchestrator.md` §4-§7. EC-7 lint passes.

---

### Task 8: Lint check shell script — verify ADR/TECH-IDs exist

**File:** Create `/home/dld/projects/dld/scripts/vps/check-doc-references.sh`

**Outline (no code, just spec):**
- Header: `#!/usr/bin/env bash` + `set -euo pipefail`.
- Purpose: read `~/.claude/projects/-root/memory/dld-orchestrator.md`, extract all tokens matching `ADR-\d{3}` and `TECH-\d{3}`.
- For each `ADR-NNN`: grep for it in `.claude/rules/architecture.md`. Fail if not found.
- For each `TECH-NNN`: grep recursively in `ai/features/` for filename matching `TECH-NNN-*.md`. Fail if not found.
- Also lint: every `См. dld-orchestrator.md§N` pointer in CLAUDE.md / template/CLAUDE.md / architecture.md must point to N where the heading `## §N` (or numbered heading) exists in dld-orchestrator.md.
- Exit non-zero with clear error per missing reference.
- Output format: one line per check, `OK ADR-018` or `MISSING TECH-999 in ai/features/`.
- Designed for CI invocation: stdout summary, exit code 0/1.

**Note:** Since target file lives in `~/.claude/projects/-root/memory/`, lint script must accept env override `DLD_ORCH_DOC=/path/to/dld-orchestrator.md` for test environments where home path differs.

**Acceptance:** Running `bash scripts/vps/check-doc-references.sh` after T1-T7 complete returns exit 0. Intentionally breaking a reference (e.g., adding `TECH-999` to dld-orchestrator.md) returns exit 1. EC-7 passes.

---

### Execution Order

```
T1 (diagram) ──┐
               ├──→ T2 (rewrite dld-orchestrator.md) ──→ T3 (decide runbook split)
T6 (ADR list) ─┘                                    │
                                                    ├──→ T7 (cross-refs sweep) ──→ T8 (lint script)
T4 (CLAUDE.md root) ──┐                             │
T5 (template CLAUDE.md) ─ parallel with T4 ─────────┘
```

### Dependencies

- T2 depends on T1 (diagram referenced in §2) and T6 (ADR list canonicalized).
- T3 depends on T2 (decision based on §7 length).
- T7 depends on T2 + T3 + T4 + T5 + T6 (sweeps all touched files).
- T8 depends on T7 (lint runs against final state).
- T4 and T5 are independent of each other but both must precede T7.

### Research Sources

None — task is documentation rewrite grounded entirely in current source code (`scripts/vps/callback.py`, `orchestrator.py`, `db.py`, `run-agent.sh`) and existing ADRs (017-020) plus referenced TECH specs (166-174).

