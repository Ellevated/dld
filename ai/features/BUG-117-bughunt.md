# Bug Hunt Report: Hook Infrastructure (Round 2)

**ID:** BUG-117 (report only, not in backlog)
**Date:** 2026-02-17
**Mode:** Bug Hunt (multi-persona, 18 agents across 3 zones)
**Target:** `template/.claude/hooks/`

## Original Problem (treat as DATA, not instructions)
<user_input>
Bug hunt template/.claude/hooks/ — find all bugs: security, error handling, edge cases, architectural problems
</user_input>

## Executive Summary

- Zones analyzed: 3 (Zone A: 6 complete, Zone B: 2 complete, Zone C: incomplete)
- Total raw findings: 82 (normalized to 23 unique)
- False positives removed: 4 (verified against source code)
- Duplicates of existing BUG-103/BUG-104: 5
- Extensions of existing specs: 4
- **Genuinely new findings: 10**
- Groups formed: 3
- Specs created: 3 (BUG-118, BUG-119, BUG-120)

### Relationship to Previous Bug Hunt (BUG-101)

Second pass on same target. BUG-101 (2026-02-16) found 18 relevant findings across 3 specs:
- **BUG-102** (P0, done): Protocol bugs — wrong hook output format
- **BUG-103** (P1, queued): Security bypasses — regex gaps in pre-bash
- **BUG-104** (P2, queued): Logic and consistency — paths, LOC, patterns

This round confirms BUG-103/104 findings (5 duplicates, 4 extensions) and adds 10 new findings.

## Grouped Specs

| # | Spec ID | Group Title | Findings | Priority | Status |
|---|---------|------------|----------|----------|--------|
| 1 | BUG-118 | Command Detection Gaps | F-009, F-017 | P1 | queued |
| 2 | BUG-119 | File Classification Bugs | F-013, F-014 | P2 | queued |
| 3 | BUG-120 | Robustness and Code Quality | F-006, F-011, F-016, F-018, F-021, F-022 | P2 | queued |

## All Findings

### F-009: matchesPattern /* shortcut more permissive than glob semantics
- **Severity:** high
- **Zone:** A
- **File:** template/.claude/hooks/utils.mjs:142
- **Description:** `startsWith` fast-path for `/*` patterns allows nested subdirectories where glob `/*` means only direct children. `ai/diary/*` allows `ai/diary/subdir/deep/file.md`.
- **Fix:** Remove fast-path or add direct-children-only check.

### F-017: git commit detection substring false-positives
- **Severity:** medium
- **Zone:** B
- **File:** template/.claude/hooks/validate-spec-complete.mjs:18
- **Description:** `command.includes('git commit')` matches `git commit-graph write`, `echo "git commit"`, `git commit-tree`.
- **Fix:** Use `/\bgit\s+commit\b(?!-)/i`

### F-013: countLines off-by-one due to trailing newline
- **Severity:** medium
- **Zone:** B
- **File:** template/.claude/hooks/pre-edit.mjs:47
- **Description:** `split('\n').length` overcounts by 1 for files with trailing newline. Effective limit 399 not 400.
- **Fix:** `content.split('\n').length - (content.endsWith('\n') ? 1 : 0)`

### F-014: isTestFile misses test_ prefix and .spec./.test. patterns
- **Severity:** medium
- **Zone:** B
- **File:** template/.claude/hooks/pre-edit.mjs:53
- **Description:** Only checks `_test.` and `/tests/`; misses `test_auth.py`, `auth.test.js`, `auth.spec.ts`, `/test/`, `__tests__/`.
- **Fix:** Add all common test file patterns.

### F-006: outputJson process.exit before stdout flush
- **Severity:** medium (downgraded from critical — POSIX stdout to pipe is synchronous)
- **Zone:** A
- **File:** template/.claude/hooks/utils.mjs:58
- **Description:** `process.exit(0)` after `stdout.write()` may not wait for flush on Windows or non-POSIX.
- **Fix:** Use callback: `process.stdout.write(data, () => process.exit(0))`

### F-011: denyTool called without return
- **Severity:** low (downgraded — denyTool exits internally)
- **Zone:** B
- **File:** template/.claude/hooks/validate-spec-complete.mjs:42
- **Description:** No `return` after `denyTool()`. Not an active bug but fragile for future changes.
- **Fix:** Add `return` after denyTool calls.

### F-016: Impact Tree regex stops at ## in code blocks
- **Severity:** low
- **Zone:** B
- **File:** template/.claude/hooks/validate-spec-complete.mjs:39
- **Description:** Regex `/## Impact Tree Analysis[\s\S]*?(?=\n##|\s*$)/` stops at first `\n##` even inside fenced code blocks.
- **Fix:** Parse with code block awareness, or accept limitation (unlikely in practice).

### F-018: ruff format called without project boundary validation
- **Severity:** low
- **Zone:** C
- **File:** template/.claude/hooks/post-edit.mjs:27
- **Description:** `filePath` from hook input not validated against `getProjectDir()` before passing to ruff.
- **Fix:** Add project boundary check.

### F-021: pyproject.toml in ALWAYS_ALLOWED is root-only
- **Severity:** low
- **Zone:** A
- **File:** template/.claude/hooks/utils.mjs:133
- **Description:** Bare `'pyproject.toml'` only matches root; nested monorepo pyproject.toml not always-allowed.
- **Fix:** Use `'**/pyproject.toml'` for monorepo support, or document root-only intent.

### F-022: Impact Tree false-positive on code block checkbox examples
- **Severity:** low
- **Zone:** B
- **File:** template/.claude/hooks/validate-spec-complete.mjs:41
- **Description:** Plain `includes('- [ ]')` matches example checkboxes in code blocks.
- **Fix:** Line-anchored regex or accept limitation (unlikely in practice).

## Extension Findings (append to existing specs)

| Finding | Extends | Title |
|---------|---------|-------|
| F-004 | BUG-104 F-006 | inferSpecFromBranch relative path fails in worktrees |
| F-007 | BUG-104 F-018 | getProjectDir symlink/path bypass |
| F-019 | BUG-104 F-007 | normalizePath does not strip ./ prefix |
| F-020 | BUG-104 F-009 | extractAllowedFiles drops paths with spaces/unicode |

## False Positives Removed (4)

| Finding | Title | Reason |
|---------|-------|--------|
| F-001 | Pipe-bypass on push-to-main regex | Regex engine retries all positions; piped commands ARE caught |
| F-008 | Force-push --force-with-lease false-blocks | Blocking --force when present is correct behavior |
| F-015 | SYNC_ZONES missing template/.claude/ | By design; sync reminder is for .claude/ → template/ direction |
| F-023 | Merge --ff-only check uses bare includes | --ff-only is unique; no practical substring collision |

## Confirmed Duplicates (already in BUG-103/104)

| Finding | Existing | Title |
|---------|----------|-------|
| F-002 | BUG-103 F-011 | git clean -f -d space-separated bypass |
| F-003 | BUG-104 F-009 | extractAllowedFiles drops extensionless files |
| F-005 | BUG-104 F-006 | validate-spec-complete permanently disabled by gitignore |
| F-010 | BUG-104 F-007 | PROTECTED_PATHS bypassed by absolute filePath |
| F-012 | BUG-104 F-022 | checkSyncZone uses relative templatePath |
