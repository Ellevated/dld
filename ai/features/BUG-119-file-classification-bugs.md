# Bug Fix: [BUG-119] File Classification Bugs

**Status:** queued | **Priority:** P2 | **Date:** 2026-02-17
**Bug Hunt Report:** [BUG-117](BUG-117-bughunt.md)

## Findings in This Group

| ID | Severity | Title |
|----|----------|-------|
| F-013 | medium | countLines off-by-one due to trailing newline |
| F-014 | medium | isTestFile misses test_ prefix and .spec./.test. patterns |

## Problem

Both findings are in `template/.claude/hooks/pre-edit.mjs`, the pre-edit hook that enforces LOC limits (400 for code, 600 for tests). Two helper functions used in the LOC enforcement path are incorrect:

### F-013: countLines off-by-one (line 45-51)

Current code:

```javascript
function countLines(filePath) {
  try {
    return readFileSync(filePath, 'utf-8').split('\n').length;
  } catch {
    return 0;
  }
}
```

`String.split('\n').length` overcounts by 1 for files ending with a trailing newline (which is the POSIX standard and the default for virtually all editors and formatters). A file with exactly 400 lines ending in `\n` has content like `line1\nline2\n...\nline400\n`. Splitting on `\n` produces 401 elements (the last being an empty string). This means the effective LOC limit is 399 for code files and 599 for test files -- one line less than documented in CLAUDE.md and architecture.md.

**Concrete impact:** A 400-line code file triggers the `askTool` soft block ("File exceeds LOC limit!") even though it is exactly at the limit. The documented limit says 400 is acceptable, but the hook blocks at 400.

### F-014: isTestFile misses common patterns (line 53-55)

Current code:

```javascript
function isTestFile(filePath) {
  return filePath.includes('_test.') || filePath.includes('/tests/');
}
```

This function determines whether a file gets the 600-line limit (test) or 400-line limit (code). It only recognizes two patterns:
- `_test.` (Go-style: `service_test.go`, Python: `service_test.py`)
- `/tests/` (directory)

**Missed patterns** (all common in real projects):
| Pattern | Example | Convention |
|---------|---------|------------|
| `test_` prefix | `test_auth.py` | Python (pytest default) |
| `.test.` infix | `auth.test.js`, `auth.test.ts` | JavaScript/TypeScript (Jest) |
| `.spec.` infix | `auth.spec.ts` | Angular, Vitest |
| `/test/` directory | `test/helpers.js` | Node.js, Java |
| `__tests__/` directory | `__tests__/auth.js` | Jest convention |

**Concrete impact:** A Python `test_auth.py` file at 450 lines gets the 400-line code limit instead of the 600-line test limit. The hook incorrectly fires a soft block for a test file that is well within its real limit.

**Note:** The project's own `codebase-inventory.mjs` (lines 67-71) already has the correct comprehensive pattern list:

```javascript
const TEST_PATTERNS = [
  /test[_/]/i, /tests[_/]/i, /spec[_/]/i, /specs[_/]/i,
  /__tests__/i, /\.test\.\w+$/, /\.spec\.\w+$/, /_test\.\w+$/,
  /test_\w+\.py$/, /\w+_test\.go$/,
];
```

The fix should align `isTestFile` with this existing pattern set.

## Root Cause

Both functions are simplified implementations that handle only the most common case and miss edge cases. `countLines` does not account for the standard trailing newline in text files. `isTestFile` was written with only Go/Python `_test.` and a single directory convention in mind, ignoring JS/TS ecosystem patterns and the Python `test_` prefix convention.

## Solution

### Fix 1: Fix countLines to handle trailing newline

Replace the naive `split('\n').length` with a version that subtracts 1 when the file ends with a newline:

```javascript
function countLines(filePath) {
  try {
    const content = readFileSync(filePath, 'utf-8');
    if (!content) return 0;
    return content.split('\n').length - (content.endsWith('\n') ? 1 : 0);
  } catch {
    return 0;
  }
}
```

### Fix 2: Expand isTestFile to cover all common patterns

Replace the two `includes` checks with a comprehensive pattern list using the same approach as `codebase-inventory.mjs`:

```javascript
const TEST_FILE_PATTERNS = [
  /_test\./, /\.test\./, /\.spec\./,
  /\/tests?\//, /__tests__\//,
  /\/test_[^/]+\.py$/,
];

function isTestFile(filePath) {
  return TEST_FILE_PATTERNS.some(pattern => pattern.test(filePath));
}
```

### Fix 3: Sync root copy

Per template-sync.md rules, after fixing `template/.claude/hooks/pre-edit.mjs`, the identical changes must be applied to `.claude/hooks/pre-edit.mjs`.

## Scope

### What changes:
1. `countLines` function body in `template/.claude/hooks/pre-edit.mjs` (lines 45-51)
2. `isTestFile` function body in `template/.claude/hooks/pre-edit.mjs` (lines 53-55)
3. Identical sync to `.claude/hooks/pre-edit.mjs` (lines 45-55)

### What does NOT change:
- Function signatures (no API change)
- LOC constants (`MAX_LOC_CODE = 400`, `MAX_LOC_TEST = 600`)
- Warning threshold logic
- Any other hook file
- `utils.mjs` (no changes needed)
- `codebase-inventory.mjs` (already correct, reference only)

