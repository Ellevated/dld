# Feature: [TECH-073] Sync Autopilot Plan Policy (template ← root)

**Status:** done | **Priority:** P2 | **Date:** 2026-02-02

## Why

Root `.claude/` содержит улучшенную логику autopilot:
- Plan **ALWAYS** запускается для re-validation спеки против текущего состояния codebase
- Template использует устаревший подход "if no plan"

Это приводит к:
1. Пропуску валидации спеки если она уже содержит Implementation Plan
2. Потенциальному drift между спекой и реальным кодом
3. Отсутствию Exa verification для существующих планов

## Context

Рассинхрон возник после улучшений в root `.claude/`:
- SKILL.md: "PHASE 1: Plan (ALWAYS)" vs "PHASE 1: Plan"
- subagent-dispatch.md: "ALWAYS RUN — even if spec has plan" vs "Create detailed plan"

Template также содержит `task-loop.md` которого нет в root — нужно решить что делать с этим файлом.

---

## Scope

**In scope:**
- Синхронизация SKILL.md: template ← root
- Синхронизация subagent-dispatch.md: template ← root
- Добавление отсутствующего модуля или удаление лишнего

**Out of scope:**
- Изменение логики Plan (она уже правильная в root)
- Рефакторинг других частей autopilot

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — кто использует?

- [ ] `grep -r "SKILL.md" template/.claude/skills/autopilot/` → модули autopilot
- [ ] `grep -r "subagent-dispatch" template/.claude/skills/autopilot/` → SKILL.md ссылается

### Step 2: DOWN — от чего зависит?

- [ ] SKILL.md ссылается на subagent-dispatch.md, finishing.md, escalation.md, safety-rules.md
- [ ] subagent-dispatch.md — самостоятельный модуль

### Step 3: BY TERM — grep по проекту

- [ ] `grep -rn "if no plan" template/.claude/` → найти устаревшие формулировки
- [ ] `grep -rn "ALWAYS" .claude/skills/autopilot/` → подтвердить ALWAYS паттерн

### Step 4: CHECKLIST — обязательные папки

- [ ] `template/.claude/skills/autopilot/` — основная цель
- [ ] `.claude/skills/autopilot/` — reference (source of truth)

### Verification

- [ ] После изменений: diff между root и template должен показывать только DLD-specific кастомизации

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.claude/skills/autopilot/SKILL.md` — sync Plan ALWAYS policy
2. `template/.claude/skills/autopilot/subagent-dispatch.md` — sync dispatch template

**Files to evaluate (may need action):**

3. `template/.claude/skills/autopilot/task-loop.md` — решить: удалить или добавить в root

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Full Sync (Copy root → template)

**Summary:** Скопировать содержимое файлов из root в template
**Pros:** Гарантированная идентичность, простота
**Cons:** Может перезаписать template-specific изменения

### Approach 2: Patch Specific Sections

**Summary:** Изменить только конкретные секции с различиями
**Pros:** Сохраняет возможные template-specific изменения
**Cons:** Риск неполной синхронизации

### Selected: 1

**Rationale:** Файлы должны быть идентичны. Template — это универсальный шаблон, в нём не должно быть специфичных изменений. Root — source of truth после TECH-062 (где мы уже синхронизировали структуру).

---

## Design

### Changes Summary

**SKILL.md differences (root → template):**

| Line | Root (correct) | Template (outdated) |
|------|----------------|---------------------|
| ~37 | `PHASE 1: Plan (ALWAYS)` | `PHASE 1: Plan` |
| ~38 | `[Plan Agent] opus → validates spec + creates/updates tasks` | `[Plan Agent] opus → tasks in spec` |
| ~44 | `└─ DOCUMENTER (inline)` | `└─ PRE-CHECK (deterministic)` |
| ~76 | `PHASE 1: PLAN (ALWAYS — validates spec against current codebase)` | `PHASE 1: PLAN (if no detailed plan exists)` |
| ~77 | `[Plan Subagent] → re-validates + creates/updates detailed tasks` | `[Plan Subagent] → detailed tasks in spec` |
| ~139 | `PHASE 1: Plan (ALWAYS)` | `PHASE 1: Plan (if needed)` |
| ~140 | `Dispatch Plan Subagent — validates spec against current codebase...` | `Check for "## Implementation Plan"...` |
| ~165 | Missing pre-flight line about plan | Has extra check about plan |

**subagent-dispatch.md differences:**

| Line | Root (correct) | Template (outdated) |
|------|----------------|---------------------|
| ~5 | Missing | `**Execution Flow:** See task-loop.md...` |
| ~11 | `PHASE 1 (ALWAYS)` | `PHASE 1 (if no plan)` |
| ~29-42 | Full ALWAYS dispatch template | Basic dispatch template |

**task-loop.md:**
- Exists only in template
- Contains decision trees for PHASE 2 steps
- Root inlines this in subagent-dispatch.md

### Decision: task-loop.md

**Option A:** Add to root — нет, root уже имеет эту логику inline
**Option B:** Remove from template — да, унифицировать с root

### Migration Steps

1. Copy SKILL.md content from root to template
2. Copy subagent-dispatch.md content from root to template
3. Delete task-loop.md from template (its content is in subagent-dispatch.md)

---

## Implementation Plan

### Task 1: Sync SKILL.md

**Type:** code
**Files:**
  - modify: `template/.claude/skills/autopilot/SKILL.md`
**Source:** `.claude/skills/autopilot/SKILL.md`
**Acceptance:**
- `diff .claude/skills/autopilot/SKILL.md template/.claude/skills/autopilot/SKILL.md` returns empty
- Quick Reference shows "Plan (ALWAYS)"
- Architecture shows "PHASE 1: PLAN (ALWAYS — validates spec)"

### Task 2: Sync subagent-dispatch.md

**Type:** code
**Files:**
  - modify: `template/.claude/skills/autopilot/subagent-dispatch.md`
**Source:** `.claude/skills/autopilot/subagent-dispatch.md`
**Acceptance:**
- `diff .claude/skills/autopilot/subagent-dispatch.md template/.claude/skills/autopilot/subagent-dispatch.md` returns empty
- Plan Subagent section shows "ALWAYS RUN"
- No reference to task-loop.md

### Task 3: Remove task-loop.md from template

**Type:** code
**Files:**
  - delete: `template/.claude/skills/autopilot/task-loop.md`
**Acceptance:**
- File no longer exists
- No broken references (grep "task-loop" in template returns 0)

### Execution Order

1 → 2 → 3

---

## Flow Coverage Matrix (REQUIRED)

| # | Change | Covered by Task | Status |
|---|--------|-----------------|--------|
| 1 | SKILL.md Plan ALWAYS | Task 1 | ✓ |
| 2 | subagent-dispatch.md ALWAYS | Task 2 | ✓ |
| 3 | Remove task-loop.md | Task 3 | ✓ |
| 4 | No broken references | Task 3 acceptance | ✓ |

---

## Definition of Done

### Functional

- [ ] `diff .claude/skills/autopilot/SKILL.md template/.claude/skills/autopilot/SKILL.md` = empty
- [ ] `diff .claude/skills/autopilot/subagent-dispatch.md template/.claude/skills/autopilot/subagent-dispatch.md` = empty
- [ ] `template/.claude/skills/autopilot/task-loop.md` не существует
- [ ] `grep -r "task-loop" template/.claude/` = 0 results

### Technical

- [ ] Tests pass (./test fast) — N/A для markdown
- [ ] No regressions

---

## Autopilot Log

[Auto-populated by autopilot during execution]
