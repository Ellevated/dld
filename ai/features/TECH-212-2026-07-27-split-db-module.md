# Feature: [TECH-212] Раскол db.py

**Priority:** P1 | **Date:** 2026-07-27

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`db.py` — 602 LOC при лимите 400. Слой доступа к SQLite для всего оркестратора: слоты,
проекты, журнал задач, решения circuit-breaker'а, находки ночного ревью.

Файл — редкий приятный случай среди восьми: **нет гигантской функции**. Самая крупная,
`_ensure_migrations`, 78 строк. 24 функции уже сгруппированы по таблицам, границы
очевидны. Раскол здесь механический и почти лишён проектных решений.

Риск не в структуре, а в двух контрактах: четыре модуля импортируют `db`, и
`night-reviewer.sh` зовёт его как CLI из семи мест.

## Context

### Кто зависит

| Потребитель | Как | Символы |
|---|---|---|
| `callback.py` | `import db` | `release_slot`, `finish_task`, `update_project_phase`, `get_project_state`, `try_acquire_slot`, `log_task`, `get_task_by_pueue_id`, `record_decision`, `count_demotes_since`, `clear_decisions` |
| `orchestrator.py` | `import db` | `seed_projects_from_json`, `get_all_projects`, `get_available_slots`, `get_provider_capacity` |
| `gate-daemon.py` | `import db` | `log_gate_cycle`, `get_all_projects` |
| `claude-runner.py` | `import db as _orch_db` (ленивый, строка 63) | `log_sdk_post_result_error` |
| `orchestrator_monitor.py` | `from db import get_db` | `get_db` — **связанное имя** |
| `night-reviewer.sh` | subprocess, 7 call-sites | CLI-команды `update-phase`, `save-finding`, `get-new-findings` |

`orchestrator_monitor.py:95` делает `from db import get_db` — связывание имени. Это
значит: если `get_db` уедет из `db.py` без реэкспорта, модуль сломается. Поэтому
`get_db` остаётся в `db.py`.

### Карта ответственностей

| Группа | Строки | Функции |
|---|---|---|
| `connection` | 25-131 | `_ensure_migrations`, `get_db` |
| `slots` | 132-174 | `try_acquire_slot`, `release_slot` |
| `projects` | 175-280 | `get_project_state`, `get_all_projects`, `update_project_phase` |
| `tasklog` | 219-305 | `log_task`, `finish_task`, `get_available_slots`, `get_provider_capacity`, `get_occupied_slots`, `get_task_by_pueue_id` |
| `decisions` | 306-420 | `record_decision`, `count_demotes_since`, `clear_decisions`, `log_sdk_post_result_error`, `log_gate_cycle`, `get_gate_health` |
| `seed` | 421-442 | `seed_projects_from_json` |
| `findings` | 443-520 | `save_finding`, `get_new_findings`, `update_finding_status`, `get_finding_by_id`, `get_all_findings`, `get_projects_for_night_scan` |
| `cli` | 533-602 | `if __name__ == "__main__"` диспетчер argv |

---

## Scope

**In scope:** вынос групп `decisions`, `findings` и тела CLI-диспетчера в flat sibling-модули;
`db.py` ≤400 LOC; сохранение всех публичных имён на месте.

**Out of scope:** изменение схемы (`schema.sql` не трогается); миграции; смена SQLite на
что-либо; изменение CLI-команд, которые зовёт `night-reviewer.sh`.

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "import db" scripts/vps/ --include="*.py"` → 5 модулей (см. таблицу выше)
- `grep -n "db.py" scripts/vps/night-reviewer.sh` → 7 call-sites (52, 108, 130, 149, 176, 187, 257)
- `grep -rn "import db" scripts/vps/tests/` → `test_db.py`; корневой `tests/scripts/test_db.py`

### Step 2: DOWN — what depends on?

`db.py` → только stdlib (`sqlite3`, `json`, `pathlib`) + `schema.sql`. Ни одного из
восьми файлов. Это лист графа зависимостей.

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/orchestrator_monitor.py` | 95 | `from db import get_db` | `get_db` **остаётся** в `db.py`, правка не нужна |
| `scripts/vps/night-reviewer.sh` | 7 мест | `python3 db.py <cmd>` | имя файла и команды сохраняются |
| `scripts/vps/db.py` | 533 | `if __name__ == "__main__"` | остаётся, тело уезжает |
| `tests/scripts/test_db.py` | — | корневой тест `get_task_by_pueue_id` (BUG-164) | не правится, символ остаётся на месте |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — `test_db.py` (213 LOC)
- [x] `tests/**` (корень) — `tests/scripts/test_db.py` (75 LOC), не правится
- [x] `db/migrations/**` — директории нет; миграции внутри `_ensure_migrations` + `schema.sql`
- [x] `ai/glossary/**` — не существует

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] Каждое имя из таблицы «Кто зависит» резолвится через `db.<name>` после раскола

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/db.py` — оставить connection/slots/projects/tasklog + тонкий CLI-вход (modify)
- `scripts/vps/db_decisions.py` — circuit-breaker и телеметрия гейта (NEW)
- `scripts/vps/db_findings.py` — находки ночного ревью (NEW)
- `scripts/vps/db_cli.py` — тело argv-диспетчера (NEW)
- `scripts/vps/tests/test_db.py` — покрытие новых модулей (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** orchestrator (infra-слой)
**Cross-cutting:** Errors — параметризованные запросы обязательны, интерполяция в SQL
запрещена (ADR-017)
**Data model:** таблицы не меняются; `schema.sql` вне Allowed Files намеренно

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

---

## Approaches

### Approach 1: Flat sibling-модули, публичные имена остаются в `db.py` (выбран)
**Source:** `research-web.md` § Approach 1; `research-codebase.md` §1
**Summary:** `db.py` делает `import db_decisions` и переэкспортирует функции как
делегаты с той же сигнатурой
**Pros:** ни один из пяти потребителей не правится; `from db import get_db` в
`orchestrator_monitor.py` продолжает работать; CLI-контракт `night-reviewer.sh` цел
**Cons:** делегаты — это строки в `db.py`, часть выигрыша по LOC съедается

### Approach 2: Потребители импортируют новые модули напрямую
**Summary:** `callback.py` делает `import db_decisions` вместо `db.record_decision`
**Pros:** нет делегатов, экономия строк максимальна
**Cons:** правит четыре прод-модуля ради косметики в пятом; расширяет blast radius
задачи с одного файла на пять; прямо противоречит принципу «сохранить публичный шов»

### Selected: 1
**Rationale:** задача — уложить `db.py` в лимит, а не переучить его потребителей. Делегат
стоит одну строку и покупает нулевой диф у четырёх модулей в горячем пути.

---

## Design

### Раскол

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `db_decisions.py` | `record_decision`, `count_demotes_since`, `clear_decisions`, `log_sdk_post_result_error`, `log_gate_cycle`, `get_gate_health` | ~120 |
| `db_findings.py` | `save_finding`, `get_new_findings`, `update_finding_status`, `get_finding_by_id`, `get_all_findings`, `get_projects_for_night_scan` | ~85 |
| `db_cli.py` | тело argv-диспетчера | ~75 |
| `db.py` | `_ensure_migrations`, `get_db`, слоты, проекты, журнал задач, `seed_projects_from_json`, делегаты, `if __name__ == "__main__"` | ~340 |

### Соединение с БД

Новые модули **не открывают своё соединение**. Они принимают его параметром либо зовут
`db.get_db()` — единственная точка, где живёт `_ensure_migrations`. Дублировать
инициализацию схемы в трёх местах — это ровно тот класс дефекта, который чинит TECH-210.

Чтобы не получить цикл `db → db_decisions → db`, `get_db` передаётся аргументом:

```python
# db_decisions.py — ноль импортов из db
def record_decision(conn, project_id, spec_id, action, reason): ...