## Allowed Files

1. `template/.claude/hooks/pre-edit.mjs` -- fix countLines and isTestFile (primary)
2. `.claude/hooks/pre-edit.mjs` -- sync identical changes from template (template-sync rule)

## Impact Tree Analysis

### UP -- who uses?

- [x] `template/.claude/hooks/pre-edit.mjs` is a PreToolUse hook for Edit/Write operations
- [x] Called by Claude Code on every file edit attempt
- [x] `countLines` is called on line 129, result compared against `maxLoc`
- [x] `isTestFile` is called on line 130 to determine which limit applies
- [x] No other files import or call these functions (they are local to pre-edit.mjs)

### DOWN -- what depends on?

- [x] `countLines` depends on: `readFileSync` from `fs`
- [x] `isTestFile` depends on: nothing (pure string check)
- [x] Both are used only in the LOC limit check block (lines 126-150)

### BY TERM -- grep project

| File | Line | Status | Action |
|------|------|--------|--------|
| `template/.claude/hooks/pre-edit.mjs` | 45-51 | needs fix | Fix countLines trailing newline |
| `template/.claude/hooks/pre-edit.mjs` | 53-55 | needs fix | Expand isTestFile patterns |
| `.claude/hooks/pre-edit.mjs` | 45-51 | needs sync | Mirror countLines fix from template |
| `.claude/hooks/pre-edit.mjs` | 53-55 | needs sync | Mirror isTestFile fix from template |
| `template/.claude/scripts/codebase-inventory.mjs` | 67-71 | reference only | Has correct TEST_PATTERNS |

### CHECKLIST -- mandatory folders

- [x] No migrations needed
- [x] No edge functions affected
- [x] Tests: Currently no hook tests exist

## Research Sources

- POSIX text file standard: files end with a trailing newline character
- JavaScript `String.split()` behavior: `"a\nb\n".split('\n')` returns `["a", "b", ""]` (3 elements for 2 lines)
- `template/.claude/scripts/codebase-inventory.mjs` lines 67-71: existing comprehensive TEST_PATTERNS array

## Implementation Plan

### Task 1: Fix countLines in template/.claude/hooks/pre-edit.mjs (line 47)

1. Add empty content early return
2. Subtract 1 from split length when content ends with newline

### Task 2: Fix isTestFile in template/.claude/hooks/pre-edit.mjs (lines 53-55)

1. Add `TEST_FILE_PATTERNS` array of regex patterns above the function
2. Replace two `includes()` calls with `.some(pattern => pattern.test(filePath))`
3. Patterns: `/_test\./`, `/\.test\./`, `/\.spec\./`, `/\/tests?\//`, `/__tests__\//`, `/\/test_[^/]+\.py$/`

### Task 3: Sync to .claude/hooks/pre-edit.mjs

1. Copy exact same changes to root copy
2. Verify both files are identical after changes

### Task 4: Manual verification

1. Create a test file with 400 lines + trailing newline, confirm countLines returns 400 (not 401)
2. Create a test file with 400 lines + no trailing newline, confirm countLines returns 400
3. Verify empty file returns 0
4. Verify isTestFile returns true for: `test_auth.py`, `auth.test.js`, `auth.spec.ts`, `src/test/helpers.js`, `src/__tests__/auth.js`, `service_test.go`, `src/tests/unit.py`
5. Verify isTestFile returns false for: `src/auth.py`, `contest.js`, `latest.py`, `testimony.md`

## Definition of Done

- [ ] F-013 fixed: `countLines` on a 400-line file with trailing newline returns exactly 400
- [ ] F-013 edge case: empty file returns 0
- [ ] F-013 edge case: file without trailing newline counts correctly
- [ ] F-014 fixed: `isTestFile('test_auth.py')` returns true
- [ ] F-014 fixed: `isTestFile('auth.test.js')` returns true
- [ ] F-014 fixed: `isTestFile('auth.spec.ts')` returns true
- [ ] F-014 fixed: `isTestFile('src/test/helpers.js')` returns true
- [ ] F-014 fixed: `isTestFile('src/__tests__/auth.js')` returns true
- [ ] F-014 no false positives: `isTestFile('contest.js')` returns false
- [ ] F-014 no false positives: `isTestFile('latest.py')` returns false
- [ ] F-014 no false positives: `isTestFile('testimony.md')` returns false
- [ ] Both copies in sync: `template/.claude/hooks/pre-edit.mjs` identical to `.claude/hooks/pre-edit.mjs`
- [ ] No regressions: existing `_test.` and `/tests/` patterns still work
- [ ] Hook still fail-safe: errors in countLines/isTestFile caught by outer try/catch

## Relationship

This spec was created from **BUG-117** (Bug Hunt Report: Hook Infrastructure Round 2). BUG-117 is a READ-ONLY report, not a backlog entry.

Related specs from the same bug hunt:
- **BUG-118** (P1, queued): Command Detection Gaps (F-009, F-017)
- **BUG-120** (P2, queued): Robustness and Code Quality (F-006, F-011, F-016, F-018, F-021, F-022)

Related specs from the previous bug hunt (BUG-101):
- **BUG-104** (P2, queued): Logic and consistency issues (covers different pre-edit.mjs findings)
