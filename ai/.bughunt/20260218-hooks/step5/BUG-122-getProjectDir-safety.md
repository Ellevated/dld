# BUG-122 — getProjectDir() Safety: macOS /private/tmp Symlink + realpathSync + /tmp Root

**Priority:** P0
**Severity:** High
**Group:** getProjectDir Safety
**Status:** queued
**Source Findings:** F-006, F-007, F-008 (validated-findings.yaml)

---

## Summary

`getProjectDir()` in `utils.mjs` is the central path safety function used by all hooks to
validate that `CLAUDE_PROJECT_DIR` is within an acceptable boundary before using it for
config loading and file operations. It has three distinct bugs:

1. **F-006:** The `/tmp` boundary check fails on macOS because `/tmp` is a symlink to
   `/private/tmp`. `resolve('/tmp/foo')` returns `'/private/tmp/foo'`, which does NOT start
   with `'/tmp'`, causing the guard to fire incorrectly and fall back to `process.cwd()`.
   Breaks ALL test environments on macOS (which use `mkdtempSync` → `/tmp/...` paths).

2. **F-007:** `CLAUDE_PROJECT_DIR=/tmp` (the root) passes the guard. This makes the entire
   `/tmp` filesystem "inside the project" — post-edit hook will ruff-format any `.py` file
   under `/tmp`, and boundary checks become meaningless.

3. **F-008:** `getProjectDir()` uses `resolve()` (lexical path normalization) instead of
   `fs.realpathSync()`. A symlink `$HOME/project -> /etc` passes the `startsWith(home)` check
   because the check uses the unresolved path. The resolved symlink target escapes the home
   boundary. This matters because the returned path is used for dynamic ESM import of
   `hooks.config.local.mjs` — executing arbitrary JavaScript from outside the intended boundary.

---

## Root Cause Analysis

```javascript
// utils.mjs:391-399 (current buggy implementation)
export function getProjectDir() {
  const dir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const resolved = resolve(dir);          // Bug F-008: lexical only, no symlink resolution
  const home = homedir();
  if (!resolved.startsWith(home) &&       // Bug F-008: startsWith passes for symlinks
      !resolved.startsWith('/tmp')) {     // Bug F-006: '/private/tmp/x'.startsWith('/tmp') = false
    return process.cwd();
  }
  return resolved;                        // Bug F-007: '/tmp' itself passes, entire /tmp = project
}
```

All three bugs share the same function and interact: fixing F-006 without F-007 still allows
`/tmp` root as project dir; fixing F-008 without F-006 still breaks macOS.

---

## Affected Files

```
## Allowed Files
.claude/hooks/utils.mjs
test/getProjectDir-safety.test.mjs
```

---

## Fix Description

### Complete replacement of getProjectDir()

```javascript
// utils.mjs — replace the entire getProjectDir() function
import { join, resolve, sep } from 'path';
import { homedir } from 'os';
import { realpathSync, existsSync } from 'fs';

/**
 * Get project directory with path traversal protection.
 *
 * Fixes applied:
 *   - F-006: Resolve /tmp to its real path (handles macOS /private/tmp symlink)
 *   - F-007: Require at least one directory level below /tmp (no bare /tmp as project root)
 *   - F-008: Use realpathSync() not resolve() to follow symlinks before prefix check
 *
 * Falls back to cwd() if CLAUDE_PROJECT_DIR escapes home or /tmp.
 */
export function getProjectDir() {
  const dir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const home = homedir();

  // Resolve the real /tmp path (handles macOS /tmp -> /private/tmp symlink)
  let tmpResolved;
  try {
    tmpResolved = realpathSync('/tmp');
  } catch {
    tmpResolved = resolve('/tmp');  // fallback if /tmp does not exist (non-POSIX)
  }

  // Use realpathSync to follow symlinks (fixes F-008)
  let resolved;
  try {
    resolved = realpathSync(dir);
  } catch {
    // dir may not exist yet (new project) — fall back to lexical resolve
    resolved = resolve(dir);
  }

  // Check home directory boundary (with separator to avoid prefix collisions)
  const homeWithSep = home.endsWith(sep) ? home : home + sep;
  if (resolved === home || resolved.startsWith(homeWithSep)) {
    return resolved;
  }

  // Check /tmp boundary (with separator to require at least one level below /tmp)
  // F-007: /tmp itself is too broad — require /tmp/<project-name>/
  const tmpWithSep = tmpResolved.endsWith(sep) ? tmpResolved : tmpResolved + sep;
  if (resolved.startsWith(tmpWithSep)) {
    return resolved;
  }

  // Out of bounds — fall back to cwd
  return process.cwd();
}
```

### Key changes explained

| Change | Addresses | Explanation |
|--------|-----------|-------------|
| `realpathSync('/tmp')` → `tmpResolved` | F-006 | macOS: `/tmp` → `/private/tmp`; check uses real path |
| `realpathSync(dir)` for project dir | F-008 | Follow symlinks before prefix check |
| `startsWith(tmpResolved + sep)` instead of `startsWith('/tmp')` | F-006 + F-007 | Real path + requires at least one subdir |
| `startsWith(home + sep)` instead of `startsWith(home)` | F-008 (side benefit) | Avoids `/home/alice` matching `/home/alice-evil` |

### Import additions required

`realpathSync` must be added to the `fs` import at the top of `utils.mjs`:

```javascript
// Before:
import { existsSync, readFileSync, writeFileSync } from 'fs';

// After:
import { existsSync, readFileSync, writeFileSync, realpathSync } from 'fs';
```

`sep` must be added to the `path` import:

