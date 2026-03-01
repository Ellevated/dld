# Task Loop — PHASE 2 Execution

SSOT for task execution flow. For EACH task from Implementation Plan.

## Flow Overview

```
CODER → TESTER → PRE-CHECK → SPEC REVIEWER → CODE QUALITY → COMMIT → LOCAL VERIFY → NEXT
```

---

## State Tracking (Enforcement as Code)

After EACH step, update the autopilot state file:

```
Write tool → autopilot-state.json (in worktree root)
```

**Format:** See `.claude/scripts/autopilot-state.mjs` for utilities.

**Before starting task loop:**
1. Initialize autopilot-state.json with `initState()`
2. After planner creates plan, call `setPlan()` with task list
3. Each step result updates the current task entry

**This is NOT optional.** Hooks read autopilot-state.json for plan-before-code gate.

---

## Step 1: CODER

```yaml
Task tool:
  subagent_type: "coder"
  prompt: |
    task: "Task {N}/{M} — {title}"
    ...
```

**Output:** `files_changed: [list of modified files]`

**Next:** Step 2 (TESTER)

<HARD-GATE>
DO NOT proceed to Step 2 until:
- [ ] autopilot-state.json updated: task.coder = "done"
- [ ] files_changed list captured
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "coder output is obvious, no need to track"
</HARD-GATE>

---

## Step 2: TESTER

**Command:** Use test-wrapper for LLM-optimized output:
```bash
node .claude/scripts/test-wrapper.mjs ./test fast
```

```yaml
Task tool:
  subagent_type: "tester"
  prompt: |
    files_changed: [{list}]
    task_scope: "{TASK_ID}: {description}"
    test_command: "node .claude/scripts/test-wrapper.mjs ./test fast"
```

**Decision Tree:**
```
TESTER result?
├─ PASSED → Step 3 (PRE-CHECK)
├─ FAILED (in-scope)
│   └─ debug_attempts < 3?
│       ├─ YES → [Debugger] → [Coder fix] → re-test (Step 2)
│       └─ NO → ESCALATE (see escalation.md)
└─ FAILED (out-of-scope)
    └─ Log "out-of-scope failure: {test}" → Step 3 (PRE-CHECK)
```

**In-scope:** Test file path contains any of `files_changed` directories.

<HARD-GATE>
DO NOT proceed to Step 3 until:
- [ ] autopilot-state.json updated: task.tester = "pass" or "fail_out_of_scope"
- [ ] If failed in-scope: debug loop completed or escalated
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "tests are simple, I'll write them later"
</HARD-GATE>

---

## Step 2.5: REGRESSION CAPTURE (conditional)

**Trigger:** `debug_attempts > 0 AND tester == "pass"`

When debug loop succeeded (bug was found and fixed):

1. Extract `regression` field from debugger's last fix output
2. Dispatch coder to create regression test file:
   ```yaml
   Task tool:
     subagent_type: "coder"
     prompt: |
       Create regression test from debugger output.
       File: {regression.test_file}
       Test: {regression.test_code}
       Do NOT modify any other file.
   ```
3. Quick verify: `pytest {test_file}::{test_name} -v` (or equivalent)

**Rules:**
- ONLY fires after successful debug loop (debug_attempts > 0)
- Does NOT go through full review cycle (test-only, minimal change)
- File goes to `tests/regression/` (immutable after creation)
- If regression field is missing from debugger output → skip (no error)

**After:** Continue to Step 3 (PRE-REVIEW CHECK)

---

## Step 3: PRE-REVIEW CHECK

Deterministic checks BEFORE AI review (saves tokens on obvious issues).

### Step 3a: Code Quality Pre-Check

**If `scripts/pre-review-check.py` exists** → run it:

```bash
python scripts/pre-review-check.py {files_changed}
```

**What PRE-CHECK catches:**
- `# TODO` or `# FIXME` in code
- Bare `except:` or `except Exception:` without re-raise
- Files > 400 LOC (code) or > 600 LOC (tests)

**If not found** → skip to Step 3b

### Step 3b: Blueprint Compliance (v2, NEW)

**If `ai/blueprint/system-blueprint/` exists** → check:

```bash
node .claude/scripts/validate-blueprint-compliance.mjs ai/features/{TASK_ID}*.md ai/blueprint/system-blueprint
```

**What BLUEPRINT CHECK catches:**
- Types not matching cross-cutting.md (e.g., float for money)
- Import direction violations
- Domain placement outside domain-map.md
- Missing Blueprint Reference in spec

**If blueprint doesn't exist** → skip (backwards compatible with legacy projects)

### Pre-Check Decision Tree
```
Step 3a result?
├─ PASS (or skipped) → Step 3b
└─ FAIL → CODER fixes → re-run Step 3a

Step 3b result?
├─ PASS (or skipped) → Step 4 (SPEC REVIEWER)
└─ FAIL → CODER fixes → re-run Step 3b
```

---

## Step 4: SPEC REVIEWER

```yaml
Task tool:
  subagent_type: "spec-reviewer"
  prompt: |
    feature_spec: "ai/features/{TASK_ID}*.md"
    task: "Task {N}/{M} — {title}"
    files_changed: [...]
```

**Decision Tree:**
```
Spec Reviewer status?
├─ approved → Step 5 (CODE QUALITY)
├─ needs_implementation
│   └─ CODER adds missing → re-review (Step 4)
│   └─ spec_review_loop < 2? YES: retry | NO: ESCALATE
└─ needs_removal
    └─ CODER removes extras → re-review (Step 4)
    └─ spec_review_loop < 2? YES: retry | NO: ESCALATE
```

