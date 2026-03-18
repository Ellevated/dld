# Codebase Research — Fix 3 DLD Cycle E2E Breaks + Smoke Test

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `db.set_project_topic` | scripts/vps/db.py:274 | Binds topic_id+chat_id to existing project | Import directly in migration script |
| `db.seed_projects_from_json` | scripts/vps/db.py:221 | COALESCE upsert that preserves existing topic binding | Already handles NULL-safe upsert — extend with default topics |
| `db.get_project_state` | scripts/vps/db.py:122 | Returns project dict with topic_id | Already used by notify.py — no change needed |
| `extract_status` / `extract_spec` | scripts/vps/openclaw-artifact-scan.py:29-39 | Parse `**Status:**` / `**Spec:**` from QA report | Pattern only — already works for files it matches |
| `TestSeedProjects.test_seed_preserves_existing_topic_binding_when_json_omits_it` | scripts/vps/tests/test_db.py:57 | Tests COALESCE upsert | Extend pattern for smoke test coverage |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| Exit-1 on missing spec | scripts/vps/qa-loop.sh:40-45 | Already has guard: exits 1 if spec not found | Break #1 is ALREADY fixed here — problem is upstream (pueue callback dispatches `/qa` without spec path, not qa-loop.sh) |
| `qa_candidates` name filter | scripts/vps/openclaw-artifact-scan.py:79 | `p.name[:4].isdigit()` — checks if first 4 chars are digits | Break #2 root: `2026-03-17...` starts with `2026` which IS 4 digits — but ISO date is 10 chars not 8 |
| `notify.py` fail-closed guard | scripts/vps/notify.py:95-101 | Refuses send if topic_id is NULL | Break #3 root: guard works correctly, but topic_id IS NULL in DB for 5 projects |

**Recommendation:**
- Break #1: fix is in `pueue-callback.sh` Step 7 — QA dispatch sends `/qa Проверь изменения...` as a free-text prompt, but qa-loop.sh expects SPEC_ID as `$3`. The callback dispatches via `run-agent.sh` as a skill=qa, but qa-loop.sh is called from orchestrator's `dispatch_qa()` — these are two DIFFERENT qa flows. The callback dispatches QA via `run-agent.sh` (agent), not via `qa-loop.sh`. So the real break is: when does `qa-loop.sh` get called? It does NOT get called by callback currently. The callback dispatches the claude agent with `/qa Проверь изменения...`. Need to confirm exactly.
- Break #2: fix `openclaw-artifact-scan.py` line 79 — the `[:4].isdigit()` check accepts `2026` but then the full pattern still needs to match QA report naming. Read more carefully below.
- Break #3: add topic_id to `projects.json` for all 5 projects OR add a one-time migration script.

---

## Deep Dive: Break #1 — QA Spec Path

### Actual flow tracing

`pueue-callback.sh` Step 7 (line 360-363) dispatches:
```
pueue add ... run-agent.sh $PROJECT_PATH $PROJECT_PROVIDER "qa" "/qa Проверь изменения после ${TASK_LABEL}"
```

This calls `run-agent.sh` with skill=`qa` and prompt=`/qa Проверь...`. The agent (`/qa` skill) runs inside the project and is expected to find the spec itself. The agent asks the user when it can't find it — that's the observed failure.

**`qa-loop.sh` is NOT involved in this path.** It's only dispatched by `orchestrator.sh:dispatch_qa()` which checks `phase=qa_pending` but also notes: "Callback owns QA/Reflect dispatch" (line 353-364) — it only resets stuck `qa_pending` to `idle` without current_task.

The `run-agent.sh` path is: `claude --print ... -p "/qa Проверь изменения после FTR-702"`. The agent gets a text prompt, not a spec path. The `/qa` skill needs to know which spec to test.

**Root cause confirmed:** callback passes a human-readable string, not the spec ID. The `/qa` skill receives `"Проверь изменения после FTR-702"` but should receive `"/qa FTR-702"` (the spec ID directly so the skill can find `ai/features/FTR-702*.md`).

