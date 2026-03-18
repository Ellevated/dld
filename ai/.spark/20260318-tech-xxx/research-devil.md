# Devil's Advocate — Fix 3 DLD Cycle Breaks + Smoke Test

## Why NOT Do This?

### Argument 1: QA "break" is already half-fixed — wrong layer was blamed
**Concern:** The inbox description says "qa-loop.sh запускается без передачи spec-пути". But reading the code: `pueue-callback.sh` (line 361) no longer calls `qa-loop.sh` at all. QA is dispatched via `run-agent.sh` with prompt `/qa Проверь изменения после ${TASK_LABEL}`. The agent uses `claude-runner.py` with `permission_mode="bypassPermissions"` — yet `20260317-162026-TECH-153.md` shows `permission_denials` for Glob. That means the SDK's `bypassPermissions` was NOT active for that session, or the QA session was launched differently (possibly via `qa-loop.sh` directly, not through the callback path). Fixing `qa-loop.sh` spec lookup might be the wrong fix if the actual production path is the callback → run-agent.sh flow.
**Evidence:** `pueue-callback.sh:361` dispatches QA via `run-agent.sh`, not `qa-loop.sh`. `claude-runner.py:95` sets `permission_mode="bypassPermissions"`. The TECH-153 QA report at `ai/qa/20260317-162026-TECH-153.md` shows actual `permission_denials` — which contradicts `bypassPermissions`.
**Impact:** High
**Counter:** Determine which code path actually ran. Check if `qa-loop.sh` is still invoked anywhere (it is not, per grep). If the permission denials came from a different Claude Code invocation path, the fix target changes.

### Argument 2: Artifact scan regex is "wrong" but its logic is actually correct for its inputs
**Concern:** The proposal says artifact scan regex doesn't match `2026-03-17-tech-151.md`. But `openclaw-artifact-scan.py:79` does not use a regex — it uses `p.name[:4].isdigit()`. The filter passes any filename whose first 4 chars are digits. `2026-03-17-tech-151.md` → first char `2`, `0`, `2`, `6` — all digits. This file WOULD be picked up. But `SKILL-v1-skill-writer.md` would NOT. The real issue may be that the event's `artifact_rel` field points to the wrong file (e.g. `ai/qa/SKILL-v1-skill-writer.md` as seen in `processed-events/20260317-161817-qa.json`), not the artifact scan filter. Fixing a regex that doesn't exist wastes effort and risks introducing an actual regression.
**Evidence:** `openclaw-artifact-scan.py:79` — `[p for p in qa_dir.glob("*.md") if p.name[:4].isdigit()]`. `ai/qa/2026-03-17-tech-151.md` passes this check. `ai/qa/20260317-162026-TECH-153.md` also passes. The real broken artifact_rel comes from `pueue-callback.sh:303`: `find ... -name "*.md" | sort | tail -1` which picks the LAST alphabetically sorted file — which may be a legacy/wrong file.
**Impact:** High
**Counter:** The actual bug is in `pueue-callback.sh:303` — the `find | sort | tail -1` picks whichever `.md` is last alphabetically, not the one written by the current QA run. Fix that, not the scan filter.

### Argument 3: topic_id backfill is a data-write with no rollback path
**Concern:** Backfilling topic_id for 5 projects requires knowing the correct Telegram thread IDs. If a wrong topic_id is written (off by one, swapped between projects), notifications silently route to the wrong thread for all future tasks. The DB has a unique index `idx_project_state_chat_topic_unique` on `(chat_id, topic_id)` — inserting an existing topic_id for the same chat_id will fail with a constraint violation that could corrupt state. There is no soft delete or undo in the schema.
**Evidence:** `schema.sql:22` — `CREATE UNIQUE INDEX ... ON project_state(chat_id, topic_id) WHERE topic_id IS NOT NULL`. `db.py:33-46` — runtime migration adds this index. `projects.json` shows 5 projects with `topic_id` absent. No migration tooling exists.
**Impact:** High
**Counter:** The fix must be done as a structured migration: verify topic IDs in Telegram first, then update `projects.json` (source of truth), then let `seed_projects_from_json` COALESCE update propagate. Never direct SQL UPDATE. Also: `seed_projects_from_json` uses `COALESCE(excluded.topic_id, project_state.topic_id)` — so if `projects.json` already has topic_id, reseed will propagate it. The path is: add topic_ids to `projects.json`, restart orchestrator cycle.

