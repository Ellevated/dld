# QA Report: TECH-157 — Immediate OpenClaw wake after pending-event write

**Date:** 2026-03-18
**Environment:** VPS production, pueue-callback.sh, openclaw-gateway v2026.3.13
**Trigger:** `/qa TECH-157`

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 7     | 4    | 3    | 0       |

## Failures

### F1: Wake command always killed by timeout — never executes

**Severity:** Critical
**Reproducibility:** Always
**Expected:** `timeout 5 openclaw system event --mode now` sends event to gateway and returns within 5 seconds
**Actual:** Node.js cold start for openclaw CLI takes ~11 seconds. `timeout 5` kills the process (exit 124) BEFORE it even begins argument validation or WebSocket connection. The wake call never reaches the gateway.
**Steps to reproduce:**
1. Run `time timeout 5 "${HOME}/.npm-global/bin/openclaw" system event --mode now`
2. Observe: exit 124, no output, ~5s wall time (killed)
3. Run `time timeout 15 "${HOME}/.npm-global/bin/openclaw" system event --mode now`
4. Observe: ~11s startup, then fails with different error (see F2)

**Evidence:**
```
$ timeout 5 openclaw system event --mode now 2>&1
EXIT: 124     (3/3 consistent runs)

$ time timeout 15 openclaw system event --mode now 2>&1
error: required option '--text <text>' not specified
real 0m11.383s   ← Node.js startup alone takes 11s
EXIT: 1
```

**User impact:** The 5-minute cron lag that TECH-157 was supposed to eliminate is still present. Users wait up to 5 minutes for cycle completion reports.
**Hint for developers:** Increase timeout from 5 to at least 15s, or use a lighter wake mechanism (e.g., `curl` to gateway REST endpoint, or `touch` a signal file).

### F2: Missing `--text` parameter — command fails even with sufficient timeout

**Severity:** Critical
**Reproducibility:** Always
**Expected:** `openclaw system event --mode now` sends a wake event to the gateway
**Actual:** `openclaw system event` requires `--text <text>` parameter (per `--help`). Without it, the command exits with error: "required option '--text' not specified"
**Steps to reproduce:**
1. Run `timeout 15 "${HOME}/.npm-global/bin/openclaw" system event --mode now`
2. Observe error: "required option '--text' not specified", exit 1
3. Run `openclaw system event --help` — confirms `--text` is required

**Evidence:**
```
$ openclaw system event --help
Options:
  --text <text>    System event text      ← REQUIRED, not optional
  --mode <mode>    Wake mode (now|next-heartbeat)

$ timeout 15 openclaw system event --mode now
error: required option '--text <text>' not specified
EXIT: 1
```

**User impact:** Even if timeout is increased, the wake would still fail because `--text` is missing.
**Hint for developers:** Add `--text "cycle-complete: ${SKILL} ${PROJECT_ID}"` to the openclaw call.

### F3: Misleading success log when wake actually failed

**Severity:** Major
**Reproducibility:** Always
**Expected:** Log says "wake sent" only when the wake actually succeeded
**Actual:** The echo "OpenClaw wake sent..." is OUTSIDE the `|| true` — it runs regardless of whether the `timeout` command succeeded or failed. The callback-debug.log shows "OpenClaw wake sent" for events that were never actually delivered.
**Steps to reproduce:**
1. Check callback-debug.log after any autopilot/reflect completion
2. Observe: "OpenClaw wake sent for autopilot event (project=dld)" is logged
3. But the actual wake command was killed by timeout (exit 124) — event was never sent

**Evidence:**
```bash
# From callback-debug.log:
[callback] OpenClaw wake sent for autopilot event (project=dld)   # ← logged
[callback] OpenClaw wake sent for reflect event (project=dld)     # ← logged

# But stderr from openclaw is NOT in the log (killed before producing output)
# No evidence of actual gateway receiving the wake
```

The code structure:
```bash
timeout 5 "$OPENCLAW_BIN" system event --mode now 2>>"$CALLBACK_LOG" || true
echo "[callback] OpenClaw wake sent..."   # ← runs ALWAYS, even on failure
```

**User impact:** Operators see "wake sent" in logs and believe the feature works. Debugging latency issues becomes harder because logs suggest wake is functional.
**Hint for developers:** Move echo inside a success check: `timeout 5 ... && echo "wake sent" || echo "wake failed"`

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | Binary guard works (executable check) | `[[ -x "$OPENCLAW_BIN" ]]` correctly finds the binary at `~/.npm-global/bin/openclaw` |
| 2 | `\|\| true` prevents callback crash | Callback exits 0 even when openclaw fails (exit 124 from timeout). Core callback functions (DB update, Telegram notify, QA/reflect dispatch) are unaffected |
| 3 | Spark does NOT trigger wake | Tasks 714, 716 (spark) have no "OpenClaw wake" log entries — correct, spark is excluded from Step 6.8 condition |
| 4 | Event files are written correctly | `pending-events/20260318-201249-autopilot.json` and `20260318-201345-reflect.json` contain valid JSON with correct project_id, skill, status, task_label |

## Additional Observations

### Events ARE being processed (but not by wake)

Despite the wake failing, pending-event files ARE being moved to `processed/`. The `openclaw-gateway` service (PID 4103935, started 20:12) appears to have its own internal file scanner that processes events independently. This confirms the spec's design: "cron stays as fallback if wake fails." The fallback IS working — but via the gateway's built-in scan, not the 5-minute cron.

### Latency comparison

| Event | Created | Processed | Latency |
|-------|---------|-----------|---------|
| Pre-TECH-157 autopilot (19:34:36) | 19:34 | ~19:40 | ~6 min (cron/gateway scan) |
| Post-TECH-157 autopilot (20:12:49) | 20:12 | ~20:18 | ~6 min (wake failed, same fallback) |

No latency improvement observed — consistent with wake not working.

### Root cause chain

```
timeout 5s → too short (Node.js cold start ~11s)
  → process killed before argument validation
    → even if survived: --text missing → exit 1
      → || true suppresses failure
        → log misleadingly says "wake sent"
```