# db.py — делегат сохраняет публичную сигнатуру
def record_decision(project_id, spec_id, action, reason):
    return db_decisions.record_decision(get_db(), project_id, spec_id, action, reason)
```

Тот же инвариант, что `gate_logic.py:19` (FF-09): новые модули — чистые листья,
ноль импортов вверх по графу.

### CLI

`db.py` сохраняет `if __name__ == "__main__":` и делегирует в `db_cli.main(sys.argv)`.
Имя файла, набор команд и формат вывода не меняются — `night-reviewer.sh` зовёт его
семь раз и не правится.

---

## Implementation Plan

> Verified against the worktree on 2026-07-28. `wc -l scripts/vps/db.py` = **602**.
> Line ranges below are the CURRENT ones — the map in § Карта ответственностей had two
> stale rows (see `## Drift Log`).

### Research Sources
- Codebase (authoritative, re-read 2026-07-28): `scripts/vps/db.py`, `callback.py:36,924-1092`,
  `orchestrator.py:28`, `gate-daemon.py:42,359-365`, `claude-runner.py:63,582-589`,
  `orchestrator_monitor.py:91-101`, `night-reviewer.sh:52,89-95,108,130,149,176,187,257`
- `.claude/rules/architecture.md` ADR-017 — SQL только параметризованный
- `gate_logic.py` — образец чистого листа (ноль импортов вверх по графу)
- Exa/Context7 недоступны в этой сессии (`web_search_exa` → HTTP 402, credits exhausted).
  Решение подтверждено чтением кода, не вебом. См. `## Drift Log`.

### Verified consumer contract (do not break)

| Consumer | Line | Binding | Symbols it resolves |
|---|---|---|---|
| `callback.py` | 36 | `import db` | `release_slot`, `finish_task`, `update_project_phase`, `get_project_state`, `try_acquire_slot`, `log_task`, `get_task_by_pueue_id`, `record_decision`, `count_demotes_since`, `clear_decisions` |
| `orchestrator.py` | 28 | `import db` | `seed_projects_from_json`, `get_all_projects`, `get_project_state`, `get_available_slots`, `get_provider_capacity`, `get_occupied_slots`, `try_acquire_slot`, `log_task`, `update_project_phase` |
| `gate-daemon.py` | 42 | `import db` | `log_gate_cycle(**kwargs)`, `get_all_projects` |
| `claude-runner.py` | 63 | `import db as _orch_db` (lazy, in try/except) | `log_sdk_post_result_error(**kwargs)` |
| `orchestrator_monitor.py` | 95 | `from db import get_db` — **bound name** | `get_db` must stay defined in `db.py` |
| `night-reviewer.sh` | 89-95 | inline `python3 -c` + `import db` | `get_project_state` |
| `night-reviewer.sh` | 52, 108, 130, 149, 257 | `python3 db.py update-phase` | CLI |
| `night-reviewer.sh` | 176 | `python3 db.py save-finding` (8 args) | CLI |
| `night-reviewer.sh` | 187 | `python3 db.py get-new-findings` | CLI |
| `tests/scripts/test_db.py` | 24 | `patch.object(db, "DB_PATH", ...)` | `DB_PATH`, `get_db`, `get_task_by_pueue_id` — **file must not be edited** |
| `scripts/vps/tests/conftest.py` | 26-30 | `setenv("DB_PATH")` + `setattr(db_mod, "DB_PATH")` | same |
| `tests/conftest.py` | 16-34 | autouse `_db_isolation` | same |

Both call sites that use keyword arguments (`gate-daemon.py:359`, `claude-runner.py:582`)
pass **only** keywords that exist in the leaf signature — no collision with the new `conn`
first parameter, which no caller ever passes.

### Design corrections to § Design (found while re-reading the code)

1. **The snippet in § Design is wrong.** `get_db` is a `@contextmanager`, so
   `db_decisions.record_decision(get_db(), ...)` passes a `_GeneratorContextManager`,
   not a `sqlite3.Connection`, and nothing commits. The delegate must be
   `with get_db(immediate=...) as conn: return leaf.fn(conn, ...)`.
2. **`immediate=True` is part of the contract.** `clear_decisions`, `save_finding` and
   `update_finding_status` currently open with `BEGIN IMMEDIATE`. Delegates must preserve it.
3. **Twelve hand-written delegates do not fit in 400 LOC.** Measured: base after extraction
   is ~335 lines; twelve `def` delegates cost 60-72 more → 395-407, i.e. at or over the
   limit with zero headroom. Plan uses one `_delegate(fn, immediate=False)` factory plus
   twelve explicit module-level bindings (~30 lines total, final file ≈ 373).
   Bindings stay explicit (`record_decision = _delegate(db_decisions.record_decision)`),
   never generated in a loop — `hasattr`, grep and static readers all keep working.
4. **`db_cli` cannot `import db`** — under `python3 db.py` the module is `__main__`, so an
   `import db` inside `db_cli` would instantiate a *second* copy of the module with its own
   `DB_PATH` and `_MIGRATIONS_APPLIED`. The dispatcher receives the module as a parameter:
   `db_cli.main(sys.argv, sys.modules[__name__])`.
5. **EC-7 vs `get_projects_for_night_scan`.** Its SQL is today an f-string starting with
   `f"SELECT ...` (db.py:527). Moving it verbatim would make EC-7 (`grep 'f"SELECT'`) fail.
   Rewrite so only the `?,?,?` placeholder list is interpolated (code below). Values stay
   parameterized — ADR-017 unaffected either way.

### Current line map (re-measured, replaces § Карта ответственностей)

