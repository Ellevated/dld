# Feature: [TECH-207] QA/Reflect silently skipped — completion-signal robustness in the post-autopilot dispatch gate

**Priority:** P1 | **Date:** 2026-06-28 | **Risk:** R1 (callback.py + claude-runner — orchestrator critical path, all projects)

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> **Founder-reviewed 2026-07-12, promoted to `queued`** (`lifecycle.create_initial`,
> `by=operator`) — confirmed still live via a fresh recurrence on awardybot
> BUG-1387 (2026-07-11, `task_status=''`, background-test-notification pattern).
> **Self-modification caveat:** implementation edits `callback.py` (the single
> status writer) — an unsupervised autopilot run on its own critical path is R1.
> Review the diff before merging; consider supervised execution.

## Why

Observed live on **awardybot** (2026-06-28): a string of completed autopilot specs
merged real work into `develop` but **never triggered QA or Reflect**. Among them
**BUG-1313 — a P0 production fix to a delivery-date validator cutting/hiding live
Pampers buyers** — merged with zero behavioural QA. Unit tests ran, but the
post-autopilot QA + Reflect tail was silently skipped.

This is not isolated: of the recent awardybot batch, **3 of 6** (BUG-1313, BUG-1311,
BUG-1309) skipped QA; the gap is silent because the lifecycle still closes `done`.

## Symptom

`callback.py` Step 6 (post-autopilot tail) dispatches `qa-<SPEC>` + `reflect-<SPEC>`
only under an **allowlist** gate (TECH-194 Layer E):

```
if skill == "autopilot" and status == "done":
    if task_status != "complete":
        log "skip QA+reflect dispatch: task_status=... (expected 'complete')"
    else:
        dispatch_qa(...) ; dispatch_reflect(...)
```

`task_status` is parsed by claude-runner / `callback._parse_log_file` from the
session's **final** telemetry line. When it is not exactly `"complete"`, QA is
skipped. The lifecycle is then independently closed `done` by the implementation
guard (work IS merged on develop) — which **masks** the skipped QA: the spec looks
fully finished.

### Forensic evidence (2026-06-28)

| Spec | task_status (final telemetry) | final assistant message | QA dispatched |
|------|-------------------------------|--------------------------|---------------|
| BUG-1313 | `''` | «Уведомление относится к фоновому прогону архитектурных тестов…» | ❌ |
| BUG-1311 | `''` | «Это уведомление об arch-тестах, которые я уже обработал через TaskOutput (1230 passed)…» | ❌ |
| BUG-1309 | `''` | «Эта нотификация относится к фоновому pytest-прогону, результат которого я уже забрал…» | ❌ |
| BUG-1310 | `'complete'` | (clean completion) | ✅ |
| BUG-1304 | `'complete'` | — | ✅ |
| TECH-1303 | `'complete'` | — | ✅ |

100% correlation: **QA dispatches ⟺ task_status == 'complete'.** Raw output of the
skipped sessions contains **zero** `task_status` completion tokens — the signal was
never emitted, not emitted-then-lost.

### Root cause

The autopilot launches its test suite (pytest / architectural tests) as a
**background task**. The background task's completion `<task-notification>` arrives
as the session's **last event**. The model spends its **final turn acknowledging
that notification** («это уведомление о фоновых тестах, я их уже забрал через
TaskOutput») instead of emitting the required `task_status: "complete"` JSON. The
completion signal is displaced → `task_status=''` → the allowlist gate (correctly,
per its contract) skips QA + Reflect.

The allowlist was deliberately chosen over a blocklist (TECH-194 Layer E) because
`task_status=""` from SIGKILL / missing output must NOT dispatch. The gate is
working as designed; the defect is **upstream**: the completion signal is fragile
to anything that lands a message after the work is done.

## Context

- Gate: `callback.py` Step 6, ~line 1480-1500 (`if skill == "autopilot" and
  status == "done": if task_status != "complete": skip`).
- `task_status` extraction: `callback._parse_log_file` (`:199-242`) +
  claude-runner `_extract_task_status`. Both read the **final** result/message.
- The implementation guard (Step 7, `verify_status_sync`) already independently
  proves the work merged on `origin/develop` (`_is_done_on_develop` / gate_logic
  `find_implementation_commit`) — a **stronger** completion signal than
  `status=="done"`, computed one step later than the QA gate.
