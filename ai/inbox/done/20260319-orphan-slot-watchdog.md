# Idea: 20260319-150500
**Source:** openclaw
**Route:** spark
**Status:** processing
---

Оркестратор зависает когда compute_slots в БД заняты задачами которых уже нет в pueue.
Это случается при рестарте сервисов, ARCH-161 миграции, любом ненормальном завершении.

**Решение:** watchdog в начале каждого цикла `orchestrator.py`.

```python
def release_orphan_slots():
    """Free compute slots whose pueue tasks are no longer running/queued."""
    running_ids = get_pueue_running_ids()  # set of int pueue_ids
    with get_db(immediate=True) as conn:
        rows = conn.execute(
            "SELECT slot_number, pueue_id FROM compute_slots WHERE pueue_id IS NOT NULL"
        ).fetchall()
        for row in rows:
            if row['pueue_id'] not in running_ids:
                conn.execute(
                    "UPDATE compute_slots SET project_id=NULL, pid=NULL, pueue_id=NULL, acquired_at=NULL "
                    "WHERE slot_number=?", (row['slot_number'],)
                )
                log.info("released orphan slot=%d pueue_id=%d", row['slot_number'], row['pueue_id'])
```

Вызывать в `process_all_projects()` перед основным циклом.

**SpecID:** BUG-162