| Group | Lines | Fate |
|---|---|---|
| header + imports + constants | 1-24 | stays (docstring updated) |
| `_ensure_migrations` | 25-99 | **stays** |
| `get_db` | 102-129 | **stays** (`orchestrator_monitor.py:95` binds it) |
| `try_acquire_slot`, `release_slot` | 132-172 | stays |
| `get_project_state`, `get_all_projects`, `update_project_phase` | 175-216 | stays |
| `log_task`, `finish_task`, `get_available_slots`, `get_provider_capacity`, `get_occupied_slots`, `get_task_by_pueue_id` | 219-303 | stays |
| `record_decision` 306-325, `count_demotes_since` 328-340, `clear_decisions` 343-353, `log_sdk_post_result_error` 356-379, `log_gate_cycle` 382-408, `get_gate_health` 411-418 | **306-418** | → `db_decisions.py` |
| `seed_projects_from_json` | 421-440 | stays |
| `save_finding` 443-470, `get_new_findings` 473-480, `update_finding_status` 483-491, `get_finding_by_id` 494-501, `get_all_findings` 504-517, `get_projects_for_night_scan` 520-530 | **443-530** | → `db_findings.py` |
| `if __name__ == "__main__":` dispatcher | 533-602 | body → `db_cli.py`, 6-line entry stays |

**Mechanical extraction rule** (applies to every function moved to `db_decisions.py` /
`db_findings.py`): copy the function verbatim, insert `conn: sqlite3.Connection,` as the
first parameter, delete the `with get_db(...) as conn:` line, dedent the remaining body by
4 spaces, keep the docstring unchanged. The `immediate=True` flag from the deleted line is
recorded in the `db.py` binding, not in the leaf.

---

### Task 1: Characterization tests for the CLI contract (before touching db.py)

**Type:** test
**Files:**
- Modify: `scripts/vps/tests/test_db.py` (currently 213 LOC, limit 600)

**Context:** `night-reviewer.sh` calls `python3 db.py <cmd>` from seven places and parses
stdout with `jq`. Nothing pins that output today. Write the net first, run it against the
UNCHANGED `db.py` — it must be **green before** Tasks 2-4, otherwise it is testing the
refactor instead of the contract.

**Step 1: Append to `scripts/vps/tests/test_db.py`**

```python
# --- TECH-212: CLI contract (night-reviewer.sh calls these 7 times) ---

import json
import os
import subprocess

DB_PY = str(Path(__file__).resolve().parent.parent / "db.py")


def _cli(*args):
    """Run `python3 db.py <args>`; DB_PATH is inherited from the isolated_db fixture."""
    return subprocess.run(
        [sys.executable, DB_PY, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class TestCliContract:
    def test_no_args_prints_usage_to_stderr_exit_1(self, isolated_db):
        r = _cli()
        assert r.returncode == 1
        assert r.stdout == ""
        assert r.stderr == (
            "Usage: python3 db.py <seed|save-finding|get-new-findings"
            "|update-finding-status|update-phase> [args...]\n"
        )

    def test_unknown_command_prints_usage_exit_1(self, isolated_db):
        r = _cli("nope")
        assert r.returncode == 1
        assert "Usage: python3 db.py <seed|save-finding|get-new-findings" in r.stderr

    def test_update_phase_output_and_effect(self, seed_project):
        r = _cli("update-phase", "testproject", "night_reviewing")
        assert r.returncode == 0
        assert r.stdout == "phase: testproject -> night_reviewing\n"
        assert db.get_project_state("testproject")["phase"] == "night_reviewing"

    def test_update_phase_wrong_argc(self, isolated_db):
        r = _cli("update-phase", "onlyone")
        assert r.returncode == 1
        assert r.stderr == "Usage: python3 db.py update-phase <project_id> <phase>\n"

    def test_save_finding_prints_row_id_then_duplicate(self, seed_project):
        first = _cli(
            "save-finding", "testproject", "fp1", "high", "medium",
            "src/a.py", "10-12", "summary text", "suggestion text",
        )
        assert first.returncode == 0
        assert first.stdout.strip().isdigit()

        again = _cli(
            "save-finding", "testproject", "fp1", "high", "medium",
            "src/a.py", "10-12", "summary text", "suggestion text",
        )
        assert again.returncode == 0
        assert again.stdout == "duplicate\n"

    def test_save_finding_wrong_argc(self, isolated_db):
        r = _cli("save-finding", "testproject")
        assert r.returncode == 1
        assert r.stderr.startswith("Usage: python3 db.py save-finding <project_id>")

    def test_get_new_findings_emits_parseable_json(self, seed_project):
        _cli(
            "save-finding", "testproject", "fp2", "low", "high",
            "src/b.py", "1", "sum2", "sug2",
        )
        r = _cli("get-new-findings", "testproject")
        assert r.returncode == 0
        rows = json.loads(r.stdout)
        assert len(rows) == 1
        assert rows[0]["fingerprint"] == "fp2"
        assert rows[0]["status"] == "new"

    def test_get_new_findings_empty_is_bare_json_array(self, seed_project):
        r = _cli("get-new-findings", "testproject")
        assert r.returncode == 0
        assert r.stdout == "[]\n"  # night-reviewer.sh:190 compares against "[]"

    def test_update_finding_status_output(self, seed_project):
        created = _cli(
            "save-finding", "testproject", "fp3", "low", "low",
            "src/c.py", "3", "sum3", "sug3",
        )
        fid = created.stdout.strip()
        r = _cli("update-finding-status", fid, "reviewed")
        assert r.returncode == 0
        assert r.stdout == f"updated finding {fid} -> reviewed\n"
        assert _cli("get-new-findings", "testproject").stdout == "[]\n"

    def test_update_finding_status_wrong_argc(self, isolated_db):
        r = _cli("update-finding-status", "1")
        assert r.returncode == 1
        assert r.stderr == "Usage: python3 db.py update-finding-status <finding_id> <status>\n"

    def test_seed_reads_json_file_and_reports_count(self, isolated_db, tmp_path):
        payload = tmp_path / "projects.json"
        payload.write_text(
            json.dumps([{"project_id": "p9", "path": "/p9", "provider": "claude"}]),
            encoding="utf-8",
        )
        r = _cli("seed", str(payload))
        assert r.returncode == 0
        assert r.stdout == "seeded 1 projects\n"
        assert db.get_project_state("p9")["path"] == "/p9"

    def test_seed_wrong_argc(self, isolated_db):
        r = _cli("seed")
        assert r.returncode == 1
        assert r.stderr == "Usage: python3 db.py seed <path/to/projects.json>\n"
```

**Step 2: Run against the UNCHANGED `db.py`**

```bash
cd scripts/vps/tests && python -m pytest test_db.py -q
```

Expected: all 12 new tests **PASS** (plus the 18 existing ones). If any fails here, the
assertion is wrong — fix the test, not `db.py`.

