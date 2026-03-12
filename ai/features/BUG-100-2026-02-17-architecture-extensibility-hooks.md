# Feature: [BUG-100] Architecture & Extensibility for Hooks

**Status:** done | **Priority:** P2 | **Date:** 2026-02-17

## Why

Hook rules (blocked commands, protected paths, LOC limits, allowed patterns) are hardcoded in source files. Users who `npx create-dld` a project cannot customize hook behavior without editing core hook code — which means their changes are lost on template updates. There's no configuration layer between "use defaults" and "fork the hooks".

## Context

- Hooks are designed as DLD template infrastructure — shipped to all users
- Current customization: edit hook source directly (fragile, lost on sync)
- Patterns are scattered across files: BLOCKED_PATTERNS in pre-bash, PROTECTED_PATHS in pre-edit, ALWAYS_ALLOWED_PATTERNS in utils, etc.
- `template-sync.md` rule exists but only handles DLD dev, not end users
- Users may need: different LOC limits, additional blocked commands, custom protected paths

---

## Scope

**In scope:**
- Configuration file for hook rules (`hooks.config.mjs` or JSON)
- Extracting hardcoded constants into configurable defaults
- User overrides that survive template updates
- Documentation for hook customization

**Out of scope:**
- Plugin system / hook marketplace
- Dynamic hook loading at runtime
- Custom hook types (new event hooks)
- Migration tool for existing customizations

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.claude/hooks/utils.mjs` — add config loading function
2. `template/.claude/hooks/pre-bash.mjs` — use config for BLOCKED_PATTERNS
3. `template/.claude/hooks/pre-edit.mjs` — use config for PROTECTED_PATHS, LOC limits, SYNC_ZONES
4. `template/.claude/hooks/hooks.config.mjs` — default configuration (new file)
5. `template/.claude/hooks/README.md` — document customization

**New files allowed:**
- `template/.claude/hooks/hooks.config.mjs` — default config with all customizable values

**FORBIDDEN:** All other files.

---

## Environment

nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: ESM config file with defaults + user overrides (Selected)

**Summary:** Create `hooks.config.mjs` with all defaults exported. Each hook imports from config. Users create `.claude/hooks/hooks.config.local.mjs` to override specific values — this file is gitignored and survives template syncs.

**Pros:**
- ESM-native (consistent with hooks)
- Type-safe (JS objects, not JSON strings)
- Supports functions as patterns (like isDestructiveClean)
- Clear separation: defaults vs overrides

**Cons:**
- Two config files to manage (defaults + local)

### Approach 2: JSON config

**Summary:** JSON file with all configuration, loaded at runtime.

**Pros:** Simpler, language-agnostic
**Cons:** Can't express function matchers (isDestructiveClean), regex needs string→RegExp conversion

### Selected: 1

**Rationale:** Hooks already use function matchers (isDestructiveClean). ESM config preserves this capability. JSON would require a string→function compilation layer — over-engineering for P2.

---

## Design

### Configuration Structure

```javascript
// hooks.config.mjs — shipped with template (defaults)
export default {
  preBash: {
    blockedPatterns: [
      // [matcher, message] — matcher is RegExp or function(cmd) → boolean
      [/git\s+push\b.*(?<![a-zA-Z0-9_-])main(?![a-zA-Z0-9_-])/i, 'Push to main blocked!...'],
      // ... existing patterns
    ],
    mergePatterns: [
      [/git\s+merge\b(?![-a-z])/i, 'Use --ff-only for merges!...'],
    ],
  },
  preEdit: {
    protectedPaths: ['tests/contracts/', 'tests/regression/'],
    maxLocCode: 400,
    maxLocTest: 600,
    warnThreshold: 7 / 8,
    syncZones: ['.claude/', 'scripts/'],
    excludeFromSync: [
      '.claude/rules/localization.md',
      '.claude/CUSTOMIZATIONS.md',
      '.claude/settings.local.json',
    ],
  },
  utils: {
    alwaysAllowedPatterns: [
      'ai/features/*.md',
      'ai/backlog.md',
      'ai/diary/**',
      '.gitignore',
      'pyproject.toml',
      '.claude/**',
    ],
  },
  promptGuard: {
    complexityPatterns: [/* ... existing ... */],
    skillIndicators: [/* ... existing ... */],
  },
};
```

### Config Loading

```javascript
// utils.mjs addition
let _config = null;

