# Devil's Advocate — BUG-162: Orphan Slot Watchdog

## Why NOT Do This?

### Argument 1: False Positive Wipe on Pueue Failure
**Concern:** `pueue status --json` can fail silently. The proposal calls `get_pueue_running_ids()` and compares DB slots against the result. If pueue is unresponsive, the subprocess call raises an exception — but the proposal's `except Exception: pass` pattern (same as `is_agent_running` at orchestrator.py:113) returns an **empty set**, not an error. All occupied slots would look like orphans and be released simultaneously, freeing slots for 2-3 new dispatches while real agents are still running.

**Evidence:** `is_agent_running` (orchestrator.py:100-115) uses identical `except Exception: pass` — returns False on any error. The same pattern in watchdog returns empty set = triggers mass release. `pueue status` has a 10-second timeout (callback.py:66), and the VPS has up to 3 concurrent sessions. A temporary pueue hang during load causes a catastrophic false positive.

**Impact:** High

**Counter:** Only proceed if `get_pueue_running_ids()` distinguishes between "empty list of tasks" and "pueue call failed". Must return `None` on failure and skip the watchdog entirely that cycle (not release anything).

---

### Argument 2: Race Condition — Callback and Watchdog Collide
**Concern:** Both `callback.py:release_slot(pueue_id)` (db.py:76) and the new watchdog call `release_slot` on the same row. Both use `BEGIN IMMEDIATE`. SQLite serializes them — one wins, the other sees `row is None` (db.py:83 returns `None` if pueue_id not found). This is safe at the DB level, but the watchdog may fire **between** the moment pueue marks a task "done" and the moment callback.py has run. Result: watchdog releases the slot, callback.py's `release_slot` gets `None` (no-op), but `finish_task` and `update_project_phase` still run correctly. Net effect: correct, but the log will show two release attempts on the same pueue_id — could confuse ops.

**Evidence:** db.py:76-91 — `release_slot` is idempotent (returns None when row not found, no UPDATE). The IMMEDIATE lock serializes concurrent writers. No data corruption risk, but log noise is a real issue since both paths are silent on the "already released" case.

**Impact:** Medium

**Counter:** Log a WARNING when watchdog releases a slot that callback.py should have handled. Add a `source` parameter to `release_slot` so logs say `watchdog` vs `callback`. This surfaces missed callbacks as a separate diagnostic signal.

---

### Argument 3: Pueue ID Reset After Daemon Restart
**Concern:** Pueue uses monotonically increasing integer IDs per daemon lifetime. After `pueued` restart, it starts from 0 (or 1). If pueue restarts, old pueue_ids in `compute_slots` will never match any new pueue task — the watchdog correctly releases them. BUT if pueue resets IDs and a new task gets the same numeric ID as an old orphaned slot, the watchdog sees it as "running" and keeps the slot locked forever.

**Evidence:** schema.sql:31 — `pueue_id INTEGER` (no UNIQUE constraint). If pueue restarts and task ID 5 is now a fresh QA job, and the DB has an orphaned slot with pueue_id=5 from before the restart — watchdog thinks slot is still occupied.

**Impact:** Medium

**Counter:** Add a `acquired_at` age threshold: only consider slots orphaned if `acquired_at < now - N minutes` (e.g., 30 min). This eliminates the ID collision window for recently restarted pueue. Alternatively, store pueue daemon start time in DB and invalidate on restart detection.

---

### Argument 4: Queued Tasks Are Not Orphaned
**Concern:** The proposal checks for Running OR Queued pueue tasks as "alive". But tasks can sit in Queued state for extended periods when all parallel slots in a group are occupied. If watchdog treats a task as "alive because Queued in pueue", the slot stays correctly reserved. This seems fine — but Stashed and Paused tasks are edge cases: pueue supports manually Stashing (holding) tasks. A stashed task is still "there" but not running. If the watchdog only counts Running+Queued and a task is Stashed, the slot gets freed while the task is still in pueue waiting for manual unstash.

**Evidence:** callback.py:163-165 checks `"Running" in status or "Queued" in status` for `is_already_queued`. The proposal inherits this pattern but doesn't address Stashed/Paused. In normal DLD usage Stashed tasks don't occur, but operator `pueue stash <id>` during incident response would trigger false release.

**Impact:** Low (non-standard operator action needed to trigger)