### Argument 4: Smoke test for full pipeline is high-maintenance and brittle
**Concern:** A smoke test that goes inbox → spark → backlog → autopilot → callback → qa → reflect touches 7 distinct components, requires live pueue daemon, live Claude API, and real DB state. It cannot run in CI (costs money, takes 30+ min, requires active systemd services). If the test itself has a bug it could leave phase stuck at `qa_running` in the real DB. It may test implementation details rather than observable outputs.
**Evidence:** `qa-loop.sh:32` updates phase to `qa_running` with direct `db_exec.sh` SQL — a stuck test leaves a real DB in bad state. The existing tests (`tests/test_db.py`, `tests/test_notify.py`) are all unit tests with isolated SQLite. No integration harness exists. Building one from scratch adds ~200 LOC of test infrastructure.
**Impact:** Medium
**Counter:** Scope the smoke test to a dry-run mode: mock the LLM call, use a pre-written fixture spec, assert phase transitions in isolated DB. A full live test belongs in a separate "staging" environment, not in the test suite.

---

## Simpler Alternatives

### Alternative 1: Fix the actual root cause — pueue-callback.sh artifact_rel selection
**Instead of:** Adding new QA spec-path passing logic and fixing artifact scan regex
**Do this:** Fix `pueue-callback.sh:303` — replace `find | sort | tail -1` (picks last alphabetically) with `find | sort -r | head -1` (picks most recent by timestamp prefix), or better: capture the `REPORT_FILE` path that `qa-loop.sh` writes and pass it explicitly via DB or event JSON.
**Pros:** 2-line fix. No new moving parts. Directly addresses root cause identified in codebase.
**Cons:** Still doesn't help if QA runs via `run-agent.sh` path (callback-dispatched QA) where the skill itself writes the file and the callback has to locate it by convention.
**Viability:** High — this is a targeted fix, not architecture

### Alternative 2: topic_id via projects.json update only (no DB migration code)
**Instead of:** Writing a migration script or a new DB function
**Do this:** Add the 5 missing `topic_id` values directly to `projects.json`, which is already the declared SSOT. `seed_projects_from_json` with `COALESCE` handles the rest on next orchestrator cycle. Zero new code.
**Pros:** Uses existing idempotent infrastructure. One config change.
**Cons:** Requires knowing the correct topic IDs. No automated validation that topic IDs are reachable.
**Viability:** High — this is the canonical path already built

### Alternative 3: Narrow smoke test — phase-transition contract test only
**Instead of:** Full end-to-end pipeline smoke test with live Claude API
**Do this:** Write a deterministic test that verifies the state machine: given a project in `idle` with a queued spec, simulate `scan_backlog` → assert DB transitions to correct phases. Use `subprocess` to call the actual bash scripts with a temp project dir containing a fixture spec and fixture backlog.
**Pros:** 100% deterministic. No LLM cost. Runs in CI. Validates the most-broken part (phase transitions) without needing live agents.
**Cons:** Does not catch QA agent behavior issues — only pipeline plumbing.
**Viability:** High

