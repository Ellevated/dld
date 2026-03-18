# Bug: [BUG-155] DLD Cycle E2E Reliability v2 — Three Gap Closure + Smoke Test

**Status:** queued | **Priority:** P0 | **Date:** 2026-03-18

## Why

TECH-154 (v1) attempted to fix cycle gaps but the DLD cycle has STILL never completed
a full pass from inbox to reflect without manual intervention. Three confirmed gaps
persist from the 2026-03-18 diagnostic session, plus additional issues found by devil
scout analysis.

**False pass scenario:** QA reports exit 0 even when it couldn't find the spec, meaning
broken specs pass QA and enter production. This is a P0 reliability issue.

## Context

TECH-154 was marked done but did not resolve the underlying issues. This spec addresses
the actual root causes found by 4 parallel scout analysis of the live codebase.

Key architectural fact: `qa-loop.sh` is dead code. The actual QA dispatch goes through
`pueue-callback.sh:361-363` → `run-agent.sh` → `claude-runner.py`. But `qa-loop.sh`
is still referenced in orchestrator.sh `dispatch_qa()` (currently neutered — callback
owns dispatch). Fixing the dead code is out of scope; fixing the live dispatch path is
in scope.

---

## Scope

**In scope:**
- Gap 1: QA spec resolution — fix `pueue-callback.sh` artifact_rel lookup to find the
  correct QA report (not draft files)
- Gap 2: Artifact scan filename filter — `pueue-callback.sh:303` uses `sort | tail -1`
  which picks up `draft-v2-*` files; need to filter to canonical format only
- Gap 3: `notify.py` — add OPS_TOPIC_ID fallback for projects without explicit topic_id
- Gap 4 (devil): `_submit_to_pueue` in `telegram-bot.py` has wrong arg order for
  `run-agent.sh` — `provider` arg gets the full command string
- Smoke test: `tests/scripts/test_cycle_smoke.py` — validate label parsing, QA dispatch
  args, artifact lookup, and notify fallback

