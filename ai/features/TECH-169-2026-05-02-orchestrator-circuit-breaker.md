---
id: TECH-169
type: TECH
status: queued
priority: P0
risk: R1
created: 2026-05-02
---

# TECH-169 — Orchestrator circuit-breaker on mass-demote

**Status:** blocked
**Blocked Reason:** no_implementation_commits
**Priority:** P0
**Risk:** R1 (затрагивает callback и orchestrator decision flow)

---

## Problem

Если завтра в `callback.py` появится regression (regex-tweak, refactor, неудачный merge) — за 1-2 часа автомат может перевернуть 50+ спек в `blocked`. Это **обратимо в принципе** (status-fix руками + git revert), но трудоёмко: придётся пройти 50 спек по 5 проектам, локально править, форсить через operator-mode.

**Live precedent (02.05):** TECH-166 v1 deploy в 22:47 — за следующие 24h в логах callback мог демоутить любую спеку без heading-варианта, плюс ARCH-176a/b/c/d на wb, плюс кучу awardybot. Если бы ничего не сдерживало — масштаб был бы больше.

**Корень:** Callback fires per-task в pueue без global rate limit. Нет signal'а "что-то идёт не так глобально, остановись".

---

## Goal

**Circuit-breaker** на уровне callback'а:

1. Каждый demote-действие (target=`done` → `blocked` через guard, или resync) пишется в `compute_slots`-adjacent table `callback_decisions`:
   ```
   id | timestamp | project_id | spec_id | verdict | reason | demoted: bool
   ```

2. **Трешхолд**: если в окне 10 минут количество `demoted=true` записей > **3** — circuit OPEN:
   - callback продолжает читать pueue results, но `verify_status_sync` no-op'ит для **всех** проектов.
   - В логе: `CIRCUIT_OPEN: N demotes in 10min, refusing further status mutations until reset`.
   - Telegram-алёрт через `event_writer.notify` (новый event-kind `circuit_breaker`).
   - Параллельно — pueue group `claude-runner` ставится на pause (`pueue group --pause claude-runner`), чтобы остановить генерацию новых задач.

3. **Reset**: ручной — оператор запускает `python3 scripts/vps/callback.py --reset-circuit`. Скрипт:
   - Чистит `callback_decisions` за последние 30 мин.
   - Пингует Telegram о reset.
   - Делает `pueue group --resume claude-runner`.

4. **Healing window**: после 30 мин без demote — circuit auto-closes. Защита от "забыли reset'нуть".

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/db.py`
- `scripts/vps/schema.sql`
- `scripts/vps/event_writer.py`
- `scripts/vps/orchestrator.py`
- `tests/integration/test_callback_circuit_breaker.py`
- `.claude/rules/dependencies.md`

---

## Tasks

1. **Schema**: новая таблица `callback_decisions(id, ts, project_id, spec_id, verdict, reason, demoted)` в `schema.sql`. Migration в `db.py::init_schema()`.
2. **db.py CRUD**: `record_decision()`, `count_demotes_since(min_ago: int)`, `clear_decisions(min_ago: int)`.
3. **Circuit state**: lightweight in-memory + DB-backed flag. `is_circuit_open()` — проверяет за каждый callback. Threshold константа.
4. **Wiring в `verify_status_sync`**: каждый demote → `record_decision(demoted=True)`. На входе — `if is_circuit_open(): log + return`.
5. **`event_writer.py`**: новый `notify_circuit_event(action, count, window_min)`.
6. **CLI**: `python3 callback.py --reset-circuit` flag.
7. **Pueue pause/resume**: subprocess вызовы из circuit-open и --reset-circuit.
8. **Auto-heal**: ленивый — `is_circuit_open()` дополнительно чекает "был ли demote в последние 30 мин"; если нет — auto-resume.
9. **Tests**: симулировать 4 demote'а подряд, проверить что 5-й no-op'ится; reset; auto-heal.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | После 4-х demote за <10мин circuit OPEN, 5-й demote no-op |
| EC-2 | deterministic | После reset — следующий demote проходит |
| EC-3 | deterministic | После 30мин без demote — auto-heal закрывает circuit |
| EC-4 | integration | Telegram event получен на open + reset (mocked event_writer) |
| EC-5 | integration | Pueue claude-runner group pauses на open, resumes на reset |
| EC-6 | deterministic | `callback_decisions` table растёт корректно, indexed по ts |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Threshold=3 слишком жёсткий — обычная legacy-зачистка триггерит false alarm | Counter учитывает только demote-with-reason, не любой sync. + Auto-heal 30мин. |
| Circuit OPEN в момент когда autopilot реально провалился — застревает blocked-цепочка | Operator получает Telegram, видит причину, делает reset. Это UX feature, не bug. |
| Pueue pause не сработает (binary missing) | callback продолжает no-op'ить — это safest default. Pause — best effort. |

---

## Drift Log

**Checked:** 2026-05-02 UTC
**Result:** no_drift

Все Allowed Files существуют, line-references из спека сверены с актуальным кодом:
- `scripts/vps/callback.py` — 1251 строка, `verify_status_sync` на 947, `main()` на 1123, импорт `db`/`event_writer` на 26-27.
- `scripts/vps/db.py` — 413 строк, `get_db()` на 43, `_ensure_migrations` на 23 (TECH-170 шаблон для миграций), CLI dispatch на 343.
- `scripts/vps/schema.sql` — 71 строка, последний `CREATE TABLE` на 56 (`night_findings`).
- `scripts/vps/event_writer.py` — 127 строк, `notify()` на 88, `main()` CLI на 100.
- `scripts/vps/orchestrator.py` — daemon, `_pueue_add` style на ~287, не модифицируется (только метаданные в dependencies.md).

Tests директорий нет — `tests/integration/test_callback_circuit_breaker.py` создаётся с нуля по шаблону `tests/integration/test_callback_no_impl_demote.py`.

---

## Implementation Plan

### Task 1: Schema — `callback_decisions` table

**Files:**
- Modify: `scripts/vps/schema.sql:71` (append after `night_findings`)
- Modify: `scripts/vps/db.py:23-40` (extend `_ensure_migrations`)

**Context:** Persistent decision log for circuit-breaker. Append-only, indexed by `ts` for window queries. Migration is idempotent so existing prod DBs upgrade on first `get_db()` call after deploy.

**Step 1: Add table to `schema.sql`**

Append after line 71 (end of file):

```sql