### Fix location
`/home/dld/projects/dld/scripts/vps/pueue-callback.sh` line 362:
```bash
"/qa Проверь изменения после ${TASK_LABEL}"
```
Change to:
```bash
"/qa ${TASK_LABEL}"
```
where `TASK_LABEL` is already the spec ID (e.g. `FTR-702`).

---

## Deep Dive: Break #2 — Artifact Scan Pattern

### `qa_candidates` filter at line 79

```python
qa_candidates = [p for p in qa_dir.glob("*.md") if p.name[:4].isdigit()]
```

Real filenames in `ai/qa/`:
- `20260317-162026-TECH-153.md` — 8-digit compact date — `[:4]` = `2026` → PASSES filter
- `2026-03-17-tech-151.md` — ISO date — `[:4]` = `2026` → PASSES filter
- `2026-03-17-tech-153.md` → PASSES
- `2026-03-17-tech153.md` → PASSES
- `draft-v2-from-scratch.md` → `[:4]` = `draf` → BLOCKED (correct)

So the `[:4].isdigit()` filter is NOT the bug — it accepts both formats.

**Real break #2:** `extract_status()` and `extract_spec()` read `**Status:**` and `**Spec:**` from QA report files. But the files like `2026-03-17-tech-151.md` were written manually (not by `qa-loop.sh`), so they may not have these fields. The `qa-loop.sh` writes properly formatted reports with `**Status:**` header — IF it was called.

However, looking at `qa-loop.sh` line 78:
```bash
REPORT_FILE="${QA_DIR}/${TIMESTAMP}-${SPEC_ID}.md"
```
where `TIMESTAMP=$(date '+%Y%m%d-%H%M%S')` — this generates `20260317-162026-TECH-153.md` format. That IS the format `artifact-scan` was built for.

But the actual files `2026-03-17-tech-151.md` (ISO format) come from **manual QA runs** (not qa-loop.sh). The scanner's `extract_status()` returns `"unknown"` when `**Status:**` line is absent — which is what happens for manual files lacking the header.

**The real break:** The QA agent (dispatched via callback → run-agent.sh) writes its own output files directly to `ai/qa/` using the agent's own naming convention (ISO date, lowercase), bypassing qa-loop.sh entirely. The `artifact_rel` pointer in the OpenClaw event (pueue-callback.sh line 303) uses:
```bash
ARTIFACT_REL=$(find "${PROJECT_PATH_FOR_EVENT}/ai/qa" -maxdepth 1 -type f -name "*.md" | sort | tail -1 ...)
```
This finds the LATEST `.md` file by sort order. For ISO-named files `2026-03-17-tech-151.md` sorted lexicographically, this can pick wrong file or an unstructured file without `**Status:**`.

**Fix locations:**
1. `openclaw-artifact-scan.py` line 29-33: make `extract_status()` also look for lowercase `**status:**` or unformatted status
2. OR: `qa-loop.sh` wraps the agent call and always writes the structured report regardless of agent output format (which it already does at lines 87-104 — but this only works when qa-loop.sh is the dispatch path, not run-agent.sh directly)
3. OR: callback's `artifact_rel` search should be scoped to files written AFTER the task started (not just latest)

---

## Deep Dive: Break #3 — topic_id NULL

### Live DB state (confirmed)

```
awardybot  | topic_id=NULL | chat_id=-1003730735152
dld        | topic_id=7    | chat_id=-1003730735152
dowry      | topic_id=NULL | chat_id=-1003730735152
dowry-mc   | topic_id=NULL | chat_id=-1003730735152
nexus      | topic_id=NULL | chat_id=-1003730735152
plpilot    | topic_id=NULL | chat_id=-1003730735152
```

`projects.json` confirms: only `dld` has `topic_id: 7`. All others are missing `topic_id` in the JSON.

`notify.py` line 96: `if not topic_id or topic_id == 1:` → refuses to send → exits 1. All 5 projects silently fail Telegram notifications.

