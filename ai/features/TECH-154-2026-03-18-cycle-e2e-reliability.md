# Feature: [TECH-154] DLD Cycle E2E Reliability — First Full Pass
**Status:** queued | **Priority:** P0 | **Date:** 2026-03-18

## Why
DLD цикл никогда не проходил полный прогон от inbox до reflect. Три конкретных разрыва выявлены в сессии 2026-03-18: (1) QA не находит спеку — false pass, (2) artifact-scan не читает QA-файлы агентского формата, (3) topic_id NULL для 5 из 6 проектов — уведомления молча падают. Без этих фиксов pipeline не завершает ни одного цикла автономно.

## Context
- pueue-callback.sh отправляет QA с промптом `/qa Проверь изменения после SPEC-ID` — QA skill не может найти спеку по freeform-тексту
- openclaw-artifact-scan.py ожидает `**Status:**` header в QA-отчётах, но QA skill (через run-agent.sh) пишет файлы с `Date:` header и ISO-форматом `2026-03-17-tech-151.md`
- projects.json — только dld имеет topic_id: 7; awardybot, dowry, dowry-mc, nexus, plpilot — без topic_id
- notify.py корректно отказывается слать без topic_id (fail-closed), но это значит 83% проектов без уведомлений

---

## Scope
**In scope:**
- Fix QA dispatch prompt в pueue-callback.sh
- Fix artifact-scan для обоих форматов QA-отчётов
- Add topic_id для всех проектов в projects.json (placeholder + CLI migration tool)
- Smoke test для full cycle validation

**Out of scope:**
- Рефакторинг qa-loop.sh vs run-agent.sh (два пути к QA — оба валидны)
- Pipeline contract layer (Approach 2 — overkill для 6 проектов)
- Dry-run mode (Approach 3 — не фиксит баги, только surfacing)
- Fix reflect dispatch (отдельный revert 6441dbc — другая задача)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `pueue-callback.sh:362` — QA dispatch prompt → called by Pueue daemon on task completion
- `openclaw-artifact-scan.py:79-88` → called by OpenClaw session via CLI
- `projects.json` → read by orchestrator.sh:sync_projects() every cycle

