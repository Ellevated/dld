# Feature: [TECH-215] Раскол orchestrator.py и разбор scan_queued

**Priority:** P1 | **Date:** 2026-07-27

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`orchestrator.py` — 1078 LOC при лимите 400, из них `scan_queued` — **201 строка в одной
функции** (строки 774-975). Это главный цикл: он читает lifecycle, проходит гейт
реконсиляции, проверяет зависимости и диспатчит автопилот. Каждая из четырёх обязанностей
внутри одного тела.

Именно в этой функции 2026-07-27 сработал баг реконсиляции: гейт закрывал спеку против её
собственного birth-коммита. Найти его удалось потому, что искали целенаправленно по
живым данным VPS — а не потому, что читая функцию, увидели проблему.

## Context

### Карта ответственностей

| Группа | Строки | Содержимое | ~LOC |
|---|---|---|---|
| `bootstrap` | 37-84 | `_load_env`, `_setup_logging`, `_signal_handler`, `_write_pid` | 48 |
| `slots` | 85-318 | `sync_projects`, `get_live_pueue_ids`, `pueue_has_active_label`, `pueue_has_active_spec`, `release_orphan_slots`, `is_agent_running`, `git_pull` | 234 |
| `backlog` | 319-597 | `_parse_backlog` (ADR-026), `_bump_unparsable_counter`, `bootstrap_new_specs`, `_parse_priority_kind`, `cleanup_stale_stashes`, `startup_reconcile` | 279 |
| `inbox` | 598-736 | `_parse_inbox_file`, `_pueue_add`, `scan_inbox` (ADR-021/022) | 139 |
| `queue` | 737-991 | `_backlog_deps`, `_unmet_dependencies`, **`scan_queued` (201)**, `dispatch_night_review` | 255 |
| `main` | 992-1078 | `process_project`, `_next_sleep`, `main` | 87 |

### Контракты

| Контракт | Где | Замечание |
|---|---|---|
| systemd `ExecStart` | `setup-vps.sh:456` | абсолютный путь к `orchestrator.py`, зашит при установке, **не перегенерируется push'ем** |
| «No dirty WT» на старте | `assert_clean_lifecycle_tree` в `main` | ADR-023, прерывает старт при грязном `ai/lifecycle/` |
| `AFTER <ID>` в backlog-строке | `_AFTER_DEP_RE`, строка 734 | единственное место, откуда берутся зависимости между спеками |
| bootstrap fail'ится в `queued` | `bootstrap_new_specs` | ADR-026: **никогда** не в `done` |
| связанный импорт | `test_orchestrator_bootstrap.py:28` | `from orchestrator import _bump_unparsable_counter, _parse_backlog` |

Последняя строка важна: тест ADR-026 связывает два приватных имени при импорте. Если они
уедут без реэкспорта — тест падает на сборке.

---

## Scope

**In scope:** вынос `slots`, `backlog`, `inbox`, `queue` в flat sibling-модули; разбор
`scan_queued` на именованные шаги; `orchestrator.py` ≤400 LOC.

**Out of scope:** изменение логики гейта реконсиляции (она в `gate_logic`, чинилась
2026-07-27); изменение интервалов опроса; изменение intake-гейта Hermes (ADR-021/022);
переименование `orchestrator.py`.

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "import orchestrator" scripts/vps/ --include="*.py"` → только тесты
- `grep -n "orchestrator.py" scripts/vps/setup-vps.sh` → строка 456, `ExecStart`
- Тесты: `test_orchestrator.py` (1311 — крупнейший тест-файл дерева),
  `test_orchestrator_bootstrap.py` (690), `test_orchestrator_git_pull.py` (188),
  `test_orchestrator_lifecycle.py` (140)

### Step 2: DOWN — what depends on?

```
orchestrator.py → db, gate_logic, lifecycle (строки 28-30)
                → event_writer (ленивый, строка 490)
