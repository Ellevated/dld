# Tech: [TECH-045] Remove or fix placeholder files

**Status:** done | **Priority:** P2 | **Date:** 2026-01-30

## Problem

Several files are placeholders with no useful content:

1. `.github/FUNDING.yml` — completely commented out, no actual funding links
2. `assets/README.md` — says "This is a placeholder for future visual assets"

These files add noise without value.

## Solution

- Delete `FUNDING.yml` (can be added later when funding is set up)
- Delete `assets/README.md` (the `.gitkeep` files are sufficient)

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `.github/FUNDING.yml` | delete | Empty placeholder |
| 2 | `assets/README.md` | delete | Placeholder content |

## Tasks

### Task 1: Delete placeholder files

**Steps:**
1. `git rm .github/FUNDING.yml`
2. `git rm assets/README.md`

**Acceptance:**
- [ ] Files removed from repository
- [ ] No broken references to these files

## DoD

- [ ] Placeholder files removed
- [ ] `git status` shows deletions
