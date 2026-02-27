#!/usr/bin/env node
// DLD Upgrade Script — deterministic template upgrade engine.
// Modes: --analyze [--local|--latest] | --apply --groups X | --apply --files X | --diff --file X
// Exit codes: 0=success, 1=error, 2=nothing to update

import { execSync, execFileSync } from 'child_process';
import { createHash } from 'crypto';
import {
  existsSync, readFileSync, writeFileSync, mkdirSync, cpSync,
  rmSync, readdirSync,
} from 'fs';
import { join, relative, dirname } from 'path';

const REPO_URL = 'https://github.com/Ellevated/dld.git';
const TEMPLATE_DIR = 'template';
const VERSION_FILE = '.dld-version';

const PROTECTED = new Set([
  'CLAUDE.md',
  '.claude/rules/localization.md',
  '.claude/rules/template-sync.md',
  '.claude/CUSTOMIZATIONS.md',
  '.claude/settings.local.json',
  '.claude/hooks/hooks.config.local.mjs',
]);

// Files that always require manual review (never auto-apply)
const ALWAYS_ASK = new Set([
  '.claude/settings.json',
]);

// Groups for batch operations
const GROUP_PATTERNS = {
  agents:         (p) => p.startsWith('.claude/agents/'),
  hooks:          (p) => p.startsWith('.claude/hooks/') && p.endsWith('.mjs') && !p.includes('__tests__'),
  'hook-tests':   (p) => p.startsWith('.claude/hooks/__tests__/'),
  skills:         (p) => p.startsWith('.claude/skills/'),
  rules:          (p) => p.startsWith('.claude/rules/') && !PROTECTED.has(p),
  'scripts-claude': (p) => p.startsWith('.claude/scripts/'),
  'scripts-bash': (p) => p.startsWith('scripts/'),
  settings:       (p) => p === '.claude/settings.json',
};

// Safe groups: auto-apply without user confirmation
const SAFE_GROUPS = new Set(['agents', 'hooks', 'hook-tests', 'rules', 'scripts-claude', 'scripts-bash']);

function sha256(filePath) {
  const content = readFileSync(filePath);
  return createHash('sha256').update(content).digest('hex');
}

function walkDir(dir, base) {
  const results = [];
  let entries;
  try { entries = readdirSync(dir, { withFileTypes: true }); }
  catch { return results; }
  for (const entry of entries) {
    if (entry.name === '.git' || entry.name === 'node_modules') continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkDir(full, base));
    } else if (entry.isFile()) {
      results.push(relative(base, full));
    }
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
  try {
    execSync('git diff --quiet HEAD', { stdio: 'pipe' });
    return false;
  } catch (err) {
    if (err.status === 1) return true; // tracked files have changes
    return false; // not a git repo or no commits — allow anyway
  }
}

function getLatestCommitSha(sourceDir) {
  try {
    return execSync('git rev-parse HEAD', {
      cwd: sourceDir, stdio: 'pipe', encoding: 'utf-8',
    }).trim();
  } catch {
    return 'unknown';
  }
}

function analyze(sourceDir, projectDir, gitRoot) {
  const templateFiles = walkDir(sourceDir, sourceDir);
  const projectFiles = walkDir(projectDir, projectDir)
    .filter((f) => f.startsWith('.claude/') || f.startsWith('scripts/'));

  const result = {
    identical: [],
    new_files: [],
    different: [],
    protected: [],
    user_only: [],
  };

  const templateSet = new Set(templateFiles);

  for (const tFile of templateFiles) {
    const userPath = join(projectDir, tFile);
    const templatePath = join(sourceDir, tFile);

    if (PROTECTED.has(tFile)) {
      result.protected.push({ path: tFile, group: getGroup(tFile) });
    } else if (!existsSync(userPath)) {
      result.new_files.push({ path: tFile, group: getGroup(tFile) });
    } else if (sha256(templatePath) === sha256(userPath)) {
      result.identical.push({ path: tFile, group: getGroup(tFile) });
    } else {
      result.different.push({
        path: tFile,
        group: getGroup(tFile),
        always_ask: ALWAYS_ASK.has(tFile),
      });
    }
  }

  // Scan for user-only files
  for (const uFile of projectFiles) {
    if (!templateSet.has(uFile) && !PROTECTED.has(uFile)) {
      result.user_only.push({ path: uFile, group: getGroup(uFile) });
    }
  }

  // Group summaries
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
    files: result,
    groups,
    summary: {
      total,
      processed: total,
      identical: result.identical.length,
      new_files: result.new_files.length,
      different: result.different.length,
      protected: result.protected.length,
      user_only: result.user_only.length,
    },
  };
}