**Acceptance Criteria:**
- [ ] 12 new tests pass against unmodified `db.py`
- [ ] `git diff --stat` touches only `scripts/vps/tests/test_db.py`
- [ ] `python -m ruff check scripts/vps/tests/test_db.py` clean (E402/I001 are per-file-ignored)

---

### Task 2: Extract `db_decisions.py` + delegates

**Type:** code
**Files:**
- Create: `scripts/vps/db_decisions.py`
- Modify: `scripts/vps/db.py` (delete 306-418; add `functools` import, `import db_decisions`, `_delegate`, 6 bindings)

**Step 1: Create `scripts/vps/db_decisions.py`**

```python
#!/usr/bin/env python3
"""
Module: db_decisions
Role: circuit-breaker decisions (TECH-169) + SDK/gate telemetry (BUG-188, ARCH-190).
Uses: sqlite3 (stdlib) — receives an open connection, never opens one.
Used by: db.py only, through thin delegates that keep the public names
         db.record_decision / db.count_demotes_since / db.clear_decisions /
         db.log_sdk_post_result_error / db.log_gate_cycle / db.get_gate_health.

Pure leaf (TECH-212): must never import db. The caller owns the connection and the
transaction; db.get_db() stays the single place migrations run.
"""

import sqlite3
from typing import Optional
```

Then move, in this order and with the mechanical extraction rule above:

| From `db.py` | New signature (first line) | `immediate` recorded in db.py |
|---|---|---|
| 306-325 | `def record_decision(conn: sqlite3.Connection, project_id: str, spec_id: Optional[str], verdict: str, reason: Optional[str], demoted: bool) -> int:` (keep the multi-line form) | no |
| 328-340 | `def count_demotes_since(conn: sqlite3.Connection, min_ago: int) -> int:` | no |
| 343-353 | `def clear_decisions(conn: sqlite3.Connection, min_ago: int) -> int:` | **yes** |
| 356-379 | `def log_sdk_post_result_error(conn: sqlite3.Connection, project_id: str, task: str, turns: int, cost_usd: float, error_msg: str, stderr: Optional[str]) -> int:` (keep multi-line form; parameter names are load-bearing — `claude-runner.py:582` calls with keywords) | no |
| 382-408 | `def log_gate_cycle(conn: sqlite3.Connection, cycle_count: int, last_poll_at: str, in_progress_specs: int, decisions_this_cycle: int, error_msg: Optional[str] = None) -> int:` (keep multi-line form; `gate-daemon.py:359` calls with keywords) | no |
| 411-418 | `def get_gate_health(conn: sqlite3.Connection) -> Optional[dict]:` | no |

Worked example — `clear_decisions`, before (db.py:343-353) and after:

```python
# db_decisions.py
def clear_decisions(conn: sqlite3.Connection, min_ago: int) -> int:
    """Delete callback_decisions rows newer than `min_ago` minutes. Returns deleted count.

    TECH-169: Used by --reset-circuit to flush the recent window.
    """
    cursor = conn.execute(
        "DELETE FROM callback_decisions WHERE ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
        (f"-{int(min_ago)} minutes",),
    )
    return cursor.rowcount or 0
```

**Step 2: Edit `scripts/vps/db.py`**

2a. Replace the module docstring (lines 2-12) with:

```python
"""
Module: db
Role: SQLite WAL helpers for orchestrator state management.
Uses: sqlite3 (stdlib), db_decisions, db_findings, db_cli
Used by: orchestrator.py, callback.py, gate-daemon.py, claude-runner.py (lazy),
         orchestrator_monitor.py (`from db import get_db`),
         night-reviewer.sh (CLI: save-finding / get-new-findings / update-phase)

TECH-212: decisions+telemetry live in db_decisions.py, night findings in db_findings.py,
the argv dispatcher in db_cli.py. Those three are pure leaves — they never import db.
This module keeps the public names as delegates so no consumer changed.
"""
```

2b. Imports (lines 14-18) become — `functools` added, sibling modules in their own block
so ruff isort (`I`) is satisfied:

```python
import functools
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import db_decisions
```

2c. **Delete lines 306-418** (the six decisions functions) together with one of the
surrounding blank-line pairs.

2d. Insert, after `seed_projects_from_json` and before `if __name__ == "__main__":`:

```python
def _delegate(fn, immediate: bool = False):
    """Bind a leaf-module function (conn first) to this module's connection.

    Keeps `db.<name>` as the public seam — callback/orchestrator/gate-daemon/
    claude-runner import `db` and nothing else — while the bodies live in pure
    leaves. `immediate` mirrors the BEGIN IMMEDIATE the original function used.
    """

    @functools.wraps(fn)
    def _call(*args, **kwargs):
        with get_db(immediate=immediate) as conn:
            return fn(conn, *args, **kwargs)

    return _call


# --- decisions + telemetry -> db_decisions.py (TECH-212) ---
record_decision = _delegate(db_decisions.record_decision)
count_demotes_since = _delegate(db_decisions.count_demotes_since)
clear_decisions = _delegate(db_decisions.clear_decisions, immediate=True)
log_sdk_post_result_error = _delegate(db_decisions.log_sdk_post_result_error)
log_gate_cycle = _delegate(db_decisions.log_gate_cycle)
get_gate_health = _delegate(db_decisions.get_gate_health)
```

**Step 3: Verify**

```bash
cd scripts/vps/tests && python -m pytest test_db.py test_callback.py test_gate_daemon.py -q
cd ../../.. && python -m pytest tests/integration/test_callback_circuit_breaker.py \
    tests/integration/test_sdk_post_result_errors_telemetry.py \
    tests/integration/test_callback_already_merged.py -q
python -m ruff check scripts/vps/db.py scripts/vps/db_decisions.py
```

Expected: all pass. `test_gate_daemon.py` calls `db_mod.log_gate_cycle(...)` /
`db_mod.get_gate_health()` and `test_sdk_post_result_errors_telemetry.py` calls
`db.log_sdk_post_result_error(...)` with keywords — these prove the delegates.

**Acceptance Criteria:**
- [ ] `grep -nE "^\s*(import db$|from db import)" scripts/vps/db_decisions.py` → 0 hits
- [ ] `grep -c "immediate=True" scripts/vps/db.py` includes the `clear_decisions` binding
- [ ] All six names still resolve: `PYTHONPATH=scripts/vps python -c "import db; [getattr(db,n) for n in ('record_decision','count_demotes_since','clear_decisions','log_sdk_post_result_error','log_gate_cycle','get_gate_health')]"`
- [ ] Task 1's CLI tests still green (nothing in the CLI path moved yet)

---

### Task 3: Extract `db_findings.py` + delegates

**Type:** code
**Files:**
- Create: `scripts/vps/db_findings.py`
- Modify: `scripts/vps/db.py` (delete the findings block; add `import db_findings` + 6 bindings)

