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

import { allowTool, askTool, denyTool, getToolInput, logHookError, readHookInput } from './utils.mjs';

// Blocked patterns - hard deny (no confirmation)
// Note: git push -f to feature branches is ALLOWED (rebase workflow)
// Only develop/main are protected from force push
const BLOCKED_PATTERNS = [
  // Push to main (Hard Block)
  [
    /git\s+push[^|]*\bmain\b/i,
    'Push to main blocked!\n\n' +
      'Use PR workflow: develop -> PR -> main\n' +
      'Direct push to main is forbidden.\n\n' +
      'See: CLAUDE.md -> Git Autonomous Mode',
  ],
  // Destructive git operations (Multi-Agent Safety)
  // Negative lookahead (?!-\w*n) excludes dry-run variants (-fdn, -dfn)
  [
    /git\s+clean\s+(?!-\w*n)-[a-z]*f[a-z]*d|git\s+clean\s+(?!-\w*n)-[a-z]*d[a-z]*f/i,
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
  [
    /git\s+push\s+(-f|--force(?!-with-lease))[^|]*\b(develop|main)\b/i,
    'Force push to protected branch blocked!\n\n' +
      'Force push allowed only on feature branches.\n' +
      'Protected: develop, main\n\n' +
      'Safe alternatives:\n' +
      '  git push --force-with-lease  # checks remote state first\n' +
      '  git push -f origin feature/{ID}  # force push feature branch\n\n' +
      'See: CLAUDE.md -> Git Autonomous Mode',
  ],
  [
    /git\s+push[^|]*\b(develop|main)\b[^|]*(-f|--force(?!-with-lease))/i,
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
  [
    /git\s+merge/i,
    'Use --ff-only for merges!\n\n' +
      'Rebase-first workflow required:\n' +
      '  1. git rebase origin/develop  # in worktree\n' +
      '  2. git push -f origin {branch}  # force push feature\n' +
      '  3. git merge --ff-only {branch}  # in main repo\n\n' +
      'See: CLAUDE.md -> Rebase Workflow',
  ],
];

function main() {
  try {
    const data = readHookInput();
    const command = getToolInput(data, 'command') || '';

    // Hard blocks (deny immediately)
    // Note: --force-with-lease is handled by regex negative lookahead (?!-with-lease)
    for (const [pattern, message] of BLOCKED_PATTERNS) {
      if (pattern.test(command)) {
        denyTool(message);
        return;
      }
    }

    // Soft blocks (ask confirmation)
    for (const [pattern, message] of MERGE_PATTERNS) {
      if (pattern.test(command)) {
        // Allow --ff-only explicitly (per spec)
        if (command.includes('--ff-only')) continue;
        askTool(message);
        return;
      }
    }

    allowTool();
  } catch (e) {
    logHookError('pre_bash', e);
    allowTool();
  }
}

main();
