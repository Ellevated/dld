# BUG-128 — Minor Quality

**Priority:** P3
**Group:** Minor Quality
**Findings:** F-031, F-032, F-033, F-034, F-035, F-036, F-037, F-038, F-039, F-040
**Scope:** `.claude/hooks/`

---

## Overview

Ten low-severity quality issues collected into one spec. Each is individually small. Grouped
here for efficient implementation in a single pass.

| ID | File | Line | Title | Severity |
|----|------|------|-------|----------|
| F-031 | `post-edit.mjs` | 27 | Argument injection into ruff via filePath starting with `--` | low |
| F-032 | `utils.mjs` | 51 | `DLD_HOOK_LOG_FILE` env var allows arbitrary file append | low |
| F-033 | `utils.mjs` | 235 | `matchesPattern()` wrapper inconsistently used | low |
| F-034 | `session-end.mjs` | 29 | Diary threshold `>5` hardcoded, no config path | low |
| F-035 | `pre-edit.mjs` | 156 | LOC warning and sync zone reminder mutually exclusive | low |
| F-036 | `validate-spec-complete.mjs` | 39 | Only first staged spec file checked | low |
| F-037 | `pre-edit.mjs` | 111 | Empty string `CLAUDE_CURRENT_SPEC_PATH` triggers inference | low |
| F-038 | `pre-edit.mjs` | 154 | `warnThreshold=1.0` makes warning unreachable | low |
| F-039 | `run-hook.mjs` | 35 | Worktree root parsing brittle, no `existsSync` validation | low |
| F-040 | `validate-spec-complete.mjs` | 12 | `stripCodeBlocks` fragile with nested backticks | low |

---

## Root Cause Analysis Per Finding

### F-031 — ruff argument injection via `--` prefixed filePath

`post-edit.mjs` calls `execFileSync('ruff', ['format', filePath])`. Although `execFileSync` with
an array prevents shell injection, ruff interprets arguments starting with `--` as CLI flags.
A `filePath` of `--config=/tmp/evil.toml` would be passed as a ruff CLI flag. The `existsSync`
check on line 68 prevents most cases but does not guard against flag-like paths.

**Fix:** Add an explicit guard before the ruff call:
```javascript
if (filePath.startsWith('-')) {
  postContinue();
  return;
}
```

### F-032 — DLD_HOOK_LOG_FILE allows arbitrary file append

`utils.mjs:51` sets `LOG_FILE = process.env.DLD_HOOK_LOG_FILE` with no path validation. Any
process that can set this env var can redirect hook debug output to an append-mode write against
any path the Node.js process can write to (`~/.bashrc`, `~/.gitconfig`, etc.). Content is JSON
(not attacker-controlled), but file corruption is possible.

**Fix:** Validate `LOG_FILE` at startup:
```javascript
const rawLogFile = process.env.DLD_HOOK_LOG_FILE || null;
const LOG_FILE = (() => {
  if (!rawLogFile) return null;
  const home = homedir();
  const tmpDir = resolve('/tmp');
  if (!rawLogFile.startsWith(home) && !rawLogFile.startsWith(tmpDir)) return null;
  try { if (lstatSync(rawLogFile).isSymbolicLink()) return null; } catch {}
  return rawLogFile;
})();
```

### F-033 — matchesPattern() wrapper inconsistently used

`utils.mjs:235` defines `matchesPattern()` as a one-line wrapper around `minimatch()`. Line 350
uses `matchesPattern()` but line 377 calls `minimatch()` directly, bypassing the wrapper. If
`matchesPattern()` is later modified (e.g., to add logging or normalization), line 377 would diverge.

**Fix:** Replace line 377's direct `minimatch()` call with `matchesPattern()`:
```javascript
// Line 377 — BEFORE
} else if (minimatch(filePath, allowed)) {

// Line 377 — AFTER
} else if (matchesPattern(filePath, allowed)) {
```

### F-034 — session-end diary threshold hardcoded