-- TECH-169: Callback decision audit for circuit-breaker
CREATE TABLE IF NOT EXISTS callback_decisions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    project_id   TEXT NOT NULL,
    spec_id      TEXT,
    verdict      TEXT NOT NULL,        -- 'demote' | 'sync' | 'noop' | 'circuit_open'
    reason       TEXT,
    demoted      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_callback_decisions_ts
    ON callback_decisions(ts);

CREATE INDEX IF NOT EXISTS idx_callback_decisions_demoted_ts
    ON callback_decisions(demoted, ts);
```

**Step 2: Extend runtime migration in `db.py:23-40`**

Replace `_ensure_migrations` body to also create the table on existing DBs:

```python
def _ensure_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent runtime migrations. Process-cached after first success.

    TECH-170: add task_log.branch column for feature-branch awareness.
    TECH-169: add callback_decisions table + indexes.
    """
    global _MIGRATIONS_APPLIED
    if _MIGRATIONS_APPLIED:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(task_log)").fetchall()}
    if "branch" not in cols:
        try:
            conn.execute("ALTER TABLE task_log ADD COLUMN branch TEXT")
        except sqlite3.OperationalError:
            pass
    # TECH-169: callback_decisions table — idempotent CREATE
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS callback_decisions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),"
            "project_id TEXT NOT NULL,"
            "spec_id TEXT,"
            "verdict TEXT NOT NULL,"
            "reason TEXT,"
            "demoted INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_callback_decisions_ts "
            "ON callback_decisions(ts)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_callback_decisions_demoted_ts "
            "ON callback_decisions(demoted, ts)"
        )
    except sqlite3.OperationalError:
        pass
    _MIGRATIONS_APPLIED = True
```

**Acceptance:**
- [ ] `sqlite3 :memory: < scripts/vps/schema.sql` succeeds.
- [ ] On a pre-existing DB without the table, first `db.get_db()` call creates it.
- [ ] `PRAGMA index_list(callback_decisions)` returns both indexes.

---

### Task 2: db.py CRUD — `record_decision`, `count_demotes_since`, `clear_decisions`

**Files:**
- Modify: `scripts/vps/db.py` (add 3 functions before `seed_projects_from_json` ~line 231)

**Context:** Thin SQL layer. Window queries use SQLite `datetime('now', '-N minutes')` for portability.

**Step 1: Add functions**

Insert after `get_task_by_pueue_id()` (line 228), before `seed_projects_from_json`:

```python
def record_decision(
    project_id: str,
    spec_id: Optional[str],
    verdict: str,
    reason: Optional[str],
    demoted: bool,
) -> int:
    """Insert one callback decision row. Returns row id.

    TECH-169: Used by callback.verify_status_sync to feed the circuit-breaker.
    `verdict` is one of: 'demote', 'sync', 'noop', 'circuit_open'.
    """
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, spec_id, verdict, reason, 1 if demoted else 0),
        )
        return cursor.lastrowid


def count_demotes_since(min_ago: int) -> int:
    """Count callback_decisions rows with demoted=1 in the last `min_ago` minutes.

    TECH-169: Window query for circuit-breaker threshold check.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM callback_decisions "
            "WHERE demoted = 1 "
            "AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
            (f"-{int(min_ago)} minutes",),
        ).fetchone()
        return int(row["cnt"]) if row else 0


