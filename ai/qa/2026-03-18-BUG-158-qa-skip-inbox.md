# QA Report: BUG-158 — QA dispatch fails for inbox tasks

**Date:** 2026-03-18
**Environment:** VPS orchestrator (pueue + callback pipeline), dld project
**Trigger:** `/qa BUG-158` — verify fix for "spec file not found" noise on inbox tasks

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 5     | 5    | 0    | 0       |

## Passed

| # | Scenario | Evidence |
|---|----------|----------|
| 1 | Inbox tasks complete without "spec file not found" error | 9 inbox tasks (#710-#729) completed. `grep "spec.*not found" callback-debug.log` = 0 results |
| 2 | No `qa-inbox-*` tasks spawned after inbox completion | `pueue status --json` analysis: 0 tasks matching `qa-inbox*` pattern across 733 total tasks |
| 3 | QA dispatches correctly for spec-based tasks (BUG-158) | Task #728 (autopilot BUG-158) -> #730 (qa-BUG-158) created and running. Log: `TASK_LABEL=BUG-158 (used as QA spec_id)` |
| 4 | Reflect dispatches for spec-based tasks | Task #728 -> #731 (reflect-BUG-158) created. Log: `reflect dispatched OK: project=dld task=BUG-158` |
| 5 | No noisy Telegram notifications about spec errors | `journalctl -u dld-bot` and `callback-debug.log`: zero "spec not found" or "QA failed" messages in last 2 hours |

## Detailed Observations

### Scenario 1: Inbox tasks complete cleanly

**Steps:** Checked 9 completed inbox tasks from last 2 hours:
- #710 `inbox-20260318-192656` -> callback: `skill=spark status=done`
- #714 `inbox-20260318-195623` -> callback: `skill=spark status=done`
- #716 `inbox-20260318-200931` (original bug trigger!) -> callback: `skill=spark status=done`
- #720-#729 (6 more inbox tasks) -> all `skill=spark status=done`

**Result:** All 9 inbox tasks completed with clean callback, no QA dispatch attempted, no error notifications.

### Scenario 2: No qa-inbox tasks exist

**Steps:** Parsed all 733 pueue tasks, filtered for `qa-inbox*` pattern.
**Result:** Zero matches. QA tasks only exist for spec IDs: `qa-TECH-151`, `qa-TECH-153`, `qa-TECH-154`, `qa-BUG-155`, `qa-TECH-156`, `qa-TECH-157`, `qa-BUG-158`.

### Scenario 3: Spec tasks still get QA

**Steps:** Traced BUG-158 autopilot task #728 through callback pipeline.
**Result:** Callback correctly identified `TASK_LABEL=BUG-158`, dispatched `qa-BUG-158` (#730, currently running) and `reflect-BUG-158` (#731).

### Scenario 5: No noisy notifications

**Steps:** Searched bot logs and callback log for error patterns.
**Result:** Zero matches for "spec not found", "QA failed", "QA skipped" in Telegram bot output.

## Notes

- The fix works via a different mechanism than described in the spec: inbox tasks are dispatched as `skill=spark` (not autopilot), so the callback's post-autopilot QA logic (Step 7) is never reached for them. The TASK_LABEL regex guard in the spec provides defense-in-depth for cases where inbox tasks might go through autopilot directly.
- The `callback-debug.log` shows no "Skipping QA" messages — this is because inbox tasks are classified as `spark` skill, bypassing the autopilot post-processing entirely. The guard is a safety net, not the primary fix path.
