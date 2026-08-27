# Bug Mode for Spark

**Purpose:** Systematic bug investigation via Quick Bug Mode (5 Whys → single spec).

For deep multi-agent analysis, use the standalone `/bughunt` skill instead.

---

## Mode Selection

| Signal | Mode | Description |
|--------|------|-------------|
| Simple bug, clear location, <5 files | **Quick Bug Mode** | 5 Whys → single spec |
| Complex bug, unclear cause, >5 files, "bug hunt", "deep analysis" | **→ /bughunt** | Redirect to standalone bughunt skill |
| User explicitly says "bug hunt", "баг-хант", "охота на баги" | **→ /bughunt** | Redirect to standalone bughunt skill |

**Default:** Quick Bug Mode. If 5 Whys reveals systemic issues → suggest `/bughunt`.

**Bug Hunt is a separate skill.** Do NOT run Bug Hunt pipeline from Spark.
If complex analysis needed, tell the user: "This needs `/bughunt` — it's a separate deep analysis skill."
If in headless mode, create inbox file with Route: bughunt instead.

---

# Quick Bug Mode

**Flow:** Reproduce → Isolate → Root Cause (5 Whys) → Create Spec → Commit + Push

## Phase 1: REPRODUCE

```
"Show exact reproduction steps:"
1. What command/action?
2. What input?
3. What output do we get?
4. What output do we expect?
```

**Get EXACT error output!** Not "test fails" but actual traceback.

## Phase 2: ISOLATE

```
Find problem boundaries:
- When did it start? (last working commit?)
- Where exactly does it fail? (file:line)
- Does it reproduce every time?
- Are there related files?
```

Read files, grep, find the exact location.

## Phase 3: ROOT CAUSE — 5 Whys

```
Why 1: Why does the test fail?
  → "Because function returns None"

Why 2: Why does function return None?
  → "Because condition X is not met"

Why 3: Why is condition X not met?
  → "Because variable Y is not initialized"

Why 4: Why is variable Y not initialized?
  → "Because migration didn't add default value"

Why 5: Why didn't migration add default?
  → "Because we forgot when adding the column"

ROOT CAUSE: Migration XXX doesn't have DEFAULT for new column.
```

**STOP when you find the REAL cause, not symptom!**

## Phase 4: CREATE BUG SPEC

Only after root cause is found → create BUG-XXX spec:

```markdown
# Bug Fix: [BUG-XXX] Title

**Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml`.
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Symptom
[What user sees / test failure]

## Root Cause (5 Whys Result)
[The REAL cause, not symptom]

## Reproduction Steps
1. [exact step]
2. [exact step]
3. Expected: X, Got: Y

## Fix Approach
[How to fix the root cause]

## Impact Tree Analysis

### Step 1: UP — who uses?
_Source: code graph (`trace_path` inbound) or grep — state which._
- [ ] All callers identified: [list files]

### Step 2: DOWN — what depends on?
- [ ] Imports in changed file checked
- [ ] External dependencies: [list]

### Step 3: BY TERM — grep entire project
| File | Line | Status | Action |
|------|------|--------|--------|

### Verification
- [ ] All found files added to Allowed Files

