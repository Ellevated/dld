# Feature: [TECH-214] Раскол lifecycle.py

**Priority:** P1 | **Date:** 2026-07-27
**Size:** 5 tasks / 11 files — неделимо, потому что общее модульное состояние
(`_write_lock`, `_ALLOWED_WRITERS`, `LIFECYCLE_DIR`) читается всеми группами сразу:
вынести половину групп, оставив состояние в старом месте, значит создать цикл импорта,
который потом придётся разбирать второй задачей.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`lifecycle.py` — 1163 LOC при лимите 400. Это тот самый файл, из которого 2026-07-27 была
взята `list_by_status()` с предположением, что она возвращает список `spec_id`. Она
возвращает список словарей, и её собственный docstring на строке 715 это говорит прямым
текстом: «Returns sorted list of dicts». Строку не прочитали, потому что файл не читают
целиком — из него берут функцию по имени.

Ошибка стоила молчаливого «0 кандидатов» в operator-скрипте восстановления при пяти
реальных, и всплыла только на живом прогоне на VPS.

Это единственный файл в дереве, где такая ошибка **необратима по построению**: он несёт
Rule 7 (ADR-025) — `done` терминален, и ошибочно записанный `done` нельзя откатить ни
одним штатным путём. Узкий escape пришлось писать отдельно, в тот же день.

## Context

### Что живёт в файле

| Группа | Строки | Содержимое |
|---|---|---|
| `errors` | 77-137 | `LifecycleWriteRaceError`, `LifecycleAlreadyDoneError`, `NotBootstrapArtifactError`, `NotFalseReconciliationError` |
| `gitplumbing` | 139-557 | `_now_iso`, `_run` (публичный алиас `run_git`), `_decode`, `_current_branch`, `_read_yaml_from_head`, `_build_yaml_content`, `_atomic_write`, `_push_best_effort`, `_try_push`, `_local_ahead_is_lifecycle_only`, `_rebase_onto_origin`, `_bump_push_failure_counter` |
| `cas` | 557-759 | `_cas_loop`, `read_lifecycle`, `write_lifecycle`, `create_initial`, `list_by_status`, `assert_clean_lifecycle_tree` |
| `filewriter` | 759-879 | `write_file_atomic`, `_atomic_write_file` |
| `recovery` | 879-1117 | `reconcile_orphans`, `recover_bootstrap_artifact`, `recover_false_reconciliation` |
| `helpers` | 1117-1163 | `now_iso`, `build_initial_yaml` |

### Общее модульное состояние — главная опасность раскола

| Символ | Строка | Кто читает |
|---|---|---|
| `_write_lock` (`threading.Lock`) | 74 | `cas` **и** `filewriter` |
| `_ALLOWED_WRITERS` | 59 | `write_lifecycle` |
| `_ALLOWED_WRITERS_FOR_CREATE` | 66 | `create_initial` |
| `LIFECYCLE_DIR` | 46 | `cas`, `recovery`, `render_backlog.py`, `lifecycle_audit.py` |
| `MAX_CAS_RETRIES` | 47 | `_cas_loop` |

`_write_lock` — не константа, а объект с состоянием. Если раскол создаст **два экземпляра
Lock** (например, каждый модуль заведёт свой), взаимное исключение перестанет работать,
и отказ будет молчаливым: ни исключения, ни лога, только редкая гонка при записи
в git-индекс. Это тот же класс, что `list_by_status`, только страшнее.

### Кто зависит

| Потребитель | Форма импорта | Символы |
|---|---|---|
| `callback.py` | `import lifecycle` | `read_lifecycle`, `write_lifecycle`, `write_file_atomic` |
| `orchestrator.py` | `import lifecycle` | `read_lifecycle`, `write_lifecycle`, `list_by_status`, `create_initial`, `assert_clean_lifecycle_tree`, `reconcile_orphans` |
| `lifecycle_audit.py` | `import lifecycle` | `LIFECYCLE_DIR` и чтение |
| `recover_bootstrap_as_done.py` | `import lifecycle` | `recover_bootstrap_artifact`, `NotBootstrapArtifactError` |
| `recover_false_reconciliation.py` | `import lifecycle` | `list_by_status`, `recover_false_reconciliation`, `NotFalseReconciliationError` |
| `spec_operator.py` | `import lifecycle` | `LifecycleWriteRaceError`, `LifecycleAlreadyDoneError` |
| `salvage.py` | **`from lifecycle import run_git as _git`** | связывает имя при импорте |
| `render_backlog.py` | **`from lifecycle import LIFECYCLE_DIR`** | связывает имя |
| `migrate_backlog_to_lifecycle.py` | **`from lifecycle import build_initial_yaml`** | связывает имя |

