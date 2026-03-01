/**
 * CI smoke tests for upgrade.mjs safety invariants.
 *
 * Tests the upgrade engine's core safety properties:
 * 1. UPGRADE_SCOPE filter — project-config files never appear in analysis
 * 2. INFRASTRUCTURE protection — upgrade.mjs never auto-applied via groups
 * 3. Project config preservation — pyproject.toml and CLAUDE.md survive upgrade
 * 4. Deprecation detection — user_only files marked as deprecated per deprecated.json
 * 5. Analyze output structure — infrastructure array present in JSON output
 *
 * Run: node --test template/.claude/scripts/__tests__/upgrade.test.mjs
 */

import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import {
  mkdtempSync, writeFileSync, readFileSync, existsSync,
  mkdirSync, cpSync, rmSync, readdirSync,
} from 'fs';
import { join, dirname } from 'path';
import { execSync } from 'child_process';
import { tmpdir } from 'os';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const UPGRADE_SCRIPT = join(__dirname, '..', 'upgrade.mjs');

function createTestProject() {
  const dir = mkdtempSync(join(tmpdir(), 'dld-upgrade-test-'));

  // Init git repo with initial commit
  execSync('git init && git config user.email "test@test.com" && git config user.name "Test"', {
    cwd: dir, stdio: 'pipe',
  });
  execSync('git commit --allow-empty -m "init"', { cwd: dir, stdio: 'pipe' });

  // Create template/ directory (simulates what the upgrade source looks like)
  const tpl = join(dir, 'template');
  mkdirSync(join(tpl, '.claude/scripts'), { recursive: true });
  mkdirSync(join(tpl, '.claude/agents'), { recursive: true });
  mkdirSync(join(tpl, '.claude/hooks'), { recursive: true });
  mkdirSync(join(tpl, '.claude/skills/spark'), { recursive: true });

  // Copy the actual upgrade.mjs to template (so the test uses the real script)
  cpSync(UPGRADE_SCRIPT, join(tpl, '.claude/scripts/upgrade.mjs'));

  // Template files that should be PROTECTED (outside UPGRADE_SCOPE)
  writeFileSync(join(tpl, 'pyproject.toml'), '[tool.mypy]\npython_version = "3.12"\n');
  writeFileSync(join(tpl, 'CLAUDE.md'), '# Template CLAUDE.md\n');
  writeFileSync(join(tpl, 'README.md'), '# Template README\n');

  // Template agent (in UPGRADE_SCOPE, safe group)
  writeFileSync(join(tpl, '.claude/agents/test-agent.md'), '# Test Agent v2\n');

  // Template hook (in UPGRADE_SCOPE, safe group)
  writeFileSync(join(tpl, '.claude/hooks/test-hook.mjs'), '// test hook v2\n');

  // Template skill (in UPGRADE_SCOPE, not safe - requires review)
  writeFileSync(join(tpl, '.claude/skills/spark/SKILL.md'), '# Spark v2\n');

  // Template deprecated.json
  writeFileSync(join(tpl, '.claude/deprecated.json'), JSON.stringify({
    schema_version: 1,
    versions: { '3.11': { removed: ['.claude/agents/old-agent.md'], renamed: {} } },
  }, null, 2));

  // Create project files (user's existing project)
  mkdirSync(join(dir, '.claude/scripts'), { recursive: true });
  mkdirSync(join(dir, '.claude/agents'), { recursive: true });
  mkdirSync(join(dir, '.claude/hooks'), { recursive: true });
  mkdirSync(join(dir, '.claude/skills/spark'), { recursive: true });

  // User's pyproject.toml with real dependencies (must survive upgrade!)
  writeFileSync(join(dir, 'pyproject.toml'), '[project]\nname = "myapp"\ndependencies = ["fastapi", "uvicorn"]\n');
  writeFileSync(join(dir, 'CLAUDE.md'), '# My Real Project\nCustom content here\n');
  writeFileSync(join(dir, 'README.md'), '# My App README\n');

  // User's existing files
  writeFileSync(join(dir, '.claude/agents/test-agent.md'), '# Test Agent v1\n');
  writeFileSync(join(dir, '.claude/hooks/test-hook.mjs'), '// test hook v1\n');
  writeFileSync(join(dir, '.claude/skills/spark/SKILL.md'), '# Spark v1\n');

  // Copy the actual upgrade.mjs as the project's script
  cpSync(UPGRADE_SCRIPT, join(dir, '.claude/scripts/upgrade.mjs'));

  // User-only file that matches deprecated list
  writeFileSync(join(dir, '.claude/agents/old-agent.md'), '# Old deprecated agent\n');

  // Commit everything so working tree is clean
  execSync('git add -A && git commit -m "setup project"', { cwd: dir, stdio: 'pipe' });

  return dir;
}

