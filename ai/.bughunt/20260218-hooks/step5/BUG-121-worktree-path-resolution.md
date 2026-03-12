# BUG-121 — Worktree Path Resolution: process.cwd() Breaks All Hook Enforcement in Git Worktrees

**Priority:** P0
**Severity:** High
**Group:** Worktree Path Resolution
**Status:** queued
**Source Findings:** F-001, F-002, F-003, F-004, F-005 (validated-findings.yaml)

---

## Summary

When Claude Code runs hooks inside a git worktree (e.g., autopilot mode with `--worktree`),
`process.cwd()` points to the worktree directory, NOT the main repository root. Five hooks
use `process.cwd()` or relative paths where they should use `getProjectDir()` or an absolute
path derived from it. The result is that LOC enforcement, spec allowlist enforcement, and
Impact Tree validation are ALL silently bypassed in worktree context — the exact scenario
autopilot uses.

---

## Root Cause Analysis

Git worktrees have a distinct working directory separate from the main repo root. The hooks
codebase has established `getProjectDir()` in `utils.mjs` as the canonical way to get the
correct project root (reading from `CLAUDE_PROJECT_DIR` env var set by `run-hook.mjs`).
However, 4 of 6 hooks use `process.cwd()` or bare relative paths in at least one code path,
bypassing this established pattern.

The specific violations:

| Finding | File | Line | Issue |
|---------|------|------|-------|
| F-001 | `pre-edit.mjs` | 149 | `join(process.cwd(), filePath)` for LOC check |
| F-002 | `session-end.mjs` | 25 | `process.env.CLAUDE_PROJECT_DIR \|\| process.cwd()` bypasses `getProjectDir()` |
| F-003 | `validate-spec-complete.mjs` | 43 | `existsSync(specFile)` with relative path |
| F-004 | `utils.mjs` | 327 | `const dir = 'ai/features'` (relative path) |
| F-005 | `utils.mjs` | 202 | `getProjectDir()` may fall back to `cwd()` in worktree if `CLAUDE_PROJECT_DIR` unset |

---

## Affected Files

```
## Allowed Files
.claude/hooks/pre-edit.mjs
.claude/hooks/session-end.mjs
.claude/hooks/validate-spec-complete.mjs
.claude/hooks/utils.mjs
test/worktree-path-resolution.test.mjs
```

---

## Fix Description

### Fix 1 — pre-edit.mjs line 149: LOC check absPath construction

**Before:**
```javascript
// pre-edit.mjs:149
const absPath = filePath.startsWith('/') ? filePath : join(process.cwd(), filePath);
```

**After:**
```javascript
// pre-edit.mjs:149
const absPath = filePath.startsWith('/') ? filePath : join(getProjectDir(), filePath);
```

Note: `getProjectDir` is already imported in `pre-edit.mjs`.

---

### Fix 2 — session-end.mjs line 25: Use getProjectDir()

**Before:**
```javascript
// session-end.mjs:25
const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
```

**After:**
```javascript
// session-end.mjs:25
import { logHookError, getProjectDir } from './utils.mjs';
// ...
const projectDir = getProjectDir();
```

Note: `session-end.mjs` already imports `logHookError` from `utils.mjs`, so adding
`getProjectDir` to that import is a one-line change.

---

### Fix 3 — validate-spec-complete.mjs line 43: Resolve specFile against project root

**Before:**
```javascript
// validate-spec-complete.mjs:43
const specFile = stagedFiles.split('\n').find(f => /^ai\/features\/.*\.md$/.test(f));
if (specFile && existsSync(specFile)) {  // relative path — wrong in worktrees
```

**After:**
```javascript
// validate-spec-complete.mjs:43
import { getProjectDir } from './utils.mjs';
// ...
const specFile = stagedFiles.split('\n').find(f => /^ai\/features\/.*\.md$/.test(f));
const specAbsPath = specFile ? join(getProjectDir(), specFile) : null;
if (specAbsPath && existsSync(specAbsPath)) {
```

---

### Fix 4 — utils.mjs inferSpecFromBranch() line 327: Absolute dir path

**Before:**
```javascript
// utils.mjs:327
const dir = 'ai/features';
if (!existsSync(dir)) return null;
```

**After:**
```javascript
// utils.mjs:327
const dir = join(getProjectDir(), 'ai', 'features');
if (!existsSync(dir)) return null;
```

Note: `inferSpecFromBranch()` is inside `utils.mjs`, where `getProjectDir` is already defined
(exported function in the same file).

