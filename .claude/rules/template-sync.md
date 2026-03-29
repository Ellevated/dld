# Template Sync Rule

## Two Copies of .claude/

DLD has TWO places with skills/agents/hooks:

```
template/.claude/   ← Universal (for all DLD users)
.claude/            ← DLD-specific (template + customizations)
```

## When Modifying .claude/ Files

**STOP and ask:** Is this universal or DLD-specific?

| Type | Where to edit | Then |
|------|---------------|------|
| **Universal improvement** | `template/.claude/` first | Cherry-pick to `.claude/` |
| **DLD-specific** | `.claude/` only | Document in CUSTOMIZATIONS.md |

## Examples

**"Improve spark prompt"** → Universal
1. Edit `template/.claude/skills/spark/SKILL.md`
2. Then sync to `.claude/skills/spark/SKILL.md`

**"Add Russian triggers"** → DLD-specific
1. Edit only `.claude/rules/localization.md`
2. Don't touch template

## Quick Check

Before editing any file in `.claude/`:

```
Does template/.claude/ have this file?
├─ YES → Edit template first, then sync
└─ NO  → It's a customization, edit .claude/ only
```

## Files Only in Root (Customizations)

- `rules/localization.md` — Russian skill triggers
- `rules/template-sync.md` — This file (DLD dual-repo sync policy)
- `settings.local.json` — Local dev settings
- `skills/scaffold/SKILL.md` — Skill generator
- `hooks/hooks.config.local.mjs` — DLD-specific hook overrides (excludeFromSync)

These are NOT in template — edit directly in `.claude/`.

## Files in Both, but Root Has DLD-Specific Extensions

These files exist in template AND root. Template has the baseline, root adds DLD-specific content.
**`/upgrade` will NOT overwrite them** (added to PROTECTED in upgrade.mjs).

- `rules/architecture.md` — Root adds ADR-015..018 (DLD orchestrator decisions), shell script safety rules
- `rules/dependencies.md` — Root has full DLD dependency map (scripts/vps/*, orchestrator, callback)

When template updates these files, manually merge changes into root.

## Deleted Files (History)

- `rules/git-local-folders.md` — Removed in TECH-144. Was redundant with root `.gitignore`.
