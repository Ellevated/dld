# Feature: [BUG-097] Test Infrastructure for Hooks

**Status:** done | **Priority:** P0 | **Date:** 2026-02-17

## Why

8 hook files (~970 LOC) with zero tests. Every bug fix (BUG-102 through BUG-120) was done blind — no regression testing, no way to verify fixes don't break each other. This is the single biggest quality risk in the DLD framework.

## Context

- Hooks are Node.js ESM (.mjs) files in `template/.claude/hooks/`
- They communicate via stdin (JSON) → stdout (JSON) protocol
- Each hook type has different protocol: PreToolUse, PostToolUse, UserPromptSubmit, Stop
- ADR-004: hooks must never crash (bare catch for fail-safe)
- Already fixed: BUG-102, 103, 104, 118, 119, 120 — all without regression tests

---

## Scope

**In scope:**
- Test framework setup using Node.js built-in `node:test` (zero deps)
- Unit tests for all pure/exportable functions in utils.mjs
- Unit tests for pure functions in each hook (patterns, matchers, helpers)
- Integration tests for hook I/O (spawn hook, pipe stdin, check stdout/exit code)
- Test runner script

**Out of scope:**
- E2E tests with actual Claude Code CLI
- Performance benchmarks
- Test coverage tooling (c8/istanbul)

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.claude/hooks/__tests__/utils.test.mjs` — unit tests for utils.mjs
2. `template/.claude/hooks/__tests__/pre-bash.test.mjs` — unit tests for pre-bash
3. `template/.claude/hooks/__tests__/pre-edit.test.mjs` — unit tests for pre-edit
4. `template/.claude/hooks/__tests__/prompt-guard.test.mjs` — unit tests for prompt-guard
5. `template/.claude/hooks/__tests__/validate-spec-complete.test.mjs` — unit tests for validate-spec-complete
6. `template/.claude/hooks/__tests__/post-edit.test.mjs` — unit tests for post-edit
7. `template/.claude/hooks/__tests__/session-end.test.mjs` — unit tests for session-end
8. `template/.claude/hooks/__tests__/run-hook.test.mjs` — unit tests for run-hook
9. `template/.claude/hooks/__tests__/integration.test.mjs` — integration tests (hook I/O)
10. `template/.claude/hooks/__tests__/helpers.mjs` — shared test helpers (spawn hook, mock stdin)
11. `template/.claude/hooks/package.json` — test script only (no deps)

**New files allowed:**
- All files in `template/.claude/hooks/__tests__/` — test directory

**FORBIDDEN:** All other files. Do NOT modify existing hook source code.

---

## Environment

nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: node:test + child_process (Selected)

**Summary:** Use Node.js built-in test runner (`node:test`, `node:assert`). Unit tests import functions directly from .mjs. Integration tests spawn hooks via `child_process.execFile` and pipe JSON stdin.

**Pros:**
- Zero dependencies (node:test ships with Node 18+)
- ESM-native (hooks are .mjs)
- Integration tests validate real hook protocol

**Cons:**
- node:test is minimal (no fancy matchers)
- child_process integration tests are slower

### Approach 2: vitest

**Summary:** Use vitest for richer testing features (mocking, snapshots).

**Pros:** Better DX, built-in mocking
**Cons:** Adds dependency, template should be zero-dep

### Selected: 1

**Rationale:** Hooks are zero-dependency infrastructure. Test framework must match. node:test is built into Node 18+ which is already a prerequisite.

---

## Design

### Test Strategy

**Unit tests (fast, isolated):** Import exported functions directly and test with assert.

```javascript
// Example: utils.test.mjs
import { describe, it } from 'node:test';
import { strictEqual } from 'node:assert';
import { extractAllowedFiles, isFileAllowed } from '../utils.mjs';

