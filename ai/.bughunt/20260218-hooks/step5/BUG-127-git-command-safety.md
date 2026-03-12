# BUG-127 — Git Command Safety

**Priority:** P2
**Group:** Git Command Safety
**Findings:** F-027, F-028, F-029, F-030
**Scope:** `.claude/hooks/`

---

## Root Cause Analysis

The pre-bash hook implements defense-in-depth for dangerous git commands. Three gaps exist in
the pattern matching logic, each independently allowing a dangerous command through:

1. **`git clean -fx` not blocked (F-027)** — `isDestructiveClean()` requires BOTH force (`-f`)
   AND directory (`-d`) flags. The `-x` flag (remove ignored files including `.env`, `node_modules`,
   secrets) is not checked. `git clean -fx` satisfies `hasForce=true` but `hasDir=false`, so the
   function returns `false` and the command is allowed. This can destroy `.env` files and other
   secrets without any safety prompt.

2. **Merge `--ff-only` bypass exploitable with `--no-ff` (F-028)** — the bypass check uses
   `command.includes('--ff-only')` as the sole guard. A command `git merge --ff-only --no-ff develop`
   contains `--ff-only` and passes the bypass, but git processes flags left-to-right: `--no-ff`
   overrides `--ff-only`, making the merge non-fast-forward. The hook approves a command that
   executes as an unsafe merge.

3. **Force push regex misses bare `git push -f` (F-030)** — the protected-branch force-push
   pattern requires `\b(develop|main)\b` to appear in the command. A bare `git push -f` with no
   explicit branch is not blocked, even though the tracking branch might be `develop` or `main`.
   The hook cannot know the tracking branch without executing git.

4. **Force push regex edge case: `--force-with-lease=ref` (F-029)** — the negative lookahead
   `/--force\b(?!-with-lease)/` covers `--force-with-lease` but the `=<refname>` form
   (`--force-with-lease=origin/main`) has subtle edge cases depending on regex engine behavior.
   Low practical impact but the pattern can be made unambiguous.

---

## Affected Files

| File | Line | Issue |
|------|------|-------|
| `.claude/hooks/hooks.config.mjs` | 12-17 | `isDestructiveClean` missing `-x` flag check |
| `.claude/hooks/pre-bash.mjs` | 18-25 | Duplicate `isDestructiveClean` — same missing `-x` |
| `.claude/hooks/pre-bash.mjs` | 67 | `--ff-only` bypass bypassable with `--no-ff` combined |
| `.claude/hooks/hooks.config.mjs` | 52 | Force push regex: bare `git push -f` not blocked |
| `.claude/hooks/hooks.config.mjs` | 52 | Force push regex: `--force-with-lease=ref` edge case |

---

## Fix Description

### Fix 1 — isDestructiveClean: add -x flag detection (F-027)

```javascript
// hooks.config.mjs — BEFORE
function isDestructiveClean(cmd) {
  const hasForce = /(?:^|\s)-[a-z]*f/i.test(cmd);
  const hasDir = /(?:^|\s)-[a-z]*d/i.test(cmd);
  return hasForce && hasDir;
}
// git clean -fx: hasForce=true, hasDir=false → false → ALLOWED (BUG)
```

```javascript
// hooks.config.mjs — AFTER
function isDestructiveClean(cmd) {
  const hasForce = /(?:^|\s)-[a-z]*f/i.test(cmd);
  const hasDir = /(?:^|\s)-[a-z]*d/i.test(cmd);
  const hasIgnored = /(?:^|\s)-[a-z]*x/i.test(cmd);  // removes ignored files
  return hasForce && (hasDir || hasIgnored);
}
// git clean -fx: hasForce=true, hasIgnored=true → true → BLOCKED (correct)
// git clean -fd: hasForce=true, hasDir=true → true → BLOCKED (correct)
// git clean -fdx: all three → true → BLOCKED (correct)
```

Apply the same fix to the duplicate in `pre-bash.mjs`. Note: BUG-126 tracks the deduplication
of `isDestructiveClean`; once fixed there, only one location needs updating.

### Fix 2 — --ff-only bypass: reject when --no-ff also present (F-028)

```javascript
// pre-bash.mjs — BEFORE
if (command.includes('--ff-only')) continue;
// 'git merge --ff-only --no-ff develop' bypasses this (BUG)
```

```javascript
// pre-bash.mjs — AFTER
if (command.includes('--ff-only') && !command.includes('--no-ff')) continue;
// 'git merge --ff-only --no-ff develop' no longer bypasses (correct)
// 'git merge --ff-only develop' still bypasses (correct)
```

### Fix 3 — Force push: block bare 'git push -f' (F-030)

```javascript
// hooks.config.mjs — BEFORE (only blocks when branch is explicit)
/git\s+push\b(?=.*\b(develop|main)\b)(?=.*(-f\b|--force\b(?!-with-lease)))/i

// hooks.config.mjs — AFTER (add separate pattern for bare push -f)
// Pattern 1: existing — explicit branch mentioned
/git\s+push\b(?=.*\b(develop|main)\b)(?=.*(-f\b|--force\b(?!-with-lease)))/i

// Pattern 2: new — bare push with force flag and no explicit branch
// When no branch is given, tracking branch (which may be develop/main) is used
/^git\s+push\s+(-f\b|--force\b(?!-with-lease))(\s+\w+)?$/i
```

