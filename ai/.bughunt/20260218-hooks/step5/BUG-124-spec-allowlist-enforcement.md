# BUG-124 — Spec Allowlist Enforcement

**Priority:** P1
**Group:** Spec Allowlist Enforcement
**Findings:** F-011, F-012, F-013, F-014, F-015, F-016, F-017
**Affected files:**
- `.claude/hooks/utils.mjs` (lines 257–383)
- `.claude/hooks/pre-edit.mjs` (lines 111, 65–71)

---

## Summary

Seven independent bypass vectors weaken the file allowlist enforcement system. Each can be triggered separately. Collectively they mean the spec-based file protection boundary has multiple holes: regex truncation drops valid paths, path normalization mismatches cause false denials, heading-level variance silently bypasses enforcement, CRLF line endings corrupt section parsing, an unvalidated env var enables arbitrary file read and full bypass, and a phantom `SEC` prefix creates non-existent spec paths.

The allowlist system is the primary safety mechanism preventing Claude Code from editing files outside a task's declared scope. Bypasses here mean Claude can edit any file during autopilot runs.

---

## Root Cause Analysis

### F-011: extractAllowedFiles regex truncates paths with special characters

```javascript
// utils.mjs:271 — CURRENT (BROKEN)
const pathMatch = trimmed.match(
  /[`*\-]*\s*([a-zA-Z0-9_./@*-]+(?:\.[a-zA-Z0-9*]+)?(?::\d+(?:-\d+)?)?)[`*]*/
);
```

**Character class `[a-zA-Z0-9_./@*-]` does not include:** `+`, `(`, `)`, space, `~`, `!`, `{`, `}`, `[`, `]`

**Impact examples:**
- `` `src/c++/parser.cpp` `` → extracted as `src/c` (stops at first `+`)
- `` `src/auth/handler (v2).py` `` → extracted as `src/auth/handler` (stops at space)
- `` `src/feature (draft)/main.py` `` → extracted as `src/feature`

In each case the real file path does not match the truncated extracted path, so `isFileAllowed()` returns false — a false denial that blocks legitimate edits the spec author intended to allow.

### F-012: isFileAllowed strips ./ from filePath but NOT from allowed entries

```javascript
// utils.mjs:342 — strips ./ from filePath
filePath = normalize(filePath).replace(/^\.\//, '');

// utils.mjs:371 — does NOT strip ./ from allowed entry
allowed = normalize(allowed).replace(/\\/g, '/');  // only win32 backslash fix
```

A spec entry of `./src/foo.py` becomes the allowed string `./src/foo.py` (after normalize, still has `./`). The filePath is `src/foo.py` (stripped). Direct comparison: `'src/foo.py' === './src/foo.py'` → false. Glob match also fails because the pattern has the prefix. Result: legitimate file denied despite being in the spec.

### F-013: extractAllowedFiles regex only matches `##` heading level

```javascript
// utils.mjs:260 — CURRENT (BROKEN)
const match = content.match(/## Allowed Files\s*\n([\s\S]*?)(?=\n##|\s*$)/i);
```

Only level-2 headings (`##`) match. If a spec uses `### Allowed Files` (level 3), the regex returns `null`, `extractAllowedFiles` returns `{ files: [], error: false }`, and `isFileAllowed` at line 365–366 returns `{ allowed: true }` (no section = allow all). This means a spec author who uses `###` gets **no enforcement at all** rather than their intended enforcement.

### F-014: Absolute path with divergent symlink resolution causes false denial

```javascript
// pre-edit.mjs:65-71 — normalizePath strips projectDir prefix
// utils.mjs:340 — isFileAllowed receives the result
```

On macOS, `CLAUDE_PROJECT_DIR` may resolve via `/var/...` while `realpathSync` yields `/private/var/...`. If Claude Code provides an absolute path and `normalizePath()` fails to strip the mismatched prefix, `isFileAllowed` receives a full absolute path like `/private/var/project/src/api.py`. No relative spec pattern like `src/api.py` matches an absolute path. The file is denied even though `src/api.py` is in the allowlist.

**Autopilot impact:** This manifests in autopilot worktree mode on macOS, where it causes spurious denials that interrupt task execution.

### F-015: CLAUDE_CURRENT_SPEC_PATH env var has no path validation — arbitrary file read + allowlist bypass

```javascript
// pre-edit.mjs:111 — CURRENT (BROKEN)
const specPath = process.env.CLAUDE_CURRENT_SPEC_PATH || inferSpecFromBranch();

// utils.mjs:259 — reads specPath with no validation
const content = readFileSync(specPath, 'utf-8');

// utils.mjs:365-366 — no section = allow all
if (result.files.length === 0) {
  return { allowed: true, allowedFiles: [] };
}
```

**Attack path:**
1. Set `CLAUDE_CURRENT_SPEC_PATH=/etc/passwd`
2. Hook reads `/etc/passwd` (arbitrary file read)
3. `/etc/passwd` contains no `## Allowed Files` section
4. `files.length === 0` → `isFileAllowed` returns `{ allowed: true }` for **every** file
5. All file-write protection is bypassed for the session

**Realistic scenario:** Any process in the same shell session that can set environment variables can bypass all hook enforcement.

### F-016: extractAllowedFiles regex fails on CRLF line endings

```javascript
// utils.mjs:260 — CURRENT (BROKEN)
const match = content.match(/## Allowed Files\s*\n([\s\S]*?)(?=\n##|\s*$)/i);
//                                                              ^^^ does not match \r\n##
```

On Windows-originated spec files or specs committed with `autocrlf=true`, line endings are `\r\n`. The lookahead `(?=\n##)` does not match `\r\n##`. The regex captures from `## Allowed Files` all the way to EOF (because `\r\n##` never terminates the match), including files listed in subsequent sections. Files from `## Test Requirements`, `## Tasks`, etc. are incorrectly added to the allowed list.

### F-017: SEC prefix in spec inference regex is not in CLAUDE.md backlog rules

```javascript
// utils.mjs:310
const msgMatch = commitMsg.match(/(FTR|BUG|TECH|ARCH|SEC)-\d+/i);

// utils.mjs:320
const match = branch.match(/(FTR|BUG|TECH|ARCH|SEC)-\d+/i);
```

CLAUDE.md states: "Prefixes: BUG, FTR, TECH, ARCH only (4 types)". `SEC` is not a valid prefix. Branches named `SEC-042-auth-hardening` trigger spec inference, construct path `ai/features/SEC-042-auth-hardening.md`, find no file (it can never legally exist), and return `null`. With no spec path, `isFileAllowed` returns `{ allowed: true }` — all file writes are allowed, bypassing enforcement.

---

## Affected Files

| File | Line | Issue |
|------|------|-------|
| `.claude/hooks/utils.mjs` | 260 | CRLF regex lookahead (F-016) |
| `.claude/hooks/utils.mjs` | 260 | `##`-only heading match (F-013) |
| `.claude/hooks/utils.mjs` | 271 | Path extraction character class (F-011) |
| `.claude/hooks/utils.mjs` | 310, 320 | SEC prefix in inference regex (F-017) |
| `.claude/hooks/utils.mjs` | 342, 371 | `./` strip asymmetry (F-012) |
| `.claude/hooks/pre-edit.mjs` | 111 | Unvalidated env var spec path (F-015) |
| `.claude/hooks/pre-edit.mjs` | 65–71 | Symlink divergence in normalizePath (F-014) |

---

## Fix Description

### Fix F-011: Extract backtick-delimited paths first

```javascript
// utils.mjs — extractAllowedFiles inner loop — FIXED
for (const line of section.split('\n')) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith('#')) continue;

  // Strategy 1: backtick-delimited path (handles any filename characters)
  const btMatch = trimmed.match(/`([^`]+)`/);
  if (btMatch) {
    let p = btMatch[1].replace(/:\d+(-\d+)?$/, ''); // strip line range
    if (p && !p.startsWith('|')) allowed.push(p);
    continue;
  }

  // Strategy 2: bold-delimited path
  const boldMatch = trimmed.match(/\*\*([^*]+)\*\*/);
  if (boldMatch) {
    let p = boldMatch[1].replace(/:\d+(-\d+)?$/, '');
    if (p && !p.startsWith('|')) allowed.push(p);
    continue;
  }

  // Strategy 3: fallback — existing regex (handles plain paths)
  const pathMatch = trimmed.match(
    /[`*\-]*\s*([a-zA-Z0-9_./@*+()\[\] -]+(?:\.[a-zA-Z0-9*]+)?(?::\d+(?:-\d+)?)?)[`*]*/
  );
  if (pathMatch) {
    let p = pathMatch[1].trim().replace(/:\d+(-\d+)?$/, '');
    if (p && !p.startsWith('|')) allowed.push(p);
  }
}
```

### Fix F-012: Strip ./ from allowed entries as well

```javascript
// utils.mjs:371 — FIXED
allowed = normalize(allowed).replace(/\\/g, '/').replace(/^\.\//, '');
//                                                ^^^^^^^^^^^^^^^^^^^ add this
```

### Fix F-013 + F-016: Fix heading regex and normalize CRLF

```javascript
// utils.mjs:259-261 — FIXED
export function extractAllowedFiles(specPath) {
  try {
    let content = readFileSync(specPath, 'utf-8');
    content = content.replace(/\r\n/g, '\n'); // normalize CRLF (F-016)
    const match = content.match(/^#{1,6}\s+Allowed Files\s*\n([\s\S]*?)(?=\n#{1,6}\s|\s*$)/im);
    //                           ^^^^^^^^^ any heading level 1-6 (F-013)
    if (!match) return { files: [], error: false };
    // ... rest unchanged
```

### Fix F-014: Use realpathSync in normalizePath

```javascript
// pre-edit.mjs:65-71 — FIXED
import { realpathSync } from 'fs';

function normalizePath(filePath, projectDir) {
  // Resolve symlinks to get canonical paths before prefix strip
  let absFile = filePath.startsWith('/') ? filePath : join(projectDir, filePath);
  try { absFile = realpathSync(absFile); } catch { /* file may not exist yet */ }
  let canonicalProject = projectDir;
  try { canonicalProject = realpathSync(projectDir); } catch { /* use as-is */ }

  if (absFile.startsWith(canonicalProject + '/')) {
    return absFile.slice(canonicalProject.length + 1);
  }
  return filePath; // fallback: return as-is
}
```

### Fix F-015: Validate CLAUDE_CURRENT_SPEC_PATH

```javascript
// pre-edit.mjs:111 — FIXED
import { realpathSync } from 'fs';
import { join } from 'path';

function resolveSpecPath(envValue, projectDir) {
  if (!envValue) return null;
  try {
    const resolved = realpathSync(envValue);
    const featuresDir = join(realpathSync(projectDir), 'ai', 'features');
    if (!resolved.startsWith(featuresDir + '/')) {
      logHookError('pre-edit', `CLAUDE_CURRENT_SPEC_PATH escapes ai/features/: ${envValue}`);
      return null; // reject — treat as no spec (allow all, but don't read arbitrary files)
    }
    if (!resolved.endsWith('.md')) {
      logHookError('pre-edit', `CLAUDE_CURRENT_SPEC_PATH not a .md file: ${envValue}`);
      return null;
    }
    return resolved;
  } catch {
    return null; // file does not exist or lstat failed — treat as no spec
  }
}

// Usage:
const envSpec = process.env.CLAUDE_CURRENT_SPEC_PATH;
const specPath = envSpec
  ? resolveSpecPath(envSpec, getProjectDir())
  : inferSpecFromBranch();
```

### Fix F-017: Remove SEC from inference regex

```javascript
// utils.mjs:310 — FIXED
const msgMatch = commitMsg.match(/(FTR|BUG|TECH|ARCH)-\d+/i);
// Remove SEC ^^

// utils.mjs:320 — FIXED
const match = branch.match(/(FTR|BUG|TECH|ARCH)-\d+/i);
// Remove SEC ^^
```

---

## Impact Tree

### Upstream (who depends on allowlist enforcement being correct?)
- Autopilot multi-task runs — must not edit files outside task scope
- `pre-edit.mjs` — primary consumer of `isFileAllowed()` and `extractAllowedFiles()`
- All task specs in `ai/features/` that declare `## Allowed Files` sections

### Downstream (what does allowlist enforcement depend on?)
- `utils.mjs:extractAllowedFiles` — parses spec, returns file list
- `utils.mjs:isFileAllowed` — checks filePath against list
- `utils.mjs:inferSpecFromBranch` — discovers spec from git branch
- `utils.mjs:minimatch` — glob matching within isFileAllowed (see BUG-125)
- `pre-edit.mjs:normalizePath` — converts absolute path to relative before check

### Risk if NOT fixed
- F-015 (SEC bypass via env): Attacker-controlled env var defeats all file write protection
- F-011 (regex truncation): Files with `+`, `(`, `)`, spaces in names are always denied — false denials break autopilot
- F-013 (heading level): Entire spec enforcement silently inactive when author uses `###`
- F-012 (dot-slash): False denials for specs using `./src/` style paths
- F-016 (CRLF): Over-broad allowlist on Windows-committed specs — extra files incorrectly allowed
- F-017 (SEC prefix): Phantom spec path inference disables enforcement on SEC branches
- F-014 (symlink): False denials in autopilot on macOS

---

## Definition of Done

- [ ] `extractAllowedFiles`: backtick-first extraction strategy implemented (F-011)
- [ ] `extractAllowedFiles`: CRLF normalization added before regex (F-016)
- [ ] `extractAllowedFiles`: heading regex updated to match any `#` level 1–6 (F-013)
- [ ] `isFileAllowed`: `./` stripped from allowed entries (F-012)
- [ ] `normalizePath` in `pre-edit.mjs`: uses `realpathSync` for both file and project dir (F-014)
- [ ] `pre-edit.mjs`: `CLAUDE_CURRENT_SPEC_PATH` validated against `ai/features/` before use (F-015)
- [ ] `inferSpecFromBranch`: `SEC` removed from both regex patterns (F-017)
- [ ] All existing allowlist tests pass
- [ ] New test: path with `+` in name is correctly allowed when in spec (F-011)
- [ ] New test: `### Allowed Files` heading enforces correctly (F-013)
- [ ] New test: `./src/foo.py` in spec allows edit of `src/foo.py` (F-012)
- [ ] New test: CRLF spec does not bleed into next section (F-016)
- [ ] New test: `CLAUDE_CURRENT_SPEC_PATH=/etc/passwd` is rejected, does not allow all (F-015)
- [ ] New test: SEC branch does not trigger phantom spec inference (F-017)

---

## Test Requirements

```javascript
// F-011: Backtick path with + character
test('extractAllowedFiles: extracts path with + character', () => {
  const spec = '## Allowed Files\n`src/c++/parser.cpp`\n';
  // assert: files = ['src/c++/parser.cpp']
});

// F-012: ./ prefix in spec entry
test('isFileAllowed: ./src/foo.py in spec allows src/foo.py', () => {
  // spec has ./src/foo.py, filePath is src/foo.py
  // assert: allowed = true
});

// F-013: Level-3 heading
test('extractAllowedFiles: ### Allowed Files is recognized', () => {
  const spec = '### Allowed Files\n`src/main.py`\n';
  // assert: files = ['src/main.py']
});

// F-015: Malicious CLAUDE_CURRENT_SPEC_PATH
test('pre-edit: CLAUDE_CURRENT_SPEC_PATH=/etc/passwd is rejected', async () => {
  const result = await runHook('pre-edit', {
    tool: 'Write', file_path: 'src/anything.py',
    env: { CLAUDE_CURRENT_SPEC_PATH: '/etc/passwd' }
  });
  // assert: hook does NOT return allow-all due to missing section
  // assert: logHookError called with path-escape message
});

// F-016: CRLF spec
test('extractAllowedFiles: CRLF spec does not include next section files', () => {
  const spec = '## Allowed Files\r\n`src/foo.py`\r\n\r\n## Other\r\n`src/bar.py`\r\n';
  // assert: files = ['src/foo.py'] (not src/bar.py)
});

// F-017: SEC branch prefix
test('inferSpecFromBranch: SEC prefix does not infer spec path', async () => {
  // mock branch = 'SEC-042-auth'
  // assert: returns null (no spec inferred)
});
```

---

## Change History

| Date | What | Task | Who |
|------|------|------|-----|
| 2026-02-18 | Spec created from Bug Hunt 20260218-hooks | BUG-124 | bughunt |
