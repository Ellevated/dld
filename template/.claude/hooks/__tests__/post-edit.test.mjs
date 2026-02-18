/**
 * Tests for post-edit.mjs
 *
 * Verifies tool filter, file-type filter, existence check, and fail-safe behaviour.
 * Ruff is NOT required — tests use non-existent or non-Python files.
 */

import { describe, it, before, after } from 'node:test';
import { strictEqual } from 'node:assert';
import { mkdtempSync, rmSync, writeFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { runHook, makePostToolInput } from './helpers.mjs';

let tmpDir;

before(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'post-edit-test-'));
});

after(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

describe('post-edit', () => {
  // --- Tool filter: only Write/Edit/MultiEdit are processed ---

  it('ignores Read tool — silent continue (exit 0, no output)', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Read', { file_path: '/tmp/something.py' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  it('ignores Bash tool — silent continue', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Bash', { command: 'echo hi' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  it('ignores unknown tool name — silent continue', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('SomeTool', { file_path: '/tmp/foo.py' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  // --- File type filter: only .py files trigger ruff ---

  it('ignores .js file edited with Edit — silent continue', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Edit', { file_path: '/tmp/app.js' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  it('ignores .md file written with Write — silent continue', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Write', { file_path: '/tmp/README.md' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  it('ignores .ts file — silent continue', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Write', { file_path: '/tmp/index.ts' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  // --- File existence check ---

  it('python file that does NOT exist — silent continue', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Edit', { file_path: '/tmp/nonexistent_file_xyz.py' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });

  // --- Python file that exists but is outside project dir ---

  it('python file outside CLAUDE_PROJECT_DIR — silent continue', () => {
    // Write a real .py file in /tmp (outside the default test project dir)
    const pyFile = join(tmpdir(), 'outside_project_test.py');
    writeFileSync(pyFile, 'x = 1\n');

    // CLAUDE_PROJECT_DIR is set to a deep subdirectory so /tmp/outside... is outside
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Edit', { file_path: pyFile }),
      { CLAUDE_PROJECT_DIR: '/home/user/myproject' },
    );
    strictEqual(result.exitCode, 0);
    // If ruff is installed it may run, but the project boundary check should prevent it
    // for paths truly outside the project dir. Either way must exit 0.
  });

  // --- Python file inside project dir (ruff may or may not be installed) ---

  it('python file inside project dir — exits 0 (ruff optional)', () => {
    const pyFile = join(tmpDir, 'module.py');
    writeFileSync(pyFile, 'x=1\n');

    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('Edit', { file_path: pyFile }),
      { CLAUDE_PROJECT_DIR: tmpDir },
    );
    // Must exit 0 regardless of whether ruff is installed
    strictEqual(result.exitCode, 0);
  });

  // --- Fail-safe: malformed input ---

  it('exits 0 on empty/malformed input (fail-safe)', () => {
    const result = runHook('post-edit.mjs', {});
    strictEqual(result.exitCode, 0);
  });

  // --- MultiEdit is also processed (same code path) ---

  it('MultiEdit with non-python file — silent continue', () => {
    const result = runHook(
      'post-edit.mjs',
      makePostToolInput('MultiEdit', { file_path: '/tmp/config.yaml' }),
    );
    strictEqual(result.exitCode, 0);
    strictEqual(result.raw, '');
  });
});