- Effect is cross-project: any autopilot session (any project in `projects.json`)
  that backgrounds its tests and receives a trailing notification skips QA.
- Manual remediation used 2026-06-28 (backfill QA for 1308/1309/1311/1313):
  `DB_PATH=<real orchestrator.db> python3 -c "import callback;
  callback.dispatch_qa('<proj>','<path>','<SPEC>','claude');
  callback.dispatch_reflect(...)"`.

---

## Scope

**In scope:**
- Make QA + Reflect dispatch robust to a missing/displaced `task_status` signal
  **when the work is independently confirmed merged on develop**.
- Preserve the TECH-194 allowlist property: do NOT dispatch QA on genuinely
  incomplete/aborted runs (SIGKILL, no merge, blocked).

**Out of scope:**
- Lifecycle SoT / status-writing model (unchanged; callback stays the single writer).
- The `./test ci` parity gate (TECH-206 — separate).
- Retroactive QA of historically-skipped specs (one-shot operator backfill, done
  manually 2026-06-28 for the recent batch).

---

## Impact Tree Analysis

### Step 1: UP — who depends on the dispatch gate?
- Every project's post-autopilot tail (QA + Reflect coverage). Loosening the gate
  affects QA dispatch frequency across all projects.

### Step 2: DOWN — what does the gate depend on?
- `extract_agent_output` / `_parse_log_file` (task_status), `dispatch_qa`,
  `dispatch_reflect`, and (for Approach A) the implementation-guard merge check
  (`_is_done_on_develop` / `gate_logic.find_implementation_commit`).

### Step 3: BY TERM
- `grep -n "task_status" scripts/vps/callback.py scripts/vps/claude-runner.py`
- `grep -n "dispatch_qa\|dispatch_reflect" scripts/vps/callback.py`

### Step 4: CHECKLIST
- [ ] `scripts/vps/tests/` — add regression for the merged-but-no-complete case.
- [ ] No lifecycle/status write changes (Rule 7 / ADR-025 untouched).
- [ ] Circuit-breaker (TECH-169) untouched.

### Step 5: DUAL SYSTEM
- Two "completion" signals now exist: explicit `task_status=="complete"` and the
  guard's merge-on-develop. Approach A unifies them; keep them consistent so QA
  doesn't double-dispatch (the `is_already_queued` dedup already guards this).

### Verification
- [ ] A done autopilot session whose work merged but `task_status==''` → QA + Reflect
      ARE dispatched.
