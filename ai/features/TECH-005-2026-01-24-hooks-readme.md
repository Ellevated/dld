# TECH: [TECH-005] Add Hooks README

**Status:** done | **Priority:** P2 | **Date:** 2026-01-24

## Problem

`template/.claude/hooks/` contains Python hooks but no README explaining:
- What hooks are
- How to use them
- What each hook does

New users see code but don't understand the purpose.

## Solution

Add README.md to hooks directory explaining the hook system.

---

## Scope

**In scope:**
- Create README explaining hooks
- Document existing hooks (pre_bash.py, pre_edit.py, post_edit.py, etc.)
- Add usage examples

**Out of scope:**
- Creating new hooks
- Modifying existing hook logic

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/hooks/README.md` | create | Documentation |

**New files allowed:**
- `template/.claude/hooks/README.md` — Hook system documentation

**FORBIDDEN:** All other files including existing hooks.

---

## Implementation Plan

### Task 1: Create Hooks README

**Files:**
- Create: `template/.claude/hooks/README.md`

**Steps:**
1. Read existing hooks to understand their purpose:
   - `pre_bash.py` — validates bash commands before execution
   - `pre_edit.py` — validates file edits before applying
   - `post_edit.py` — runs after file edits
   - `prompt_guard.py` — guards prompt content
   - `session-end.sh` — cleanup on session end
   - `validate-spec-complete.sh` — validates spec completeness
   - `utils.py` — shared utilities

2. Write README with structure:
```markdown
# Claude Code Hooks

## Overview
Hooks intercept Claude Code actions for validation and automation.

## Available Hooks

### pre_bash.py
Runs before bash commands. Use for:
- Blocking dangerous commands
- Logging command history

### pre_edit.py
Runs before file edits. Use for:
- Preventing edits to protected files
- Validating edit patterns

### post_edit.py
Runs after file edits. Use for:
- Auto-formatting
- Triggering builds

### prompt_guard.py
Validates prompt content.

### session-end.sh
Cleanup when session ends.

### validate-spec-complete.sh
Validates spec files are complete.

## Configuration
How to enable/disable hooks in Claude Code settings.

## Creating Custom Hooks
Guidelines for adding new hooks.
```

**Acceptance:**
- [ ] All existing hooks documented
- [ ] Purpose of each hook clear
- [ ] Usage examples included

---

## Definition of Done

### Functional
- [ ] README explains hook system
- [ ] All hooks documented
- [ ] New user understands purpose

### Technical
- [ ] Valid markdown
- [ ] Accurate descriptions

---

## Autopilot Log

*(Filled by Autopilot during execution)*
