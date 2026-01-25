# TECH: [TECH-011] Translate All Skills

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

Skills SKILL.md files contain Russian text. Need English for international launch.

## Solution

Translate all 11 skill files to English.

---

## Scope

**In scope (skills with SKILL.md):**
- `template/.claude/skills/audit/SKILL.md`
- `template/.claude/skills/autopilot/SKILL.md`
- `template/.claude/skills/autopilot/autopilot-git.md`
- `template/.claude/skills/bootstrap/SKILL.md`
- `template/.claude/skills/claude-md-writer/SKILL.md`
- `template/.claude/skills/coder/SKILL.md`
- `template/.claude/skills/council/SKILL.md`
- `template/.claude/skills/planner/SKILL.md`
- `template/.claude/skills/reflect/SKILL.md`
- `template/.claude/skills/review/SKILL.md`
- `template/.claude/skills/scaffold/SKILL.md`
- `template/.claude/skills/scout/SKILL.md`
- `template/.claude/skills/spark/SKILL.md`
- `template/.claude/skills/tester/SKILL.md`

**Out of scope:**
- Changing logic or behavior
- Adding new features

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/skills/audit/SKILL.md` | modify | Translate |
| 2 | `template/.claude/skills/autopilot/SKILL.md` | modify | Translate |
| 3 | `template/.claude/skills/autopilot/autopilot-git.md` | modify | Translate |
| 4 | `template/.claude/skills/bootstrap/SKILL.md` | modify | Translate |
| 5 | `template/.claude/skills/claude-md-writer/SKILL.md` | modify | Translate |
| 6 | `template/.claude/skills/coder/SKILL.md` | modify | Translate |
| 7 | `template/.claude/skills/council/SKILL.md` | modify | Translate |
| 8 | `template/.claude/skills/planner/SKILL.md` | modify | Translate |
| 9 | `template/.claude/skills/reflect/SKILL.md` | modify | Translate |
| 10 | `template/.claude/skills/review/SKILL.md` | modify | Translate |
| 11 | `template/.claude/skills/scaffold/SKILL.md` | modify | Translate |
| 12 | `template/.claude/skills/scout/SKILL.md` | modify | Translate |
| 13 | `template/.claude/skills/spark/SKILL.md` | modify | Translate |
| 14 | `template/.claude/skills/tester/SKILL.md` | modify | Translate |

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Translate Core Skills (spark, autopilot, bootstrap)

**Files:**
- Modify: `template/.claude/skills/spark/SKILL.md`
- Modify: `template/.claude/skills/autopilot/SKILL.md`
- Modify: `template/.claude/skills/autopilot/autopilot-git.md`
- Modify: `template/.claude/skills/bootstrap/SKILL.md`

**Note:** autopilot/SKILL.md is large (~32KB). Focus on Russian text only.

**Acceptance:**
- [ ] All 4 files translated
- [ ] No Russian text remains

### Task 2: Translate Review/Test Skills

**Files:**
- Modify: `template/.claude/skills/council/SKILL.md`
- Modify: `template/.claude/skills/audit/SKILL.md`
- Modify: `template/.claude/skills/reflect/SKILL.md`
- Modify: `template/.claude/skills/review/SKILL.md`

**Acceptance:**
- [ ] All 4 files translated

### Task 3: Translate Utility Skills

**Files:**
- Modify: `template/.claude/skills/coder/SKILL.md`
- Modify: `template/.claude/skills/tester/SKILL.md`
- Modify: `template/.claude/skills/scout/SKILL.md`
- Modify: `template/.claude/skills/planner/SKILL.md`
- Modify: `template/.claude/skills/scaffold/SKILL.md`
- Modify: `template/.claude/skills/claude-md-writer/SKILL.md`

**Acceptance:**
- [ ] All 6 files translated

---

## Execution Order

Task 1 → Task 2 → Task 3 (can parallel)

---

## Definition of Done

### Functional
- [ ] All 14 files translated
- [ ] No Russian text remains
- [ ] Skills still work correctly

### Technical
- [ ] Valid markdown
- [ ] Consistent terminology

---

## Autopilot Log

- **2026-01-25**: All 14 skill files verified - already in English
  - `spark/SKILL.md` - already translated
  - `autopilot/SKILL.md` - already translated
  - `autopilot/autopilot-git.md` - already translated
  - `bootstrap/SKILL.md` - already translated
  - `claude-md-writer/SKILL.md` - already translated
  - `coder/SKILL.md` - already translated
  - `council/SKILL.md` - already translated
  - `planner/SKILL.md` - already translated
  - `reflect/SKILL.md` - already translated
  - `review/SKILL.md` - already translated
  - `scaffold/SKILL.md` - already translated
  - `scout/SKILL.md` - already translated
  - `tester/SKILL.md` - already translated
  - `audit/SKILL.md` - already translated
- grep for Cyrillic found 0 matches
