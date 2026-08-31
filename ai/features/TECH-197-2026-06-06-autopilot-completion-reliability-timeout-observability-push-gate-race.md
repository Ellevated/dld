# Feature: [TECH-197] Reliable autopilot session completion — claude-runner timeout observability + callback push-after-gate grace

**Priority:** P1 | **Date:** 2026-06-06

> **Lifecycle state** is tracked in `ai/lifecycle/TECH-197.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.

## Why

Heavy autopilot specs (R1, multi-layer) hit `claude-runner.py` `TIMEOUT_SECONDS=5400` and produce TWO distinct failures, both observed on awardybot 2026-06-05 (BUG-1117, BUG-1118):

1. **Zero observability on timeout.** When the 90-min `asyncio.wait_for` fires, the run dies with an *unhandled* `TimeoutError` — the final JSON result is never printed, the log file is never written, and `turns`/`cost`/per-turn activity are lost entirely. We cannot diagnose what a session did for 90 minutes. The 36-min "warm-up" before the first commit on BUG-1118 is only visible via git, not telemetry.

2. **Push-after-gate race → false `blocked`.** The callback gate `_is_done_on_develop` checks **only `origin/develop`**. When timeout interrupts autopilot *between* the local merge and `git push origin develop`, the implementation sits in **local develop but not origin**. The gate (checking origin) sees nothing → `no_merged_implementation` → false `blocked`. On BUG-1117: 6 impl commits (322 LOC in Allowed Files) merged to local develop by 16:50Z; gate checked origin at 17:11:40Z → blocked; impl reached origin only at 17:11:53Z via callback's own `lifecycle._push_best_effort` — 13s *after* the gate. The gate logic is correct (`_subject_implements` works, `_is_done_on_develop` returns True now), it is a pure timing race.

Cost of doing nothing: every heavy spec that times out burns ~$22 of completed work into a false `blocked`, requires manual operator `force-done`, and leaves no telemetry to find the real bottleneck.

## Context

- `claude-runner.py` runs the Claude Agent SDK `query()` loop. Result metrics (turns/cost/model_usage) are captured **only** from `ResultMessage`; the SDK does not emit partial cost in intermediate messages (verified: research-patterns.md, research-codebase.md).
- Timeout structure (verified, research-external.md + direct read): `main()` wraps `asyncio.wait_for(run_task(...), timeout=TIMEOUT_SECONDS)` at line 382. On timeout, `wait_for` injects `CancelledError` into the `async for` at line 204. The inner `except asyncio.TimeoutError` (line 260) does **not** catch `CancelledError` (different class hierarchy) → propagates → `run_task` aborts before `log_file.write_text` (349) and `return log_data` (362) → `wait_for` re-raises as `TimeoutError` in `main()` → unhandled → process crashes, no JSON, no log.
- Callback gate is the **single status writer** (ADR-023/025), **fail-closed by design**: ambiguity → `blocked`, never `done`. Any fix that risks a false `done` (spec marked done while code is NOT in origin/develop) is R0 and unacceptable — see Approaches / Devil findings.
- The `finishing.md` flow already pushes develop (step 8, line 49) *before* emitting `task_status` in the final JSON. So push-before-signal exists for the *normal* path; the gap is the *timeout-interrupted* path where push never runs.

---

## Scope

**In scope:**
- claude-runner: graceful timeout handling (catch the real cancellation), write log + JSON with partial metrics on timeout, per-turn heartbeat file.
- callback: push local develop to origin *before* the gate (flush a timeout-interrupted merge) + short fetch/grace-retry loop for network race, with demote-once accounting.
- autopilot skill: tighten push-before-signal — emit `needs_review` (not `complete`) if the develop push fails.
- Regression tests for all of the above.

**Out of scope:**
- Spec granularity (splitting heavy R1 specs into <60-min phases) — separate concern, tracked elsewhere.
- Raising `TIMEOUT_SECONDS` — palliative, not addressed here.
- Unifying `gate_logic.find_implementation_commit` (shadow daemon) with `callback._is_done_on_develop` — follow-up (noted in Reflect).
- Variant "gate checks local develop directly" — **rejected** (R0 false-done, see Approaches).
- claude-runner pushing the spec branch on timeout (Variant D) — runner does not know the per-spec worktree/branch; rejected (see Approaches).

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- `claude-runner.py` `run_task` / `main` — invoked by `run-agent.sh:47` (provider=claude). No Python importers (entry-point script). ✓
- `callback.verify_status_sync` — single caller `callback.py` main dispatch (line ~1405); tests in `scripts/vps/tests/test_callback.py` (6 call sites). ✓
- `callback._is_done_on_develop` — called only by `verify_status_sync`. ✓
- autopilot `finishing.md` / `autopilot-git.md` — consumed by autopilot SDK session (skill prompt), mirrored in `template/.claude/`. ✓

### Step 2: DOWN — what depends on?
- claude-runner → `claude_agent_sdk.query`, `asyncio`, `db.log_sdk_post_result_error` (lazy). Adds: `asyncio.timeout` (3.11+; runner venv is py3.12 ✓), atomic file write for heartbeat.
- callback → `lifecycle._push_best_effort` pattern (reuse for push-local), `_fetch_develop`, `db.count_demotes_since`/`record_decision` (circuit breaker — demote-once interaction).

### Step 3: BY TERM
- `asyncio.wait_for` → 1 hit (claude-runner.py:382). Replaced by `asyncio.timeout` context.
- `except asyncio.TimeoutError` → claude-runner.py:260 (unreachable, replaced).
- `_is_done_on_develop` → callback.py:736 (def), :1109 (call). No other refs.

| File | Line | Status | Action |
|------|------|--------|--------|
| scripts/vps/claude-runner.py | 260 | unreachable except | replace with reachable timeout catch |
| scripts/vps/claude-runner.py | 382 | wait_for | move timeout inside run_task via `asyncio.timeout` |
| scripts/vps/callback.py | 1098-1118 | gate decision | add push-local + grace-retry before blocked |
| scripts/vps/callback.py | 1147-1154 | demote accounting | demote-once across retries |
| .claude/skills/autopilot/finishing.md | 25-49 | signal/push order | needs_review on push-develop failure |

### Step 4: CHECKLIST
- [x] `tests/**` — `scripts/vps/tests/test_callback.py` (extend), new `test_claude_runner_timeout.py`
- [x] `db/migrations/**` — none (no schema change; heartbeat is a file, not a table)
- [x] `ai/glossary/**` — n/a (not money-related)

### Verification
- [x] All found files in Allowed Files
- [x] No old-term leftovers (replacing `wait_for` at the single callsite)

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/claude-runner.py` — Task 1: asyncio.timeout context + reachable timeout catch + partial log/JSON + heartbeat (modify)
- `scripts/vps/callback.py` — Task 2: push-local-before-gate + grace-retry + demote-once (modify)
- `.claude/skills/autopilot/finishing.md` — Task 3: needs_review on develop-push failure (modify)
- `.claude/skills/autopilot/autopilot-git.md` — Task 3: push retry → needs_review guard (modify)
- `template/.claude/skills/autopilot/finishing.md` — Task 3: template sync (modify)
- `template/.claude/skills/autopilot/autopilot-git.md` — Task 3: template sync (modify)
- `scripts/vps/tests/test_callback.py` — Task 4: gate race + demote-once regression (modify)
- `scripts/vps/tests/test_claude_runner_timeout.py` — Task 4: timeout-path observability (NEW)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (scripts/vps/) — no ai/blueprint/system-blueprint/ for this infra layer.
**Cross-cutting:** Errors (explicit exit codes), no Money/Auth.
**Data model:** none (heartbeat is a transient file; no schema change).

---

## Historical Risks

<!-- lessons-binding v1 -->

`ai/lessons/` exists but contains only `.gitkeep` (empty bank — verified research-codebase.md). No formalized lessons for this domain.

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

Informal precedent (memory + audit log): BUG-1101, FTR-1102, FTR-1105 (timeout/hang with work stranded in branch), BUG-188 (post-result exception must not override exit_code=0 — Task 1 must preserve this guard at claude-runner.py:290-299).

---

## Approaches

### Approach 1: Observability-only (claude-runner timeout fix + heartbeat)
**Source:** research-external.md (asyncio CancelledError pattern), research-patterns.md (1A heartbeat)
**Summary:** Fix only Layer 1 — graceful timeout, partial log, heartbeat. Leave the gate race.
**Pros:** Smallest, R2, no callback risk. Unblocks diagnosis.
**Cons:** Does NOT stop false `blocked` — heavy specs keep burning into manual force-done.

### Approach 2: Gate fetch-retry only (Variant B)
**Source:** research-external.md (retry+fetch), research-patterns.md (2B), research-devil.md (Proceed-with-guards)
**Summary:** callback sleeps+fetches+retries the gate ×3 before blocking.
**Pros:** Deterministic, fail-closed preserved.
**Cons:** Does NOT fix BUG-1117 — at timeout the impl is in *local* develop, never pushed to origin; there is nothing to fetch. Only covers the network-race sub-case.

### Approach 3 (SELECTED): Combined — graceful timeout + heartbeat (L1) + push-local-before-gate + grace-retry + demote-once (L2) + push-before-signal guard (autopilot)
**Source:** synthesis of all 4 scouts + reflog evidence (research-codebase.md, research-devil.md SA-4)
**Summary:** Each sub-case has a matched fix:
- Normal completion → autopilot already pushes develop before signal (Task 3 hardens: `needs_review` if push fails).
- Timeout after local merge (BUG-1117) → callback pushes local develop to origin *before* the gate (Task 2), so the gate sees the merged impl.
- Network/push lag race → gate fetch+grace-retry ×3 (Task 2).
- Not-merged (BUG-1118) → nothing in local develop to push → gate stays `blocked` (correct).
- Any timeout → log+JSON+heartbeat written with partial metrics (Task 1).
**Pros:** Covers all observed sub-cases; **fail-closed invariant untouched** (every gate path still requires the commit to be in origin/develop — push-local that fails → blocked, exactly as today). Demote-once prevents circuit-breaker false-trip.
**Cons:** Touches callback (R1, critical writer); 4 files of skill+test. Mitigated by tests + fail-closed preservation.

### Selected: 3
**Rationale:** Approaches 1 and 2 each fix only one observed failure. The reflog evidence proves BUG-1117's impl never reached origin until callback's own push — so only push-local-before-gate closes it, and it does so *without* weakening the fail-closed gate (push failure still yields `blocked`). Variant C (gate reads local develop) is rejected: it would let the gate return `done` while code is absent from origin (R0 false-done; code lives only on the VPS and vanishes on `git reset --hard origin/develop`).

---

## Design

### Layer 1 — claude-runner graceful timeout + heartbeat

**Timeout restructure:**
- Remove `asyncio.wait_for(...)` wrapper in `main()` (line 382). Instead wrap the `async for message in query(...)` loop in `run_task` with `async with asyncio.timeout(TIMEOUT_SECONDS):`.
- On timeout, `asyncio.timeout` raises `TimeoutError` **inside** `run_task`, where `turns`/`cost_usd`/`last_assistant_text`/`usage_metrics` are in scope. Catch it (replace the unreachable `except asyncio.TimeoutError` at 260 with a reachable one), set `exit_code=124`, `result_text=f"Timeout after {TIMEOUT_SECONDS}s (partial: {turns} turns, ${cost_usd:.4f})"`.
- The existing log-build + `log_file.write_text` (324-349) + `return log_data` (362) then run normally → `main()` prints JSON and exits 124.
- **Preserve BUG-188 guard** (290-299): post-ResultMessage exception must not override `exit_code=0`. Do not regress.

**Heartbeat:**
- On each `AssistantMessage` in the loop (212-218), increment a `turn` counter and atomically write `logs/{project}-{ts}.heartbeat.json`: `{"turn": N, "elapsed_s": int, "last_tool": str|null, "started_at": iso, "model": MODEL}`. Atomic = write tmp + `os.replace`.
- `cost_usd` is NOT available mid-run (SDK gives it only in `ResultMessage`) — heartbeat omits cost; final log has it. Document this in a comment.
- Best-effort: heartbeat write failure must never crash the runner (bare except, ADR-004 style).

### Layer 2 — callback push-local-before-gate + grace-retry

In `verify_status_sync`, between `_get_started_at`/`_commit_stats` and the gate decision (around 1098-1118):
- **Push-local (timeout recovery):** if the pueue result is non-Success (failed/timeout) — best-effort `git -C <project> push origin develop` to flush any merge the autopilot completed locally before being killed. Reuse the `lifecycle._push_best_effort` pattern (timeout=30, never raises). Failure → continue (gate will fail-closed).
- **Grace-retry (network race):** wrap `_is_done_on_develop` in a loop: if False, `sleep(5)` → `_fetch_develop` → re-check, up to 3 attempts (≤15s total). Covers the observed 13s race with margin.
- **Demote-once:** the `blocked` demote accounting (1147-1154) fires only **once**, after the final failed attempt — NOT per retry. Otherwise 3 retries = 3 demotes → circuit breaker (TECH-169, threshold 3/10min) trips from a single spec. (Devil SA-4.)
- Guard: grace-retry only runs when it can help — i.e. push-local was attempted or result=Success. For result=Failed with autopilot-signaled `blocked`/`needs_review`, honor the signal (no retry).

### Layer 3 — autopilot push-before-signal guard

In `finishing.md` step 8 + `autopilot-git.md` push section: after `git push origin develop`, if the push fails (after the existing retry), emit `"task_status": "needs_review"` in the final JSON instead of `"complete"`. This preserves the signal that work exists but did not reach origin (Devil A-guard). Mirror to `template/.claude/`.

### Database Changes
None. Heartbeat is a transient file; no schema migration.

---

## Implementation Plan

### Research Sources
- [Python asyncio timeout/cancellation](https://docs.python.org/3/library/asyncio-task.html) — `asyncio.timeout` context manager (3.11+), CancelledError vs TimeoutError semantics
- [Python bug 40672](https://bugs.python.org/issue40672) — wait_for injects CancelledError, not TimeoutError
- [akuity/kargo #3071](https://github.com/akuity/kargo/issues/3071) — git gate push-before-check race; retry+fetch resolution
- [Zuul gating](https://zuul-ci.org/docs/zuul/latest/gating.html) — fail-closed CI gate with speculative re-check

### Task 1: claude-runner graceful timeout + heartbeat
**Type:** code
**Files:**
  - modify: `scripts/vps/claude-runner.py`
**Pattern:** [Python asyncio timeout](https://docs.python.org/3/library/asyncio-task.html)
**Acceptance:** Timeout path writes log_file + prints JSON with partial `turns`/`cost`/`result_preview` and `exit_code=124`; heartbeat file updated per turn; BUG-188 guard intact.

### Task 2: callback push-local-before-gate + grace-retry + demote-once
**Type:** code
**Files:**
  - modify: `scripts/vps/callback.py`
**Pattern:** [akuity/kargo #3071](https://github.com/akuity/kargo/issues/3071)
**Acceptance:** On non-Success with impl merged in local develop, callback pushes origin then gate→`done`; network-race resolved within grace window; a single spec produces exactly ONE demote regardless of retries; fail-closed preserved (push fail → blocked).

### Task 3: autopilot push-before-signal guard
**Type:** code (skill prompt)
**Files:**
  - modify: `.claude/skills/autopilot/finishing.md`
  - modify: `.claude/skills/autopilot/autopilot-git.md`
  - modify: `template/.claude/skills/autopilot/finishing.md`
  - modify: `template/.claude/skills/autopilot/autopilot-git.md`
**Pattern:** Devil A-guard (research-devil.md)
**Acceptance:** develop-push failure → `needs_review` emitted (not `complete`); root and template copies identical.

### Task 4: regression tests
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_callback.py`
  - create: `scripts/vps/tests/test_claude_runner_timeout.py`
**Pattern:** ADR-013 (real git repos via tmp_path, no mocks for integration)
**Acceptance:** All EC rows below pass.

### Execution Order
1 → 4(timeout part) ; 2 → 4(callback part) ; 3 (independent) — recommend 1, 2, 3, then 4.

---

## Flow Coverage Matrix

| # | Flow Step | Covered by Task | Status |
|---|-----------|-----------------|--------|
| 1 | Session times out → metrics preserved | Task 1 | ✓ |
| 2 | Per-turn progress visible | Task 1 (heartbeat) | ✓ |
| 3 | Timeout after local merge → gate sees impl | Task 2 (push-local) | ✓ |
| 4 | Network push-lag race → gate retries | Task 2 (grace-retry) | ✓ |
| 5 | Retries don't trip circuit breaker | Task 2 (demote-once) | ✓ |
| 6 | Normal push fails → signal preserved | Task 3 (needs_review) | ✓ |
| 7 | Not-merged spec stays blocked | Task 2 (fail-closed, no local impl) | ✓ existing+preserved |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Timeout writes telemetry | run_task hits asyncio.timeout with N turns accumulated | log_file written, JSON printed, exit_code=124, result_preview contains "partial" + turn count | deterministic | external scout | P0 |
| EC-2 | BUG-188 guard intact | ResultMessage(is_error=False) then SDK raises | exit_code stays 0 | deterministic | BUG-188 | P0 |
| EC-3 | Heartbeat per turn | 3 AssistantMessages | heartbeat.json exists, turn==3, has last_tool/elapsed_s | deterministic | patterns scout | P1 |
| EC-4 | Demote-once across retries | gate False ×3 then blocked | exactly 1 record_decision(demoted=True) | deterministic | devil SA-4 | P0 |
| EC-5 | Variant-C never introduced | grep callback gate | no path returns done from local-only develop (origin/develop only) | deterministic | devil R0 | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-6 | tmp git repo: impl merged to local develop, NOT pushed to origin remote; spec Allowed Files match | callback verify_status_sync (non-Success) | callback pushes origin, gate→done | integration | reflog/BUG-1117 | P0 |
| EC-7 | tmp git repo: impl on feature branch only, develop clean | callback verify_status_sync | stays blocked (no false done) | integration | BUG-1118 | P0 |
| EC-8 | tmp git repo: impl pushed to origin 1 fetch-cycle late | callback gate grace-retry | resolves to done on 2nd fetch | integration | network race | P1 |
| EC-9 | tmp git repo: push origin fails (no remote) | callback push-local + gate | stays blocked, fail-closed, exactly 1 demote | integration | devil fail-closed | P0 |

### Coverage Summary
- Deterministic: 5 | Integration: 4 | LLM-Judge: 0 | Total: 9 (min 3 ✓)

### TDD Order
1. EC-1 (timeout telemetry) → FAIL → implement Task 1 → PASS
2. EC-6/EC-7/EC-9 (push-local + fail-closed) → FAIL → implement Task 2 → PASS
3. EC-4 (demote-once) → FAIL → refine Task 2 → PASS
4. Remaining by priority

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | runner imports + compiles | `python3 -m py_compile scripts/vps/claude-runner.py` | exit 0 | 30s |
| AV-S2 | callback imports | `DB_PATH=/tmp/t.db python3 -c "import sys;sys.path.insert(0,'scripts/vps');import callback"` | exit 0 | 30s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | full test suite | venv | `cd scripts/vps && python3 -m pytest tests/test_callback.py tests/test_claude_runner_timeout.py -q` | all pass |

### Verify Command

```bash
# Smoke
python3 -m py_compile scripts/vps/claude-runner.py
DB_PATH=/tmp/tech197.db python3 -c "import sys;sys.path.insert(0,'scripts/vps');import callback"
# Functional
cd scripts/vps && DB_PATH=/tmp/tech197.db python3 -m pytest tests/test_callback.py tests/test_claude_runner_timeout.py -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

**Note:** infra change on VPS orchestrator — no HTTP deploy. Effect observable on next heavy autopilot timeout (heartbeat file + non-empty log + correct done/blocked).

---

## Definition of Done

### Functional
- [ ] Timeout produces log + JSON + heartbeat with partial metrics (exit 124)
- [ ] callback push-local-before-gate closes BUG-1117 class; BUG-1118 class stays blocked
- [ ] demote-once: single spec never trips circuit breaker via retries
- [ ] autopilot emits needs_review on develop-push failure (root + template)

### Tests
- [ ] All EC-1..EC-9 pass
- [ ] Coverage not decreased

### Technical
- [ ] `./test fast` / pytest passes
- [ ] No regressions in existing test_callback.py (6 call sites)
- [ ] fail-closed invariant verified (EC-5, EC-9)
- [ ] BUG-188 guard intact (EC-2)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
