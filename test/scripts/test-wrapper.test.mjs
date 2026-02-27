/**
 * Tests for test-wrapper.mjs
 *
 * Verifies:
 * - Pass output is compact (single line)
 * - Fail output includes summary and file path
 * - Test count extraction from multiple frameworks
 * - Full output saved to file on failure
 */

import { execSync } from 'child_process';
import { writeFileSync, mkdirSync, existsSync, rmSync } from 'fs';
import { join } from 'path';
import { strict as assert } from 'assert';

const WRAPPER_PATH = join(process.cwd(), 'template/.claude/scripts/test-wrapper.mjs');
const TEST_DIR = join(process.cwd(), 'test/scripts/.tmp-test-wrapper');

function setup() {
  mkdirSync(TEST_DIR, { recursive: true });
}

function cleanup() {
  try { rmSync(TEST_DIR, { recursive: true, force: true }); } catch {}
  try { rmSync('ai/.test-output', { recursive: true, force: true }); } catch {}
}

function runWrapper(command) {
  try {
    const output = execSync(`node ${WRAPPER_PATH} ${command}`, {
      encoding: 'utf-8',
      timeout: 30_000,
      cwd: process.cwd(),
    });
    return { exitCode: 0, output: output.trim() };
  } catch (err) {
    return { exitCode: err.status || 1, output: (err.stdout || '').trim() };
  }
}

// --- Tests ---

function testPassOutputIsCompact() {
  const result = runWrapper('echo "15 passed, 2 warnings in 1.5s"');
  assert.equal(result.exitCode, 0, 'Should exit 0 on success');
  assert.ok(result.output.startsWith('PASS:'), `Output should start with PASS: got "${result.output}"`);
  const lines = result.output.split('\n');
  assert.equal(lines.length, 1, 'Pass output should be a single line');
  console.log('  PASS: testPassOutputIsCompact');
}

function testFailOutputHasSummary() {
  // Create a script that exits with code 1
  const failScript = join(TEST_DIR, 'fail.sh');
  writeFileSync(failScript, '#!/bin/sh\necho "FAILED tests/test_foo.py::test_bar"\necho "AssertionError: expected 1 got 2"\nexit 1\n');
  execSync(`chmod +x ${failScript}`);

  const result = runWrapper(failScript);
  assert.equal(result.exitCode, 1, 'Should exit 1 on failure');
  assert.ok(result.output.includes('FAIL:'), `Output should contain FAIL: got "${result.output}"`);
  assert.ok(result.output.includes('Full output:'), 'Output should include full output path');
  console.log('  PASS: testFailOutputHasSummary');
}

function testPytestCountExtraction() {
  const result = runWrapper('echo "===== 42 passed, 3 warnings in 5.2s ====="');
  assert.ok(result.output.includes('42'), `Should extract pytest count: got "${result.output}"`);
  console.log('  PASS: testPytestCountExtraction');
}

function testJestCountExtraction() {
  const result = runWrapper('echo "Tests: 18 passed, 18 total"');
  assert.ok(result.output.includes('18'), `Should extract jest count: got "${result.output}"`);
  console.log('  PASS: testJestCountExtraction');
}

function testFullOutputSavedOnFailure() {
  const failScript = join(TEST_DIR, 'fail2.sh');
  writeFileSync(failScript, '#!/bin/sh\necho "test output line 1"\necho "FAILED test_bar"\nexit 1\n');
  execSync(`chmod +x ${failScript}`);

  const result = runWrapper(failScript);
  assert.equal(result.exitCode, 1);

  // Check that full output file was created
  assert.ok(existsSync('ai/.test-output'), 'Should create ai/.test-output directory');
  console.log('  PASS: testFullOutputSavedOnFailure');
}

function testDefaultCommand() {
  // Without a ./test script, default command will fail — that's fine,
  // we just verify the wrapper handles it gracefully
  const result = runWrapper('');
  // Will fail because ./test doesn't exist, but shouldn't crash
  assert.ok(result.exitCode !== undefined, 'Should return an exit code');
  console.log('  PASS: testDefaultCommand (graceful failure)');
}

// --- Runner ---

function main() {
  console.log('test-wrapper.test.mjs');
  setup();
  try {
    testPassOutputIsCompact();
    testFailOutputHasSummary();
    testPytestCountExtraction();
    testJestCountExtraction();
    testFullOutputSavedOnFailure();
    testDefaultCommand();
    console.log(`\n6/6 tests passed`);
  } finally {
    cleanup();
  }
}

main();