function apply(sourceDir, projectDir, targets) {
  const applied = [];
  const skipped = [];
  const errors = [];

  for (const filePath of targets) {
    if (PROTECTED.has(filePath)) {
      skipped.push({ path: filePath, reason: 'protected' });
      continue;
    }
    const src = join(sourceDir, filePath);
    const dst = join(projectDir, filePath);
    if (!existsSync(src)) {
      errors.push({ path: filePath, reason: 'not found in template' });
      continue;
    }
    try {
      mkdirSync(dirname(dst), { recursive: true });
      cpSync(src, dst);
      applied.push(filePath);
    } catch (err) {
      errors.push({ path: filePath, reason: err.message });
    }
  }

  return { applied, skipped, errors };
}

function resolveTargets(report, groupNames, fileNames) {
  const targets = new Set();
  if (groupNames) {
    const names = groupNames.split(',').map((g) => g.trim());
    for (const name of names) {
      const addFromCategory = (category) => {
        for (const item of report.files[category]) {
          if (item.group === name && !item.always_ask) targets.add(item.path);
        }
      };
      if (name === 'safe') {
        // All safe groups: new + different
        for (const item of report.files.new_files) {
          if (SAFE_GROUPS.has(item.group)) targets.add(item.path);
        }
        for (const item of report.files.different) {
          if (SAFE_GROUPS.has(item.group) && !item.always_ask) targets.add(item.path);
        }
      } else if (name === 'new') {
        for (const item of report.files.new_files) targets.add(item.path);
      } else {
        addFromCategory('new_files');
        addFromCategory('different');
      }
    }
  }
  if (fileNames) {
    for (const f of fileNames.split(',').map((s) => s.trim())) {
      targets.add(f);
    }
  }
  return [...targets];
}

function showDiff(sourceDir, projectDir, filePath) {
  const src = join(sourceDir, filePath);
  const dst = join(projectDir, filePath);
  if (!existsSync(src)) {
    console.error(`Template file not found: ${filePath}`);
    process.exit(1);
  }
  if (!existsSync(dst)) {
    console.log(`--- /dev/null\n+++ b/${filePath}`);
    console.log(readFileSync(src, 'utf-8').split('\n').map((l) => `+${l}`).join('\n'));
    return;
  }
  try {
    execFileSync('git', ['diff', '--no-index', '--', dst, src], { stdio: 'inherit' });
  } catch {
    // git diff returns exit 1 when files differ — that's normal
  }
}

function readVersion(projectDir) {
  const versionPath = join(projectDir, VERSION_FILE);
  if (!existsSync(versionPath)) return null;
  try { return JSON.parse(readFileSync(versionPath, 'utf-8')); }
  catch { return null; }
}

function writeVersion(projectDir, commitSha) {
  const versionPath = join(projectDir, VERSION_FILE);
  const data = {
    version: '3.9.0',
    template_commit: commitSha,
    template_repo: REPO_URL,
    upgraded_at: new Date().toISOString(),
    skip: [],
  };
  writeFileSync(versionPath, JSON.stringify(data, null, 2) + '\n');
  return data;
}

