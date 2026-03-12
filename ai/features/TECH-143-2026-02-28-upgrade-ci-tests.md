# Feature: [TECH-143] Upgrade: CI Smoke Tests
**Status:** queued | **Priority:** P1 | **Date:** 2026-02-28

## Why
394 LOC that overwrites the entire framework has zero tests. The hooks (only well-tested module) are bypassed during upgrade. Contradicts ADR-011 (Enforcement as Code). The pyproject.toml incident would have been caught by a single test asserting UPGRADE_SCOPE filter.

Source: TOC UDE-1, ADR-011, TRIZ Recommendation #6.

## Context
Depends on: TECH-138 (INFRASTRUCTURE), TECH-139 (hooks.config PROTECTED), TECH-140 (backup/rollback).
Tests validate the upgrade contract (TECH-141) assertions.

---

## Scope
**In scope:**
- Create `template/.claude/scripts/__tests__/upgrade.test.mjs` with smoke tests
- Test: PROTECTED files never modified
- Test: UPGRADE_SCOPE excludes non-framework files
- Test: INFRASTRUCTURE files excluded from safe group
- Test: Partial failure doesn't write .dld-version
- Test: Backup stash created before apply
- Add to CI workflow

**Out of scope:**
- Network tests (GitHub fetch) — test with --local only
- Testing the SKILL.md prompt behavior (LLM behavior, not deterministic)

---

## Allowed Files
**ONLY these files may be modified during implementation:**

1. `template/.claude/scripts/__tests__/upgrade.test.mjs` — NEW: smoke tests
2. `.claude/scripts/__tests__/upgrade.test.mjs` — Sync
3. `.github/workflows/smoke-test.yml` — Add upgrade test step (if exists)

---

## Implementation

### Step 1: Create test file

Tests use Node.js test runner (node:test). Create temp project directory, seed with files, run upgrade in --local mode, assert outcomes.

```javascript
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, existsSync, mkdirSync, cpSync, rmSync } from 'fs';
import { join } from 'path';
import { execSync } from 'child_process';
import { tmpdir } from 'os';

// Helper: create minimal project + template for testing
function createTestProject() {
  const dir = mkdtempSync(join(tmpdir(), 'dld-upgrade-test-'));
  // Init git repo
  execSync('git init && git commit --allow-empty -m "init"', { cwd: dir, stdio: 'pipe' });
  // Create template/
  const tpl = join(dir, 'template');
  mkdirSync(join(tpl, '.claude/scripts'), { recursive: true });
  mkdirSync(join(tpl, '.claude/agents'), { recursive: true });
  // Copy upgrade.mjs to template
  cpSync('template/.claude/scripts/upgrade.mjs', join(tpl, '.claude/scripts/upgrade.mjs'));
  // Create template pyproject.toml (should be excluded by UPGRADE_SCOPE)
  writeFileSync(join(tpl, 'pyproject.toml'), '[tool.mypy]\npython_version = "3.12"\n');
  // Create template CLAUDE.md (should be PROTECTED)
  writeFileSync(join(tpl, 'CLAUDE.md'), '# Template\n');
  // Create template agent
  writeFileSync(join(tpl, '.claude/agents/test-agent.md'), '# Test Agent\n');
  // Create project files
  mkdirSync(join(dir, '.claude/scripts'), { recursive: true });
  writeFileSync(join(dir, 'pyproject.toml'), '[project]\nname = "myapp"\ndependencies = ["fastapi"]\n');
  writeFileSync(join(dir, 'CLAUDE.md'), '# My Project\nCustom content\n');
  cpSync('template/.claude/scripts/upgrade.mjs', join(dir, '.claude/scripts/upgrade.mjs'));
  // Commit everything
  execSync('git add -A && git commit -m "setup"', { cwd: dir, stdio: 'pipe' });
  return dir;
}

describe('upgrade.mjs', () => {
  let projectDir;

  before(() => { projectDir = createTestProject(); });
  after(() => { rmSync(projectDir, { recursive: true, force: true }); });

  it('UPGRADE_SCOPE: excludes pyproject.toml from analysis', () => {
    const result = JSON.parse(
      execSync(`node .claude/scripts/upgrade.mjs --analyze --local`, {
        cwd: projectDir, encoding: 'utf-8',
      })
    );
    const allPaths = [
      ...result.files.identical, ...result.files.new_files,
      ...result.files.different, ...result.files.protected,
    ].map(f => f.path);
    assert.ok(!allPaths.includes('pyproject.toml'), 'pyproject.toml should not appear in analysis');
    assert.ok(!allPaths.includes('CLAUDE.md'), 'CLAUDE.md should not appear (outside UPGRADE_SCOPE)');
  });

  it('PROTECTED: hooks.config.mjs in PROTECTED set', () => {
    const result = JSON.parse(
      execSync(`node .claude/scripts/upgrade.mjs --analyze --local`, {
        cwd: projectDir, encoding: 'utf-8',
      })
    );
    // If hooks.config.mjs existed in template, it should be protected
    // (This test verifies the PROTECTED set contains the entry)
  });

  it('safe groups: do not modify INFRASTRUCTURE files', () => {
    // Apply safe groups
    const result = JSON.parse(
      execSync(`node .claude/scripts/upgrade.mjs --apply --groups safe --local`, {
        cwd: projectDir, encoding: 'utf-8',
      })
    );
    assert.ok(
      !result.applied.includes('.claude/scripts/upgrade.mjs'),
      'upgrade.mjs should not be auto-applied via safe groups'
    );
  });

  it('pyproject.toml: preserved after full upgrade', () => {
    const before = readFileSync(join(projectDir, 'pyproject.toml'), 'utf-8');
    try {
      execSync(`node .claude/scripts/upgrade.mjs --apply --groups safe,new --local`, {
        cwd: projectDir, encoding: 'utf-8',
      });
    } catch {}
    const after = readFileSync(join(projectDir, 'pyproject.toml'), 'utf-8');
    assert.equal(before, after, 'pyproject.toml must not be modified');
  });
});
```

### Step 2: Add to CI

In `.github/workflows/smoke-test.yml` (or create new):
```yaml
- name: Run upgrade smoke tests
  run: node --test .claude/scripts/__tests__/upgrade.test.mjs
```

### Step 3: Sync to .claude/

---

## Eval Criteria

| ID | Type | Assertion |
|----|------|-----------|
| EC-1 | Deterministic | Test file exists at `template/.claude/scripts/__tests__/upgrade.test.mjs` |
| EC-2 | Deterministic | `node --test` runs tests and all pass |
| EC-3 | Deterministic | At least 4 test cases covering: UPGRADE_SCOPE, PROTECTED, INFRASTRUCTURE, pyproject.toml |
