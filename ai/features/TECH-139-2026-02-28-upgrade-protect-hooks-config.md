# Feature: [TECH-139] Upgrade: Protect hooks.config.mjs
**Status:** queued | **Priority:** P0 | **Date:** 2026-02-28

## Why
`hooks.config.mjs` is in SAFE_GROUPS (auto-applied without confirmation). The DLD project version has a customization (`git-local-folders.md` in `excludeFromSync`, line 88) that the template version lacks. Next `/upgrade` will silently overwrite this, removing user's hook rules.

The `.local.mjs` override pattern exists but is underused. The fix is twofold: protect the main config + document the override pattern.

Source: TRIZ TC-1 (Taking out — extract volatile from stable), TOC UDE-4.

## Context
Part of `/upgrade` safety hardening. TRIZ report Recommendation #4.

---

## Scope
**In scope:**
- Add `hooks.config.mjs` to PROTECTED in upgrade.mjs
- Add header comment to template's hooks.config.mjs documenting .local.mjs pattern
- When analyze() detects hooks.config.mjs divergence, emit migration suggestion in output

**Out of scope:**
- Automatically migrating user customizations to .local.mjs
- Changing how hooks.config.local.mjs override mechanism works (already works)

---

## Allowed Files
**ONLY these files may be modified during implementation:**

1. `template/.claude/scripts/upgrade.mjs` — Add hooks.config.mjs to PROTECTED
2. `.claude/scripts/upgrade.mjs` — Sync
3. `template/.claude/hooks/hooks.config.mjs` — Add header comment about .local.mjs

---

## Implementation

### Step 1: Add to PROTECTED (upgrade.mjs)

```javascript
const PROTECTED = new Set([
  // ... existing entries ...
  '.claude/hooks/hooks.config.mjs',
]);
```

### Step 2: Add header comment (template hooks.config.mjs)

At the top of `template/.claude/hooks/hooks.config.mjs`, after any existing header:

```javascript
// Hook configuration. DO NOT EDIT for project-specific rules.
// Use hooks.config.local.mjs for customizations (protected from upgrades).
// See: .claude/hooks/hooks.config.local.mjs
```

### Step 3: Sync to .claude/

Sync upgrade.mjs changes (preserving DLD-specific entries).

---

## Eval Criteria

| ID | Type | Assertion |
|----|------|-----------|
| EC-1 | Deterministic | PROTECTED set includes `'.claude/hooks/hooks.config.mjs'` |
| EC-2 | Deterministic | `--apply --groups safe` does NOT modify hooks.config.mjs |
| EC-3 | Deterministic | template hooks.config.mjs contains `.local.mjs` reference in header |
