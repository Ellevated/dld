# Bug Fix: [BUG-120] Robustness and Code Quality

**Status:** queued | **Priority:** P2 | **Date:** 2026-02-17
**Bug Hunt Report:** [BUG-117](BUG-117-bughunt.md)

## Findings in This Group

| ID | Severity | Title | File |
|----|----------|-------|------|
| F-006 | medium | outputJson process.exit before stdout flush | `template/.claude/hooks/utils.mjs:58` |
| F-011 | low | denyTool called without return | `template/.claude/hooks/validate-spec-complete.mjs:42` |
| F-016 | low | Impact Tree regex stops at ## in code blocks | `template/.claude/hooks/validate-spec-complete.mjs:39` |
| F-018 | low | ruff format called without project boundary validation | `template/.claude/hooks/post-edit.mjs:27` |
| F-021 | low | pyproject.toml in ALWAYS_ALLOWED is root-only | `template/.claude/hooks/utils.mjs:133` |
| F-022 | low | Impact Tree false-positive on code block checkbox examples | `template/.claude/hooks/validate-spec-complete.mjs:41` |

## Root Cause

Six independent hardening gaps in the hooks subsystem, grouped by theme: robustness and code quality. No single root cause -- these are defense-in-depth improvements across three files. The common thread is that each finding represents a code path that works in the happy case but can fail or produce incorrect results in edge cases (Windows pipe semantics, monorepo layouts, specs with code blocks, path traversal via hook input).

## Problem

### F-006: outputJson process.exit before stdout flush

In `template/.claude/hooks/utils.mjs` lines 58-65:

```javascript
function outputJson(data) {
  try {
    process.stdout.write(JSON.stringify(data) + '\n');
  } catch {
    // pipe closed early — OK
  }
  process.exit(0);
}
```

