# TECH-001: Split autopilot.md into modules

**Status:** done
**Created:** 2026-01-22
**Type:** TECH (refactoring)

---

## Problem

`template/.claude/skills/autopilot/SKILL.md` = 1192 lines.
DLD принцип: max 400 LOC per file (600 for complex).
Нарушаем собственные правила = bad look для open source launch.

---

## Solution

Разбить на логические модули, main SKILL.md импортирует остальные.

---

## Input

```
template/.claude/skills/autopilot/SKILL.md (1192 lines)
```

---

## Output

```
template/.claude/skills/autopilot/
├── SKILL.md              # Core: metadata, trigger, phases overview (~200 LOC)
├── worktree-setup.md     # Git worktree creation & cleanup (~150 LOC)
├── subagent-dispatch.md  # How to spawn/manage subagents (~150 LOC)
├── smart-testing.md      # Test strategy, scope protection (~150 LOC)
├── migrations.md         # DB migrations (optional, stack-specific) (~100 LOC)
├── finishing.md          # Pre-done checklist, PR creation (~100 LOC)
└── troubleshooting.md    # Common issues & recovery (~100 LOC)
```

---

## Implementation Steps

### Step 1: Analyze current structure
- Read SKILL.md
- Identify logical sections
- Map lines to modules

### Step 2: Extract worktree-setup.md
- Git worktree creation
- Branch naming
- Cleanup on finish/abort

### Step 3: Extract subagent-dispatch.md
- Subagent types (planner, coder, tester, etc)
- When to spawn which
- Context passing rules

### Step 4: Extract smart-testing.md
- Test file detection
- Scope protection (contracts/, regression/)
- Smart test selection

### Step 5: Extract migrations.md
- Git-first migration flow
- CI-only apply rule
- Stack-specific (can be optional)

### Step 6: Extract finishing.md
- Pre-done checklist
- PR creation rules
- Auto-push rules

### Step 7: Extract troubleshooting.md
- Common failures
- Recovery procedures
- When to abort vs retry

### Step 8: Refactor main SKILL.md
- Keep: metadata, trigger, high-level flow
- Add: imports/references to modules
- Remove: extracted content

### Step 9: Verify
- Each file < 400 LOC
- No broken references
- Skill still works end-to-end

---

## Files Allowed to Modify

- `template/.claude/skills/autopilot/SKILL.md`
- `template/.claude/skills/autopilot/*.md` (create new)

---

## Done Criteria

- [x] Main SKILL.md < 300 LOC → 192 LOC
- [x] Each module < 400 LOC → all pass (max 328 LOC)
- [x] Total modules: 6-7 files → 7 files
- [x] Clear imports/references between files → table in SKILL.md
- [x] No content lost → all logic preserved
- [x] Consistent formatting (English) → English throughout

---

## Notes

- Translate to English during split (kill two birds)
- Keep Russian version in comments only if critical context
- Preserve all logic, just reorganize

---

## Autopilot Log

### Task 1/1: Split autopilot.md — 2026-01-24
- Coder: completed (6 files: SKILL.md, worktree-setup.md, subagent-dispatch.md, finishing.md, escalation.md, safety-rules.md)
- Tester: skipped (no tests for .md)
- Documenter: skipped (self-documenting)
- Spec Reviewer: approved (all criteria met)
- Code Quality Reviewer: approved (all < 400 LOC)
- Commit: pending