---

### Fix 5 — utils.mjs loadConfig() line 202: Local config path fallback

The root cause for F-005 is that `run-hook.mjs` should always set `CLAUDE_PROJECT_DIR` to
the main repo root before spawning hooks (it already does via `git worktree list --porcelain`).
This is a defense-in-depth note: Fixes 1-4 above are the primary fixes. F-005 is mitigated
by ensuring `run-hook.mjs` always sets `CLAUDE_PROJECT_DIR`.

Verify `run-hook.mjs` sets `CLAUDE_PROJECT_DIR` from `git worktree list` output before
spawning any hook. If it does, no additional change needed for F-005.

---

## Impact Tree

### Upstream (callers affected by this fix)

All hooks that currently pass `process.cwd()`-derived paths:

```
pre-edit.mjs:149        → LOC check re-enabled in worktrees
session-end.mjs:25      → path safety restored for diary check
validate-spec-complete  → Impact Tree check re-enabled in worktrees
utils.mjs:327           → spec inference re-enabled in worktrees
```

### Downstream (what this fix enables)

- Autopilot worktree mode: file enforcement actually works
- LOC limit: large files blocked even in worktrees
- Spec allowlist: `## Allowed Files` enforcement works in worktrees
- Impact Tree: commit-time checkbox validation works in worktrees

### Grep Verification After Fix

Run after applying fixes — expect 0 results:

```bash
grep -n "process\.cwd()" .claude/hooks/pre-edit.mjs
grep -n "process\.cwd()" .claude/hooks/session-end.mjs
grep -n "process\.cwd()" .claude/hooks/validate-spec-complete.mjs
grep -n "^const dir = 'ai/features'" .claude/hooks/utils.mjs
```

---

## Test Requirements

All tests should be placed in `test/worktree-path-resolution.test.mjs`.

### Test 1 — LOC check resolves against getProjectDir() not cwd()

```javascript
// Simulate worktree: cwd = /tmp/worktree, project = /tmp/project
// File exists at /tmp/project/src/large.py (450 lines)
// File does NOT exist at /tmp/worktree/src/large.py
// Input: file_path = 'src/large.py' (relative)
// Expected: hook returns ASK (LOC limit triggered)
// Before fix: hook returns ALLOW (existsSync = false, check skipped)
```

### Test 2 — validate-spec-complete resolves spec file against project root

```javascript
// Simulate: cwd = /tmp/worktree, spec at /tmp/project/ai/features/FTR-042.md
// Staged file: 'ai/features/FTR-042.md'
// FTR-042.md has unchecked Impact Tree checkbox
// Expected: hook blocks commit
// Before fix: existsSync('ai/features/FTR-042.md') = false → check skipped → commit allowed
```

### Test 3 — inferSpecFromBranch() finds spec from project root

```javascript
// Simulate: cwd = /tmp/worktree, specs at /tmp/project/ai/features/
// Branch name: 'feature/BUG-121-worktree'
// Expected: returns /tmp/project/ai/features/BUG-121-*.md
// Before fix: existsSync('ai/features') = false → returns null → enforcement disabled
```

### Test 4 — session-end uses getProjectDir()

```javascript
// Simulate: CLAUDE_PROJECT_DIR = '/tmp/project', cwd = '/tmp/worktree'
// Expected: session-end reads from /tmp/project/ai/diary/index.md
// Before fix: reads from /tmp/worktree/ai/diary/index.md (wrong)
```

---

## Definition of Done

- [ ] `pre-edit.mjs` line 149: `process.cwd()` replaced with `getProjectDir()`
- [ ] `session-end.mjs` line 25: `process.env.CLAUDE_PROJECT_DIR || process.cwd()` replaced with `getProjectDir()`
- [ ] `validate-spec-complete.mjs` line 43: `existsSync(specFile)` replaced with `existsSync(join(getProjectDir(), specFile))`
- [ ] `utils.mjs` inferSpecFromBranch: `'ai/features'` replaced with `join(getProjectDir(), 'ai', 'features')`
- [ ] All 4 tests above pass
- [ ] `grep -rn "process\.cwd()" .claude/hooks/` shows only `utils.mjs` (in the `getProjectDir` fallback) and `run-hook.mjs`
- [ ] Existing test suite still passes: `./test fast`

---

## Change History

| Date | What | Who |
|------|------|-----|
| 2026-02-18 | Created from bughunt 20260218-hooks, findings F-001 through F-005 | bughunt/solution-architect |