**Counter:** Document that watchdog does not protect Stashed/Paused tasks. Acceptable for this use case. Or add Stashed/Paused to the "alive" set.

---

## Simpler Alternatives

### Alternative 1: Manual CLI Command, Not Automatic Watchdog
**Instead of:** Automatic watchdog on every cycle
**Do this:** Add `python3 db.py release-orphan-slots` CLI command to db.py that an operator runs post-restart. Same logic, no automatic execution.
**Pros:** Zero risk of false-positive mass release. Operator runs it once after a known-bad restart, with eyes on logs. No additional `pueue status` call per cycle.
**Cons:** Requires operator intervention — doesn't self-heal. The stated problem (orchestrator hangs silently after restart) remains until someone notices.
**Viability:** Medium — solves the restart case but misses cases where operator is unavailable.

### Alternative 2: Age-Based TTL Only (No Pueue Query)
**Instead of:** Querying pueue for live task IDs
**Do this:** Add `acquired_at` staleness check — release any slot with `acquired_at < now() - MAX_TASK_DURATION` (e.g., 90 minutes, since MAX_TURNS=80 at 60min wall clock).
**Pros:** No pueue dependency, no false-positive risk from pueue failures. One SQL query, no subprocess. Works even if pueue is completely down.
**Cons:** Fixed timeout means legitimately long tasks (edge case) get their slot force-released. But current `MAX_TIMEOUT=60min` from runner config makes a 90-min TTL safe.
**Viability:** High — simpler, more robust than pueue-query approach. No race conditions, no ID reset risk.

### Alternative 3: Watchdog Only On Startup (Not Every Cycle)
**Instead of:** Running watchdog every 5-minute poll cycle
**Do this:** Run `release_orphan_slots()` once in `main()` at startup, before the poll loop begins.
**Pros:** Solves the stated problem (restart leaves stale slots) with minimal ongoing risk. No per-cycle pueue overhead. The watchdog runs at the moment when stale slots are most likely.
**Cons:** Doesn't catch orphans that accumulate mid-run (e.g., pueue task killed externally while orchestrator is running). But per the inbox description, the real trigger is service restarts.
**Viability:** High — directly solves the stated root cause.

**Verdict:** Alternative 2 (TTL-based) or Alternative 3 (startup-only) solve 90% of the stated problem with zero pueue query risk. The full watchdog is justified only if we see orphans accumulate mid-run — not demonstrated in the bug report. Recommend starting with Alternative 3 (startup-only) and adding TTL as a secondary guard.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Pueue call fails (timeout/exception) | `pueue status` returns non-zero / raises | Watchdog does NOT release any slots; logs error | High | P0 | deterministic |
| DA-2 | Normal cycle: 2 slots occupied, both pueue tasks Running | DB has slot 1 pueue_id=5, slot 2 pueue_id=6; pueue returns both Running | No slots released | High | P0 | deterministic |
| DA-3 | Genuine orphan: task finished without callback | DB has slot with pueue_id=99; pueue has no task 99 | Slot released; logged with `source=watchdog` | High | P0 | deterministic |
| DA-4 | Callback fires same cycle as watchdog | Slot with pueue_id=7; callback releases first, then watchdog runs | Watchdog sees no row for pueue_id=7; no double release; no error | High | P0 | deterministic |
| DA-5 | Pueue returns empty task list (no tasks at all) | All pueue groups empty, DB has 1 occupied slot (task just submitted) | Must check: is this a real "empty" or pueue failure? Only release if pueue call succeeded | High | P0 | deterministic |
| DA-6 | Pueue ID reuse after daemon restart | DB slot pueue_id=3; pueue restarts; new task gets id=3 | Slot NOT released (appears live) — acceptable tradeoff; document | Medium | P1 | deterministic |
| DA-7 | Task is Queued in pueue (not yet Running) | DB slot pueue_id=10; pueue shows task 10 as Queued | Slot NOT released | Medium | P1 | deterministic |
| DA-8 | Pueue returns `{}` tasks dict (empty JSON, valid response) | Valid pueue response with no tasks | Treat as "all orphans" ONLY if pueue call exit_code=0 | High | P0 | deterministic |
| DA-9 | All slots are free (no occupied slots) | `compute_slots` has no rows with non-NULL pueue_id | Watchdog is no-op; no queries to pueue needed | Low | P2 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | `is_agent_running` pueue call | orchestrator.py:103-114 | Existing pueue call in same cycle — no double invocation needed (can reuse result) | P1 |
| SA-2 | `scan_backlog` slot check | orchestrator.py:306 | `get_available_slots` still returns correct count after watchdog runs | P0 |
| SA-3 | `callback.py:release_slot` | callback.py:272-275 | `db.release_slot` returns None gracefully when slot already freed by watchdog | P0 |
| SA-4 | `task_log` table | db.py:156-164 | `finish_task` with pueue_id of watchdog-released slot still updates correctly (separate table) | P1 |

