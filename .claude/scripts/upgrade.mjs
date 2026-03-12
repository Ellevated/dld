#!/usr/bin/env node
// DLD Upgrade Script — deterministic template upgrade engine.
// Modes: --analyze [--local|--latest] | --apply --groups X | --apply --files X | --diff --file X | --cleanup
// Exit codes: 0=success, 1=error, 2=nothing to update

import { execSync, execFileSync } from 'child_process';
import { createHash } from 'crypto';
import { existsSync, readFileSync, writeFileSync, mkdirSync, cpSync, rmSync, readdirSync } from 'fs';
import { join, relative, dirname } from 'path';

const REPO_URL = 'https://github.com/Ellevated/dld.git';
const TEMPLATE_DIR = 'template';
const VERSION_FILE = '.dld-version';

// Project-config files that upgrade must NEVER touch.
const PROTECTED = new Set([
  'CLAUDE.md', 'README.md', '.gitignore', 'pyproject.toml', 'package.json',
  'Cargo.toml', 'go.mod', 'requirements.txt',
  '.claude/rules/localization.md', '.claude/rules/template-sync.md',
  '.claude/CUSTOMIZATIONS.md', '.claude/settings.local.json',
  '.claude/hooks/hooks.config.local.mjs', '.claude/hooks/hooks.config.mjs',
]);

// Files that always require manual review (never auto-apply)
const ALWAYS_ASK = new Set(['.claude/settings.json']);

// Infrastructure files: engine + hook runner. Never auto-apply via groups.
// Only applied when explicitly named via --files.
const INFRASTRUCTURE = new Set([
  '.claude/scripts/upgrade.mjs',
  '.claude/hooks/run-hook.mjs',
]);

const GROUP_PATTERNS = {
  agents:           (p) => p.startsWith('.claude/agents/'),
  hooks:            (p) => p.startsWith('.claude/hooks/') && p.endsWith('.mjs') && !p.includes('__tests__'),
  'hook-tests':     (p) => p.startsWith('.claude/hooks/__tests__/'),
  skills:           (p) => p.startsWith('.claude/skills/'),
  rules:            (p) => p.startsWith('.claude/rules/') && !PROTECTED.has(p),
  'scripts-claude': (p) => p.startsWith('.claude/scripts/'),
  'scripts-bash':   (p) => p.startsWith('scripts/'),
  settings:         (p) => p === '.claude/settings.json',
};

const SAFE_GROUPS = new Set(['agents', 'hooks', 'hook-tests', 'rules', 'scripts-claude', 'scripts-bash']);

// Upgrade only touches DLD framework files. Scaffolding (pyproject.toml, ai/, etc.) is excluded.
const UPGRADE_SCOPE = (f) => f.startsWith('.claude/') || f.startsWith('scripts/');

function sha256(filePath) {
  return createHash('sha256').update(readFileSync(filePath)).digest('hex');
}

function walkDir(dir, base) {
  const results = [];
  let entries;
  try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return results; }
  for (const entry of entries) {
    if (entry.name === '.git' || entry.name === 'node_modules') continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) results.push(...walkDir(full, base));
    else if (entry.isFile()) results.push(relative(base, full));
  }
  return results;
}

function getGroup(filePath) {
  for (const [name, matcher] of Object.entries(GROUP_PATTERNS)) {
    if (matcher(filePath)) return name;
  }
  return 'other';
}

function isGitDirty() {
  try { execSync('git diff --quiet HEAD', { stdio: 'pipe' }); return false; }
  catch (err) { return err.status === 1; }
}

function getLatestCommitSha(sourceDir) {
  try { return execSync('git rev-parse HEAD', { cwd: sourceDir, stdio: 'pipe', encoding: 'utf-8' }).trim(); }
  catch { return 'unknown'; }
}

function loadDeprecated(sourceDir) {
  const depPath = join(sourceDir, '.claude/deprecated.json');
  if (!existsSync(depPath)) return { removed: [], renamed: {} };
  try {
    const data = JSON.parse(readFileSync(depPath, 'utf-8'));
    const removed = [], renamed = {};
    for (const ver of Object.values(data.versions || {})) {
      if (ver.removed) removed.push(...ver.removed);
      if (ver.renamed) Object.assign(renamed, ver.renamed);
    }
    return { removed, renamed };
  } catch { return { removed: [], renamed: {} }; }
}