Три последних связывают имя в момент импорта. Значит `run_git`, `LIFECYCLE_DIR` и
`build_initial_yaml` обязаны остаться резолвимыми из `lifecycle` — иначе три модуля
падают на импорте.

### Покрытие — самое плотное в дереве

Шесть тест-файлов, 1800 LOC тестов на 1163 LOC исходника: `test_lifecycle.py` (649),
`test_lifecycle_done_terminal.py` (392), `test_lifecycle_push_rebase.py` (255),
`test_lifecycle_wt_sync.py` (211), `test_lifecycle_run_encoding.py` (159),
`test_lifecycle_create_initial.py` (134). Это и есть регрессионная сеть раскола.

---

## Scope

**In scope:** вынос `errors`, `gitplumbing`, `cas`-механики, `push`-механики и `recovery`
в flat sibling-модули; единственный экземпляр `_write_lock`; `lifecycle.py` ≤400 LOC с
сохранением всех публичных имён.

**Out of scope:** изменение Rule 7 (ADR-025) — она остаётся структурно в
`write_lifecycle`; изменение формата YAML; изменение CAS-протокола; трогать
`recover_*.py` operator-скрипты (публичный API сохраняется, они не правятся).

---

## Impact Tree Analysis

### Step 1: UP — who uses?

`grep -rn "import lifecycle\|from lifecycle import" . --include="*.py"` → 9 модулей
(таблица «Кто зависит») + 6 тест-файлов + корневой
`tests/integration/test_lifecycle_identity.py`.

### Step 2: DOWN — what depends on?