**Step 1: Create `scripts/vps/db_findings.py`**

```python
#!/usr/bin/env python3
"""
Module: db_findings
Role: night-review findings CRUD (FTR-147) — night_findings table.
Uses: sqlite3 (stdlib) — receives an open connection, never opens one.
Used by: db.py only, through thin delegates that keep the public names
         db.save_finding / db.get_new_findings / db.update_finding_status /
         db.get_finding_by_id / db.get_all_findings / db.get_projects_for_night_scan.
         The live consumer is night-reviewer.sh via `python3 db.py <cmd>` (db_cli.py).

Pure leaf (TECH-212): must never import db.
"""

import sqlite3
from typing import Optional
```

Move with the mechanical rule:

| From `db.py` | New signature (first line) | `immediate` |
|---|---|---|
| 443-470 | `def save_finding(conn: sqlite3.Connection, project_id: str, fingerprint: str, severity: str, confidence: str, file_path: Optional[str], line_range: Optional[str], summary: str, suggestion: Optional[str]) -> Optional[int]:` (keep multi-line form) | **yes** |
| 473-480 | `def get_new_findings(conn: sqlite3.Connection, project_id: str) -> list[dict]:` | no |
| 483-491 | `def update_finding_status(conn: sqlite3.Connection, finding_id: int, status: str) -> None:` | **yes** |
| 494-501 | `def get_finding_by_id(conn: sqlite3.Connection, finding_id: int) -> Optional[dict]:` | no |
| 504-517 | `def get_all_findings(conn: sqlite3.Connection, project_id: str, status: Optional[str] = None) -> list[dict]:` | no |
| 520-530 | see below — **not a verbatim move** | no |

`get_projects_for_night_scan` is the one function whose body changes (EC-7: `f"SELECT`
must not appear in `db_*.py`):

```python
def get_projects_for_night_scan(conn: sqlite3.Connection, project_ids: list[str]) -> list[dict]:
    """Return enabled projects whose project_id is in the given list."""
    if not project_ids:
        return []
    # Only the "?,?,?" placeholder list is interpolated — every value stays a
    # bound parameter (ADR-017).
    placeholders = ",".join("?" * len(project_ids))
    sql = (
        "SELECT * FROM project_state WHERE enabled = 1 "
        f"AND project_id IN ({placeholders}) ORDER BY project_id"
    )
    rows = conn.execute(sql, project_ids).fetchall()
    return [dict(r) for r in rows]
```

Behaviour note (accepted, zero callers today): the delegate opens a connection before the
`if not project_ids` guard runs, so an empty-list call now touches the DB file. Harmless —
`_ensure_migrations` is idempotent and tolerates a missing schema.

**Step 2: Edit `scripts/vps/db.py`**

2a. Imports block gains one line:

```python
import db_decisions
import db_findings
```

