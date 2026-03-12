# Feature: [TECH-142] Upgrade: Deprecation Manifest + Zombie Detection
**Status:** queued | **Priority:** P2 | **Date:** 2026-02-28

## Why
Files removed from template accumulate as zombies in user projects. `user_only` detection reports them but never explains WHY they're orphaned. Old agents, skills, and rules persist indefinitely, potentially conflicting with new versions.

Source: TRIZ TC-5 (Preliminary action).

## Context
TRIZ report Recommendation #7.

---

## Scope
**In scope:**
- Create `template/.claude/deprecated.json` with version-keyed removed/renamed entries
- In analyze(), cross-reference user_only files against deprecated.json
- Add `deprecated` category to JSON output with actionable messages
- Add `--cleanup` flag to move deprecated files to `.claude/.upgrade-trash/`

**Out of scope:**
- Automatic deletion (always require confirmation)
- Populating historical deprecations (start fresh from current version)

---

## Allowed Files
**ONLY these files may be modified during implementation:**

1. `template/.claude/deprecated.json` — NEW: deprecation manifest
2. `template/.claude/scripts/upgrade.mjs` — Add deprecated detection + cleanup flag
3. `.claude/deprecated.json` — Sync
4. `.claude/scripts/upgrade.mjs` — Sync

---

## Implementation

### Step 1: Create deprecated.json

```json
{
  "schema_version": 1,
  "versions": {
    "3.11": {
      "removed": [],
      "renamed": {}
    }
  }
}
```

### Step 2: Add deprecation detection to analyze()

```javascript
function loadDeprecated(sourceDir) {
  const depPath = join(sourceDir, '.claude/deprecated.json');
  if (!existsSync(depPath)) return { removed: [], renamed: {} };
  try {
    const data = JSON.parse(readFileSync(depPath, 'utf-8'));
    // Merge all versions into flat lists
    const removed = [];
    const renamed = {};
    for (const ver of Object.values(data.versions || {})) {
      if (ver.removed) removed.push(...ver.removed);
      if (ver.renamed) Object.assign(renamed, ver.renamed);
    }
    return { removed, renamed };
  } catch { return { removed: [], renamed: {} }; }
}
```

In analyze(), after user_only detection:
```javascript
const deprecated = loadDeprecated(sourceDir);
for (const item of result.user_only) {
  if (deprecated.removed.includes(item.path)) {
    item.deprecated = true;
    item.message = `Removed from DLD. Safe to delete.`;
  } else if (deprecated.renamed[item.path]) {
    item.deprecated = true;
    item.message = `Renamed to ${deprecated.renamed[item.path]}`;
  }
}
```

### Step 3: Add --cleanup flag

```javascript
else if (args[i] === '--cleanup') flags.mode = 'cleanup';
```

Cleanup mode:
```javascript
if (flags.mode === 'cleanup') {
  const report = analyze(sourceDir, projectDir, ...);
  const deprecatedFiles = report.files.user_only.filter(f => f.deprecated);
  if (deprecatedFiles.length === 0) {
    console.log(JSON.stringify({ message: 'No deprecated files found.' }));
    process.exit(2);
  }
  const trashDir = join(projectDir, '.claude/.upgrade-trash');
  mkdirSync(trashDir, { recursive: true });
  const moved = [];
  for (const item of deprecatedFiles) {
    const src = join(projectDir, item.path);
    const dst = join(trashDir, item.path);
    mkdirSync(dirname(dst), { recursive: true });
    cpSync(src, dst);
    rmSync(src);
    moved.push(item.path);
  }
  console.log(JSON.stringify({ moved, trash_dir: '.claude/.upgrade-trash' }));
}
```

### Step 4: Update SKILL.md

After Step 5 (Verification), if deprecated files found:
```
Deprecated files found (safe to remove):
  {path} — {message}

Run cleanup? This moves files to .claude/.upgrade-trash/ (recoverable).
```

### Step 5: Sync to .claude/

---

## Eval Criteria

| ID | Type | Assertion |
|----|------|-----------|
| EC-1 | Deterministic | `template/.claude/deprecated.json` exists and parses as valid JSON |
| EC-2 | Deterministic | analyze() output marks user_only files matching deprecated entries |
| EC-3 | Deterministic | `--cleanup` moves deprecated files to `.claude/.upgrade-trash/` |
| EC-4 | Deterministic | Non-deprecated user_only files are never touched by cleanup |