`session-end.mjs:29` uses `if (pendingCount > 5)` with no config path. It is the only hook that
does not call `loadConfig()`. Users with different workflow cadences cannot customize this threshold.

**Fix:** Add `sessionEnd.pendingThreshold` to `hooks.config.mjs` (default: 5) and have
`session-end.mjs` call `loadConfig()`:
```javascript
// hooks.config.mjs — add to config object
sessionEnd: {
  pendingThreshold: 5,
},

// session-end.mjs — AFTER
const config = await loadConfig();
const pendingThreshold = config?.sessionEnd?.pendingThreshold ?? 5;
if (pendingCount > pendingThreshold) { ... }
```

### F-035 — LOC warning and sync zone reminder mutually exclusive

`pre-edit.mjs:156` has an early `return` after the LOC warning fires. This prevents the sync
zone reminder (which checks if the file exists in `template/.claude/`) from ever being shown
when a file is both over LOC limit AND in a sync zone.

**Fix:** Collect all soft warnings into an array and emit them together:
```javascript
const warnings = [];

if (loc >= warnLoc && loc < maxLoc) {
  warnings.push(`File is approaching LOC limit (${loc}/${maxLoc} lines). Consider splitting.`);
}

if (isInSyncZone(filePath)) {
  warnings.push(`This file exists in template/.claude/ — remember to sync changes.`);
}

if (warnings.length > 0) {
  askTool(warnings.join('\n\n---\n\n'));
  return;
}
```

### F-036 — Only first staged spec file checked for Impact Tree

`validate-spec-complete.mjs:39` uses `Array.find()` which returns only the first matching spec
file. If two spec files are staged simultaneously, only the first is checked. The second can
have unfilled Impact Tree checkboxes and be committed.

**Fix:** Use `Array.filter()` and check all staged spec files:
```javascript
// BEFORE
const specFile = stagedFiles.split('\n').find(f => /^ai\/features\/.*\.md$/.test(f));
if (specFile && existsSync(join(projectDir, specFile))) {
  checkSpec(join(projectDir, specFile));
}

// AFTER
const specFiles = stagedFiles.split('\n').filter(f => /^ai\/features\/.*\.md$/.test(f));
for (const specFile of specFiles) {
  const absPath = join(projectDir, specFile);
  if (existsSync(absPath)) {
    checkSpec(absPath);  // blocks on first failure
  }
}
```

### F-037 — Empty CLAUDE_CURRENT_SPEC_PATH triggers inference

`pre-edit.mjs:111`:
```javascript
const specPath = process.env.CLAUDE_CURRENT_SPEC_PATH || inferSpecFromBranch();
```
JavaScript's `||` treats empty string as falsy. Setting `CLAUDE_CURRENT_SPEC_PATH=''` to
disable enforcement calls `inferSpecFromBranch()` instead — the opposite of the operator's intent.

**Fix:** Use explicit undefined/empty check:
```javascript
const envSpec = process.env.CLAUDE_CURRENT_SPEC_PATH;
const specPath = (envSpec !== undefined && envSpec !== '')
  ? envSpec
  : inferSpecFromBranch();
```

### F-038 — warnThreshold=1.0 makes warning unreachable

`pre-edit.mjs:154`:
```javascript
const warnLoc = Math.floor(maxLoc * warnThreshold);
```
When `warnThreshold=1.0`, `warnLoc === maxLoc`. The hard-block condition `loc >= maxLoc` fires
first; the warning condition `loc >= warnLoc` is never reached.

**Fix:** Cap `warnLoc` to one below `maxLoc`:
```javascript
const warnLoc = Math.min(Math.floor(maxLoc * warnThreshold), maxLoc - 1);
```
Also document in `hooks.config.mjs` that `warnThreshold` must be less than `1.0`.

### F-039 — run-hook.mjs worktree root parsing brittle