**Verdict:** All three breaks have simpler targeted fixes. The QA break needs root-cause re-investigation first (which path dispatched it: qa-loop.sh or callback→run-agent?). Artifact scan filter is not broken in the way described. topic_id is a config-only fix. Only the smoke test requires new code, and it should be scoped to phase transitions only.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | QA launched via callback path — spec not found | `pueue-callback.sh` dispatches `/qa Проверь изменения после TECH-999` where TECH-999 spec doesn't exist | QA agent returns non-zero exit; phase → `qa_failed`; NOT false-pass with exit 0 | High | P0 | deterministic |
| DA-2 | QA launched via qa-loop.sh — spec not found | `qa-loop.sh dld /path/to/dld TECH-999` | exit 1, phase set to `idle` (not stuck at `qa_running`), notify "spec not found" | High | P0 | deterministic |
| DA-3 | artifact_rel points to wrong QA file | callback writes event with `artifact_rel = ai/qa/SKILL-v1-skill-writer.md` (old file), new QA report exists | artifact_scan reports correct new file, not old one | High | P0 | deterministic |
| DA-4 | topic_id backfill via projects.json reseed | projects.json updated with valid topic_id, orchestrator cycle runs | `project_state.topic_id` updated in DB, notifications route to correct thread | High | P0 | deterministic |
| DA-5 | topic_id collision — two projects same chat+topic | projects.json: project A and project B both have `topic_id=7, chat_id=X` | Second upsert raises constraint violation, not silently overwritten | High | P0 | deterministic |
| DA-6 | QA false-pass — phase stuck at qa_pending | autopilot completes, callback sets phase `qa_pending`, QA dispatch fails silently | orchestrator's `dispatch_qa` invariant check detects qa_pending + no current_task, resets to idle | Med | P1 | deterministic |
| DA-7 | artifact scan with mixed filename formats | `ai/qa/` contains `2026-03-17-tech-151.md`, `20260317-162026-TECH-153.md`, `SKILL-v1-skill-writer.md` | scan returns first two, excludes SKILL file | Med | P1 | deterministic |
| DA-8 | Smoke test — phase stuck after QA crash | qa-loop.sh crashes mid-run (power cut simulation: SIGKILL) | phase stuck at `qa_running`; recovery mechanism or monitoring detects this | Med | P1 | deterministic |
| DA-9 | QA exit 0 despite permission_denials | claude-runner.py runs QA with `bypassPermissions` but SDK version doesn't support it | permission denials in JSON but ResultMessage.is_error = false → exit_code = 0 | High | P0 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | pueue-callback.sh artifact_rel selection | pueue-callback.sh:303 | After fix, artifact_rel must point to QA report written by CURRENT run, not oldest/last-alpha file | P0 |
| SA-2 | seed_projects_from_json COALESCE behavior | db.py:234-235 | After adding topic_id to projects.json, reseed must NOT overwrite topic_id for `dld` project (already has topic_id=7) | P0 |
| SA-3 | openclaw-artifact-scan.py qa_candidates filter | openclaw-artifact-scan.py:79 | `name[:4].isdigit()` filter — verify both `2026-` and `20260317-` format names pass, verify `SKILL-` fails | P1 |
| SA-4 | dispatch_qa invariant in orchestrator.sh | orchestrator.sh:353-362 | qa_pending + current_task=NULL → reset to idle must fire correctly after stuck-QA scenario | P1 |
| SA-5 | notify.py fail-closed behavior | notify.py:95-98 | After topic_id backfill, projects with topic_id=1 (General) must still be rejected | P1 |

### Assertion Summary
- Deterministic: 9 | Side-effect: 5 | Total: 14

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| pueue-callback.sh artifact scan | pueue-callback.sh:303 | `find ... sort tail -1` picks last-alphabetical .md, not latest QA run | Replace with timestamp-based selection or write artifact path into event at creation time |
| qa-loop.sh spec search | qa-loop.sh:38 | `find -name "${SPEC_ID}*"` won't find specs in subdirs like `ai/features/BUG-083/BUG-083.md` — only top-level matches | Add `-maxdepth 2` or use `find -name` with recursive fallback; currently `head -1` silently returns empty for subdirs |
| QA dispatch via callback | pueue-callback.sh:362 | `/qa Проверь изменения после ${TASK_LABEL}` gives QA agent no path hint — the skill must locate the spec itself via Glob, which requires correct cwd and bypassPermissions | Confirm `claude-runner.py` `bypassPermissions` is active in production; verify SDK version supports it |
| notify.py send_to_project | notify.py:95-98 | Fail-closed: 5 of 6 projects have no topic_id, so ALL notifications for those projects are silently dropped | Add topic_ids to projects.json |
| openclaw pending-events | pueue-callback.sh:296-318 | event JSON `artifact_rel` for QA currently set to whatever `.md` file is last-sorted in `ai/qa/` — often a legacy report | Fix at write time: use the report filename that qa-loop/agent writes, or parse from agent output |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| claude-runner.py `bypassPermissions` | SDK API | High — permission_denials seen in production despite claim of bypass | Verify SDK version; add SDK version pin to requirements.txt |
| db.py `seed_projects_from_json` COALESCE | Data | Med — if topic_id is added to projects.json for all projects, and existing DB has a different topic_id for `dld`, COALESCE keeps DB value (old wins) | Document explicitly: first reseed after adding topic_id will NOT update projects with existing topic_id. Must UPDATE directly or drop+reseed. |
| orchestrator.sh `dispatch_qa` | Logic | Med — currently only resets qa_pending+no-task, but if phase=qa_running and agent crashes, no recovery | Add qa_running timeout check (e.g. running >45min → reset to idle) |
| ai/qa/ filename format contract | Convention | Med — no authoritative spec for what qa-loop.sh should name files; multiple formats already exist in production | Pick one format, document it, migrate old files or grandfather them |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Which code path actually ran the failing QA for TECH-153 — `qa-loop.sh` directly (old path) or `pueue-callback.sh` → `run-agent.sh` → `claude-runner.py` (new path)?
   **Why it matters:** The fix target is completely different. `qa-loop.sh` fix addresses the `find` command. `claude-runner.py` path fix addresses SDK permission mode. The `permission_denials` in TECH-153 output suggest the latter, but `qa-loop.sh` shows `exit 1` on spec-not-found (not exit 0). The inbox report says "exit 0 false pass" — which only makes sense if the agent ran and returned is_error=false despite permission failures.

