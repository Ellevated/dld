# Codebase Research — BUG-162: Orphan Slot Watchdog

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `db.release_slot` | scripts/vps/db.py:76 | Освобождает слот по pueue_id, возвращает project_id или None | Import directly — ровно то, что нужно вызвать для каждого orphan slot |
| `db.get_db` (context manager) | scripts/vps/db.py:23 | WAL-соединение с BEGIN IMMEDIATE для атомарных операций | Reuse для нового запроса SELECT occupied slots |
| `is_agent_running` pattern | scripts/vps/orchestrator.py:100 | Парсит `pueue status --json` → набор активных task ids | Pattern only — нужен аналог, возвращающий set всех running/queued IDs |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| `is_agent_running` | scripts/vps/orchestrator.py:100-115 | Вызывает `pueue status --json`, итерирует tasks, фильтрует по статусу | Нужно то же самое, но вернуть `set[int]` всех active pueue task IDs |
| `release_slot` by pueue_id | scripts/vps/db.py:76-91 | UPDATE compute_slots WHERE pueue_id = ? (IMMEDIATE) | Та же транзакция нужна в watchdog для каждого orphan |
| `callback.py` Step 1 | scripts/vps/callback.py:271-275 | Вызывает db.release_slot(pueue_id) в try/except | Pattern: watchdog делает то же, только в цикле |

**Recommendation:** Новая функция `release_orphan_slots()` в `orchestrator.py` реиспользует паттерн `is_agent_running` для получения active IDs. Новая функция `get_occupied_slots()` добавляется в `db.py` (одна SQL-строка). `release_slot` используется as-is.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
# Command used:
grep -r "from.*db\|import db" scripts/vps/ --include="*.py"

# Results: 3 files
```

| File | Line | Usage |
|------|------|-------|
| scripts/vps/orchestrator.py | 26 | `import db` |
| scripts/vps/callback.py | 26 | `import db` |
| scripts/vps/tests/test_db.py | 21 | `import db` |

Добавление новой функции `get_occupied_slots()` в db.py не меняет существующий публичный API — только расширяет. Callers не затронуты.

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| sqlite3 (stdlib) | scripts/vps/db.py | `get_db()` context manager |
| pueue CLI | subprocess | `pueue status --json` |
| db module | scripts/vps/db.py | `get_occupied_slots()` (new), `release_slot()` |

### Step 3: BY TERM — Grep key terms

```bash
# Command used:
grep -rn "compute_slots\|release_slot\|get_available_slots" scripts/vps/ --include="*.py"

# Results: 23 occurrences
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/db.py | 51 | `def try_acquire_slot(...)` |
| scripts/vps/db.py | 59 | `SELECT slot_number FROM compute_slots WHERE provider = ? AND project_id IS NULL` |
| scripts/vps/db.py | 68 | `UPDATE compute_slots SET project_id = ?, pueue_id = ?` |
| scripts/vps/db.py | 76 | `def release_slot(pueue_id: int)` |
| scripts/vps/db.py | 80 | `SELECT slot_number, project_id FROM compute_slots WHERE pueue_id = ?` |
| scripts/vps/db.py | 87 | `UPDATE compute_slots SET project_id = NULL, pid = NULL, pueue_id = NULL` |
| scripts/vps/db.py | 167 | `def get_available_slots(provider: str)` |
| scripts/vps/db.py | 171 | `SELECT COUNT(*) as cnt FROM compute_slots WHERE provider = ? AND project_id IS NULL` |
| scripts/vps/orchestrator.py | 270 | `db.try_acquire_slot(project_id, provider, pueue_id)` |
| scripts/vps/orchestrator.py | 306 | `db.get_available_slots(provider) < 1` |
| scripts/vps/orchestrator.py | 319 | `db.try_acquire_slot(project_id, provider, pueue_id)` |
| scripts/vps/callback.py | 273 | `db.release_slot(pueue_id)` |
| scripts/vps/tests/test_db.py | 119-165 | TestSlotAcquisition — 7 test methods |

### Step 4: CHECKLIST — Mandatory folders

- [x] `tests/**` — scripts/vps/tests/test_db.py (192 LOC). Нужно добавить `TestOrphanWatchdog` класс
- [ ] `db/migrations/**` — N/A (orchestrator использует SQLite, schema.sql, не миграции)
- [ ] `ai/glossary/**` — N/A (orchestrator-domain не имеет glossary)

### Step 5: DUAL SYSTEM check

N/A — не меняется источник данных. Watchdog читает из той же compute_slots таблицы и использует тот же release_slot механизм что и callback.py.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| scripts/vps/orchestrator.py | 386 | Main loop daemon | modify — добавить `release_orphan_slots()` + вызов в `main()` |
| scripts/vps/db.py | 359 | SQLite helpers | modify — добавить `get_occupied_slots()` |
| scripts/vps/tests/test_db.py | 192 | Unit tests for db.py | modify — добавить тест для `get_occupied_slots` |
| scripts/vps/schema.sql | 70 | DB schema | read-only — compute_slots уже содержит нужные колонки |
| scripts/vps/callback.py | 342 | Pueue callback | read-only — release_slot там уже работает корректно |

