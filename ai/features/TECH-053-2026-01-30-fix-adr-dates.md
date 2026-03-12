# Tech: [TECH-053] Fill ADR placeholder dates

**Status:** done | **Priority:** P2 | **Date:** 2026-01-30

## Problem

Architecture Decision Records have placeholder dates:

**.claude/rules/architecture.md:**
```markdown
| ADR-001 | Money in cents | YYYY-MM | Avoid float precision errors |
| ADR-002 | Result instead of exceptions | YYYY-MM | Explicit error handling |
| ADR-003 | Async everywhere | YYYY-MM | Consistency, performance |
```

`YYYY-MM` is a template placeholder, not a real date.

## Solution

Replace with actual dates. Since these are foundational decisions from project start, use 2026-01 (project creation date).

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `.claude/rules/architecture.md` | modify | Fill ADR dates |
| 2 | `template/.claude/rules/architecture.md` | keep | Template should keep YYYY-MM |

**Note:** Only fix the main project's architecture.md. The template version should keep `YYYY-MM` as it's meant to be filled by users.

## Tasks

### Task 1: Update ADR dates

**Files:** `.claude/rules/architecture.md`

**Steps:**
1. Replace `YYYY-MM` with `2026-01` for all three ADRs

**Acceptance:**
- [ ] All ADRs have real dates
- [ ] Template still has placeholders

## DoD

- [ ] No `YYYY-MM` in main architecture.md
- [ ] Template unchanged (keeps placeholders)
