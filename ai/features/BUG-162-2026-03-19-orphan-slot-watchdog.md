# Feature: [BUG-162] Orphan Slot Watchdog — Release Stale compute_slots

**Status:** queued | **Priority:** P1 | **Date:** 2026-03-19

## Why

Оркестратор зависает когда `compute_slots` в БД заняты задачами, которых уже нет в pueue.
Это случается при рестарте сервисов, ARCH-161 миграции, любом ненормальном завершении.
`callback.py` не вызывается → слот остаётся заблокированным → `get_available_slots() == 0` →
orchestrator больше не диспатчит задачи.

## Context

- `compute_slots` таблица хранит `pueue_id` активной задачи (schema.sql:26-33)
- Слот занят когда `project_id IS NOT NULL`
- Освобождение — только через `callback.py` при нормальном завершении pueue task
- Если callback не вызывается (crash, SIGKILL, `pueue reset`, рестарт) → deadlock

---

## Scope

**In scope:**
- Функция `release_orphan_slots()` в `orchestrator.py` — сверка DB с pueue status
- Вспомогательная функция `get_occupied_slots()` в `db.py`
- Вызов watchdog в начале каждого цикла `main()` (до `sync_projects()`)
- Unit-тесты для обоих функций

**Out of scope:**
- TTL/lease-based expiry (YAGNI — добавим если watchdog окажется недостаточен)
- Heartbeat-механизм (требует изменений в run-agent.sh)
- Изменения в callback.py / schema.sql
- Рефакторинг `is_agent_running()` для reuse (follow-up)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?

- `db.get_available_slots()` ← `orchestrator.py:306` (scan_backlog) — affected positively
- `db.try_acquire_slot()` ← `orchestrator.py:270,319` — unaffected (new function, not modifying API)
- `db.release_slot()` ← `callback.py:273` — unaffected (watchdog uses same function)

### Step 2: DOWN — what depends on?

- `pueue` CLI (subprocess) — `pueue status --json`
- `sqlite3` stdlib — via `db.get_db(immediate=True)`
- `db.release_slot()` — existing, idempotent function

### Step 3: BY TERM — grep entire project