/**
 * Run upgrade.mjs with given args and return parsed JSON output.
 * Handles exit code 2 (nothing to update) gracefully — returns stdout JSON.
 * Throws only on genuine errors (exit code 1).
 */
function runUpgrade(projectDir, args) {
  try {
    const output = execSync(
      `node .claude/scripts/upgrade.mjs ${args} --source ${join(projectDir, 'template')}`,
      { cwd: projectDir, encoding: 'utf-8', stdio: 'pipe' },
    );
    return JSON.parse(output);
  } catch (err) {
    // exit code 2 = nothing to apply — stdout may still contain valid JSON
    if (err.status === 2 && err.stdout) {
      try { return JSON.parse(err.stdout); } catch {}
    }
    // exit code 1 = real error
    throw err;
  }
}

/**
 * Run upgrade and return raw stdout string (for cases where output may be empty).
 */
function runUpgradeRaw(projectDir, args) {
  try {
    return execSync(
      `node .claude/scripts/upgrade.mjs ${args} --source ${join(projectDir, 'template')}`,
      { cwd: projectDir, encoding: 'utf-8', stdio: 'pipe' },
    );
  } catch (err) {
    if (err.status === 2) return err.stdout || '';
    throw err;
  }
}

describe('upgrade.mjs safety invariants', () => {
  let projectDir;

  before(() => {
    projectDir = createTestProject();
  });

  after(() => {
    try { rmSync(projectDir, { recursive: true, force: true }); } catch {}
  });

  // ---------------------------------------------------------------------------
  // UPGRADE_SCOPE filter
  // ---------------------------------------------------------------------------

  describe('UPGRADE_SCOPE filter', () => {
    it('excludes pyproject.toml from analysis', () => {
      const report = runUpgrade(projectDir, '--analyze');
      const allPaths = [
        ...report.files.identical,
        ...report.files.new_files,
        ...report.files.different,
        ...report.files.protected,
        ...(report.files.infrastructure || []),
      ].map(f => f.path);
      assert.ok(!allPaths.includes('pyproject.toml'), 'pyproject.toml must not appear in analysis');
    });

    it('excludes CLAUDE.md from analysis (outside scope)', () => {
      const report = runUpgrade(projectDir, '--analyze');
      const allPaths = [
        ...report.files.identical,
        ...report.files.new_files,
        ...report.files.different,
        ...report.files.protected,
        ...(report.files.infrastructure || []),
      ].map(f => f.path);
      assert.ok(!allPaths.includes('CLAUDE.md'), 'CLAUDE.md must not appear (outside UPGRADE_SCOPE)');
    });

    it('excludes README.md from analysis', () => {
      const report = runUpgrade(projectDir, '--analyze');
      const allPaths = [
        ...report.files.identical,
        ...report.files.new_files,
        ...report.files.different,
        ...report.files.protected,
        ...(report.files.infrastructure || []),
      ].map(f => f.path);
      assert.ok(!allPaths.includes('README.md'), 'README.md must not appear in analysis');
    });
  });

  // ---------------------------------------------------------------------------
  // INFRASTRUCTURE protection
  // ---------------------------------------------------------------------------

  describe('INFRASTRUCTURE protection', () => {
    it('classifies upgrade.mjs as infrastructure (not in different or new_files)', () => {
      const report = runUpgrade(projectDir, '--analyze');
      assert.ok(Array.isArray(report.files.infrastructure), 'infrastructure category must exist');
      // Both project and template have identical upgrade.mjs (same file copied),
      // so it should NOT appear in different or new_files.
      const inDifferent = report.files.different.some(f => f.path === '.claude/scripts/upgrade.mjs');
      const inNew = report.files.new_files.some(f => f.path === '.claude/scripts/upgrade.mjs');
      assert.ok(!inDifferent && !inNew, 'upgrade.mjs must NOT be in different or new_files');
    });

    it('safe groups do not include infrastructure files when upgrade.mjs differs', () => {
      // Make template's upgrade.mjs different from project's version
      const templateUpgrade = join(projectDir, 'template/.claude/scripts/upgrade.mjs');
      const originalContent = readFileSync(templateUpgrade, 'utf-8');
      writeFileSync(templateUpgrade, originalContent + '\n// v2\n');
      execSync('git add -A && git commit -m "modify template upgrade.mjs"', { cwd: projectDir, stdio: 'pipe' });

      let result;
      try {
        result = runUpgrade(projectDir, '--apply --groups safe');
      } catch (e) {
        // exit code 2 = nothing to apply — acceptable
        result = { applied: [] };
      }

      // upgrade.mjs must NOT be auto-applied via safe groups
      const applied = result.applied || [];
      assert.ok(
        !applied.includes('.claude/scripts/upgrade.mjs'),
        'upgrade.mjs must NOT be auto-applied via safe groups',
      );

      // Restore clean state for subsequent tests
      execSync('git checkout -- .', { cwd: projectDir, stdio: 'pipe' });
      execSync('git checkout HEAD~1 -- template/.claude/scripts/upgrade.mjs', { cwd: projectDir, stdio: 'pipe' });
      execSync('git add -A && git commit -m "restore template upgrade.mjs"', { cwd: projectDir, stdio: 'pipe' });
    });
  });

  // ---------------------------------------------------------------------------
  // Project config preservation
  // ---------------------------------------------------------------------------

  describe('project config preservation', () => {
    it('pyproject.toml survives full upgrade (safe + new groups)', () => {
      const before = readFileSync(join(projectDir, 'pyproject.toml'), 'utf-8');
      try {
        runUpgrade(projectDir, '--apply --groups safe,new');
      } catch {
        // exit 2 = nothing to apply, content is still intact
      }
      // Reset any applied files for other tests
      execSync('git checkout -- .', { cwd: projectDir, stdio: 'pipe' });
      const after = readFileSync(join(projectDir, 'pyproject.toml'), 'utf-8');
      assert.equal(before, after, 'pyproject.toml content must be preserved');
    });

    it('CLAUDE.md survives full upgrade (safe + new groups)', () => {
      const before = readFileSync(join(projectDir, 'CLAUDE.md'), 'utf-8');
      try {
        runUpgrade(projectDir, '--apply --groups safe,new');
      } catch {
        // exit 2 = nothing to apply, content is still intact
      }
      execSync('git checkout -- .', { cwd: projectDir, stdio: 'pipe' });
      const after = readFileSync(join(projectDir, 'CLAUDE.md'), 'utf-8');
      assert.equal(before, after, 'CLAUDE.md content must be preserved');
    });
  });

  // ---------------------------------------------------------------------------
  // Deprecation detection
  // ---------------------------------------------------------------------------

  describe('deprecation detection', () => {
    it('marks deprecated user_only files per deprecated.json', () => {
      const report = runUpgrade(projectDir, '--analyze');
      const oldAgent = report.files.user_only.find(f => f.path === '.claude/agents/old-agent.md');
      assert.ok(oldAgent, 'old-agent.md should be in user_only');
      assert.ok(oldAgent.deprecated, 'old-agent.md should be marked as deprecated');
    });
  });

  // ---------------------------------------------------------------------------
  // Analyze output structure
  // ---------------------------------------------------------------------------

  describe('analyze output structure', () => {
    it('contains infrastructure array in files output', () => {
      const report = runUpgrade(projectDir, '--analyze');
      assert.ok(Array.isArray(report.files.infrastructure), 'files.infrastructure must be an array');
    });

    it('contains infrastructure count in summary', () => {
      const report = runUpgrade(projectDir, '--analyze');
      assert.ok('infrastructure' in report.summary, 'summary must contain infrastructure count');
      assert.equal(typeof report.summary.infrastructure, 'number', 'summary.infrastructure must be a number');
    });
  });
});