def clear_decisions(min_ago: int) -> int:
    """Delete callback_decisions rows newer than `min_ago` minutes. Returns deleted count.

    TECH-169: Used by --reset-circuit to flush the recent window.
    """
    with get_db(immediate=True) as conn:
        cursor = conn.execute(
            "DELETE FROM callback_decisions "
            "WHERE ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
            (f"-{int(min_ago)} minutes",),
        )
        return cursor.rowcount or 0
```

**Acceptance:**
- [ ] `record_decision("p", "TECH-1", "demote", "no_impl", True)` returns int > 0.
- [ ] After 4 inserts with `demoted=True`, `count_demotes_since(10)` == 4.
- [ ] `clear_decisions(30)` removes inserted rows; subsequent `count_demotes_since(10)` == 0.

---

### Task 3: Circuit-breaker module in `callback.py`

**Files:**
- Modify: `scripts/vps/callback.py` (add new section after line 908 `is_merged_to_develop`, before `_emit_audit` line 913)

**Context:** Self-contained block of constants + 4 helpers (`is_circuit_open`, `_pueue_pause`, `_pueue_resume`, `_circuit_state_label`). Uses Task-2 db helpers + Task-5 event helper. Threshold/window are module-level constants for testability.

**Step 1: Add constants and helpers**

Insert at line 909 (between `is_merged_to_develop` and `# ---` separator):

```python
# --- TECH-169: Circuit-breaker -----------------------------------------------

# Threshold: more than this many demotes within WINDOW_MIN → circuit OPEN.
CIRCUIT_THRESHOLD = 3
CIRCUIT_WINDOW_MIN = 10
# Healing: if there were no demotes in the last HEAL_MIN minutes, circuit
# auto-closes (lazy check inside is_circuit_open).
CIRCUIT_HEAL_MIN = 30
# Reset CLI clears decisions newer than this (matches HEAL_MIN by design).
CIRCUIT_RESET_CLEAR_MIN = 30
# Pueue group paused on OPEN / resumed on RESET.
CIRCUIT_PUEUE_GROUP = "claude-runner"


def is_circuit_open() -> bool:
    """Return True if circuit-breaker is currently OPEN.

    Logic:
      1. Count demotes in last CIRCUIT_WINDOW_MIN minutes.
      2. If count > CIRCUIT_THRESHOLD → OPEN.
      3. Auto-heal: if count == 0 over CIRCUIT_HEAL_MIN window → CLOSED
         (cheap because we just compared to 0 above; no extra query).

    Pure function over DB state — no in-memory flag (callback is short-lived
    per pueue completion).
    """
    try:
        recent = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
    except Exception as exc:  # noqa: BLE001 — callback must not crash
        log.warning("CIRCUIT: count_demotes_since failed: %s", exc)
        return False
    if recent > CIRCUIT_THRESHOLD:
        # Lazy auto-heal: if last 30 min were quiet, ignore stale window.
        try:
            heal = db.count_demotes_since(CIRCUIT_HEAL_MIN)
        except Exception:
            heal = recent
        if heal == 0:
            log.info("CIRCUIT: auto-heal — no demotes in %d min", CIRCUIT_HEAL_MIN)
            return False
        return True
    return False


def _pueue_pause(group: str = CIRCUIT_PUEUE_GROUP) -> bool:
    """Best-effort pause of a pueue group. Returns True on success.

    Never raises — pueue might be missing, socket mismatch, etc.
    """
    try:
        r = subprocess.run(
            ["pueue", "pause", "--group", group],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            log.warning("CIRCUIT: paused pueue group=%s", group)
            return True
        log.warning(
            "CIRCUIT: pause failed (rc=%s) stderr=%s",
            r.returncode,
            r.stderr.strip()[:200],
        )
        return False
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("CIRCUIT: pause subprocess error: %s", exc)
        return False


def _pueue_resume(group: str = CIRCUIT_PUEUE_GROUP) -> bool:
    """Best-effort resume of a pueue group. Returns True on success."""
    try:
        r = subprocess.run(
            ["pueue", "start", "--group", group],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            log.warning("CIRCUIT: resumed pueue group=%s", group)
            return True
        log.warning(
            "CIRCUIT: resume failed (rc=%s) stderr=%s",
            r.returncode,
            r.stderr.strip()[:200],
        )
        return False
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("CIRCUIT: resume subprocess error: %s", exc)
        return False


def _trip_circuit(project_id: str, spec_id: str | None, count: int) -> None:
    """Side-effects fired exactly once when circuit transitions to OPEN.

    1. Log structured warning.
    2. Record an explicit 'circuit_open' decision (NOT counted as demote).
    3. Notify via event_writer (Telegram-equivalent).
    4. Pause claude-runner pueue group (best-effort).
    """
    log.error(
        "CIRCUIT_OPEN: %d demotes in %d min, refusing further status mutations until reset",
        count,
        CIRCUIT_WINDOW_MIN,
    )
    try:
        db.record_decision(project_id, spec_id, "circuit_open",
                           f"threshold_exceeded:{count}/{CIRCUIT_WINDOW_MIN}min",
                           demoted=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record_decision(circuit_open) failed: %s", exc)
    try:
        event_writer.notify_circuit_event(
            action="open",
            count=count,
            window_min=CIRCUIT_WINDOW_MIN,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: notify_circuit_event(open) failed: %s", exc)
    _pueue_pause()


# -----------------------------------------------------------------------------
```