function analyze(sourceDir, projectDir, gitRoot) {
  const templateFiles = walkDir(sourceDir, sourceDir).filter(UPGRADE_SCOPE);
  const projectFiles = walkDir(projectDir, projectDir).filter(UPGRADE_SCOPE);
  const result = { identical: [], new_files: [], different: [], protected: [], infrastructure: [], user_only: [] };
  const templateSet = new Set(templateFiles);

  for (const tFile of templateFiles) {
    const userPath = join(projectDir, tFile);
    const templatePath = join(sourceDir, tFile);
    if (PROTECTED.has(tFile)) {
      result.protected.push({ path: tFile, group: getGroup(tFile) });
    } else if (INFRASTRUCTURE.has(tFile)) {
      if (!existsSync(userPath))
        result.infrastructure.push({ path: tFile, group: getGroup(tFile), status: 'new' });
      else if (sha256(templatePath) !== sha256(userPath))
        result.infrastructure.push({ path: tFile, group: getGroup(tFile), status: 'changed' });
      // identical = skip silently
    } else if (!existsSync(userPath)) {
      result.new_files.push({ path: tFile, group: getGroup(tFile) });
    } else if (sha256(templatePath) === sha256(userPath)) {
      result.identical.push({ path: tFile, group: getGroup(tFile) });
    } else {
      result.different.push({ path: tFile, group: getGroup(tFile), always_ask: ALWAYS_ASK.has(tFile) });
    }
  }

  for (const uFile of projectFiles) {
    if (!templateSet.has(uFile) && !PROTECTED.has(uFile))
      result.user_only.push({ path: uFile, group: getGroup(uFile) });
  }

  const deprecated = loadDeprecated(sourceDir);
  for (const item of result.user_only) {
    if (deprecated.removed.includes(item.path)) {
      item.deprecated = true; item.message = 'Removed from DLD. Safe to delete.';
    } else if (deprecated.renamed[item.path]) {
      item.deprecated = true; item.message = `Renamed to ${deprecated.renamed[item.path]}`;
    }
  }

  const groups = {};
  for (const category of ['new_files', 'different']) {
    for (const item of result[category]) {
      if (!groups[item.group]) groups[item.group] = { new_files: 0, different: 0, safe: SAFE_GROUPS.has(item.group) };
      groups[item.group][category]++;
    }
  }

  const total = templateFiles.length;
  return {
    version: readVersion(projectDir),
    template_commit: getLatestCommitSha(gitRoot || sourceDir),
    files: result, groups,
    summary: {
      total, processed: total,
      identical: result.identical.length, new_files: result.new_files.length,
      different: result.different.length, protected: result.protected.length,
      infrastructure: result.infrastructure.length, user_only: result.user_only.length,
    },
  };
}

function apply(sourceDir, projectDir, targets) {
  const applied = [], skipped = [], errors = [];
  for (const filePath of targets) {
    if (PROTECTED.has(filePath)) { skipped.push({ path: filePath, reason: 'protected' }); continue; }
    const src = join(sourceDir, filePath), dst = join(projectDir, filePath);
    if (!existsSync(src)) { errors.push({ path: filePath, reason: 'not found in template' }); continue; }
    try { mkdirSync(dirname(dst), { recursive: true }); cpSync(src, dst); applied.push(filePath); }
    catch (err) { errors.push({ path: filePath, reason: err.message }); }
  }
  return { applied, skipped, errors };
}

function validate(projectDir, appliedFiles) {
  const issues = [];
  const hooksConfig = join(projectDir, '.claude/hooks/hooks.config.mjs');
  if (existsSync(hooksConfig) && appliedFiles.some(f => f.startsWith('.claude/hooks/'))) {
    try { execSync(`node --check ${hooksConfig}`, { stdio: 'pipe' }); }
    catch { issues.push({ file: '.claude/hooks/hooks.config.mjs', reason: 'syntax error after upgrade' }); }
  }
  const settingsPath = join(projectDir, '.claude/settings.json');
  if (existsSync(settingsPath) && appliedFiles.some(f => f === '.claude/settings.json')) {
    try { JSON.parse(readFileSync(settingsPath, 'utf-8')); }
    catch { issues.push({ file: '.claude/settings.json', reason: 'invalid JSON after upgrade' }); }
  }
  return issues;
}

