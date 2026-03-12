# Bug Fix: [BUG-118] Command Detection Gaps

**Status:** queued | **Priority:** P1 | **Date:** 2026-02-17
**Bug Hunt Report:** [BUG-117](BUG-117-bughunt.md)

## Findings in This Group

| ID | Severity | Title |
|----|----------|-------|
| F-009 | high | matchesPattern /* shortcut more permissive than glob semantics |
| F-017 | medium | git commit detection substring false-positives |

## Problem

### F-009: matchesPattern `/*` fast-path allows deep nesting

In `template/.claude/hooks/utils.mjs`, lines 142-148:

```javascript
function matchesPattern(filePath, pattern) {
  if (pattern.endsWith('/*')) {
    const dirPrefix = pattern.slice(0, -1); // "ai/diary/*" -> "ai/diary/"
    return filePath.startsWith(dirPrefix);
  }
  return minimatch(filePath, pattern);
}
```

The `startsWith` check means a pattern like `ai/diary/*` matches `ai/diary/subdir/deep/file.md`. In standard glob semantics, `/*` means only direct children -- a single `*` does not match `/`. The `minimatch` function on line 155 correctly handles this (it converts `*` to `[^/]*`), but the fast-path on line 143-146 bypasses this correct behavior.

**Same bug exists a second time** in `isFileAllowed`, lines 290-294:

```javascript
    // Prefix match (allow subdirs)
    const prefix = allowed.replace(/\/\*$/, '') + '/';
    if (filePath.startsWith(prefix)) {
      return { allowed: true, allowedFiles: result.files };
    }
```

This code explicitly says "allow subdirs" in its comment, which is also incorrect for `/*` glob patterns. A spec entry like `src/utils/*` would allow `src/utils/deep/nested/secret.mjs`.

**Impact:** The `ALWAYS_ALLOWED_PATTERNS` array contains `ai/diary/*`, `ai/features/*.md`, and `.claude/*`. The diary and .claude patterns are especially concerning -- `.claude/*` as a glob should only allow direct children of `.claude/`, but the fast-path allows `.claude/deeply/nested/anything` to bypass spec enforcement.

**Mitigating factor:** In practice, the `ALWAYS_ALLOWED_PATTERNS` are intentionally permissive zones, and `.claude/**` would be the "correct" pattern if deep nesting were desired. The real risk is in user-supplied Allowed Files from specs (the second occurrence at line 290), where a spec author writing `src/hooks/*` expects single-level matching but gets recursive.

### F-017: git commit detection matches unrelated git subcommands

In `template/.claude/hooks/validate-spec-complete.mjs`, line 18:

```javascript
    if (!command.includes('git commit')) {
      process.exit(0);
    }
```

`String.includes('git commit')` is a plain substring match. It triggers on:
- `git commit-graph write` -- a legitimate git plumbing command
- `git commit-tree abc123` -- another plumbing command
- `echo "git commit"` -- string in an echo statement
- `git commit-graph verify` -- graph verification

This causes the hook to unnecessarily check for Impact Tree completeness on commands that are not actual commits, potentially blocking legitimate operations.

## Solution

### Fix 1: Replace `matchesPattern` fast-path with correct direct-children check

**Remove** the `startsWith` fast-path entirely from `matchesPattern`. The `minimatch` function already handles `/*` patterns correctly -- it converts `*` to `[^/]*` which does NOT match path separators. The fast-path was a premature optimization that introduced incorrect behavior.

The function becomes a simple pass-through to `minimatch`:

```javascript
function matchesPattern(filePath, pattern) {
  return minimatch(filePath, pattern);
}
```

### Fix 1b: Remove duplicate prefix match in `isFileAllowed`

Lines 290-294 perform the SAME incorrect `startsWith` match for spec Allowed Files. This code block should be removed entirely. The `minimatch` call on line 287 already handles `/*` patterns correctly. The prefix match is redundant (duplicates minimatch behavior) and incorrect (allows deep nesting).

### Fix 1c: Evaluate and update `ALWAYS_ALLOWED_PATTERNS` if needed

After the fix, `ai/diary/*` will only match files directly in `ai/diary/`, not `ai/diary/subdir/file.md`. If deep nesting should be allowed, the pattern must be changed to `ai/diary/**`. Review each pattern:

| Pattern | Current behavior | After fix | Action needed? |
|---------|-----------------|-----------|---------------|
| `ai/features/*.md` | Matches `ai/features/deep/x.md` | Only `ai/features/x.md` | No -- specs are flat |
| `ai/diary/*` | Matches `ai/diary/deep/x.md` | Only `ai/diary/x.md` | Change to `ai/diary/**` if nested diaries exist |
| `.claude/*` | Matches `.claude/deep/nested/x` | Only `.claude/x` | Change to `.claude/**` to keep current intent |

### Fix 2: Replace `includes('git commit')` with regex

Replace the substring check with a regex that:
1. Matches `git commit` as a standalone command (not `git commit-graph`, `git commit-tree`)
2. Uses word boundary and negative lookahead for hyphen

```javascript
if (!/\bgit\s+commit\b(?!-)/i.test(command)) {
  process.exit(0);
}
```

This regex:
- `\b` ensures `git` is a word boundary (not part of `fugit`)
- `\s+` allows flexible whitespace between `git` and `commit`
- `\b` after `commit` ensures it is a complete word
- `(?!-)` negative lookahead rejects `commit-graph`, `commit-tree`, etc.
- `/i` for case insensitivity

## Scope

### What changes

1. `matchesPattern` function in `utils.mjs` -- remove the `/*` fast-path (lines 142-148)
2. `isFileAllowed` function in `utils.mjs` -- remove the redundant prefix match block (lines 290-294)
3. `ALWAYS_ALLOWED_PATTERNS` -- update patterns to `**` where deep nesting is intended
4. `validate-spec-complete.mjs` -- replace `command.includes('git commit')` with regex (line 18)

### What does NOT change

- `minimatch` function (already correct)
- `extractAllowedFiles` function (parsing logic is unrelated)
- `pre-bash.mjs` (already uses proper regex patterns)
- `pre-edit.mjs` (caller of `isFileAllowed`, no changes needed)
- `post-edit.mjs`, `prompt-guard.mjs`, `session-end.mjs`, `run-hook.mjs` (unrelated)

## Allowed Files

1. `template/.claude/hooks/utils.mjs` -- Fix `matchesPattern` fast-path (lines 142-148) and remove redundant prefix match (lines 290-294), update ALWAYS_ALLOWED_PATTERNS
2. `template/.claude/hooks/validate-spec-complete.mjs` -- Replace `includes('git commit')` with regex (line 18)
3. `.claude/hooks/utils.mjs` -- Sync from template (per template-sync rule)
4. `.claude/hooks/validate-spec-complete.mjs` -- Sync from template (per template-sync rule)

## Impact Tree Analysis

### UP -- who uses the changed code?

**`matchesPattern`** (private function in utils.mjs):
- [x] Called by `isFileAllowed` at line 260 -- iterates `ALWAYS_ALLOWED_PATTERNS`
- [x] `isFileAllowed` is exported and called by `template/.claude/hooks/pre-edit.mjs:93`

**`isFileAllowed` prefix match block** (lines 290-294):
- [x] Part of the `isFileAllowed` function, same callers as above

**`command.includes('git commit')` in validate-spec-complete.mjs**:
- [x] Called within `main()` of that hook
- [x] Hook is triggered by Claude Code for PreToolUse on Bash tool
- [x] No other code calls into validate-spec-complete.mjs

### DOWN -- what does the changed code depend on?

**`matchesPattern`:**
- [x] Calls `minimatch` (internal, same file, line 155) -- no change needed
- [x] Uses `String.startsWith`, `String.endsWith`, `String.slice` -- built-ins

**`validate-spec-complete.mjs` line 18:**
- [x] Uses `String.includes` (being replaced with `RegExp.test`) -- built-in
- [x] No external dependencies affected

### BY TERM -- grep project

| Term | File | Line | Status | Action |
|------|------|------|--------|--------|
| `startsWith(dirPrefix)` | `template/.claude/hooks/utils.mjs` | 145 | needs fix | Remove fast-path |
| `startsWith(dirPrefix)` | `.claude/hooks/utils.mjs` | 145 | needs sync | Sync from template |
| `startsWith(prefix)` (in isFileAllowed) | `template/.claude/hooks/utils.mjs` | 292 | needs fix | Remove redundant prefix match block |
| `startsWith(prefix)` (in isFileAllowed) | `.claude/hooks/utils.mjs` | 292 | needs sync | Sync from template |
| `includes('git commit')` | `template/.claude/hooks/validate-spec-complete.mjs` | 18 | needs fix | Replace with regex |
| `includes('git commit')` | `.claude/hooks/validate-spec-complete.mjs` | 18 | needs sync | Sync from template |

### CHECKLIST -- mandatory folders

| Folder | Relevant? | Action |
|--------|-----------|--------|
| tests/ | Yes | No tests exist yet for hooks; regression tests should be created |
| migrations/ | No | N/A |

## Implementation Plan

### Task 1: Fix `matchesPattern` in template utils.mjs

1. Replace lines 142-148 -- remove the `endsWith('/*')` fast-path entirely
2. Function becomes simple pass-through to `minimatch`

### Task 2: Remove redundant prefix match in `isFileAllowed`

1. Remove lines 290-294 (the `// Prefix match (allow subdirs)` block)
2. The `minimatch` call on line 287 already handles glob patterns

### Task 3: Update `ALWAYS_ALLOWED_PATTERNS`

1. Change `.claude/*` to `.claude/**` (has nested content: rules/, agents/, skills/, contexts/, hooks/)
2. Change `ai/diary/*` to `ai/diary/**` if nested subdirectories exist
3. Leave `ai/features/*.md` unchanged (specs are flat)

### Task 4: Fix git commit detection in validate-spec-complete.mjs

1. Replace line 18: `if (!command.includes('git commit'))` with `if (!/\bgit\s+commit\b(?!-)/i.test(command))`

### Task 5: Sync to .claude/hooks/

1. Copy fixed `utils.mjs` from `template/.claude/hooks/` to `.claude/hooks/`
2. Copy fixed `validate-spec-complete.mjs` from `template/.claude/hooks/` to `.claude/hooks/`

### Task 6: Manual verification

1. Verify `matchesPattern('ai/diary/sub/deep.md', 'ai/diary/*')` returns `false`
2. Verify `matchesPattern('ai/diary/today.md', 'ai/diary/*')` returns `true`
3. Verify `matchesPattern('.claude/hooks/utils.mjs', '.claude/**')` returns `true`
4. Verify `/\bgit\s+commit\b(?!-)/i.test('git commit -m "msg"')` returns `true`
5. Verify `/\bgit\s+commit\b(?!-)/i.test('git commit-graph write')` returns `false`
6. Verify `/\bgit\s+commit\b(?!-)/i.test('git commit-tree abc')` returns `false`
7. Verify `/\bgit\s+commit\b(?!-)/i.test('git commit --amend')` returns `true`

## Definition of Done

- [ ] `matchesPattern` no longer uses `startsWith` fast-path; delegates to `minimatch` for all patterns
- [ ] `isFileAllowed` redundant prefix match block (lines 290-294) removed
- [ ] `ALWAYS_ALLOWED_PATTERNS` reviewed -- patterns updated to `**` where deep nesting is intended
- [ ] `validate-spec-complete.mjs` uses regex `/\bgit\s+commit\b(?!-)/i` instead of `includes('git commit')`
- [ ] Template files synced to `.claude/hooks/`
- [ ] Manual verification: glob `/*` only matches direct children
- [ ] Manual verification: `git commit-graph` and `git commit-tree` no longer trigger the hook
- [ ] No regressions: `git commit -m "msg"` and `git commit --amend` still trigger the hook
- [ ] Grep `startsWith(dirPrefix)` across project returns 0 results
- [ ] Grep `includes('git commit')` across `.mjs` files returns 0 results

## Relationship

This spec was created from **BUG-117** (Bug Hunt Report: Hook Infrastructure Round 2). BUG-117 is a READ-ONLY report, not a backlog entry. This spec (BUG-118) is the actionable backlog entry for the "Command Detection Gaps" group.

Related specs from the same bug hunt:
- **BUG-119** (P2, queued): File Classification Bugs (F-013, F-014)
- **BUG-120** (P2, queued): Robustness and Code Quality (F-006, F-011, F-016, F-018, F-021, F-022)

Related specs from the previous bug hunt (BUG-101):
- **BUG-103** (P1, queued): Security bypasses in pre-bash regex patterns
- **BUG-104** (P2, queued): Logic and consistency issues in path handling