`run-hook.mjs:35`:
```javascript
root = output.split('\n')[0].replace('worktree ', '').trim();
```
No validation that `root` is a real directory. If git output format changes or is malformed,
`root` is a garbage string, `hookPath` points to nothing, and all hooks silently pass (fail-open).

**Fix:**
```javascript
const firstLine = output.split('\n').find(l => l.startsWith('worktree '));
root = firstLine ? firstLine.replace(/^worktree\s+/, '').trim() : null;
if (!root || !existsSync(root)) {
  logHookError('run-hook', `Invalid worktree root: ${root}. Falling back to cwd.`);
  root = process.cwd();
}
```

### F-040 — stripCodeBlocks fragile with nested backtick sequences

`validate-spec-complete.mjs:12`:
```javascript
return text.replace(/```[\s\S]*?```/g, '');
```
The non-greedy match stops at the FIRST closing triple-backtick inside a code block. Specs
with inline triple-backtick sequences inside code blocks cause partial stripping, leaving
`- [ ]` patterns from code examples in the stripped output — causing false positive
Impact Tree checkbox failures.

**Fix:** Use line-by-line fence boundary scanning:
```javascript
function stripCodeBlocks(text) {
  const lines = text.split('\n');
  const result = [];
  let inFence = false;
  for (const line of lines) {
    if (line.startsWith('```')) {
      inFence = !inFence;
      continue;
    }
    if (!inFence) result.push(line);
  }
  return result.join('\n');
}
```

---

## Affected Files

| File | Finding | Change |
|------|---------|--------|
| `.claude/hooks/post-edit.mjs` | F-031 | Guard against `filePath.startsWith('-')` |
| `.claude/hooks/utils.mjs` | F-032 | Validate `DLD_HOOK_LOG_FILE` path |
| `.claude/hooks/utils.mjs` | F-033 | Replace `minimatch()` at line 377 with `matchesPattern()` |
| `.claude/hooks/session-end.mjs` | F-034 | Call `loadConfig()`, use `pendingThreshold` from config |
| `.claude/hooks/hooks.config.mjs` | F-034 | Add `sessionEnd.pendingThreshold: 5` |
| `.claude/hooks/pre-edit.mjs` | F-035 | Collect and join soft warnings |
| `.claude/hooks/validate-spec-complete.mjs` | F-036 | Use `Array.filter()` for all staged specs |
| `.claude/hooks/pre-edit.mjs` | F-037 | Use explicit undefined/empty check for env var |
| `.claude/hooks/pre-edit.mjs` | F-038 | Cap `warnLoc` to `maxLoc - 1` |
| `.claude/hooks/run-hook.mjs` | F-039 | Add `existsSync(root)` validation |
| `.claude/hooks/validate-spec-complete.mjs` | F-040 | Rewrite `stripCodeBlocks()` with line-by-line scanning |

---

## Impact Tree

### Upstream

- `post-edit.mjs` — called by Claude Code PostToolUse hook after every file write
- `utils.mjs` logging — called on every hook invocation when `DLD_HOOK_LOG_FILE` set
- `validate-spec-complete.mjs` — called by pre-commit hook on every `git commit`
- `pre-edit.mjs` — called by Claude Code PreToolUse hook before every file write
- `run-hook.mjs` — entry point for all hooks, called by Claude Code

### Downstream (effects of fixes)

- F-031: `--config=/tmp/evil.toml` type filePaths no longer passed to ruff
- F-032: Arbitrary file append via `DLD_HOOK_LOG_FILE` prevented
- F-033: Future `matchesPattern()` modifications apply uniformly
- F-034: Users can customize diary reminder threshold via config
- F-035: Developers see both LOC warning AND sync reminder when both apply
- F-036: All staged spec files checked, not just first
- F-037: `CLAUDE_CURRENT_SPEC_PATH=''` correctly disables enforcement
- F-038: `warnThreshold=1.0` config no longer silently suppresses all warnings
- F-039: Malformed `git worktree list` output logged and handled gracefully
- F-040: Specs with code blocks containing triple-backtick sequences validated correctly

### Files to verify after change

- [ ] `test/post-edit.test.mjs` — add test for `--` prefixed filePath
- [ ] `test/utils.test.mjs` — add test for `DLD_HOOK_LOG_FILE` validation
- [ ] `test/utils.test.mjs` — verify `matchesPattern` used consistently
- [ ] `test/session-end.test.mjs` — test `pendingThreshold` config
- [ ] `test/pre-edit.test.mjs` — test LOC + sync zone warning combination
- [ ] `test/validate-spec-complete.test.mjs` — test multiple staged specs
- [ ] `test/pre-edit.test.mjs` — test empty string `CLAUDE_CURRENT_SPEC_PATH`
- [ ] `test/pre-edit.test.mjs` — test `warnThreshold=1.0`
- [ ] `test/run-hook.test.mjs` — test malformed worktree output
- [ ] `test/validate-spec-complete.test.mjs` — test nested backtick in code block

---

## Definition of Done

- [ ] F-031: `filePath` starting with `-` causes `postContinue()` without calling ruff
- [ ] F-032: `DLD_HOOK_LOG_FILE` pointing outside `$HOME`/`/tmp` is ignored at startup
- [ ] F-033: No direct `minimatch()` calls in `isFileAllowed()` — all go through `matchesPattern()`
- [ ] F-034: `session-end.mjs` reads `pendingThreshold` from config; `hooks.config.mjs` has default of 5
- [ ] F-035: Both LOC warning and sync zone reminder shown together when both conditions met
- [ ] F-036: All staged spec files (not just first) checked for Impact Tree completeness
- [ ] F-037: `CLAUDE_CURRENT_SPEC_PATH=''` disables enforcement (does not trigger inference)
- [ ] F-038: `warnThreshold=1.0` produces `warnLoc = maxLoc - 1` (warning is reachable)
- [ ] F-039: `existsSync(root)` check added; failure falls back to `cwd` with error log
- [ ] F-040: `stripCodeBlocks()` uses line-by-line fence scanner; handles nested backtick sequences
- [ ] All existing hook tests pass (`./test fast`)

---

## Test Requirements

### Unit tests to add (representative selection)

```javascript
// test/post-edit.test.mjs
test('filePath starting with -- is not passed to ruff', async () => {
  const result = await runHook('post-edit', {
    tool_input: { file_path: '--config=/tmp/evil.toml' }
  });
  // Should postContinue without calling ruff
  assert.equal(result.exit_code, 0);
});

