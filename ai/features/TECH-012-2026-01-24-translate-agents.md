# TECH: [TECH-012] Translate All Agent Prompts

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

Agent prompt files contain Russian text. Need English for international launch.

## Solution

Translate all agent prompt files to English.

---

## Scope

**In scope:**
- `template/.claude/agents/coder.md`
- `template/.claude/agents/debugger.md`
- `template/.claude/agents/diary-recorder.md`
- `template/.claude/agents/documenter.md`
- `template/.claude/agents/planner.md`
- `template/.claude/agents/review.md`
- `template/.claude/agents/scout.md`
- `template/.claude/agents/spark.md`
- `template/.claude/agents/spec-reviewer.md`
- `template/.claude/agents/tester.md`
- `template/.claude/agents/council/architect.md`
- `template/.claude/agents/council/pragmatist.md`
- `template/.claude/agents/council/product.md`
- `template/.claude/agents/council/security.md`
- `template/.claude/agents/council/synthesizer.md`
- `template/.claude/agents/_shared/context-loader.md`
- `template/.claude/agents/_shared/context-updater.md`
- `template/.claude/rules/architecture.md`
- `template/.claude/rules/domains/_template.md`
- `template/.claude/rules/dependencies.md`

**Out of scope:**
- Changing agent logic
- Adding new agents

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/agents/coder.md` | modify | Translate |
| 2 | `template/.claude/agents/debugger.md` | modify | Translate |
| 3 | `template/.claude/agents/diary-recorder.md` | modify | Translate |
| 4 | `template/.claude/agents/documenter.md` | modify | Translate |
| 5 | `template/.claude/agents/planner.md` | modify | Translate |
| 6 | `template/.claude/agents/review.md` | modify | Translate |
| 7 | `template/.claude/agents/scout.md` | modify | Translate |
| 8 | `template/.claude/agents/spark.md` | modify | Translate |
| 9 | `template/.claude/agents/spec-reviewer.md` | modify | Translate |
| 10 | `template/.claude/agents/tester.md` | modify | Translate |
| 11 | `template/.claude/agents/council/architect.md` | modify | Translate |
| 12 | `template/.claude/agents/council/pragmatist.md` | modify | Translate |
| 13 | `template/.claude/agents/council/product.md` | modify | Translate |
| 14 | `template/.claude/agents/council/security.md` | modify | Translate |
| 15 | `template/.claude/agents/council/synthesizer.md` | modify | Translate |
| 16 | `template/.claude/agents/_shared/context-loader.md` | modify | Translate |
| 17 | `template/.claude/agents/_shared/context-updater.md` | modify | Translate |
| 18 | `template/.claude/rules/architecture.md` | modify | Translate |
| 19 | `template/.claude/rules/domains/_template.md` | modify | Translate |
| 20 | `template/.claude/rules/dependencies.md` | modify | Translate |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Translate Core Agents

**Files:**
- Modify: `template/.claude/agents/coder.md`
- Modify: `template/.claude/agents/planner.md`
- Modify: `template/.claude/agents/tester.md`
- Modify: `template/.claude/agents/review.md`
- Modify: `template/.claude/agents/debugger.md`

**Acceptance:**
- [ ] All 5 files translated

### Task 2: Translate Utility Agents

**Files:**
- Modify: `template/.claude/agents/spark.md`
- Modify: `template/.claude/agents/scout.md`
- Modify: `template/.claude/agents/documenter.md`
- Modify: `template/.claude/agents/diary-recorder.md`
- Modify: `template/.claude/agents/spec-reviewer.md`

**Acceptance:**
- [ ] All 5 files translated

### Task 3: Translate Council Agents

**Files:**
- Modify: `template/.claude/agents/council/architect.md`
- Modify: `template/.claude/agents/council/pragmatist.md`
- Modify: `template/.claude/agents/council/product.md`
- Modify: `template/.claude/agents/council/security.md`
- Modify: `template/.claude/agents/council/synthesizer.md`

**Acceptance:**
- [ ] All 5 files translated

### Task 4: Translate Shared & Rules

**Files:**
- Modify: `template/.claude/agents/_shared/context-loader.md`
- Modify: `template/.claude/agents/_shared/context-updater.md`
- Modify: `template/.claude/rules/architecture.md`
- Modify: `template/.claude/rules/domains/_template.md`
- Modify: `template/.claude/rules/dependencies.md`

**Acceptance:**
- [ ] All 5 files translated

---

## Execution Order

Task 1 → Task 2 → Task 3 → Task 4 (can parallel)

---

## Definition of Done

### Functional
- [ ] All 20 files translated
- [ ] No Russian text remains
- [ ] Agent prompts still work

### Technical
- [ ] Valid markdown
- [ ] Consistent terminology

---

## Autopilot Log

- **2026-01-25**: All 20 files translated/verified
  - **Modified:** `coder.md` - translated Module Header Format
  - **Modified:** `documenter.md` - translated "Формат записи"
  - **Modified:** `architecture.md`, `_template.md`, `dependencies.md` - translated
  - **Verified:** All other files already in English
- grep for Cyrillic found 0 matches in agents/ and rules/
