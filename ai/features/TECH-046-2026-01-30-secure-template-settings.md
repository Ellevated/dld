# Tech: [TECH-046] Remove bypassPermissions from template settings

**Status:** done | **Priority:** P0 | **Date:** 2026-01-30

## Problem

`template/.claude/settings.json` has `"defaultMode": "bypassPermissions"` which gives Claude full system access without confirmation. This is a **security risk** for new users who copy the template.

**Current (dangerous):**
```json
{
  "defaultMode": "bypassPermissions"
}
```

## Solution

Remove `defaultMode` from template settings. Users should explicitly opt into bypass mode if they want it.

**Safe default:** No `defaultMode` field = Claude asks for permission (standard behavior).

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/settings.json` | modify | Remove bypassPermissions |

## Tasks

### Task 1: Remove bypassPermissions from template

**Files:** `template/.claude/settings.json`

**Steps:**
1. Remove line `"defaultMode": "bypassPermissions",`
2. Keep all other settings (model, hooks, permissions)

**Acceptance:**
- [ ] No `defaultMode` in template settings
- [ ] JSON is valid
- [ ] Hooks still configured

## DoD

- [ ] `bypassPermissions` removed from template
- [ ] Template uses safe defaults
- [ ] JSON syntax valid