function resolveTargets(report, groupNames, fileNames) {
  const targets = new Set();
  if (groupNames) {
    const names = groupNames.split(',').map((g) => g.trim());
    for (const name of names) {
      const addFromCategory = (category) => {
        for (const item of report.files[category])
          if (item.group === name && !item.always_ask && !INFRASTRUCTURE.has(item.path)) targets.add(item.path);
      };
      if (name === 'safe') {
        for (const item of report.files.new_files)
          if (SAFE_GROUPS.has(item.group) && !INFRASTRUCTURE.has(item.path)) targets.add(item.path);
        for (const item of report.files.different)
          if (SAFE_GROUPS.has(item.group) && !item.always_ask && !INFRASTRUCTURE.has(item.path)) targets.add(item.path);
      } else if (name === 'new') {
        for (const item of report.files.new_files)
          if (!PROTECTED.has(item.path) && !INFRASTRUCTURE.has(item.path)) targets.add(item.path);
      } else { addFromCategory('new_files'); addFromCategory('different'); }
    }
  }
  if (fileNames) for (const f of fileNames.split(',').map((s) => s.trim())) targets.add(f);
  return [...targets];
}

function showDiff(sourceDir, projectDir, filePath) {
  const src = join(sourceDir, filePath), dst = join(projectDir, filePath);
  if (!existsSync(src)) { console.error(`Template file not found: ${filePath}`); process.exit(1); }
  if (!existsSync(dst)) {
    console.log(`--- /dev/null\n+++ b/${filePath}`);
    console.log(readFileSync(src, 'utf-8').split('\n').map((l) => `+${l}`).join('\n'));
    return;
  }
  try { execFileSync('git', ['diff', '--no-index', '--', dst, src], { stdio: 'inherit' }); } catch {}
}

function readVersion(projectDir) {
  const versionPath = join(projectDir, VERSION_FILE);
  if (!existsSync(versionPath)) return null;
  try { return JSON.parse(readFileSync(versionPath, 'utf-8')); } catch { return null; }
}

function writeVersion(projectDir, commitSha) {
  const data = { version: '3.10.0', template_commit: commitSha, template_repo: REPO_URL,
    upgraded_at: new Date().toISOString(), skip: [] };
  writeFileSync(join(projectDir, VERSION_FILE), JSON.stringify(data, null, 2) + '\n');
  return data;
}

function parseArgs() {
  const args = process.argv.slice(2), flags = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--analyze') flags.mode = 'analyze';
    else if (args[i] === '--apply') flags.mode = 'apply';
    else if (args[i] === '--diff') flags.mode = 'diff';
    else if (args[i] === '--cleanup') flags.mode = 'cleanup';
    else if (args[i] === '--local') flags.local = true;
    else if (args[i] === '--latest') flags.latest = true;
    else if (args[i] === '--groups' && args[i + 1]) flags.groups = args[++i];
    else if (args[i] === '--files' && args[i + 1]) flags.files = args[++i];
    else if (args[i] === '--file' && args[i + 1]) flags.file = args[++i];
    else if (args[i] === '--source' && args[i + 1]) flags.source = args[++i];
  }
  return flags;
}

function resolveSource(flags, projectDir) {
  if (flags.source) return { sourceDir: flags.source, tempCloneRoot: null };
  if (flags.local) {
    const localTemplate = join(projectDir, 'template');
    if (!existsSync(localTemplate)) {
      console.error(JSON.stringify({ error: 'No template/ directory found. Use --latest for GitHub fetch.' }));
      process.exit(1);
    }
    return { sourceDir: localTemplate, tempCloneRoot: null };
  }
  let tempCloneRoot = null;
  try {
    tempCloneRoot = join('/tmp', `dld-upgrade-${Date.now()}`);
    execSync(`git clone --depth 1 --filter=blob:none --sparse ${REPO_URL} ${tempCloneRoot}`, { stdio: 'pipe' });
    execSync(`git -C ${tempCloneRoot} sparse-checkout set ${TEMPLATE_DIR}`, { stdio: 'pipe' });
    return { sourceDir: join(tempCloneRoot, TEMPLATE_DIR), tempCloneRoot };
  } catch (err) {
    try { if (tempCloneRoot) rmSync(tempCloneRoot, { recursive: true, force: true }); } catch {}
    console.error(JSON.stringify({ error: `Network fetch failed: ${err.message}` }));
    process.exit(1);
  }
}

