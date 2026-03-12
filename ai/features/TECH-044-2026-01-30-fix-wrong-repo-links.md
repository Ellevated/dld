# Tech: [TECH-044] Fix links pointing to wrong repository

**Status:** done | **Priority:** P0 | **Date:** 2026-01-30

## Problem

Several documentation files link to `github.com/anthropics/claude-code` instead of `github.com/Ellevated/dld`. This sends users to the wrong repository for bug reports and documentation.

**Found in:**
1. `FAQ.md:151` — GitHub Issues link points to anthropics/claude-code
2. `.github/ISSUE_TEMPLATE/config.yml:4` — Documentation link points to anthropics/claude-code

## Solution

Replace all incorrect `anthropics/claude-code` links with `Ellevated/dld`.

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `FAQ.md` | modify | Fix GitHub Issues link |
| 2 | `.github/ISSUE_TEMPLATE/config.yml` | modify | Fix documentation link |

## Tasks

### Task 1: Fix FAQ.md link

**Files:** `FAQ.md`

**Steps:**
1. Line 151: Replace `https://github.com/anthropics/claude-code/issues` with `https://github.com/Ellevated/dld/issues`

**Acceptance:**
- [ ] Link points to Ellevated/dld

### Task 2: Fix Issue Template config

**Files:** `.github/ISSUE_TEMPLATE/config.yml`

**Steps:**
1. Line 4: Replace `https://github.com/anthropics/claude-code` with `https://github.com/Ellevated/dld`
2. Update "about" text if needed

**Acceptance:**
- [ ] Link points to Ellevated/dld

## DoD

- [ ] All links point to correct repository
- [ ] No remaining `anthropics/claude-code` references in user-facing docs
