# TECH: [TECH-007] Translate Foundation Docs

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

Foundation docs are in Russian. For international open source launch, all documentation must be in English.

## Solution

Translate all foundation documentation to English while preserving structure and meaning.

---

## Scope

**In scope:**
- `docs/00-bootstrap.md`
- `docs/foundation/00-why.md`
- `docs/foundation/01-double-loop.md`
- `docs/foundation/02-agent-roles.md`

**Out of scope:**
- Changing document structure
- Adding new content

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `docs/00-bootstrap.md` | modify | Translate |
| 2 | `docs/foundation/00-why.md` | modify | Translate |
| 3 | `docs/foundation/01-double-loop.md` | modify | Translate |
| 4 | `docs/foundation/02-agent-roles.md` | modify | Translate |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Translate docs/00-bootstrap.md

**Files:**
- Modify: `docs/00-bootstrap.md`

**Steps:**
1. Read current file
2. Translate all Russian text to English
3. Keep code examples unchanged
4. Preserve markdown formatting

**Acceptance:**
- [ ] No Russian text remains
- [ ] Structure unchanged

### Task 2: Translate docs/foundation/*.md

**Files:**
- Modify: `docs/foundation/00-why.md`
- Modify: `docs/foundation/01-double-loop.md`
- Modify: `docs/foundation/02-agent-roles.md`

**Steps:**
1. Read each file
2. Translate all Russian text to English
3. Keep diagrams/ASCII art unchanged or translate labels
4. Preserve markdown formatting

**Acceptance:**
- [ ] All 3 files translated
- [ ] No Russian text remains

---

## Execution Order

Task 1 → Task 2 (independent, can parallel)

---

## Definition of Done

### Functional
- [ ] All 4 files translated
- [ ] No Russian text remains
- [ ] Meaning preserved

### Technical
- [ ] Valid markdown
- [ ] Links work

---

## Autopilot Log

*(Filled by Autopilot during execution)*
