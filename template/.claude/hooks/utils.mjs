/**
 * Shared utilities for Claude Code hooks.
 *
 * This module provides helper functions for:
 * - PreToolUse hooks (pre-bash.mjs, pre-edit.mjs)
 * - PostToolUse hooks (post-edit.mjs)
 * - UserPromptSubmit hooks (prompt-guard.mjs)
 * - Stop hooks (session-end.mjs)
 *
 * Usage:
 *   import { allowTool, denyTool, readHookInput } from './utils.mjs';
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, chmodSync } from 'fs';
import { join, dirname, normalize, resolve } from 'path';
import { homedir } from 'os';
import { execFileSync } from 'child_process';

// Timeout for git operations (branch detection, etc.)
const GIT_TIMEOUT_MS = 5000;

// --- Error Logging ---

function getErrorLogPath() {
  const cacheDir = join(homedir(), '.cache', 'dld');
  mkdirSync(cacheDir, { recursive: true });
  return join(cacheDir, 'hook-errors.log');
}

export function logHookError(hookName, error) {
  try {
    const ts = new Date().toISOString();
    const logPath = getErrorLogPath();
    writeFileSync(logPath, `${ts} [${hookName}]: ${error}\n`, { flag: 'a' });
    try { chmodSync(logPath, 0o600); } catch { /* fail-safe */ }
  } catch (logErr) {
    // fail-safe: logging must never crash hook
    // but at least try console before giving up
    try {
      console.error(`[hook-error] ${hookName}: ${error}`);
    } catch {
      // truly hopeless, give up silently
    }
  }
}

// --- Hook Input/Output ---

