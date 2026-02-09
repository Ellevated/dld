/**
 * Session End Hook - soft reminder about diary entries.
 * NEVER blocks, only reminds.
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
const indexFile = join(projectDir, 'ai', 'diary', 'index.md');

function countPending() {
  if (!existsSync(indexFile)) return 0;
  try {
    const content = readFileSync(indexFile, 'utf-8');
    return (content.match(/\| pending \|/g) || []).length;
  } catch {
    return 0;
  }
}

const pendingCount = countPending();

if (pendingCount > 5) {
  process.stdout.write(
    JSON.stringify({
      decision: 'approve',
      reason: `Reminder: ${pendingCount} pending diary entries. Consider /reflect when convenient.`,
    }) + '\n',
  );
} else {
  process.stdout.write('{}\n');
}
