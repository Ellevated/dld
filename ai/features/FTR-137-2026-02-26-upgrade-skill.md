# Feature: [FTR-137] Deterministic DLD Upgrade Skill

**Status:** in_progress | **Priority:** P1 | **Date:** 2026-02-26

## Why

Users ask Claude Code "обнови DLD с гитхаба" → Claude is non-deterministic, skips files, misses changes, may overwrite customizations. Need a `/upgrade` skill backed by a deterministic Node.js script that handles ALL file operations, while Claude only provides UX (present report, relay user decisions).

## Context

- DLD template has 150+ files (.claude/skills, agents, hooks, rules, scripts)
- Users get DLD via `npx create-dld` which copies template/ contents
- Users CAN modify any file — skills, agents, hooks, rules
- Currently no version tracking (no .dld-version)
- `check-sync.sh` exists but is DLD-internal (compares template/ vs root .claude/)
- `excludeFromSync` in hooks.config.mjs defines protected files
- create-dld already has sparse-clone pattern for GitHub fetch

---

## Scope

**In scope:**
- `upgrade.mjs` — deterministic Node.js script (analyze + apply)
- `SKILL.md` — skill prompt for Claude UX layer
- `.dld-version` — written after first upgrade (version tracking for future)
- Localization triggers for Russian
- CLAUDE.md skills table update

**Out of scope:**
- Per-file SHA256 checksums in .dld-version (v1.0)
- Rename detection / rename manifest (v1.0)
- 3-way merge with `git merge-file` (v1.0)
- Changes to create-dld package (separate TECH task)
- GitHub Actions auto-PR workflow (future)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `grep -r "upgrade\|dld-version" . --include="*.md" --include="*.mjs"` → 4 results
- CHANGELOG.md:113 (manual upgrade instructions)
- template/.claude/skills/retrofit/SKILL.md:17 (framework upgrade trigger)
- docs/getting-started/upgrade-paths.md (tier upgrades, different concept)

### Step 2: DOWN — what depends on?
- `packages/create-dld/index.js:14` — REPO_URL for GitHub fetch
- `template/.claude/hooks/hooks.config.mjs:85` — excludeFromSync list
- `scripts/check-sync.sh` — reference for diff logic