## Research Sources
- [Pattern](https://example.com) — description from Scout

## Allowed Files

<!-- callback-allowlist v1 -->

- `path/to/file.py` — fix location
- `path/to/test.py` — add regression test

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| L-NNN | root_cause_class | prevention rule | TASK-IDs |

Write "none" explicitly when the lessons bank holds nothing for this area, or when
`ai/lessons/` does not exist here. A placeholder left in place reads as researched.

## Implementation Plan

### Task 1: [Name]
**Type:** code | test | migrate
**Files:**
  - modify: `path/to/file.py`
**Acceptance:** [how to verify this task is done]

### Task 2: Regression test
**Type:** test
**Files:**
  - create: `tests/test_name.py`
**Acceptance:** fails on the commit before the fix, passes after

### Execution Order
1 → 2

## Eval Criteria

| ID | Scenario | Input | Expected | Type | Priority |
|----|----------|-------|----------|------|----------|
| EC-1 | reproduces the reported failure | the exact input from Reproduction Steps | fails before the fix, passes after | deterministic | P0 |
| EC-2 | the boundary the root cause turns on | | | deterministic | P0 |
| EC-3 | nearest untouched neighbour still works | | | deterministic | P1 |

### Coverage Summary

Deterministic: N | Integration: N | Total: N (minimum 3)

## Acceptance Verification

| ID | Check | Command | Expected |
|----|-------|---------|----------|
| AV-S1 | the thing still starts | exact command | exit 0 |
| AV-F1 | the reported symptom is gone | exact command | exact expected output |

Runnable commands, not placeholders. If the bug genuinely cannot be verified from
outside the test suite, write `N/A: {reason}` — that is a claim a reader can argue
with, which an empty section is not.

## Definition of Done
- [ ] Root cause fixed
- [ ] Original test passes
- [ ] Regression test added
- [ ] No new failures
```

**Size.** The same ceiling as a feature spec, because the same autopilot session runs
it: up to 5 tasks and 10 entries in Allowed Files is fine; 6–8 tasks or 11–15 entries
needs one line saying why it is indivisible; beyond that, split into an epic plus
independently shippable children and write them all now. A bug report of a few kopecks
answered with 22 files is three bugs wearing one id — file the other two.

→ Then go to `completion.md` for ID protocol, commit + push.

---

## Bug Research Template

When investigating bug patterns:

```yaml
Task tool:
  description: "Scout: {error_type} fix patterns"
  subagent_type: "scout"
  max_turns: 8
  prompt: |
    MODE: quick
    QUERY: "{error_type}: <user_input>{error_message}</user_input>. Common causes and fixes in {tech_stack}."
    TYPE: error
    DATE: {current date}
```

---

## Exact Paths Required (BUG-328)

**RULE:** Allowed Files must contain EXACT file paths, not placeholders.

---

## Bug Mode Rules

**Investigation Rules:**
- NEVER guess the cause — investigate first!
- NEVER fix symptom — fix root cause!
- NEVER skip reproduction — must have exact steps!

**Execution Rules:**
- ALWAYS create spec — Autopilot does the actual fix
- ALWAYS add regression test — in spec's DoD
- ALWAYS use Impact Tree — find all affected files

**Handoff Rules:**
- Bugs go through: spark → autopilot (via orchestrator approval)
- No direct fixes during spark (READ-ONLY mode)
- Auto-commit + push spec before completion
- DO NOT invoke autopilot — orchestrator manages lifecycle

---

## Pre-Completion Checklist

### Quick Bug Mode Checklist
1. [ ] Root cause identified (5 Whys complete)
2. [ ] Reproduction steps exact
3. [ ] Scout research done
4. [ ] Impact Tree Analysis complete
5. [ ] Allowed Files exact (no placeholders), and inside the size ceiling above
6. [ ] Implementation Plan: ≥1 `### Task N` with Type / Files / Acceptance — a one-line
   fix is still one task, and `requirePlanBeforeCode` denies the commit without it
7. [ ] Eval Criteria: ≥3 EC rows and a Coverage Summary — the pre-commit hook blocks without them
8. [ ] Acceptance Verification: ≥1 AV-S and ≥1 AV-F, or `N/A: {reason}`
9. [ ] Historical Risks filled from the lessons bank, or "none" written explicitly
10. [ ] Regression test in DoD
11. [ ] ID determined by protocol (completion.md)
12. [ ] Spec file created (status: queued)
13. [ ] `git cat-file -e HEAD:ai/lifecycle/{ID}.yaml` succeeds and the record says
    `status: queued` — or it does not, and the spec ships with a backlog row instead
    (`completion.md`, "The backlog is a render — with exactly one exception")
14. [ ] Auto-commit + push done

---

## Output Format

```yaml
status: completed | blocked
mode: quick
bug_id: BUG-XXX
root_cause: "[1-line summary]"
spec_path: "ai/features/BUG-XXX.md"
spec_status: queued
pushed: true | false
```
