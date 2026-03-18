# Devil's Advocate: Notification Suppression Risks

## Critical Risks

1. **OpenClaw SPOF**: If OpenClaw crashes, user gets ZERO notifications. Mitigation: keep error notifications active.

2. **Failed Task Notifications**: SKIP_NOTIFY must only suppress SUCCESS notifications, not FAILURES. Current plan says "errors — discuss separately" but implementation must explicitly preserve them.

3. **User Feedback Void**: User sends message → silence. Acceptable if OpenClaw acknowledges. Risk if OpenClaw is slow (>2 min).

4. **Pending Events Safe**: Step 6.8 runs before Step 6. SKIP_NOTIFY doesn't affect events.

5. **Night Reviewer**: Already handled by group check (line 75-79). No change needed.

## CRITICAL IMPLEMENTATION NOTE

The SKIP_NOTIFY for spark/autopilot/qa must be conditioned on STATUS == "done" only.
Failed tasks must still notify.

## Eval Criteria

| ID | Scenario | Expected | Type |
|----|----------|----------|------|
| EC-1 | Spark completes successfully | No Telegram notification | deterministic |
| EC-2 | Autopilot completes successfully | No notification, pending-event written | deterministic |
| EC-3 | Autopilot FAILS | Telegram notification IS sent | deterministic |
| EC-4 | QA completes successfully | No notification | deterministic |
| EC-5 | inbox-processor dispatches spark | No "Starting" notification | deterministic |

## Verdict: Proceed — but preserve failure notifications
