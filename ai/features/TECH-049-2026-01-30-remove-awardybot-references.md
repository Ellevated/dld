# Tech: [TECH-049] Remove personal project references

**Status:** done | **Priority:** P1 | **Date:** 2026-01-30

## Problem

Personal project "awardybot" is mentioned in public documentation:

1. `CHANGELOG.md:51` — "Template sync from production project (awardybot)"
2. `docs/19-living-architecture.md:520` — "Success Metrics (from ARCH-392 awardybot)"

This looks unprofessional in an open source methodology project.

## Solution

Remove or generalize these references:
- CHANGELOG: Remove the parenthetical, just say "Template sync from production project"
- Living architecture: Change to generic "Success Metrics" or "(from internal project)"

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `CHANGELOG.md` | modify | Remove awardybot reference |
| 2 | `docs/19-living-architecture.md` | modify | Remove awardybot reference |

## Tasks

### Task 1: Clean CHANGELOG.md

**Files:** `CHANGELOG.md`

**Steps:**
1. Line 51: Change "Template sync from production project (awardybot)" to "Template sync from production project"

**Acceptance:**
- [ ] No "awardybot" in CHANGELOG

### Task 2: Clean living-architecture.md

**Files:** `docs/19-living-architecture.md`

**Steps:**
1. Line 520: Change "(from ARCH-392 awardybot)" to "(example metrics)"

**Acceptance:**
- [ ] No "awardybot" in documentation

## DoD

- [ ] `grep -r "awardybot" .` returns 0 results (excluding .git)
- [ ] No personal project names in public docs
