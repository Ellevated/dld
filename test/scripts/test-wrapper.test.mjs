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

/**
 * A failing "test command", written as a node script rather than a shell script.
 *
 * The fixtures used to be `.sh` + `chmod +x`, which cannot run on Windows — the
 * suite aborted at the second test on any Windows checkout, and nothing in CI
 * ran it either, so it was failing silently in both places.
 */
function failFixture(name, lines) {
  const path = join(TEST_DIR, `${name}.mjs`);
  const body = lines.map(l => `console.log(${JSON.stringify(l)});`).join('\n');
  writeFileSync(path, `${body}\nprocess.exit(1);\n`);
  return `node ${path}`;
}

function testFailOutputHasSummary() {
  const failScript = failFixture('fail', [
    'FAILED tests/test_foo.py::test_bar',
    'AssertionError: expected 1 got 2',
  ]);

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
  const failScript = failFixture('fail2', ['test output line 1', 'FAILED test_bar']);

  const result = runWrapper(failScript);
  assert.equal(result.exitCode, 1);

  // Check that full output file was created
  assert.ok(existsSync('ai/.test-output'), 'Should create ai/.test-output directory');
  console.log('  PASS: testFullOutputSavedOnFailure');
}

function testMissingCommandIsNotAFailure() {
  // This assertion used to read `exitCode !== undefined`, which `err.status || 1`
  // can never violate — so it passed while the wrapper reported a missing ./test
  // as `FAIL: 0 failure(s)`, i.e. a broken suite with no failures in it.
  //
  // It then failed on a Russian Windows, where cmd.exe returns exit 1 and an
  // OEM-codepage message Node decodes as mojibake: the guard was reading the
  // shell's wording, so it only worked in English. The wrapper now stats the
  // path instead.
  const result = runWrapper('./definitely-not-a-real-test-command');
  assert.equal(result.exitCode, 2, `Missing command should exit 2, got ${result.exitCode}`);
  assert.ok(
    result.output.includes('TEST_COMMAND_UNAVAILABLE'),
    `Should name the missing command: got "${result.output}"`
  );
  assert.ok(!result.output.includes('FAIL:'), 'A missing command is not a test failure');
  console.log('  PASS: testMissingCommandIsNotAFailure');
}

function testRealFailureStillReportsFail() {
  // The guard above must not swallow genuine failures.
  const failScript = failFixture('fail3', ['FAILED tests/test_x.py::test_y']);

  const result = runWrapper(failScript);
  assert.equal(result.exitCode, 1, 'A real failure keeps exit 1');
  assert.ok(result.output.includes('FAIL:'), `Should report FAIL: got "${result.output}"`);
  assert.ok(!result.output.includes('TEST_COMMAND_UNAVAILABLE'), 'A real failure is not a missing command');
  console.log('  PASS: testRealFailureStillReportsFail');
}

function testExistingPathWithASpaceIsNotMissing() {
  // The path check keys on existence, not on shape — and the path may contain a
  // space, because `main` rebuilds the command with `args.join(' ')` and the
  // caller's quoting does not survive that. Splitting on whitespace would stat
  // the first fragment and call a command that exists missing.
  //
  // A directory is the portable way to say "this path exists and running it
  // fails": every shell refuses it, with a message none of the not-found
  // patterns match, on every platform. No quotes, no metacharacters — the two
  // things this wrapper is known to mangle.
  const spaced = join(TEST_DIR, 'dir with space');
  mkdirSync(spaced, { recursive: true });

  const result = runWrapper(spaced);
  assert.notEqual(result.exitCode, 0, 'Running a directory does not succeed');
  assert.ok(
    !result.output.includes('TEST_COMMAND_UNAVAILABLE'),
    `A path that exists is never "unavailable": got "${result.output}"`
  );
  console.log('  PASS: testExistingPathWithASpaceIsNotMissing');
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
    testMissingCommandIsNotAFailure();
    testRealFailureStillReportsFail();
    testExistingPathWithASpaceIsNotMissing();
    console.log(`\n8/8 tests passed`);
  } finally {
    cleanup();
  }
}

main();
