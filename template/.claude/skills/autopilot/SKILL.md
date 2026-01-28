---
name: autopilot
description: Autonomous task execution with subagents (coder, tester, debugger, reviewer)
model: opus
---

# Autopilot v3.4 — Fresh Subagents + Worktree Always

Autonomous execution: Plan → Fresh subagent per task → commit → next.

**Activation:**
- `autopilot` — creates worktree, plans, executes (default)
- `autopilot --no-worktree` — skip worktree (for tiny fixes only)

## Quick Reference

```
PHASE 0: Worktree Setup        → worktree-setup.md
  └─ CI check → worktree → env copy → baseline

PHASE 1: Plan                  → subagent-dispatch.md
  └─ [Plan Agent] opus → tasks in spec

PHASE 2: Execute (per task)    → subagent-dispatch.md
  └─ [Coder] sonnet → files
  └─ [Tester] sonnet → pass?
      └─ fail? → [Debugger] opus (max 3) → escalation.md
  └─ DOCUMENTER (inline)
  └─ [Spec Reviewer] sonnet → approved?
  └─ [Code Quality] opus → approved?
  └─ COMMIT (no push)

PHASE 3: Finish                → finishing.md
  └─ Final test → Exa verification → status done → merge develop → cleanup
```

**Limits & Escalation:** See `escalation.md`
**Safety Rules:** See `safety-rules.md`

---

## Modules

| Module | Content |
|--------|---------|
| `worktree-setup.md` | Git worktree creation, env setup, cleanup |
| `subagent-dispatch.md` | Subagent types, dispatch templates, model routing |
| `finishing.md` | Pre-done checklist, status sync, merge flow |
| `escalation.md` | Limits, debug/refactor loops, Spark/Council |
| `safety-rules.md` | Forbidden actions, file/test/git safety |

---

## Architecture

```
PHASE 0: WORKTREE SETUP
  See: worktree-setup.md

PHASE 1: PLAN (if no detailed plan exists)
  [Plan Subagent] → detailed tasks in spec
  See: subagent-dispatch.md#plan-subagent

PHASE 2: FOR EACH TASK (fresh subagent per task!)
  [CODER] → code → files_changed
  [TESTER] → Smart Testing
  [DEPLOY CHECK] → migrations? serverless?
  [DOCUMENTER] → inline
  [SPEC REVIEWER] → Stage 1
  [CODE QUALITY] → Stage 2
  COMMIT (NO PUSH yet!)
  See: subagent-dispatch.md

PHASE 3: FINISHING
  See: finishing.md
```

---

## Plan vs Workflow Separation

**Plan defines WHAT:**
- What code to write
- Which files to create/modify
- Acceptance criteria

**Autopilot defines HOW:**
- Fixed workflow for EACH task
- Gates and checkpoints
- Review process

### Task Execution Template

For EACH task from plan:

```
┌─────────────────────────────────────────────────────┐
│ 1. CODER → files_changed                            │
│ 2. MIGRATION VALIDATION (if *.sql)                  │
│ 3. TESTER → Smart Testing                           │
│ 4. DOCUMENTER → update docs                         │
│ 5. SPEC REVIEWER (Stage 1) → matches spec?          │
│ 6. CODE QUALITY (Stage 2) → architecture ok?        │
│ 7. COMMIT (NO PUSH yet!)                            │
└─────────────────────────────────────────────────────┘
```

⛔ **Skipping any step = VIOLATION**

---

## Main Loop

```
while (queued/resumed tasks in ai/backlog.md):
  1. Read backlog → find first queued/resumed (P0 first)
  2. Status → in_progress (BOTH spec + backlog!)

  3. PHASE 0: Worktree Setup
     See: worktree-setup.md

  4. PHASE 1: Plan (if needed)
     Check for "## Implementation Plan"
     Missing? → dispatch Plan Subagent

  5. PHASE 2: Execute
     FOR EACH TASK:
       a. CODER → files_changed
       b. TESTER → pass? (debug loop if fail)
       c. DEPLOY CHECK
       d. DOCUMENTER
       e. TWO-STAGE REVIEW
       f. COMMIT (no push)

  6. PHASE 3: Finishing
     See: finishing.md

  7. Continue to next spec
```

---

## Pre-flight Check

Before taking a task:

1. **Status:** Must be `queued` or `resumed`
2. **Plan:** Must have `## Implementation Plan`

Skip if either check fails.

---

## How to Read Feature Doc

```
## Problem/Solution     ← context
## Scope               ← what to do
## Allowed Files       ← ONLY these can be modified!
## Implementation Plan ← YOUR TASKS!
  ### Task 1           ← execute in order
## Definition of Done  ← check AFTER all tasks!
```

---

## Statuses

**Flow:** `draft → queued → in_progress → done`
**Recovery:** `in_progress → blocked → resumed → in_progress`

---

## Context Management

Compact after each spec to prevent context explosion:

```
Spec 1 → PHASE 0-3 → AUTO-COMPACT
Spec 2 → PHASE 0-3 → AUTO-COMPACT
...
No more queued → END
```

---

## References

- Agent roles: `docs/foundation/02-agent-roles.md`
- Creating skills: `/scaffold` skill
- Smart Testing: `.claude/agents/tester.md`
- Migrations: `.claude/rules/database.md`
