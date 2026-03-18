# Devil's Advocate — Silence intermediate Telegram notifications during DLD cycle

## Why NOT Do This?

### Argument 1: Autopilot failures become invisible
**Concern:** The proposal says "Ошибки (failed tasks) — можно оставить, обсудить отдельно" without a concrete decision. The natural implementation of `if [[ "$SKILL" == "autopilot" ]]; then SKIP_NOTIFY=true` suppresses BOTH success and failure notifications. The user won't know autopilot crashed until OpenClaw wakes and reports — which may be minutes later, or never if OpenClaw itself has issues.
**Evidence:** `pueue-callback.sh:238-263` — the current SKIP_NOTIFY block has no skill-level exception for `STATUS=failed`. Adding autopilot to the skip list without a `"$STATUS" == "done"` guard silences the `❌ PROJ: Автопилот по TECH-N — ошибка` notifications too.
**Impact:** High
**Counter:** Implement as `if [[ "$SKILL" == "autopilot" && "$STATUS" == "done" ]]; then SKIP_NOTIFY=true`. Failures must always notify.

### Argument 2: OpenClaw becomes a single point of failure for cycle feedback
**Concern:** After silencing the DLD bot, the entire notification chain becomes: callback writes `pending-events/` → OpenClaw reads → OpenClaw sends summary. If OpenClaw crashes, times out, or has a parse error, the user gets zero feedback about completed work. Currently the DLD bot acts as an independent fallback path.
**Evidence:** `openclaw-artifact-scan.py:85-140` — OpenClaw reads `pending-events/*.json` idempotently. There is no TTL, watchdog, or retry mechanism. The `processed-events/` directory shows real events have been processed (e.g. `20260318-192159-qa.json`), but nothing guards against OpenClaw being down during a cycle.
**Impact:** High
**Counter:** Keep DLD bot as a time-gated fallback: suppress notifications normally, but if `STATUS=failed` OR if a task has been in `qa_pending` for >30 minutes with no OpenClaw response, send a DLD bot alert.

### Argument 3: inbox-processor "Starting..." is an acknowledgement receipt, not intermediate noise
**Concern:** When a user sends a Telegram message, the flow is: message → inbox file → inbox-processor sends "🚀 Создаю спеку". This notification is not an intermediate cycle step — it is proof the user's message was received and acted upon. Silencing it would leave the user wondering if their message was lost for 30+ minutes.
**Evidence:** `inbox-processor.sh:183-191` — `NOTIFY_MSG="🚀 *${PROJECT_ID}*: ${SKILL_LABEL}\n${IDEA_SHORT}"` is sent unconditionally before pueue dispatch. The inbox source file (`done/20260318-silence-intermediate-notifications.md`) says to silence spark/autopilot/qa but does not explicitly include inbox-processor pre-dispatch notifications.
**Impact:** Medium
**Counter:** Do NOT silence inbox-processor.sh "Starting..." notifications. They serve a different purpose (acknowledgement) than callback completion notifications (progress reporting).

### Argument 4: Spark from inbox is a terminal task, not an intermediate step
**Concern:** The proposal groups spark with "intermediate" cycle steps. But a spark triggered from inbox (user asks "create a spec for X") is the TERMINAL task — autopilot does not follow immediately. Silencing spark completion removes the only signal that the spec was created. Note also that Step 6.8 in pueue-callback.sh currently only writes pending-events for `autopilot`, `qa`, and `reflect` — NOT for spark (`pueue-callback.sh:296`). So if spark is silenced, there is also no OpenClaw wake event.
**Evidence:** `inbox-processor.sh:90-106` — spark and spark_bug routes produce a spec file and that's it. `pueue-callback.sh:296` — event write condition is `"$SKILL" == "autopilot" || "$SKILL" == "qa" || "$SKILL" == "reflect"`.
**Impact:** Medium
**Counter:** Either keep spark notification in pueue-callback.sh, OR extend Step 6.8 to also write pending-events for spark skill before silencing it.

---