`seed_projects_from_json` uses `COALESCE(excluded.topic_id, project_state.topic_id)` — so if topic_id is already in DB but not in JSON, it's preserved. But since these projects were ALWAYS seeded without topic_id, the DB also has NULL.

**Fix:** Add `topic_id` values for all projects to `projects.json`. The topic IDs need to be obtained from the Telegram group (each project has its own forum topic). This is data the human must provide — not determinable from code.

Alternative: use `db.set_project_topic()` as a one-time migration CLI call per project.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

**Break #1 — qa-loop.sh / pueue-callback.sh QA dispatch:**
- `pueue-callback.sh` calls `run-agent.sh` with qa skill — no other callers
- `orchestrator.sh:dispatch_qa()` calls `qa-loop.sh` — dead in current setup (callback owns QA)

**Break #2 — openclaw-artifact-scan.py:**
- Called by OpenClaw session as `python3 scripts/vps/openclaw-artifact-scan.py --project-dir .`
- Referenced in `ai/openclaw/README.md`
- No Python import chains (standalone script)

**Break #3 — projects.json:**
- `orchestrator.sh:sync_projects()` reads it every cycle → `db.seed_projects_from_json()`
- `notify.py` reads `topic_id` from DB (written by seed)

### Step 2: DOWN — What does it depend on?

