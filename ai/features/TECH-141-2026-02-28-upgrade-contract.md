# Feature: [TECH-141] Upgrade Contract Specification
**Status:** queued | **Priority:** P1 | **Date:** 2026-02-28

## Why
The core TOC constraint: upgrade.mjs has no formal contract. Every bug leads to reactive patches (add X to PROTECTED after it breaks). Without a contract: no tests (what to assert?), no rollback (what state to restore?), no hooks (what invariants to check?).

Source: TOC core constraint (POLICY), ADR-011 (Enforcement as Code).

## Context
TRIZ report Recommendation #1. This is a DOCUMENT, not code. It defines invariants that TECH-143 (CI tests) will assert against.

---

## Scope
**In scope:**
- Create `.claude/contracts/upgrade-contract.md` defining formal invariants
- Define file lifecycle states (added, modified, deprecated, removed)
- Define atomicity and reversibility guarantees
- Define trust tiers (PROTECTED, INFRASTRUCTURE, SAFE, ALWAYS_ASK)

**Out of scope:**
- Code changes (this is a specification document)
- CI implementation (TECH-143)
- Changing existing upgrade.mjs behavior

---

## Allowed Files
**ONLY these files may be modified during implementation:**

1. `template/.claude/contracts/upgrade-contract.md` — NEW: formal upgrade contract
2. `.claude/contracts/upgrade-contract.md` — Sync from template

---

## Implementation

### Step 1: Create contract document

Create `template/.claude/contracts/upgrade-contract.md` with the following sections:

#### 1. Scope Invariants
- ONLY files matching UPGRADE_SCOPE (`.claude/`, `scripts/`) are touched
- Files outside UPGRADE_SCOPE are NEVER read, compared, or modified
- PROTECTED files are NEVER modified regardless of source

#### 2. Trust Tiers
| Tier | Behavior | Files |
|------|----------|-------|
| PROTECTED | Never touched, never offered | CLAUDE.md, pyproject.toml, etc. |
| INFRASTRUCTURE | Only via explicit `--files`, always show diff | upgrade.mjs, run-hook.mjs |
| ALWAYS_ASK | Always show diff, require approval | settings.json |
| SAFE | Auto-apply in batch mode | agents, hooks, rules, scripts |
| OTHER | Show in report, require per-file approval | skills, etc. |

#### 3. Atomicity
- Either ALL files in a group are applied, or NONE (on error, rollback via git)
- `.dld-version` is written ONLY after clean apply (no errors, no validation failures)

#### 4. Reversibility
- Backup via `git stash create` before any apply
- On validation failure: automatic rollback via `git checkout -- .`
- Stash ref preserved in `.dld-upgrade-log` for manual recovery

#### 5. File Lifecycle
| State | Meaning | Detection |
|-------|---------|-----------|
| added | New in template, not in project | exists in template, not in project |
| modified | Exists in both, SHA differs | SHA256 comparison |
| identical | Exists in both, SHA matches | SHA256 comparison |
| deprecated | Removed from template | Listed in deprecated.json |
| user_only | Exists in project only | Not in template |

#### 6. Post-Apply Validation
- hooks.config.mjs: must parse as valid JS
- settings.json: must parse as valid JSON
- PROTECTED files: must be unchanged
- Audit log: every apply recorded in `.dld-upgrade-log`

### Step 2: Sync to .claude/

---

## Eval Criteria

| ID | Type | Assertion |
|----|------|-----------|
| EC-1 | Deterministic | File `template/.claude/contracts/upgrade-contract.md` exists |
| EC-2 | Deterministic | Contract defines all 5 trust tiers |
| EC-3 | Deterministic | Contract defines atomicity invariant |
| EC-4 | Deterministic | Contract defines reversibility mechanism |
| EC-5 | Deterministic | Contract defines file lifecycle states |