- `compute_slots` → 23 occurrences in scripts/vps/*.py — all read-only from our perspective
- `release_slot` → 3 occurrences (db.py def, callback.py call, test) — not modified
- `get_available_slots` → 2 occurrences — not modified, will return correct values post-watchdog

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/` — add test for `get_occupied_slots` and watchdog logic
- [ ] `db/migrations/` — N/A (no schema change)

### Verification

- [x] All found files added to Allowed Files
- [x] grep by old term = 0 (no term renames)

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `scripts/vps/orchestrator.py` — add `get_live_pueue_ids()` + `release_orphan_slots()` + call in `main()`
2. `scripts/vps/db.py` — add `get_occupied_slots()`
3. `scripts/vps/tests/test_db.py` — add tests for `get_occupied_slots()`
4. `scripts/vps/tests/test_orchestrator.py` — add tests for watchdog logic

**New files allowed:**

- `scripts/vps/tests/test_orchestrator.py` — if not exists, create for watchdog tests

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** orchestrator (scripts/vps/)
**Cross-cutting:** Reliability, fault recovery
**Data model:** `compute_slots` table (no schema changes)

---

## Approaches

### Approach 1: Proactive Watchdog (cross-reference pueue status) ✅

**Source:** [BullMQ Stalled Jobs](https://oneuptime.com/blog/post/2026-01-21-bullmq-stalled-jobs/view), [Semaphore UI #3681](https://github.com/semaphoreui/semaphore/issues/3681)
**Summary:** В начале каждого цикла вызывается `release_orphan_slots()` — получает множество live pueue IDs через `pueue status --json`, сравнивает с occupied slots в DB, освобождает orphans через `db.release_slot()`.
**Pros:** Быстрое обнаружение (~5 мин), точное (без false positives), нет изменений схемы, R2
**Cons:** Зависит от pueue CLI (handled: skip на ошибку)

### Approach 2: TTL / Lease Auto-Expiry

**Source:** [SQLite lease-heartbeat recovery](https://docsaid.org/en/blog/sqlite-lease-heartbeat-recovery)
**Summary:** Слоты с `acquired_at` старше N минут освобождаются автоматически.
**Pros:** Не зависит от pueue CLI
**Cons:** TTL ≥90 мин = медленное обнаружение, false positive на длинных задачах

### Approach 3: Startup-only cleanup

**Source:** Devil scout Alternative 3
**Summary:** `release_orphan_slots()` только при старте оркестратора, не каждый цикл.
**Pros:** Минимальный risk, нет per-cycle overhead
**Cons:** Не покрывает mid-run orphans (pueue task killed externally while orchestrator runs)

### Selected: 1

**Rationale:** Cross-reference watchdog — промышленный стандарт (BullMQ, Temporal, Semaphore).
Быстрая реакция (≤5 мин vs 90+ мин TTL). Нет изменений схемы.
Devil scout: proceed with caution — критично вернуть `None` on pueue failure.

---

## Design

### Architecture

```
main() poll loop
    ↓ (start of cycle)
release_orphan_slots()
    ├── get_live_pueue_ids() → set[int] | None
    │   └── subprocess: pueue status --json
    ├── db.get_occupied_slots() → list[dict]
    └── for each orphan: db.release_slot(pueue_id)
    ↓
sync_projects()
    ↓
dispatch_night_review()
    ↓
for proj in get_all_projects():
    process_project(pid, pdir)
```

### Implementation Details

**1. `get_live_pueue_ids()` in orchestrator.py:**

```python
def get_live_pueue_ids() -> set[int] | None:
    """Return set of pueue task IDs that are Running or Queued.

    Returns None on failure (pueue unreachable) — caller must skip watchdog.
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            log.warning("pueue status exit %d: %s", r.returncode, r.stderr[:200])
            return None
        data = json.loads(r.stdout)
        live: set[int] = set()
        for task_id_str, task in data.get("tasks", {}).items():
            status = task.get("status", "")
            if isinstance(status, dict) and ("Running" in status or "Locked" in status):
                live.add(int(task_id_str))
            elif status in ("Queued", "Stashed", "Paused"):
                live.add(int(task_id_str))
        return live
    except Exception as exc:
        log.warning("get_live_pueue_ids failed: %s", exc)
        return None
```

**Key decisions (Devil scout):**
- Returns `None` on failure, NOT empty set — prevents false positive mass release
- Checks `r.returncode != 0` — catches pueue daemon down
- Includes Stashed/Paused in live set — prevents release on manual operator hold
- `Locked` is pueue v4 synonym for Queued in some contexts

**2. `release_orphan_slots()` in orchestrator.py:**

```python
def release_orphan_slots() -> int:
    """Release compute slots whose pueue tasks no longer exist.

    Called at the start of each main() cycle to prevent deadlocks
    after service restart or abnormal termination (BUG-162).

    Returns count of released slots. Returns 0 if pueue unreachable.
    """
    live_ids = get_live_pueue_ids()
    if live_ids is None:
        return 0  # pueue unreachable — skip this cycle

    occupied = db.get_occupied_slots()
    if not occupied:
        return 0

    released = 0
    for slot in occupied:
        pueue_id = slot["pueue_id"]
        if pueue_id not in live_ids:
            project_id = db.release_slot(pueue_id)
            log.warning(
                "watchdog: released orphan slot=%d project=%s pueue_id=%d acquired_at=%s",
                slot["slot_number"], project_id or slot.get("project_id"),
                pueue_id, slot.get("acquired_at", "unknown"),
            )
            released += 1

    if released:
        log.info("watchdog: released %d orphan slot(s) total", released)
    return released
```

**3. `get_occupied_slots()` in db.py:**

```python
def get_occupied_slots() -> list[dict]:
    """Return all compute_slots with non-NULL pueue_id."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT slot_number, provider, project_id, pueue_id, acquired_at "
            "FROM compute_slots WHERE pueue_id IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]
```

**4. Integration in `main()`:**

```python
while not _stop.is_set():
    try:
        release_orphan_slots()  # BUG-162: clean stale slots before dispatch
        sync_projects()
        dispatch_night_review()
        for proj in db.get_all_projects():
            ...
```

---

## Implementation Plan

### Research Sources

- [BullMQ Stalled Jobs](https://oneuptime.com/blog/post/2026-01-21-bullmq-stalled-jobs/view) — cross-reference watchdog pattern
- [SQLite Atomic Claims](https://docsaid.org/en/blog/sqlite-job-queue-atomic-claim) — BEGIN IMMEDIATE + CAS guard
- [Semaphore UI #3681](https://github.com/semaphoreui/semaphore/issues/3681) — orphaned task slot reaper

### Task 1: Add `get_occupied_slots()` to db.py

**Type:** code
**Files:**
  - modify: `scripts/vps/db.py`
**Pattern:** Existing `get_available_slots` at db.py:167 — same SELECT pattern
**Acceptance:** Function returns list[dict] with slot_number, provider, project_id, pueue_id, acquired_at. Returns empty list when no slots occupied. Update module docstring.

### Task 2: Add `get_live_pueue_ids()` and `release_orphan_slots()` to orchestrator.py

**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.py`
**Pattern:** `is_agent_running()` at orchestrator.py:100 for pueue status parsing
**Acceptance:**
  - `get_live_pueue_ids()` returns `None` on failure (not empty set)
  - `release_orphan_slots()` skips when pueue unreachable
  - Called once at start of main loop cycle, before `sync_projects()`
  - Logs at WARNING level with slot details for forensics

### Task 3: Unit tests for watchdog

**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_db.py`
  - create: `scripts/vps/tests/test_orchestrator.py`
**Pattern:** Existing `TestSlotAcquisition` in test_db.py
**Acceptance:** Tests cover: pueue failure → no release, genuine orphan → released, all running → no release, callback+watchdog race → idempotent

### Execution Order

1 → 2 → 3

---

## Flow Coverage Matrix (REQUIRED)

| # | Flow Step | Covered by Task | Status |
|---|-----------|-----------------|--------|
| 1 | Orchestrator starts poll cycle | Task 2 (call in main) | ✓ |
| 2 | Watchdog queries pueue for live tasks | Task 2 (get_live_pueue_ids) | ✓ |
| 3 | Watchdog queries DB for occupied slots | Task 1 (get_occupied_slots) | ✓ |
| 4 | Watchdog releases orphan slots | Task 2 (release_orphan_slots) | ✓ |
| 5 | Orchestrator proceeds to dispatch | - | existing |
| 6 | Available slots correctly updated | - | existing (get_available_slots) |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Pueue call fails → no slots released | pueue status returns non-zero or raises exception | `release_orphan_slots()` returns 0, no DB changes | deterministic | devil DA-1 | P0 |
| EC-2 | All tasks Running → no slots released | DB slots with pueue_id 5,6; pueue shows both Running | `release_orphan_slots()` returns 0 | deterministic | devil DA-2 | P0 |
| EC-3 | Genuine orphan → slot released | DB slot with pueue_id=99; pueue has no task 99 | Slot released, function returns 1, log.warning emitted | deterministic | devil DA-3 | P0 |
| EC-4 | Pueue returns empty tasks (valid response) | pueue exit 0, tasks={}, DB has 1 occupied slot | Slot released (empty live set but pueue succeeded) | deterministic | devil DA-8 | P0 |
| EC-5 | No occupied slots → fast no-op | DB all slots free | Function returns 0, no pueue call errors | deterministic | devil DA-9 | P2 |
| EC-6 | Queued task not released | DB slot pueue_id=10; pueue shows task 10 as "Queued" | Slot NOT released | deterministic | devil DA-7 | P1 |
| EC-7 | get_occupied_slots returns correct data | DB has 2 slots occupied, 2 free | Returns exactly 2 dicts with correct fields | deterministic | codebase | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-8 | Slot acquired via try_acquire_slot, pueue task finished | Run release_orphan_slots with pueue returning no tasks | Slot freed, get_available_slots increases by 1 | integration | codebase | P0 |

### Coverage Summary

- Deterministic: 7 | Integration: 1 | LLM-Judge: 0 | Total: 8 (min 3 ✓)

### TDD Order

1. EC-7 (get_occupied_slots) → implement db.py
2. EC-1 (pueue failure) → implement get_live_pueue_ids with None return
3. EC-2, EC-6 (no false positives) → implement watchdog core
4. EC-3, EC-4 (genuine orphans) → implement release logic
5. EC-8 (integration) → wire into main()

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | orchestrator.py imports clean | `python3 -c "import orchestrator"` from scripts/vps/ | exit 0 | 5s |
| AV-S2 | db.py imports clean | `python3 -c "import db"` from scripts/vps/ | exit 0 | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Watchdog releases orphan | Seed DB with occupied slot pueue_id=9999, no pueue tasks | Call release_orphan_slots() | Returns 1, slot freed |
| AV-F2 | Watchdog skips on pueue error | Mock pueue to fail | Call release_orphan_slots() | Returns 0, no DB changes |

### Verify Command (copy-paste ready)

```bash
# Smoke
cd /home/dld/projects/dld/scripts/vps && python3 -c "import orchestrator; import db; print('OK')"
# Unit tests
cd /home/dld/projects/dld && python3 -m pytest scripts/vps/tests/ -v -k "orphan or occupied"
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional

- [ ] `release_orphan_slots()` releases slots whose pueue tasks are gone
- [ ] `release_orphan_slots()` does NOT release slots when pueue CLI fails
- [ ] `release_orphan_slots()` does NOT release Running/Queued/Stashed/Paused tasks
- [ ] Watchdog called once per cycle at start of main loop
- [ ] All tasks from Implementation Plan completed

### Tests

- [ ] All eval criteria pass
- [ ] Coverage not decreased

### Technical

- [ ] Tests pass (python3 -m pytest scripts/vps/tests/)
- [ ] No regressions
- [ ] orchestrator.py stays under 400 LOC

---

## Autopilot Log

[Auto-populated by autopilot during execution]
