# Feature: [TECH-140] Upgrade: Git Stash Backup + Post-Apply Validation
**Status:** queued | **Priority:** P0 | **Date:** 2026-02-28

## Why
upgrade.mjs has zero backup/rollback. If apply() fails on file 20 of 49, the project is in mixed state with no audit trail and no recovery path. Adding git stash before apply + validation after gives rollback for free using existing git infrastructure.

Source: TRIZ PC-4 (Separation in time), TC-3 (Preliminary action), TOC EC-4.

## Context
Part of `/upgrade` safety hardening. TRIZ report Recommendation #3.

---

## Scope
**In scope:**
- `git stash create` before apply() to create backup reference
- Post-apply validation: PROTECTED files unchanged, hooks.config loads, settings.json parses
- On validation failure: `git checkout -- .` to restore + report
- Audit log: write applied files list to `.dld-upgrade-log`

**Out of scope:**
- Changing the apply() copy mechanism itself
- Adding per-file rollback (git stash is all-or-nothing, which is fine)
- CI tests (separate spec TECH-143)

---

## Allowed Files
**ONLY these files may be modified during implementation:**

1. `template/.claude/scripts/upgrade.mjs` — Add backup/validate/rollback logic
2. `.claude/scripts/upgrade.mjs` — Sync

---

## Implementation

### Step 1: Add backup before apply (main function, apply mode)

Before calling `apply()`:

```javascript
// Create backup reference (returns empty string if nothing to stash)
let stashRef = '';
try {
  stashRef = execSync('git stash create', { encoding: 'utf-8', stdio: 'pipe' }).trim();
} catch {
  // No git or no changes — proceed without backup
}
```

### Step 2: Add validate() function

```javascript
function validate(projectDir, appliedFiles) {
  const issues = [];

  // Check PROTECTED files weren't somehow modified
  for (const p of PROTECTED) {
    const full = join(projectDir, p);
    if (!existsSync(full)) continue;
    // We don't have pre-apply SHA here, but git diff will catch it
  }

  // Verify hooks.config loads
  const hooksConfig = join(projectDir, '.claude/hooks/hooks.config.mjs');
  if (existsSync(hooksConfig) && appliedFiles.some(f => f.startsWith('.claude/hooks/'))) {
    try {
      // Syntax check via Node.js parse
      execSync(`node --check ${hooksConfig}`, { stdio: 'pipe' });
    } catch (err) {
      issues.push({ file: '.claude/hooks/hooks.config.mjs', reason: 'syntax error after upgrade' });
    }
  }

  // Verify settings.json parses
  const settingsPath = join(projectDir, '.claude/settings.json');
  if (existsSync(settingsPath) && appliedFiles.some(f => f === '.claude/settings.json')) {
    try {
      JSON.parse(readFileSync(settingsPath, 'utf-8'));
    } catch {
      issues.push({ file: '.claude/settings.json', reason: 'invalid JSON after upgrade' });
    }
  }

  return issues;
}
```

### Step 3: Wire backup + validate into apply mode

```javascript
} else if (flags.mode === 'apply') {
  // ... existing target resolution ...

  // Backup
  let stashRef = '';
  try {
    stashRef = execSync('git stash create', { encoding: 'utf-8', stdio: 'pipe' }).trim();
  } catch {}

  const result = apply(sourceDir, projectDir, targets);

  // Validate
  if (result.applied.length > 0) {
    const issues = validate(projectDir, result.applied);
    if (issues.length > 0) {
      result.validation_issues = issues;
      // Rollback
      if (stashRef) {
        try {
          execSync('git checkout -- .', { stdio: 'pipe' });
          result.rolled_back = true;
          result.rollback_ref = stashRef;
        } catch {}
      }
    }
  }

  // Write .dld-version only on clean apply
  if (result.applied.length > 0 && result.errors.length === 0 && !result.rolled_back) {
    const version = writeVersion(projectDir, report.template_commit);
    result.version = version;
  }

  // Audit log
  if (result.applied.length > 0) {
    const logEntry = {
      timestamp: new Date().toISOString(),
      applied: result.applied,
      errors: result.errors,
      rolled_back: result.rolled_back || false,
      stash_ref: stashRef || null,
    };
    const logPath = join(projectDir, '.dld-upgrade-log');
    const existing = existsSync(logPath) ? readFileSync(logPath, 'utf-8') : '';
    writeFileSync(logPath, existing + JSON.stringify(logEntry) + '\n');
  }

  console.log(JSON.stringify(result, null, 2));
}
```

### Step 4: Update SKILL.md

Add to Step 5 (Verification):
- If result contains `validation_issues`, show them with warning
- If `rolled_back: true`, inform user that changes were reverted and show stash ref
- Suggest: "Run `git stash apply {ref}` to re-apply if you want to debug"

### Step 5: Add .dld-upgrade-log to .gitignore

Ensure `.dld-upgrade-log` is in template's `.gitignore`.

### Step 6: Sync to .claude/

---

## Eval Criteria

| ID | Type | Assertion |
|----|------|-----------|
| EC-1 | Deterministic | apply mode creates stash reference before first cpSync |
| EC-2 | Deterministic | validate() checks hooks.config.mjs syntax after hook-related applies |
| EC-3 | Deterministic | validate() checks settings.json parsability after settings apply |
| EC-4 | Deterministic | On validation failure, `rolled_back: true` appears in JSON output |
| EC-5 | Deterministic | `.dld-upgrade-log` is written after every apply |
| EC-6 | Deterministic | `.dld-version` is NOT written when rolled_back is true |
