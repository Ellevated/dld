/**
 * Pre-Edit hook: protects files and enforces LOC limits.
 *
 * Hard blocks:
 * - Files outside Allowed Files in spec (when spec exists)
 * - Protected test files (contracts/, regression/)
 *
 * Soft blocks:
 * - Files exceeding LOC limits (400 code, 600 tests)
 */

import { readFileSync, existsSync } from 'fs';
import { join, normalize } from 'path';
import {
  allowTool,
  askTool,
  debugLog,
  debugTiming,
  denyTool,
  getProjectDir,
  getToolInput,
  inferSpecFromBranch,
  isFileAllowed,
  logHookError,
  readHookInput,
} from './utils.mjs';

// Protected paths (Hard Block)
const PROTECTED_PATHS = ['tests/contracts/', 'tests/regression/'];

// LOC limits (Soft Block)
const MAX_LOC_CODE = 400;
const MAX_LOC_TEST = 600;
const WARN_THRESHOLD = 7 / 8; // 87.5%

// Sync zones (files that should stay in sync with template/)
const SYNC_ZONES = ['.claude/', 'scripts/'];

// Excluded from sync reminders (DLD-specific customizations)
const EXCLUDE_FROM_SYNC = [
  '.claude/rules/localization.md',
  '.claude/rules/template-sync.md',
  '.claude/rules/git-local-folders.md',
  '.claude/CUSTOMIZATIONS.md',
  '.claude/settings.local.json',
];

function countLines(filePath) {
  try {
    const content = readFileSync(filePath, 'utf-8');
    if (!content) return 0;
    return content.split('\n').length - (content.endsWith('\n') ? 1 : 0);
  } catch {
    return 0;
  }
}

const TEST_FILE_PATTERNS = [
  /_test\./, /\.test\./, /\.spec\./,
  /\/tests?\//, /__tests__\//,
  /(^|\/)test_[^/]+\.py$/,
];

function isTestFile(filePath) {
  return TEST_FILE_PATTERNS.some(pattern => pattern.test(filePath));
}

function normalizePath(filePath) {
  if (!filePath) return '';
  const projectDir = getProjectDir();
  if (filePath.startsWith(projectDir)) {
    return filePath.slice(projectDir.length).replace(/^[/\\]/, '');
  }
  return filePath;
}

function checkSyncZone(relPath) {
  if (!relPath) return null;

  const inSyncZone = SYNC_ZONES.some(zone => relPath.startsWith(zone));
  if (!inSyncZone) return null;
  if (EXCLUDE_FROM_SYNC.includes(relPath)) return null;

  const templatePath = join(getProjectDir(), 'template', relPath);
  if (existsSync(templatePath)) {
    return (
      `SYNC ZONE: ${relPath}\n\n` +
      `This file exists in template/${relPath}\n` +
      `Remember to sync changes bidirectionally.\n\n` +
      `See: .claude/rules/template-sync.md`
    );
  }
  return null;
}

function main() {
  const timer = debugTiming('pre-edit');
  try {
    const data = readHookInput();
    const filePath = getToolInput(data, 'file_path') || '';
    const relPath = normalizePath(filePath);
    debugLog('pre-edit', 'input', { file: relPath });

    // Check Allowed Files (Hard Block) - only when spec exists
    const specPath = process.env.CLAUDE_CURRENT_SPEC_PATH || inferSpecFromBranch();
    const { allowed, allowedFiles } = isFileAllowed(relPath, specPath);
    if (!allowed) {
      const allowedList = allowedFiles.slice(0, 10).map(f => `  - ${f}`).join('\n');
      debugLog('pre-edit', 'deny', { reason: 'not_in_allowed_files', file: relPath });
      timer.end('deny');
      denyTool(
        `File not in Allowed Files!\n\n` +
          `${relPath}\n\n` +
          `Spec: ${specPath || '(not found)'}\n\n` +
          `Allowed files:\n${allowedList}\n\n` +
          `To fix:\n` +
          `1. Edit ${specPath || '(spec file)'}\n` +
          `2. Find ## Allowed Files section\n` +
          `3. Add: \`${relPath}\` — {description}\n` +
          `4. Save and retry\n\n` +
          `Or change approach to use only allowed files.`,
      );
      return;
    }

    // Check protected paths (Hard Block)
    for (const protectedPath of PROTECTED_PATHS) {
      if (relPath.startsWith(protectedPath)) {
        debugLog('pre-edit', 'deny', { reason: 'protected_path', file: relPath });
        timer.end('deny');
        denyTool(
          `Protected test file!\n\n` +
            `${relPath}\n\n` +
            `tests/contracts/ and tests/regression/ cannot be modified.\n` +
            `Fix the code, not the test.\n\n` +
            `See: CLAUDE.md -> Test Safety`,
        );
        return;
      }
    }

    // Check LOC limits (Soft Block)
    const absPath = filePath.startsWith('/') ? filePath : join(process.cwd(), filePath);

    if (existsSync(absPath)) {
      const loc = countLines(absPath);
      const maxLoc = isTestFile(relPath) ? MAX_LOC_TEST : MAX_LOC_CODE;
      const warnLoc = Math.floor(maxLoc * WARN_THRESHOLD);

      if (loc >= maxLoc) {
        debugLog('pre-edit', 'ask', { reason: 'loc_limit', file: relPath, loc, maxLoc });
        timer.end('ask');
        askTool(
          `File exceeds LOC limit!\n\n` +
            `${relPath}: ${loc} lines (limit: ${maxLoc})\n\n` +
            `Consider splitting the file.\n` +
            `See: CLAUDE.md -> File Limits\n\n` +
            `Proceed anyway?`,
        );
        return;
      } else if (loc >= warnLoc) {
        debugLog('pre-edit', 'ask', { reason: 'loc_warning', file: relPath, loc, maxLoc });
        timer.end('ask');
        askTool(
          `File approaching LOC limit\n\n` +
            `${relPath}: ${loc} lines (limit: ${maxLoc})\n\n` +
            `Proceed?`,
        );
        return;
      }
    }

    // Check sync zone (Soft reminder)
    const syncReminder = checkSyncZone(relPath);
    if (syncReminder) {
      debugLog('pre-edit', 'ask', { reason: 'sync_zone', file: relPath });
      timer.end('ask');
      askTool(syncReminder);
      return;
    }

    debugLog('pre-edit', 'allow', { file: relPath });
    timer.end('allow');
    allowTool();
  } catch (e) {
    debugLog('pre-edit', 'error', { error: String(e) });
    timer.end('error');
    logHookError('pre_edit', e);
    allowTool();
  }
}

main();
