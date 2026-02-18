/**
 * Tests for session-end.mjs
 *
 * Verifies countPending() behaviour through integration:
 * - No diary/index.md → silent exit 0
 * - <=5 pending entries → silent exit 0
 * - >5 pending entries → JSON with decision:'approve' and systemMessage with count
 */

import { describe, it, before, after } from 'node:test';
import { strictEqual, ok } from 'node:assert';
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { runHook, makeStopInput } from './helpers.mjs';

let tmpDir;

before(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'session-end-test-'));
});

after(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

/**
 * Build a diary index.md with a given number of `| pending |` rows.
 */
function makeDiaryIndex(pendingCount) {
  const header = '# Diary Index\n\n| Date | Title | Status |\n|------|-------|--------|\n';
  const rows = Array.from({ length: pendingCount }, (_, i) =>
    `| 2026-02-${String(i + 1).padStart(2, '0')} | Entry ${i + 1} | pending |`,
  ).join('\n');
  return header + rows + '\n';
}

describe('session-end', () => {
  // --- No diary directory at all ---

  it('exits 0 silently when CLAUDE_PROJECT_DIR has no ai/diary/index.md', () => {
    const emptyDir = mkdtempSync(join(tmpdir(), 'session-end-empty-'));
    try {
      const result = runHook('session-end.mjs', makeStopInput(), {
        CLAUDE_PROJECT_DIR: emptyDir,
      });
      strictEqual(result.exitCode, 0);
      strictEqual(result.raw, '');
    } finally {
      rmSync(emptyDir, { recursive: true, force: true });
    }
  });

  // --- 0 pending entries ---

  it('exits 0 silently when diary has 0 pending entries', () => {
    const dir = mkdtempSync(join(tmpdir(), 'session-end-zero-'));
    try {
      mkdirSync(join(dir, 'ai', 'diary'), { recursive: true });
      writeFileSync(join(dir, 'ai', 'diary', 'index.md'), makeDiaryIndex(0));

      const result = runHook('session-end.mjs', makeStopInput(), {
        CLAUDE_PROJECT_DIR: dir,
      });
      strictEqual(result.exitCode, 0);
      strictEqual(result.raw, '');
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  // --- Exactly 5 pending entries (boundary: must be silent) ---

  it('exits 0 silently when diary has exactly 5 pending entries', () => {
    const dir = mkdtempSync(join(tmpdir(), 'session-end-five-'));
    try {
      mkdirSync(join(dir, 'ai', 'diary'), { recursive: true });
      writeFileSync(join(dir, 'ai', 'diary', 'index.md'), makeDiaryIndex(5));

      const result = runHook('session-end.mjs', makeStopInput(), {
        CLAUDE_PROJECT_DIR: dir,
      });
      strictEqual(result.exitCode, 0);
      strictEqual(result.raw, '');
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  // --- 6 pending entries (boundary: must output reminder) ---

  it('outputs approve + systemMessage when diary has 6 pending entries', () => {
    const dir = mkdtempSync(join(tmpdir(), 'session-end-six-'));
    try {
      mkdirSync(join(dir, 'ai', 'diary'), { recursive: true });
      writeFileSync(join(dir, 'ai', 'diary', 'index.md'), makeDiaryIndex(6));

      const result = runHook('session-end.mjs', makeStopInput(), {
        CLAUDE_PROJECT_DIR: dir,
      });
      strictEqual(result.exitCode, 0);
      strictEqual(result.stdout?.decision, 'approve');
      ok(result.stdout?.systemMessage, 'systemMessage should be present');
      ok(
        result.stdout.systemMessage.includes('6'),
        'systemMessage should mention the pending count',
      );
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  // --- Many pending entries ---

  it('outputs approve + systemMessage with correct count for 10 pending entries', () => {
    const dir = mkdtempSync(join(tmpdir(), 'session-end-ten-'));
    try {
      mkdirSync(join(dir, 'ai', 'diary'), { recursive: true });
      writeFileSync(join(dir, 'ai', 'diary', 'index.md'), makeDiaryIndex(10));

      const result = runHook('session-end.mjs', makeStopInput(), {
        CLAUDE_PROJECT_DIR: dir,
      });
      strictEqual(result.exitCode, 0);
      strictEqual(result.stdout?.decision, 'approve');
      ok(result.stdout?.systemMessage?.includes('10'), 'count 10 should appear in message');
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  // --- Never blocks session end (decision is always 'approve' when output is present) ---

  it('decision is never "block" even with many pending entries', () => {
    const dir = mkdtempSync(join(tmpdir(), 'session-end-noblock-'));
    try {
      mkdirSync(join(dir, 'ai', 'diary'), { recursive: true });
      writeFileSync(join(dir, 'ai', 'diary', 'index.md'), makeDiaryIndex(20));

      const result = runHook('session-end.mjs', makeStopInput(), {
        CLAUDE_PROJECT_DIR: dir,
      });
      strictEqual(result.exitCode, 0);
      // If output present, decision must be approve
      if (result.stdout) {
        strictEqual(result.stdout.decision, 'approve');
      }
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  // --- systemMessage contains /reflect hint ---

  it('systemMessage mentions /reflect', () => {
    const dir = mkdtempSync(join(tmpdir(), 'session-end-reflect-'));
    try {
      mkdirSync(join(dir, 'ai', 'diary'), { recursive: true });
      writeFileSync(join(dir, 'ai', 'diary', 'index.md'), makeDiaryIndex(7));

      const result = runHook('session-end.mjs', makeStopInput(), {
        CLAUDE_PROJECT_DIR: dir,
      });
      strictEqual(result.exitCode, 0);
      ok(
        result.stdout?.systemMessage?.includes('/reflect'),
        'reminder should suggest /reflect',
      );
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  // --- Fail-safe: bad input ---

  it('exits 0 on empty input (fail-safe)', () => {
    const result = runHook('session-end.mjs', {});
    strictEqual(result.exitCode, 0);
  });
});
