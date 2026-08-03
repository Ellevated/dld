/**
 * Test Output Wrapper — reduces noise in LLM context.
 *
 * Runs test command and produces LLM-optimized output:
 * - Pass: single summary line
 * - Fail: compact summary with first 5 lines of each stacktrace
 * - Full output saved to file for debugging
 *
 * Usage: node .claude/scripts/test-wrapper.mjs [command] [args...]
 * Default: ./test fast
 *
 * Used by: tester.md agent, autopilot task-loop.md
 */

import { execSync } from 'child_process';
import { writeFileSync, mkdirSync, existsSync } from 'fs';
import { join } from 'path';

const MAX_TRACE_LINES = 5;
const FULL_OUTPUT_DIR = 'ai/.test-output';

// Exit code for "the test command does not exist here", kept distinct from 1
// ("tests ran and failed"). `./test` is a per-project artifact — some repos ship
// one, some do not — so its absence is an expected state, not a test result.
const EXIT_COMMAND_UNAVAILABLE = 2;

/**
 * Distinguish a missing test command from failing tests.
 *
 * Without this the wrapper reported `FAIL: 0 failure(s)` — "tests failed, zero
 * failures" — because no failure pattern matches a shell's not-found message.
 * That reads as a broken test suite and sends the caller hunting for failures
 * that were never run.
 *
 * The default command is `./test fast` — a path — so ask the filesystem rather
 * than the shell. Reading the shell's wording is locale-dependent: a Russian
 * Windows returns exit 1 with an OEM-codepage message that Node decodes as
 * mojibake, so the English patterns below match nothing and the guard silently
 * stops guarding. The text check stays as a fallback for bare commands
 * (`pytest`, `npm test`), where there is no path to stat.
 */
const PATH_SHAPED = /^(?:\.{1,2}[\\/]|[\\/]|[A-Za-z]:[\\/])/;

/**
 * Tri-state, because "the filesystem has no opinion" is not the same answer as
 * "the path is there": true = names a path that is absent, false = the path is
 * present, null = not path-shaped, so only the shell's output can tell us.
 */
function commandPathState(command) {
  const trimmed = command.trim();

  const quoted = trimmed.match(/^"([^"]+)"/);
  if (quoted) return PATH_SHAPED.test(quoted[1]) ? !existsSync(quoted[1]) : null;

  const tokens = trimmed.split(/\s+/);
  if (!tokens.length || !PATH_SHAPED.test(tokens[0])) return null;

  // The path may contain spaces and arrive unquoted — `main` rebuilds the
  // command with `args.join(' ')`, which drops the quoting the caller wrote.
  // So "absent" means no prefix of the tokens resolves to a file; otherwise
  // `C:\Program Files\nodejs\node.exe -e …` would be reported as unavailable.
  for (let i = 1; i <= tokens.length; i++) {
    if (existsSync(tokens.slice(0, i).join(' '))) return false;
  }
  return true;
}

function looksLikeMissingCommand(exitCode, output) {
  // POSIX shells use 127 for not-found; cmd.exe returns 1 with its own wording.
  if (exitCode === 127) return true;
  return /(?:command not found|No such file or directory|is not recognized as an internal or external command|cannot find the path)/i
    .test(output);
}

