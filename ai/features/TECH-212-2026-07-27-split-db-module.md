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

### Research Sources
- `research-codebase.md` §1 (`db.py`) — карта групп с диапазонами строк
- `research-codebase.md` §3 — полный граф импортов и CLI-потребители
- `.claude/rules/architecture.md` ADR-017 — SQL только параметризованный

### Task 1: Вынести `decisions` и `findings`
**Type:** code
**Files:**
  - create: `scripts/vps/db_decisions.py`
  - create: `scripts/vps/db_findings.py`
  - modify: `scripts/vps/db.py`
**Pattern:** `gate_logic.py` — чистый лист без импортов вверх по графу
**Acceptance:** новые модули не содержат `import db`; все 12 функций доступны как
`db.<name>` с прежней сигнатурой

### Task 2: Вынести тело CLI
**Type:** code
**Files:**
  - create: `scripts/vps/db_cli.py`
  - modify: `scripts/vps/db.py`
**Pattern:** —
**Acceptance:** `python3 scripts/vps/db.py get-new-findings` даёт тот же вывод, что до правки;
`wc -l scripts/vps/db.py` ≤ 400

### Task 3: Тесты
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_db.py`
**Pattern:** существующие кейсы `test_db.py`
**Acceptance:** покрыты обе новые группы; корневой `tests/scripts/test_db.py` зелёный **без правок**

### Execution Order
1 → 2 → 3

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
