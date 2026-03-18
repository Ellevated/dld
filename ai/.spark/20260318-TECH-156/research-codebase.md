# Codebase Research — Silence Intermediate Telegram Notifications (TECH-156)

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `SKIP_NOTIFY` gate | scripts/vps/pueue-callback.sh:238-263 | Existing skip-notify pattern with multiple conditions | Extend — add spark/autopilot/qa success cases |
| `SKILL` extraction | scripts/vps/pueue-callback.sh:127-131 | Parses skill name from agent JSON output | Import directly — already reliable |
| reflect skip pattern | scripts/vps/pueue-callback.sh:241-244 | `if [[ "$SKILL" == "reflect" ]]; then SKIP_NOTIFY=true` | Exact pattern to replicate for other skills |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| reflect skip | pueue-callback.sh:241-244 | Already silenced — single-skill condition | Identical pattern for spark/autopilot/qa |
| secondary QA skip | pueue-callback.sh:248-251 | Label-based noise filter | Same SKIP_NOTIFY mechanism |
| night-reviewer early exit | pueue-callback.sh:75-79 | Group-level skip before DB work | Different scope — group, not skill |

**Recommendation:** Extend the existing `SKIP_NOTIFY` block in `pueue-callback.sh` (lines 238-263). Add a skill-list check: `spark`, `autopilot`, `qa` on success → `SKIP_NOTIFY=true`. Keep failures surfaced. In `inbox-processor.sh` lines 186-191 add a parallel guard skipping pre-dispatch notify for the same three skills. No new abstractions needed — the pattern is already proven.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
grep -rn "notify\.py" scripts/vps/
# Results: 8 call sites across 5 files
```

| File | Line | Usage |
|------|------|-------|
| scripts/vps/pueue-callback.sh | 267 | `python3 "$NOTIFY_PY" "$PROJECT_ID" "$MSG"` — completion notification |
| scripts/vps/inbox-processor.sh | 188 | `python3 "$NOTIFY_PY" "$PROJECT_ID" "$NOTIFY_MSG"` — pre-dispatch "Starting..." |
| scripts/vps/qa-loop.sh | 42 | `notify.py ... "QA skipped: spec not found"` — error path only |
| scripts/vps/qa-loop.sh | 108 | `notify.py ... "$NOTIFY_TEXT"` — QA PASSED |
| scripts/vps/qa-loop.sh | 112 | `notify.py ... "$NOTIFY_TEXT"` — QA FAILED |
| scripts/vps/night-reviewer.sh | 215 | `notify.py "${PROJECT_ID}" "${msg}"` — each new finding |

`orchestrator.sh` references venv path for `notify.py` (line 27) but does NOT call it directly — 0 call sites. `telegram-bot.py` uses `context.bot.send_message()` directly for interactive approval flows — separate channel, not `notify.py`.

### Step 2: DOWN — What does pueue-callback.sh depend on?

| Dependency | File | Function |
|------------|------|----------|
| db.py | scripts/vps/db.py | `callback()`, `get_project_state()` |
| notify.py | scripts/vps/notify.py | CLI: `notify.py <project_id> <msg>` |
| pueue CLI | PATH | `pueue status --json`, `pueue log`, `pueue add` |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "SKIP_NOTIFY" scripts/vps/
# Results: 7 occurrences, all in pueue-callback.sh
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/pueue-callback.sh | 238 | `SKIP_NOTIFY=false` — initial value |
| scripts/vps/pueue-callback.sh | 241 | reflect skip condition |
| scripts/vps/pueue-callback.sh | 248 | secondary QA skip condition |
| scripts/vps/pueue-callback.sh | 254 | unknown skill skip condition |
| scripts/vps/pueue-callback.sh | 260 | failed+no-skill skip condition |
| scripts/vps/pueue-callback.sh | 265 | gate: `if [[ "$SKIP_NOTIFY" == "false" ...` |
| scripts/vps/pueue-callback.sh | 402 | debug log entry: `skip_notify=${SKIP_NOTIFY}` |

```bash
grep -rn "NOTIFY_MSG\|notify\.py" scripts/vps/inbox-processor.sh
# Results: 4 occurrences, lines 170-191
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/inbox-processor.sh | 170-179 | Skill label map for pre-dispatch message |
| scripts/vps/inbox-processor.sh | 183-184 | Builds `NOTIFY_MSG="🚀 *${PROJECT_ID}*: ${SKILL_LABEL}\n${IDEA_SHORT}"` |
| scripts/vps/inbox-processor.sh | 186 | `NOTIFY_PY="${SCRIPT_DIR}/notify.py"` |
| scripts/vps/inbox-processor.sh | 188 | `python3 "$NOTIFY_PY" "$PROJECT_ID" "$NOTIFY_MSG"` |

### Step 4: CHECKLIST — Mandatory folders

- [x] `tests/**` — `scripts/vps/tests/test_cycle_smoke.py` covers `notify.py` OPS_TOPIC_ID fallback (class `TestNotifyFallback`, lines 147-200). `scripts/vps/tests/test_notify.py` directly tests `send_to_project`. Both files exist.
- [ ] `db/migrations/**` — N/A, no schema changes
- [ ] `ai/glossary/**` — N/A, notification behavior is not domain-level

### Step 5: DUAL SYSTEM check

N/A — not changing data source. The OpenClaw `pending-events` files are written in Step 6.8 of `pueue-callback.sh` (lines 287-318), which runs BEFORE the `SKIP_NOTIFY` gate (lines 265-273). Silencing Telegram does not affect event file generation. The two systems are already orthogonal.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| scripts/vps/pueue-callback.sh | 402 | Pueue completion callback — core notification gate | modify |
| scripts/vps/inbox-processor.sh | 239 | Inbox dispatch — pre-dispatch "Starting..." notification | modify |
| scripts/vps/qa-loop.sh | 114 | QA runner — sends QA PASSED/FAILED independently | read-only (see Risk 1) |

**Total:** 2 files to modify, 1 file to review, 641 LOC

---

## Full Notification Source Map

| Source | File:line | Trigger | Silence? |
|--------|-----------|---------|----------|
| Completion (spark/autopilot/qa) success | pueue-callback.sh:267 | Task completes | YES |
| Completion failure | pueue-callback.sh:267 | Task fails | KEEP |
| Pre-dispatch "🚀 Starting..." | inbox-processor.sh:188 | Before inbox task launch | YES (spark/autopilot/qa) |
| QA PASSED | qa-loop.sh:108 | QA exit 0 | YES — qa-loop bypasses callback |
| QA FAILED | qa-loop.sh:112 | QA exit non-zero | KEEP |
| QA skipped (spec not found) | qa-loop.sh:42 | Error path | KEEP |
| Night finding per item | night-reviewer.sh:215 | Each new night audit finding | KEEP |
| Approval prompt | telegram-bot.py:169 | Spark spec ready — user action | KEEP |

---

## Reuse Opportunities

### Import (use as-is)
- `SKILL` variable extraction (pueue-callback.sh:127-131) — already parsed from agent JSON, available for any condition in the same script.

### Extend (copy structure, not code)
- Extend the `SKIP_NOTIFY` block at lines 238-263: replace individual skill checks with `case "$SKILL" in spark|autopilot|qa) if [[ "$STATUS" == "done" ]]; then SKIP_NOTIFY=true; fi ;; esac`.

### Pattern (copy structure, not code)
- The reverted commit `6b16f6a` (2026-03-18 19:26:34) has the exact correct implementation for `pueue-callback.sh`. It used `SKIP_NOTIFY=true` as default and unset it only for `STATUS=failed && SKILL != ""`. The diff is 9 lines added / 25 removed — can be used as reference.

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -8 -- scripts/vps/pueue-callback.sh scripts/vps/inbox-processor.sh
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-18 | a214790 | Ellevated | Revert "fix(orchestrator): silence all intermediate notifications..." |
| 2026-03-18 | 6b16f6a | Ellevated | fix(orchestrator): silence all intermediate notifications — north-star compliance |
| 2026-03-18 | 3ca3e21 | Ellevated | fix(orchestrator): BUG-155 cycle e2e reliability v2 — 4 bugs fixed + smoke test |
| 2026-03-18 | 99d8ba7 | Ellevated | fix(orchestrator): TECH-154 cycle e2e reliability |
| 2026-03-18 | e7d619d | Ellevated | fix(orchestrator): always dispatch reflect after autopilot |
| 2026-03-18 | 1b358e4 | Ellevated | fix(inbox): enforce topic-scoped routing |
| 2026-03-18 | 1721266 | Ellevated | fix(inbox): write TASK_CMD to file to avoid pueue shell escaping |

**Observation — CRITICAL:** This feature was already implemented in commit `6b16f6a` and immediately reverted in `a214790` (same minute, 19:26). The revert has no explanation in the commit message. Examining the diff: the previous attempt only modified `pueue-callback.sh` — it did NOT touch `inbox-processor.sh` pre-dispatch notifications. The current task explicitly includes `inbox-processor.sh`, which is the missing piece from the previous attempt. The implementation approach in the reverted commit was correct and can be directly reused.

---

## Risks

1. **Risk:** `qa-loop.sh` sends notifications that bypass `pueue-callback.sh` entirely
   **Impact:** `qa-loop.sh` is called from `orchestrator.sh` as a background subprocess (`dispatch_qa()`), not through pueue. Its QA PASSED notification (line 108) will continue to fire even after `pueue-callback.sh` is silenced. This creates an incomplete silence.
   **Mitigation:** Silence `qa-loop.sh` line 108 for the PASSED case. Keep line 112 (FAILED) and line 42 (spec not found). Adds qa-loop.sh to the change set.

2. **Risk:** The previous implementation (6b16f6a) was reverted 24 seconds after being created
   **Impact:** Unknown failure — possibly triggered a smoke test failure, possibly a scope issue (missing inbox-processor.sh). Current task explicitly covers both files, which is the gap.
   **Mitigation:** Cover all three files (pueue-callback.sh, inbox-processor.sh, qa-loop.sh) in one atomic commit. Verify `test_cycle_smoke.py` and `test_notify.py` still pass after change.

3. **Risk:** Silencing spark success notification suppresses the approval prompt flow
   **Impact:** In `pueue-callback.sh`, `SKIP_NOTIFY` only controls the generic completion message. The approval prompt (`telegram-bot.py:169`, `auto_approve_start()`) is triggered separately via `auto_approve_start()` in `telegram-bot.py` — it does NOT go through `pueue-callback.sh`. These are independent flows.
   **Mitigation:** No action needed — confirm `auto_approve_start()` call path is not via `notify.py` (confirmed: it uses `context.bot.send_message()` directly at telegram-bot.py:169).