- [ ] A done session with NO merge and `task_status==''` → QA still SKIPPED.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/callback.py` — Step 6 gate: also dispatch when guard confirms merge-on-develop despite `task_status != "complete"` (modify)
- `scripts/vps/tests/test_callback_dispatch.py` — regression tests for merged-but-no-complete-signal + no-merge-no-dispatch (create or modify)

**Optional (only if Approach C hardening is taken — flag in review first):**
- `scripts/vps/claude-runner.py` — scan ALL session messages for the last `task_status` token instead of only the final message (modify)
- `.claude/skills/autopilot/finishing.md` + `template/.claude/skills/autopilot/finishing.md` — collect/await background tasks BEFORE emitting the completion signal (modify, template-sync)

**FORBIDDEN:** All other files — especially `lifecycle.py`, `orchestrator.py`,
`gate-daemon.py`, and any `ai/lifecycle/*.yaml`. The single-writer status model
must not change.

---

## Approaches

### Approach A: Merge-confirmed completion fallback in callback Step 6 (SELECTED)
**Summary:** In Step 6, when `skill=="autopilot" and status=="done"` but
`task_status != "complete"`, run the same merge check the guard uses
(`_is_done_on_develop` / `gate_logic.find_implementation_commit` against the spec's
Allowed Files on `origin/develop`). If a real implementation commit is confirmed
merged → dispatch QA + Reflect anyway (log `QA_DISPATCH_MERGE_FALLBACK`). Otherwise
keep skipping.
**Pros:** Closes the hole for ALL missing-signal causes (background-notification
hijack, post-result truncation, SDK quirks) with one change; reuses an existing,
trusted check; preserves the allowlist intent (merge-on-develop is a *stronger*
completion proof than `status=="done"`, so SIGKILL/no-work cases still skip);
single-file change, fully unit-testable.
**Cons:** Couples Step 6 to the guard logic (a `git` call earlier in the callback —
already done in Step 7, so reorder/share the result); marginally more git work per
completion.

### Approach B: Make the autopilot emit `task_status: complete` robustly
**Summary:** Autopilot collects/awaits all background tasks before the completion
step and re-emits the JSON if a notification lands after.
**Cons:** Best-effort — you cannot guarantee the model's final turn; trailing
notifications are not fully controllable. Good as complementary hardening, weak as
the primary fix.

### Approach C: Robust extraction — scan all messages for last `task_status`
**Cons:** The skipped sessions emitted the token **zero** times, so there is nothing
earlier to recover. Helps the post-result-truncation variant but NOT the
background-notification-hijack variant (the dominant one here). Complementary only.

### Selected: A (B + C optional complementary hardening, flag in review)
**Rationale:** A is the only approach that closes the dominant failure mode
deterministically, is self-contained in callback.py, preserves the TECH-194
allowlist safety property (still requires confirmed merged work), and is fully
testable. B/C are best-effort and do not cover the observed cause.

---

## Historical Risks

<!-- lessons-binding v1 -->

- **TECH-194 Layer E** — the allowlist (`task_status=="complete"`) replaced a
  blocklist precisely because `task_status==""` from SIGKILL/missing-output
  dispatched incorrectly. Approach A must NOT regress to a blocklist: it adds QA
  dispatch ONLY when a real merge is independently confirmed (stronger than
  `status=="done"`), so SIGKILL-without-merge still skips.
- **ADR-024 (BUG-188)** — post-result SDK exceptions already corrupt final
  telemetry; this is a sibling symptom (final line unreliable). Do not rely on the
  final telemetry line alone.
- **ADR-023 / ADR-025** — callback is the single status writer; this spec must not
  touch lifecycle writes, only the QA/Reflect *dispatch* decision.
- **[[project_qa-skip-background-notification-hijack]]** (operator memory) — full
  forensic + manual backfill procedure.

---

## Eval Criteria (MANDATORY)

### Deterministic / Integration Assertions
| ID | Scenario | Setup | Expected | Type | Priority |
|----|----------|-------|----------|------|----------|
| EC-1 | merged + no complete signal → QA dispatched | autopilot done, `task_status=''`, spec implementation commit present on a local `origin/develop` fixture | `dispatch_qa` + `dispatch_reflect` called once each | integration | P0 |
| EC-2 | no merge + no complete signal → still skipped | autopilot done, `task_status=''`, NO implementation commit on develop | neither dispatched; logs skip | integration | P0 |
| EC-3 | explicit complete still works | `task_status='complete'` | dispatched (unchanged behaviour) | integration | P0 |
| EC-4 | blocked/needs_review never dispatch | `status` not done / `task_status='blocked'` | not dispatched | deterministic | P1 |
| EC-5 | dedup intact | dispatch twice for same spec | second is a no-op (`is_already_queued`) | integration | P1 |

### Coverage Summary
- Integration: 4 | Deterministic: 1 | Total: 5 (min 3) ✓
- Tests use real git repos via tmp_path (ADR-013 — no mocks in integration).

---

## Definition of Done

### Functional
- [ ] Done autopilot run whose work is confirmed merged on develop → QA + Reflect
      dispatched even when `task_status != "complete"`.
- [ ] Done run with NO confirmed merge → QA still skipped (allowlist preserved).
- [ ] Explicit `task_status=="complete"` path unchanged.

### Tests
- [ ] EC-1..EC-5 pass (`scripts/vps/tests/`, real-repo fixtures, no mocks).

### Technical
- [ ] Single-writer status model untouched (no lifecycle.py / *.yaml edits).
- [ ] Circuit-breaker (TECH-169) untouched.
- [ ] New log marker `QA_DISPATCH_MERGE_FALLBACK` for observability.

### Follow-ups (separate inbox items)
- [ ] Approach B: autopilot collects background tasks before the completion signal.
- [ ] Approach C: claude-runner scans all messages for last `task_status`.
- [ ] One-shot: audit historically done-without-QA specs across projects, backfill.

---

## Autopilot Log
[Auto-populated by autopilot during execution]