**Acceptance:**
- [ ] `is_circuit_open()` returns False on empty DB.
- [ ] After inserting 4 rows with `demoted=1, ts=now`, returns True.
- [ ] If those rows were inserted >30 min ago (auto-heal), returns False.
- [ ] `_pueue_pause()` returns False (not crash) when `pueue` binary missing.

---

### Task 4: Wire circuit-breaker into `verify_status_sync`

**Files:**
- Modify: `scripts/vps/callback.py:947-1093` (function body)

**Context:** Two integration points:
1. **Top of function** — if circuit OPEN, log + record `noop` decision + return early (no spec/backlog mutation).
2. **Right after demote decision** — when guard fires (`guard_reason` set, target flipped to `blocked`), record `decision(demoted=True)` AND check threshold; if just-tripped, fire `_trip_circuit`.

We also record `decision(demoted=False, verdict='sync')` for normal status-syncs and `verdict='demote'` for spec-authority guards (`spec_already_blocked`/`spec_already_done`) — but those are **not counted** as demotes (they merely realign backlog).

**Step 1: Add early-return at function entry (after line 967, after `project_id = Path(project_path).name`)**

```python
    # TECH-169: Circuit-breaker — refuse all status mutations when OPEN.
    if is_circuit_open():
        log.warning(
            "CIRCUIT_OPEN: skipping verify_status_sync(%s, target=%s) — circuit is open",
            spec_id, target,
        )
        try:
            db.record_decision(project_id, spec_id, "noop",
                               "circuit_open", demoted=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("CIRCUIT: record_decision(noop) failed: %s", exc)
        return
```

**Step 2: Record decision when impl-guard demotes (after line 1014 `target = "blocked"`)**

Modify the demote branch starting at line 1003 (`if not _has_implementation_commits(...)`) so that immediately after `target = "blocked"`:

```python
            target = "blocked"
            # TECH-169: feed circuit-breaker
            try:
                db.record_decision(project_id, spec_id, "demote",
                                   guard_reason, demoted=True)
                count = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
                if count > CIRCUIT_THRESHOLD:
                    _trip_circuit(project_id, spec_id, count)
            except Exception as exc:  # noqa: BLE001
                log.warning("CIRCUIT: record/check failed: %s", exc)
```

**Step 3: Record `sync`/`noop` decisions for non-demote paths (NOT counted)**

a) Inside the two `_emit_audit` blocks at lines 1033 and 1048 (spec-authority short-circuits), add a `record_decision(verdict='sync', demoted=False)` call before the existing `_emit_audit`:

```python
            try:
                db.record_decision(project_id, spec_id, "sync",
                                   "spec_already_blocked", demoted=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("CIRCUIT: record_decision failed: %s", exc)
```

(and `"spec_already_done"` for the second branch)

b) At the final exit of the function (before `_git_commit_push` line 1093), add:

