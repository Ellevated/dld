/**
 * Post-Edit hook: auto-formats Python files after Write/Edit.
 *
 * Actions:
 * - Runs `ruff format` on Python files
 * - Shows lint warnings (non-blocking)
 *
 * Requirements:
 * - ruff must be installed (pip install ruff)
 */

import { existsSync } from 'fs';
import { basename, resolve } from 'path';
import { execFileSync } from 'child_process';
import { debugLog, debugTiming, getProjectDir, getToolInput, logHookError, postContinue, readHookInput } from './utils.mjs';

// Ruff configuration
const RUFF_TIMEOUT_MS = 10000;
const RUFF_LINT_RULES = 'E,W,F';
const MAX_LINT_WARNINGS = 5;

// Claude Code tools that write files
const FILE_WRITE_TOOLS = ['Write', 'Edit', 'MultiEdit'];

function formatPythonFile(filePath) {
  try {
    execFileSync('ruff', ['format', filePath], { timeout: RUFF_TIMEOUT_MS, stdio: 'pipe' });
    return { success: true, msg: 'formatted' };
  } catch (e) {
    if (e.code === 'ENOENT') return { success: false, msg: 'ruff not found' };
    if (e.killed) return { success: false, msg: 'format timeout' };
    return { success: false, msg: String(e.message || e) };
  }
}

function checkLintWarnings(filePath) {
  try {
    const result = execFileSync('ruff', ['check', filePath, `--select=${RUFF_LINT_RULES}`], {
      timeout: RUFF_TIMEOUT_MS,
      stdio: 'pipe',
      encoding: 'utf-8',
    });
    return result ? result.trim().split('\n').slice(0, MAX_LINT_WARNINGS) : [];
  } catch (e) {
    // ruff check returns non-zero when warnings found — output is in stderr/stdout
    const output = e.stdout || '';
    return output ? output.trim().split('\n').slice(0, MAX_LINT_WARNINGS) : [];
  }
}

function main() {
  const timer = debugTiming('post-edit');
  try {
    const data = readHookInput();
    const toolName = data.tool_name || '';

    if (!FILE_WRITE_TOOLS.includes(toolName)) {
      debugLog('post-edit', 'skip', { reason: 'not_write_tool', tool: toolName });
      timer.end('skip');
      postContinue();
      return;
    }

    const filePath = getToolInput(data, 'file_path') || '';
    debugLog('post-edit', 'input', { tool: toolName, file: filePath });

    if (!filePath.endsWith('.py')) {
      debugLog('post-edit', 'skip', { reason: 'not_python' });
      timer.end('skip');
      postContinue();
      return;
    }

    if (!existsSync(filePath)) {
      debugLog('post-edit', 'skip', { reason: 'file_not_found' });
      timer.end('skip');
      postContinue();
      return;
    }

    // Project boundary check (F-018)
    const projectDir = getProjectDir();
    const absPath = resolve(filePath);
    if (!absPath.startsWith(projectDir)) {
      debugLog('post-edit', 'skip', { reason: 'outside_project' });
      timer.end('skip');
      postContinue();
      return;
    }

    const messages = [];

    const { success } = formatPythonFile(filePath);
    if (success) {
      messages.push(`ruff format: ${basename(filePath)}`);
    }

    const warnings = checkLintWarnings(filePath);
    if (warnings.length > 0) {
      messages.push(`lint warnings (${warnings.length}):`);
      messages.push(...warnings.map(w => `  ${w}`));
    }

    debugLog('post-edit', 'continue', { formatted: success });
    timer.end('continue');

    if (messages.length > 0) {
      postContinue(messages.join('\n'));
    } else {
      postContinue();
    }
  } catch (e) {
    debugLog('post-edit', 'error', { error: String(e) });
    timer.end('error');
    logHookError('post_edit', e);
    postContinue(); // Fail-safe: don't block on errors
  }
}

main();
