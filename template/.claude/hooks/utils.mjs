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

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'fs';
import { join, dirname, normalize } from 'path';
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
    writeFileSync(getErrorLogPath(), `${ts} [${hookName}]: ${error}\n`, { flag: 'a' });
  } catch {
    // fail-safe: logging must never crash hook
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
  'ai/diary/*',
  '.gitignore',
  'pyproject.toml',
  '.claude/*',
];

function matchesPattern(filePath, pattern) {
  if (pattern.endsWith('/*')) {
    const dirPrefix = pattern.slice(0, -1); // "ai/diary/*" -> "ai/diary/"
    return filePath.startsWith(dirPrefix);
  }
  return minimatch(filePath, pattern);
}

/**
 * Simple fnmatch-style glob matching (no external deps).
 * Supports: *, ? and character classes [abc].
 * Does NOT match / with * (same as Python fnmatch).
 */
function minimatch(str, pattern) {
  // Escape regex specials, then convert glob to regex
  let re = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '[^/]*')
    .replace(/\?/g, '[^/]');
  re = `^${re}$`;
  return new RegExp(re).test(str);
}

export function extractAllowedFiles(specPath) {
  try {
    const content = readFileSync(specPath, 'utf-8');
    const match = content.match(/## Allowed Files\s*\n([\s\S]*?)(?=\n##|\s*$)/i);
    if (!match) return [];

    const section = match[1];
    const allowed = [];

    for (const line of section.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;

      // Extract path from markdown formats: `path`, **path**, or path - description
      const pathMatch = trimmed.match(/[`*]*([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+(?::\d+(?:-\d+)?)?)[`*]*/);
      if (pathMatch) {
        let p = pathMatch[1];
        p = p.replace(/:\d+(-\d+)?$/, ''); // Remove line number suffix
        if (p && !p.startsWith('|')) {
          allowed.push(p);
        }
      }
    }
    return allowed;
  } catch {
    return []; // fail-safe: missing spec = allow all
  }
}

export function inferSpecFromBranch() {
  try {
    const branch = execFileSync('git', ['branch', '--show-current'], {
      timeout: GIT_TIMEOUT_MS,
      encoding: 'utf-8',
    }).trim();

    if (!branch) return null;

    const match = branch.match(/(FTR|BUG|TECH|ARCH|SEC)-\d+/i);
    if (!match) return null;

    const taskId = match[0].toUpperCase();
    const pattern = `ai/features/${taskId}-`;

    // Simple glob: list files in ai/features/ matching prefix
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
  const allowedFiles = extractAllowedFiles(specPath);
  if (allowedFiles.length === 0) {
    return { allowed: true, allowedFiles: [] }; // No Allowed Files section = allow all
  }

  // Check if file matches any allowed pattern
  for (let allowed of allowedFiles) {
    allowed = normalize(allowed).replace(/\\/g, '/');
    // Direct match
    if (filePath === allowed) {
      return { allowed: true, allowedFiles };
    }
    // Glob pattern match
    if (minimatch(filePath, allowed)) {
      return { allowed: true, allowedFiles };
    }
    // Prefix match (allow subdirs)
    const prefix = allowed.replace(/\/\*$/, '') + '/';
    if (filePath.startsWith(prefix)) {
      return { allowed: true, allowedFiles };
    }
  }

  return { allowed: false, allowedFiles };
}