export function readHookInput() {
  try {
    const raw = readFileSync(0, 'utf-8'); // fd 0 = stdin
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function outputJson(data) {
  try {
    process.stdout.write(JSON.stringify(data) + '\n');
  } catch {
    // pipe closed early — OK
  }
  process.exit(0);
}

// --- PreToolUse hook helpers ---

export function allowTool() {
  process.exit(0); // Silent exit = allow
}

export function denyTool(reason) {
  outputJson({
    hookSpecificOutput: {
      permissionDecision: 'deny',
      permissionDecisionReason: reason,
    },
  });
}

export function askTool(reason) {
  outputJson({
    hookSpecificOutput: {
      permissionDecision: 'ask',
      permissionDecisionReason: reason,
    },
  });
}

// --- UserPromptSubmit hook helpers ---

export function approvePrompt() {
  outputJson({ decision: 'approve' });
}

export function blockPrompt(reason) {
  outputJson({ decision: 'block', reason });
}

// --- PostToolUse hook helpers ---

export function postContinue(message = '') {
  if (message) {
    outputJson({
      decision: 'continue',
      hookSpecificOutput: { additionalContext: message },
    });
  } else {
    process.exit(0); // Silent exit = continue
  }
}

export function postBlock(reason) {
  outputJson({
    decision: 'block',
    hookSpecificOutput: { additionalContext: reason },
  });
}

// --- Data extraction ---

export function getToolInput(data, key) {
  return (data.tool_input || {})[key] || null;
}

export function getUserPrompt(data) {
  return data.user_prompt || '';
}

// --- Allowed Files enforcement ---

const ALWAYS_ALLOWED_PATTERNS = [
  'ai/features/*.md',
  'ai/backlog.md',
  'ai/diary/**',
  '.gitignore',
  'pyproject.toml',
  '.claude/**',
];

function matchesPattern(filePath, pattern) {
  return minimatch(filePath, pattern);
}

/**
 * Simple fnmatch-style glob matching (no external deps).
 * Supports: *, **, ? and character classes [abc].
 * Does NOT match / with * (same as Python fnmatch).
 */
function minimatch(str, pattern) {
  // Escape regex specials, then convert glob to regex
  // Use placeholder for ** before converting single *
  let re = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*\*/g, '\x00GLOBSTAR\x00')
    .replace(/\*/g, '[^/]*')
    .replace(/\?/g, '[^/]')
    .replace(/\x00GLOBSTAR\x00/g, '.*');
  re = `^${re}$`;
  return new RegExp(re).test(str);
}

export function extractAllowedFiles(specPath) {
  try {
    const content = readFileSync(specPath, 'utf-8');
    const match = content.match(/## Allowed Files\s*\n([\s\S]*?)(?=\n##|\s*$)/i);
    if (!match) return { files: [], error: false };

    const section = match[1];
    const allowed = [];

    for (const line of section.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;

      // Extract path from markdown formats: `path`, **path**, or path - description
      const pathMatch = trimmed.match(/[`*\-]*\s*([a-zA-Z0-9_./@-]+\.[a-zA-Z0-9]+(?::\d+(?:-\d+)?)?)[`*]*/);
      if (pathMatch) {
        let p = pathMatch[1];
        // NOTE: Line number ranges (e.g., :10-20) are informational only, not enforced.
        // Full file is allowed when path matches, regardless of line range.
        p = p.replace(/:\d+(-\d+)?$/, ''); // Remove line number suffix
        if (p && !p.startsWith('|')) {
          allowed.push(p);
        }
      }
    }
    return { files: allowed, error: false };
  } catch {
    return { files: [], error: true }; // read error = deny all
  }
}

export function inferSpecFromBranch() {
  try {
    // 1. Try branch name first
    let branch = execFileSync('git', ['branch', '--show-current'], {
      timeout: GIT_TIMEOUT_MS,
      encoding: 'utf-8',
    }).trim();

    // 2. Fallback: detached HEAD — try symbolic-ref
    if (!branch) {
      try {
        branch = execFileSync('git', ['symbolic-ref', '--short', 'HEAD'], {
          timeout: GIT_TIMEOUT_MS,
          encoding: 'utf-8',
        }).trim();
      } catch {
        // 3. Last resort: extract task ID from latest commit message
        try {
          const commitMsg = execFileSync('git', ['log', '-1', '--pretty=%s'], {
            timeout: GIT_TIMEOUT_MS,
            encoding: 'utf-8',
          }).trim();
          const msgMatch = commitMsg.match(/(FTR|BUG|TECH|ARCH|SEC)-\d+/i);
          if (msgMatch) branch = msgMatch[0];
        } catch {
          return null; // fail-safe (ADR-004)
        }
      }
    }

    if (!branch) return null;

    const match = branch.match(/(FTR|BUG|TECH|ARCH|SEC)-\d+/i);
    if (!match) return null;

    const taskId = match[0].toUpperCase();

    // Look for spec file in ai/features/ matching prefix
    try {
      const dir = 'ai/features';
      if (!existsSync(dir)) return null;
      const files = readdirSync(dir);
      const found = files.find(f => f.startsWith(`${taskId}-`) && f.endsWith('.md'));
      return found ? join(dir, found) : null;
    } catch {
      return null;
    }
  } catch {
    return null; // fail-safe: git error = no spec inference
  }
}

export function isFileAllowed(filePath, specPath) {
  // Normalize path
  filePath = normalize(filePath).replace(/^\.\//, '');
  if (process.platform === 'win32') {
    filePath = filePath.replace(/\\/g, '/');
  }

  // Always-allowed files
  for (const pattern of ALWAYS_ALLOWED_PATTERNS) {
    if (matchesPattern(filePath, pattern)) {
      return { allowed: true, allowedFiles: [] };
    }
  }

  // No spec = allow all
  if (!specPath) {
    return { allowed: true, allowedFiles: [] };
  }

  // Get allowed files from spec
  const result = extractAllowedFiles(specPath);
  if (result.error) {
    return { allowed: false, allowedFiles: [], error: 'spec read failed' };
  }
  if (result.files.length === 0) {
    return { allowed: true, allowedFiles: [] }; // No Allowed Files section = allow all
  }

  // Check if file matches any allowed pattern
  for (let allowed of result.files) {
    allowed = normalize(allowed).replace(/\\/g, '/');
    // Direct match
    if (filePath === allowed) {
      return { allowed: true, allowedFiles: result.files };
    }
    // Glob pattern match
    if (minimatch(filePath, allowed)) {
      return { allowed: true, allowedFiles: result.files };
    }
  }

  return { allowed: false, allowedFiles: result.files };
}

// --- Path safety ---

/**
 * Get project directory with path traversal protection.
 * Falls back to cwd() if CLAUDE_PROJECT_DIR escapes home or /tmp.
 */
export function getProjectDir() {
  const dir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  const resolved = resolve(dir);
  const home = homedir();
  if (!resolved.startsWith(home) && !resolved.startsWith('/tmp')) {
    return process.cwd();
  }
  return resolved;
}
