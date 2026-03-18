# Bug Fix: [BUG-160] Fix broken OpenClaw wake in pueue-callback.sh

**Status:** done | **Priority:** P1 | **Date:** 2026-03-18

## Symptom

OpenClaw wake call after pending-event write silently fails. The `|| true` swallows errors, so callback completes normally but OpenClaw never wakes — users wait up to 5 min (cron fallback) for cycle reports.

## Root Cause (5 Whys Result)

Two bugs on line 334 of `pueue-callback.sh`:

1. **`timeout 5` kills Node.js process** — OpenClaw CLI requires ~11s cold start. `timeout 5` sends SIGTERM after 5s, killing the process before it connects to the gateway.
2. **Missing `--text` parameter** — `openclaw system event --mode now` requires `--text <text>`. Without it, the command fails with a missing argument error.

Current code (line 334):
```bash
timeout 5 "$OPENCLAW_BIN" system event --mode now 2>>"$CALLBACK_LOG" || true
```

## Reproduction Steps

1. Complete an autopilot task in pueue
2. pueue-callback.sh fires, writes pending-event JSON
3. Wake call executes: `timeout 5 openclaw system event --mode now`
4. Expected: OpenClaw gateway processes event immediately
5. Got: Process killed after 5s (timeout) OR missing `--text` error

## Fix Approach

Replace single broken line with corrected command:

```bash
timeout 30 "$OPENCLAW_BIN" system event --mode now --text "cycle-event: ${SKILL} ${STATUS} for ${PROJECT_ID}" 2>>"$CALLBACK_LOG" || true
```

Changes:
- `timeout 5` → `timeout 30` (OpenClaw default `--timeout` is 30000ms; 30s bash timeout aligns with it)
- Add `--text` with descriptive event text containing skill, status, project_id

### Alternative considered: remove wake entirely

The openclaw prompt already asks: "Убрать wake совсем, оставить только cron". This is NOT recommended because:
- 5-min cron lag × 3 skills = up to 15-min total delay
- The fix is trivial (1 line change)
- Cron remains as fallback regardless

## Impact Tree Analysis

### Step 1: UP — who uses?
- pueue-callback.sh is called by Pueue daemon on every task completion
- OpenClaw wake is only used in Step 6.8 (lines 300-337)

### Step 2: DOWN — what depends on?
- `openclaw` CLI binary at `${HOME}/.npm-global/bin/openclaw`
- OpenClaw gateway must be running for `system event` to work

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| pueue-callback.sh | 334 | BUG | Fix timeout + add --text |
| dependencies.md | openclaw CLI section | OK | Already documented |

### Verification
- [x] All found files added to Allowed Files

## Blueprint Reference

Orchestrator pipeline → pueue-callback.sh → OpenClaw wake (hybrid push+cron model)

## Allowed Files

1. `scripts/vps/pueue-callback.sh` — fix wake command (line 334)

## Tasks

### Task 1: Fix openclaw wake command

**Files:** `scripts/vps/pueue-callback.sh`

**Changes:**
Replace line 334:
```bash
# BEFORE (broken):
timeout 5 "$OPENCLAW_BIN" system event --mode now 2>>"$CALLBACK_LOG" || true

# AFTER (fixed):
timeout 30 "$OPENCLAW_BIN" system event --mode now --text "cycle-event: ${SKILL} ${STATUS} for ${PROJECT_ID}" 2>>"$CALLBACK_LOG" || true
```

## Tests

### Deterministic

| ID | Input | Expected | Verification |
|----|-------|----------|--------------|
| T1 | Run `openclaw system event --help` | Shows `--text` as option | CLI reference |
| T2 | Run `timeout 30 openclaw system event --mode now --text "test"` | Exits 0 (or gateway-not-running error, NOT timeout) | Manual CLI test |
| T3 | Grep pueue-callback.sh for `timeout 5` | 0 matches — old timeout removed | `grep "timeout 5" scripts/vps/pueue-callback.sh` |

### Integration

| ID | Scenario | Expected |
|----|----------|----------|
| T4 | Complete a pueue autopilot task with gateway running | callback-debug.log shows "OpenClaw wake sent" within 30s |
| T5 | Complete a pueue task with gateway NOT running | Callback completes without hanging (|| true catches error) |

## Definition of Done

- [x] Root cause fixed (timeout + missing --text)
- [x] callback-debug.log confirms wake succeeds
- [x] No regression — callback still completes even if openclaw binary missing/gateway down
