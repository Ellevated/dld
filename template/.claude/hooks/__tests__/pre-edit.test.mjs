/**
 * Integration tests for pre-edit.mjs
 *
 * Tests the hook's three main behaviors:
 * 1. Protected paths (Hard Block) — tests/contracts/ and tests/regression/
 * 2. LOC enforcement (Soft Block) — ASK when file exceeds or approaches limit
 * 3. isTestFile detection — determines which LOC limit applies (400 vs 600)
 * 4. countLines accuracy — verified via LOC threshold triggers
 *
 * Run: node --test __tests__/pre-edit.test.mjs
 */

import { describe, it, before, after } from 'node:test';
import { strictEqual, ok } from 'node:assert';
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { runHook, makePreToolInput } from './helpers.mjs';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let tmpDir;

/** Write a file with exactly `n` non-empty lines (no trailing newline). */
function makeFile(name, lines) {
  const path = join(tmpDir, name);
  const content = Array.from({ length: lines }, (_, i) => `line${i + 1}`).join('\n');
  writeFileSync(path, content, 'utf-8');
  return path;
}

/** Write a file with exactly `n` lines with a trailing newline. */
function makeFileWithNewline(name, lines) {
  const path = join(tmpDir, name);
  const content = Array.from({ length: lines }, (_, i) => `line${i + 1}`).join('\n') + '\n';
  writeFileSync(path, content, 'utf-8');
  return path;
}

/** Write a file with the given raw content string. */
function makeFileRaw(name, content) {
  const path = join(tmpDir, name);
  writeFileSync(path, content, 'utf-8');
  return path;
}

function isDeny(result) {
  return (
    result.exitCode === 0 &&
    result.stdout?.hookSpecificOutput?.permissionDecision === 'deny'
  );
}

function isAsk(result) {
  return (
    result.exitCode === 0 &&
    result.stdout?.hookSpecificOutput?.permissionDecision === 'ask'
  );
}

function isAllow(result) {
  return result.exitCode === 0 && result.stdout === null;
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

before(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'pre-edit-test-'));
});