```python
    try:
        db.record_decision(project_id, spec_id,
                           "sync" if fixes else "noop",
                           final_reason, demoted=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record_decision failed: %s", exc)
```

**Acceptance:**
- [ ] After 3 demotes, the 4th demote still fires (threshold is `> 3`, i.e. 4th is the trip).
- [ ] After 4 demotes, `verify_status_sync` next call returns immediately, spec/backlog unchanged.
- [ ] `callback_decisions` has rows: 4× verdict=demote demoted=1, 1× verdict=circuit_open demoted=0, then noop rows for subsequent calls.
- [ ] `spec_already_blocked` short-circuit records `demoted=0` — does NOT contribute to threshold.

---

### Task 5: `event_writer.notify_circuit_event`

**Files:**
- Modify: `scripts/vps/event_writer.py` (add new function before `main()` line 100)

**Context:** Distinct event-kind so OpenClaw can route circuit alerts to a dedicated chat / colour. Uses `skill="circuit_breaker"`, `status=action` (`open`|`reset`|`heal`).

**Step 1: Add function**

Insert after `notify()` (line 98), before `main()`:

```python
def notify_circuit_event(action: str, count: int, window_min: int) -> None:
    """Emit a circuit-breaker event via the OpenClaw pipeline.

    TECH-169: distinct from regular notify() — uses skill='circuit_breaker'
    so OpenClaw can route to a dedicated alerts channel.

    Args:
        action: 'open' | 'reset' | 'heal'.
        count: Number of demotes that triggered (or 0 for reset/heal).
        window_min: Window minutes used in threshold calc.
    """
    # Use SCRIPT_DIR as project_path so the event lands in scripts/vps/
    # ai/openclaw/pending-events/ — separate from per-project pipelines.
    project_path = str(Path(__file__).resolve().parent)
    if action == "open":
        message = (
            f"CIRCUIT_OPEN: {count} demotes in {window_min} min — "
            f"callback halted, claude-runner paused. "
            f"Run `python3 callback.py --reset-circuit` to resume."
        )
        status = "failed"
    elif action == "reset":
        message = (
            "CIRCUIT_RESET: operator reset — decisions cleared, "
            "claude-runner resumed."
        )
        status = "done"
    elif action == "heal":
        message = f"CIRCUIT_HEAL: auto-closed after {window_min} min idle."
        status = "done"
    else:
        message = f"circuit event: {action}"
        status = "done"
    notify(project_path, "circuit_breaker", status, message, "")
```

**Acceptance:**
- [ ] `notify_circuit_event("open", 4, 10)` writes a JSON file to `scripts/vps/ai/openclaw/pending-events/`.
- [ ] File contains `"skill": "circuit_breaker"` and the trigger count in `message`.
- [ ] `notify_circuit_event("reset", 0, 10)` works (no exception on count=0).

---

### Task 6: CLI flag `--reset-circuit`

**Files:**
- Modify: `scripts/vps/callback.py:1123-1247` (`main()`)

**Context:** Operator-only manual reset. Triggered via `python3 callback.py --reset-circuit`. Independent of the pueue-callback signature (which uses positional `<id> <group> <result>`).

**Step 1: Add a dispatch branch at the top of `main()`**

Replace lines 1124-1129 (start of `try` block, before pueue arg parsing):

```python
def main() -> None:
    """Main callback entry point. ALWAYS exits 0.

    Two modes:
      • Pueue callback: argv = [pueue_id, group, result]  — fired by daemon.
      • Operator CLI:   argv = ['--reset-circuit']        — manual reset.
    """
    try:
        _load_env()
        _setup_logging()

        # TECH-169: operator CLI mode
        if len(sys.argv) > 1 and sys.argv[1] == "--reset-circuit":
            _reset_circuit_cli()
            return

        pueue_id = sys.argv[1] if len(sys.argv) > 1 else "0"
        group = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        result = sys.argv[3] if len(sys.argv) > 3 else "unknown"
        ...
```

**Step 2: Add `_reset_circuit_cli` helper above `main()` (after `_trip_circuit` from Task 3)**

```python
def _reset_circuit_cli() -> None:
    """Operator-triggered circuit reset.

    Steps:
      1. Clear callback_decisions newer than CIRCUIT_RESET_CLEAR_MIN.
      2. Resume claude-runner pueue group.
      3. Send reset event (Telegram-equivalent).
    """
    try:
        deleted = db.clear_decisions(CIRCUIT_RESET_CLEAR_MIN)
        log.warning("CIRCUIT_RESET: cleared %d decision row(s)", deleted)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT_RESET: clear_decisions failed: %s", exc)
    _pueue_resume()
    try:
        event_writer.notify_circuit_event(action="reset", count=0,
                                          window_min=CIRCUIT_WINDOW_MIN)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT_RESET: notify failed: %s", exc)
    print(f"circuit reset: cleared decisions, resumed {CIRCUIT_PUEUE_GROUP}")
```