## Simpler Alternatives

### Alternative 1: Silence cycle interior only (autopilot success + qa success)
**Instead of:** SKIP_NOTIFY=true for spark, autopilot, qa broadly
**Do this:** Add `SKIP_NOTIFY=true` only for: `autopilot` with `STATUS=done`, `qa` with `STATUS=done`. Reflect is already silenced. Keep: spark completions, all failures, inbox-processor "Starting..." receipts.
**Pros:** 2 conditional blocks added to pueue-callback.sh only. Preserves failure visibility. Preserves acknowledgement receipts. OpenClaw still gets its events unaffected. Lowest regression risk.
**Cons:** User still sees spark completion notification for inbox-triggered tasks. Acceptable — these are terminal.
**Viability:** High — solves 90% of cycle noise with 10% of the risk.

### Alternative 2: Silence spark completions too, but extend Step 6.8 to cover spark
**Instead of:** Keeping spark notifications
**Do this:** Silence spark in pueue-callback.sh AND extend Step 6.8 to write a pending-event for spark completions. OpenClaw then has full visibility.
**Pros:** Fully silent cycle. OpenClaw is informed about everything.
**Cons:** Requires two changes (SKIP_NOTIFY + Step 6.8 extension). OpenClaw must handle spark events in its reporting logic.
**Viability:** Medium — cleaner long-term but more moving parts now.

### Alternative 3: Do nothing in code — mute Telegram topic
**Instead of:** Any code change
**Do this:** Mute the project's Telegram topic during active cycle hours (Telegram client setting).
**Pros:** Zero code change. Zero regression risk.
**Cons:** Manual per-user action. Doesn't work in shared group contexts. Does not address the design goal of OpenClaw owning cycle reporting.
**Viability:** Low — treats symptom, not cause.

**Verdict:** Alternative 1 is the correct minimal implementation. Silence autopilot SUCCESS and QA SUCCESS in pueue-callback.sh. Do not silence spark, do not silence failures, do not touch inbox-processor.sh. Spark + inbox-processor can be addressed in a follow-up once OpenClaw coverage is confirmed.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Autopilot succeeds | skill=autopilot, STATUS=done | No Telegram notification sent | High | P0 | deterministic |
| DA-2 | Autopilot fails | skill=autopilot, STATUS=failed | Telegram notification sent (❌) | High | P0 | deterministic |
| DA-3 | QA succeeds | skill=qa, STATUS=done | No Telegram notification sent | High | P0 | deterministic |
| DA-4 | QA fails | skill=qa, STATUS=failed | Telegram notification sent (❌) | High | P0 | deterministic |
| DA-5 | Spark from inbox completes | skill=spark, STATUS=done | Notification sent (terminal task, no OpenClaw event) | Med | P1 | deterministic |
| DA-6 | inbox-processor fires before dispatch | any route (spark/autopilot/qa) | "🚀 Starting..." notification sent (unchanged) | Med | P1 | deterministic |
| DA-7 | pending-events written when autopilot silenced | skill=autopilot, STATUS=done, SKIP_NOTIFY=true | Step 6.8 still writes EVENT file in ai/openclaw/pending-events/ | High | P0 | deterministic |
| DA-8 | Reflect already silenced | skill=reflect, any status | SKIP_NOTIFY=true (behavior unchanged from before) | Low | P2 | deterministic |
| DA-9 | Secondary QA from inbox already silenced | skill=qa, label starts with qa-inbox- | SKIP_NOTIFY=true (behavior unchanged from before) | Low | P2 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | pending-events write (Step 6.8) | pueue-callback.sh:287-318 | Step 6.8 executes regardless of SKIP_NOTIFY value — must not be gated | P0 |
| SA-2 | QA dispatch after autopilot (Step 7) | pueue-callback.sh:325-368 | QA still dispatched when autopilot done, SKIP_NOTIFY has no effect on dispatch logic | P0 |
| SA-3 | Reflect dispatch after autopilot (Step 7) | pueue-callback.sh:370-395 | Reflect still dispatched when autopilot done | P0 |
| SA-4 | inbox-processor "Starting..." | inbox-processor.sh:183-191 | inbox-processor.sh not modified — notification fires as before | P1 |
| SA-5 | qa-loop.sh independent notify | scripts/vps/qa-loop.sh | qa-loop.sh has its own notify calls — audit required before closing scope | P1 |

