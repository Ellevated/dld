---
name: upgrade
description: Manually update DLD framework files from latest GitHub template. NO auto-apply script (deleted 2026-05-25). Cherry-pick by hand.
---

# /upgrade — DLD Framework Update (Manual)

**Why manual:** Previous auto-apply script (`upgrade.mjs`) was deleted 2026-05-25 after repeatedly overwriting PROTECTED files (`architecture.md`, `dependencies.md`) despite filter logic. Manual cherry-pick is slower but does not destroy project ADRs.

---

## Operator Flow

### 1. Fetch latest template

```bash
TMP=$(mktemp -d)
git clone --depth 1 --filter=blob:none --sparse https://github.com/Ellevated/dld.git "$TMP"
git -C "$TMP" sparse-checkout set template
SRC="$TMP/template"
```

### 2. Diff what's different

```bash
diff -rq "$SRC/.claude" .claude | head -50
diff -rq "$SRC/scripts" scripts 2>/dev/null | head -20
```

### 3. Cherry-pick SAFE groups (canonical from template)

- `.claude/agents/` — agent prompts
- `.claude/hooks/*.mjs` — hook code (skip `hooks.config.local.mjs`)
- `.claude/hooks/__tests__/` — hook tests
- `.git-hooks/pre-commit` — wrapper (then `git config core.hooksPath .git-hooks`)

```bash
cp -rv "$SRC/.claude/agents/." .claude/agents/
cp -rv "$SRC/.claude/hooks/." .claude/hooks/
cp -v  "$SRC/.git-hooks/pre-commit" .git-hooks/pre-commit && chmod +x .git-hooks/pre-commit
git config core.hooksPath .git-hooks
```

### 4. Review-required (per-file decision)

- `.claude/skills/` — may have project-specific overrides
- `.claude/settings.json` — preferences differ per machine

```bash
diff "$SRC/.claude/skills/spark/SKILL.md" .claude/skills/spark/SKILL.md
# Decide → cp only if accepting verbatim
```

### 5. NEVER overwrite these (project-specific content)

| File | Why |
|------|-----|
| `CLAUDE.md` | Project description, custom rules |
| `.claude/rules/architecture.md` | ADRs, anti-patterns — project specific |
| `.claude/rules/dependencies.md` | Per-project dependency map |
| `.claude/rules/localization.md` | Language triggers |
| `.claude/rules/template-sync.md` | Drift policy |
| `.claude/CUSTOMIZATIONS.md` | Per-project notes |
| `.claude/hooks/hooks.config.mjs` | Hook routing |
| `.claude/hooks/hooks.config.local.mjs` | Local overrides |
| `.claude/settings.local.json` | Local machine settings |
| `.gitignore`, `package.json`, `pyproject.toml`, `requirements.txt` | Project config |

If template introduced new ADRs/dependencies — manually **MERGE** them into the project file, do NOT replace.

### 6. Cleanup

```bash
rm -rf "$TMP"
```

---

## Notes

- For DLD-internal projects (root + template in same repo): use the `template-sync.md` workflow instead.
- If a file currently in "never overwrite" actually should be auto-syncable — propose moving it via a TECH spec; don't bypass.
- After update: restart Claude Code session to pick up new agent prompts.
