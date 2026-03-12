# BUG-126 — Config & Dead Code

**Priority:** P2
**Group:** Config & Dead Code
**Findings:** F-021, F-022, F-023, F-024, F-025, F-026
**Scope:** `.claude/hooks/`

---

## Root Cause Analysis

The hooks system has a documented configuration contract: hooks read runtime behavior from
`hooks.config.mjs`, which users override via `hooks.config.local.mjs`. This contract is
broken in two distinct ways:

1. **prompt-guard.mjs completely ignores the config system** — it hardcodes `COMPLEXITY_PATTERNS`,
   `SKILL_INDICATORS`, and `KEYWORD_TARGET_GAP` as module-level constants and never calls
   `loadConfig()`. The `promptGuard` section in `hooks.config.mjs` (lines 106-124) is dead code.
   User customizations via `hooks.config.local.mjs` silently have zero effect.

2. **`loadConfig()` permanently caches failures** — when the config file fails to load (syntax
   error, missing file), `_config` is set to `{}` (an empty object, which is truthy). All
   subsequent calls see a truthy `_config` and return `{}` immediately. A transient failure
   permanently disables all custom rules for the entire process lifetime with no diagnostic output.

3. **Silent error absorption** — the inner catch for `hooks.config.local.mjs` load failure
   has a comment `/* no local config = use defaults */` but writes no log entry. A developer
   with a syntax error in their local config sees absolutely no feedback.

4. **`isDestructiveClean` duplicated** — defined identically in `hooks.config.mjs` (lines 12-17)
   and `pre-bash.mjs` (lines 18-25). Any fix to one misses the other.

5. **`ALWAYS_ALLOWED_PATTERNS` duplicated** — defined in `utils.mjs:226` as hardcoded fallback
   AND in `hooks.config.mjs:96`. Two copies can silently drift.

6. **Dead import** — `dirname` is imported from `'path'` in `utils.mjs:15` but never used anywhere
   in the file.

---

## Affected Files

| File | Line | Issue |
|------|------|-------|
| `.claude/hooks/prompt-guard.mjs` | 15-38 | Hardcoded patterns, never reads config |
| `.claude/hooks/prompt-guard.mjs` | 18 | `KEYWORD_TARGET_GAP` hardcoded |
| `.claude/hooks/utils.mjs` | 191-215 | `loadConfig()` caches failures as `{}` |
| `.claude/hooks/utils.mjs` | 208 | Silent local config load failure |
| `.claude/hooks/utils.mjs` | 15 | `dirname` imported but unused |
| `.claude/hooks/utils.mjs` | 226 | `ALWAYS_ALLOWED_PATTERNS` duplicate |
| `.claude/hooks/pre-bash.mjs` | 18-25 | `isDestructiveClean` duplicate |
| `.claude/hooks/hooks.config.mjs` | 12-17 | `isDestructiveClean` duplicate |
| `.claude/hooks/hooks.config.mjs` | 106-124 | `promptGuard` section — dead code |

---

## Fix Description

### Fix 1 — prompt-guard: read config (F-021)

```javascript
// prompt-guard.mjs — BEFORE
const KEYWORD_TARGET_GAP = 30;
const COMPLEXITY_PATTERNS = [/implement/i, /create/i, ...];
const SKILL_INDICATORS = [/\/spark/i, /\/autopilot/i, ...];

// prompt-guard.mjs — main()
function main() {
  // Never calls loadConfig()
  ...
}
```

```javascript
// prompt-guard.mjs — AFTER
import { loadConfig } from './utils.mjs';

// Default fallback constants retained for reference
const DEFAULT_KEYWORD_TARGET_GAP = 30;
const DEFAULT_COMPLEXITY_PATTERNS = [/implement/i, /create/i, ...];
const DEFAULT_SKILL_INDICATORS = [/\/spark/i, /\/autopilot/i, ...];

async function main() {
  const config = await loadConfig();
  const keywordTargetGap = config?.promptGuard?.keywordTargetGap ?? DEFAULT_KEYWORD_TARGET_GAP;
  const complexityPatterns = config?.promptGuard?.complexityPatterns ?? DEFAULT_COMPLEXITY_PATTERNS;
  const skillIndicators = config?.promptGuard?.skillIndicators ?? DEFAULT_SKILL_INDICATORS;
  ...
}
```

### Fix 2 — loadConfig: don't cache failures (F-022)

```javascript
// utils.mjs — BEFORE
let _config = null;
export async function loadConfig() {
  if (_config) return _config;  // {} is truthy — cached failure indistinguishable
  try { ... } catch {
    _config = {};  // error cached permanently
    return _config;
  }
}
```