**Acceptance:**
- [ ] `python3 scripts/vps/callback.py --reset-circuit` exits 0.
- [ ] After reset, `count_demotes_since(30)` == 0.
- [ ] Reset event JSON appears in `scripts/vps/ai/openclaw/pending-events/`.
- [ ] Pueue resume invoked (best-effort — no failure even if pueue absent).

---

### Task 7: Integration tests — `tests/integration/test_callback_circuit_breaker.py`

**Files:**
- Create: `tests/integration/test_callback_circuit_breaker.py`

**Context:** Real fs + real git + real sqlite, per ADR-013. Pueue subprocess + event_writer subprocess are stubbed via env-var/PATH redirect (NOT `unittest.mock` patches of business logic — the stubs replace external binaries with no-op shell scripts, simulating "real call into a temp file"). Mirrors the style of `test_callback_no_impl_demote.py`.

**Step 1: Test scaffold**

```python
"""TECH-169 — integration tests for callback circuit-breaker.

ADR-013: real fs + real git + real sqlite. External binaries (pueue,
openclaw) are replaced with temp shell stubs that record invocations
to a file — no mocks of business logic.

Covers EC-1..EC-6.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import db  # noqa: E402
import event_writer  # noqa: E402


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite DB seeded from schema.sql, isolated per test."""
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    # Reset migration cache so _ensure_migrations runs against this DB
    db._MIGRATIONS_APPLIED = False
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


@pytest.fixture
def stub_pueue_bin(tmp_path, monkeypatch):
    """Replace `pueue` on PATH with a stub that records argv to a file."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    log_file = tmp_path / "pueue-calls.log"
    stub = stub_dir / "pueue"
    stub.write_text(
        f'#!/usr/bin/env bash\necho "$@" >> "{log_file}"\nexit 0\n'
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_dir}:{os.environ['PATH']}")
    return log_file


@pytest.fixture
def stub_event_writer(tmp_path, monkeypatch):
    """Redirect notify_circuit_event output dir to tmp_path."""
    events_dir = tmp_path / "events"
    # event_writer derives path from __file__; instead patch write_event
    # to redirect via env. Cleanest: monkeypatch write_event to use tmp.
    real_write = event_writer.write_event

    def fake_write(project_path, skill, status, message, artifact_rel=""):
        return real_write(str(events_dir), skill, status, message, artifact_rel)

    monkeypatch.setattr(event_writer, "write_event", fake_write)
    monkeypatch.setattr(event_writer, "wake_openclaw", lambda: True)
    return events_dir


def _seed_state(project_id: str = "proj") -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_state (project_id, path) "
            "VALUES (?, ?)",
            (project_id, "/tmp/ignored"),
        )


# --- EC-1: 4-th demote no-ops -----------------------------------------------


def test_ec1_circuit_opens_after_threshold(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    # 3 demotes — circuit closed (threshold is > 3, so 3 == not yet open)
    for i in range(3):
        db.record_decision("proj", f"TECH-{i}", "demote", "no_impl", demoted=True)
    assert callback.is_circuit_open() is False

    # 4th demote — pushes count to 4 > 3 → OPEN
    db.record_decision("proj", "TECH-3", "demote", "no_impl", demoted=True)
    assert callback.is_circuit_open() is True


# --- EC-2: reset re-enables -------------------------------------------------


def test_ec2_reset_closes_circuit(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    for i in range(5):
        db.record_decision("proj", f"TECH-{i}", "demote", "no_impl", demoted=True)
    assert callback.is_circuit_open() is True

    callback._reset_circuit_cli()
    assert callback.is_circuit_open() is False
    # Pueue resume invoked
    log_text = stub_pueue_bin.read_text() if stub_pueue_bin.exists() else ""
    assert "start --group claude-runner" in log_text


# --- EC-3: 30-min idle auto-heals -------------------------------------------


def test_ec3_auto_heal_after_idle(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    # Insert 5 demotes with ts older than HEAL_MIN (31 min ago)
    with db.get_db() as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO callback_decisions "
                "(ts, project_id, spec_id, verdict, reason, demoted) "
                "VALUES (strftime('%Y-%m-%dT%H:%M:%SZ','now','-31 minutes'),"
                " ?, ?, ?, ?, ?)",
                ("proj", f"TECH-{i}", "demote", "no_impl", 1),
            )
    # Window query for 10 min → 0 → not OPEN
    assert callback.is_circuit_open() is False


# --- EC-4: events emitted on open + reset -----------------------------------


def test_ec4_events_emitted(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    callback._trip_circuit("proj", "TECH-99", 4)
    # Reset
    callback._reset_circuit_cli()

    files = sorted(stub_event_writer.rglob("*.json"))
    assert len(files) >= 2
    bodies = "\n".join(f.read_text() for f in files)
    assert '"skill": "circuit_breaker"' in bodies
    assert "CIRCUIT_OPEN" in bodies
    assert "CIRCUIT_RESET" in bodies


# --- EC-5: pueue pause/resume invoked ---------------------------------------


def test_ec5_pueue_pause_on_open_resume_on_reset(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    callback._trip_circuit("proj", "TECH-99", 4)
    callback._reset_circuit_cli()

    log_text = stub_pueue_bin.read_text()
    assert "pause --group claude-runner" in log_text
    assert "start --group claude-runner" in log_text


# --- EC-6: callback_decisions table grows + indexed ------------------------


def test_ec6_decisions_table_shape(tmp_db):
    _seed_state("proj")
    for i in range(10):
        db.record_decision("proj", f"TECH-{i}", "demote", "no_impl", demoted=True)
    with db.get_db() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM callback_decisions").fetchone()[0]
        idx_rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='callback_decisions'"
        ).fetchall()
    assert cnt == 10
    idx_names = {r[0] for r in idx_rows}
    assert "idx_callback_decisions_ts" in idx_names
    assert "idx_callback_decisions_demoted_ts" in idx_names
```