function main() {
  const [major] = process.versions.node.split('.');
  if (parseInt(major) < 18) {
    console.error(JSON.stringify({ error: 'Node.js 18+ required', current: process.versions.node }));
    process.exit(1);
  }
  const flags = parseArgs();
  const projectDir = process.cwd();
  if (!flags.mode) {
    console.error('Usage: upgrade.mjs --analyze [--local|--latest] | --apply --groups X | --diff --file X | --cleanup');
    process.exit(1);
  }
  if ((flags.mode === 'apply' || flags.mode === 'analyze') && isGitDirty()) {
    console.error(JSON.stringify({ error: 'Working tree is dirty. Commit or stash changes before upgrading.' }));
    process.exit(1);
  }

  const { sourceDir, tempCloneRoot } = resolveSource(flags, projectDir);
  const gitRoot = flags.local ? projectDir : tempCloneRoot;

  try {
    if (flags.mode === 'analyze') {
      const report = analyze(sourceDir, projectDir, gitRoot);
      console.log(JSON.stringify(report, null, 2));
      if (report.summary.new_files === 0 && report.summary.different === 0) process.exit(2);
    } else if (flags.mode === 'diff') {
      if (!flags.file) { console.error(JSON.stringify({ error: 'Specify --file for diff mode.' })); process.exit(1); }
      showDiff(sourceDir, projectDir, flags.file);
    } else if (flags.mode === 'cleanup') {
      const report = analyze(sourceDir, projectDir, gitRoot);
      const deprecatedFiles = report.files.user_only.filter(f => f.deprecated);
      if (deprecatedFiles.length === 0) { console.log(JSON.stringify({ message: 'No deprecated files found.' })); process.exit(2); }
      const trashDir = join(projectDir, '.claude/.upgrade-trash');
      mkdirSync(trashDir, { recursive: true });
      const moved = [];
      for (const item of deprecatedFiles) {
        const src = join(projectDir, item.path), dst = join(trashDir, item.path);
        mkdirSync(dirname(dst), { recursive: true }); cpSync(src, dst); rmSync(src);
        moved.push(item.path);
      }
      console.log(JSON.stringify({ moved, trash_dir: '.claude/.upgrade-trash' }));
    } else if (flags.mode === 'apply') {
      if (!flags.groups && !flags.files) {
        console.error(JSON.stringify({ error: 'Specify --groups or --files for apply mode.' })); process.exit(1);
      }
      const report = analyze(sourceDir, projectDir, gitRoot);
      const targets = resolveTargets(report, flags.groups, flags.files);
      if (targets.length === 0) {
        console.log(JSON.stringify({ applied: [], skipped: [], errors: [], message: 'No files to apply.' })); process.exit(2);
      }
      let stashRef = '';
      try { stashRef = execSync('git stash create', { encoding: 'utf-8', stdio: 'pipe' }).trim(); } catch {}
      const result = apply(sourceDir, projectDir, targets);
      if (result.applied.length > 0) {
        const issues = validate(projectDir, result.applied);
        if (issues.length > 0) {
          result.validation_issues = issues;
          if (stashRef) {
            try { execSync('git checkout -- .', { stdio: 'pipe' }); result.rolled_back = true; result.rollback_ref = stashRef; } catch {}
          }
        }
      }
      if (result.applied.length > 0 && result.errors.length === 0 && !result.rolled_back)
        result.version = writeVersion(projectDir, report.template_commit);
      if (result.applied.length > 0) {
        const logEntry = { timestamp: new Date().toISOString(), applied: result.applied,
          errors: result.errors, rolled_back: result.rolled_back || false, stash_ref: stashRef || null };
        const logPath = join(projectDir, '.dld-upgrade-log');
        const existing = existsSync(logPath) ? readFileSync(logPath, 'utf-8') : '';
        writeFileSync(logPath, existing + JSON.stringify(logEntry) + '\n');
      }
      console.log(JSON.stringify(result, null, 2));
    }
  } finally {
    if (tempCloneRoot) try { rmSync(tempCloneRoot, { recursive: true, force: true }); } catch {}
  }
}

main();