For Pattern 2, the appropriate action is `askTool` (not `denyTool`), since the tracking branch
is unknown. The user should confirm before proceeding.

### Fix 4 — Force push regex: unambiguous --force-with-lease handling (F-029)

```javascript
// hooks.config.mjs — BEFORE
/--force\b(?!-with-lease)/

// hooks.config.mjs — AFTER (covers both --force-with-lease and --force-with-lease=ref)
/--force(?!-with-lease)/
```

The `\b` word boundary is redundant here: `--force` is always followed by space, `=`, or end of
string when it is the flag. Removing `\b` and ensuring the lookahead covers both forms makes the
pattern unambiguous.

---

## Impact Tree

### Upstream (what calls the affected code)

- `pre-bash.mjs:main()` — called by Claude Code PreToolUse hook for every Bash tool call
- `isDestructiveClean()` — called from `pre-bash.mjs` for any `git clean` command
- Force push patterns — evaluated against every `git push` command

### Downstream (what changes with the fix)

- `git clean -fx` now triggers ask/deny (was: silently allowed)
- `git merge --ff-only --no-ff` now evaluated correctly (was: treated as safe ff-only)
- `git push -f` (bare, no branch) now asks for confirmation (was: silently allowed)
- `git push --force-with-lease=origin/main` unambiguously allowed (was: potential edge case)

### Blast radius analysis

- **No regressions for normal workflows**: `git clean -f`, `git clean -fd`, `git push origin feature/foo` unaffected
- **Possible new prompts for**: `git clean -fx` (intentional), `git push -f` without explicit branch (intentional)
- **Tests to update**: any test that expects `git clean -fx` to pass silently

### Files to verify after change

- [ ] `test/pre-bash.test.mjs` — update `git clean -fx` test expectations
- [ ] `test/hooks-config.test.mjs` — verify `isDestructiveClean` changes
- [ ] `test/pre-bash.test.mjs` — verify `--ff-only --no-ff` combined flag
- [ ] `test/pre-bash.test.mjs` — verify bare `git push -f` triggers ask

---

## Definition of Done

- [ ] `git clean -fx` triggers ask/deny (was: allowed)
- [ ] `git clean -fdx` triggers ask/deny (was: allowed)
- [ ] `git clean -f somefile` (no -d, no -x) still allowed (normal clean)
- [ ] `git merge --ff-only develop` still bypasses check (correct)
- [ ] `git merge --ff-only --no-ff develop` no longer bypasses (was: bypass)
- [ ] `git push -f` (bare) triggers ask for confirmation (was: allowed)
- [ ] `git push -f origin develop` still triggers deny (existing behavior retained)
- [ ] `git push --force-with-lease=origin/main origin develop` still allowed
- [ ] Both copies of `isDestructiveClean` updated (or BUG-126 deduplication applied first)
- [ ] All existing hook tests pass (`./test fast`)

---

## Test Requirements

### Unit tests to add

```javascript
// test/pre-bash.test.mjs

// F-027: git clean -x flag
test('git clean -fx triggers ask (removes ignored files)', async () => {
  const result = await runHook('pre-bash', { command: 'git clean -fx' });
  assert.equal(result.decision, 'ask');
});

test('git clean -fdx triggers ask (force + dir + ignored)', async () => {
  const result = await runHook('pre-bash', { command: 'git clean -fdx' });
  assert.equal(result.decision, 'ask');
});

test('git clean -f without -d or -x is allowed', async () => {
  const result = await runHook('pre-bash', { command: 'git clean -f somefile.tmp' });
  assert.equal(result.decision, 'allow');
});

// F-028: --ff-only + --no-ff combined
test('git merge --ff-only develop is allowed (safe)', async () => {
  const result = await runHook('pre-bash', { command: 'git merge --ff-only develop' });
  assert.equal(result.decision, 'allow');
});

test('git merge --ff-only --no-ff develop is blocked (--no-ff wins)', async () => {
  const result = await runHook('pre-bash', { command: 'git merge --ff-only --no-ff develop' });
  assert.equal(result.decision, 'ask');
});

// F-030: bare git push -f
test('git push -f (bare) triggers ask (tracking branch unknown)', async () => {
  const result = await runHook('pre-bash', { command: 'git push -f' });
  assert.equal(result.decision, 'ask');
});

test('git push -f origin feature/foo is allowed (not protected branch)', async () => {
  const result = await runHook('pre-bash', { command: 'git push -f origin feature/foo' });
  assert.equal(result.decision, 'allow');
});
```

---

## Change History

| Date | What | Who |
|------|------|-----|
| 2026-02-18 | Created from bughunt 20260218-hooks P2 group | solution-architect |