**Step 2: Verify tests pass**

```bash
cd /home/dld/projects/dld-tech-169
python3 -m pytest tests/integration/test_callback_circuit_breaker.py -v
```

Expected: 6 PASSED.

**Acceptance:**
- [ ] All 6 tests pass against fresh checkout.
- [ ] No `unittest.mock.patch` on business logic — only `db.DB_PATH`, `event_writer.write_event` redirect, and `pueue` PATH stub.
- [ ] Tests are isolated — each gets its own `tmp_db`.

---

### Task 8: End-to-end verification through `verify_status_sync`

**Files:**
- Modify: `tests/integration/test_callback_circuit_breaker.py` (append)

**Context:** Tasks 1-7 build & unit-test the pieces. This adds a single end-to-end test that drives `verify_status_sync` 5× with a no-impl spec setup (mirrors `test_ec8_demote_when_no_impl_commits` from existing suite) and asserts:
- 1st-4th calls: spec demoted to `blocked`.
- 5th call: spec untouched, decision row `verdict='noop' reason='circuit_open'`.

**Step 1: Append helpers + test**

```python
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _make_project(tmp_path: Path, idx: int, spec_id: str) -> Path:
    repo = tmp_path / f"proj{idx}"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(
        f"# {spec_id}\n\n**Status:** in_progress\n\n"
        f"## Allowed Files\n\n- `src/x.py`\n\n## Tests\n"
    )
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n"
        f"| {spec_id} | demo | in_progress | P1 |\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_e2e_5th_call_is_noop_circuit_open(
    tmp_path, tmp_db, stub_pueue_bin, stub_event_writer, monkeypatch
):
    # Suppress real `git push` (no remote in tests)
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)

    # Build 4 separate projects, each triggers a demote (no-impl).
    repos = []
    for i in range(4):
        spec_id = f"TECH-{900 + i}"
        repo = _make_project(tmp_path, i, spec_id)
        with db.get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_state (project_id, path) "
                "VALUES (?, ?)",
                (f"proj{i}", str(repo)),
            )
            conn.execute(
                "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"proj{i}", f"autopilot-{spec_id}", "autopilot", "running", 100 + i),
            )
        time.sleep(1.1)
        repos.append((repo, spec_id, 100 + i))

    # Calls 1-4: demote each (count climbs 1..4). After call 4, circuit OPEN.
    for repo, spec_id, pid in repos:
        callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=pid)

    # All 4 specs demoted
    for repo, spec_id, _ in repos:
        spec_text = (repo / "ai" / "features" / f"{spec_id}.md").read_text()
        assert "**Status:** blocked" in spec_text

    # Now circuit is OPEN. 5th call (any project) should no-op.
    repo5 = _make_project(tmp_path, 99, "TECH-905")
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_state (project_id, path) "
            "VALUES (?, ?)",
            ("proj99", str(repo5)),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("proj99", "autopilot-TECH-905", "autopilot", "running", 199),
        )
    time.sleep(1.1)
    # No impl commit on this repo either — would demote, except circuit OPEN.
    callback.verify_status_sync(str(repo5), "TECH-905", target="done", pueue_id=199)

    spec_text = (repo5 / "ai" / "features" / "TECH-905.md").read_text()
    # NOT demoted — circuit stopped the mutation
    assert "**Status:** in_progress" in spec_text
    assert "**Status:** blocked" not in spec_text

    # Decision recorded as noop:circuit_open
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT verdict, reason FROM callback_decisions "
            "WHERE spec_id = 'TECH-905'"
        ).fetchall()
    assert any(r[0] == "noop" and r[1] == "circuit_open" for r in rows)
```