**Total:** 5 files (3 modify, 2 read-only), 1349 LOC

---

## Reuse Opportunities

### Import (use as-is)
- `db.release_slot(pueue_id)` — полностью подходит для освобождения каждого orphan-слота. BEGIN IMMEDIATE, транзакционно, возвращает project_id для логирования.
- `db.get_db(immediate=True)` — context manager для нового `get_occupied_slots()` query.

### Extend (subclass or wrap)
- N/A

### Pattern (copy structure, not code)
- `is_agent_running()` в orchestrator.py:100-115 — паттерн вызова `pueue status --json` + парсинг tasks dict. Watchdog использует тот же вызов, но возвращает `set[int]` (все active pueue IDs) вместо bool. Нужно учесть статусы: Running, Queued (Locked в pueue v4 = Queued).
- `callback.py` Step 1 (try/except вокруг release_slot) — паттерн fault-tolerant освобождения слота.

---

## Git Context

### Recent Changes to Affected Areas

```bash
# Command used:
git log --oneline -- scripts/vps/orchestrator.py scripts/vps/db.py
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-18 | 6c18d02 | Ellevated | refactor(orchestrator): radical rewrite — Python replaces bash + Telegram (ARCH-161) |
| 2026-03-18 | dc369dc | Ellevated | chore: ARCH-161 cleanup — remove legacy files, update refs, drop Telegram deps |

**Observation:** ARCH-161 был выполнен вчера (2026-03-18). Именно при такой радикальной переписке compute_slots могли остаться с grязными pueue_id от старых bash-задач. Это подтверждает, что watchdog нужен сейчас.

---

## Design Notes (для имплементации)

### Новая функция в db.py

```python
def get_occupied_slots() -> list[dict]:
    """Return all compute_slots with non-NULL pueue_id."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT slot_number, provider, project_id, pueue_id "
            "FROM compute_slots WHERE pueue_id IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]
```

### Новая функция в orchestrator.py

```python
def release_orphan_slots() -> int:
    """Release compute slots whose pueue_id no longer exists in pueue.

    Called at the start of each main() cycle to prevent deadlocks after
    service restart or abnormal termination (ARCH-161, BUG-162).

    Returns: count of released slots.
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(r.stdout)
        active_ids: set[int] = set()
        for task_id, task in data.get("tasks", {}).items():
            status = task.get("status", "")
            # Running is dict: {"Running": {...}}, Queued is "Queued" string
            if isinstance(status, dict) and ("Running" in status or "Locked" in status):
                active_ids.add(int(task_id))
            elif status in ("Queued",):
                active_ids.add(int(task_id))
    except Exception as exc:
        log.warning("release_orphan_slots: pueue status failed: %s", exc)
        return 0

    occupied = db.get_occupied_slots()
    released = 0
    for slot in occupied:
        if slot["pueue_id"] not in active_ids:
            project_id = db.release_slot(slot["pueue_id"])
            log.warning(
                "orphan slot released: slot=%d project=%s pueue_id=%d",
                slot["slot_number"], project_id, slot["pueue_id"],
            )
            released += 1

    if released:
        log.info("watchdog: released %d orphan slot(s)", released)
    return released
```

### Место вызова в main()

В функции `main()` в начале цикла, до `sync_projects()`:

```python
while not _stop.is_set():
    try:
        release_orphan_slots()   # <- добавить здесь
        sync_projects()
        dispatch_night_review()
        ...
```

### Важный нюанс: статусы pueue

Из кода `is_agent_running()` (orchestrator.py:111): Running приходит как dict `{"Running": {...}}`. Queued приходит как строка `"Queued"`. Нужно проверить оба.

---

## Risks

1. **Risk:** pueue status --json недоступен (pueued не запущен)
   **Impact:** watchdog вернёт 0, не освободит слоты — но это безопасно, не хуже текущего состояния
   **Mitigation:** try/except уже в дизайне, логируем warning и возвращаем 0

2. **Risk:** Race condition — watchdog видит задачу как orphan, но она только что была добавлена в pueue и ещё не стартовала
   **Impact:** Slot освобождается, затем задача запускается без слота — двойной dispatch
   **Mitigation:** pueue status возвращает Queued статус для задач в очереди. Если проверять И Running И Queued, race window отсутствует. В дизайне выше оба статуса включены в active_ids.

3. **Risk:** db.py сейчас не экспортирует `get_occupied_slots` в module docstring
   **Impact:** Незначительно — нужно обновить docstring в заголовке db.py
   **Mitigation:** Добавить в "Used by" строку при имплементации
