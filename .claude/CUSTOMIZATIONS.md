# DLD Customizations

Files that exist ONLY in root `.claude/` (not in `template/.claude/`).

These are DLD-project-specific and should NOT be synced to template.

## Files List

| File | Purpose | Sync Policy |
|------|---------|-------------|
| `rules/localization.md` | Russian skill triggers | Never — DLD-specific |
| `rules/template-sync.md` | Template/root sync workflow | Never — DLD meta-rule |
| `settings.local.json` | Local dev settings (bypassPermissions) | Never — gitignored |
| `skills/scaffold/SKILL.md` | Skill/agent generator | Consider adding to template |

---

## Sync Workflow

### When improving DLD framework (universal change)

1. Make change in `template/.claude/` first
2. Review: does this apply to our root?
3. If yes → cherry-pick to `.claude/`
4. Commit: `chore: sync from template`

### When adding DLD-specific customization

1. Add only to `.claude/`
2. Add entry to this file
3. Commit: `feat(dld): description`

---

## How to Check Divergence

Run `scripts/check-sync.sh` to see:
- Files only in root (customizations)
- Files with different line counts

This is informational only — not all differences need syncing.

---

## Last Sync

| Date | What | Who |
|------|------|-----|
| 2026-02-02 | Initial sync both directions (TECH-062) | autopilot |