### Assertion Summary
- Deterministic: 9 | Side-effect: 5 | Total: 14

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| Step 6.8 pending-events write | pueue-callback.sh:287-318 | If implementor accidentally wraps Step 6.8 inside `if [[ "$SKIP_NOTIFY" == "false" ]]`, OpenClaw loses wake signals | Keep Step 6.8 unconditional — it is durable event infrastructure, not a notification |
| QA/Reflect tail dispatch (Step 7) | pueue-callback.sh:325-397 | Same risk: if refactor accidentally moves Step 7 inside SKIP_NOTIFY gate, QA and Reflect stop dispatching | Keep Step 7 unconditional — it is dispatch logic, not notification |
| qa-loop.sh | scripts/vps/qa-loop.sh | qa-loop.sh is a separate script with its own notify.py calls — not in scope of pueue-callback.sh changes but may create inconsistency | Audit qa-loop.sh before releasing |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| OpenClaw pending-events | data | High | If Step 6.8 gated on SKIP_NOTIFY=false, OpenClaw loses wake signals — must remain unconditional |
| inbox-processor.sh notify path | call | Medium | inbox-processor.sh calls notify.py independently from pueue-callback.sh — changes to callback do not affect it |
| qa-loop.sh notify | call | Medium | Independent script with its own notify.py calls, not covered by this proposal's scope |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Should autopilot and QA FAILURES still notify via DLD bot?
   **Why it matters:** If "yes" (strongly recommended), the implementation must guard with `STATUS == "done"`, not just check the skill name. This is the highest-risk implementation mistake — easy to get wrong, invisible until an autopilot crash goes unnoticed for hours.

2. **Question:** Should spark completion from inbox be silenced?
   **Why it matters:** Spark is terminal for inbox-originated tasks. Silencing it means zero feedback for a 20-30 min spark run. Critically: Step 6.8 does NOT currently write pending-events for spark (`pueue-callback.sh:296`), so OpenClaw won't know spark completed either. If spark is to be silenced, Step 6.8 must be extended to cover it first.

3. **Question:** Should inbox-processor "Starting..." notifications be suppressed?
   **Why it matters:** These are acknowledgement receipts for user-originated messages. Silencing them breaks the user's mental model: "I sent a message, did it arrive?" They are structurally different from cycle-internal progress noise.

4. **Question:** What is the recovery path if OpenClaw is unresponsive for 1+ hours?
   **Why it matters:** After this change, OpenClaw is the sole reporting path for cycle completion. Without a fallback mechanism, a prolonged OpenClaw outage means zero visibility into what the orchestrator is doing.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The noise reduction goal is valid — autopilot+QA completions during a cycle generate 2-3 notifications per task that OpenClaw already consolidates. The correct minimal change is: silence autopilot and qa in pueue-callback.sh, but ONLY for `STATUS=done`. Failures must remain visible. Spark should remain visible (it is terminal for inbox tasks and has no OpenClaw fallback yet). inbox-processor.sh must not be touched.

**Conditions for success:**
1. `SKIP_NOTIFY=true` for autopilot MUST be conditional on `STATUS == "done"` — failures alert always (P0)
2. `SKIP_NOTIFY=true` for qa MUST be conditional on `STATUS == "done"` — failures alert always (P0)
3. Step 6.8 (pending-events write) and Step 7 (QA/Reflect dispatch) in pueue-callback.sh must remain unconditional — not gated on SKIP_NOTIFY (P0)
4. inbox-processor.sh "Starting..." notification must NOT be silenced (acknowledgement receipt)
5. Audit qa-loop.sh for independent notify.py calls before declaring scope complete
