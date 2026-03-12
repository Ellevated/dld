/**
 * Cross-platform hook runner with git worktree support.
 *
 * Usage: node .claude/hooks/run-hook.mjs <hook-name>
 * Example: node .claude/hooks/run-hook.mjs pre-bash
 *
 * Resolves the main repo root (for worktree support) and runs
 * the specified hook from .claude/hooks/<hook-name>.mjs
 */

import { execFileSync } from 'child_process';
import { join } from 'path';
import { existsSync } from 'fs';
import { pathToFileURL } from 'url';
import { logHookError } from './utils.mjs';

const hookName = process.argv[2];
if (!hookName) {
  process.exit(0); // No hook specified — silently allow
}

// Validate hookName — alphanumeric, hyphens, dots only (prevent path traversal)
if (!/^[a-zA-Z0-9._-]+$/.test(hookName)) {
  process.exit(0); // Silent fail-safe for invalid hook names
}

// Find main repo root (worktree support)
let root;
try {
  const output = execFileSync('git', ['worktree', 'list', '--porcelain'], {
    encoding: 'utf-8',
    timeout: 5000,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  root = output.split('\n')[0].replace('worktree ', '').trim();
} catch {
  root = process.cwd();
}

const hookPath = join(root, '.claude', 'hooks', `${hookName}.mjs`);

if (existsSync(hookPath)) {
  try {
    // Dynamic import with file:// URL (required for Windows paths with drive letters)
    await import(pathToFileURL(hookPath).href);
  } catch (err) {
    logHookError(hookName, err);
    process.exit(0); // fail-safe: allow operation to proceed (ADR-004)
  }
} else {
  // Hook not found — silently allow (ADR-004: fail-safe)
  process.exit(0);
}
