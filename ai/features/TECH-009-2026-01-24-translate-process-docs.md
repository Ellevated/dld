# TECH: [TECH-009] Translate Process Docs (09-14)

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

Process docs (09-14) are in Russian. Need English for international launch.

## Solution

Translate 6 process documentation files to English.

---

## Scope

**In scope:**
- `docs/09-onboarding.md`
- `docs/10-testing.md`
- `docs/11-ci-cd.md`
- `docs/12-docker.md`
- `docs/13-migration.md`
- `docs/14-suggested-domains.md`

**Out of scope:**
- Changing structure
- Adding new content

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `docs/09-onboarding.md` | modify | Translate |
| 2 | `docs/10-testing.md` | modify | Translate |
| 3 | `docs/11-ci-cd.md` | modify | Translate |
| 4 | `docs/12-docker.md` | modify | Translate |
| 5 | `docs/13-migration.md` | modify | Translate |
| 6 | `docs/14-suggested-domains.md` | modify | Translate |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Translate 09-11

**Files:**
- Modify: `docs/09-onboarding.md`
- Modify: `docs/10-testing.md`
- Modify: `docs/11-ci-cd.md`

**Steps:**
1. Read each file
2. Translate all Russian text to English
3. Keep code/config examples unchanged
4. Preserve markdown formatting

**Acceptance:**
- [ ] All 3 files translated
- [ ] No Russian text remains

### Task 2: Translate 12-14

**Files:**
- Modify: `docs/12-docker.md`
- Modify: `docs/13-migration.md`
- Modify: `docs/14-suggested-domains.md`

**Steps:**
1. Read each file
2. Translate all Russian text to English
3. Keep code examples unchanged
4. Preserve tables

**Acceptance:**
- [ ] All 3 files translated
- [ ] No Russian text remains

---

## Execution Order

Task 1 → Task 2 (independent, can parallel)

---

## Definition of Done

### Functional
- [ ] All 6 files translated
- [ ] No Russian text remains
- [ ] Technical accuracy preserved

### Technical
- [ ] Valid markdown
- [ ] Config examples work

---

## Autopilot Log

*(Filled by Autopilot during execution)*
