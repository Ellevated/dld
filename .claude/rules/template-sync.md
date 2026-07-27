---
paths:
  - ".claude/**"
  - "template/**"
---

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
**`/upgrade` will NOT overwrite them** — but only because `/upgrade` is now manual cherry-pick. The auto-apply `upgrade.mjs` was deleted 2026-05-25 after it overwrote these files in awardybot/dowry despite a PROTECTED filter. See `.claude/skills/upgrade/SKILL.md` for the manual flow.

- `rules/architecture.md` — Root adds ADR-015..018 (DLD orchestrator decisions), shell script safety rules
- `rules/dependencies.md` — Root has full DLD dependency map (scripts/vps/*, orchestrator, callback)
- `rules/model-capabilities.md` — Root's `paths:` header covers `template/**` and `scripts/vps/*`
  as well, because DLD edits both trees. Body must stay byte-identical.
- **LLM-Native economics wording**, in `agents/board/{cmo,coo}.md`,
  `agents/architect/{dx,evolutionary,synthesizer}.md` — root states it as a fact about this
  repo ("this codebase is maintained by AI agents … MUST reflect this reality"); template
  hedges for downstream users ("For human teams, include both"). Deliberate: DLD has no human
  implementers, a template user might.
- `agents/architect/synthesizer.md` — template carries an extra "Effort Estimate" section.

Found by audit 2026-07-27, not by anyone noticing. Undocumented divergence is
indistinguishable from an interrupted sync — record it here when you create it.

When template updates these files, manually merge changes into root.

## Deleted Files (History)

- `rules/git-local-folders.md` — Removed in TECH-144. Was redundant with root `.gitignore`.
