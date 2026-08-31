/**
 * Pre-Edit hook: protects files and enforces LOC limits.
 *
 * Hard blocks:
 * - Files outside Allowed Files in spec (when spec exists)
 * - Protected test files (contracts/, regression/)
 * - Plan-before-code gate (src/ edits blocked when autopilot-state.json has plan_exists: false)
 *
 * Soft blocks:
 * - Files exceeding LOC limits (400 code, 600 tests)
 *
 * Configurable via hooks.config.mjs / hooks.config.local.mjs
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import {
  allowTool,
  askTool,
  debugLog,
  debugTiming,
  denyTool,
  getProjectDir,
  getToolInput,
  getWorktreeRoot,
  inferSpecFromBranch,
  isFileAllowed,
  loadConfig,
  logHookError,
  readHookInput,
} from './utils.mjs';

// Hardcoded fallbacks (used when config is unavailable)
const FALLBACK_PROTECTED = ['tests/contracts/', 'tests/regression/'];
const FALLBACK_MAX_LOC_CODE = 400;
const FALLBACK_MAX_LOC_TEST = 600;
const FALLBACK_WARN_THRESHOLD = 7 / 8;
const FALLBACK_SYNC_ZONES = ['.claude/', 'scripts/'];
const FALLBACK_EXCLUDE_SYNC = [
  '.claude/rules/localization.md',
  '.claude/CUSTOMIZATIONS.md',
  '.claude/settings.local.json',
];
const FALLBACK_INT_PATTERNS = [/^tests\/integration\//, /\.integration\.test\./, /\.integration\.spec\./];
const FALLBACK_MOCK_PATTERNS = [/jest\.mock\s*\(/, /vi\.mock\s*\(/, /\bunittest\.mock\b/, /\bMagicMock\b/, /@patch\b/, /\bmock\.patch\b/, /\bsinon\.stub\b/, /\bsinon\.mock\b/];

function countLines(filePath) {
  try {
    const content = readFileSync(filePath, 'utf-8');
    if (!content) return 0;
    return content.split('\n').length - (content.endsWith('\n') ? 1 : 0);
  } catch {
    return 0;
  }
}

/**
 * Whether the pending edit leaves the file no larger than it already is.
 *
 * A file already past the limit is otherwise unfixable: every edit is denied,
 * while the hook's own advice ("split the file") requires editing that same
 * file. Growth stays blocked; shrinking edits — the split itself, deletions,
 * refactors — are allowed, so the advice becomes possible to follow.
 *
 * For Edit, comparing the line counts of old_string and new_string is enough,
 * and it holds for replace_all too: a delta that is non-positive per occurrence
 * cannot grow the file however many occurrences are replaced.
 *
 * Note: getToolInput() returns null for an empty string, so a deletion arrives
 * as old_string set and new_string null — that is a shrink, not a missing key.
 */
function editDoesNotGrowFile(data, currentLoc) {
  const oldString = getToolInput(data, 'old_string');
  if (oldString !== null) {
    const newString = getToolInput(data, 'new_string') || '';
    const removed = oldString.split('\n').length;
    const added = newString ? newString.split('\n').length : 0;
    return added <= removed;
  }

  const content = getToolInput(data, 'content');
  if (content !== null) {
    const newLoc = content.split('\n').length - (content.endsWith('\n') ? 1 : 0);
    return newLoc <= currentLoc;
  }

  return false;
}

const TEST_FILE_PATTERNS = [
  /_test\./, /\.test\./, /\.spec\./,
  /\/tests?\//, /__tests__\//,
  /(^|\/)test_[^/]+\.py$/,
];

function isTestFile(filePath) {
  return TEST_FILE_PATTERNS.some(pattern => pattern.test(filePath));
}

function isIntegrationTest(relPath, patterns) {
  return patterns.some(p => p.test(relPath));
}

function containsMockPattern(content, patterns) {
  if (!content) return null;
  for (const p of patterns) {
    if (p.test(content)) return p.source;
  }
  return null;
}

/**
 * Find autopilot-state.json in project dir or worktree root.
 * Covers mismatch when CLAUDE_PROJECT_DIR != cwd worktree.
 */
function findAutopilotState() {
  const candidates = [join(getProjectDir(), 'autopilot-state.json')];
  const worktreeRoot = getWorktreeRoot();
  if (worktreeRoot) {
    candidates.push(join(worktreeRoot, 'autopilot-state.json'));
  }
  for (const p of candidates) {
    if (existsSync(p)) {
      try { return JSON.parse(readFileSync(p, 'utf-8')); } catch { /* fail-safe */ }
    }
  }
  return null;
}

function normalizePath(filePath) {
  if (!filePath) return '';
  const projectDir = getProjectDir();
  if (filePath.startsWith(projectDir)) {
    return filePath.slice(projectDir.length).replace(/^[/\\]/, '');
  }
  return filePath;
}

