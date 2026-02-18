/**
 * Block git commit if spec has unfilled Impact Tree checkboxes.
 *
 * This hook ensures that Impact Tree Analysis is completed before committing.
 * It checks for unchecked boxes (- [ ]) in the Impact Tree section of feature specs.
 */

import { readFileSync, existsSync } from 'fs';
import { execFileSync } from 'child_process';
import { denyTool, readHookInput, getToolInput } from './utils.mjs';

function stripCodeBlocks(text) {
  return text.replace(/```[\s\S]*?```/g, '');
}

function main() {
  try {
    const data = readHookInput();
    const command = getToolInput(data, 'command') || '';

    // Only check for git commit (excludes git commit-graph, git commit-tree, etc.)
    if (!/\bgit\s+commit\b(?!-)/i.test(command)) {
      process.exit(0);
    }

    // Find spec in current staged changes
    // Note: If ai/ is in .gitignore, spec files will never be staged and this hook is a no-op.
    // This is correct — the hook is for projects that track specs in git.
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

      if (impactSection) {
        const stripped = stripCodeBlocks(impactSection[0]);
        if (stripped.includes('- [ ]')) {
          denyTool(
            'Spec has unfilled Impact Tree checkboxes!\n\n' +
              'Complete the Impact Tree Analysis before committing:\n' +
              '1. Fill all checkboxes in Impact Tree section\n' +
              '2. Ensure grep results are recorded\n' +
              '3. Verify all found files are in Allowed Files\n\n' +
              'See: CLAUDE.md -> Impact Tree Analysis',
          );
          return;
        }
      }
    }

    process.exit(0);
  } catch {
    process.exit(0); // fail-safe
  }
}

main();