**Out of scope:**
- Removing `qa-loop.sh` entirely (separate cleanup task)
- Reflect dispatch race condition with QA (devil gap #6 — phase machine redesign)
- `db_exec.sh` SQL injection (ADR-017 violation — separate TECH task)
- Migrating QA dispatch from callback to orchestrator

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP -- who uses?
- [x] `pueue-callback.sh` used by: Pueue daemon (callback on task completion)
- [x] `notify.py` used by: pueue-callback.sh, orchestrator.sh, qa-loop.sh, night-reviewer.sh
- [x] `telegram-bot.py` used by: systemd service (dld-telegram-bot.service)

### Step 2: DOWN -- what depends on?
- [x] `pueue-callback.sh` → db.py, notify.py, run-agent.sh, pueue CLI
- [x] `notify.py` → db.py, python-telegram-bot
- [x] `telegram-bot.py` → db.py, run-agent.sh, pueue CLI

### Step 3: BY TERM -- grep entire project
- [x] `artifact_rel` — only in pueue-callback.sh
- [x] `OPS_TOPIC_ID` — new env var, grep = 0 (new)
- [x] `_submit_to_pueue` — only in telegram-bot.py

### Step 4: CHECKLIST -- mandatory folders
- [x] `tests/scripts/` — new test file
- [x] `scripts/vps/.env.example` — add OPS_TOPIC_ID

### Verification
- [x] All found files added to Allowed Files
- [x] grep by old terms = no rename needed

---

## Allowed Files

**ONLY these files may be modified during implementation:**
1. `scripts/vps/pueue-callback.sh` — fix artifact_rel lookup for QA reports
2. `scripts/vps/notify.py` — add OPS_TOPIC_ID fallback
3. `scripts/vps/telegram-bot.py` — fix _submit_to_pueue arg order
4. `scripts/vps/.env.example` — add OPS_TOPIC_ID

**New files allowed:**
- `tests/scripts/test_cycle_smoke.py` — smoke test for cycle components

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (scripts/vps/)
**Cross-cutting:** Notifications, Phase Machine
**Data model:** project_state.topic_id

---

## Approaches

### Approach 1: Surgical Fix + Unit Smoke Test (Selected)

**Source:** Codebase scout + Devil scout analysis
**Summary:** Fix 4 specific bugs in 3 files + add pytest smoke test
**Pros:** Minimal blast radius, each fix is independent, testable
**Cons:** Doesn't address phase machine race conditions (devil gap #6)

### Approach 2: QA Dispatch Rewrite

**Source:** Pattern scout recommendation
**Summary:** Move QA dispatch from callback to orchestrator poll loop
**Pros:** Cleaner architecture, eliminates race conditions
**Cons:** Major refactor of phase machine, R0 risk (could break existing flow)

### Selected: 1

**Rationale:** Approach 1 fixes the 3 reported gaps + 1 critical devil finding with
R1 risk. Phase machine redesign (Approach 2) is a separate ARCH task.

---

## Design

### User Flow
1. Autopilot completes a spec → pueue callback fires
2. Callback identifies correct QA report file (not drafts) → creates OpenClaw event
3. Callback dispatches QA via run-agent.sh with correct args
4. QA agent runs, writes report
5. notify.py sends result to project topic (or OPS_TOPIC_ID fallback)

### Architecture

```
pueue-callback.sh
├── Fix 1: artifact_rel filter (grep for canonical YYYYMMDD-HHMMSS pattern)
├── Fix 2: _submit_to_pueue arg order (provider before command)
└── Fix 3: QA report lookup excludes draft-* files

notify.py
└── Fix 4: OPS_TOPIC_ID fallback when topic_id is NULL
```

### Root Cause Analysis (per gap)

**Gap 1: QA не находит спеку**

Root cause: NOT in qa-loop.sh (dead code). Real issue is in `telegram-bot.py:_submit_to_pueue()`.
Args to run-agent.sh are in WRONG order:
```python
# CURRENT (BROKEN):
task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
            f"claude -p /autopilot {task_id}", project.get("provider", "claude"), "autopilot"]
# This produces: run-agent.sh <path> <"claude -p /autopilot TECH-151"> <"claude"> <"autopilot">
# run-agent.sh expects: <path> <provider> <skill> <task...>
# So PROVIDER gets the full command string → case match fails

# FIXED:
task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
            project.get("provider", "claude"), "autopilot",
            f"/autopilot {task_id}"]
# This produces: run-agent.sh <path> <"claude"> <"autopilot"> <"/autopilot TECH-151">
```

When run-agent.sh fails silently (pueue catches exit), the callback fires with
STATUS=failed, SKILL="" (no agent JSON output), and QA is never dispatched.
Result: no QA runs, cycle stops.

**Gap 2: artifact-scan не читает QA файлы**

Root cause in `pueue-callback.sh:303`:
```bash
find "${PROJECT_PATH_FOR_EVENT}/ai/qa" -maxdepth 1 -type f -name "*.md" | sort | tail -1
```
This picks the lexicographically LAST .md file, which could be `draft-v2-from-scratch.md`
instead of the actual QA report. Fix: filter to canonical pattern `[0-9]*-*.md`.

**Gap 3: topic_id NULL**

Root cause: `notify.py:96-101` fail-closed (correct behavior) but provides NO fallback.
Five projects have NULL topic_id because they were added before `/bindtopic` existed.
Fix: add OPS_TOPIC_ID env var as operations fallback channel.

---

## Implementation Plan

### Research Sources
- Codebase scout: pueue-callback.sh dispatch flow analysis
- Devil scout: 4 additional gaps found (2 included in scope)
- Pattern scout: "normalize at write boundary" principle

### Task 1: Fix _submit_to_pueue arg order in telegram-bot.py
**Type:** code
**Files:**
  - modify: `scripts/vps/telegram-bot.py`
**Acceptance:** run-agent.sh receives args in correct order: `<path> <provider> <skill> <task>`

### Task 2: Fix artifact_rel lookup in pueue-callback.sh
**Type:** code
**Files:**
  - modify: `scripts/vps/pueue-callback.sh`
**Acceptance:** `artifact_rel` only matches QA reports with canonical `YYYYMMDD-HHMMSS-*` prefix, excludes `draft-*` files

### Task 3: Add OPS_TOPIC_ID fallback to notify.py
**Type:** code
**Files:**
  - modify: `scripts/vps/notify.py`
  - modify: `scripts/vps/.env.example`
**Acceptance:** When project has no topic_id, notification goes to OPS_TOPIC_ID (if set); logged as warning

### Task 4: Cycle smoke test
**Type:** test
**Files:**
  - create: `tests/scripts/test_cycle_smoke.py`
**Acceptance:** Tests pass, covering: label parsing, QA dispatch arg order, artifact lookup filter, notify fallback logic

### Execution Order
1 → 2 → 3 → 4

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Autopilot completes spec | - | existing |
| 2 | Callback parses label correctly | Task 4 (test) | existing |
| 3 | _submit_to_pueue sends correct args | Task 1 | fix |
| 4 | Callback finds correct QA artifact | Task 2 | fix |
| 5 | QA dispatched with correct spec ID | Task 1 | fix |
| 6 | QA writes report | - | existing |
| 7 | Notification sent to correct topic | Task 3 | fix |
| 8 | Full cycle validated | Task 4 | new |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | _submit_to_pueue arg order | project with path=/p, provider=claude, task_id=TECH-151 | run-agent.sh args: ["/p", "claude", "autopilot", "/autopilot TECH-151"] | deterministic | devil scout | P0 |
| EC-2 | artifact_rel excludes drafts | ai/qa/ has draft-v2-from-scratch.md + 20260318-120000-TECH-151.md | artifact_rel = ai/qa/20260318-120000-TECH-151.md | deterministic | codebase scout | P0 |
| EC-3 | artifact_rel handles empty dir | ai/qa/ has no matching files | artifact_rel = "" (empty string) | deterministic | devil scout | P1 |
| EC-4 | notify fallback to OPS_TOPIC | project with topic_id=NULL, OPS_TOPIC_ID=42 | message sent to thread_id=42 | deterministic | pattern scout | P0 |
| EC-5 | notify no fallback when no OPS | project with topic_id=NULL, OPS_TOPIC_ID not set | return False, log warning | deterministic | devil scout | P1 |
| EC-6 | notify normal path unchanged | project with topic_id=100 | message sent to thread_id=100 (no fallback) | deterministic | codebase scout | P0 |
| EC-7 | label parsing colon separator | label="dld:TECH-151" | PROJECT_ID="dld", TASK_LABEL="TECH-151" | deterministic | codebase scout | P1 |

### Coverage Summary
- Deterministic: 7 | Integration: 0 | LLM-Judge: 0 | Total: 7 (min 3)

### TDD Order
1. Write test from EC-1 -> FAIL -> Fix _submit_to_pueue -> PASS
2. EC-2, EC-3 -> Fix artifact_rel -> PASS
3. EC-4, EC-5, EC-6 -> Add OPS_TOPIC_ID fallback -> PASS
4. EC-7 -> Existing behavior validation -> PASS

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Tests pass | `cd /home/dld/projects/dld && python3 -m pytest tests/scripts/test_cycle_smoke.py -v` | exit 0 | 30s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | _submit_to_pueue arg order | Read telegram-bot.py | Verify run-agent.sh args: path, provider, skill, task | Args in correct order |
| AV-F2 | artifact_rel filter | Create dummy ai/qa/ with draft + canonical files | Run find with filter | Only canonical file returned |
| AV-F3 | notify OPS fallback | Set OPS_TOPIC_ID in env | Call send_to_project with NULL topic | Message routed to OPS topic |

### Verify Command (copy-paste ready)

```bash
# Smoke
cd /home/dld/projects/dld && python3 -m pytest tests/scripts/test_cycle_smoke.py -v

# Verify _submit_to_pueue fix
grep -A5 '_submit_to_pueue' scripts/vps/telegram-bot.py | grep 'run-agent.sh'

# Verify artifact_rel filter
grep 'find.*ai/qa' scripts/vps/pueue-callback.sh | head -1

# Verify OPS_TOPIC_ID
grep 'OPS_TOPIC_ID' scripts/vps/notify.py
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] _submit_to_pueue passes args to run-agent.sh in correct order
- [ ] artifact_rel lookup excludes non-canonical files (draft-*, etc.)
- [ ] notify.py falls back to OPS_TOPIC_ID when project has no topic_id
- [ ] All 7 eval criteria pass

### Tests
- [ ] tests/scripts/test_cycle_smoke.py passes
- [ ] Coverage not decreased

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