function checkSyncZone(relPath, syncZones, excludeFromSync) {
  if (!relPath) return null;

  const inSyncZone = syncZones.some(zone => relPath.startsWith(zone));
  if (!inSyncZone) return null;
  if (excludeFromSync.includes(relPath)) return null;

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

async function main() {
  const timer = debugTiming('pre-edit');
  try {
    const data = readHookInput();
    const filePath = getToolInput(data, 'file_path') || '';
    const relPath = normalizePath(filePath);
    debugLog('pre-edit', 'input', { file: relPath });

    const config = await loadConfig();
    const protectedPaths = config?.preEdit?.protectedPaths || FALLBACK_PROTECTED;
    const maxLocCode = config?.preEdit?.maxLocCode ?? FALLBACK_MAX_LOC_CODE;
    const maxLocTest = config?.preEdit?.maxLocTest ?? FALLBACK_MAX_LOC_TEST;
    const warnThreshold = config?.preEdit?.warnThreshold ?? FALLBACK_WARN_THRESHOLD;
    const syncZones = config?.preEdit?.syncZones || FALLBACK_SYNC_ZONES;
    const excludeFromSync = config?.preEdit?.excludeFromSync || FALLBACK_EXCLUDE_SYNC;
    const alwaysAllowed = config?.utils?.alwaysAllowedPatterns || undefined;

    // Check Allowed Files (Hard Block) - only when spec exists
    const specPath = process.env.CLAUDE_CURRENT_SPEC_PATH || inferSpecFromBranch();
    const { allowed, allowedFiles } = isFileAllowed(relPath, specPath, alwaysAllowed);
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
    for (const protectedPath of protectedPaths) {
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

    // Check mock ban in integration tests (Hard Block)
    const mockBan = config?.preEdit?.mockBan;
    if (mockBan?.enabled !== false) {
      const intPatterns = mockBan?.integrationTestPatterns || FALLBACK_INT_PATTERNS;
      if (isIntegrationTest(relPath, intPatterns)) {
        const newContent = getToolInput(data, 'new_string') || getToolInput(data, 'content') || '';
        const mockPats = mockBan?.mockPatterns || FALLBACK_MOCK_PATTERNS;
        const matched = containsMockPattern(newContent, mockPats);
        if (matched) {
          debugLog('pre-edit', 'deny', { reason: 'mock_in_integration', file: relPath, pattern: matched });
          timer.end('deny');
          denyTool(
            `Mock in integration test!\n\n` +
              `${relPath}\nPattern: ${matched}\n\n` +
              `Integration tests must use real dependencies (Testcontainers).\n` +
              `Mocks allowed only in tests/unit/.`,
          );
          return;
        }
      }
    }

    // Check plan-before-code gate (Hard Block)
    // Only activates when autopilot-state.json exists AND plan_exists is false
    const requirePlan = config?.enforcement?.requirePlanBeforeCode !== false;
    if (requirePlan && relPath.startsWith('src/')) {
      try {
        const autopilotState = findAutopilotState();
        if (autopilotState && autopilotState.plan_exists === false) {
          debugLog('pre-edit', 'deny', { reason: 'no_plan', file: relPath });
          timer.end('deny');
          denyTool(
            'Plan not found in spec. Run planner first.\n\n' +
              `File: ${relPath}\n` +
              'autopilot-state.json shows plan_exists: false\n\n' +
              'The planner must create an implementation plan before code changes.\n' +
              'See: task-loop.md -> Step 1',
          );
          return;
        }
      } catch {
        // fail-safe: autopilot-state read error = don't block (ADR-004)
      }
    }

    // Check LOC limits (Soft Block)
    const absPath = filePath.startsWith('/') ? filePath : join(process.cwd(), filePath);

    if (existsSync(absPath)) {
      const loc = countLines(absPath);
      const maxLoc = isTestFile(relPath) ? maxLocTest : maxLocCode;
      const warnLoc = Math.floor(maxLoc * warnThreshold);

      if (loc >= maxLoc) {
        if (editDoesNotGrowFile(data, loc)) {
          debugLog('pre-edit', 'allow', { reason: 'loc_limit_shrinking_edit', file: relPath, loc, maxLoc });
          timer.end('allow');
          allowTool();
          return;
        }
        debugLog('pre-edit', 'deny', { reason: 'loc_limit', file: relPath, loc, maxLoc });
        timer.end('deny');
        denyTool(
          `File exceeds LOC limit!\n\n` +
            `${relPath}: ${loc} lines (limit: ${maxLoc})\n\n` +
            `Edits that grow this file are blocked. Edits that shrink it are allowed,\n` +
            `so the split itself is possible: move code into a new module, then delete\n` +
            `it here. Deletions and same-size rewrites pass too.\n\n` +
            `See: CLAUDE.md -> File Limits`,
        );
        return;
      } else if (loc >= warnLoc) {
        // Soft warning: allow edit but log — denyTool() would be too aggressive,
        // askTool() kills bypass mode (claude-code#37420)
        debugLog('pre-edit', 'allow', { reason: 'loc_warning', file: relPath, loc, maxLoc });
        timer.end('allow');
        allowTool();
        return;
      }
    }

    // Check sync zone (Soft reminder) — allow edit, log reminder
    // askTool() kills bypass mode (claude-code#37420), and denyTool() would block all template edits
    const syncReminder = checkSyncZone(relPath, syncZones, excludeFromSync);
    if (syncReminder) {
      debugLog('pre-edit', 'allow', { reason: 'sync_zone', file: relPath, reminder: syncReminder });
      timer.end('allow');
      allowTool();
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
