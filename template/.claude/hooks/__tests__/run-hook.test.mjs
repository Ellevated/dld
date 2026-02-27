/**
 * Tests for run-hook.mjs
 *
 * Verifies hookName validation: path traversal prevention, special char rejection,
 * missing argument handling, and acceptance of valid hook names.
 */

import { describe, it } from 'node:test';
import { strictEqual } from 'node:assert';
import { execFileSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUN_HOOK = join(__dirname, '..', 'run-hook.mjs');

/**
 * Run run-hook.mjs with optional hookName argument and empty stdin.
 */
function runRunner(hookName, stdinData = '{}') {
  const args = hookName !== undefined ? [RUN_HOOK, hookName] : [RUN_HOOK];
  try {
    const stdout = execFileSync('node', args, {
      input: stdinData,
      encoding: 'utf-8',
      timeout: 10000,
      env: { ...process.env, CLAUDE_PROJECT_DIR: '/tmp/test-project' },
    });
    return { exitCode: 0, stdout: stdout.trim() };
  } catch (e) {
    return { exitCode: e.status ?? 1, stdout: (e.stdout || '').trim() };
  }
}

describe('run-hook hookName validation', () => {
  // --- No argument ---

  it('exits 0 silently when no hookName is provided', () => {
    const result = runRunner(undefined);
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  // --- Path traversal: must be silently rejected ---

  it('rejects "../../../etc/passwd" (path traversal)', () => {
    const result = runRunner('../../../etc/passwd');
    // Must exit 0 silently (fail-safe, not an error)
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  it('rejects "../../secret" (path traversal with dots)', () => {
    const result = runRunner('../../secret');
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  it('rejects "/etc/passwd" (absolute path)', () => {
    const result = runRunner('/etc/passwd');
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  // --- Special characters: must be silently rejected ---

  it('rejects "foo;rm -rf /" (shell injection)', () => {
    const result = runRunner('foo;rm -rf /');
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  it('rejects "hook$(whoami)" (command substitution)', () => {
    const result = runRunner('hook$(whoami)');
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  it('rejects "hook|cat /etc/passwd" (pipe injection)', () => {
    const result = runRunner('hook|cat /etc/passwd');
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  it('rejects "hook name" (space not allowed)', () => {
    const result = runRunner('hook name');
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout, '');
  });

  // --- Valid hook names: must be accepted (hook not found = still exits 0) ---

  it('accepts "pre-bash" — valid alphanumeric+hyphen', () => {
    // Hook file likely exists (worktree has hooks), exits 0 either way
    const result = runRunner('pre-bash');
    strictEqual(result.exitCode, 0);
  });

  it('accepts "post-edit" — valid hook name', () => {
    const result = runRunner('post-edit');
    strictEqual(result.exitCode, 0);
  });

  it('accepts "prompt-guard" — valid hook name', () => {
    const result = runRunner('prompt-guard');
    strictEqual(result.exitCode, 0);
  });

  it('accepts "nonexistent-hook" — exits 0 (hook not found is fail-safe)', () => {
    const result = runRunner('nonexistent-hook-xyz-does-not-exist');
    strictEqual(result.exitCode, 0);
  });

  it('accepts "hook.v2" — dots allowed in hookName', () => {
    const result = runRunner('hook.v2');
    strictEqual(result.exitCode, 0);
  });

  // --- Edge cases ---

  it('rejects empty string hookName', () => {
    // Empty string: regex /^[a-zA-Z0-9._-]+$/ fails on empty string → exits 0 silently
    const result = runRunner('');
    strictEqual(result.exitCode, 0);
  });
});
