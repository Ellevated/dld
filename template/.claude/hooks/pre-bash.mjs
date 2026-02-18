/**
 * Pre-Bash hook: blocks dangerous commands.
 *
 * Hard blocks:
 * - Push to main branch (protected workflow)
 * - Destructive git operations (git clean -fd, git reset --hard)
 * - Force push to protected branches (develop, main)
 *
 * Soft blocks (ask confirmation):
 * - Merge without --ff-only (rebase-first workflow)
 *
 * Customize BLOCKED_PATTERNS for project-specific rules.
 */

import { allowTool, askTool, debugLog, debugTiming, denyTool, getToolInput, logHookError, readHookInput } from './utils.mjs';

// F-011: Detect destructive git clean — handles separated flags and --force
function isDestructiveClean(cmd) {
  if (!/git\s+clean\b/i.test(cmd)) return false;
  // Dry-run is always safe
  if (/(?:^|\s)-\w*n/i.test(cmd) || /--dry-run/i.test(cmd)) return false;
  const hasForce = /(?:^|\s)--force\b/i.test(cmd) || /(?:^|\s)-[a-z]*f/i.test(cmd);
  const hasDir = /(?:^|\s)-[a-z]*d/i.test(cmd);
  return hasForce && hasDir;
}

// Blocked patterns - hard deny (no confirmation)
// Note: git push -f to feature branches is ALLOWED (rebase workflow)
// Only develop/main are protected from force push
// Entries: [pattern_or_function, message]
const BLOCKED_PATTERNS = [
  // Push to main (Hard Block)
  // F-014: Use lookaround to avoid false positives on branch names containing "main"
  [
    /git\s+push\b.*(?<![a-zA-Z0-9_-])main(?![a-zA-Z0-9_-])/i,
    'Push to main blocked!\n\n' +
      'Use PR workflow: develop -> PR -> main\n' +
      'Direct push to main is forbidden.\n\n' +
      'See: CLAUDE.md -> Git Autonomous Mode',
  ],
  // Destructive git clean (Multi-Agent Safety)
  // F-011: Function-based check handles --force, -f -d, -fd, etc.
  [
    isDestructiveClean,
    'git clean -fd blocked!\n\n' +
      'Destroys untracked files from other agents.\n' +
      'Safe alternatives:\n' +
      '  git checkout -- .     # reset tracked only\n' +
      '  git stash -u          # stash with recovery\n' +
      '  git clean -fdn        # dry-run first\n\n' +
      'See: CLAUDE.md -> Multi-Agent Safety',
  ],
  [
    /git\s+reset\s+--hard/i,
    'git reset --hard blocked!\n\n' +
      'Wipes uncommitted work from all agents.\n' +
      'Safe alternatives:\n' +
      '  git checkout -- .     # reset tracked only\n' +
      '  git stash             # save work first\n\n' +
      'See: CLAUDE.md -> Multi-Agent Safety',
  ],
  // Force push safety (allow feature branches only)
  // Note: --force-with-lease is ALLOWED (safe force push that checks remote state)
  // Only block -f and --force (without -with-lease suffix)
  // Lookaheads match both conditions regardless of order
  [
    /git\s+push\b(?=.*\b(develop|main)\b)(?=.*(-f\b|--force\b(?!-with-lease)))/i,
    'Force push to protected branch blocked!\n\n' +
      'Force push allowed only on feature branches.\n' +
      'Protected: develop, main\n\n' +
      'Safe alternatives:\n' +
      '  git push --force-with-lease  # checks remote state first\n' +
      '  git push -f origin feature/{ID}  # force push feature branch\n\n' +
      'See: CLAUDE.md -> Git Autonomous Mode',
  ],
];

// Merge without rebase verification (Parallel Safety)
const MERGE_PATTERNS = [
  // F-013: Word boundary + negative lookahead excludes merge-base, mergetool
  [
    /git\s+merge\b(?![-a-z])/i,
    'Use --ff-only for merges!\n\n' +
      'Rebase-first workflow required:\n' +
      '  1. git rebase origin/develop  # in worktree\n' +
      '  2. git push -f origin {branch}  # force push feature\n' +
      '  3. git merge --ff-only {branch}  # in main repo\n\n' +
      'See: CLAUDE.md -> Rebase Workflow',
  ],
];

function main() {
  const timer = debugTiming('pre-bash');
  try {
    const data = readHookInput();
    const command = getToolInput(data, 'command') || '';
    debugLog('pre-bash', 'input', { command: command.slice(0, 100) });

    // Hard blocks (deny immediately)
    // Supports both RegExp and function matchers
    for (const [matcher, message] of BLOCKED_PATTERNS) {
      const blocked = typeof matcher === 'function' ? matcher(command) : matcher.test(command);
      if (blocked) {
        debugLog('pre-bash', 'deny', { reason: 'blocked_pattern', command: command.slice(0, 100) });
        timer.end('deny');
        denyTool(message);
        return;
      }
    }

    // Soft blocks (ask confirmation)
    for (const [pattern, message] of MERGE_PATTERNS) {
      if (pattern.test(command)) {
        // Allow --ff-only explicitly (per spec)
        if (command.includes('--ff-only')) continue;
        debugLog('pre-bash', 'ask', { reason: 'merge_pattern', command: command.slice(0, 100) });
        timer.end('ask');
        askTool(message);
        return;
      }
    }

    debugLog('pre-bash', 'allow');
    timer.end('allow');
    allowTool();
  } catch (e) {
    debugLog('pre-bash', 'error', { error: String(e) });
    timer.end('error');
    logHookError('pre_bash', e);
    allowTool();
  }
}

main();
