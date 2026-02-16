# Task Loop — PHASE 2 Execution

SSOT for task execution flow. For EACH task from Implementation Plan.

## Flow Overview

```
CODER → TESTER → PRE-CHECK → SPEC REVIEWER → CODE QUALITY → COMMIT → NEXT
```

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

---

## Step 2: TESTER

```yaml
Task tool:
  subagent_type: "tester"
  prompt: |
    files_changed: [{list}]
    task_scope: "{TASK_ID}: {description}"
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
2. Increment task counter: `current_task += 1`
3. Continue to NEXT TASK (back to Step 1)

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

Reset counters at start of each task.

---

## Quick Reference

```
Task N:
  CODER → files
  TESTER → pass?
    └─ fail in-scope? debug (max 3)
    └─ fail out-scope? skip, continue
  PRE-CHECK → pass?
    └─ fail? coder fix, retry
  SPEC REVIEWER → approved?
    └─ needs_*? coder fix, retry (max 2)
  CODE QUALITY → approved?
    └─ needs_refactor? coder fix, retry (max 2)
  COMMIT → log → NEXT TASK
```