**Acceptance:**
- [ ] All 4 specs in calls 1-4 are demoted to `blocked`.
- [ ] 5th spec stays `in_progress` (circuit OPEN intercepted).
- [ ] `callback_decisions` has a `verdict='noop' reason='circuit_open'` row for the 5th spec.

---

### Task 9: Update `dependencies.md`

**Files:**
- Modify: `.claude/rules/dependencies.md` (sections for `db.py`, `callback.py`, `event_writer.py`)

**Context:** Document new public API surface: `db.record_decision/count_demotes_since/clear_decisions`, `event_writer.notify_circuit_event`, callback CLI flag `--reset-circuit`.

**Step 1: Edit `db.py` "Used by" block (around line 25 of the file)**

Add row:

```
| callback.py | scripts/vps/callback.py | record_decision(), count_demotes_since(), clear_decisions() (TECH-169) |
```

**Step 2: Edit `callback.py` "Uses" block (around line 184-194)**

Add rows to the "Uses (→)" table:

```
| db.py | scripts/vps/db.py | record_decision(), count_demotes_since(), clear_decisions() (TECH-169) |
| event_writer.py | scripts/vps/event_writer.py | notify_circuit_event() (TECH-169) |
| pueue CLI | PATH | pueue pause/start --group claude-runner (TECH-169 circuit) |
```

**Step 3: Edit `event_writer.py` "Used by"**

Add row:

```
| callback.py | scripts/vps/callback.py | import: notify_circuit_event() (TECH-169) |
```

**Step 4: Append to "Last Update" table**

```
| 2026-05-02 | callback circuit-breaker (TECH-169): callback_decisions table, record_decision/count_demotes_since/clear_decisions (db.py), notify_circuit_event (event_writer.py), --reset-circuit CLI (callback.py) | autopilot |
```

**Acceptance:**
- [ ] All three module sections list the new public functions.
- [ ] "Last Update" row dated 2026-05-02 documents TECH-169 surface.

---

### Execution Order

```
Task 1 (schema)           → must be first — DB shape
Task 2 (db CRUD)          → depends on Task 1
Task 5 (event_writer)     → independent of 1/2 (can run parallel)
Task 3 (circuit module)   → depends on Task 2 + Task 5
Task 4 (wiring)           → depends on Task 3
Task 6 (CLI flag)         → depends on Task 3 + Task 5
Task 7 (unit-ish integration tests) → depends on Tasks 1-6
Task 8 (e2e test)         → depends on Task 4 + Task 6
Task 9 (dependencies.md)  → last, documentation
```

Linear path:
```
1 → 2 → 3 → 4 → 7
        ↘ 6 ↗
5 ────────────↗
                  ↘ 8 → 9
```

### Dependencies

- **Task 2** needs Task 1's table.
- **Task 3** uses Task 2's helpers + Task 5's `notify_circuit_event`.
- **Task 4** edits the same file as Task 3 (callback.py) — apply Task 3 patches first to avoid conflicts.
- **Task 6** adds CLI mode in `main()` of callback.py — must come after Task 3 (uses `_pueue_resume`, `CIRCUIT_RESET_CLEAR_MIN`).
- **Task 7** (EC-1..EC-6) tests pieces in isolation; Task 8 drives end-to-end through `verify_status_sync`.
- **Task 9** documents what landed; do last.

### Research Sources

None required — feature is self-contained over existing primitives (sqlite3, subprocess, pueue CLI). Pueue group pause/resume syntax verified against `pueue --help` (`pueue pause --group <name>` / `pueue start --group <name>` are stable since pueue 3.x; the project's setup-vps.sh already uses `pueue group add`).
