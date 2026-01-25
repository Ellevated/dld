# TECH: [TECH-010] Translate LLM Workflow Docs (15-19)

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

LLM workflow docs (15-19) are in Russian. Need English for international launch.

## Solution

Translate 5 LLM workflow documentation files to English.

---

## Scope

**In scope:**
- `docs/15-skills-setup.md`
- `docs/16-forbidden.md`
- `docs/17-backlog-management.md`
- `docs/18-spec-template.md`
- `docs/19-living-architecture.md`

**Out of scope:**
- Changing structure
- Adding new content

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `docs/15-skills-setup.md` | modify | Translate |
| 2 | `docs/16-forbidden.md` | modify | Translate |
| 3 | `docs/17-backlog-management.md` | modify | Translate |
| 4 | `docs/18-spec-template.md` | modify | Translate |
| 5 | `docs/19-living-architecture.md` | modify | Translate |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Translate 15-17

**Files:**
- Modify: `docs/15-skills-setup.md`
- Modify: `docs/16-forbidden.md`
- Modify: `docs/17-backlog-management.md`

**Steps:**
1. Read each file
2. Translate all Russian text to English
3. Keep code examples unchanged
4. Preserve tables and diagrams

**Acceptance:**
- [ ] All 3 files translated
- [ ] No Russian text remains

### Task 2: Translate 18-19

**Files:**
- Modify: `docs/18-spec-template.md`
- Modify: `docs/19-living-architecture.md`

**Steps:**
1. Read each file (19 is large ~19KB)
2. Translate all Russian text to English
3. Keep code/template examples unchanged
4. Preserve markdown formatting

**Acceptance:**
- [ ] Both files translated
- [ ] No Russian text remains

---

## Execution Order

Task 1 → Task 2 (independent, can parallel)

---

## Definition of Done

### Functional
- [ ] All 5 files translated
- [ ] No Russian text remains
- [ ] Templates still usable

### Technical
- [ ] Valid markdown
- [ ] Template examples work

---

## Autopilot Log

- **2026-01-25**: All 5 files translated to English
  - `docs/15-skills-setup.md` - already in English
  - `docs/16-forbidden.md` - already in English
  - `docs/17-backlog-management.md` - translated
  - `docs/18-spec-template.md` - translated
  - `docs/19-living-architecture.md` - translated
- No Russian text remains, structure preserved