---

## Step 5: CODE QUALITY

```yaml
Task tool:
  subagent_type: "review"
  prompt: |
    TASK: {description}
    FILES CHANGED: {list}
```

**Decision Tree:**
```
Code Quality status?
├─ approved → Step 6 (COMMIT)  ← CRITICAL!
├─ needs_refactor
│   └─ refactor_loop < 2?
│       ├─ YES → CODER fixes → re-test (Step 2) → re-review (Step 5)
│       └─ NO → ESCALATE to Council
└─ needs_discussion
    └─ STOP → Ask human (status: blocked)
```

**CRITICAL:** `approved` means proceed to COMMIT. Do NOT stop here!

<HARD-GATE>
DO NOT proceed to Step 6 until:
- [ ] autopilot-state.json updated: task.reviewer = "approved"
- [ ] All review loops resolved (spec reviewer + code quality)
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "the code is clean, review is a formality"
</HARD-GATE>

---

## Step 6: COMMIT

**All reviews passed. Commit the changes.**

```bash
git add {files_changed}
git commit -m "{type}({scope}): {description}"
```

**Commit message format:**
- `feat(autopilot): add task-loop decision trees`
- `fix(review): add TODO/FIXME check`
- `docs(diary): create escaped-defects template`

**If commit fails:**
1. Check error message (pre-commit hook? disk space? locked repo?)
2. Fix the issue if possible
3. Retry commit ONCE
4. If still fails → set spec status to `blocked`, add "ACTION REQUIRED: commit failure" to spec, STOP

**NEVER increment task counter if commit failed.**

**After commit:**
1. Log to Autopilot Log in spec file
2. Update autopilot-state.json: task.status = "done", task.commit = "{hash}"
3. Continue to Step 7 (LOCAL VERIFY)

<HARD-GATE>
DO NOT proceed to Step 7 until:
- [ ] Commit successful (verified by git)
- [ ] autopilot-state.json updated: task.status = "done", task.commit = hash
- [ ] Autopilot Log in spec file updated
Skipping this gate = VIOLATION. No rationalization accepted.
Common rationalization to REJECT: "I'll batch commits for efficiency"
</HARD-GATE>

---

## Step 7: LOCAL VERIFY (conditional)

**Trigger:** Spec has `## Acceptance Verification` section with AV-* checks.
**Skip if:** No AV section in spec, or section contains "N/A".

### 7a: Smoke Checks
Run commands from spec's Smoke Checks table (AV-S* rows).
```
Result?
├─ ALL PASS → Step 7b
├─ FAIL, retry < 2 → wait 5s, retry
├─ FAIL, retry >= 2 → WARN in Autopilot Log, continue
```

### 7b: Functional Checks
Run commands from spec's Functional Checks table (AV-F* rows).
```
Result?
├─ ALL PASS → update state, NEXT TASK
├─ FAIL, retry < 2 → CODER fix → re-commit → retry
├─ FAIL, retry >= 2 → WARN in Autopilot Log, continue
```

### Cleanup
Stop any processes started during smoke/functional checks.

**NON-BLOCKING** — verification failures produce warnings only, never block task progression.

**After LOCAL VERIFY:**
1. Update autopilot-state.json: task.verify = "pass" | "warn" | "skip"
2. Log result to Autopilot Log in spec file
3. Increment task counter: `current_task += 1`
4. Continue to NEXT TASK (back to Step 1)

<HARD-GATE>
- [ ] autopilot-state.json: task.verify = "pass" | "warn" | "skip"
- [ ] If warn: details logged to Autopilot Log
</HARD-GATE>

---

## After ALL Tasks

When `current_task > total_tasks`:

```
→ PHASE 3 (finishing.md)
```

---

## Loop Counters

| Counter | Limit | On Limit |
|---------|-------|----------|
| `debug_attempts` | 3 | Escalate (escalation.md) |
| `spec_review_loop` | 2 | Escalate to Council |
| `refactor_loop` | 2 | Escalate to Council |
| `verify_smoke_retry` | 2 | Warn (don't block) |
| `verify_func_retry` | 2 | Warn → Coder fix, then warn |

Reset counters at start of each task.

---

## Rationalization Pre-emption Table

When you feel tempted to skip a step, consult this table:

| LLM thinks | Correct action |
|---|---|
| "Tests are simple, I'll write them later" | TDD: test BEFORE code. No test = no commit. |
| "The code is clean, review is a formality" | Review catches real issues. Run it honestly. |
| "I'll batch commits for efficiency" | One task = one commit. Atomic commits only. |
| "This coder output is obvious" | Track it in state.json anyway. Hooks depend on it. |
| "Pre-check will pass, I can skip it" | Run deterministic checks. They catch TODOs and LOC violations. |
| "I'll update state.json at the end" | Update AFTER EACH STEP. State must be current. |

---

## Quick Reference

```
Task N:
  CODER → files → update state
  TESTER → pass? → update state
    └─ fail in-scope? debug (max 3)
    └─ fail out-scope? skip, continue
  PRE-CHECK → pass?
    └─ fail? coder fix, retry
  SPEC REVIEWER → approved?
    └─ needs_*? coder fix, retry (max 2)
  CODE QUALITY → approved? → update state
    └─ needs_refactor? coder fix, retry (max 2)
  COMMIT → log → update state
  LOCAL VERIFY → pass/warn/skip → update state → NEXT TASK
```
