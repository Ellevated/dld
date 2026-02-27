/**
 * Shared test helpers for hook tests.
 *
 * Provides utilities for spawning hooks as child processes
 * and verifying their stdin→stdout protocol.
 */

import { execFileSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HOOKS_DIR = join(__dirname, '..');

/**
 * Run a hook as a child process, piping JSON to stdin.
 *
 * @param {string} hookFile - Hook filename (e.g., 'pre-bash.mjs')
 * @param {object} stdinData - Data to pipe as JSON to stdin
 * @param {object} [envOverrides] - Extra environment variables
 * @returns {{ exitCode: number, stdout: object|null, raw: string }}
 */
export function runHook(hookFile, stdinData, envOverrides = {}) {
  const hookPath = join(HOOKS_DIR, hookFile);
  const input = JSON.stringify(stdinData);

  try {
    const raw = execFileSync('node', [hookPath], {
      input,
      encoding: 'utf-8',
      timeout: 10000,
      env: {
        ...process.env,
        CLAUDE_PROJECT_DIR: '/tmp/test-project',
        ...envOverrides,
      },
    });

    const trimmed = raw.trim();
    return {
      exitCode: 0,
      stdout: trimmed ? JSON.parse(trimmed) : null,
      raw: trimmed,
    };
  } catch (e) {
    const raw = (e.stdout || '').trim();
    let parsed = null;
    try {
      if (raw) parsed = JSON.parse(raw);
    } catch {
      // unparseable output
    }
    return {
      exitCode: e.status ?? 1,
      stdout: parsed,
      raw,
    };
  }
}

/**
 * Create a PreToolUse hook input payload.
 */
export function makePreToolInput(toolName, toolInput = {}) {
  return {
    hook_type: 'PreToolUse',
    tool_name: toolName,
    tool_input: toolInput,
  };
}

/**
 * Create a PostToolUse hook input payload.
 */
export function makePostToolInput(toolName, toolInput = {}, toolOutput = '') {
  return {
    hook_type: 'PostToolUse',
    tool_name: toolName,
    tool_input: toolInput,
    tool_output: toolOutput,
  };
}

/**
 * Create a UserPromptSubmit hook input payload.
 */
export function makePromptInput(userPrompt) {
  return {
    hook_type: 'UserPromptSubmit',
    user_prompt: userPrompt,
  };
}

/**
 * Create a Stop hook input payload.
 */
export function makeStopInput(reason = 'end_turn') {
  return {
    hook_type: 'Stop',
    stop_reason: reason,
  };
}

export { HOOKS_DIR };
