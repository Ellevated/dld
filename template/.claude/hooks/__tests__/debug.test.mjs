/**
 * Tests for debugLog and debugTiming in utils.mjs.
 *
 * Uses node:test + node:assert (no external deps).
 * Spawns child processes via spawnSync to capture stderr.
 *
 * Run: node --test __tests__/debug.test.mjs
 */

import { describe, it, before, after } from 'node:test';
import { strictEqual, ok } from 'node:assert';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'child_process';
import { dirname } from 'path';
import { fileURLToPath, pathToFileURL } from 'url';

import { debugLog, debugTiming } from '../utils.mjs';
import { runHook, makePreToolInput, makePromptInput } from './helpers.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UTILS_PATH = join(__dirname, '..', 'utils.mjs');
const UTILS_URL = pathToFileURL(UTILS_PATH).href;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let tmpDir;

/**
 * Spawn a Node inline script, capturing both stdout and stderr.
 * The script body is prepended with the utils.mjs import automatically.
 */
function captureDebug(scriptBody, env = {}) {
  const script = `import { debugLog, debugTiming } from '${UTILS_URL}';\n${scriptBody}`;
  const result = spawnSync('node', ['--input-type=module'], {
    input: script,
    encoding: 'utf-8',
    timeout: 5000,
    env: { PATH: process.env.PATH, HOME: process.env.HOME, ...env },
  });
  return {
    exitCode: result.status,
    stdout: (result.stdout || '').trim(),
    stderr: (result.stderr || '').trim(),
  };
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

before(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'debug-test-'));
});

