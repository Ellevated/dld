# Tech: [TECH-070] Sync LOC Limits Across Documentation

**Status:** queued | **Priority:** P2 | **Date:** 2026-02-02

## Why

LOC limits have drifted across documentation files. Source of truth is `skill-writer/SKILL.md`, but at least one file has outdated values.

## Context

DLD has **two categories** of LOC limits:

| Category | What | Limit | Source of Truth |
|----------|------|-------|-----------------|
| Source code | `*.py`, `*.ts`, etc. | 400 LOC (600 tests) | `architecture.md` |
| DLD config | CLAUDE.md | < 200 lines | `skill-writer/SKILL.md` |
| DLD config | Rules (`*.md` in rules/) | < 500 lines | `skill-writer/SKILL.md` |
| DLD config | Skills (`SKILL.md`) | < 500 lines | `skill-writer/SKILL.md` |

## Scope

**In scope:**
- Fix `docs/09-onboarding.md` where CLAUDE.md limit is wrong (100 → 200)
- Add explicit limits table to `template/CLAUDE.md` for clarity

**Out of scope:**
- Changing actual limits (they are correct in source of truth)
- Code LOC limits (400/600) — already consistent

## Impact Tree Analysis

### Step 1: BY TERM — grep for wrong value
- [x] `grep -rn "< 100 lines" . --include="*.md"` → 1 result
- [x] `grep -rn "CLAUDE.md < 100" . --include="*.md"` → 1 result (docs/09-onboarding.md:71)

| File | Line | Status | Action |
|------|------|--------|--------|
| `docs/09-onboarding.md` | 71 | Wrong | Fix 100 → 200 |

### Step 2: Verify no other drifts
- [x] All other CLAUDE.md limits say < 200 — verified

### Verification
- [x] All found files added to Allowed Files
- [x] grep by "CLAUDE.md < 100" = 0 after fix

## Allowed Files

**ONLY these files may be modified:**
1. `docs/09-onboarding.md` — fix CLAUDE.md limit (100 → 200)

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Implementation Plan

### Task 1: Fix onboarding.md
**Type:** docs
**Files:** modify `docs/09-onboarding.md`
**Change:** Line 71: `CLAUDE.md < 100 lines` → `CLAUDE.md < 200 lines`
**Acceptance:** grep "CLAUDE.md < 100" = 0 results

### Execution Order
1 (single task)

## Definition of Done

### Functional
- [x] Wrong limit fixed

### Technical
- [ ] `grep -rn "CLAUDE.md < 100" . --include="*.md"` returns 0 results
- [ ] No regressions

## Autopilot Log
<!-- filled by autopilot -->