| File | Depends on | Function |
|------|-----------|----------|
| pueue-callback.sh | run-agent.sh | QA skill dispatch |
| pueue-callback.sh | db.py | `callback` CLI |
| pueue-callback.sh | notify.py | Telegram notification |
| openclaw-artifact-scan.py | ai/qa/*.md | QA report files |
| openclaw-artifact-scan.py | ai/openclaw/pending-events/*.json | Event files |
| notify.py | db.py | `get_project_state()` |
| projects.json | orchestrator.sh | seeded via `seed_projects_from_json` |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "topic_id" scripts/vps/ --include="*.py" --include="*.json" --include="*.sh"
# Results: 30+ occurrences across db.py, notify.py, projects.json, schema.sql, tests/
```

Key occurrences:
| File | Line | Context |
|------|------|---------|
| scripts/vps/notify.py | 96 | `if not topic_id or topic_id == 1:` — fail-closed guard |
| scripts/vps/db.py | 235 | `COALESCE(excluded.topic_id, project_state.topic_id)` — preserves existing binding |
| scripts/vps/projects.json | 13 | `"topic_id": 7` — only dld has it |
| scripts/vps/schema.sql | 13 | `topic_id INTEGER` — nullable column |

```bash
grep -rn "qa_candidates\|\.glob.*\.md\|name\[:4\]" scripts/vps/ --include="*.py"
# Results: 2 occurrences in openclaw-artifact-scan.py
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/openclaw-artifact-scan.py | 79 | `qa_candidates = [p for p in qa_dir.glob("*.md") if p.name[:4].isdigit()]` |
| scripts/vps/openclaw-artifact-scan.py | 80 | `for qa_file in sorted(qa_candidates, reverse=True)[:10]:` |

```bash
grep -rn '"/qa ' scripts/vps/ --include="*.sh"
# Results: 3 occurrences
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/pueue-callback.sh | 362 | `"/qa Проверь изменения после ${TASK_LABEL}"` — bug here |
| scripts/vps/qa-loop.sh | 65 | `"-p" "/qa ${SPEC_ID}"` — correct usage |
| scripts/vps/night-reviewer.sh | (via claude CLI) | `"/audit night"` — different skill |

### Step 4: CHECKLIST — Mandatory folders

- [x] `scripts/vps/tests/` — 5 test files found (test_db.py, test_notify.py, test_approve_handler.py, test_inbox_processor.bats, conftest.py)
- [ ] `db/migrations/` — N/A (no migrations dir, schema.sql is the migration)
- [ ] `ai/glossary/` — N/A for this feature (VPS scripts, not domain code)

No existing test for:
- qa-loop.sh dispatch correctness
- openclaw-artifact-scan.py QA file parsing
- End-to-end cycle (smoke test — explicitly requested)

### Step 5: DUAL SYSTEM check

**Break #3** touches data routing: `projects.json` → `db.seed_projects_from_json()` → `project_state.topic_id` → `notify.py`. Two consumers read topic_id:
- `notify.py` — for Telegram message routing
- `telegram-bot.py` — `get_project_by_topic()` for incoming message routing

Adding topic_id to projects.json and reseeding will make BOTH routing directions work. No conflict.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| scripts/vps/pueue-callback.sh | 408 | Break #1: QA dispatch sends wrong prompt | modify |
| scripts/vps/openclaw-artifact-scan.py | 118 | Break #2: QA file pattern matching | modify |
| scripts/vps/projects.json | 45 | Break #3: missing topic_id for 5 projects | modify |
| scripts/vps/tests/test_db.py | 230 | Existing tests (read-only for impact) | read-only |
| scripts/vps/qa-loop.sh | 114 | QA dispatch flow (read-only — already correct) | read-only |
| scripts/vps/notify.py | 242 | topic_id guard (read-only — behavior is correct) | read-only |
| scripts/vps/db.py | 476 | DB layer (read-only — COALESCE already correct) | read-only |
| scripts/vps/tests/test_qa_cycle.py | 0 | NEW: smoke test for full cycle | create |

**Total:** 3 modify + 1 create + 4 read-only, ~900 LOC modified/created

---

## Reuse Opportunities

### Import (use as-is)

- `db.set_project_topic(project_id, topic_id, chat_id)` — use in migration/setup script to bind existing projects to topics
- `db.seed_projects_from_json()` — already idempotent with COALESCE; just add topic_id to projects.json entries

### Extend (subclass or wrap)

- `extract_status()` in `openclaw-artifact-scan.py:29` — extend to handle ISO-dated files that may lack `**Status:**` header (add fallback: scan for `passed`/`failed` keywords in filename)
- QA report write block in `qa-loop.sh:87-104` — already writes structured format; the fix is ensuring it's CALLED rather than bypassed

### Pattern (copy structure, not code)

- `scripts/vps/tests/test_db.py` — pytest pattern with `isolated_db` / `seed_project` fixtures; use same fixtures for smoke test
- `conftest.py` — reuse fixtures for new `test_qa_cycle.py`

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -10 -- scripts/vps/qa-loop.sh scripts/vps/openclaw-artifact-scan.py scripts/vps/notify.py scripts/vps/pueue-callback.sh scripts/vps/projects.json scripts/vps/orchestrator.sh
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-18 | 6441dbc | Ellevated | revert: remove fix(orchestrator): always dispatch reflect after autopilot |
| 2026-03-18 | e7d619d | Ellevated | fix(orchestrator): always dispatch reflect after autopilot, drop diary pending gate |
| 2026-03-18 | 1b358e4 | Ellevated | fix(orchestrator): enforce topic-scoped routing |
| 2026-03-17 | 86d056e | Ellevated | orchestrator: finalize north-star alignment |
| 2026-03-17 | 9462cc7 | Ellevated | openclaw: add hybrid artifact wake flow |

**Observation:** Активная разработка orchestrator прямо сегодня. Коммит `e7d619d` был reverted через `6441dbc` — это значит reflect-dispatch нестабилен, надо учитывать при добавлении smoke теста. Routing был зафиксирован в `1b358e4` — `notify.py`'s fail-closed guard уже корректен, но данные в БД ещё не обновлены.

---

## Concrete Fix Summary

### Fix #1 — pueue-callback.sh line 362

**File:** `/home/dld/projects/dld/scripts/vps/pueue-callback.sh`

Current (line 362):
```bash
"/qa Проверь изменения после ${TASK_LABEL}"
```

Change to:
```bash
"/qa ${TASK_LABEL}"
```

`TASK_LABEL` at this point is already the spec ID (e.g. `FTR-702`). The `/qa` skill receives the spec ID directly and can locate `ai/features/FTR-702*.md`.

**Note:** There is also a conceptual mismatch — the callback dispatches QA via `run-agent.sh` (claude agent with `/qa` skill), while `qa-loop.sh` is a separate wrapper that calls claude with `/qa SPEC_ID`. The callback path does NOT use `qa-loop.sh` — it calls `run-agent.sh` directly. The `/qa` skill inside claude must be self-sufficient in finding the spec file. Passing the spec ID (`TASK_LABEL`) directly is the correct fix.

### Fix #2 — openclaw-artifact-scan.py lines 79-88

**File:** `/home/dld/projects/dld/scripts/vps/openclaw-artifact-scan.py`

The `[:4].isdigit()` filter PASSES both formats. The real issue is `extract_status()` returns `"unknown"` for files without `**Status:**` header (e.g. manually-written QA files or agent-written files with different structure).

Two sub-fixes needed:
1. Make `extract_status()` also scan for bare `passed`/`failed`/`PASSED`/`FAILED` words as fallback
2. Make `artifact_rel` pointer in pueue-callback.sh more precise: use the file written by this specific task run, not just `tail -1` of all QA files

For Fix #2 in callback (line 302-304), the `find` command should filter by modification time since task started, or the qa-loop.sh / agent should write a sentinel file with a known name that the callback can reference.

### Fix #3 — projects.json

**File:** `/home/dld/projects/dld/scripts/vps/projects.json`

Add `topic_id` for all 5 missing projects. **Required data from human operator:**
- `awardybot` → topic_id = ?
- `dowry` → topic_id = ?
- `dowry-mc` → topic_id = ?
- `nexus` → topic_id = ?
- `plpilot` → topic_id = ?

These are Telegram forum topic thread IDs — must be obtained from the actual Telegram group. Cannot be inferred from code.

Alternatively, `set_project_topic()` in `db.py:274` can be called directly for each project without touching projects.json (if the operator knows the topic IDs but doesn't want to update json).

### Smoke Test — test_qa_cycle.py

**File:** `/home/dld/projects/dld/scripts/vps/tests/test_qa_cycle.py` (NEW)

Test: full cycle mock — seed project with topic_id → create inbox file → verify orchestrator would pick it up → verify notify.py routing works → verify artifact-scan returns structured output for qa-loop.sh written report.

Does NOT test the actual claude invocation (that's an integration test requiring live infra). Tests the wiring: projects.json → DB → routing → artifact naming.

---

## Risks

1. **Risk:** Fix #1 changes QA prompt from human-readable to spec ID — the `/qa` skill must handle spec ID as input (not just freeform text)
   **Impact:** If `/qa` skill doesn't support `"/qa FTR-702"` syntax, the agent gets a bare ID with no context and may still fail
   **Mitigation:** Check `.claude/skills/qa/SKILL.md` to confirm it accepts spec ID; if not, fix the skill prompt too

2. **Risk:** Fix #3 requires real Telegram topic IDs — these are operational data, not discoverable from code
   **Impact:** Without correct topic_ids, notifications remain silent even after the fix
   **Mitigation:** Spark spec must include a task for operator to provide topic IDs via `/addproject` Telegram wizard or direct DB update

3. **Risk:** Break #2 has two layers — `artifact_rel` pointer in callback AND `extract_status` parsing
   **Impact:** Even after fixing extract_status, if `artifact_rel` points to wrong file, OpenClaw gets wrong artifact summary
   **Mitigation:** Fix both: improve `extract_status` fallback AND tighten `artifact_rel` file selection in pueue-callback.sh

4. **Risk:** Reflect revert (6441dbc reverts e7d619d) — smoke test may hit the same instability
   **Impact:** Smoke test for full cycle (inbox → reflect) may be flaky if reflect dispatch is broken
   **Mitigation:** Scope smoke test to inbox → autopilot → qa_pending → QA pass only; exclude reflect from smoke test scope until that revert is resolved