after(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// 1. debugLog — no-op when disabled (imported directly)
// ---------------------------------------------------------------------------

describe('debugLog — no-op when DLD_HOOK_DEBUG not set', () => {
  it('does not throw when called without debug env', () => {
    // DEBUG constant is evaluated at import time, so in the current process
    // (where DLD_HOOK_DEBUG is not 1) this is a no-op.
    let threw = false;
    try {
      debugLog('test-hook', 'some-event', { key: 'value' });
    } catch {
      threw = true;
    }
    strictEqual(threw, false, 'debugLog should not throw');
  });

  it('does not throw when called with empty data', () => {
    let threw = false;
    try {
      debugLog('test-hook', 'some-event');
    } catch {
      threw = true;
    }
    strictEqual(threw, false, 'debugLog with no data should not throw');
  });

  it('does not throw when called with complex nested data', () => {
    let threw = false;
    try {
      debugLog('test-hook', 'some-event', { nested: { deep: [1, 2, 3] } });
    } catch {
      threw = true;
    }
    strictEqual(threw, false, 'debugLog with nested data should not throw');
  });
});

// ---------------------------------------------------------------------------
// 2. debugLog — writes to stderr when DLD_HOOK_DEBUG=1
// ---------------------------------------------------------------------------

describe('debugLog — writes JSON to stderr when DLD_HOOK_DEBUG=1', () => {
  it('emits JSON line to stderr with correct hook and event fields', () => {
    const result = captureDebug(
      `debugLog('my-hook', 'my-event', { foo: 'bar' });`,
      { DLD_HOOK_DEBUG: '1' }
    );
    strictEqual(result.exitCode, 0, 'script should exit 0');
    ok(result.stderr.length > 0, 'stderr should not be empty');
    const parsed = JSON.parse(result.stderr);
    strictEqual(parsed.hook, 'my-hook', 'hook field should match');
    strictEqual(parsed.event, 'my-event', 'event field should match');
    strictEqual(parsed.foo, 'bar', 'extra data field should be present');
    ok(typeof parsed.ts === 'string', 'ts field should be a string');
  });

  it('emits no output to stderr when DLD_HOOK_DEBUG is not set', () => {
    const result = captureDebug(
      `debugLog('my-hook', 'my-event', { foo: 'bar' });`,
      {}
    );
    strictEqual(result.exitCode, 0, 'script should exit 0');
    strictEqual(result.stderr, '', 'stderr should be empty when debug is off');
  });

  it('emits no output to stderr when DLD_HOOK_DEBUG=0', () => {
    const result = captureDebug(
      `debugLog('my-hook', 'my-event', { foo: 'bar' });`,
      { DLD_HOOK_DEBUG: '0' }
    );
    strictEqual(result.exitCode, 0, 'script should exit 0');
    strictEqual(result.stderr, '', 'stderr should be empty when DLD_HOOK_DEBUG=0');
  });
});

// ---------------------------------------------------------------------------
// 3. debugLog — file logging
// ---------------------------------------------------------------------------

describe('debugLog — file logging with DLD_HOOK_LOG_FILE', () => {
  it('writes JSON entry to log file when DLD_HOOK_DEBUG=1 and log file set', () => {
    const logFile = join(tmpDir, 'hook-debug.log');
    const result = captureDebug(
      `debugLog('file-hook', 'file-event', { x: 42 });`,
      { DLD_HOOK_DEBUG: '1', DLD_HOOK_LOG_FILE: logFile }
    );
    strictEqual(result.exitCode, 0, 'script should exit 0');
    ok(existsSync(logFile), 'log file should be created');
    const content = readFileSync(logFile, 'utf-8').trim();
    const parsed = JSON.parse(content);
    strictEqual(parsed.hook, 'file-hook', 'hook field in file should match');
    strictEqual(parsed.event, 'file-event', 'event field in file should match');
    strictEqual(parsed.x, 42, 'extra data field in file should match');
  });

  it('does not create log file when DLD_HOOK_DEBUG is not set', () => {
    const logFile = join(tmpDir, 'should-not-exist.log');
    const result = captureDebug(
      `debugLog('file-hook', 'file-event', { x: 42 });`,
      { DLD_HOOK_LOG_FILE: logFile }
    );
    strictEqual(result.exitCode, 0, 'script should exit 0');
    strictEqual(existsSync(logFile), false, 'log file should not be created when debug is off');
  });
});

// ---------------------------------------------------------------------------
// 4. debugTiming — measures elapsed time
// ---------------------------------------------------------------------------

describe('debugTiming — measures elapsed time and emits complete event', () => {
  it('emits complete event with decision and ms when DLD_HOOK_DEBUG=1', () => {
    const result = captureDebug(
      `
const t = debugTiming('timed-hook');
// brief synchronous work to ensure non-zero elapsed
let sum = 0; for (let i = 0; i < 1000; i++) sum += i;
t.end('allow');
`,
      { DLD_HOOK_DEBUG: '1' }
    );
    strictEqual(result.exitCode, 0, 'script should exit 0');
    ok(result.stderr.length > 0, 'stderr should not be empty');
    const parsed = JSON.parse(result.stderr);
    strictEqual(parsed.hook, 'timed-hook', 'hook field should match');
    strictEqual(parsed.event, 'complete', 'event should be complete');
    strictEqual(parsed.decision, 'allow', 'decision should match');
    ok(typeof parsed.ms === 'string', 'ms should be a string (toFixed result)');
  });

  it('emits no output when DLD_HOOK_DEBUG is not set', () => {
    const result = captureDebug(
      `
const t = debugTiming('timed-hook');
t.end('deny');
`,
      {}
    );
    strictEqual(result.exitCode, 0, 'script should exit 0');
    strictEqual(result.stderr, '', 'stderr should be empty when debug is off');
  });
});

// ---------------------------------------------------------------------------
// 5. Integration: hook with DLD_HOOK_DEBUG=1 still produces correct output
// ---------------------------------------------------------------------------

describe('integration — debug mode does not break hook protocol output', () => {
  it('pre-bash allows a safe command even with DLD_HOOK_DEBUG=1', () => {
    const input = makePreToolInput('Bash', { command: 'ls -la' });
    const result = runHook('pre-bash.mjs', input, { DLD_HOOK_DEBUG: '1' });
    strictEqual(result.exitCode, 0, 'hook should exit 0');
    strictEqual(result.stdout, null, 'safe command should be silently allowed (null stdout)');
  });

  it('pre-bash denies a dangerous command even with DLD_HOOK_DEBUG=1', () => {
    const input = makePreToolInput('Bash', { command: 'git push --force origin main' });
    const result = runHook('pre-bash.mjs', input, { DLD_HOOK_DEBUG: '1' });
    strictEqual(result.exitCode, 0, 'hook should exit 0');
    ok(result.stdout, 'dangerous command should produce stdout output');
    strictEqual(
      result.stdout.hookSpecificOutput?.permissionDecision,
      'deny',
      'expected permissionDecision=deny'
    );
  });

  it('prompt-guard approves a simple prompt even with DLD_HOOK_DEBUG=1', () => {
    const input = makePromptInput('What is 2 + 2?');
    const result = runHook('prompt-guard.mjs', input, { DLD_HOOK_DEBUG: '1' });
    strictEqual(result.exitCode, 0, 'hook should exit 0');
    ok(result.stdout, 'prompt-guard should produce stdout output');
    strictEqual(result.stdout.decision, 'approve', 'simple prompt should be approved');
  });
});