### Assertion Summary
- Deterministic: 9 | Side-effect: 4 | Total: 13

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| `is_agent_running` | orchestrator.py:100-115 | Both `is_agent_running` and watchdog call `pueue status --json` in same cycle — 2x subprocess overhead per cycle | Refactor: extract shared `_get_pueue_tasks()` cache, reuse within one cycle |
| `callback.py:release_slot` | callback.py:272-275 | Watchdog may preempt callback; `release_slot` returns None silently — no error, but missed callback becomes invisible | Add WARNING log in callback when `release_slot` returns None for a completed task |
| `scan_backlog` slot dispatch | orchestrator.py:306 | If watchdog runs AFTER `get_available_slots` check but BEFORE `try_acquire_slot`, a freed slot could be double-acquired | Watchdog must run at cycle START (before any dispatch), not inside `process_project` per-project |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| pueue CLI | subprocess/external | High | Must distinguish failure from "no tasks"; check `r.returncode == 0` before trusting result |
| SQLite WAL + BEGIN IMMEDIATE | data | Low | Already correct — `release_slot` is idempotent under concurrent access |
| `compute_slots.pueue_id` | data | Medium | No UNIQUE constraint — pueue ID reuse after restart is possible; add `acquired_at` TTL guard |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Should `get_pueue_running_ids()` also include "Queued" tasks, or only "Running"?
   **Why it matters:** A task freshly submitted is Queued before it starts Running. If only Running is included, a Queued task's slot is freed by the watchdog within the same cycle it was submitted. At current poll interval (300s), this window is small but real during high load.

2. **Question:** Can we share the pueue status call between `is_agent_running` and the watchdog?
   **Why it matters:** Each `pueue status --json` is a subprocess call with 10s timeout. Running it twice per cycle per project adds latency and doubles the chance of timeout under load. The right design is a single call that populates both `is_agent_running` and the orphan check.

3. **Question:** Where exactly in `main()` does the watchdog run — before or inside `for proj in db.get_all_projects()`?
   **Why it matters:** If inside `process_project`, it runs N times per cycle (once per project) but pueue slots are global (not per-project). Running it once per cycle at the top of the loop is correct. Running it N times is wasteful and multiplies the risk window.

4. **Question:** What is the expected behavior when pueue daemon is completely stopped (not just slow)?
   **Why it matters:** `pueued` stop + orchestrator still running is a valid maintenance scenario. In this state ALL slots look orphaned. The watchdog must not release them — this would allow the orchestrator to dispatch tasks to a stopped pueue, which would fail silently.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The problem is real — stale slots do block the orchestrator after restarts. The proposed solution is conceptually correct but has one critical flaw: it uses the same `except Exception: pass` pattern as `is_agent_running`, which means pueue failure = empty set = all slots released. This is a higher-severity bug than the one it's fixing.

**Conditions for success:**
1. `get_pueue_running_ids()` MUST return `None` on error (subprocess failure, timeout, bad JSON) and the watchdog must skip entirely when it gets `None` — not treat it as "no running tasks"
2. Watchdog runs ONCE per cycle at the top of `main()`'s loop body (before `for proj in ...`), not inside `process_project`
3. Consider TTL guard (Alternative 2) as secondary defense: release slot unconditionally if `acquired_at < now - 90min`, regardless of pueue state — this handles the pueue-restart ID reuse case
4. Reuse the pueue status call: extract `_get_pueue_tasks() -> dict | None` helper used by both `is_agent_running` and the watchdog, called once per cycle and cached
5. Log watchdog releases at WARNING level with `source=watchdog` and the `acquired_at` timestamp — distinguishes from normal callback releases in ops investigation
