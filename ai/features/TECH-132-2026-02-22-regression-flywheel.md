# Feature: [TECH-132] Regression Flywheel — Auto-Generate Regression Tests from Debug Loops

**Status:** done | **Priority:** P1 | **Date:** 2026-02-22

## Why

When Debugger fixes an in-scope test failure, the fix proves a real bug existed. But the fix doesn't become a permanent regression test — the same bug class can re-emerge. Braintrust pattern: every fixed failure → permanent test case. This closes the feedback loop.

## Context

- Independent of TECH-130/131 (can run in parallel)
- Debugger agent (debugger.md:193 LOC) proposes fixes but doesn't generate regression tests
- Task loop (task-loop.md:295 LOC) has no Step 2.5 between TESTER and PRE-CHECK
- Protected paths: `tests/regression/` is immutable (hooks.config.mjs:78)
- Diary recorder captures `test_retry > 1` but not regression creation
- EDD pattern: "every fixed bug → permanent test" (Braintrust, Hamel Husain)

---

## Scope

**In scope:**
- Add Step 3.5 to debugger.md — generate regression test entry alongside fix
- Add Step 2.5 to task-loop.md — capture regression test after successful debug loop
- Add `regression_captured` trigger to diary-recorder.md
- Add trigger to escalation.md

**Out of scope:**
- Eval Criteria format (TECH-130)
- Existing test infrastructure changes
- Auto-running regression tests in CI (project-specific)

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] task-loop.md orchestrates Step 2 (TESTER) → debugger → coder → re-test
- [x] Diary recorder called by escalation triggers

### Step 2: DOWN — what depends on?
- [x] debugger.md output consumed by task-loop.md to dispatch coder
- [x] tests/regression/ is a protected path (pre-edit hook)

### Step 3: BY TERM
- [x] `debug_attempts` — task-loop.md, escalation.md
- [x] `regression` — not currently in any agent prompt
- [x] `tests/regression/` — hooks.config.mjs, tester.md, pre-edit.mjs

### Step 4: CHECKLIST
- [x] tests/regression/ — will receive new files (not modify existing)
- [x] Note: pre-edit hook blocks MODIFYING tests/regression/ but CREATING new files is allowed via coder with explicit task

### Verification
- [x] All found files added to Allowed Files

---

## Allowed Files

1. `template/.claude/agents/debugger.md` — add Step 3.5 regression entry
2. `template/.claude/skills/autopilot/task-loop.md` — add Step 2.5 regression capture
3. `template/.claude/agents/diary-recorder.md` — add regression_captured trigger
4. `template/.claude/skills/autopilot/escalation.md` — add trigger

**Sync after:**
- `.claude/agents/debugger.md`
- `.claude/skills/autopilot/task-loop.md`
- `.claude/agents/diary-recorder.md`
- `.claude/skills/autopilot/escalation.md`

---

## Environment
nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Debugger generates full test code (Selected)
Debugger adds `regression` field to fix output with complete test code. Task loop Step 2.5 dispatches coder to create the file.
**Pros:** Complete, debugger already understands root cause
**Cons:** More debugger output

### Approach 2: Separate regression-generator agent
New agent analyzes debug loop transcript and generates tests.
**Pros:** Separation of concerns
**Cons:** Over-engineering, extra cost, another agent to maintain

### Selected: 1
**Rationale:** Debugger already has full context (root cause, fix, verify). Adding regression field is minimal overhead.

---

## Design

### Debugger Output Extension (Step 3.5)

After existing output format (debugger.md:84-95), add:

```yaml
status: fix_proposed
scope: in_scope
root_cause: "Missing await on async call"
fix:
  file: src/domains/seller/agent.py
  change: "Add await before process_message()"
  verify: "Run test_seller_agent"
regression:                          # NEW
  test_name: "test_regression_ftr042_missing_await"
  test_file: "tests/regression/test_seller.py"
  test_code: |
    def test_regression_ftr042_missing_await():
        """Regression: Missing await on async call. Source: FTR-042 debug loop."""
        # Arrange
        agent = SellerAgent()
        # Act
        result = await agent.process_message("test")
        # Assert
        assert result is not None
```

### Task Loop Step 2.5

Between Step 2 HARD-GATE (line 93) and Step 3 PRE-CHECK (line 96):

```markdown
## Step 2.5: REGRESSION CAPTURE (conditional)

**Trigger:** debug_attempts > 0 AND tester == "pass"

If debug loop succeeded:
1. Extract `regression` field from debugger's last fix output
2. Dispatch coder to create regression test file
3. Quick verify: pytest {test_file}::{test_name} -v

**Rules:**
- ONLY fires after successful debug loop
- Does NOT go through full review cycle (test-only, minimal change)
- File goes to tests/regression/ (immutable after creation)
```

---

## Implementation Plan

### Task 1: Add Step 3.5 to debugger.md
**Type:** code
**Files:** modify: `template/.claude/agents/debugger.md`
**Pattern:** After Step 3 (line 78), add Step 3.5 with regression field template
**Acceptance:** Debugger output format includes `regression` field

### Task 2: Add Step 2.5 to task-loop.md
**Type:** code
**Files:** modify: `template/.claude/skills/autopilot/task-loop.md`
**Pattern:** After Step 2 HARD-GATE (line 93), add Step 2.5 conditional block
**Acceptance:** Task loop has regression capture step with trigger condition

### Task 3: Update diary-recorder.md and escalation.md
**Type:** code
**Files:** modify: `template/.claude/agents/diary-recorder.md`, `template/.claude/skills/autopilot/escalation.md`
**Pattern:** Add `regression_captured` trigger type
**Acceptance:** Diary can record regression captures

### Task 4: Sync template -> .claude/
**Type:** code
**Files:** sync 4 files
**Acceptance:** Files identical

### Execution Order
1 -> 2 -> 3 -> 4

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Debugger output includes regression | Fix proposed after debug | Output YAML has `regression` field with test_name, test_file, test_code | deterministic | user requirement | P0 |
| EC-2 | Step 2.5 triggers on debug success | debug_attempts=1, tester=pass | Step 2.5 fires, regression test created | deterministic | design | P0 |
| EC-3 | Step 2.5 skips when no debug | debug_attempts=0, tester=pass | Step 2.5 does NOT fire | deterministic | design | P1 |

### Coverage Summary
- Deterministic: 3 | Integration: 0 | LLM-Judge: 0 | Total: 3

### TDD Order
1. EC-1 -> debugger output format
2. EC-2 -> Step 2.5 trigger logic
3. EC-3 -> skip condition

---

## Definition of Done

### Functional
- [ ] Debugger output includes `regression` field when proposing fix
- [ ] Task loop Step 2.5 captures regression test after debug success
- [ ] Diary recorder logs `regression_captured` events

### Tests
- [ ] All eval criteria pass
- [ ] No regressions

### Technical
- [ ] Template files synced to .claude/

---

## Autopilot Log
[Auto-populated by autopilot during execution]