2. **Question:** Is `qa-loop.sh` still used in production at all, or is it dead code?
   **Why it matters:** `pueue-callback.sh` now dispatches QA via `run-agent.sh`. If `qa-loop.sh` is unreachable from any live code path, fixing its `find` command has zero impact. The `orchestrator.sh` references `qa-loop.sh` in comments but not in `dispatch_qa()` which only checks invariants.

3. **Question:** What are the actual Telegram topic IDs for the 5 projects missing them (awardybot, dowry, dowry-mc, nexus, plpilot)?
   **Why it matters:** Wrong topic_id = misdirected notifications for all future tasks. The unique index on `(chat_id, topic_id)` means writing a wrong value that collides with `dld` (topic_id=7) will fail silently or error.

4. **Question:** Does `seed_projects_from_json` `COALESCE` propagate a newly-added topic_id to the DB, or is it blocked by "keep existing value" semantics?
   **Why it matters:** `COALESCE(excluded.topic_id, project_state.topic_id)` — if `project_state.topic_id` is currently NULL and `excluded.topic_id` has a value, COALESCE returns the new value. So it WILL propagate for NULL → value. But if topic_id is already set (like `dld`), reseed with a different value will be IGNORED. This is the correct behavior, but the team must understand it.

5. **Question:** Why does `20260317-162026-TECH-153.md` show `permission_denials` if `claude-runner.py` uses `bypassPermissions`?
   **Why it matters:** If the SDK's `bypassPermissions` mode is silently broken or only applies to certain tool types, every QA and autopilot run is operating with unexpectedly restricted permissions. This is a systemic risk, not a qa-loop.sh bug.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The three reported breaks are real but two of them are misdiagnosed at the code level. Break 1 (QA can't find spec) needs root cause investigation — the production path goes through `claude-runner.py` with `bypassPermissions`, not `qa-loop.sh`'s `find`. The `permission_denials` in the TECH-153 report are the critical symptom. Break 2 (artifact scan format mismatch) — the scan filter `name[:4].isdigit()` already handles both `2026-` and `20260317-` formats; the real bug is in `pueue-callback.sh:303`'s artifact_rel selection. Break 3 (topic_id NULL) is a pure config fix in `projects.json` requiring no code changes. The smoke test is the only genuinely new work and must be scoped to phase-transition contract testing only, not full live pipeline.

**Conditions for success:**
1. Before coding: run `pueue log <last-qa-task-id>` on the VPS to determine whether the TECH-153 QA failure came from qa-loop.sh or from run-agent.sh path; this changes Break 1's fix entirely
2. Break 2 fix must target `pueue-callback.sh:303` artifact_rel selection, NOT the scan filter in `openclaw-artifact-scan.py` which is already correct
3. Break 3 must be fixed via `projects.json` update only (not a new DB migration function), with topic IDs verified in Telegram before writing
4. Smoke test must use an isolated temp DB and fixture files — never touch production DB state
5. Add a `qa_running` timeout guard to `orchestrator.sh` (any project stuck in `qa_running` for > N minutes → reset to idle + alert) to prevent the stuck-phase failure mode that currently has no recovery