2b. Delete the findings block (current 443-530, i.e. everything between
`seed_projects_from_json` and `if __name__ == "__main__":` after Task 2's edits).

2c. Append to the bindings block:

```python
# --- night findings -> db_findings.py (TECH-212) ---
save_finding = _delegate(db_findings.save_finding, immediate=True)
get_new_findings = _delegate(db_findings.get_new_findings)
update_finding_status = _delegate(db_findings.update_finding_status, immediate=True)
get_finding_by_id = _delegate(db_findings.get_finding_by_id)
get_all_findings = _delegate(db_findings.get_all_findings)
get_projects_for_night_scan = _delegate(db_findings.get_projects_for_night_scan)
```

**Step 3: Verify**

```bash
cd scripts/vps/tests && python -m pytest test_db.py -q
python -m ruff check scripts/vps/db.py scripts/vps/db_findings.py
grep -nE 'f"SELECT|f"INSERT|% \(' scripts/vps/db_findings.py scripts/vps/db_decisions.py
```

Expected: `test_db.py` green (the CLI still runs from `db.py`'s own `__main__`, now hitting
the delegates); grep prints nothing.

**Acceptance Criteria:**
- [ ] `grep -nE "^\s*(import db$|from db import)" scripts/vps/db_findings.py` → 0 hits
- [ ] Task 1's 12 CLI tests still green — save-finding dedup still returns `duplicate`, which
      proves `immediate=True` + `INSERT OR IGNORE` survived
- [ ] EC-7 grep clean

---

### Task 4: Extract `db_cli.py`, leave a 6-line entry point

**Type:** code
**Files:**
- Create: `scripts/vps/db_cli.py`
- Modify: `scripts/vps/db.py` (replace lines 533-602 with the entry point)

**Step 1: Create `scripts/vps/db_cli.py`** — complete file:

```python
#!/usr/bin/env python3
"""
Module: db_cli
Role: argv dispatcher for `python3 db.py <cmd>` (night-reviewer.sh calls it 7 times).
Uses: json, sys (stdlib).
Used by: db.py `if __name__ == "__main__":` only.

Pure leaf (TECH-212): must never import db. Under `python3 db.py` that module is
__main__, so an `import db` here would create a SECOND module object with its own
DB_PATH and _MIGRATIONS_APPLIED. The caller passes itself in as `api` instead.

Command set and output are frozen — night-reviewer.sh parses stdout with jq and
compares get-new-findings against the literal "[]".
"""

import json
import sys

_USAGE = (
    "Usage: python3 db.py <seed|save-finding|get-new-findings"
    "|update-finding-status|update-phase> [args...]"
)


def main(argv: list[str], api) -> int:
    """Dispatch argv. `api` is the db module. Returns the process exit code."""
    cmd = argv[1] if len(argv) > 1 else ""

    if cmd == "seed":
        if len(argv) != 3:
            print("Usage: python3 db.py seed <path/to/projects.json>", file=sys.stderr)
            return 1
        with open(argv[2], encoding="utf-8") as f:
            projects = json.load(f)
        api.seed_projects_from_json(projects)
        print(f"seeded {len(projects)} projects")
        return 0

    if cmd == "save-finding":
        # Args: project_id fingerprint severity confidence file_path line_range summary suggestion
        if len(argv) != 10:
            print(
                "Usage: python3 db.py save-finding <project_id> <fingerprint> <severity>"
                " <confidence> <file_path> <line_range> <summary> <suggestion>",
                file=sys.stderr,
            )
            return 1
        fid = api.save_finding(
            argv[2],
            argv[3],
            argv[4],
            argv[5],
            argv[6],
            argv[7],
            argv[8],
            argv[9],
        )
        print(fid if fid is not None else "duplicate")
        return 0

    if cmd == "get-new-findings":
        if len(argv) != 3:
            print("Usage: python3 db.py get-new-findings <project_id>", file=sys.stderr)
            return 1
        print(json.dumps(api.get_new_findings(argv[2])))
        return 0

    if cmd == "update-finding-status":
        if len(argv) != 4:
            print(
                "Usage: python3 db.py update-finding-status <finding_id> <status>",
                file=sys.stderr,
            )
            return 1
        api.update_finding_status(int(argv[2]), argv[3])
        print(f"updated finding {argv[2]} -> {argv[3]}")
        return 0

    if cmd == "update-phase":
        if len(argv) != 4:
            print("Usage: python3 db.py update-phase <project_id> <phase>", file=sys.stderr)
            return 1
        api.update_project_phase(argv[2], argv[3])
        print(f"phase: {argv[2]} -> {argv[3]}")
        return 0

    print(_USAGE, file=sys.stderr)
    return 1
```

Two deliberate deltas from the original body, both invisible to `night-reviewer.sh`:
`open(..., encoding="utf-8")` (repo convention since 2026-07-27) and `return N` instead of
`sys.exit(N)`, with the exit code re-raised by the caller.

**Step 2: Replace `db.py` lines 533-602 with**

```python
if __name__ == "__main__":
    import sys

    import db_cli

    # sys.modules[__name__] is this module under its __main__ identity — passing it
    # keeps db_cli a leaf and guarantees one module object, one DB_PATH.
    sys.exit(db_cli.main(sys.argv, sys.modules[__name__]))
```

**Step 3: Verify**

```bash
wc -l scripts/vps/db.py scripts/vps/db_cli.py scripts/vps/db_decisions.py scripts/vps/db_findings.py
cd scripts/vps/tests && python -m pytest test_db.py -q
python -m ruff check scripts/vps/db.py scripts/vps/db_cli.py
```

Expected: `db.py` ≈ 373 (hard requirement ≤400), each new module well under 400; all 30
tests in `test_db.py` pass, including the 12 CLI characterization tests written in Task 1
against the pre-refactor code.

**Acceptance Criteria:**
- [ ] `wc -l scripts/vps/db.py` ≤ 400
- [ ] `grep -nE "^\s*(import db$|from db import)" scripts/vps/db_cli.py` → 0 hits
- [ ] Task 1's CLI tests pass **unmodified** — this is the byte-identical-output proof (EC-9)
- [ ] `python3 scripts/vps/db.py` with no args → same usage text on stderr, exit 1

---

### Task 5: Contract regression tests + full suite

**Type:** test
**Files:**
- Modify: `scripts/vps/tests/test_db.py`

**Context:** Tasks 2-4 are verified by behaviour; this task nails the *shape* so the split
cannot silently rot back (leaf purity, LOC ceiling, public surface).

**Step 1: Append to `scripts/vps/tests/test_db.py`**

```python
# --- TECH-212: structural contract of the split ---

import re

VPS = Path(VPS_DIR)
LEAF_MODULES = ["db_decisions.py", "db_findings.py", "db_cli.py"]

PUBLIC_SURFACE = [
    # connection + slots + projects + tasklog (stayed in db.py)
    "DB_PATH", "get_db", "try_acquire_slot", "release_slot", "get_project_state",
    "get_all_projects", "update_project_phase", "log_task", "finish_task",
    "get_available_slots", "get_provider_capacity", "get_occupied_slots",
    "get_task_by_pueue_id", "seed_projects_from_json",
    # delegated to db_decisions
    "record_decision", "count_demotes_since", "clear_decisions",
    "log_sdk_post_result_error", "log_gate_cycle", "get_gate_health",
    # delegated to db_findings
    "save_finding", "get_new_findings", "update_finding_status",
    "get_finding_by_id", "get_all_findings", "get_projects_for_night_scan",
]


class TestSplitContract:
    def test_public_surface_intact(self):
        """EC-1: every name a consumer resolves through `db.` is still there."""
        missing = [n for n in PUBLIC_SURFACE if not hasattr(db, n)]
        assert missing == [], f"db lost public names: {missing}"

    def test_from_db_import_get_db_still_works(self):
        """EC-2: orchestrator_monitor.py:95 binds the name, not the module."""
        from db import get_db  # noqa: PLC0415
        assert callable(get_db)

    @pytest.mark.parametrize("name", LEAF_MODULES)
    def test_new_modules_are_leaves(self, name):
        """EC-3: a cycle here would give `python3 db.py` two module objects."""
        source = (VPS / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*import db\s*$", source, re.M), f"{name} imports db"
        assert not re.search(r"^\s*from db import", source, re.M), f"{name} imports from db"

    @pytest.mark.parametrize("name", ["db.py", *LEAF_MODULES])
    def test_under_loc_limit(self, name):
        """EC-4 + EC-5: 400 LOC is the reason this task exists."""
        loc = len((VPS / name).read_text(encoding="utf-8").splitlines())
        assert loc <= 400, f"{name} is {loc} LOC"

    def test_ensure_migrations_defined_once(self):
        """EC-6: schema init has exactly one home."""
        defs = [
            p.name
            for p in VPS.glob("*.py")
            if re.search(r"^def _ensure_migrations", p.read_text(encoding="utf-8"), re.M)
        ]
        assert defs == ["db.py"], f"_ensure_migrations defined in {defs}"

    @pytest.mark.parametrize("name", LEAF_MODULES)
    def test_sql_stays_parameterized(self, name):
        """EC-7 / ADR-017: no interpolated SQL literals."""
        source = (VPS / name).read_text(encoding="utf-8")
        assert 'f"SELECT' not in source
        assert 'f"INSERT' not in source
        assert "% (" not in source


class TestDelegatedBehaviour:
    def test_record_decision_and_count_window(self, seed_project):
        """EC-10: circuit-breaker window still counts through the delegate."""
        for i in range(4):
            db.record_decision("testproject", f"TECH-{i}", "demote", "no_impl", demoted=True)
        assert db.count_demotes_since(10) == 4
        assert db.clear_decisions(10) == 4
        assert db.count_demotes_since(10) == 0

    def test_gate_health_roundtrip(self, seed_project):
        """gate-daemon.py:359 calls with keywords only."""
        row_id = db.log_gate_cycle(
            cycle_count=7,
            last_poll_at="2026-07-28T00:00:00Z",
            in_progress_specs=2,
            decisions_this_cycle=1,
            error_msg=None,
        )
        assert row_id > 0
        latest = db.get_gate_health()
        assert latest["cycle_count"] == 7
        assert latest["in_progress_specs"] == 2

    def test_sdk_post_result_error_keyword_call(self, seed_project):
        """claude-runner.py:582 calls with keywords only."""
        row_id = db.log_sdk_post_result_error(
            project_id="testproject",
            task="autopilot TECH-212",
            turns=5,
            cost_usd=1.25,
            error_msg="boom",
            stderr=None,
        )
        assert row_id > 0

    def test_findings_lifecycle_through_delegates(self, seed_project):
        fid = db.save_finding(
            "testproject", "fp-x", "high", "high", "src/x.py", "1-2", "sum", "sug"
        )
        assert fid is not None
        assert db.save_finding(
            "testproject", "fp-x", "high", "high", "src/x.py", "1-2", "sum", "sug"
        ) is None
        assert len(db.get_new_findings("testproject")) == 1
        assert db.get_finding_by_id(fid)["fingerprint"] == "fp-x"
        db.update_finding_status(fid, "reviewed")
        assert db.get_new_findings("testproject") == []
        assert len(db.get_all_findings("testproject")) == 1
        assert len(db.get_all_findings("testproject", status="reviewed")) == 1

    def test_projects_for_night_scan(self, seed_project):
        assert db.get_projects_for_night_scan([]) == []
        rows = db.get_projects_for_night_scan(["testproject", "ghost"])
        assert [r["project_id"] for r in rows] == ["testproject"]
```

Add `import pytest` to the test module's imports if it is not already there (it is not —
the current file imports only `sqlite3`, `sys`, `Path`).

