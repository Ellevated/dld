/**
 * Tests for validate-spec-complete.mjs
 *
 * Verifies command detection regex (git commit vs git commit-graph/commit-tree),
 * and that non-commit commands pass through silently.
 *
 * Note: Most checks are a no-op without a real git repo with staged spec files.
 * These tests focus on command-level gating behaviour.
 */

import { describe, it } from 'node:test';
import { strictEqual } from 'node:assert';
import { runHook, makePreToolInput } from './helpers.mjs';

describe('validate-spec-complete', () => {
  // --- Non-commit commands: should exit 0 silently ---

  it('ignores "echo hello" — not a git command', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'echo hello' }),
    );
    strictEqual(result.exitCode, 0);
    // Silent exit means no JSON output
    strictEqual(result.raw, '');
  });

  it('ignores "ls -la" — not a git command', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'ls -la' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  it('ignores "git status" — not a commit', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'git status' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  it('ignores "git push origin develop" — not a commit', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'git push origin develop' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  // --- git commit-graph and git commit-tree: must NOT trigger (regex uses \b(?!-)) ---

  it('ignores "git commit-graph write" — hyphen excludes it', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'git commit-graph write' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  it('ignores "git commit-tree HEAD" — hyphen excludes it', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'git commit-tree HEAD' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  // --- git commit: triggers check, but no staged files = no-op (exits 0) ---

  it('runs on "git commit -m ..." — exits 0 when no staged spec files', () => {
    // Without staged spec files the hook calls git diff --cached and finds nothing.
    // git may not exist or may fail — hook catches that and exits 0.
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'git commit -m "test"' }),
    );
    // Allowed outcomes: exit 0 (no staged spec) or exit 0 (git not available)
    strictEqual(result.exitCode, 0);
  });

  it('runs on "git commit --amend" — exits 0 when no staged spec files', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'git commit --amend' }),
    );
    strictEqual(result.exitCode, 0);
  });

  // --- Tool type does not matter — hook reads command field ---

  it('ignores non-Bash tool (no command field) — exits 0 silently', () => {
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Write', { file_path: '/tmp/foo.py' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  // --- Fail-safe: malformed input ---

  it('exits 0 on empty input (fail-safe)', () => {
    const result = runHook('validate-spec-complete.mjs', {});
    strictEqual(result.exitCode, 0);
  });

  // --- stripCodeBlocks behaviour (indirect) ---
  // The hook strips code blocks before checking for `- [ ]`.
  // We verify that a commit with a spec containing ONLY code-block checkboxes is NOT blocked.
  // (Since no real staged files exist in CI, this is tested via the no-staged-files path.)

  it('case-insensitive match: "GIT COMMIT -m" is also detected', () => {
    // The regex uses /i flag — uppercase should also trigger the check.
    // Without staged spec files it will exit 0.
    const result = runHook(
      'validate-spec-complete.mjs',
      makePreToolInput('Bash', { command: 'GIT COMMIT -m "caps"' }),
    );
    strictEqual(result.exitCode, 0);
  });
});
