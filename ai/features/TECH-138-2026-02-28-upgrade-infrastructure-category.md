# Feature: [TECH-138] Upgrade Engine: INFRASTRUCTURE Category
**Status:** queued | **Priority:** P0 | **Date:** 2026-02-28

## Why
upgrade.mjs is in `scripts-claude` group → `SAFE_GROUPS` → auto-applies without confirmation via `--apply --groups safe`. This means the upgrade engine silently overwrites its own logic. Node.js loads script to memory so current run completes, but next run uses unreviewed code. Same risk applies to `run-hook.mjs` — the hook runner.

Source: TRIZ analysis TECH-2 (Segmentation), Physical Contradiction PC-1 (Separation in condition).

## Context
Part of `/upgrade` safety hardening after pyproject.toml overwrite incident.
TRIZ report: `ai/.triz/20260228-upgrade/report.md` — Recommendation #2.

---

## Scope
**In scope:**
- Add INFRASTRUCTURE set in upgrade.mjs for files that must never auto-apply
- Exclude INFRASTRUCTURE files from group-based resolveTargets()
- When analyze() detects INFRASTRUCTURE changes, emit distinct category in JSON output
- Update SKILL.md to present engine updates as a separate approval step

**Out of scope:**
- Changing apply() function itself (already has PROTECTED check)
- CI tests for upgrade (separate spec TECH-143)
- Backup/rollback mechanism (separate spec TECH-140)

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- `.claude/skills/upgrade/SKILL.md` — parses JSON output, presents to user
- Users running `/upgrade` — affected by auto-apply behavior

### Step 2: DOWN — what depends on?
- `SAFE_GROUPS` set — determines what auto-applies
- `resolveTargets()` — builds file list for apply
- `GROUP_PATTERNS` — classifies files into groups

### Step 3: BY TERM — grep entire project
- `scripts-claude` in GROUP_PATTERNS → matches `.claude/scripts/**`
- `SAFE_GROUPS` includes `scripts-claude`

### Step 4: CHECKLIST
- [x] No tests to break (no upgrade tests exist yet)
- [x] No migrations needed
- [x] Template-sync: universal change → edit template/ first, sync to .claude/

### Verification
- [x] All changed files in Allowed Files

---

## Allowed Files
**ONLY these files may be modified during implementation:**

**Modified files:**
1. `template/.claude/scripts/upgrade.mjs` — Add INFRASTRUCTURE set, modify resolveTargets()
2. `.claude/scripts/upgrade.mjs` — Sync from template (+ DLD-specific PROTECTED entries)
3. `template/.claude/skills/upgrade/SKILL.md` — Add engine update presentation step
4. `.claude/skills/upgrade/SKILL.md` — Sync from template

---

## Implementation

### Step 1: Add INFRASTRUCTURE set (upgrade.mjs)

After PROTECTED set, add:

```javascript
// Infrastructure files: engine + hook runner. Never auto-apply via groups.
// Only applied when explicitly named via --files.
const INFRASTRUCTURE = new Set([
  '.claude/scripts/upgrade.mjs',
  '.claude/hooks/run-hook.mjs',
]);
```

### Step 2: Modify resolveTargets()

In `resolveTargets()`, when processing `safe` group and `new` group, skip INFRASTRUCTURE files:

```javascript
if (name === 'safe') {
  for (const item of report.files.new_files) {
    if (SAFE_GROUPS.has(item.group) && !INFRASTRUCTURE.has(item.path)) targets.add(item.path);
  }
  for (const item of report.files.different) {
    if (SAFE_GROUPS.has(item.group) && !item.always_ask && !INFRASTRUCTURE.has(item.path)) targets.add(item.path);
  }
}
```

Also in the named group handler:
```javascript
const addFromCategory = (category) => {
  for (const item of report.files[category]) {
    if (item.group === name && !item.always_ask && !INFRASTRUCTURE.has(item.path)) targets.add(item.path);
  }
};
```

### Step 3: Modify analyze() output

Add `infrastructure` category to result:

```javascript
const result = {
  identical: [],
  new_files: [],
  different: [],
  protected: [],
  infrastructure: [],  // NEW
  user_only: [],
};
```

In the classification loop, check INFRASTRUCTURE before other checks:
```javascript
if (PROTECTED.has(tFile)) {
  result.protected.push({ path: tFile, group: getGroup(tFile) });
} else if (INFRASTRUCTURE.has(tFile)) {
  // Check if different from user version
  if (!existsSync(userPath)) {
    result.infrastructure.push({ path: tFile, group: getGroup(tFile), status: 'new' });
  } else if (sha256(templatePath) !== sha256(userPath)) {
    result.infrastructure.push({ path: tFile, group: getGroup(tFile), status: 'changed' });
  }
  // If identical, skip silently
} else if ...
```

Add infrastructure count to summary.

### Step 4: Update SKILL.md

After Step 3 (safe groups), add:

```markdown
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

Ask: "Apply engine update? (review diff above) Y/n"

If yes:
```bash
node .claude/scripts/upgrade.mjs --apply --files {path}
```
```

### Step 5: Sync to .claude/

Copy changes from template/ to .claude/ (preserving DLD-specific PROTECTED entries like `git-local-folders.md`).

---

## Eval Criteria

| ID | Type | Assertion |
|----|------|-----------|
| EC-1 | Deterministic | `--apply --groups safe` does NOT apply `.claude/scripts/upgrade.mjs` |
| EC-2 | Deterministic | `--apply --groups safe` does NOT apply `.claude/hooks/run-hook.mjs` |
| EC-3 | Deterministic | `--apply --files .claude/scripts/upgrade.mjs` DOES apply it (explicit override) |
| EC-4 | Deterministic | analyze() output JSON contains `infrastructure` array |
| EC-5 | Deterministic | SKILL.md contains "ENGINE UPDATE" presentation step |
