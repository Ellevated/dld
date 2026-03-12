# Tech: [TECH-047] Unify hook paths between settings files

**Status:** done | **Priority:** P1 | **Date:** 2026-01-30

## Problem

Hook paths are inconsistent between main and template settings. Template used relative paths which break in worktrees and subdirectories.

## Solution

Both main and template now use worktree-safe pattern:
```bash
ROOT=$(git worktree list --porcelain | head -1 | sed "s/^worktree //")
```

This works in both main repo and any git worktree.

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/settings.json` | modify | Update hook paths |

## Tasks

### Task 1: Update template hook paths

**Files:** `template/.claude/settings.json`

**Steps:**
1. Replace all relative hook paths with `git rev-parse` pattern:
   - `python3 .claude/hooks/X.py` → `bash -c 'python3 "$(git rev-parse --show-toplevel)/.claude/hooks/X.py"'`
   - `bash .claude/hooks/X.sh` → `bash -c 'bash "$(git rev-parse --show-toplevel)/.claude/hooks/X.sh"'`
2. Keep `2>/dev/null` for Python hooks (matches main)

**Acceptance:**
- [ ] All hook paths use `git rev-parse --show-toplevel`
- [ ] Format matches main settings.json
- [ ] JSON is valid

## DoD

- [ ] Template hooks work in worktrees
- [ ] Paths match main settings pattern
