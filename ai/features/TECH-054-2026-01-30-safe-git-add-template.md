# Tech: [TECH-054] Replace git add -A with safe alternative in template

**Status:** done | **Priority:** P1 | **Date:** 2026-01-30

## Problem

`template/CLAUDE.md:162` recommends:
```markdown
`git add -A && git commit -m "..."`
```

`git add -A` adds **everything**, including:
- `.env` files with secrets
- Credentials and API keys
- Large binary files
- Temporary files

This is a dangerous pattern to recommend in a template.

## Solution

Replace with safer patterns:
1. `git add .` (still adds all but from current dir)
2. Better: `git add <specific-files>` recommendation
3. Add warning about reviewing `git status` first

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/CLAUDE.md` | modify | Fix git add recommendation |

## Tasks

### Task 1: Update git add recommendation

**Files:** `template/CLAUDE.md`

**Steps:**
1. Line 162: Change the command to show safer pattern
2. Update to:
   ```markdown
   1. `git status && git diff`
   2. `git add <files>` (or `git add -p` for interactive)
   3. `git commit -m "..."` (Conventional Commits)
   ```
3. Add note: "Review `git status` before committing. Never commit `.env` or credentials."

**Acceptance:**
- [ ] No `git add -A` recommendation
- [ ] Safer pattern documented
- [ ] Warning about secrets included

## DoD

- [ ] Template promotes safe git practices
- [ ] No blanket `git add -A` in template