// test/pre-edit.test.mjs
test('empty CLAUDE_CURRENT_SPEC_PATH disables enforcement', async () => {
  const result = await runHook('pre-edit', {
    tool_input: { file_path: 'src/foo.py' },
    env: { CLAUDE_CURRENT_SPEC_PATH: '' }
  });
  // Should not attempt spec lookup
  assert.equal(result.decision, 'allow');
});

test('warnThreshold=1.0 still shows warning at maxLoc-1 lines', async () => {
  // Test with config: { loc: { maxLoc: 400, warnThreshold: 1.0 } }
  // File at 399 lines should still show warning
});

// test/validate-spec-complete.test.mjs
test('all staged spec files checked, not just first', async () => {
  // Stage two spec files, second has unchecked box
  // Verify hook blocks on second file
});

test('stripCodeBlocks handles code block with triple-backtick sequence inside', () => {
  const input = '```js\nconst x = `hello`\n```\n- [ ] unchecked';
  const stripped = stripCodeBlocks(input);
  assert(!stripped.includes('- [ ]'));  // false positive eliminated
});

// test/run-hook.test.mjs
test('malformed git worktree output falls back to cwd with error log', async () => {
  // Mock git returning malformed output
  // Verify hook uses cwd and logs error
});
```

---

## Change History

| Date | What | Who |
|------|------|-----|
| 2026-02-18 | Created from bughunt 20260218-hooks P3 group | solution-architect |
