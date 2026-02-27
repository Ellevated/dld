/**
 * Tests for prompt-guard.mjs
 *
 * Verifies complexity detection, skill indicator bypass, and fail-safe behaviour.
 */

import { describe, it } from 'node:test';
import { strictEqual, ok } from 'node:assert';
import { execFileSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { runHook, makePromptInput, HOOKS_DIR } from './helpers.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Run the prompt-guard hook with raw (possibly invalid) stdin.
 */
function runRaw(stdinData) {
  const hookPath = join(HOOKS_DIR, 'prompt-guard.mjs');
  try {
    const raw = execFileSync('node', [hookPath], {
      input: stdinData,
      encoding: 'utf-8',
      timeout: 10000,
      env: { ...process.env, CLAUDE_PROJECT_DIR: '/tmp/test-project' },
    }).trim();
    return { exitCode: 0, raw, stdout: raw ? JSON.parse(raw) : null };
  } catch (e) {
    const raw = (e.stdout || '').trim();
    let parsed = null;
    try { if (raw) parsed = JSON.parse(raw); } catch { /* unparseable */ }
    return { exitCode: e.status ?? 1, raw, stdout: parsed };
  }
}

describe('prompt-guard', () => {
  // --- Complexity patterns: expect block ---

  it('blocks "implement a login feature"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('implement a login feature'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  it('blocks "create endpoint for payments"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('create endpoint for payments'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  it('blocks "write a function to validate emails"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('write a function to validate emails'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  it('blocks "build api for user registration"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('build api for user registration'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  it('blocks "add new feature for notifications"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('add new feature for notifications'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  it('blocks "add new functionality for search"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('add new functionality for search'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  it('blocks "write a class for database access"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('write a class for database access'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  it('blocks "create a service for authentication"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('create a service for authentication'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'block');
  });

  // --- Skill indicators: expect approve even if complex ---

  it('approves when /spark is present (overrides complexity)', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('/spark implement a login feature'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves when /autopilot is present', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('/autopilot create endpoint for payments'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves when word "spark" appears in prompt', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('spark implement a login feature'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves when word "autopilot" appears in prompt', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('autopilot build api for orders'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves when /audit is present', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('/audit check this feature code'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves when word "audit" appears in prompt', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('audit create endpoint review'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves when /plan is present', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('/plan write a function for X'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves when /council is present', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('/council should we create a new api service'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  // --- Simple/non-complex prompts: expect approve ---

  it('approves simple prompt "fix typo"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('fix typo'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves "what does this code do?"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('what does this code do?'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves "show me the README"', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('show me the README'));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  it('approves empty prompt (fail-safe)', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput(''));
    strictEqual(result.exitCode, 0);
    strictEqual(result.stdout?.decision, 'approve');
  });

  // --- Fail-safe: malformed input ---

  it('approves on malformed JSON input (fail-safe)', () => {
    const result = runRaw('not-valid-json{{{');
    // Fail-safe: malformed input must produce approve (exit 0 with approve or just exit 0)
    if (result.stdout) {
      strictEqual(result.stdout.decision, 'approve');
    } else {
      strictEqual(result.exitCode, 0);
    }
  });

  it('approves on empty stdin (fail-safe)', () => {
    const result = runRaw('');
    if (result.stdout) {
      strictEqual(result.stdout.decision, 'approve');
    } else {
      strictEqual(result.exitCode, 0);
    }
  });

  // --- Block message quality ---

  it('block response includes /spark hint', () => {
    const result = runHook('prompt-guard.mjs', makePromptInput('implement a payment service'));
    strictEqual(result.stdout?.decision, 'block');
    ok(result.stdout?.reason?.includes('/spark'), 'block reason should mention /spark');
  });
});