### Step 3: BY TERM — grep entire project
- `grep -rn ".dld-version" .` → 0 results (file doesn't exist yet)
- `grep -rn "upgrade" . --include="*.md"` → CHANGELOG, retrofit, upgrade-paths

| File | Line | Status | Action |
|------|------|--------|--------|
| CHANGELOG.md | 113 | existing manual upgrade | Reference only |
| retrofit/SKILL.md | 17 | mentions framework upgrade | No change needed |
| upgrade-paths.md | 1 | tier upgrades (different) | No change needed |

### Step 4: CHECKLIST — mandatory folders
- [x] `template/.claude/skills/upgrade/` checked — does NOT exist (create)
- [x] `template/.claude/scripts/upgrade.mjs` checked — does NOT exist (create)
- [x] `.claude/skills/upgrade/` checked — does NOT exist (create after template)
- [x] No migration needed (no DB)
- [x] No glossary needed

### Verification
- [x] All found files added to Allowed Files
- [x] grep by ".dld-version" = 0 (new file, no cleanup needed)

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.claude/scripts/upgrade.mjs` — main deterministic upgrade script (create)
2. `template/.claude/skills/upgrade/SKILL.md` — skill prompt (create)
3. `template/CLAUDE.md` — add upgrade to skills table (modify)
4. `.claude/CLAUDE.md` — sync skills table (modify, DLD-specific)
5. `.claude/rules/localization.md` — add Russian triggers (modify, DLD-specific)

**New files allowed:**
- `template/.claude/scripts/upgrade.mjs` — deterministic upgrade engine
- `template/.claude/skills/upgrade/SKILL.md` — skill UX orchestrator

**Sync after template:**
- `.claude/scripts/upgrade.mjs` — copy from template
- `.claude/skills/upgrade/SKILL.md` — copy from template

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: true
docker: false
database: false

---

## Blueprint Reference

**Domain:** DLD framework tooling (meta — tools for DLD users)
**Cross-cutting:** None (standalone skill, no business logic)
**Data model:** `.dld-version` JSON file (new, user-side)

---

## Approaches

### Approach 1: Conservative Script (no .dld-version)
**Source:** Devil scout research-devil.md
**Summary:** Compare every file against latest template. Identical → skip. Different → ask. No version tracking.
**Pros:** Works for ALL users immediately. No chicken-and-egg.
**Cons:** False positives — asks about ALL different files (~50+ on first upgrade). Bad UX at scale.

### Approach 2: Smart Classification (full .dld-version + checksums)
**Source:** External scout (cruft pattern) research-external.md
**Summary:** Per-file SHA256 manifest written at install time. 4-state classification. Auto-update safe files.
**Pros:** Precise. Minimal user interaction. Gold standard (cruft, React Native).
**Cons:** Requires create-dld changes. Chicken-and-egg for existing users. 3-5 days.

### Approach 3: Phased Delivery (v0.1 now → v1.0 later)
**Source:** Synthesis of all 4 scouts
**Summary:** v0.1 ships a script that fetches latest template, classifies by IDENTICAL/NEW/DIFFERENT/PROTECTED, groups by directory. Auto-applies safe groups, asks about conflicts. Writes .dld-version after first run (commit SHA only). Future versions add checksums.
**Pros:** Ships in 2 days. Validates demand. No blockers.
**Cons:** v0.1 may ask about more files than necessary (no per-file hashes).

### Selected: 3
**Rationale:** Solves the core problem (deterministic file operations, 150/150 verification) immediately. Devil scout is right: validate demand before investing in full cruft-style system. v0.1 covers 80%+ of cases because most users don't customize agent prompts.

---

## Design

### User Flow

1. User: "Клод, обнови DLD скиллы с гитхаба" (or `/upgrade`)
2. Claude reads SKILL.md → runs pre-flight checks
3. Claude runs: `node .claude/scripts/upgrade.mjs --analyze`
4. Script fetches latest template via sparse-clone to /tmp
5. Script compares ALL files, outputs JSON report to stdout
6. Claude reads report, presents grouped summary to user
7. User confirms: "да" / selects specific groups
8. Claude runs: `node .claude/scripts/upgrade.mjs --apply --groups safe,new`
9. Script copies files deterministically, outputs result
10. For conflicts: Claude shows diff per-file, user picks (keep/take/skip)
11. Claude runs: `node .claude/scripts/upgrade.mjs --apply --files .claude/skills/spark/SKILL.md`
12. Script writes .dld-version with current commit SHA
13. Claude: "Upgrade complete. 52/52 files. Restart Claude Code."

### Architecture

```
User → Claude Code → /upgrade skill (SKILL.md)
                         ↓
                    upgrade.mjs (Node.js, deterministic)
                    ├── --analyze → JSON report (stdout)
                    ├── --apply --groups X → batch copy
                    └── --apply --files X → per-file copy
                         ↓
                    .dld-version (written after success)
```

**Key principle:** Script does ALL file I/O. Claude NEVER copies files directly. Claude only:
- Runs the script via Bash tool
- Reads stdout JSON
- Presents results to user
- Passes user decisions back to script

### Script Modes

```
upgrade.mjs --analyze [--local | --latest]
  → Outputs JSON: { version, files: { identical, new, different, protected, user_only }, summary }

upgrade.mjs --apply --groups safe,new [--source /tmp/dld-xxx]
  → Copies all files in specified groups. Returns { applied, skipped, errors }

upgrade.mjs --apply --files path1,path2 [--source /tmp/dld-xxx]
  → Copies specific files. Returns { applied, skipped, errors }

upgrade.mjs --diff --file path
  → Shows unified diff for a specific file
```

### File Classification Logic (v0.1)

```javascript
for (const templateFile of allTemplateFiles) {
  const userFile = resolve(projectRoot, templateFile);

  if (isProtected(templateFile))        → PROTECTED (never touch)
  else if (!existsSync(userFile))       → NEW (auto-add)
  else if (hashMatch(templateFile, userFile)) → IDENTICAL (skip, up to date)
  else                                  → DIFFERENT (needs decision)
}

// Also scan for USER_ONLY files
for (const userFile of allUserFiles) {
  if (!existsInTemplate(userFile))      → USER_ONLY (leave alone)
}
```

### Protected Files List

Imported from `hooks.config.mjs:excludeFromSync` + additions:

```javascript
const PROTECTED = [
  'CLAUDE.md',                          // User's project config
  '.claude/rules/localization.md',       // User's language triggers
  '.claude/rules/template-sync.md',      // Sync policy
  '.claude/rules/git-local-folders.md',  // Gitignore rules
  '.claude/CUSTOMIZATIONS.md',           // User's documented changes
  '.claude/settings.local.json',         // User's local settings
  '.claude/hooks/hooks.config.local.mjs', // User's hook overrides
];
```

### .dld-version Schema (v0.1)

Written after first successful upgrade:

```json
{
  "version": "3.9.0",
  "template_commit": "769a2ae2f8c...",
  "template_repo": "https://github.com/Ellevated/dld.git",
  "upgraded_at": "2026-02-26T12:00:00Z",
  "skip": []
}
```

No per-file hashes in v0.1 (that's v1.0 scope).

### Grouping Strategy

Files are grouped by directory for batch decisions:

| Group | Path Pattern | Default Action |
|-------|-------------|----------------|
| agents | `.claude/agents/**` | Auto-update (rarely customized) |
| hooks | `.claude/hooks/*.mjs` | Auto-update (customize via .local.mjs) |
| hook-tests | `.claude/hooks/__tests__/**` | Auto-update |
| skills | `.claude/skills/**` | Ask per-skill-directory |
| rules | `.claude/rules/**` (non-protected) | Auto-update |
| scripts-claude | `.claude/scripts/**` | Auto-update |
| scripts-bash | `scripts/**` | Auto-update |
| settings | `.claude/settings.json` | Always ask (may have user hooks) |

### Database Changes

N/A — no database.

---

## Drift Log

**Checked:** 2026-02-26 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `template/CLAUDE.md` | skills table order differs from root CLAUDE.md (eval position, descriptions) | AUTO-FIX: noted, insertion point adjusted to line 160 |
| `CLAUDE.md` (root) | v3.7 header vs template v3.9; missing eval trigger row | AUTO-FIX: insertion point at line 160 confirmed |
| `packages/create-dld/index.js:154` | no change, sparse-clone pattern still at line 154-156 | none |
| `template/.claude/hooks/hooks.config.mjs:85` | no change, excludeFromSync at lines 85-91 with 5 entries | none |
| `scripts/check-sync.sh` | no change, 70 LOC | none |

### References Updated
- Task 1: create-dld sparse-clone confirmed at `packages/create-dld/index.js:154-156`
- Task 1: excludeFromSync confirmed at `template/.claude/hooks/hooks.config.mjs:85-91` (5 items, NOT including `hooks.config.local.mjs`)
- Task 3: template/CLAUDE.md skills table lines 144-160, insert after line 160 (diagram row)
- Task 3: root CLAUDE.md skills table lines 144-160, insert after line 160 (eval row)
- Task 3: localization.md has 28 lines, insert new row before `## Action` section at line 29

---

## Detailed Implementation Plan

### Research Sources
- [cruft -- template upgrade tool](https://cruft.github.io/cruft/) -- .dld-version schema, classification logic
- [rn-diff-purge](https://github.com/react-native-community/rn-diff-purge) -- commit-anchored diff pattern
- [git sparse-checkout docs](https://git-scm.com/docs/git-sparse-checkout) -- confirmed: `--depth 1 --filter=blob:none --sparse` is correct pattern
- [create-dld/index.js:154](packages/create-dld/index.js:154) -- sparse-clone pattern to reuse (verified 2026-02-26)
- [hooks.config.mjs:85](template/.claude/hooks/hooks.config.mjs:85) -- excludeFromSync list (verified 2026-02-26, 5 entries)
- [codebase-inventory.mjs](template/.claude/scripts/codebase-inventory.mjs) -- reference for DLD script patterns (371 LOC, walkDir, JSON stdout)

### Task 1: Create upgrade.mjs script

**Files:**
- Create: `template/.claude/scripts/upgrade.mjs`

**Context:**
The core deterministic engine. Fetches latest DLD template via git sparse-clone (same pattern as create-dld), walks all template files, classifies each against user's project, outputs structured JSON. Claude never touches files directly -- this script does ALL I/O.

**Step 1: Write the script**

```javascript
// template/.claude/scripts/upgrade.mjs
#!/usr/bin/env node
/**
 * DLD Upgrade Script — deterministic template upgrade engine.
 *
 * Modes:
 *   --analyze [--local | --latest]  → JSON report to stdout
 *   --apply --groups safe,new [--source /tmp/dld-xxx]  → batch copy
 *   --apply --files path1,path2 [--source /tmp/dld-xxx]  → per-file copy
 *   --diff --file path  → unified diff to stdout
 *
 * Exit codes: 0 = success, 1 = error, 2 = nothing to update
 */

import { execSync } from 'child_process';
import { createHash } from 'crypto';
import {
  existsSync, readFileSync, writeFileSync, mkdirSync, cpSync,
  rmSync, readdirSync, statSync,
} from 'fs';
import { join, relative, dirname, resolve } from 'path';

// --- Constants ---

const REPO_URL = 'https://github.com/Ellevated/dld.git';
const TEMPLATE_DIR = 'template';
const VERSION_FILE = '.dld-version';

const PROTECTED = new Set([
  'CLAUDE.md',
  '.claude/rules/localization.md',
  '.claude/rules/template-sync.md',
  '.claude/rules/git-local-folders.md',
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

// Groups safe for auto-apply (no user customization expected)
const SAFE_GROUPS = new Set(['agents', 'hooks', 'hook-tests', 'rules', 'scripts-claude', 'scripts-bash']);

// --- Helpers ---

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
    const status = execSync('git status --porcelain', { stdio: 'pipe', encoding: 'utf-8' });
    return status.trim().length > 0;
  } catch {
    return false; // not a git repo — allow anyway
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

function fetchLatestTemplate() {
  const tempDir = join('/tmp', `dld-upgrade-${Date.now()}`);
  try {
    execSync(
      `git clone --depth 1 --filter=blob:none --sparse ${REPO_URL} ${tempDir}`,
      { stdio: 'pipe' },
    );
    execSync(
      `git -C ${tempDir} sparse-checkout set ${TEMPLATE_DIR}`,
      { stdio: 'pipe' },
    );
    return join(tempDir, TEMPLATE_DIR);
  } catch (err) {
    // Clean up on failure
    try { rmSync(tempDir, { recursive: true, force: true }); } catch {}
    throw new Error(`Failed to fetch latest template: ${err.message}`);
  }
}

// --- Core: Analyze ---

function analyze(sourceDir, projectDir) {
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
  let processed = 0;

  for (const tFile of templateFiles) {
    processed++;
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
    template_commit: getLatestCommitSha(sourceDir.replace(`/${TEMPLATE_DIR}`, '')),
    files: result,
    groups,
    summary: {
      total,
      processed,
      identical: result.identical.length,
      new_files: result.new_files.length,
      different: result.different.length,
      protected: result.protected.length,
      user_only: result.user_only.length,
    },
  };
}

// --- Core: Apply ---

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

// --- Core: Diff ---

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
    execSync(`git diff --no-index -- "${dst}" "${src}"`, { stdio: 'inherit' });
  } catch {
    // git diff returns exit 1 when files differ — that's normal
  }
}

// --- Version file ---

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

// --- CLI ---

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

  // Pre-flight: git dirty check (only for --apply)
  if (flags.mode === 'apply' && isGitDirty()) {
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
      // Dirty check also applies to analyze to be safe
      if (isGitDirty()) {
        console.error(JSON.stringify({
          error: 'Working tree is dirty. Please commit or stash your changes before analyzing.',
        }));
        process.exit(1);
      }
      const report = analyze(sourceDir, projectDir);
      console.log(JSON.stringify(report, null, 2));
      if (report.summary.new_files === 0 && report.summary.different === 0) {
        process.exit(2); // nothing to update
      }
    } else if (flags.mode === 'apply') {
      if (!flags.groups && !flags.files) {
        console.error(JSON.stringify({ error: 'Specify --groups or --files for apply mode.' }));
        process.exit(1);
      }
      const report = analyze(sourceDir, projectDir);
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
```

**Step 2: Verify script runs**

```bash
cd /Users/desperado/dev/dld/.worktrees/FTR-137
node template/.claude/scripts/upgrade.mjs --analyze --local
```

Expected: JSON output with files.identical, files.new_files, files.different, files.protected, summary.total. Exit code 0 or 2 (if nothing to update on self-comparison, exit 2).

**Step 3: Verify protected files are excluded**

Run the analyze and confirm:
- `CLAUDE.md` appears in `files.protected`
- `.claude/rules/localization.md` appears in `files.protected`
- `.claude/CUSTOMIZATIONS.md` appears in `files.protected`
- None of these appear in `files.different` or `files.new_files`

**Step 4: Verify git dirty check**

```bash
# Make a dirty change
echo "test" >> /tmp/dirty-test.txt
cp /tmp/dirty-test.txt .
node template/.claude/scripts/upgrade.mjs --analyze --local
# Should exit 1 with "commit or stash" error
git checkout -- .
```

**Acceptance Criteria:**
- [ ] `--analyze --local` outputs valid JSON with all 5 classification categories
- [ ] `--analyze` (default) fetches from GitHub via sparse-clone
- [ ] `--apply --groups safe` copies only safe-group files
- [ ] `--apply --files` copies specific files
- [ ] `--diff --file` shows unified diff
- [ ] Protected files NEVER in apply targets
- [ ] settings.json always in `different` with `always_ask: true`, never auto-applied
- [ ] Git dirty tree refuses with exit code 1
- [ ] `.dld-version` written after successful apply
- [ ] `summary.processed === summary.total`
- [ ] Network failure on `--latest` produces clean error, no partial state
- [ ] Exit code 2 when nothing to update
- [ ] Script < 400 LOC (estimated: ~350 LOC including comments)

---

### Task 2: Create SKILL.md prompt

**Files:**
- Create: `template/.claude/skills/upgrade/SKILL.md`

**Context:**
The UX layer. Claude reads this skill and follows the protocol: run upgrade.mjs, parse JSON output, present grouped report to user, handle confirmations, relay decisions back to script. Claude NEVER copies files directly.

**Step 1: Write the skill**

```markdown
---
name: upgrade
description: Upgrade DLD framework files from latest template on GitHub.
---

# /upgrade -- DLD Framework Upgrade

Deterministic upgrade of DLD skills, agents, hooks, rules, and scripts from the latest template.

**Key principle:** The upgrade.mjs script does ALL file operations. You NEVER copy or modify files directly. You only:
1. Run the script via Bash
2. Read its JSON output
3. Present results to user
4. Pass user decisions back to the script

## Pre-flight

1. Verify `node --version` >= 18
2. Verify `.claude/scripts/upgrade.mjs` exists
3. If missing: "upgrade.mjs not found. Run `npx create-dld` to set up a DLD project first."

## Flow

### Step 1: Analyze

```bash
node .claude/scripts/upgrade.mjs --analyze
```

Parse the JSON output. If exit code 2: "Your DLD is up to date. No changes needed."

If exit code 1: show error message from JSON and stop.

### Step 2: Present Report

Show grouped summary to user:

```
DLD Upgrade Report
==================
Template commit: {report.template_commit}

Summary: {identical} up to date, {new_files} new, {different} changed, {protected} protected

Groups:
  agents:         {N} new, {N} changed  [safe -- auto-update]
  hooks:          {N} new, {N} changed  [safe -- auto-update]
  skills:         {N} new, {N} changed  [review recommended]
  rules:          {N} new, {N} changed  [safe -- auto-update]
  scripts-claude: {N} new, {N} changed  [safe -- auto-update]
  settings:       {N} changed           [always ask]

Protected (never touched): {protected count} files
User-only (your files, untouched): {user_only count} files
```

### Step 3: User Confirmation

Ask: "Apply safe groups automatically? (agents, hooks, rules, scripts) Y/n"

If yes:
```bash
node .claude/scripts/upgrade.mjs --apply --groups safe,new
```

### Step 4: Handle Conflicts

For each non-safe group with changes (skills, settings):

Show per-file diff:
```bash
node .claude/scripts/upgrade.mjs --diff --file {path}
```

For each file ask: "Take template version / Keep yours / Skip"

If "take":
```bash
node .claude/scripts/upgrade.mjs --apply --files {path}
```

### Step 5: Verification

After all applies, run analyze again:
```bash
node .claude/scripts/upgrade.mjs --analyze
```

Report final state:
```
Upgrade complete.
  Applied: {N} files
  Skipped: {N} files (user decision)
  Protected: {N} files (never touched)
  Remaining differences: {N} files

Restart Claude Code to activate changes.
```

## Rules

- NEVER use Read/Edit/Write tools to copy template files
- ALWAYS use upgrade.mjs for ALL file operations
- Show diff before asking user to accept changes
- Protected files are NEVER offered for update
- settings.json ALWAYS requires explicit user approval
- If --analyze fails with network error, suggest: "Try again or use --local if you have the DLD repo cloned"
- After successful upgrade, remind user to restart Claude Code

## Error Recovery

- Network failure: suggest retry or `--local` mode
- Partial apply (some errors): show what succeeded and what failed
- Git dirty: tell user to commit or stash first
```

**Step 2: Verify skill file exists and is valid**

```bash
cat template/.claude/skills/upgrade/SKILL.md | head -5
```

Expected: frontmatter with `name: upgrade` and `description:`.

**Acceptance Criteria:**
- [ ] Skill has valid frontmatter with name and description
- [ ] Protocol uses ONLY upgrade.mjs for file operations (no direct Read/Edit/Write)
- [ ] Flow covers: pre-flight, analyze, present, confirm, apply, verify
- [ ] Grouped report with safe/unsafe classification
- [ ] Per-file diff shown before conflict resolution
- [ ] Protected files explicitly excluded
- [ ] settings.json always requires manual approval
- [ ] Error recovery for network, partial apply, git dirty
- [ ] Restart reminder at end
- [ ] < 200 LOC (estimated: ~120 LOC)

---

### Task 3: Update CLAUDE.md skills tables + localization

**Files:**
- Modify: `template/CLAUDE.md:160` -- add upgrade row after diagram row
- Modify: `CLAUDE.md:160` -- add upgrade row after eval row
- Modify: `template/CLAUDE.md:188` -- add upgrade trigger to auto-selection table
- Modify: `CLAUDE.md:187` -- add upgrade trigger to auto-selection table
- Modify: `.claude/rules/localization.md:28` -- add Russian triggers before `## Action`

**Context:**
Register the new skill in all discovery points so Claude can find and activate it. Three files: template CLAUDE.md (for all DLD users), root CLAUDE.md (DLD repo itself), and localization.md (Russian triggers, DLD-specific).

**Step 1: Add to template/CLAUDE.md skills table**

In `template/CLAUDE.md`, after line 160 (`| **diagram** | Generate professional Excalidraw diagrams from description or code analysis |`), insert:

```markdown
| **upgrade** | Upgrade DLD framework from latest GitHub template |
```

**Step 2: Add to template/CLAUDE.md auto-selection triggers**

In `template/CLAUDE.md`, after line 188 (`| "retrofit", "brownfield", "reassess project" | retrofit |`), insert:

```markdown
| "upgrade DLD", "update framework", "обнови DLD" | upgrade |
```

**Step 3: Add to root CLAUDE.md skills table**

In `CLAUDE.md`, after line 160 (`| **eval** | Agent prompt eval suite -- golden datasets + LLM-as-Judge scoring |`), insert:

```markdown
| **upgrade** | Upgrade DLD framework from latest GitHub template |
```

**Step 4: Add to root CLAUDE.md auto-selection triggers**

In `CLAUDE.md`, after line 187 (`| "retrofit", "brownfield", "reassess project" | retrofit |`), insert:

```markdown
| "upgrade DLD", "update framework", "обнови DLD" | upgrade |
```

**Step 5: Add Russian triggers to localization.md**

In `.claude/rules/localization.md`, before the `## Action` section (line 30), insert:

```markdown
| "обнови DLD", "апгрейд", "обнови скиллы", "обнови фреймворк" | `/upgrade` |
```

**Acceptance Criteria:**
- [ ] `upgrade` row appears in template/CLAUDE.md skills table
- [ ] `upgrade` row appears in root CLAUDE.md skills table
- [ ] Auto-selection trigger for "upgrade DLD" in both CLAUDE.md files
- [ ] Russian triggers in localization.md: "обнови DLD", "апгрейд", "обнови скиллы", "обнови фреймворк"
- [ ] No duplicate rows or broken table formatting

---

### Task 4: Sync template to root .claude

**Files:**
- Create: `.claude/scripts/upgrade.mjs` (copy from `template/.claude/scripts/upgrade.mjs`)
- Create: `.claude/skills/upgrade/SKILL.md` (copy from `template/.claude/skills/upgrade/SKILL.md`)

**Context:**
DLD repo has two copies of `.claude/` -- template (universal) and root (DLD-specific). After creating files in template, sync to root. This is per `template-sync.md` rule.

**Step 1: Copy upgrade.mjs**

```bash
cp template/.claude/scripts/upgrade.mjs .claude/scripts/upgrade.mjs
```

**Step 2: Create upgrade skill directory and copy SKILL.md**

```bash
mkdir -p .claude/skills/upgrade
cp template/.claude/skills/upgrade/SKILL.md .claude/skills/upgrade/SKILL.md
```

**Step 3: Verify sync**

```bash
diff template/.claude/scripts/upgrade.mjs .claude/scripts/upgrade.mjs
diff template/.claude/skills/upgrade/SKILL.md .claude/skills/upgrade/SKILL.md
```

Expected: no output (files identical).

**Acceptance Criteria:**
- [ ] `.claude/scripts/upgrade.mjs` identical to template version
- [ ] `.claude/skills/upgrade/SKILL.md` identical to template version
- [ ] `diff` commands return empty output

---

### Execution Order

Task 1 --> Task 2 --> Task 3 --> Task 4

All tasks are sequential. Task 4 depends on Tasks 1 and 2 (files must exist in template first). Task 3 is logically independent but ordered after 1-2 for clean commits.

### Dependencies

- Task 1: standalone (no dependencies on other tasks)
- Task 2: standalone (references upgrade.mjs by path but doesn't import it)
- Task 3: standalone (text edits to existing files)
- Task 4: depends on Task 1 AND Task 2 (copies their output files)

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User says "обнови DLD" | Task 2 (SKILL.md trigger) | ✓ |
| 2 | Claude runs pre-flight checks | Task 2 (SKILL.md) + Task 1 (script) | ✓ |
| 3 | Script fetches latest template | Task 1 (--analyze) | ✓ |
| 4 | Script compares all files | Task 1 (classification) | ✓ |
| 5 | Claude presents grouped report | Task 2 (SKILL.md) | ✓ |
| 6 | User confirms batch update | Task 2 (SKILL.md) | ✓ |
| 7 | Script copies safe files | Task 1 (--apply --groups) | ✓ |
| 8 | Claude shows diff for conflicts | Task 1 (--diff) + Task 2 | ✓ |
| 9 | User resolves each conflict | Task 2 (SKILL.md) | ✓ |
| 10 | Script copies resolved files | Task 1 (--apply --files) | ✓ |
| 11 | Script writes .dld-version | Task 1 (post-apply) | ✓ |
| 12 | Claude shows final verification | Task 2 (SKILL.md) | ✓ |

**GAPS:** None — all steps covered.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Clean analyze returns valid JSON | `--analyze --local` on project with .claude/ | JSON with files.identical, files.new, files.different, files.protected, summary.total | deterministic | codebase scout | P0 |
| EC-2 | Protected files never in apply list | `--analyze` on project with CLAUDE.md modified | CLAUDE.md appears in files.protected, NOT in files.different | deterministic | devil DA-7 | P0 |
| EC-3 | Dirty git tree → script refuses | `--analyze` with uncommitted changes | Exit code 1, stderr contains "commit or stash" | deterministic | devil DA-4 | P0 |
| EC-4 | New files detected correctly | Template has file X, user project doesn't | X appears in files.new | deterministic | external scout | P0 |
| EC-5 | Identical files detected correctly | User file SHA256 matches template file | File appears in files.identical, NOT files.different | deterministic | patterns scout | P0 |
| EC-6 | Apply copies files deterministically | `--apply --groups safe` with 5 safe files | All 5 files copied, report shows applied: 5 | deterministic | user requirement | P0 |
| EC-7 | Verification gate: processed == total | Any analyze run | summary.processed === summary.total | deterministic | external scout | P0 |
| EC-8 | .dld-version written after apply | Successful `--apply` run | .dld-version exists, contains valid JSON with template_commit | deterministic | external scout | P1 |
| EC-9 | Diff mode outputs unified diff | `--diff --file .claude/skills/spark/SKILL.md` | stdout contains `---` and `+++` diff markers | deterministic | user requirement | P1 |
| EC-10 | User-only files preserved | User has .claude/rules/my-custom.md not in template | File appears in files.user_only, never deleted | deterministic | devil DA-7 | P0 |
| EC-11 | Node < 18 warning for hooks | Run on Node 16 | stderr warning about hooks, script still runs for non-hook files | deterministic | devil DA-5 | P1 |
| EC-12 | Network failure handled | `--latest` with no network | Exit code 1, clear error message, no partial state | deterministic | devil DA-6 | P1 |
| EC-13 | settings.json always flagged for review | settings.json differs | Appears in files.different, NEVER in auto-apply groups | deterministic | codebase scout | P0 |

### Coverage Summary
- Deterministic: 13 | Integration: 0 | LLM-Judge: 0 | Total: 13 (min 3 ✓)

### TDD Order
1. EC-3 (dirty tree guard — simplest safety check)
2. EC-2 (protected files — core classification)
3. EC-1 (valid JSON output — full analysis)
4. EC-5 (identical detection — SHA256 comparison)
5. EC-4 (new file detection)
6. EC-10 (user-only preservation)
7. EC-13 (settings.json always-ask)
8. EC-6 (apply mode — copies files)
9. EC-7 (verification gate)
10. EC-8 (.dld-version writing)
11. EC-9 (diff mode)
12. EC-11, EC-12 (edge cases)

---

## Definition of Done

### Functional
- [ ] `node .claude/scripts/upgrade.mjs --analyze --local` returns valid JSON report
- [ ] `node .claude/scripts/upgrade.mjs --apply` copies files deterministically
- [ ] `/upgrade` skill activated by trigger words
- [ ] Full user journey works: analyze → present → confirm → apply → verify

### Tests
- [ ] All 13 eval criteria pass
- [ ] Coverage not decreased

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions
- [ ] upgrade.mjs < 400 LOC
- [ ] SKILL.md < 400 LOC

---

## Future Tasks (out of scope for FTR-137)

| Task | Description | Trigger |
|------|-------------|---------|
| TECH-XXX | create-dld writes .dld-version at install time | After FTR-137 ships |
| TECH-XXX | Per-file SHA256 checksums in .dld-version | When users request smart classification |
| TECH-XXX | Rename detection manifest | When DLD refactors file paths |
| TECH-XXX | `git merge-file` for .mjs/.json 3-way merge | When users report merge issues |

---

## Autopilot Log
[Auto-populated by autopilot during execution]