function parseArgs() {
  const args = process.argv.slice(2);
  const flags = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--analyze') flags.mode = 'analyze';
    else if (args[i] === '--apply') flags.mode = 'apply';
    else if (args[i] === '--diff') flags.mode = 'diff';
    else if (args[i] === '--local') flags.local = true;
    else if (args[i] === '--latest') flags.latest = true;
    else if (args[i] === '--groups' && args[i + 1]) flags.groups = args[++i];
    else if (args[i] === '--files' && args[i + 1]) flags.files = args[++i];
    else if (args[i] === '--file' && args[i + 1]) flags.file = args[++i];
    else if (args[i] === '--source' && args[i + 1]) flags.source = args[++i];
  }
  return flags;
}

function main() {
  // Node version check
  const [major] = process.versions.node.split('.');
  if (parseInt(major) < 18) {
    console.error(JSON.stringify({ error: 'Node.js 18+ required', current: process.versions.node }));
    process.exit(1);
  }

  const flags = parseArgs();
  const projectDir = process.cwd();

  if (!flags.mode) {
    console.error('Usage: upgrade.mjs --analyze [--local|--latest] | --apply --groups X | --diff --file X');
    process.exit(1);
  }

  if ((flags.mode === 'apply' || flags.mode === 'analyze') && isGitDirty()) {
    console.error(JSON.stringify({
      error: 'Working tree is dirty. Please commit or stash your changes before upgrading.',
    }));
    process.exit(1);
  }

  // Resolve template source
  let sourceDir = flags.source;
  let tempCloneRoot = null;

  if (!sourceDir) {
    if (flags.local) {
      // Local mode: use template/ from parent DLD repo (for dev/testing)
      const localTemplate = join(projectDir, 'template');
      if (!existsSync(localTemplate)) {
        console.error(JSON.stringify({ error: 'No template/ directory found. Use --latest for GitHub fetch.' }));
        process.exit(1);
      }
      sourceDir = localTemplate;
    } else {
      // Default: fetch from GitHub
      try {
        tempCloneRoot = join('/tmp', `dld-upgrade-${Date.now()}`);
        execSync(
          `git clone --depth 1 --filter=blob:none --sparse ${REPO_URL} ${tempCloneRoot}`,
          { stdio: 'pipe' },
        );
        execSync(
          `git -C ${tempCloneRoot} sparse-checkout set ${TEMPLATE_DIR}`,
          { stdio: 'pipe' },
        );
        sourceDir = join(tempCloneRoot, TEMPLATE_DIR);
      } catch (err) {
        try { if (tempCloneRoot) rmSync(tempCloneRoot, { recursive: true, force: true }); } catch {}
        console.error(JSON.stringify({ error: `Network fetch failed: ${err.message}` }));
        process.exit(1);
      }
    }
  }

  try {
    if (flags.mode === 'analyze') {
      const report = analyze(sourceDir, projectDir, flags.local ? projectDir : tempCloneRoot);
      console.log(JSON.stringify(report, null, 2));
      if (report.summary.new_files === 0 && report.summary.different === 0) {
        process.exit(2); // nothing to update
      }
    } else if (flags.mode === 'apply') {
      if (!flags.groups && !flags.files) {
        console.error(JSON.stringify({ error: 'Specify --groups or --files for apply mode.' }));
        process.exit(1);
      }
      const report = analyze(sourceDir, projectDir, flags.local ? projectDir : tempCloneRoot);
      const targets = resolveTargets(report, flags.groups, flags.files);
      if (targets.length === 0) {
        console.log(JSON.stringify({ applied: [], skipped: [], errors: [], message: 'No files to apply.' }));
        process.exit(2);
      }
      const result = apply(sourceDir, projectDir, targets);
      // Write .dld-version after successful apply
      if (result.applied.length > 0 && result.errors.length === 0) {
        const version = writeVersion(projectDir, report.template_commit);
        result.version = version;
      }
      console.log(JSON.stringify(result, null, 2));
    } else if (flags.mode === 'diff') {
      if (!flags.file) {
        console.error(JSON.stringify({ error: 'Specify --file for diff mode.' }));
        process.exit(1);
      }
      showDiff(sourceDir, projectDir, flags.file);
    }
  } finally {
    // Cleanup temp clone
    if (tempCloneRoot) {
      try { rmSync(tempCloneRoot, { recursive: true, force: true }); } catch {}
    }
  }
}

main();
