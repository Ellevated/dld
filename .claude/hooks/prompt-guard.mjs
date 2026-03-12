/**
 * Prompt guard: suggests spark for complex tasks.
 *
 * Soft block:
 * - Complex tasks without spark/autopilot
 *
 * Detects patterns like:
 * - "create new feature", "implement X"
 * - "add endpoint", "write function"
 */

import { approvePrompt, blockPrompt, getUserPrompt, logHookError, readHookInput } from './utils.mjs';

// Max chars between keyword and target in complexity patterns
const KEYWORD_TARGET_GAP = 30;

// Complexity indicators (keywords + explicit code requests)
const COMPLEXITY_PATTERNS = [
  new RegExp(
    `\\b(implement|create|build|add|write)\\b.{0,${KEYWORD_TARGET_GAP}}\\b(feature|function|endpoint|api|service|handler)`,
    'i',
  ),
  /\bnew\s+(feature|functionality)/i,
  /\bwrite\s+(a\s+)?(function|class|method|code|script)/i,
  /\bcreate\s+(a\s+)?(endpoint|api|handler|service)/i,
];

// Skip if already using skills
const SKILL_INDICATORS = [
  /\/spark/,
  /\/autopilot/,
  /\/audit/,
  /\/plan/,
  /\/council/,
  /\bspark\b/,
  /\bautopilot\b/,
  /\baudit\b/,
];

function main() {
  try {
    const data = readHookInput();
    const prompt = getUserPrompt(data);
    const promptLower = prompt.toLowerCase();

    // Skip if using skills
    for (const indicator of SKILL_INDICATORS) {
      if (indicator.test(promptLower)) {
        approvePrompt();
        return;
      }
    }

    // Check for complexity patterns
    for (const pattern of COMPLEXITY_PATTERNS) {
      if (pattern.test(promptLower)) {
        blockPrompt(
          'Complex task detected!\n\n' +
            'Consider using /spark for proper planning:\n' +
            '  /spark <task description>\n\n' +
            'Benefits:\n' +
            '  - Structured research (Exa)\n' +
            '  - Explicit file allowlist\n' +
            '  - Auto-handoff to autopilot\n' +
            '  - Deterministic workflow\n\n' +
            'Retype with /spark or rephrase to proceed.',
        );
        return;
      }
    }

    approvePrompt();
  } catch (e) {
    logHookError('prompt_guard', e);
    approvePrompt();
  }
}

main();