function main() {
  const args = process.argv.slice(2);
  const command = args.length > 0 ? args.join(' ') : './test fast';

  const startTime = Date.now();
  let stdout = '';
  let exitCode = 0;

  try {
    stdout = execSync(command, {
      encoding: 'utf-8',
      stdio: ['inherit', 'pipe', 'pipe'],
      timeout: 300_000, // 5 min
      maxBuffer: 10 * 1024 * 1024, // 10 MB
    });
  } catch (err) {
    exitCode = err.status || 1;
    stdout = (err.stdout || '') + '\n' + (err.stderr || '');
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  // When the command names a path, the filesystem is the answer — the shell's
  // exit code and wording are not consulted at all. A path that exists but
  // could not be launched is a failed run, not an absent test command, and on
  // POSIX that case still exits 127.
  const pathState = commandPathState(command);
  const commandUnavailable =
    pathState === null ? looksLikeMissingCommand(exitCode, stdout) : pathState;

  if (exitCode !== 0 && commandUnavailable) {
    console.log(`TEST_COMMAND_UNAVAILABLE: ${command}`);
    console.log('No test command at this path — nothing ran. This is not a test failure.');
    process.exit(EXIT_COMMAND_UNAVAILABLE);
  }

  if (exitCode === 0) {
    // Extract test count from common frameworks
    const counts = extractTestCounts(stdout);
    console.log(`PASS: ${counts} (${elapsed}s)`);
  } else {
    // Save full output to file
    const outputPath = saveFullOutput(stdout, command);

    // Extract and display compact failure summary
    const failures = extractFailures(stdout);
    console.log(`FAIL: ${failures.length} failure(s) (${elapsed}s)`);
    console.log(`Full output: ${outputPath}`);
    console.log('---');

    for (const failure of failures.slice(0, 10)) {
      console.log(`  ${failure.name}`);
      for (const line of failure.trace) {
        console.log(`    ${line}`);
      }
      console.log('');
    }
  }

  process.exit(exitCode);
}

/**
 * Extract test counts from output (pytest, jest, mocha, cargo).
 */
function extractTestCounts(output) {
  // pytest: "15 passed, 2 warnings"
  const pytest = output.match(/(\d+)\s+passed/);
  if (pytest) {
    const warnings = output.match(/(\d+)\s+warnings?/);
    return `${pytest[1]} tests passed${warnings ? `, ${warnings[1]} warnings` : ''}`;
  }

  // jest: "Tests: 15 passed, 15 total"
  const jest = output.match(/Tests:\s*(\d+)\s+passed.*?(\d+)\s+total/);
  if (jest) return `${jest[1]}/${jest[2]} tests passed`;

  // mocha: "15 passing"
  const mocha = output.match(/(\d+)\s+passing/);
  if (mocha) return `${mocha[1]} tests passed`;

  // cargo: "test result: ok. 15 passed"
  const cargo = output.match(/test result: ok\.\s+(\d+)\s+passed/);
  if (cargo) return `${cargo[1]} tests passed`;

  // Generic: count "PASSED" or "ok" lines
  const passLines = output.split('\n').filter(l => /\bPASS(ED)?\b/i.test(l));
  if (passLines.length > 0) return `${passLines.length} tests passed`;

  return 'All tests passed';
}

/**
 * Extract test failures with truncated stacktraces.
 */
function extractFailures(output) {
  const failures = [];
  const lines = output.split('\n');

  // Strategy: find FAILED/FAIL lines, then grab next N lines as trace
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // pytest: "FAILED tests/test_foo.py::test_bar"
    const pytestMatch = line.match(/FAILED\s+(.+)/);
    if (pytestMatch) {
      failures.push({ name: pytestMatch[1].trim(), trace: getTrace(lines, i) });
      continue;
    }

    // jest: "FAIL src/foo.test.js" or "● test name"
    const jestFail = line.match(/^\s*FAIL\s+(.+)/);
    if (jestFail) {
      failures.push({ name: jestFail[1].trim(), trace: getTrace(lines, i) });
      continue;
    }

    // Generic: "AssertionError", "Error:", "FAILED"
    if (/(?:AssertionError|AssertError|Error:.*expected|FAILED\b)/i.test(line) && !failures.find(f => f.name === line.trim())) {
      failures.push({ name: line.trim().slice(0, 120), trace: getTrace(lines, i) });
    }
  }

  // Deduplicate by name
  const seen = new Set();
  return failures.filter(f => {
    if (seen.has(f.name)) return false;
    seen.add(f.name);
    return true;
  });
}

/**
 * Get MAX_TRACE_LINES non-empty lines after index.
 */
function getTrace(lines, startIdx) {
  const trace = [];
  for (let j = startIdx + 1; j < lines.length && trace.length < MAX_TRACE_LINES; j++) {
    const line = lines[j].trim();
    if (!line) continue;
    if (/^={3,}|^-{3,}|^FAILED|^PASS/.test(line)) break;
    trace.push(line);
  }
  return trace;
}

/**
 * Save full output to timestamped file.
 */
function saveFullOutput(output, command) {
  try {
    mkdirSync(FULL_OUTPUT_DIR, { recursive: true });
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const filename = `test-${ts}.log`;
    const path = join(FULL_OUTPUT_DIR, filename);
    writeFileSync(path, `Command: ${command}\nTimestamp: ${new Date().toISOString()}\n${'='.repeat(60)}\n${output}`);
    return path;
  } catch {
    return '(could not save output)';
  }
}

main();
