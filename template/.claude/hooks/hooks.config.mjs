// Hook configuration — default rules from DLD template.
// DO NOT EDIT for project-specific customizations.
// Use hooks.config.local.mjs instead (protected from upgrades).

/**
 * Default configuration for Claude Code hooks.
 *
 * All hook rules (blocked commands, protected paths, LOC limits, etc.)
 * are defined here as defaults. Users can override any value by creating
 * hooks.config.local.mjs in the same directory.
 *
 * See README.md -> Customizing Hooks for details.
 */

// F-011: Detect destructive git clean — handles separated flags and --force
function isDestructiveClean(cmd) {
  if (!/git\s+clean\b/i.test(cmd)) return false;
  if (/(?:^|\s)-\w*n/i.test(cmd) || /--dry-run/i.test(cmd)) return false;
  const hasForce = /(?:^|\s)--force\b/i.test(cmd) || /(?:^|\s)-[a-z]*f/i.test(cmd);
  const hasDir = /(?:^|\s)-[a-z]*d/i.test(cmd);
  return hasForce && hasDir;
}

export default {
  preBash: {
    // Hard blocks — deny immediately, no confirmation
    // Entries: [matcher, message] — matcher is RegExp or function(cmd) → boolean
    blockedPatterns: [
      [
        /git\s+push\b.*(?<![a-zA-Z0-9_-])main(?![a-zA-Z0-9_-])/i,
        'Push to main blocked!\n\n' +
          'Use PR workflow: develop -> PR -> main\n' +
          'Direct push to main is forbidden.\n\n' +
          'See: CLAUDE.md -> Git Autonomous Mode',
      ],
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
    ],
    // Soft blocks — ask user for confirmation
    mergePatterns: [
      [
        /git\s+merge\b(?![-a-z])/i,
        'Use --ff-only for merges!\n\n' +
          'Rebase-first workflow required:\n' +
          '  1. git rebase origin/develop  # in worktree\n' +
          '  2. git push -f origin {branch}  # force push feature\n' +
          '  3. git merge --ff-only {branch}  # in main repo\n\n' +
          'See: CLAUDE.md -> Rebase Workflow',
      ],
    ],
  },

  preEdit: {
    // Protected paths — hard block
    protectedPaths: ['tests/contracts/', 'tests/regression/'],
    // LOC limits — soft block
    maxLocCode: 400,
    maxLocTest: 600,
    warnThreshold: 7 / 8,
    // Sync zones
    syncZones: ['.claude/', 'scripts/'],
    excludeFromSync: [
      '.claude/rules/localization.md',
      '.claude/rules/template-sync.md',
      '.claude/CUSTOMIZATIONS.md',
      '.claude/settings.local.json',
    ],
  },

  utils: {
    // Files always allowed regardless of spec allowlist
    alwaysAllowedPatterns: [
      'ai/features/*.md',
      'ai/backlog.md',
      'ai/diary/**',
      '.gitignore',
      'pyproject.toml',
      '.claude/**',
    ],
  },

  enforcement: {
    requireResearchForSpec: true,
    requirePlanBeforeCode: true,
    requireTestsInSpec: true,
    requireEvalCriteria: true,
    requireAcceptanceVerification: false,
    minTestCases: 3,
    minEvalCriteria: 3,
    minResearchFiles: 2,
  },

  promptGuard: {
    keywordTargetGap: 30,
    complexityPatterns: [
      /\b(implement|create|build|add|write)\b.{0,30}\b(feature|function|endpoint|api|service|handler)/i,
      /\bnew\s+(feature|functionality)/i,
      /\bwrite\s+(a\s+)?(function|class|method|code|script)/i,
      /\bcreate\s+(a\s+)?(endpoint|api|handler|service)/i,
    ],
    skillIndicators: [
      /\/spark/,
      /\/autopilot/,
      /\/audit/,
      /\/plan/,
      /\/council/,
      /\bspark\b/,
      /\bautopilot\b/,
      /\baudit\b/,
    ],
  },
};