```javascript
// Before:
import { join, dirname, normalize, resolve } from 'path';

// After (also removes unused dirname — see F-026):
import { join, normalize, resolve, sep } from 'path';
```

---

## Impact Tree

### Upstream (all hooks call getProjectDir())

Every hook that calls `getProjectDir()` is affected by this fix:

| Hook | Usage | Effect of fix |
|------|-------|---------------|
| `pre-edit.mjs` | spec path, LOC check | Correct project root on macOS CI |
| `post-edit.mjs` | project boundary check | Correct boundary — no more /tmp-wide ruff |
| `validate-spec-complete.mjs` | spec file resolution (after BUG-121) | Correct root |
| `utils.mjs` `loadConfig()` | config path | Symlink-safe config loading |
| `utils.mjs` `inferSpecFromBranch()` | spec dir path (after BUG-121) | Correct root |
| `session-end.mjs` | diary path (after BUG-121) | Correct root |

### Downstream (what breaks if NOT fixed)

- macOS CI: All hooks fall back to `cwd()` instead of project root → enforcement silently broken
- `/tmp` root attack: Ruff-formats any `.py` anywhere in `/tmp`
- Symlink bypass: Attacker-controlled project dir outside home boundary executes arbitrary JS

### Functions that call getProjectDir()

```bash
grep -n "getProjectDir()" .claude/hooks/
```

Expected callers:
- `utils.mjs`: `loadConfig()`, `inferSpecFromBranch()`
- `pre-edit.mjs`: `normalizePath()`, LOC check (after BUG-121)
- `post-edit.mjs`: project boundary
- `validate-spec-complete.mjs`: spec resolution (after BUG-121)
- `session-end.mjs`: diary path (after BUG-121)

---

## Test Requirements

All tests in `test/getProjectDir-safety.test.mjs`.

### Test 1 — F-006: macOS /tmp symlink resolution

```javascript
// Simulate macOS environment where /tmp -> /private/tmp
// Input: CLAUDE_PROJECT_DIR = '/tmp/myproject'
// (After realpathSync, becomes '/private/tmp/myproject')
// Expected: getProjectDir() returns '/private/tmp/myproject' (valid, inside real /tmp)
// Before fix: '/private/tmp/myproject'.startsWith('/tmp') = false → returns cwd()

// Test using the actual resolved path:
const tmpReal = realpathSync('/tmp');  // '/private/tmp' on macOS
const testDir = join(tmpReal, 'myproject');
// Set CLAUDE_PROJECT_DIR = testDir
// Assert getProjectDir() === testDir
```

### Test 2 — F-007: /tmp root rejected

```javascript
// Input: CLAUDE_PROJECT_DIR = '/tmp' (or realpathSync equivalent)
// Expected: getProjectDir() returns process.cwd() (not '/tmp')
// Because: /tmp itself is too broad — requires at least /tmp/<name>
```

### Test 3 — F-008: Symlink to outside home rejected

```javascript
// Create symlink: /tmp/test-symlink -> /etc  (or any path outside home and /tmp)
// Input: CLAUDE_PROJECT_DIR = '/tmp/test-symlink'
// Expected: getProjectDir() returns process.cwd() (symlink escapes to /etc)
// Before fix: resolve('/tmp/test-symlink') = '/tmp/test-symlink' → startsWith('/tmp') = true → WRONG
```

### Test 4 — Normal home directory path still works

```javascript
// Input: CLAUDE_PROJECT_DIR = join(homedir(), 'projects', 'myapp')
// Expected: getProjectDir() returns the same path
// Ensure: fix does not break the common case
```

### Test 5 — /tmp subdir still works

```javascript
// Input: CLAUDE_PROJECT_DIR = '/tmp/test-project' (real path on macOS: '/private/tmp/test-project')
// Expected: getProjectDir() returns realpathSync('/tmp/test-project')
// Not cwd() fallback
```

### Test 6 — /tmp with sep prevents prefix collision

```javascript
// Input: CLAUDE_PROJECT_DIR resolves to '/private/tmp-extra/project'
// Expected: getProjectDir() returns cwd() (not inside /tmp — it's /tmp-extra)
// Verifies the sep-based check prevents false positives
```

---

## Definition of Done

- [ ] `utils.mjs`: `getProjectDir()` uses `realpathSync()` for both `/tmp` resolution and project dir resolution
- [ ] `utils.mjs`: Boundary check uses `startsWith(tmpResolved + sep)` — requires subdir below `/tmp`
- [ ] `utils.mjs`: Boundary check uses `startsWith(home + sep)` — prevents prefix collision
- [ ] `utils.mjs`: `realpathSync` added to `fs` import
- [ ] `utils.mjs`: `sep` added to `path` import
- [ ] All 6 tests above pass
- [ ] Existing test suite still passes: `./test fast`
- [ ] Verified on macOS: `CLAUDE_PROJECT_DIR=/tmp/testdir node -e "import('./utils.mjs').then(m => console.log(m.getProjectDir()))"` returns `/private/tmp/testdir` (not `cwd()`)

---

## Dependency on BUG-121

This fix is independent of BUG-121 (Worktree Path Resolution). Both can be implemented in
parallel. However, the combined effect is:

- BUG-121: Ensures hooks USE `getProjectDir()` everywhere
- BUG-122: Ensures `getProjectDir()` RETURNS the correct value

Both are required for full worktree + macOS correctness.

---

## Change History

| Date | What | Who |
|------|------|-----|
| 2026-02-18 | Created from bughunt 20260218-hooks, findings F-006, F-007, F-008 | bughunt/solution-architect |