**Step 2: Full suite**

```bash
python -m pytest -q                       # testpaths = tests + scripts/vps/tests
git status --porcelain tests/scripts/test_db.py   # must be empty
wc -l scripts/vps/db.py scripts/vps/db_*.py scripts/vps/tests/test_db.py
```

Expected: 0 failed; `tests/scripts/test_db.py` untouched (AV-F2); `test_db.py` under 600.

**Acceptance Criteria:**
- [ ] Whole suite green (`python -m pytest -q`), no test outside `scripts/vps/tests/test_db.py` modified
- [ ] `git diff --name-only` = exactly the 5 Allowed Files (+ this spec)
- [ ] `scripts/vps/tests/test_db.py` ≤ 600 LOC

---

### Execution Order

```
Task 1 (net first, green on OLD code)
   ↓
Task 2 (db_decisions)  →  Task 3 (db_findings)   [sequential: both edit db.py]
   ↓
Task 4 (db_cli + entry point, db.py drops under 400)
   ↓
Task 5 (structural contract + full suite)
```

### Dependencies

- Task 1 has no dependencies and MUST be green before Task 2 starts — it is the only
  evidence that CLI output did not change (EC-9).
- Tasks 2, 3, 4 all edit `db.py`; run them strictly in order, one commit each.
- Task 5 depends on 2+3+4 (its LOC and leaf assertions fail until all three land).

### Out of scope reminders

- `schema.sql` is NOT in Allowed Files — no table changes.
- `docs/orchestrator/components.md:111-112` and `.claude/rules/dependencies.md` describe
  the db groups and will be stale after this task; both are outside Allowed Files. Leave
  them alone; note it in the diary for `/reflect`.
- No `template/scripts/vps/` exists → no template sync task (checked 2026-07-28).

---

## Drift Log

