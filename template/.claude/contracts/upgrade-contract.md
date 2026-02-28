# Upgrade Contract Specification

Formal invariants for the DLD upgrade engine (upgrade.mjs).
All tests and validations derive from this document.

## Scope Invariants

- ONLY files matching UPGRADE_SCOPE (`.claude/`, `scripts/`) are processed
- Files outside UPGRADE_SCOPE are NEVER read, compared, or modified
- PROTECTED files are NEVER modified regardless of command or flags
- INFRASTRUCTURE files are NEVER auto-applied via group operations

## Trust Tiers

| Tier | Behavior | Examples |
|------|----------|---------|
| PROTECTED | Never touched, never offered | CLAUDE.md, pyproject.toml, package.json, hooks.config.mjs |
| INFRASTRUCTURE | Only via explicit `--files`, always show diff | upgrade.mjs, run-hook.mjs |
| ALWAYS_ASK | Always show diff, require per-file approval | settings.json |
| SAFE | Auto-apply in batch `--groups safe` | agents, hooks, rules, scripts |
| OTHER | Show in report, require per-file approval | skills |

## Atomicity

- `.dld-version` is written ONLY after clean apply (no errors, no validation failures, no rollback)
- On validation failure: automatic rollback via `git checkout -- .`

## Reversibility

- Backup via `git stash create` before any apply operation
- Stash ref preserved in `.dld-upgrade-log` for manual recovery
- Audit log records every apply: timestamp, files, errors, rollback status

## File Lifecycle

| State | Meaning | Detection |
|-------|---------|-----------|
| added | New in template, not in project | exists in template, not in project |
| modified | Exists in both, SHA256 differs | SHA256 comparison |
| identical | Exists in both, SHA256 matches | skip silently |
| deprecated | Removed from template, listed in deprecated.json | cross-reference |
| user_only | Exists in project only, not in template | not in template set |

## Post-Apply Validation

After every apply:
1. hooks.config.mjs must parse as valid JavaScript (`node --check`)
2. settings.json must parse as valid JSON
3. Audit log entry written to `.dld-upgrade-log`

On validation failure:
1. Rollback all changes (`git checkout -- .`)
2. Set `rolled_back: true` in JSON output
3. Preserve stash ref for manual recovery

## Version Tracking

- `.dld-version` contains: version, template_commit SHA, timestamp, skip list
- Written only after successful, validated apply
- `skip[]` field: files user explicitly chose to skip (for future use)
