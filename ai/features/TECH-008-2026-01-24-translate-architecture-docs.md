# TECH: [TECH-008] Translate Architecture Docs (01-08)

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

Architecture docs (01-08) are in Russian. Need English for international launch.

## Solution

Translate 8 architecture documentation files to English.

---

## Scope

**In scope:**
- `docs/01-principles.md`
- `docs/02-naming.md`
- `docs/03-project-structure.md`
- `docs/04-claude-md-template.md`
- `docs/05-domain-template.md`
- `docs/06-cross-domain.md`
- `docs/07-antipatterns.md`
- `docs/08-metrics.md`

**Out of scope:**
- Changing structure
- Adding new content

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `docs/01-principles.md` | modify | Translate |
| 2 | `docs/02-naming.md` | modify | Translate |
| 3 | `docs/03-project-structure.md` | modify | Translate |
| 4 | `docs/04-claude-md-template.md` | modify | Translate |
| 5 | `docs/05-domain-template.md` | modify | Translate |
| 6 | `docs/06-cross-domain.md` | modify | Translate |
| 7 | `docs/07-antipatterns.md` | modify | Translate |
| 8 | `docs/08-metrics.md` | modify | Translate |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Translate 01-04

**Files:**
- Modify: `docs/01-principles.md`
- Modify: `docs/02-naming.md`
- Modify: `docs/03-project-structure.md`
- Modify: `docs/04-claude-md-template.md`

**Steps:**
1. Read each file
2. Translate all Russian text to English
3. Keep code examples unchanged
4. Preserve markdown formatting and tables

**Acceptance:**
- [ ] All 4 files translated
- [ ] No Russian text remains

### Task 2: Translate 05-08

**Files:**
- Modify: `docs/05-domain-template.md`
- Modify: `docs/06-cross-domain.md`
- Modify: `docs/07-antipatterns.md`
- Modify: `docs/08-metrics.md`

**Steps:**
1. Read each file
2. Translate all Russian text to English
3. Keep code examples unchanged
4. Preserve tables and diagrams

**Acceptance:**
- [ ] All 4 files translated
- [ ] No Russian text remains

---

## Execution Order

Task 1 → Task 2 (independent, can parallel)

---

## Definition of Done

### Functional
- [ ] All 8 files translated
- [ ] No Russian text remains
- [ ] Technical terms consistent

### Technical
- [ ] Valid markdown
- [ ] Tables render correctly

---

## Autopilot Log

*(Filled by Autopilot during execution)*
