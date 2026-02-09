/**
 * Block git commit if spec has unfilled Impact Tree checkboxes.
 *
 * This hook ensures that Impact Tree Analysis is completed before committing.
 * It checks for unchecked boxes (- [ ]) in the Impact Tree section of feature specs.
 */

import { readFileSync, existsSync } from 'fs';
import { execFileSync } from 'child_process';
import { readHookInput, getToolInput } from './utils.mjs';

function main() {
  try {
    const data = readHookInput();
    const command = getToolInput(data, 'command') || '';

    // Only check for git commit
    if (!command.includes('git commit')) {
      process.exit(0);
    }

    // Find spec in current staged changes
    let stagedFiles;
    try {
      stagedFiles = execFileSync('git', ['diff', '--cached', '--name-only'], {
        encoding: 'utf-8',
        timeout: 5000,
      }).trim();
    } catch {
      process.exit(0);
    }

    const specFile = stagedFiles
      .split('\n')
      .find(f => /^ai\/features\/.*\.md$/.test(f));

    if (specFile && existsSync(specFile)) {
      const content = readFileSync(specFile, 'utf-8');
      const impactSection = content.match(/## Impact Tree Analysis[\s\S]*?(?=\n##|\s*$)/);

      if (impactSection && impactSection[0].includes('- [ ]')) {
        process.stdout.write(
          JSON.stringify({
            hookSpecificOutput: {
              permissionDecision: 'deny',
              permissionDecisionReason:
                'Spec has unfilled Impact Tree checkboxes!\n\n' +
                'Complete the Impact Tree Analysis before committing:\n' +
                '1. Fill all checkboxes in Impact Tree section\n' +
                '2. Ensure grep results are recorded\n' +
                '3. Verify all found files are in Allowed Files\n\n' +
                'See: CLAUDE.md -> Impact Tree Analysis',
            },
          }) + '\n',
        );
        process.exit(0);
      }
    }

    process.exit(0);
  } catch {
    process.exit(0); // fail-safe
  }
}

main();