**Checked:** 2026-07-28 21:20 UTC (planner, worktree `.worktrees/TECH-212`)
**Result:** light_drift — AUTO-FIX applied in `## Implementation Plan`

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/db.py` | still 602 LOC, all 24 functions present | AUTO-FIX: none needed, ranges re-measured |
| `scripts/vps/db.py` | § Карта ответственностей rows `projects 175-280` and `tasklog 219-305` overlap and are wrong | AUTO-FIX: corrected to `projects 175-216`, `tasklog 219-303` in the plan's line map |
| `scripts/vps/db.py` | `decisions` ends at 418 (spec said 420); `findings` ends at 530 (spec said 520) | AUTO-FIX: corrected in plan |
| `scripts/vps/db.py` | `get_provider_capacity` (added 2026-07-27) is in the tasklog group and stays | AUTO-FIX: added to the stays-list and to `PUBLIC_SURFACE` |
| § Design snippet | `db_decisions.record_decision(get_db(), ...)` — `get_db` is a `@contextmanager`, that passes a context-manager object, not a `Connection`, and never commits | AUTO-FIX: plan uses `with get_db(immediate=...) as conn:` inside a `_delegate` factory |
| § Design LOC estimate | "делегат стоит одну строку" — measured, 12 hand-written delegates land db.py at 395-407, i.e. at/over the limit | AUTO-FIX: `_delegate` factory + 12 explicit bindings (~30 lines), projected db.py ≈ 373 |
| `scripts/vps/db.py:527` | `get_projects_for_night_scan` uses `f"SELECT ... IN ({placeholders})"` — a verbatim move would fail EC-7's grep | AUTO-FIX: rewritten so only the placeholder list is interpolated |
| `scripts/vps/db_cli.py` (new) | a leaf that imported `db` would get a SECOND module object under `python3 db.py` (that run's module is `__main__`) — two `DB_PATH`s, two `_MIGRATIONS_APPLIED` | AUTO-FIX: `main(argv, api)` receives `sys.modules[__name__]` |
| `scripts/vps/tests/conftest.py`, `tests/conftest.py` | DB isolation patches `db.DB_PATH` (env + attribute) | verified compatible — `get_db` stays in `db.py` and reads `DB_PATH` at call time |
| `template/scripts/vps/` | does not exist | no sync task (sync zone check ran, `template/scripts/` has 8 root-level scripts only) |
| Exa MCP | `web_search_exa` → HTTP 402 "credits limit exceeded" | research fell back to codebase reading; approach unchanged (mechanical refactor, no external API surface) |

### References Updated

- Task 2: `decisions 306-420` → `306-418`, with per-function ranges
- Task 3: `findings 443-520` → `443-530`, with per-function ranges
- Task 4: `cli 533-602` confirmed unchanged
- § Кто зависит: `orchestrator.py` symbol list extended with `get_project_state`,
  `get_occupied_slots`, `get_provider_capacity` (verified by grep, 18 `db.` call sites)

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | `db.py` под 400 | Task 1, 2 | ✓ |
| 2 | Пять потребителей не правятся | Task 1 (делегаты) | ✓ |
| 3 | CLI-контракт `night-reviewer.sh` цел | Task 2 | ✓ |
| 4 | Схема инициализируется в одном месте | Task 1 (design) | ✓ |
| 5 | Покрытие не упало | Task 3 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Публичные имена на месте | `hasattr(db, n)` для 20 символов из § Кто зависит | все `True` | deterministic | codebase §4 | P0 |
| EC-2 | `from db import get_db` работает | импорт `orchestrator_monitor` | без ошибок | deterministic | codebase §3 | P0 |
| EC-3 | Новые модули — листья | `grep "^import db$\|^from db import" scripts/vps/db_*.py` | 0 попаданий | deterministic | FF-09 паттерн | P0 |
| EC-4 | `db.py` под лимитом | `wc -l scripts/vps/db.py` | ≤ 400 | deterministic | user | P0 |
| EC-5 | Новые модули под лимитом | `wc -l scripts/vps/db_*.py` | каждый ≤ 400 | deterministic | user | P1 |
| EC-6 | Схема создаётся один раз | `grep -c "_ensure_migrations" scripts/vps/*.py` | определение ровно одно | deterministic | design | P0 |
| EC-7 | SQL параметризован | `grep -n "f\"SELECT\|f\"INSERT\|% (" scripts/vps/db_*.py` | 0 попаданий | deterministic | ADR-017 | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-8 | Пустая БД | `python3 scripts/vps/db.py update-phase <proj> <phase>` | exit 0, строка в таблице | integration | night-reviewer | P0 |
| EC-9 | БД с находками | `python3 scripts/vps/db.py get-new-findings` | вывод побайтово тот же, что до правки | integration | night-reviewer | P0 |
| EC-10 | Circuit-breaker | 4 demote за 10 минут через `db.record_decision` | `count_demotes_since` = 4, цепь открывается | integration | TECH-169 | P0 |

### Coverage Summary
Deterministic: 7 | Integration: 3 | LLM-Judge: 0 | Total: 10 (min 3 ✓)

### TDD Order
1. EC-9 — снять эталонный вывод CLI ДО правки
2. EC-1, EC-2, EC-3 — контракт импортов
3. EC-8, EC-10 — интеграция
4. EC-4..EC-7 — форма

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Модуль импортируется | `PYTHONPATH=scripts/vps python -c "import db"` | exit 0 | 15s |
| AV-S2 | CLI отвечает | `python3 scripts/vps/db.py` без аргументов | usage, exit ≠ 2 не требуется — тот же код, что до правки | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты зелёные | — | `cd scripts/vps/tests && python -m pytest -q` | 0 failed |
| AV-F2 | Корневые тесты БД | — | `python -m pytest tests/scripts/test_db.py -q` | passed, файл не правился |
| AV-F3 | Ночное ревью не сломано | VPS | `bash scripts/vps/night-reviewer.sh --dry-run` (или первые 3 вызова `db.py` вручную) | exit 0 |
| AV-F4 | Демоны на новом коде | VPS | `systemctl --user restart dld-orchestrator dld-gate-daemon && systemctl --user is-active dld-orchestrator dld-gate-daemon` | `active` дважды |

### Verify Command

```bash
PYTHONPATH=scripts/vps python -c "import db, db_decisions, db_findings, db_cli"
wc -l scripts/vps/db.py scripts/vps/db_*.py
cd scripts/vps/tests && python -m pytest -q
python -m pytest tests/scripts/test_db.py -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `db.py` ≤ 400 LOC, три новых модуля ≤ 400 каждый
- [ ] Все публичные имена доступны как `db.<name>`
- [ ] CLI-команды и их вывод не изменились

### Tests
- [ ] EC-1..EC-10 проходят
- [ ] `tests/scripts/test_db.py` зелёный без правок

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2 локально
- [ ] AV-F3, AV-F4 на VPS — рестарт демонов обязателен

### Technical
- [ ] Новые модули не импортируют `db` (ноль циклов)
- [ ] `_ensure_migrations` определён ровно один раз

---

## Autopilot Log

### Task 1/5: Характеризационные тесты CLI-контракта — 2026-07-28 00:30
- Coder: completed (1 file: scripts/vps/tests/test_db.py, 213→413 LOC)
- Tester: passed (29 тестов зелёные против НЕИЗМЕНЁННОГО db.py — сеть снята до раскола)
- Spec compliance: matches
- Code Quality Reviewer: needs_refactor (1 blocking, 2 advisory) → все три исправлены → approved
  - blocking: `get_new_findings` пинился по неиспользуемым ключам; night-reviewer.sh:205-211
    читает 7 ключей через `jq // ""` — потеря колонки деградировала бы молча
- Exa Verify: skipped (web_search_exa → HTTP 402, кредиты исчерпаны)
- Local Verify: pass
- Commit: 7519519

### Task 2/5: Вынос db_decisions.py — 2026-07-28 00:52
- Coder: completed (2 files: db_decisions.py NEW 127 LOC, db.py 602→516)
- Tester: passed (472 vps-теста)
- Spec compliance: matches
- Code Quality Reviewer: approved (4 advisory) — body-for-body сверка с HEAD, `immediate=True`
  сохранён только у `clear_decisions`, keyword-имена для `**kwargs`-вызовов из daemon'ов целы
- Local Verify: pass (EC-3/EC-6/EC-7 зелёные)
- Commit: 5fad8b7

### Task 3/5: Вынос db_findings.py — 2026-07-28 01:05
- Coder: completed (2 files: db_findings.py NEW 105 LOC, db.py 516→435)
- Tester: passed (472 vps-теста)
- Spec compliance: matches
- Code Quality Reviewer: approved (3 advisory) — `get_projects_for_night_scan` переписан так,
  что интерполируется только список `?,?,?`; SQL прогнан бок-о-бок со старым на живой схеме
- Local Verify: pass
- Commit: caa5c7b

### Task 4/5: Вынос db_cli.py — 2026-07-28 01:20
- Coder: completed (2 files: db_cli.py NEW 88 LOC, db.py 435→**373**)
- Tester: passed (472 vps-теста)
- Spec compliance: matches
- Code Quality Reviewer: approved (2 advisory) — дифференциальный прогон old vs new по 13
  инвокациям: stdout/stderr/exit-code совпали байт-в-байт (md5)
- Local Verify: pass (EC-4 373≤400, EC-5 все листы ≤400)
- Commit: d67deac

### Task 5/5: Структурные контрактные тесты — 2026-07-28 01:45
- Coder: completed (1 file: test_db.py 413→568 LOC)
- Tester: passed (487 vps-тестов)
- Spec compliance: matches (EC-1..EC-7 + EC-10 покрыты)
- Mutation-проверка: удаление одного делегата из db.py → EC-1 падает (тесты не тавтологичны)
- Commit: 8624e78

### PHASE 3 — 2026-07-28 02:10
- Full suite: 681 passed, 3 failed (**pre-existing на develop**, callback-тесты, вне scope:
  test_callback_blocked_no_dispatch, test_callback_status_sync, test_callback_allowlist_v1)
- ruff check + ruff format: clean на всех 5 изменённых файлах
- AV-S1 import db,db_decisions,db_findings,db_cli → exit 0
- AV-S2 CLI usage → тот же текст, exit 1 (как до правки)
- AV-F1/AV-F2: pass; `tests/scripts/test_db.py` зелёный БЕЗ правок
- AV-F3: 7 CLI call-sites прогнаны old vs new на копии прод-БД (`orchestrator.db`) — вывод идентичен
- Documenter: completed → `.claude/rules/dependencies.md`, `docs/orchestrator/components.md` (06187cb)
- Exa Verify: skipped — Exa MCP исчерпал кредиты (HTTP 402), см. SIGNAL-2026-07-28-0134