### Step 2: DOWN — what depends on?
| File | Depends on | Function |
|------|-----------|----------|
| pueue-callback.sh | run-agent.sh, db.py, notify.py | QA/reflect dispatch |
| openclaw-artifact-scan.py | ai/qa/*.md, ai/openclaw/ | QA report parsing |
| projects.json | orchestrator.sh | seed via db.seed_projects_from_json |
| notify.py | db.py:get_project_state() | topic_id lookup |

### Step 3: BY TERM — grep entire project
- `grep -rn "topic_id" scripts/vps/` → 30+ results (db.py, notify.py, projects.json, schema.sql, tests/)
- `grep -rn '"/qa ' scripts/vps/ --include="*.sh"` → 3 results (pueue-callback.sh:362, qa-loop.sh:65)
- `grep -rn "extract_status\|qa_candidates" scripts/vps/` → 2 results (openclaw-artifact-scan.py:29,79)

| File | Line | Status | Action |
|------|------|--------|--------|
| scripts/vps/pueue-callback.sh | 362 | BUG | Fix QA prompt |
| scripts/vps/openclaw-artifact-scan.py | 29-33 | BUG | Add fallback status extraction |
| scripts/vps/openclaw-artifact-scan.py | 79 | OK | Filter already accepts both formats |
| scripts/vps/projects.json | all | DATA | Add topic_id for 5 projects |
| scripts/vps/notify.py | 95-101 | OK | Guard works correctly |
| scripts/vps/db.py | 235 | OK | COALESCE preserves existing bindings |

### Step 4: CHECKLIST — mandatory folders
- [x] `scripts/vps/tests/` checked — need new test file
- [x] `scripts/vps/schema.sql` checked — no migration needed (topic_id column exists)

### Verification
- [x] All found files added to Allowed Files
- [x] grep by old term = 0 after fix (no stale patterns remain)

---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `scripts/vps/pueue-callback.sh` — Fix QA dispatch prompt (line 362)
2. `scripts/vps/openclaw-artifact-scan.py` — Improve extract_status() + extract_spec() fallbacks
3. `scripts/vps/projects.json` — Add topic_id placeholder for all 5 missing projects

**New files allowed:**
- `scripts/vps/tests/test_cycle_smoke.py` — Smoke test for full cycle wiring

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** scripts/vps (orchestrator infrastructure)
**Cross-cutting:** Notifications (Telegram topic routing), DB state management
**Data model:** project_state.topic_id (nullable INTEGER)

---

## Approaches

### Approach 1: Targeted Surgical Fixes (based on codebase + patterns scouts)
**Source:** [CircleCI smoke testing](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/), [BATS E2E testing](https://blog.cubieserver.de/2025/effective-end-to-end-testing-with-bats/)
**Summary:** Fix each break at the exact location: callback prompt, artifact-scan parser, projects.json data. Add pytest smoke test for cycle wiring.
**Pros:** R2 blast radius per fix, no new abstractions, independently deployable
**Cons:** No systemic protection against future format drift

### Approach 2: Pipeline Contract Layer (based on patterns scout)
**Source:** [Conduktor data contracts](https://conduktor.io/glossary/data-contracts-for-reliable-pipelines)
**Summary:** Add pipeline_contract.py as cross-cutting validation layer at all stage boundaries.
**Pros:** Prevents future format drift structurally
**Cons:** ~$15, R1 blast radius, overkill for 6-project orchestrator, doesn't fix bugs — wraps them

### Selected: 1
**Rationale:** Root causes are known, each fix is 1-5 lines, R2 scope. Contract layer (Approach 2) is justified when pipeline grows to 15+ projects. Smoke test provides regression guard at lower cost. Consistent with ADR-017 (fix via Python CLI, not new layers).

---

## Design

### Architecture

```
pueue-callback.sh ─→ run-agent.sh ─→ claude-runner.py ─→ /qa SPEC_ID
       │                                                       │
       │  Fix #1: pass spec ID directly                        │
       │  (was: freeform "Проверь изменения после...")         │
       │                                                       ↓
       │                                              QA skill finds spec
       │
       ├──→ openclaw-artifact-scan.py
       │         Fix #2: extract_status() handles both formats
       │         - qa-loop.sh: **Status:** passed (structured)
       │         - QA skill:   Date: 2026-03-17 (unstructured)
       │
       └──→ notify.py ──→ topic_id from DB
                    Fix #3: projects.json has topic_id for all projects
```

### Database Changes
No schema changes. Data fix: UPDATE project_state SET topic_id WHERE project_id IN (...).
Seeded via projects.json on next orchestrator cycle.

---

## Implementation Plan

### Research Sources
- [CircleCI Smoke Testing](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/) — smoke test structure
- [BATS E2E testing](https://blog.cubieserver.de/2025/effective-end-to-end-testing-with-bats/) — bash pipeline testing
- [PTB issue #4139](https://github.com/python-telegram-bot/python-telegram-bot/issues/4139) — thread routing

### Task 1: Fix QA dispatch prompt in pueue-callback.sh
**Type:** code
**Files:**
  - modify: `scripts/vps/pueue-callback.sh`
**Acceptance:**
- QA dispatch sends `/qa SPEC_ID` (not freeform Russian text)
- SPEC_ID is extracted from TASK_LABEL (already available)

**Details:**
Line 362 change:
```bash
# Before:
"/qa Проверь изменения после ${TASK_LABEL}"
# After:
"/qa ${TASK_LABEL}"
```

### Task 2: Fix artifact-scan QA report parsing
**Type:** code
**Files:**
  - modify: `scripts/vps/openclaw-artifact-scan.py`
**Acceptance:**
- `extract_status()` returns "passed"/"failed" for both QA report formats
- Files like `2026-03-17-tech-151.md` (QA skill format) correctly parsed
- Files like `20260317-162026-TECH-153.md` (qa-loop.sh format) still work

**Details:**
1. `extract_status()` — add fallback: if `**Status:**` not found, scan for `## Summary` table with `Pass`/`Fail` counts, or look for `Вердикт:` line
2. `extract_spec()` — add fallback: extract SPEC_ID from filename via regex `(TECH|FTR|BUG|ARCH)-\d+` (case-insensitive)

### Task 3: Add topic_id to projects.json + DB migration helper
**Type:** code
**Files:**
  - modify: `scripts/vps/projects.json`
**Acceptance:**
- All 6 projects have topic_id in JSON
- orchestrator.sh sync cycle seeds DB with topic_ids
- notify.py sends to correct topics for all projects

**Details:**
Topic IDs must be provided by operator. Spec creates placeholder structure:
```json
{
  "project_id": "awardybot",
  "topic_id": null,  // ACTION REQUIRED: operator must set real topic_id
  ...
}
```
Implementation task: add `topic_id` key to all 5 entries. Operator fills real values before deploy.

### Task 4: Smoke test for cycle wiring
**Type:** test
**Files:**
  - create: `scripts/vps/tests/test_cycle_smoke.py`
**Pattern:** [CircleCI smoke testing](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/)
**Acceptance:**
- Test validates: project with topic_id → notify.py can route
- Test validates: QA report in both formats → artifact-scan extracts status
- Test validates: callback QA prompt format is `/qa SPEC-ID` (not freeform)
- All tests pass with `pytest scripts/vps/tests/test_cycle_smoke.py`

### Execution Order
1 → 2 → 3 → 4

---

## Flow Coverage Matrix (REQUIRED)

| # | Pipeline Step | Covered by Task | Status |
|---|--------------|-----------------|--------|
| 1 | Inbox file created | - | existing |
| 2 | Orchestrator scans inbox | - | existing |
| 3 | Spark creates spec | - | existing |
| 4 | Autopilot executes | - | existing |
| 5 | Callback dispatches QA | Task 1 | fix |
| 6 | QA agent finds spec | Task 1 | fix |
| 7 | QA writes report | - | existing |
| 8 | Artifact-scan parses QA report | Task 2 | fix |
| 9 | Callback sends notification | Task 3 | fix |
| 10 | Full cycle verified | Task 4 | new |

**GAPS:** None. All broken steps covered by tasks, all working steps marked existing.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | QA dispatch prompt format | pueue-callback.sh dispatches QA after autopilot done | Prompt is `/qa SPEC-ID` (no Russian freeform text) | deterministic | codebase scout | P0 |
| EC-2 | artifact-scan: structured QA report | `20260317-162026-TECH-153.md` with `**Status:** passed` | extract_status() returns "passed" | deterministic | codebase scout | P0 |
| EC-3 | artifact-scan: agent QA report | `2026-03-17-tech-151.md` with `## Summary` table | extract_status() returns "failed" (6 failures in report) | deterministic | codebase scout | P0 |
| EC-4 | artifact-scan: spec from filename | `2026-03-17-tech-151.md` | extract_spec() returns "TECH-151" | deterministic | codebase scout | P1 |
| EC-5 | projects.json has topic_id for all | Read projects.json | All 6 entries have `topic_id` key (non-null after operator fills) | deterministic | user requirement | P0 |
| EC-6 | notify.py routes with topic_id | Project with topic_id=7, message "test" | send_to_project() returns True | deterministic | external scout | P1 |

### Integration Assertions (if applicable)

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-7 | Seed project with topic_id in isolated DB | Call notify.py send_to_project() | Message sent to correct topic (mocked Telegram) | integration | external scout | P1 |

### Coverage Summary
- Deterministic: 6 | Integration: 1 | LLM-Judge: 0 | Total: 7 (min 3 met)

### TDD Order
1. EC-1 (QA prompt) → fix callback → PASS
2. EC-2, EC-3, EC-4 (artifact-scan) → fix parser → PASS
3. EC-5 (projects.json) → add topic_id → PASS
4. EC-6, EC-7 (notify routing) → verify end-to-end → PASS

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Tests pass | `cd scripts/vps && python3 -m pytest tests/test_cycle_smoke.py -v` | exit 0 | 30s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | QA prompt is clean | Read pueue-callback.sh line 362 | `grep '"/qa ${TASK_LABEL}"' scripts/vps/pueue-callback.sh` | Match found |
| AV-F2 | All projects have topic_id key | Read projects.json | `python3 -c "import json; d=json.load(open('scripts/vps/projects.json')); assert all('topic_id' in p for p in d)"` | exit 0 |
| AV-F3 | artifact-scan handles ISO format | Create test file with ISO date + Summary table | `python3 scripts/vps/openclaw-artifact-scan.py --project-dir /tmp/test` returns non-unknown status | JSON with status != "unknown" |

### Verify Command (copy-paste ready)

```bash
# Smoke
cd /home/dld/projects/dld
python3 -m pytest scripts/vps/tests/test_cycle_smoke.py -v

# Functional
grep '"/qa ${TASK_LABEL}"' scripts/vps/pueue-callback.sh
python3 -c "import json; d=json.load(open('scripts/vps/projects.json')); assert all('topic_id' in p for p in d), 'Missing topic_id'"
```

### Post-Deploy URL
```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [x] QA dispatch sends spec ID directly (not freeform text)
- [x] artifact-scan parses both QA report formats
- [x] All projects have topic_id in projects.json
- [x] Smoke test validates full cycle wiring

### Tests
- [x] All eval criteria from ## Eval Criteria section pass
- [x] Coverage not decreased

### Acceptance Verification
- [x] All Smoke checks (AV-S*) pass locally
- [x] All Functional checks (AV-F*) pass locally
- [x] Verify Command runs without errors

### Technical
- [x] Tests pass (./test fast)
- [x] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