after(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// Protected paths — Hard Block
// ---------------------------------------------------------------------------

describe('protected paths', () => {
  it('denies edit to tests/contracts/ file', () => {
    const input = makePreToolInput('Edit', {
      file_path: 'tests/contracts/foo.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isDeny(result), `expected deny, got: ${JSON.stringify(result.stdout)}`);
  });

  it('deny reason mentions tests/contracts/', () => {
    const input = makePreToolInput('Edit', {
      file_path: 'tests/contracts/schema.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isDeny(result));
    ok(
      result.stdout.hookSpecificOutput.permissionDecisionReason.includes('tests/contracts/'),
      'reason should mention tests/contracts/'
    );
  });

  it('denies edit to tests/regression/ file', () => {
    const input = makePreToolInput('Edit', {
      file_path: 'tests/regression/bar.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isDeny(result), `expected deny, got: ${JSON.stringify(result.stdout)}`);
  });

  it('denies nested file inside tests/regression/', () => {
    const input = makePreToolInput('Edit', {
      file_path: 'tests/regression/subdir/deep.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isDeny(result), `expected deny for nested regression path`);
  });

  it('allows edit to tests/unit/ (not protected)', () => {
    const input = makePreToolInput('Edit', {
      file_path: 'tests/unit/baz.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `expected allow for tests/unit/, got: ${JSON.stringify(result.stdout)}`);
  });

  it('allows edit to a path that merely contains the word contracts (not a protected prefix)', () => {
    const input = makePreToolInput('Edit', {
      file_path: 'src/contracts_service.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `expected allow for contracts in filename, got: ${JSON.stringify(result.stdout)}`);
  });
});

// ---------------------------------------------------------------------------
// LOC enforcement — code files (limit = 400, warn at 350)
// ---------------------------------------------------------------------------

describe('LOC enforcement — code files', () => {
  it('allows code file under LOC limit (300 lines)', () => {
    const absPath = makeFile('small_code.py', 300);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `expected allow for 300-line file, got: ${JSON.stringify(result.stdout)}`);
  });

  it('asks for code file at exactly the LOC limit (400 lines)', () => {
    const absPath = makeFile('at_limit_code.py', 400);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `expected ask for 400-line file, got: ${JSON.stringify(result.stdout)}`);
  });

  it('asks for code file exceeding LOC limit (401 lines)', () => {
    const absPath = makeFile('over_limit_code.py', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `expected ask for 401-line file, got: ${JSON.stringify(result.stdout)}`);
  });

  it('asks for code file in warn zone (350 lines, >= 87.5% of 400)', () => {
    // warn threshold = floor(400 * 7/8) = floor(350) = 350
    const absPath = makeFile('warn_zone_code.py', 350);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `expected ask for 350-line file (warn zone), got: ${JSON.stringify(result.stdout)}`);
  });

  it('allows code file just below warn zone (349 lines)', () => {
    const absPath = makeFile('under_warn_code.py', 349);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `expected allow for 349-line file, got: ${JSON.stringify(result.stdout)}`);
  });
});

// ---------------------------------------------------------------------------
// LOC enforcement — test files (limit = 600, warn at 525)
// ---------------------------------------------------------------------------

describe('LOC enforcement — test files', () => {
  it('allows test file under LOC limit (400 lines)', () => {
    // A test file named foo_test.py should have the higher limit (600)
    const absPath = makeFile('foo_test.py', 400);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `expected allow for 400-line test file, got: ${JSON.stringify(result.stdout)}`);
  });

  it('asks for test file at exactly the test LOC limit (600 lines)', () => {
    const absPath = makeFile('bar_test.py', 600);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `expected ask for 600-line test file, got: ${JSON.stringify(result.stdout)}`);
  });

  it('asks for test file exceeding test LOC limit (601 lines)', () => {
    const absPath = makeFile('baz_test.py', 601);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `expected ask for 601-line test file, got: ${JSON.stringify(result.stdout)}`);
  });

  it('asks for test file in warn zone (525 lines, >= 87.5% of 600)', () => {
    // warn threshold = floor(600 * 7/8) = floor(525) = 525
    const absPath = makeFile('warn_test.py', 525);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `expected ask for 525-line test file (warn zone), got: ${JSON.stringify(result.stdout)}`);
  });

  it('allows test file just below warn zone (524 lines)', () => {
    const absPath = makeFile('ok_test.py', 524);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `expected allow for 524-line test file, got: ${JSON.stringify(result.stdout)}`);
  });
});

// ---------------------------------------------------------------------------
// isTestFile detection — LOC limit selection
// ---------------------------------------------------------------------------

describe('isTestFile — LOC limit selection', () => {
  // Each test verifies that a file with 401 lines (over code limit, under test limit)
  // is treated as ASK for code files but ALLOW for test files.

  it('foo_test.py is treated as a test file (400 lines allowed)', () => {
    const absPath = makeFile('module_test.py', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `foo_test.py with 401 lines should be allowed (test limit=600)`);
  });

  it('foo.test.js is treated as a test file', () => {
    const absPath = makeFile('module.test.js', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `foo.test.js with 401 lines should be allowed`);
  });

  it('foo.spec.ts is treated as a test file', () => {
    const absPath = makeFile('module.spec.ts', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `foo.spec.ts with 401 lines should be allowed`);
  });

  it('test_foo.py at root level is treated as a test file', () => {
    const absPath = makeFile('test_module.py', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `test_foo.py with 401 lines should be allowed`);
  });

  it('main.py is NOT a test file (code limit applies)', () => {
    const absPath = makeFile('main.py', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `main.py with 401 lines should trigger ASK (code limit=400)`);
  });

  it('testing.py is NOT a test file (no pattern match)', () => {
    const absPath = makeFile('testing.py', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `testing.py should NOT be a test file — code limit applies`);
  });

  it('contest.py is NOT a test file (no pattern match)', () => {
    const absPath = makeFile('contest.py', 401);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `contest.py should NOT be a test file — code limit applies`);
  });
});

// ---------------------------------------------------------------------------
// countLines accuracy — edge cases
// ---------------------------------------------------------------------------

describe('countLines — edge cases via LOC trigger', () => {
  it('empty file (0 lines) is allowed', () => {
    const absPath = makeFileRaw('empty.py', '');
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `empty file should be allowed`);
  });

  it('single line with trailing newline (1 line) is allowed', () => {
    const absPath = makeFileRaw('single_newline.py', 'hello\n');
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `single line with newline should be allowed`);
  });

  it('content with trailing newline: 400 lines = exactly at limit (ASK)', () => {
    // 400 lines with trailing newline: "line1\nline2\n...\nline400\n"
    // split('\n') → 401 elements, endsWith('\n') → subtract 1 → 400 lines
    const absPath = makeFileWithNewline('at_limit_newline.py', 400);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `400 lines with trailing newline should trigger ASK`);
  });

  it('content without trailing newline: 400 lines = exactly at limit (ASK)', () => {
    // 400 lines without trailing newline: "line1\nline2\n...\nline400"
    // split('\n') → 400 elements, no endsWith('\n') → 400 lines
    const absPath = makeFile('at_limit_no_newline.py', 400);
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAsk(result), `400 lines without trailing newline should trigger ASK`);
  });

  it('non-existent file path is allowed (countLines returns 0)', () => {
    const absPath = join(tmpDir, 'nonexistent_file.py');
    const input = makePreToolInput('Edit', { file_path: absPath });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `non-existent file should be allowed (0 lines)`);
  });
});

// ---------------------------------------------------------------------------
// General behavior — allow, Write tool, edge inputs
// ---------------------------------------------------------------------------

describe('general behavior', () => {
  it('allows Write tool for a normal file', () => {
    const input = makePreToolInput('Write', {
      file_path: 'src/new_module.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isAllow(result), `Write to new module should be allowed`);
  });

  it('denies Write tool to tests/contracts/', () => {
    const input = makePreToolInput('Write', {
      file_path: 'tests/contracts/new_contract.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isDeny(result), `Write to contracts should be denied`);
  });

  it('allows when file_path is empty string', () => {
    const input = makePreToolInput('Edit', { file_path: '' });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    // Empty path: relPath is empty, not in protected paths, no file on disk to count → allow
    ok(isAllow(result), `empty file_path should be allowed (fail-safe)`);
  });

  it('hook exit code is always 0 (never crashes)', () => {
    const input = makePreToolInput('Edit', { file_path: 'src/main.py' });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    strictEqual(result.exitCode, 0, `hook should never exit with non-zero`);
  });

  it('deny decision includes "Fix the code, not the test" message', () => {
    const input = makePreToolInput('Edit', {
      file_path: 'tests/regression/critical.py',
    });
    const result = runHook('pre-edit.mjs', input, {
      CLAUDE_PROJECT_DIR: tmpDir,
      CLAUDE_CURRENT_SPEC_PATH: '',
    });
    ok(isDeny(result));
    ok(
      result.stdout.hookSpecificOutput.permissionDecisionReason.includes('Fix the code, not the test'),
      'deny reason should instruct to fix code not test'
    );
  });
});