describe('extractAllowedFiles', () => {
  it('extracts paths from Allowed Files section', () => { ... });
});
```

**Integration tests (spawn hook process):** Test the full hook flow by spawning as child process.

```javascript
// Example: helpers.mjs
import { execFileSync } from 'child_process';
export function runHook(hookFile, stdinData) {
  const input = JSON.stringify(stdinData);
  try {
    const stdout = execFileSync('node', [hookFile], {
      input,
      encoding: 'utf-8',
      timeout: 5000,
      env: { ...process.env, CLAUDE_PROJECT_DIR: '/tmp/test-project' },
    });
    return { exitCode: 0, stdout: stdout ? JSON.parse(stdout.trim()) : null };
  } catch (e) {
    return { exitCode: e.status, stdout: e.stdout ? JSON.parse(e.stdout.trim()) : null };
  }
}
```

### What to Test Per File

**utils.mjs (highest priority — shared by all hooks):**
- `minimatch()` — glob patterns: `*`, `**`, `?`, character classes, edge cases
- `extractAllowedFiles()` — markdown parsing, backtick/bold paths, empty section, line ranges
- `isFileAllowed()` — ALWAYS_ALLOWED_PATTERNS, spec-based allowlist, no spec = allow all
- `inferSpecFromBranch()` — branch name parsing, task ID extraction
- `getProjectDir()` — path traversal protection, fallback to cwd
- `readHookInput()` — valid JSON, empty input, malformed JSON
- `outputJson()` — flush behavior (via integration test)

**pre-bash.mjs:**
- `isDestructiveClean()` — `git clean -fd`, `git clean --force -d`, `-fdn` dry-run, edge cases
- BLOCKED_PATTERNS — push to main, force push to protected branches, false positives (fix-main-menu)
- MERGE_PATTERNS — merge, merge-base (should NOT match), --ff-only bypass

**pre-edit.mjs:**
- `countLines()` — trailing newline handling, empty file, missing file
- `isTestFile()` — all patterns: `_test.`, `.test.`, `.spec.`, `/tests/`, `__tests__/`, `test_prefix.py`
- `normalizePath()` — absolute to relative conversion, Windows path normalization
- `checkSyncZone()` — sync zones, exclude list, template exists check
- LOC limits — 400/600 thresholds, warning at 87.5%, test file detection
- Protected paths — `tests/contracts/`, `tests/regression/`

**prompt-guard.mjs:**
- COMPLEXITY_PATTERNS — "implement feature", "write function", gap limits
- SKILL_INDICATORS — `/spark`, `/autopilot`, word boundaries

**validate-spec-complete.mjs:**
- `stripCodeBlocks()` — removes triple-backtick blocks
- git commit detection — `git commit` (match), `git commit-graph` (no match)
- Impact Tree checkbox detection — `- [ ]` in Impact Tree section

**post-edit.mjs:**
- File type filtering — .py files only, non-.py skipped
- Tool name filtering — Write, Edit, MultiEdit only
- Project boundary check

**session-end.mjs:**
- `countPending()` — count `| pending |` in file, missing file, empty file

**run-hook.mjs:**
- Hook name validation — alphanumeric/hyphens only, path traversal prevention

---

## Implementation Plan

### Task 1: Create test helpers and package.json

**Type:** code
**Files:**
  - create: `template/.claude/hooks/__tests__/helpers.mjs`
  - create: `template/.claude/hooks/package.json`
**Acceptance:**
  - `helpers.mjs` exports `runHook()` function for integration tests
  - `package.json` has `"test"` script: `"node --test __tests__/*.test.mjs"`
  - `cd template/.claude/hooks && npm test` runs (even if 0 tests)

### Task 2: Unit tests for utils.mjs

**Type:** test
**Files:**
  - create: `template/.claude/hooks/__tests__/utils.test.mjs`
**Acceptance:**
  - Tests for minimatch: at least 15 cases (*, **, ?, exact match, no match, edge cases)
  - Tests for extractAllowedFiles: 5+ cases (markdown formats, empty, error)
  - Tests for isFileAllowed: 8+ cases (always-allowed, spec-allowed, denied, no spec)
  - Tests for getProjectDir: 3+ cases (normal, traversal, fallback)
  - All tests pass

### Task 3: Unit tests for pre-bash.mjs

**Type:** test
**Files:**
  - create: `template/.claude/hooks/__tests__/pre-bash.test.mjs`
**Acceptance:**
  - Tests for isDestructiveClean: 8+ cases
  - Tests for blocked patterns: 10+ cases (positive and negative)
  - Tests for merge patterns: 5+ cases
  - Integration test: spawn pre-bash with dangerous command → exit with deny
  - All tests pass

### Task 4: Unit tests for pre-edit.mjs

**Type:** test
**Files:**
  - create: `template/.claude/hooks/__tests__/pre-edit.test.mjs`
**Acceptance:**
  - Tests for countLines: 5+ cases (empty, trailing newline, no newline)
  - Tests for isTestFile: 10+ cases (all patterns)
  - Tests for LOC enforcement via integration
  - Tests for protected paths via integration
  - All tests pass

### Task 5: Unit tests for remaining hooks

**Type:** test
**Files:**
  - create: `template/.claude/hooks/__tests__/prompt-guard.test.mjs`
  - create: `template/.claude/hooks/__tests__/validate-spec-complete.test.mjs`
  - create: `template/.claude/hooks/__tests__/post-edit.test.mjs`
  - create: `template/.claude/hooks/__tests__/session-end.test.mjs`
  - create: `template/.claude/hooks/__tests__/run-hook.test.mjs`
**Acceptance:**
  - Each hook has 3+ test cases minimum
  - prompt-guard: complexity patterns + skill indicators
  - validate-spec-complete: stripCodeBlocks + git commit regex
  - session-end: countPending
  - run-hook: hookName validation
  - All tests pass

### Task 6: Integration tests

**Type:** test
**Files:**
  - create: `template/.claude/hooks/__tests__/integration.test.mjs`
**Acceptance:**
  - Test each hook type via child_process spawn
  - PreToolUse hooks: verify deny/allow/ask JSON output
  - PostToolUse hooks: verify continue/block JSON output
  - UserPromptSubmit hooks: verify approve/block JSON output
  - Stop hooks: verify approve output
  - Fail-safe test: malformed stdin → hook exits 0 (ADR-004)
  - All tests pass

### Execution Order

1 → 2 → 3 → 4 → 5 → 6

---

## Tests (MANDATORY)

### What to test
- [ ] All pure functions in utils.mjs produce correct output
- [ ] pre-bash blocks dangerous commands and allows safe ones
- [ ] pre-edit enforces LOC limits and protected paths
- [ ] prompt-guard detects complexity and skips when skills are used
- [ ] Hook protocol: correct JSON format for deny/allow/ask/approve/block
- [ ] ADR-004 fail-safe: malformed input never crashes hooks

### How to test
- Unit: import functions directly, assert with node:assert
- Integration: spawn hooks via child_process, pipe JSON stdin, check stdout

### TDD Order
1. Write helpers.mjs → 2. Write tests → 3. Verify all pass against existing code

---

## Definition of Done

### Functional
- [ ] All test files created in `__tests__/` directory
- [ ] `cd template/.claude/hooks && npm test` passes
- [ ] 60+ test cases total across all files

### Tests
- [ ] Each hook file has its own test file
- [ ] Integration tests cover all 4 hook protocols
- [ ] ADR-004 fail-safe behavior verified

### Technical
- [ ] Zero dependencies (only node:test, node:assert, child_process)
- [ ] Tests run on Node.js 18+
- [ ] No modifications to existing hook source code

---

## Autopilot Log
[Auto-populated by autopilot during execution]
