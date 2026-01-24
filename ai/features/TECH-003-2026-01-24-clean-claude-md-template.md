# TECH: [TECH-003] Clean CLAUDE.md Template

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

`template/CLAUDE.md` contains Russian text and needs to be universal for any stack.
Current state is not copy-paste ready for international open source launch.

## Solution

Make CLAUDE.md stack-agnostic and English-only while keeping the structure.

---

## Scope

**In scope:**
- Translate Russian text to English
- Replace stack-specific examples with placeholders
- Keep all structural sections intact

**Out of scope:**
- Changing the structure or adding new sections
- Adding project-specific content

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/CLAUDE.md` | modify | Main target |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Translate and Clean CLAUDE.md

**Files:**
- Modify: `template/CLAUDE.md`

**Steps:**
1. Read current file
2. Translate all Russian text to English:
   - "заполнить после /bootstrap" → "fill after /bootstrap"
   - "Трёхуровневая система знаний..." → English equivalent
   - All comments and descriptions
3. Replace stack-specific examples with placeholders
4. Ensure all placeholders use `{placeholder}` format

**Acceptance:**
- [ ] No Russian text remains
- [ ] All placeholders are clear and universal
- [ ] Structure unchanged

---

## Definition of Done

### Functional
- [ ] No Russian text in file
- [ ] Placeholders use consistent `{placeholder}` format
- [ ] File is copy-paste ready for any stack

### Technical
- [ ] Valid markdown
- [ ] All links work (relative paths)

---

## Autopilot Log

*(Filled by Autopilot during execution)*
