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
 * Configurable via hooks.config.mjs / hooks.config.local.mjs
 */

import { allowTool, askTool, debugLog, debugTiming, denyTool, getToolInput, loadConfig, logHookError, readHookInput } from './utils.mjs';

// F-011: Detect destructive git clean — handles separated flags and --force
function isDestructiveClean(cmd) {
  if (!/git\s+clean\b/i.test(cmd)) return false;
  // Dry-run is always safe
  if (/(?:^|\s)-\w*n/i.test(cmd) || /--dry-run/i.test(cmd)) return false;
  const hasForce = /(?:^|\s)--force\b/i.test(cmd) || /(?:^|\s)-[a-z]*f/i.test(cmd);
  const hasDir = /(?:^|\s)-[a-z]*d/i.test(cmd);
  return hasForce && hasDir;
}

// Hardcoded fallback patterns (used when config is unavailable)
const FALLBACK_BLOCKED = [
  [/git\s+push\b.*(?<![a-zA-Z0-9_-])main(?![a-zA-Z0-9_-])/i, 'Push to main blocked!'],
  [isDestructiveClean, 'git clean -fd blocked!'],
  [/git\s+reset\s+--hard/i, 'git reset --hard blocked!'],
  [/git\s+push\b(?=.*\b(develop|main)\b)(?=.*(-f\b|--force\b(?!-with-lease)))/i, 'Force push to protected branch blocked!'],
];

const FALLBACK_MERGE = [
  [/git\s+merge\b(?![-a-z])/i, 'Use --ff-only for merges!'],
];

async function main() {
  const timer = debugTiming('pre-bash');
  try {
    const data = readHookInput();
    const command = getToolInput(data, 'command') || '';
    debugLog('pre-bash', 'input', { command: command.slice(0, 100) });

    const config = await loadConfig();
    const blockedPatterns = config?.preBash?.blockedPatterns || FALLBACK_BLOCKED;
    const mergePatterns = config?.preBash?.mergePatterns || FALLBACK_MERGE;

    // Hard blocks (deny immediately)
    // Supports both RegExp and function matchers
    for (const [matcher, message] of blockedPatterns) {
      const blocked = typeof matcher === 'function' ? matcher(command) : matcher.test(command);
      if (blocked) {
        debugLog('pre-bash', 'deny', { reason: 'blocked_pattern', command: command.slice(0, 100) });
        timer.end('deny');
        denyTool(message);
        return;
      }
    }

    // Soft blocks (ask confirmation)
    for (const [pattern, message] of mergePatterns) {
      const matched = typeof pattern === 'function' ? pattern(command) : pattern.test(command);
      if (matched) {
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