```javascript
// utils.mjs — AFTER
let _config = null;
let _configLoaded = false;

export async function loadConfig() {
  if (_configLoaded) return _config;
  _configLoaded = true;  // set before await to prevent double-load
  try {
    // ... load logic ...
  } catch (err) {
    _config = {};  // empty but distinguishable via _configLoaded
    return _config;
  }
}

// resetConfigCache() must also reset _configLoaded
export function resetConfigCache() {
  _config = null;
  _configLoaded = false;
}
```

### Fix 3 — loadConfig: log local config failures (F-023)

```javascript
// utils.mjs — BEFORE
} catch { /* no local config = use defaults */ }

// utils.mjs — AFTER
} catch (localErr) {
  logHookError('loadConfig', `local config failed to load: ${localErr}`);
  // Continue with base config defaults
}
```

### Fix 4 — isDestructiveClean: single source of truth (F-024)

```javascript
// pre-bash.mjs — AFTER
// Remove the duplicate definition; import from utils.mjs or hooks.config.mjs
import { isDestructiveClean } from './utils.mjs';
// OR: use the config-loaded version already passed from loadConfig()
```

The canonical definition should live in `utils.mjs` and be exported. `hooks.config.mjs`
and `pre-bash.mjs` both import from there.

### Fix 5 — Remove dirname dead import (F-026)

```javascript
// utils.mjs line 15 — BEFORE
import { join, dirname, normalize, resolve } from 'path';

// utils.mjs line 15 — AFTER
import { join, normalize, resolve } from 'path';
```

### Fix 6 — ALWAYS_ALLOWED_PATTERNS: single source (F-025)

The hardcoded `ALWAYS_ALLOWED_PATTERNS` in `utils.mjs:226` should be the canonical default.
`hooks.config.mjs` should import from `utils.mjs` to initialize its `utils.alwaysAllowedPatterns`
default, eliminating the second copy.

---

## Impact Tree

### Upstream (what calls the affected code)

- `prompt-guard.mjs:main()` — called by Claude Code UserPromptSubmit hook
- `loadConfig()` — called by `pre-edit.mjs`, `pre-bash.mjs`, `post-edit.mjs`, `session-end.mjs`
- `isDestructiveClean()` — called by `pre-bash.mjs` for every bash command

### Downstream (what the fix enables)

- Users can now override `promptGuard.complexityPatterns` in `hooks.config.local.mjs`
- Config load failures are retryable (removed permanent `_config = {}` caching)
- Operators see diagnostic output when local config fails to load
- Single canonical `isDestructiveClean` — no divergence risk on future patches
- Single canonical `ALWAYS_ALLOWED_PATTERNS` — no config-vs-hardcoded drift
- Cleaner `utils.mjs` with no dead import

### Files to verify after change

- [ ] `test/prompt-guard.test.mjs` — add tests for config-loaded patterns
- [ ] `test/utils.test.mjs` — verify `resetConfigCache()` resets both flags
- [ ] `test/pre-bash.test.mjs` — verify `isDestructiveClean` import works
- [ ] `hooks.config.mjs` — `promptGuard` section is now live code, verify defaults match constants

---

## Definition of Done

- [ ] `prompt-guard.mjs` calls `loadConfig()` and uses `config.promptGuard.*` with fallback
- [ ] `loadConfig()` uses `_configLoaded` boolean sentinel (not truthiness of `_config`) to detect cache
- [ ] `resetConfigCache()` resets both `_config = null` and `_configLoaded = false`
- [ ] Local config load failure writes a `logHookError` entry
- [ ] `isDestructiveClean` defined once; `pre-bash.mjs` imports it
- [ ] `ALWAYS_ALLOWED_PATTERNS` defined once; no duplicate in `hooks.config.mjs`
- [ ] `dirname` removed from `utils.mjs` import line 15
- [ ] All existing hook tests pass (`./test fast`)
- [ ] New test: user-defined `complexityPatterns` in local config overrides hardcoded patterns in prompt-guard

---

## Test Requirements

### Unit tests to add

```javascript
// test/prompt-guard.test.mjs
test('uses complexityPatterns from config when provided', async () => {
  // Set up config mock with custom patterns
  // Verify prompt-guard uses config patterns, not hardcoded
});

test('falls back to default patterns when config is empty', async () => {
  // Config returns {}
  // Verify default COMPLEXITY_PATTERNS are used
});
```

```javascript
// test/utils.test.mjs
test('loadConfig caches success result', async () => {
  const first = await loadConfig();
  const second = await loadConfig();
  // second call should not re-import
});

test('loadConfig does not permanently cache load errors', async () => {
  // Simulate load failure
  resetConfigCache();
  // Second call should attempt load again (not return cached {})
});

test('resetConfigCache resets both _config and _configLoaded', () => {
  resetConfigCache();
  // Verify next loadConfig() performs fresh load
});
```

---

## Change History

| Date | What | Who |
|------|------|-----|
| 2026-02-18 | Created from bughunt 20260218-hooks P2 group | solution-architect |
