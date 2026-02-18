/**
 * Tests for hook configuration system.
 *
 * Tests:
 * 1. deepMerge — object/array merge semantics
 * 2. loadConfig — default loading, user overrides, fail-safe
 * 3. Integration — hooks use config values
 *
 * Run: node --test __tests__/config.test.mjs
 */

import { describe, it, beforeEach } from 'node:test';
import { strictEqual, deepStrictEqual, ok } from 'node:assert';
import { writeFileSync, mkdtempSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

import { deepMerge, loadConfig, resetConfigCache } from '../utils.mjs';
import { runHook, makePreToolInput } from './helpers.mjs';

// ---------------------------------------------------------------------------
// deepMerge
// ---------------------------------------------------------------------------

describe('deepMerge', () => {
  it('merges flat objects', () => {
    const result = deepMerge({ a: 1, b: 2 }, { b: 3, c: 4 });
    deepStrictEqual(result, { a: 1, b: 3, c: 4 });
  });

  it('recursively merges nested objects', () => {
    const target = { preEdit: { maxLocCode: 400, maxLocTest: 600 } };
    const source = { preEdit: { maxLocCode: 500 } };
    const result = deepMerge(target, source);
    deepStrictEqual(result, { preEdit: { maxLocCode: 500, maxLocTest: 600 } });
  });

  it('replaces arrays (not concatenates)', () => {
    const target = { items: [1, 2, 3] };
    const source = { items: [4, 5] };
    const result = deepMerge(target, source);
    deepStrictEqual(result, { items: [4, 5] });
  });

  it('preserves target keys not in source', () => {
    const target = { a: 1, b: 2, c: 3 };
    const source = { b: 20 };
    const result = deepMerge(target, source);
    deepStrictEqual(result, { a: 1, b: 20, c: 3 });
  });

  it('handles empty source', () => {
    const target = { a: 1 };
    const result = deepMerge(target, {});
    deepStrictEqual(result, { a: 1 });
  });

  it('handles empty target', () => {
    const source = { a: 1 };
    const result = deepMerge({}, source);
    deepStrictEqual(result, { a: 1 });
  });

  it('does not mutate target', () => {
    const target = { a: { b: 1 } };
    const source = { a: { b: 2 } };
    deepMerge(target, source);
    strictEqual(target.a.b, 1);
  });

  it('treats RegExp as leaf (not recursed)', () => {
    const target = { pattern: /foo/i };
    const source = { pattern: /bar/g };
    const result = deepMerge(target, source);
    strictEqual(result.pattern.source, 'bar');
    strictEqual(result.pattern.flags, 'g');
  });

  it('replaces object with array', () => {
    const target = { a: { nested: true } };
    const source = { a: [1, 2] };
    const result = deepMerge(target, source);
    deepStrictEqual(result.a, [1, 2]);
  });

  it('replaces array with object', () => {
    const target = { a: [1, 2] };
    const source = { a: { nested: true } };
    const result = deepMerge(target, source);
    deepStrictEqual(result.a, { nested: true });
  });

  it('handles deeply nested merge (3 levels)', () => {
    const target = { l1: { l2: { l3: 'old', keep: true } } };
    const source = { l1: { l2: { l3: 'new' } } };
    const result = deepMerge(target, source);
    deepStrictEqual(result, { l1: { l2: { l3: 'new', keep: true } } });
  });
});

// ---------------------------------------------------------------------------
// loadConfig
// ---------------------------------------------------------------------------

describe('loadConfig', () => {
  beforeEach(() => {
    resetConfigCache();
  });

  it('loads default config successfully', async () => {
    const config = await loadConfig();
    ok(config.preBash, 'config should have preBash section');
    ok(config.preEdit, 'config should have preEdit section');
    ok(config.utils, 'config should have utils section');
    ok(config.promptGuard, 'config should have promptGuard section');
  });

  it('default config has blockedPatterns array', async () => {
    const config = await loadConfig();
    ok(Array.isArray(config.preBash.blockedPatterns), 'blockedPatterns should be array');
    ok(config.preBash.blockedPatterns.length >= 4, 'should have at least 4 blocked patterns');
  });

  it('default config has correct LOC limits', async () => {
    const config = await loadConfig();
    strictEqual(config.preEdit.maxLocCode, 400);
    strictEqual(config.preEdit.maxLocTest, 600);
  });

  it('default config has protectedPaths', async () => {
    const config = await loadConfig();
    ok(config.preEdit.protectedPaths.includes('tests/contracts/'));
    ok(config.preEdit.protectedPaths.includes('tests/regression/'));
  });

  it('default config has alwaysAllowedPatterns', async () => {
    const config = await loadConfig();
    ok(config.utils.alwaysAllowedPatterns.includes('ai/backlog.md'));
    ok(config.utils.alwaysAllowedPatterns.includes('.claude/**'));
  });

  it('default config has mergePatterns', async () => {
    const config = await loadConfig();
    ok(Array.isArray(config.preBash.mergePatterns));
    ok(config.preBash.mergePatterns.length >= 1);
  });

  it('default config has promptGuard patterns', async () => {
    const config = await loadConfig();
    ok(Array.isArray(config.promptGuard.complexityPatterns));
    ok(Array.isArray(config.promptGuard.skillIndicators));
  });

  it('caches config after first load', async () => {
    const config1 = await loadConfig();
    const config2 = await loadConfig();
    strictEqual(config1, config2, 'should return same object reference');
  });

  it('resetConfigCache allows reloading', async () => {
    await loadConfig();
    resetConfigCache();
    // After reset, loadConfig should work again without errors
    const config = await loadConfig();
    ok(config.preBash, 'reloaded config should have preBash');
  });
});

// ---------------------------------------------------------------------------
// Integration: pre-bash uses config
// ---------------------------------------------------------------------------

describe('pre-bash uses config', () => {
  it('blocks git push main (from config)', () => {
    const input = makePreToolInput('Bash', {
      command: 'git push origin main',
    });
    const result = runHook('pre-bash.mjs', input);
    ok(
      result.stdout?.hookSpecificOutput?.permissionDecision === 'deny',
      `expected deny, got: ${JSON.stringify(result.stdout)}`,
    );
  });

  it('allows safe commands (from config)', () => {
    const input = makePreToolInput('Bash', {
      command: 'git status',
    });
    const result = runHook('pre-bash.mjs', input);
    strictEqual(result.stdout, null, 'safe command should be allowed (null output)');
  });

  it('asks for merge without --ff-only (from config)', () => {
    const input = makePreToolInput('Bash', {
      command: 'git merge feature/foo',
    });
    const result = runHook('pre-bash.mjs', input);
    strictEqual(
      result.stdout?.hookSpecificOutput?.permissionDecision,
      'ask',
      'merge without --ff-only should ask',
    );
  });
});

// ---------------------------------------------------------------------------
// Integration: config defaults match hardcoded values
// ---------------------------------------------------------------------------

describe('config defaults match original behavior', () => {
  it('blockedPatterns[0] blocks push to main', async () => {
    const config = await loadConfig();
    resetConfigCache();
    const [matcher] = config.preBash.blockedPatterns[0];
    ok(matcher.test('git push origin main'), 'should match push to main');
    ok(!matcher.test('git push origin develop'), 'should not match push to develop');
  });

  it('blockedPatterns[1] is a function (isDestructiveClean)', async () => {
    const config = await loadConfig();
    resetConfigCache();
    const [matcher] = config.preBash.blockedPatterns[1];
    strictEqual(typeof matcher, 'function', 'second pattern should be a function');
    ok(matcher('git clean -fd'), 'should match git clean -fd');
    ok(!matcher('git clean -fdn'), 'should not match dry-run');
  });

  it('blockedPatterns[2] blocks git reset --hard', async () => {
    const config = await loadConfig();
    resetConfigCache();
    const [matcher] = config.preBash.blockedPatterns[2];
    ok(matcher.test('git reset --hard'), 'should match git reset --hard');
    ok(!matcher.test('git reset --soft HEAD~1'), 'should not match soft reset');
  });

  it('mergePatterns[0] matches git merge', async () => {
    const config = await loadConfig();
    resetConfigCache();
    const [matcher] = config.preBash.mergePatterns[0];
    ok(matcher.test('git merge feature/foo'), 'should match git merge');
    ok(!matcher.test('git merge-base foo bar'), 'should not match merge-base');
  });

  it('warnThreshold is 87.5%', async () => {
    const config = await loadConfig();
    resetConfigCache();
    strictEqual(config.preEdit.warnThreshold, 7 / 8);
  });
});