`process.stdout.write()` is asynchronous when stdout is a pipe (which it is when Claude Code reads hook output). Calling `process.exit(0)` immediately after can truncate the JSON output before it reaches the parent process. This is a well-documented Node.js issue (nodejs/node#3669, nodejs/node#2972). On Windows, this is especially prevalent. The same pattern also exists in `session-end.mjs` where `process.stdout.write()` is followed by `process.exit(0)`.

### F-011: denyTool called without return

In `template/.claude/hooks/validate-spec-complete.mjs` lines 41-50:

```javascript
if (impactSection && impactSection[0].includes('- [ ]')) {
    denyTool(
      'Spec has unfilled Impact Tree checkboxes!\n\n' + ...
    );
}

process.exit(0);
```

`denyTool()` calls `outputJson()` which calls `process.exit(0)`, so the missing `return` is currently harmless -- execution never reaches line 53. However, if `outputJson` or `denyTool` is ever refactored to not exit (e.g., to use the callback flush pattern from F-006), code would fall through. Compare with `pre-edit.mjs` line 108 and `pre-bash.mjs` line 89, which both correctly `return` after `denyTool()`.

### F-016: Impact Tree regex stops at `##` in code blocks

In `template/.claude/hooks/validate-spec-complete.mjs` line 39:

```javascript
const impactSection = content.match(/## Impact Tree Analysis[\s\S]*?(?=\n##|\s*$)/);
```

The `(?=\n##` lookahead stops matching at the first `\n##` -- including `##` characters inside fenced code blocks. If a spec contains a code block with `## Some Heading` inside the Impact Tree section, the regex truncates early.

### F-018: ruff format called without project boundary validation

In `template/.claude/hooks/post-edit.mjs`:

The `filePath` from hook input is passed directly to `ruff format` without validating it falls within `getProjectDir()`. While Claude Code itself constrains file paths, a malformed hook input could cause `ruff` to operate on files outside the project boundary.

### F-021: pyproject.toml in ALWAYS_ALLOWED is root-only

In `template/.claude/hooks/utils.mjs` lines 133-140:

```javascript
const ALWAYS_ALLOWED_PATTERNS = [
  'ai/features/*.md',
  'ai/backlog.md',
  'ai/diary/*',
  '.gitignore',
  'pyproject.toml',  // <-- bare name, no glob
  '.claude/*',
];
```

The bare string `'pyproject.toml'` only matches the root-level file. In a monorepo with `packages/foo/pyproject.toml`, those nested files would not be always-allowed.

### F-022: Impact Tree false-positive on code block checkbox examples

In `template/.claude/hooks/validate-spec-complete.mjs` line 41:

```javascript
if (impactSection && impactSection[0].includes('- [ ]')) {
```

Plain `includes('- [ ]')` matches literal `- [ ]` anywhere in the extracted section -- including inside fenced code blocks that show checkbox examples.

## Solution

### F-006: Use write callback for process.exit

Change `outputJson` to use the `process.stdout.write` callback to wait for the buffer to flush before calling `process.exit(0)`. Add a safety timeout so hooks never hang. Also apply the same pattern to `session-end.mjs`.

```javascript
function outputJson(data) {
  try {
    process.stdout.write(JSON.stringify(data) + '\n', () => process.exit(0));
  } catch {
    process.exit(0); // pipe closed early — exit anyway
  }
  setTimeout(() => process.exit(0), 500); // safety net
}
```

### F-011: Add return after denyTool

Add `return` after the `denyTool()` call in `validate-spec-complete.mjs`. Consistent with `pre-edit.mjs` and `pre-bash.mjs`.

### F-016 and F-022: Code-block-aware Impact Tree parsing

Strip fenced code blocks from the Impact Tree section before checking for unchecked checkboxes:

```javascript
function stripCodeBlocks(text) {
  return text.replace(/```[\s\S]*?```/g, '');
}
```

Apply after extracting `impactSection`, before the `includes('- [ ]')` check.

### F-018: Add project boundary check before ruff invocation

Import `getProjectDir` from `utils.mjs`, resolve the `filePath` to an absolute path, verify it starts with `getProjectDir()` before passing to `ruff`. If outside boundary, skip formatting.

### F-021: Document root-only intent with inline comment

The `pyproject.toml` entry is intentionally root-only. DLD projects are not monorepos by convention. Add an inline comment: `'pyproject.toml', // root-only; monorepos customize locally`

## Scope

**Changes:**
- `template/.claude/hooks/utils.mjs` -- F-006 (outputJson flush), F-021 (comment)
- `template/.claude/hooks/validate-spec-complete.mjs` -- F-011 (return), F-016+F-022 (code block stripping)
- `template/.claude/hooks/post-edit.mjs` -- F-018 (boundary check)
- `template/.claude/hooks/session-end.mjs` -- F-006 (flush pattern)

**Does NOT change:**
- `.claude/hooks/*` (DLD-local copies) -- synced separately per template-sync rule
- No changes to hook APIs (denyTool, allowTool, etc. signatures unchanged)
- No new dependencies (pure Node.js)
- No behavior changes for happy-path scenarios

**After template changes are verified, sync to DLD-local copies:**
- `.claude/hooks/utils.mjs`
- `.claude/hooks/validate-spec-complete.mjs`
- `.claude/hooks/post-edit.mjs`
- `.claude/hooks/session-end.mjs`

## Allowed Files

1. `template/.claude/hooks/utils.mjs` -- F-006 outputJson flush fix, F-021 comment
2. `template/.claude/hooks/validate-spec-complete.mjs` -- F-011 return, F-016+F-022 code block stripping
3. `template/.claude/hooks/post-edit.mjs` -- F-018 project boundary check
4. `template/.claude/hooks/session-end.mjs` -- F-006 flush pattern
5. `.claude/hooks/utils.mjs` -- sync from template
6. `.claude/hooks/validate-spec-complete.mjs` -- sync from template
7. `.claude/hooks/post-edit.mjs` -- sync from template
8. `.claude/hooks/session-end.mjs` -- sync from template

## Impact Tree Analysis

### UP -- who uses the affected functions?

**`outputJson()`** (private in utils.mjs, called by exported functions):
- [x] `denyTool()` -- called from `pre-bash.mjs`, `pre-edit.mjs`, `validate-spec-complete.mjs`
- [x] `askTool()` -- called from `pre-bash.mjs`, `pre-edit.mjs`
- [x] `approvePrompt()` -- called from `prompt-guard.mjs`
- [x] `blockPrompt()` -- called from `prompt-guard.mjs`
- [x] `postContinue()` -- called from `post-edit.mjs`
- [x] `postBlock()` -- exported but unused

**`ALWAYS_ALLOWED_PATTERNS`** (private in utils.mjs):
- [x] `isFileAllowed()` -- called from `pre-edit.mjs:93`

### DOWN -- what do the affected files depend on?

- [x] `utils.mjs`: fs, path, os, child_process
- [x] `validate-spec-complete.mjs`: fs, child_process, ./utils.mjs
- [x] `post-edit.mjs`: fs, path, child_process, ./utils.mjs — will add getProjectDir import
- [x] `session-end.mjs`: fs, path, ./utils.mjs

### BY TERM -- grep across project

| Term | File | Line | Status | Action |
|------|------|------|--------|--------|
| `process.exit(0)` after `stdout.write` | `template/.claude/hooks/utils.mjs` | 64 | needs fix | Move into write callback |
| `process.exit(0)` after `stdout.write` | `template/.claude/hooks/session-end.mjs` | 42 | needs fix | Move into write callback |
| `denyTool(` without return | `template/.claude/hooks/validate-spec-complete.mjs` | 42 | needs fix | Add return |
| `denyTool(` with return | `template/.claude/hooks/pre-bash.mjs` | 88-89 | OK | Already has return |
| `denyTool(` with return | `template/.claude/hooks/pre-edit.mjs` | 96-108 | OK | Already has return |
| `'pyproject.toml'` | `template/.claude/hooks/utils.mjs` | 138 | needs comment | Add root-only comment |
| `includes('- [ ]')` | `template/.claude/hooks/validate-spec-complete.mjs` | 41 | needs fix | Strip code blocks first |

### CHECKLIST -- mandatory folders

- [x] `template/.claude/hooks/` -- all changes here (primary)
- [x] `.claude/hooks/` -- sync copies
- [x] No migrations involved
- [x] No edge functions involved

## Research Sources

- https://github.com/nodejs/node/issues/3669 -- `process.stdout.write` data loss with `process.exit()`
- https://github.com/nodejs/node/issues/2972 -- stdout not completely flushed on process exit
- https://github.com/cowboy/node-exit -- Library specifically addressing this flush issue
- Node.js official docs: `process.exit()` is an "emergency handbrake" that terminates immediately

## Implementation Plan

### Task 1: Fix outputJson flush in utils.mjs (F-006, F-021)

**File:** `template/.claude/hooks/utils.mjs`

1. Modify `outputJson()` (lines 58-65): move `process.exit(0)` into the callback of `process.stdout.write()`, add `setTimeout(500)` safety net
2. Add inline comment on `'pyproject.toml'` (line 138): `// root-only; monorepos customize locally`

### Task 2: Fix validate-spec-complete.mjs (F-011, F-016, F-022)

**File:** `template/.claude/hooks/validate-spec-complete.mjs`

1. Add `return` after the `denyTool()` call (after line 49)
2. Add `stripCodeBlocks(text)` helper that removes content between triple-backtick fences
3. After extracting `impactSection`, strip code blocks before `includes('- [ ]')` check

### Task 3: Add project boundary check in post-edit.mjs (F-018)

**File:** `template/.claude/hooks/post-edit.mjs`

1. Add `getProjectDir` to the import from `./utils.mjs`
2. Import `resolve` from `path`
3. After `existsSync(filePath)` check, validate filePath starts with `getProjectDir()`
4. If outside boundary, skip formatting

### Task 4: Fix session-end.mjs flush (F-006)

**File:** `template/.claude/hooks/session-end.mjs`

1. Apply the same flush pattern as Task 1 to `process.stdout.write()` + `process.exit(0)`
2. Add `setTimeout(500)` safety net

### Task 5: Sync to DLD-local copies

1. Copy each modified template file to the corresponding `.claude/hooks/` path
2. Verify file contents match

## Definition of Done

- [ ] F-006: `outputJson()` uses write callback before `process.exit(0)` with timeout safety net
- [ ] F-006: `session-end.mjs` uses same flush pattern
- [ ] F-011: `return` added after `denyTool()` in `validate-spec-complete.mjs`
- [ ] F-016: Code block content stripped before Impact Tree section boundary detection
- [ ] F-018: `post-edit.mjs` validates `filePath` against `getProjectDir()` before ruff invocation
- [ ] F-021: `pyproject.toml` entry in `ALWAYS_ALLOWED_PATTERNS` has root-only comment
- [ ] F-022: Code block content stripped before `includes('- [ ]')` check
- [ ] All four template files synced to `.claude/hooks/` local copies
- [ ] No new hook crashes (ADR-004 compliance)
- [ ] Impact tree verified: grep for all changed terms shows 0 stale references

## Relationship

This spec addresses 6 findings from Bug Hunt report [BUG-117](BUG-117-bughunt.md), grouped under "Robustness and Code Quality." These are hardening fixes -- none represent active bugs that cause failures in normal operation, but each addresses a code path that could fail under specific conditions (Windows, monorepos, specs with code blocks, malformed hook input).

Related specs from the same bug hunt:
- **BUG-118** (P1, queued): Command Detection Gaps (F-009, F-017)
- **BUG-119** (P2, queued): File Classification Bugs (F-013, F-014)

Related specs from the previous bug hunt (BUG-101):
- **BUG-103** (P1, queued): Security bypasses in pre-bash regex patterns
- **BUG-104** (P2, queued): Logic and consistency issues in path handling