export async function loadConfig() {
  if (_config) return _config;
  try {
    const { default: defaults } = await import('./hooks.config.mjs');
    // Try loading user overrides
    try {
      const localPath = join(getProjectDir(), '.claude', 'hooks', 'hooks.config.local.mjs');
      if (existsSync(localPath)) {
        const { default: local } = await import(pathToFileURL(localPath).href);
        _config = deepMerge(defaults, local);
        return _config;
      }
    } catch { /* no local config = use defaults */ }
    _config = defaults;
    return _config;
  } catch {
    return {}; // fail-safe: no config = hardcoded defaults remain
  }
}
```

### User Override Example

```javascript
// .claude/hooks/hooks.config.local.mjs (gitignored, user-specific)
export default {
  preEdit: {
    maxLocCode: 500,         // Override: allow longer files
    protectedPaths: [        // Extend: add custom protected paths
      'tests/contracts/',
      'tests/regression/',
      'src/core/critical.py', // project-specific protection
    ],
  },
  preBash: {
    blockedPatterns: [
      // Add custom blocked command
      [/rm\s+-rf\s+\//i, 'Blocked: rm -rf / is not allowed'],
    ],
  },
};
```

---

## Implementation Plan

### Task 1: Create hooks.config.mjs with defaults

**Type:** code
**Files:**
  - create: `template/.claude/hooks/hooks.config.mjs`
**Acceptance:**
  - All current hardcoded constants extracted as named exports
  - preBash, preEdit, utils, promptGuard sections
  - Existing behavior preserved exactly

### Task 2: Add config loading to utils.mjs

**Type:** code
**Files:**
  - modify: `template/.claude/hooks/utils.mjs`
**Acceptance:**
  - `loadConfig()` exported, caches config after first load
  - Loads defaults from hooks.config.mjs
  - Merges user overrides from hooks.config.local.mjs (if exists)
  - Fail-safe: config load failure → use hardcoded defaults
  - deepMerge handles arrays (replace, not concat) and objects (recursive merge)

### Task 3: Wire config into pre-bash.mjs and pre-edit.mjs

**Type:** code
**Files:**
  - modify: `template/.claude/hooks/pre-bash.mjs`
  - modify: `template/.claude/hooks/pre-edit.mjs`
**Acceptance:**
  - pre-bash reads BLOCKED_PATTERNS and MERGE_PATTERNS from config
  - pre-edit reads PROTECTED_PATHS, LOC limits, SYNC_ZONES from config
  - Falls back to hardcoded values if config unavailable
  - Existing behavior unchanged with default config

### Task 4: Document hook customization

**Type:** code
**Files:**
  - modify: `template/.claude/hooks/README.md`
**Acceptance:**
  - Section on customizing hooks via hooks.config.local.mjs
  - Examples for common customizations (LOC limits, blocked commands, protected paths)
  - Note that hooks.config.local.mjs survives template syncs

### Task 5: Tests for config system

**Type:** test
**Files:**
  - create: `template/.claude/hooks/__tests__/config.test.mjs`
**Acceptance:**
  - Default config loads correctly
  - User override merges with defaults
  - Missing config file → defaults used
  - Invalid config file → defaults used (fail-safe)
  - Array override replaces (not concatenates)
  - All tests pass

### Execution Order

1 → 2 → 3 → 4 → 5

---

## Tests (MANDATORY)

### What to test
- [ ] Default config contains all current hardcoded values
- [ ] Config loading falls back gracefully on errors
- [ ] User overrides merge correctly with defaults
- [ ] pre-bash uses config patterns (not hardcoded)
- [ ] pre-edit uses config limits (not hardcoded)
- [ ] Existing behavior identical with default config

### How to test
- Unit: test loadConfig, deepMerge functions
- Integration: spawn hooks with custom config, verify behavior changes

### TDD Order
1. Create config → test defaults match current behavior → 2. Wire hooks → integration test

---

## Definition of Done

### Functional
- [ ] hooks.config.mjs contains all extractable constants
- [ ] hooks.config.local.mjs overrides are loaded and merged
- [ ] Existing behavior unchanged with default config
- [ ] Users can customize LOC limits, blocked commands, protected paths

### Tests
- [ ] Config loading tests pass
- [ ] Integration: hook with custom config behaves differently

### Technical
- [ ] Zero dependencies added
- [ ] Fail-safe: broken config → defaults (ADR-004)
- [ ] All files under 400 LOC

---

## Autopilot Log
[Auto-populated by autopilot during execution]
