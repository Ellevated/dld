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

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
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
- [ ] **Signature change or method removal:** a separate `grep -rn "{symbol}" tests/`, and
      **every** caller test goes in Allowed Files — not just the obvious one. Precedent
      (AwardyBot TECH-1325): 2 listed, 5 broke.

## Blueprint Reference

<!-- Only where `ai/blueprint/system-blueprint/` exists. There it is REQUIRED:
     validate-blueprint-compliance.mjs (task-loop Step 3b) FAILs the spec without it.
     Domain must be one value from ai/blueprint/system-blueprint/domain-map.md
     section "Current Domains" — one word, no markdown emphasis around the value. -->
**Domain:** {one domain slug, e.g. marketing}
**Cross-cutting:** {Money (int minor units)? Auth? Errors? — from cross-cutting.md, or "none"}
**Data model:** {affected tables, or "none"}

## Research Sources
- [Pattern](https://example.com) — description from Scout

## Allowed Files

<!-- callback-allowlist v1 -->

- `path/to/file.py` — fix location
- `path/to/test.py` — add regression test

**Before leaving this section, run the linter — it is the SSOT, not the prose above:**

```bash
node .claude/scripts/validate-allowlist.mjs ai/features/{TASK_ID}-*.md
```

Exit 1 = the allowlist is unusable (fix in place, re-run, do not delete the spec).
Exit 0 with warnings still needs answers — see `feature-mode.md` Phase 5.5 for the
code table. In particular `W005_COUPLED_TEST_UNLISTED` names test files that
reference an allowlisted source module and are not on the list: allowlist each, or
write one line per file saying why the fix cannot touch it. This is the 6×-repeated
failure where the coder correctly refuses a non-allowlisted test and the task ends
red mid-run. The couplings that break *without* naming the changed symbol — check
them by hand: strict `==` on a return value whose shape changes, fixed-length
`side_effect` lists that break on a call-count change, mock chains missing a method
the fix newly calls.

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

**A grep on a literal string also matches prose.** `git grep "<removed string>" -- src/`
hits the comment or docstring that documents the removal, so the guard fails on a correct
fix and the loop learns to wave it through. Either exclude prose in the command
(`git grep -n "<s>" -- src/ | grep -v '^\s*#'`, or grep only the call site
`git grep "logger.*<s>"`), or state in the Expected column that the string must not
appear in comments or docstrings either — and say which. Precedent: BUG-495 AV-F1.

**Dry-run every AV-F against the pre-fix tree while authoring it.** A guard that passes
before the fix proves nothing (BUG-497: 3 of 4 were vacuous — one grepped a string the
fix re-introduces, one reverted a file whose logic the plan moves elsewhere).

**Never accept a guard by reading the source — accept it by killing it.** An AV that says
"the UPDATE contains `.is_("tg_msg_id", "null")` — verified by reading the source"
(`inspect.getsource`, `grep`) passes on code no test ever executes: in BUG-502 all five
tests mocked the function outright, so deleting the ownership gate kept 115 tests green
and the AV green with them. Word it as a mutation instead: **"removing <the guard> must
red at least one named test"**, and name the test. Same fix as the pre-fix dry-run above,
one level down: an AV must be able to fail for the reason it exists.

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
12. [ ] Spec file created
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
