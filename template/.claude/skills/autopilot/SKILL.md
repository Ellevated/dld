---
name: autopilot
description: Autonomous spec execution with subagents (planner, coder, tester, reviewer).
model: opus
---

# Autopilot v3.5 — Fresh Subagents + Loop Mode

Autonomous execution: Plan → Fresh subagent per task → commit → next.

**Activation:**
- `autopilot` — process all queued specs (interactive)
- `autopilot SPEC_ID` — process single spec only (loop mode)
- `autopilot --no-worktree` — skip worktree (for tiny fixes only)

## Loop Mode (Single Spec)

When called with `autopilot TECH-069` (specific SPEC_ID):

1. **Process ONLY that spec** — ignore other queued specs
2. **Exit after completion** — do NOT continue to next spec
3. **Let external orchestrator handle next** — fresh context per spec

This enables `autopilot-loop.sh` to run overnight with fresh context per spec.

**Detection:** If first argument matches pattern `(TECH|FTR|BUG|ARCH)-\d+`, enter loop mode.

## Quick Reference

```
PHASE 0: Worktree Setup        → worktree-setup.md
  └─ CI check → worktree → env copy → baseline

PHASE 1: Plan (ALWAYS)         → subagent-dispatch.md
  └─ [Plan Agent] opus → re-reads codebase → tasks in spec

PHASE 2: Execute (per task)    → task-loop.md
  └─ [Coder] sonnet → files
  └─ [Tester] sonnet → pass?
      └─ fail? → [Debugger] opus (max 3) → escalation.md
  └─ PRE-CHECK (deterministic)
  └─ [Spec Reviewer] sonnet → approved?
  └─ [Code Quality] opus → approved?
  └─ COMMIT (no push)

PHASE 3: Finish                → finishing.md
  └─ Final test → Exa verification → status done → push feature → merge develop → push develop → cleanup
```

**Limits & Escalation:** See `escalation.md`
**Safety Rules:** See `safety-rules.md`

---

## Modules

| Module | Content |
|--------|---------|
| `worktree-setup.md` | Git worktree creation, env setup, cleanup |
| `subagent-dispatch.md` | Subagent types, dispatch templates, model routing |
| `task-loop.md` | PHASE 2 execution flow, decision trees after each step |
| `finishing.md` | Pre-done checklist, status sync, merge flow |
| `escalation.md` | Limits, debug/refactor loops, Spark/Council |
| `safety-rules.md` | Forbidden actions, file/test/git safety |

---

## Architecture

```
PHASE 0: WORKTREE SETUP
  See: worktree-setup.md

PHASE 1: PLAN (ALWAYS — even if spec has plan)
  [Plan Subagent] → re-reads codebase → writes/overwrites plan
  WHY: specs queued earlier have stale line numbers after prior specs execute
  See: subagent-dispatch.md#plan-subagent

PHASE 2: FOR EACH TASK (fresh subagent per task!)
  [CODER] → code → files_changed
  [TESTER] → Smart Testing
  PRE-CHECK → deterministic validation
  [SPEC REVIEWER] → Stage 1
  [CODE QUALITY] → Stage 2
  COMMIT (NO PUSH yet!)
  See: task-loop.md (SSOT for execution flow)

PHASE 3: FINISHING
  Push feature branch → merge develop → push develop
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
│ 2. TESTER → Smart Testing                           │
│ 3. PRE-CHECK → deterministic validation             │
│ 4. SPEC REVIEWER (Stage 1) → matches spec?          │
│ 5. CODE QUALITY (Stage 2) → architecture ok?        │
│ 6. COMMIT (NO PUSH yet!)                            │
└─────────────────────────────────────────────────────┘
```

**SSOT:** See `task-loop.md` for detailed decision trees after each step.

⛔ **Skipping any step = VIOLATION**

---

## Main Loop

### Interactive Mode (no SPEC_ID)
```
while (queued/resumed tasks in ai/backlog.md):
  1. Read backlog → find first queued/resumed (P0 first)
  2. Status → in_progress (BOTH spec + backlog!)

  3. PHASE 0: Worktree Setup
     See: worktree-setup.md

  4. PHASE 1: Plan (ALWAYS runs)
     ALWAYS dispatch Plan Subagent — even if spec has plan
     Planner re-reads codebase, validates/regenerates plan
     WHY: prior specs changed code → old plans have stale refs
     After PHASE 1: plan MUST exist → else blocked

  5. PHASE 2: Execute (see task-loop.md for SSOT)
     FOR EACH TASK:
       a. CODER → files_changed
       b. TESTER → pass? (debug loop if fail)
       c. PRE-CHECK → deterministic validation
       d. SPEC REVIEWER → matches spec?
       e. CODE QUALITY → architecture ok?
       f. COMMIT (no push)

  6. PHASE 3: Finishing
     See: finishing.md

  7. Continue to next spec
```

### Loop Mode (SPEC_ID provided)
```
1. Validate SPEC_ID exists in backlog
2. Verify status is queued or resumed (not in_progress!)
3. Set status → in_progress
4. PHASE 0-3: Same as interactive (including push in Phase 3!)
5. EXIT (do NOT continue to next spec)
   └─ External orchestrator provides fresh context
```

**Why loop mode?** Prevents context accumulation. Each spec = fresh Claude session.

---

## Pre-flight Check

Before taking a spec from backlog:

1. **Status:** Must be `queued` or `resumed` → skip otherwise

After PHASE 1 (planner always runs):

2. **Plan:** Must have `## Implementation Plan`
3. If plan missing after PHASE 1 → set `blocked`, skip spec

Skip if status check fails, **with warning to user:**

```
SKIP: {TASK_ID}
Status: {current_status} (expected: queued or resumed)
Fix the issue and re-run autopilot.
```

⛔ **Skipping planner = VIOLATION.** Planner runs before EVERY spec, no exceptions.

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

### Interactive Mode
Context accumulates. AUTO-COMPACT after each spec (legacy).

### Loop Mode (Recommended)
Each spec = fresh Claude session via external orchestrator.

```
autopilot-loop.sh:
  └─ claude "autopilot TECH-065" → fresh context
  └─ claude "autopilot TECH-066" → fresh context
  └─ claude "autopilot TECH-067" → fresh context
  └─ ...
```

**Memory persists via files:**
- `ai/backlog.md` — task status
- `ai/diary/autopilot-progress.md` — learnings
- Git history — code changes

See: `./scripts/autopilot-loop.sh`

---

## References

- Agent roles: `.claude/agents/*.md`
- Creating skills: `/skill-writer create` skill
- Smart Testing: `.claude/agents/tester.md`
