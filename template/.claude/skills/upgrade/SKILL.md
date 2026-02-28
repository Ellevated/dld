---
name: upgrade
description: Upgrade DLD framework files from latest template on GitHub.
---

# /upgrade — DLD Framework Upgrade

Deterministic upgrade of DLD skills, agents, hooks, rules, and scripts from the latest template.

**Key principle:** The upgrade.mjs script does ALL file operations. You NEVER copy or modify files directly. You only:
1. Run the script via Bash
2. Read its JSON output
3. Present results to user
4. Pass user decisions back to the script

## Pre-flight

1. Verify `node --version` >= 18
2. Verify `.claude/scripts/upgrade.mjs` exists
3. If missing: "upgrade.mjs not found. Run `npx create-dld` to set up a DLD project first."

## Flow

### Step 1: Analyze

```bash
node .claude/scripts/upgrade.mjs --analyze
```

Parse the JSON output. If exit code 2: "Your DLD is up to date. No changes needed."

If exit code 1: show error message from JSON and stop.

### Step 2: Present Report

Show grouped summary to user:

```
DLD Upgrade Report
==================
Template commit: {report.template_commit}

Summary: {identical} up to date, {new_files} new, {different} changed, {protected} protected

Groups:
  agents:         {N} new, {N} changed  [safe — auto-update]
  hooks:          {N} new, {N} changed  [safe — auto-update]
  skills:         {N} new, {N} changed  [review recommended]
  rules:          {N} new, {N} changed  [safe — auto-update]
  scripts-claude: {N} new, {N} changed  [safe — auto-update]
  settings:       {N} changed           [always ask]

Protected (never touched): {protected count} files
User-only (your files, untouched): {user_only count} files
```

### Step 3: User Confirmation

Ask: "Apply safe groups automatically? (agents, hooks, rules, scripts) Y/n"

If yes:
```bash
node .claude/scripts/upgrade.mjs --apply --groups safe,new
```

### Step 3b: Engine Updates

If report contains infrastructure files with changes:

Show:
```
ENGINE UPDATE (requires explicit approval):
  .claude/scripts/upgrade.mjs — {status}
  .claude/hooks/run-hook.mjs — {status}
```

For each, show diff:
```bash
node .claude/scripts/upgrade.mjs --diff --file {path}
```

Ask: "Apply engine update? Y/n"

If yes:
```bash
node .claude/scripts/upgrade.mjs --apply --files {path}
```

### Step 4: Handle Conflicts

For each non-safe group with changes (skills, settings):

Note: `hooks.config.mjs` is PROTECTED and will never appear here. Users should use `hooks.config.local.mjs` for project-specific hook customizations — it is never touched by upgrades.

Show per-file diff:
```bash
node .claude/scripts/upgrade.mjs --diff --file {path}
```

For each file ask: "Take template version / Keep yours / Skip"

If "take":
```bash
node .claude/scripts/upgrade.mjs --apply --files {path}
```

### Step 5: Verification

After all applies, run analyze again:
```bash
node .claude/scripts/upgrade.mjs --analyze
```

Report final state:
```
Upgrade complete.
  Applied: {N} files
  Skipped: {N} files (user decision)
  Protected: {N} files (never touched)
  Remaining differences: {N} files

Restart Claude Code to activate changes.
```

If result contains `validation_issues`, show warning:
```
WARNING: Post-apply validation failed:
  {validation_issues[]}

Check .dld-upgrade-log for details.
```

If result contains `rolled_back: true`, inform user:
```
ROLLBACK: Changes were rolled back due to validation failure.
  Stash ref: {stash_ref} (run `git stash show {stash_ref}` to inspect)
  No files were modified.
```

If report contains deprecated files present in the project, offer cleanup:
```
DEPRECATED FILES found in your project:
  {deprecated_files[]}

These were removed from DLD template. Run cleanup? Y/n
```

If yes:
```bash
node .claude/scripts/upgrade.mjs --cleanup
```

## Rules

- NEVER use Read/Edit/Write tools to copy template files
- ALWAYS use upgrade.mjs for ALL file operations
- Show diff before asking user to accept changes
- Protected files are NEVER offered for update
- settings.json ALWAYS requires explicit user approval
- If --analyze fails with network error, suggest: "Try again or use --local if you have the DLD repo cloned"
- After successful upgrade, remind user to restart Claude Code

## Error Recovery

- Network failure: suggest retry or `--local` mode
- Partial apply (some errors): show what succeeded and what failed
- Git dirty: tell user to commit or stash first
- Validation failure + rollback: show stash ref, suggest manual inspection
- Deprecated files remaining: run `node .claude/scripts/upgrade.mjs --cleanup`