```

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/setup-vps.sh` | 456 | `ExecStart=... orchestrator.py` | **не трогать** — имя сохраняется |
| `scripts/vps/tests/test_orchestrator_bootstrap.py` | 28 | связанный импорт двух приватных имён | реэкспорт в `orchestrator.py` |
| `scripts/vps/tests/test_orchestrator.py` | 3 приватные ссылки | monkeypatch | перенацелить |
| `scripts/vps/orchestrator.py` | 734 | `_AFTER_DEP_RE` | переезжает вместе с `_backlog_deps` |
| `docs/orchestrator/components.md` | — | описывает компоненты | чинит ARCH-209 |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — четыре файла
- [x] `tests/**` (корень) — `tests/integration/test_autopilot_no_status_write.py`
      косвенно; **не правится**
- [x] `db/migrations/**` — нет
- [x] `ai/glossary/**` — не существует

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] `_parse_backlog` и `_bump_unparsable_counter` резолвятся из `orchestrator`

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/orchestrator.py` — bootstrap, главный цикл, реэкспорты (modify)
- `scripts/vps/orchestrator_slots.py` — слоты, pueue-опрос, git pull (NEW)
- `scripts/vps/orchestrator_backlog.py` — парсер backlog и bootstrap спек (NEW)
- `scripts/vps/orchestrator_inbox.py` — intake-гейт Hermes (NEW)
- `scripts/vps/orchestrator_queue.py` — очередь, зависимости, диспатч (NEW)
- `scripts/vps/tests/test_orchestrator.py` — перенацелить monkeypatch (modify)
- `scripts/vps/tests/test_orchestrator_bootstrap.py` — проверить связанный импорт (modify)
- `scripts/vps/tests/test_orchestrator_lifecycle.py` — импорты (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — bootstrap fail'ится в `queued`, никогда в `done` (ADR-026)
**Data model:** читает `ai/lifecycle/*.yaml`, пишет только через `lifecycle.*`

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

Дефектный след из git-истории: silent bootstrap-as-done на awardybot (ADR-026,
позиционный regex против дрейфа разметки backlog), ложная реконсиляция 2026-07-27,
ARCH-1246/FTR-1245 против незакрытой TECH-1244 (отсюда `AFTER`-зависимости).

---

## Approaches

### Approach 1: Flat siblings + разбор `scan_queued` (выбран)
**Source:** `research-web.md` § Approach 1; `research-devil.md` § Alternative 2
**Summary:** четыре новых модуля, `scan_queued` остаётся в `orchestrator_queue.py`, но её
тело раскладывается на шаги
**Pros:** имя точки входа не трогается, systemd-юниты на десяти VPS не переустанавливаются
**Cons:** три тест-файла правятся

### Approach 2: Только вынести модули, `scan_queued` не трогать
**Summary:** перенести 201-строчную функцию в `orchestrator_queue.py` как есть
**Pros:** меньше правок в самом чувствительном коде
**Cons:** лимит по файлу будет удовлетворён, а функция, в которой сидел баг реконсиляции,
останется ровно такой же нечитаемой. Это цель, подменённая метрикой

### Selected: 1
**Rationale:** Approach 2 удовлетворяет число и не удовлетворяет причину, по которой число
существует. `scan_queued` — то место, где уже пряталась ошибка.

---

## Design

### Раскол

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `orchestrator_slots.py` | `sync_projects`, `get_live_pueue_ids`, `pueue_has_active_label`, `pueue_has_active_spec`, `release_orphan_slots`, `is_agent_running`, `git_pull` | ~240 |
| `orchestrator_backlog.py` | `_parse_backlog`, `_bump_unparsable_counter`, `bootstrap_new_specs`, `_parse_priority_kind`, `cleanup_stale_stashes`, `startup_reconcile` | ~285 |
| `orchestrator_inbox.py` | `_parse_inbox_file`, `_pueue_add`, `scan_inbox` | ~145 |
| `orchestrator_queue.py` | `_AFTER_DEP_RE`, `_backlog_deps`, `_unmet_dependencies`, `scan_queued` (разобранная), `dispatch_night_review` | ~270 |
| `orchestrator.py` | `_load_env`, `_setup_logging`, `_signal_handler`, `_write_pid`, `process_project`, `_next_sleep`, `main`, реэкспорты | ~180 |

### Разбор `scan_queued`

201 строка → обёртка плюс шаги с говорящими именами внутри `orchestrator_queue.py`.
Обязанности видны из текущего тела:

1. взять `queued`/`resumed` из lifecycle
2. пройти гейт реконсиляции (`gate_logic.parse_allowed_files` → `fetch_develop` →
   `find_implementation_commit`), при попадании — пометить `done` и не диспатчить
3. проверить незакрытые `AFTER`-зависимости
4. проверить готовность спеки
5. `_pueue_add` и запись `in_progress`

Каждый шаг — отдельная функция. Обёртка `scan_queued` сохраняет имя, сигнатуру и
контракт возврата (`bool` — «задиспатчено ли»).

### Реэкспорты

```python
# orchestrator.py — тест ADR-026 связывает эти два имени при импорте
from orchestrator_backlog import _parse_backlog, _bump_unparsable_counter  # noqa: F401
```

Это единственное место, где связанная форма допустима: она обслуживает существующий
контракт теста, а не внутренний вызов. Все внутренние вызовы — через атрибут модуля.

---

## Implementation Plan

### Research Sources
- `research-codebase.md` §1 (`orchestrator.py`) — карта с диапазонами строк
- `research-devil.md` § Alternative 2 — extract-function как настоящее лекарство
- `.claude/rules/architecture.md` ADR-021, ADR-022, ADR-023, ADR-026

### Task 1: Слоты и pueue
**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_slots.py`
  - modify: `scripts/vps/orchestrator.py`
  - modify: `scripts/vps/tests/test_orchestrator_git_pull.py`
**Pattern:** `orchestrator_monitor.py` — уже существующий sibling с тем же неймингом
**Acceptance:** `test_orchestrator_git_pull.py` зелёный

### Task 2: Backlog и bootstrap
**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_backlog.py`
  - modify: `scripts/vps/orchestrator.py`
  - modify: `scripts/vps/tests/test_orchestrator_bootstrap.py`
**Pattern:** Task 1
**Acceptance:** связанный импорт на строке 28 резолвится; ADR-026 соблюдён —
неразобранный статус даёт `queued` плюс WARNING `BOOTSTRAP_UNPARSABLE`

### Task 3: Inbox
**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_inbox.py`
  - modify: `scripts/vps/orchestrator.py`
**Pattern:** Task 1
**Acceptance:** диспатчатся только `Status: queued`; `new`/`draft`/`clarifying`/`stale`/`rejected` игнорируются

### Task 4: Очередь и разбор `scan_queued`
**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_queue.py`
  - modify: `scripts/vps/orchestrator.py`
  - modify: `scripts/vps/tests/test_orchestrator.py`
  - modify: `scripts/vps/tests/test_orchestrator_lifecycle.py`
**Pattern:** пошаговая структура из § Design
**Acceptance:** ни одна функция в модуле не длиннее 80 строк; `TestReconciliationGate`
в `test_orchestrator.py` зелёный

### Task 5: Довести до лимита
**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.py`
**Pattern:** —
**Acceptance:** все пять файлов ≤ 400 LOC

### Execution Order
1 → 2 → 3 → 4 → 5

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Слоты и pueue вынесены | Task 1 | ✓ |
| 2 | Bootstrap вынесен, ADR-026 цел | Task 2 | ✓ |
| 3 | Intake-гейт вынесен | Task 3 | ✓ |
| 4 | `scan_queued` читается по частям | Task 4 | ✓ |
| 5 | Все файлы под 400 | Task 5 | ✓ |
| 6 | systemd не переустанавливается | — | имя сохранено |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Гейт не закрывает спеку против birth-коммита | allowlist только с `ai/lifecycle/X.yaml` | спека диспатчится, не `done` | deterministic | инцидент 2026-07-27 | P0 |
| EC-2 | Bootstrap при неразобранном статусе | backlog со сдвинутой разметкой | `queued` + WARNING, **не** `done` | deterministic | ADR-026 | P0 |
| EC-3 | `AFTER` блокирует диспатч | спека с `AFTER TECH-210`, та не `done` | не диспатчится | deterministic | ARCH-1246 | P0 |
| EC-4 | Отсутствующая зависимость считается закрытой | `AFTER` на несуществующий ID | диспатчится | deterministic | текущий docstring | P1 |
| EC-5 | Intake пропускает только `queued` | пять файлов inbox с разными статусами | обработан один | deterministic | ADR-021 | P0 |
| EC-6 | Грязный `ai/lifecycle/` прерывает старт | грязное дерево | `main` падает на `assert_clean_lifecycle_tree` | deterministic | ADR-023 | P0 |
| EC-7 | Связанный импорт теста цел | `from orchestrator import _parse_backlog, _bump_unparsable_counter` | без ошибок | deterministic | codebase §3 | P0 |
| EC-8 | Ни одной длинной функции | AST-обход `orchestrator_queue.py` | max тело ≤ 80 строк | deterministic | Why | P1 |
| EC-9 | Все файлы под лимитом | `wc -l scripts/vps/orchestrator*.py` | каждый ≤ 400 | deterministic | user | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-10 | Проект с одной `queued` спекой | полный цикл `process_project` | pueue-задача создана, lifecycle → `in_progress` | integration | ADR-023 | P0 |
| EC-11 | systemd-юнит дословно | `ExecStart` из `setup-vps.sh:456` | демон стартует, пишет pid | integration | devil SA-7 | P0 |

### Coverage Summary
Deterministic: 9 | Integration: 2 | LLM-Judge: 0 | Total: 11 (min 3 ✓)

### TDD Order
1. EC-1, EC-2, EC-3, EC-5 — характеризация гейтов до резки
2. EC-6, EC-7 — контракты старта и импортов
3. EC-10, EC-11 — интеграция
4. EC-4, EC-8, EC-9 — форма

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Модули импортируемы | `PYTHONPATH=scripts/vps python -c "import orchestrator"` | exit 0 | 15s |
| AV-S2 | Скрипт компилируется | `python -m py_compile scripts/vps/orchestrator.py` | exit 0 | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты оркестратора | — | `cd scripts/vps/tests && python -m pytest -q -k orchestrator` | 0 failed |
| AV-F2 | Весь VPS-набор | — | `cd scripts/vps/tests && python -m pytest -q` | 0 failed |
| AV-F3 | Демон стартует на VPS | VPS | `systemctl --user restart dld-orchestrator && systemctl --user is-active dld-orchestrator` | `active` |
| AV-F4 | Цикл проходит | VPS | `journalctl --user -u dld-orchestrator -n 50` после одного цикла | нет traceback, есть строка опроса проектов |

### Verify Command

```bash
python -m py_compile scripts/vps/orchestrator.py
PYTHONPATH=scripts/vps python -c "import orchestrator, orchestrator_slots, orchestrator_backlog, orchestrator_inbox, orchestrator_queue"
wc -l scripts/vps/orchestrator*.py
cd scripts/vps/tests && python -m pytest -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `orchestrator.py` и четыре новых модуля ≤ 400 LOC
- [ ] `scan_queued` разобрана, ни одной функции длиннее 80 строк
- [ ] Имя точки входа не изменилось

### Tests
- [ ] EC-1..EC-11 проходят
- [ ] `test_orchestrator.py::TestReconciliationGate` зелёный

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2 локально
- [ ] AV-F3, AV-F4 на VPS — демон держит код в памяти, рестарт обязателен

### Technical
- [ ] ADR-021/022/023/026 соблюдены
- [ ] Внутренние вызовы — через атрибут модуля, не связанным именем

---

## Autopilot Log