`lifecycle.py` → stdlib + `yaml`. Ни одного из восьми файлов. Лист графа.

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/salvage.py` | 35 | `from lifecycle import run_git as _git` | `run_git` остаётся в `lifecycle` |
| `scripts/vps/render_backlog.py` | 30 | `from lifecycle import LIFECYCLE_DIR` | реэкспорт обязателен |
| `scripts/vps/migrate_backlog_to_lifecycle.py` | 27 | `from lifecycle import build_initial_yaml` | реэкспорт обязателен |
| `scripts/vps/tests/test_lifecycle.py` | 8 приватных ссылок | monkeypatch | перенацелить на модуль, где функция осела |
| `scripts/vps/tests/test_lifecycle_push_rebase.py` | 8 | monkeypatch push-механики | перенацелить |
| `scripts/vps/tests/test_lifecycle_run_encoding.py` | 7 | `lifecycle._run`, байтовый I/O | перенацелить |
| `scripts/vps/tests/test_lifecycle_done_terminal.py` | 1 | Rule 7 | **не должен потребовать правки** — Rule 7 не переезжает |
| `docs/orchestrator/status-model.md` | 9 цитат `lifecycle.py:NNN` | номера строк | чинит ARCH-209 |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — 4 из 6 файлов требуют правки импортов
- [x] `tests/**` (корень) — `tests/integration/test_lifecycle_identity.py` **не правится**
      (работает через публичный API)
- [x] `db/migrations/**` — нет
- [x] `ai/glossary/**` — не существует; `lifecycle.py:26` ссылается на несуществующий
      `ai/glossary/orchestrator.md`, предсуществующий дрейф, чинит ARCH-209

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] Три связанных импорта (`run_git`, `LIFECYCLE_DIR`, `build_initial_yaml`) резолвятся

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/lifecycle.py` — публичный API, Rule 7, реэкспорты (modify)
- `scripts/vps/lifecycle_const.py` — константы и единственный `_write_lock` (NEW)
- `scripts/vps/lifecycle_errors.py` — четыре класса исключений (NEW)
- `scripts/vps/lifecycle_git.py` — примитивы git и сборка YAML (NEW)
- `scripts/vps/lifecycle_cas.py` — атомарная запись и CAS-цикл (NEW)
- `scripts/vps/lifecycle_push.py` — push, rebase, счётчик отказов (NEW)
- `scripts/vps/lifecycle_recovery.py` — три узких escape из Rule 7 (NEW)
- `scripts/vps/tests/test_lifecycle.py` — перенацелить monkeypatch (modify)
- `scripts/vps/tests/test_lifecycle_push_rebase.py` — перенацелить monkeypatch (modify)
- `scripts/vps/tests/test_lifecycle_run_encoding.py` — перенацелить monkeypatch (modify)
- `scripts/vps/tests/test_lifecycle_wt_sync.py` — перенацелить monkeypatch (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator — SoT статусов спек
**Cross-cutting:** Errors — fail-closed; Rule 7 (ADR-025) структурна в `write_lifecycle`
**Data model:** `ai/lifecycle/{spec_id}.yaml`, формат не меняется

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

Дефектный след из git-истории: BUG-185 (autostash race, закрыт ADR-023),
bootstrap-as-done на awardybot (ADR-026), ложная реконсиляция 2026-07-27,
`_run` с `text=True` и cp1251 (2026-07-26).

---

## Risk Classification

**R1, не R0.** Рассмотрено и отклонено: R0 требует необратимости, слома публичного API,
миграции схемы или утечки. Здесь ничего из этого нет — публичные имена сохраняются по
построению, формат YAML не трогается, откат делается `git revert` плюс рестарт демонов.

Необратимой эта область становится **если дефект просочится**: ошибочный `done`
терминален. Но это верно для любой правки `lifecycle.py`, включая ту, что была сделана
2026-07-27 без совета. Классифицировать каждое касание как R0 значит обесценить R0.

Что из этого следует практически: плотность тестов здесь выше, чем в любой другой из семи
задач (11 EC), и деплой обязан включать рестарт демонов и прогон `lifecycle_audit.py`
до и после.

---

## Approaches

### Approach 1: Константы в отдельный лист, механика в siblings, публичный API на месте (выбран)
**Source:** `research-web.md` § Approach 1; `research-codebase.md` §1
**Summary:** `lifecycle_const.py` — чистый лист без импортов, все остальные модули
импортируют его; `lifecycle.py` остаётся фасадом с публичными именами
**Pros:** `_write_lock` физически один — модуль-константы импортируется один раз, Python
кэширует его в `sys.modules`; три связанных импорта продолжают работать
**Cons:** шесть новых файлов вместо трёх-четырёх

### Approach 2: Оставить константы в `lifecycle.py`, siblings импортируют его обратно
**Summary:** `lifecycle_cas.py` делает `import lifecycle` ради `_write_lock`
**Cons:** цикл. `lifecycle` импортирует `lifecycle_cas`, тот импортирует `lifecycle`.
Python это переживёт при аккуратном порядке, но получится ровно та конструкция, которая
ломается от перестановки строк — и ломается на импорте, то есть на старте демона

### Approach 3: Передавать lock параметром
**Summary:** `_cas_loop(repo, spec_id, branch, make_yaml, lock=...)`
**Pros:** явная зависимость, ноль общего состояния
**Cons:** меняет сигнатуры внутренних функций, на которые целятся 24 monkeypatch в
четырёх тест-файлах; выигрыш чисто эстетический — lock здесь всё равно процессный синглтон

### Selected: 1
**Rationale:** единственный вариант, который даёт один экземпляр Lock без цикла импорта и
без правки сигнатур. Приём стандартный: модуль-константы как лист графа — та же роль,
что у `gate_logic.py` для гейта.

---

## Design

### Раскол

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `lifecycle_const.py` | `LIFECYCLE_DIR`, `MAX_CAS_RETRIES`, `_ALLOWED_WRITERS`, `_ALLOWED_WRITERS_FOR_CREATE`, `_VALID_PRIORITIES`, `_write_lock` | ~40 |
| `lifecycle_errors.py` | четыре класса исключений | ~65 |
| `lifecycle_git.py` | `_now_iso`, `_run`, `_decode`, `_current_branch`, `_read_yaml_from_head`, `_build_yaml_content` | ~210 |
| `lifecycle_cas.py` | `_atomic_write`, `_atomic_write_file`, `_cas_loop` | ~230 |
| `lifecycle_push.py` | `_push_best_effort`, `_try_push`, `_local_ahead_is_lifecycle_only`, `_rebase_onto_origin`, `_bump_push_failure_counter` | ~185 |
| `lifecycle_recovery.py` | `reconcile_orphans`, `recover_bootstrap_artifact`, `recover_false_reconciliation` | ~245 |
| `lifecycle.py` | `read_lifecycle`, `write_lifecycle` (**Rule 7 здесь**), `create_initial`, `list_by_status`, `assert_clean_lifecycle_tree`, `write_file_atomic`, `now_iso`, `build_initial_yaml`, `run_git`, реэкспорты | ~300 |

### Направление импортов (жёсткое)

```
lifecycle_const  ← лист, ноль импортов из scripts/vps/
     ↑
lifecycle_errors ← только stdlib
     ↑
lifecycle_git ── lifecycle_cas ── lifecycle_push ── lifecycle_recovery
     ↑                                                      ↑
     └──────────────── lifecycle.py ────────────────────────┘
```

Ни один sibling не импортирует `lifecycle`. Тот же инвариант, что `gate_logic.py:19`.

### Rule 7 не переезжает

`write_lifecycle` остаётся в `lifecycle.py` вместе с проверкой:

```python
if status != "done":
    _existing_head = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
    if _existing_head and _existing_head.get("status") == "done":
        raise LifecycleAlreadyDoneError(...)
```

ADR-025 состоит именно в том, что Rule 7 структурна в примитиве записи, а не в вызывающем.
Перенос её в sibling с последующим делегированием заново открывает вопрос «а все ли пути
записи её проходят». Она остаётся там, где её ищут.

### Реэкспорты для трёх связанных импортов

```python
from lifecycle_const import LIFECYCLE_DIR, MAX_CAS_RETRIES   # render_backlog.py
run_git = lifecycle_git._run                                  # salvage.py
# build_initial_yaml определена прямо здесь                   # migrate_backlog_to_lifecycle.py
```

---

## Implementation Plan

### Research Sources
- `research-codebase.md` §1 (`lifecycle.py`) — карта групп и общего состояния
- `research-web.md` § Best Practice 3 — сохранить публичный шов, вынести потроха
- `.claude/rules/architecture.md` ADR-023, ADR-025, ADR-026, ADR-027

### Task 1: Константы и исключения
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_const.py`
  - create: `scripts/vps/lifecycle_errors.py`
  - modify: `scripts/vps/lifecycle.py`
**Pattern:** `gate_logic.py` — лист графа, ноль I/O на импорте
**Acceptance:** `lifecycle._write_lock is lifecycle_const._write_lock` → `True`;
все шесть тест-файлов зелёные без правок

### Task 2: Примитивы git
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_git.py`
  - modify: `scripts/vps/lifecycle.py`
  - modify: `scripts/vps/tests/test_lifecycle_run_encoding.py`
**Pattern:** Task 1
**Acceptance:** `_run` по-прежнему возвращает декодированный `str`, `cwd` keyword-only;
байтовый I/O сохранён (нет `text=True`)

### Task 3: CAS и push
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_cas.py`
  - create: `scripts/vps/lifecycle_push.py`
  - modify: `scripts/vps/lifecycle.py`
  - modify: `scripts/vps/tests/test_lifecycle_push_rebase.py`
  - modify: `scripts/vps/tests/test_lifecycle_wt_sync.py`
**Pattern:** Task 1
**Acceptance:** `git status --porcelain` после записи пуст (инвариант «No dirty WT»,
TECH-194 Layer D); CAS-гонка по-прежнему даёт `LifecycleWriteRaceError` после
`MAX_CAS_RETRIES`

### Task 4: Recovery
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_recovery.py`
  - modify: `scripts/vps/lifecycle.py`
  - modify: `scripts/vps/tests/test_lifecycle.py`
**Pattern:** Task 1
**Acceptance:** три escape по-прежнему валидируют свои сигнатуры и бросают
`NotBootstrapArtifactError` / `NotFalseReconciliationError` на несовпадении

### Task 5: Довести до лимита
**Type:** code
**Files:**
  - modify: `scripts/vps/lifecycle.py`
**Pattern:** —
**Acceptance:** `wc -l scripts/vps/lifecycle.py` ≤ 400; все семь файлов ≤ 400

### Execution Order
1 → 2 → 3 → 4 → 5

Каждая задача — отдельный коммит с зелёным прогоном. Порядок снизу вверх по графу: лист
первым, фасад последним.

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Общее состояние в одном экземпляре | Task 1 | ✓ |
| 2 | Три связанных импорта резолвятся | Task 1, 2 | ✓ |
| 3 | Rule 7 на месте | — | не переезжает (design) |
| 4 | CAS и push не изменили поведение | Task 3 | ✓ |
| 5 | Escape'ы валидируют как раньше | Task 4 | ✓ |
| 6 | Все файлы под 400 | Task 5 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Lock — один экземпляр | `lifecycle._write_lock is lifecycle_cas._write_lock` | `True` | deterministic | design | P0 |
| EC-2 | Rule 7 цела | `write_lifecycle` на спеке со статусом `done`, новый статус `queued` | `LifecycleAlreadyDoneError` | deterministic | ADR-025 | P0 |
| EC-3 | Rule 7 у всех writer'ов | цикл по `_ALLOWED_WRITERS` | исключение для каждого | deterministic | ADR-025 | P0 |
| EC-4 | `list_by_status` возвращает словари | вызов на репозитории с 3 спеками | `list[dict]`, ключ `spec_id` присутствует | deterministic | инцидент 2026-07-27 | P0 |
| EC-5 | Working tree не грязнится | `write_lifecycle`, затем `git status --porcelain` | пусто | deterministic | TECH-194 Layer D | P0 |
| EC-6 | Байтовый git I/O | ветка с кириллицей и CRLF | без `UnicodeDecodeError` | deterministic | фикс 2026-07-26 | P0 |
| EC-7 | Связанные импорты живы | импорт `salvage`, `render_backlog`, `migrate_backlog_to_lifecycle` | без ошибок | deterministic | codebase §3 | P0 |
| EC-8 | `spark` не может писать статус | `write_lifecycle(..., by="spark")` | `ValueError` | deterministic | ADR-025 | P0 |
| EC-9 | `spark` может клеймить ID | `create_initial(..., by="spark", status="queued")` | успех | deterministic | ADR-027 | P0 |
| EC-10 | Siblings не импортируют фасад | `grep "^import lifecycle$\|^from lifecycle import" scripts/vps/lifecycle_*.py` | 0 попаданий | deterministic | design | P0 |
| EC-11 | Все файлы под лимитом | `wc -l scripts/vps/lifecycle*.py` | каждый ≤ 400 | deterministic | user | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-12 | Два процесса пишут одну спеку | одновременный `write_lifecycle` | один побеждает, второй получает `LifecycleWriteRaceError`, YAML не повреждён | integration | ADR-023 | P0 |
| EC-13 | Аудитор до и после | `lifecycle_audit.py` на том же репозитории | ноль новых категорий дрейфа | integration | ADR-026 | P0 |

### Coverage Summary
Deterministic: 11 | Integration: 2 | LLM-Judge: 0 | Total: 13 (min 3 ✓)

### TDD Order
1. EC-1 — до всякой резки: доказать, что схема с модулем-константами даёт один Lock
2. EC-2, EC-3, EC-8, EC-9 — Rule 7 и writer-гейт, характеризация
3. EC-4..EC-7 — контракты, на которых уже обжигались
4. EC-12, EC-13 — интеграция
5. EC-10, EC-11 — форма

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Все модули импортируемы | `PYTHONPATH=scripts/vps python -c "import lifecycle"` | exit 0 | 15s |
| AV-S2 | Потребители со связанным импортом | `PYTHONPATH=scripts/vps python -c "import salvage, render_backlog, migrate_backlog_to_lifecycle"` | exit 0 | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Все шесть тестов lifecycle | — | `cd scripts/vps/tests && python -m pytest -q -k lifecycle` | 0 failed |
| AV-F2 | Весь VPS-набор | — | `cd scripts/vps/tests && python -m pytest -q` | 0 failed |
| AV-F3 | Корневая интеграция | — | `python -m pytest tests/integration/test_lifecycle_identity.py -q` | passed, файл не правился |
| AV-F4 | Аудит дрейфа на VPS | VPS | `python3 scripts/vps/lifecycle_audit.py` до и после деплоя | `diff` пуст |
| AV-F5 | Демоны на новом коде | VPS | `systemctl --user restart dld-orchestrator dld-gate-daemon && systemctl --user is-active dld-orchestrator dld-gate-daemon` | `active` дважды |

### Verify Command

```bash
PYTHONPATH=scripts/vps python -c "import lifecycle, salvage, render_backlog, migrate_backlog_to_lifecycle"
PYTHONPATH=scripts/vps python -c "import lifecycle, lifecycle_cas; assert lifecycle._write_lock is lifecycle_cas._write_lock"
wc -l scripts/vps/lifecycle*.py
cd scripts/vps/tests && python -m pytest -q
python -m pytest tests/integration/test_lifecycle_identity.py -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `lifecycle.py` и шесть новых модулей ≤ 400 LOC каждый
- [ ] `_write_lock` — ровно один экземпляр
- [ ] Rule 7 осталась в `write_lifecycle`
- [ ] Ни один sibling не импортирует `lifecycle`

### Tests
- [ ] EC-1..EC-13 проходят
- [ ] `test_lifecycle_done_terminal.py` зелёный **без правок** — Rule 7 не двигалась
- [ ] `tests/integration/test_lifecycle_identity.py` зелёный без правок

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2, AV-F3 локально
- [ ] AV-F4 — аудит дрейфа чист до и после
- [ ] AV-F5 — рестарт демонов; без него живёт старый код

### Technical
- [ ] Формат YAML не изменён
- [ ] CAS-протокол не изменён
- [ ] `git status --porcelain` пуст после записи

---

## Autopilot Log
