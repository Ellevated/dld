# Bug Fix: [BUG-158] QA dispatch fails for inbox tasks (no spec file)

**Status:** queued | **Priority:** P1 | **Risk:** R2 | **Date:** 2026-03-18

## Symptom

`QA skipped: spec file not found for inbox-20260318-200931` — QA dispatch falls after autopilot processes an inbox task directly (TASK_LABEL = `inbox-YYYYMMDD-HHMMSS`).

## Root Cause (5 Whys Result)

`pueue-callback.sh` Step 7 unconditionally dispatches QA after any autopilot completion. Inbox tasks have labels like `inbox-20260318-200931` which don't correspond to any spec file in `ai/features/`. QA (`qa-loop.sh`) tries to find the spec, fails, sends a noisy notification, and exits with error.

## Reproduction Steps

1. Send a message to Telegram bot that creates an inbox task
2. Orchestrator picks it up, dispatches autopilot with label `project_id:inbox-20260318-XXXXXX`
3. Autopilot completes successfully
4. `pueue-callback.sh` Step 7 dispatches QA with spec_id = `inbox-20260318-XXXXXX`
5. Expected: QA skipped gracefully for non-spec tasks. Got: `qa-loop.sh` fails with "spec file not found"

## Fix Approach

In `pueue-callback.sh` Step 7, before QA dispatch, check that TASK_LABEL matches the spec pattern `(TECH|FTR|BUG|ARCH)-[0-9]+`. If not — skip QA with a log message. Reflect dispatch stays unconditional (it doesn't depend on spec files).

## Impact Tree Analysis

### Step 1: UP — who uses pueue-callback.sh?
- [x] Pueue daemon (callback config) — no change to interface
- [x] run-agent.sh (label format) — no change

### Step 2: DOWN — what does Step 7 depend on?
- [x] `qa-loop.sh` — no change needed (it already handles missing spec gracefully)
- [x] `run-agent.sh` — no change needed
- [x] `db.py` — no change needed

### Step 3: BY TERM — grep entire project
| File | Line | Status | Action |
|------|------|--------|--------|
| pueue-callback.sh | 340-383 | target | Add TASK_LABEL guard |

### Verification
- [x] All found files added to Allowed Files

## Allowed Files

1. `scripts/vps/pueue-callback.sh` — add TASK_LABEL pattern guard in Step 7

## Tasks

### Task 1: Add TASK_LABEL guard to QA dispatch

In `scripts/vps/pueue-callback.sh`, Step 7 (around line 356), wrap the QA dispatch block with a pattern check:

```bash
# Skip QA for non-spec tasks (inbox tasks have no spec file to validate against)
if [[ "$TASK_LABEL" =~ ^(TECH|FTR|BUG|ARCH)-[0-9]+ ]]; then
    # ... existing QA dispatch logic (lines 361-383) ...
else
    echo "[callback] Skipping QA: task_label '${TASK_LABEL}' is not a spec (no spec file)"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] QA skipped: non-spec task_label=${TASK_LABEL}" >> "$CALLBACK_LOG"
fi
```

Reflect dispatch (lines 385-410) stays OUTSIDE the guard — it doesn't depend on spec files.

## Tests

### Deterministic

| # | Input | Expected | Verification |
|---|-------|----------|-------------|
| 1 | TASK_LABEL=`inbox-20260318-200931` after autopilot done | QA NOT dispatched, log says "Skipping QA" | grep callback-debug.log for "Skipping QA" |
| 2 | TASK_LABEL=`FTR-146` after autopilot done | QA dispatched normally | pueue status shows qa-FTR-146 task |
| 3 | TASK_LABEL=`BUG-155` after autopilot done | QA dispatched normally | pueue status shows qa-BUG-155 task |

### Integration

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Send inbox message → autopilot completes → callback fires | No "spec file not found" notification, reflect still runs |
| 2 | Queued spec task → autopilot completes → callback fires | Both QA and reflect dispatched |

## Definition of Done

- [x] Root cause fixed (TASK_LABEL guard added)
- [ ] No "spec file not found" for inbox tasks
- [ ] Reflect still dispatches for inbox tasks
- [ ] Spec-based tasks still get QA dispatch
