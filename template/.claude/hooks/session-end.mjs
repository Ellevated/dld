/**
 * Session End Hook - soft reminder about diary entries.
 * NEVER blocks session end, only adds context via systemMessage.
 *
 * Stop hook protocol: { decision: "approve"|"block", reason: "...", systemMessage: "..." }
 * We always approve (never prevent session end) but attach reminder as systemMessage.
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { logHookError } from './utils.mjs';

function countPending(indexFile) {
  if (!existsSync(indexFile)) return 0;
  try {
    const content = readFileSync(indexFile, 'utf-8');
    return (content.match(/\| pending \|/g) || []).length;
  } catch {
    return 0;
  }
}

function main() {
  try {
    const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
    const indexFile = join(projectDir, 'ai', 'diary', 'index.md');
    const pendingCount = countPending(indexFile);

    if (pendingCount > 5) {
      try {
        process.stdout.write(
          JSON.stringify({
            decision: 'approve',
            systemMessage: `Reminder: ${pendingCount} pending diary entries. Consider /reflect when convenient.`,
          }) + '\n',
        );
      } catch {
        // pipe closed — OK
      }
    }

    process.exit(0);
  } catch (e) {
    logHookError('session_end', e);
    process.exit(0); // fail-safe: never prevent session end
  }
}

main();
