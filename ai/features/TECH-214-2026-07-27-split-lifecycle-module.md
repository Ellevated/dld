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
- **Внутрирепозиторный прецедент вместо веб-поиска:** TECH-211 (`heartbeat_reaper.py`
  459→255, `lifecycle_audit.py` 525→254) и TECH-212 (`db.py` 602→373 + три листа,
  публичный API байт-в-байт) смёржены 27–28.07. Два одинаковых раскола за 48 часов в
  этом же дереве — более сильное свидетельство, чем любая внешняя статья; веб-запросы
  не делались осознанно.

### Проверка дрейфа (2026-07-28, worktree TECH-214)

`lifecycle.py` = **1163 LOC, не изменялся** с момента написания спеки. Групповые границы
из секции Context совпадают с реальностью. Ниже — точная посимвольная карта; **все номера
строк относятся к исходному файлу до Task 1**, после первого коммита они смещаются —
переносите по именам, номера нужны только для первой выемки.

| Строки | Символ | Уезжает в |
|---|---|---|
| 1-27 | module docstring | остаётся (переписать в Task 5) |
| 29-42 | импорты | остаётся (прореживать по задачам) |
| 44 | `log = logging.getLogger(__name__)` | остаётся + копия в каждом sibling |
| 46 | `LIFECYCLE_DIR` | `lifecycle_const` |
| 47 | `MAX_CAS_RETRIES` | `lifecycle_const` |
| 48-51 | `_PUSH_REBASE_RETRIES` (**нет в таблицах спеки**) | `lifecycle_const` |
| 52-59 | `_ALLOWED_WRITERS` (+ комментарий ADR-025) | `lifecycle_const` |
| 61-66 | `_ALLOWED_WRITERS_FOR_CREATE` | `lifecycle_const` |
| 68-69 | `_VALID_PRIORITIES` | `lifecycle_const` |
| 71-74 | `_write_lock` | `lifecycle_const` |
| 77-84 | `LifecycleWriteRaceError` (default arg = `MAX_CAS_RETRIES`) | `lifecycle_errors` |
| 86-100 | `LifecycleAlreadyDoneError` | `lifecycle_errors` |
| 103-116 | `NotBootstrapArtifactError` | `lifecycle_errors` |
| 119-131 | `NotFalseReconciliationError` | `lifecycle_errors` |
| 139-140 | `_now_iso` | `lifecycle_git` |
| 143-181 | `_run` (**`_decode` — вложенная функция 178-179, отдельным символом не существует**) | `lifecycle_git` |
| 184-187 | `run_git = _run` + комментарий | `lifecycle_git` |
| 190-194 | `_current_branch` | `lifecycle_git` |
| 197-204 | `_read_yaml_from_head` | `lifecycle_git` |
| 207-267 | `_build_yaml_content` | `lifecycle_git` |
| 270-404 | `_atomic_write` (ленивый `import render_backlog` на 326) | `lifecycle_cas` |
| 407-440 | `_push_best_effort` | `lifecycle_push` |
| 443-457 | `_try_push` | `lifecycle_push` |
| 460-489 | `_local_ahead_is_lifecycle_only` | `lifecycle_push` |
| 492-544 | `_rebase_onto_origin` | `lifecycle_push` |
| 547-554 | `_bump_push_failure_counter` | `lifecycle_push` |
| 557-583 | `_cas_loop` | `lifecycle_cas` |
| 591-598 | `read_lifecycle` | остаётся |
| 601-642 | `write_lifecycle` (**Rule 7 — 623-626**) | остаётся |
| 645-706 | `create_initial` (Rule 7 mirror — 689-691) | остаётся |
| 709-743 | `list_by_status` | остаётся |
| 746-756 | `assert_clean_lifecycle_tree` | остаётся |
| 759-803 | `write_file_atomic` | остаётся |
| 806-876 | `_atomic_write_file` | `lifecycle_cas` |
| 879-898 | `reconcile_orphans` | **остаётся** (см. «Отклонения», DAG) |
| 901-989 | `recover_bootstrap_artifact` | `lifecycle_recovery` |
| 992-1114 | `recover_false_reconciliation` | `lifecycle_recovery` |
| 1117-1119 | `now_iso` | остаётся |
| 1122-1163 | `build_initial_yaml` | остаётся |

Потребители перепроверены: 11 модулей `import lifecycle` / `from lifecycle import`
(в таблице Context девять — не хватает `gate-daemon.py:44` и `audit_categories.py:21`,
оба используют только публичные имена + `LIFECYCLE_DIR`). Связанных при импорте —
ровно три, как и сказано: `salvage.py:35 run_git`, `render_backlog.py:30 LIFECYCLE_DIR`,
`migrate_backlog_to_lifecycle.py:28 build_initial_yaml`.

### Инварианты раскола — нарушение любого даёт молчаливый отказ

**И-1. Кросс-модульный вызов функции — только через модуль.**
```python
import lifecycle_git
r = lifecycle_git._run(["git", "rev-parse", "HEAD"], cwd=repo_dir)   # ДА
from lifecycle_git import _run                                       # НЕТ
```
Причина: тесты подменяют `lifecycle_git._run` (`test_lifecycle.py:123/352/362`). Имя,
связанное при импорте в другом модуле, подмену не увидит — patch применится, тест
позеленеет, а проверять будет нечего. Это ровно тот класс отказа, из-за которого спека
существует.

**И-2. Константы, классы исключений и `run_git` — только по имени (`from … import`).**
```python
from lifecycle_const import LIFECYCLE_DIR, MAX_CAS_RETRIES, _ALLOWED_WRITERS, _write_lock
from lifecycle_errors import LifecycleWriteRaceError
```
Причина: (а) EC-1 требует `lifecycle._write_lock is lifecycle_cas._write_lock` — атрибут
обязан существовать в обоих модулях; (б) файлы **вне** Allowed Files читают приватные
константы через фасад и правиться не могут:
`tests/integration/test_lifecycle_identity.py:86,95,163` (`lifecycle._ALLOWED_WRITERS`),
`test_lifecycle_done_terminal.py:247` (`lifecycle._ALLOWED_WRITERS` в `@parametrize`,
вычисляется на импорте модуля), `test_lifecycle.py:520-523`.
`_write_lock` никогда не переприсваивается, поэтому связывание имени безопасно.

**И-3. Приватные имена НЕ реэкспортируются фасадом** (кроме констант из И-2).
Никаких `_run = lifecycle_git._run`, `_push_best_effort = …`, `_atomic_write = …` в
`lifecycle.py`. Такой алиас превращает `patch.object(lifecycle, "_run", …)` в
no-op, который проходит молча. Тесты перенацеливаются на модуль-владелец.

**И-4. Ни один sibling не импортирует `lifecycle`.** Проверка — явным списком файлов,
а не glob'ом: `scripts/vps/lifecycle_*.py` матчит предсуществующий `lifecycle_audit.py`,
который `import lifecycle` делает (строка 58) и от regex `^import lifecycle$` спасается
только хвостовым `# noqa`.
```bash
grep -nE "^[[:space:]]*(import lifecycle([[:space:]]|$)|from lifecycle import)" \
  scripts/vps/lifecycle_const.py scripts/vps/lifecycle_errors.py \
  scripts/vps/lifecycle_git.py scripts/vps/lifecycle_cas.py \
  scripts/vps/lifecycle_push.py scripts/vps/lifecycle_recovery.py
# ожидание: пустой вывод, rc=1
```

**И-5. Линтер.** ruff `select = ["E","F","W","I"]`, `line-length = 100`, `E501` ignored.
Реэкспорты требуют `# noqa: F401`. Локальные модули идут в ту же секцию, что `yaml`
(прецедент `render_backlog.py:29-30`): сначала `import x` по алфавиту, затем `from x import`.
После каждой задачи — `ruff check scripts/vps/` = 0 ошибок; лишние stdlib-импорты в
`lifecycle.py` удалять в той же задаче, где уехал последний потребитель.

**И-6. Заголовок модуля** по конвенции CLAUDE.md: `Module/Role/Uses/Used by`.
Строку `Glossary:` в новых файлах **не писать** — `ai/glossary/orchestrator.md` не
существует (предсуществующий дрейф `lifecycle.py:26`, чинит ARCH-209); тиражировать
мёртвый указатель шестикратно незачем.

**Базовая линия до Task 1** (записать числа, они — эталон на все пять задач):
```bash
cd scripts/vps/tests && python -m pytest -q          # ожидание: 0 failed
cd ../../.. && python -m pytest tests/ -q            # 3 падения предсуществуют на develop
                                                     # (дневник BUG-218) — их число не должно расти
ruff check scripts/vps/
wc -l scripts/vps/lifecycle.py                       # 1163
```

### Task 1: Константы и исключения
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_const.py` (~45 LOC)
  - create: `scripts/vps/lifecycle_errors.py` (~70 LOC)
  - modify: `scripts/vps/lifecycle.py`
**Pattern:** `gate_logic.py` — лист графа, ноль I/O на импорте

**Шаги:**
1. `lifecycle_const.py` — заголовок + `import threading` + строки **46-74 дословно**
   (включая все комментарии ADR-025 / ARCH-196 / TECH-200 и блок про in-process lock):
```python
"""
Module: lifecycle_const
Role: Leaf of the lifecycle module graph — every module-level constant plus the
      single process-wide write lock. Imported (never imports), so the Lock
      exists exactly once per process: Python caches the module in sys.modules.

Uses:
  - threading: Lock

Used by:
  - lifecycle.py, lifecycle_errors.py, lifecycle_cas.py, lifecycle_push.py,
    lifecycle_recovery.py
"""

import threading

# <<< строки 46-74 исходника, дословно >>>
```
2. `lifecycle_errors.py` — заголовок + `from lifecycle_const import MAX_CAS_RETRIES` +
   строки **77-131 дословно** (четыре класса).
   Внимание: секция Approaches утверждает «`lifecycle_errors` ← только stdlib» — это
   неверно, `LifecycleWriteRaceError.__init__` имеет `attempts: int = MAX_CAS_RETRIES`
   (строка 80). Зависимость `errors → const` штатная и графу не противоречит.
3. `lifecycle.py`: удалить строки 46-74 и 77-131; удалить `import threading`;
   добавить в блок импортов:
```python
from lifecycle_const import (  # noqa: F401 — re-export: read via lifecycle.<NAME>
    LIFECYCLE_DIR,
    MAX_CAS_RETRIES,
    _ALLOWED_WRITERS,
    _ALLOWED_WRITERS_FOR_CREATE,
    _PUSH_REBASE_RETRIES,
    _VALID_PRIORITIES,
    _write_lock,
)
from lifecycle_errors import (  # noqa: F401 — re-export
    LifecycleAlreadyDoneError,
    LifecycleWriteRaceError,
    NotBootstrapArtifactError,
    NotFalseReconciliationError,
)
```

**Acceptance:**
- [ ] `python -c "import lifecycle, lifecycle_const; assert lifecycle._write_lock is lifecycle_const._write_lock"` (PYTHONPATH=scripts/vps)
- [ ] Все семь `test_lifecycle*.py` + `tests/integration/test_lifecycle_identity.py`
      зелёные **без единой правки** — реэкспорт И-2 держит `lifecycle._ALLOWED_WRITERS`
- [ ] `ruff check scripts/vps/` чист

### Task 2: Примитивы git
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_git.py` (~165 LOC)
  - modify: `scripts/vps/lifecycle.py`
  - modify: `scripts/vps/tests/test_lifecycle_run_encoding.py`
  - modify: `scripts/vps/tests/test_lifecycle.py` ← **добавлено к плану спеки**: после
    выемки `_run` ломается `test_lifecycle.py`, а не только encoding-файл
**Pattern:** Task 1

**Шаги:**
1. `lifecycle_git.py`: заголовок + импорты + строки **139-267 дословно**
   (`_now_iso`, `_run` вместе с вложенным `_decode`, комментарий + `run_git = _run`,
   `_current_branch`, `_read_yaml_from_head`, `_build_yaml_content`). Ничего не
   переписывать: докстринга `_run` — единственное место, где записаны правила
   байтового I/O.
```python
import subprocess
from datetime import datetime, timezone
from typing import Optional

import yaml
from lifecycle_const import LIFECYCLE_DIR
```
2. `lifecycle.py`: удалить 139-267; добавить `import lifecycle_git` и
   `from lifecycle_git import run_git  # noqa: F401 — public alias (salvage.py:35)`;
   заменить **каждый** оставшийся вызов `_run(` → `lifecycle_git._run(`,
   `_now_iso()` → `lifecycle_git._now_iso()`, `_current_branch(` →
   `lifecycle_git._current_branch(`, `_read_yaml_from_head(` →
   `lifecycle_git._read_yaml_from_head(`, `_build_yaml_content(` →
   `lifecycle_git._build_yaml_content(` (≈34 места).
   Удалить `from datetime import datetime, timezone` (остался без потребителей).
   Проверка: `grep -nE "[^._a-zA-Z](_run|_now_iso|_current_branch|_read_yaml_from_head|_build_yaml_content)\(" scripts/vps/lifecycle.py` → пусто.
3. `test_lifecycle_run_encoding.py`:
   - строка 2: `lifecycle._run` → `lifecycle_git._run` (докстринга)
   - после строки 32 добавить `import lifecycle_git  # noqa: E402`
   - строки **78, 90, 103, 107, 114, 118**: `lifecycle._run(` → `lifecycle_git._run(`
   - `import lifecycle` оставить: строки 129-159 используют публичный API
4. `test_lifecycle.py`:
   - после строки 25 добавить `import lifecycle_git  # noqa: E402`
   - **106**: `real_run = lifecycle._run` → `lifecycle_git._run`
   - **123**: `patch.object(lifecycle, "_run", injecting_run)` → `patch.object(lifecycle_git, "_run", injecting_run)`
   - **352**, **362**: `patch.object(lifecycle, "_run", return_value=fail)` → `patch.object(lifecycle_git, "_run", …)`
   - **399**: `inspect.signature(lifecycle._run)` → `inspect.signature(lifecycle_git._run)`
   - строки 354/363 (`lifecycle._push_best_effort`) на этом шаге **не трогать** — push
     ещё в фасаде и вызывает `lifecycle_git._run`, подмена достаёт до него

**Acceptance:**
- [ ] `_run` возвращает декодированный `str`, `cwd` keyword-only, `timeout=30`,
      `text=True` не появился: `grep -n "text=True" scripts/vps/lifecycle_git.py` → пусто
- [ ] `test_lifecycle_run_encoding.py` — 7/7 зелёных (CRLF/кириллица проверяются на байтах)
- [ ] `test_lifecycle.py::test_concurrent_commit_during_write_not_reverted` зелёный —
      это доказательство, что подмена `lifecycle_git._run` доходит до `_atomic_write`
- [ ] `test_lifecycle_wt_sync.py`, `test_lifecycle_done_terminal.py`,
      `test_lifecycle_create_initial.py`, `test_lifecycle_audit.py` — без правок

### Task 3: CAS и push
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_cas.py` (~265 LOC)
  - create: `scripts/vps/lifecycle_push.py` (~175 LOC)
  - modify: `scripts/vps/lifecycle.py`
  - modify: `scripts/vps/tests/test_lifecycle_push_rebase.py`
  - modify: `scripts/vps/tests/test_lifecycle.py`
  - ~~`test_lifecycle_wt_sync.py`~~ — **правок не требует**, работает только через
    `create_initial` / `write_lifecycle` / `write_file_atomic` (проверено: 99, 102, 138, 182)
**Pattern:** Task 1

**Шаги:**
1. `lifecycle_push.py` (первым — `cas` от него зависит): строки **407-554 дословно**.
```python
import logging
import subprocess
from pathlib import Path

import lifecycle_git
from lifecycle_const import LIFECYCLE_DIR, _PUSH_REBASE_RETRIES

log = logging.getLogger(__name__)
```
   Внутри — `_run(` → `lifecycle_git._run(`.
2. `lifecycle_cas.py`: строки **270-404** (`_atomic_write`), **806-876**
   (`_atomic_write_file`), **557-583** (`_cas_loop`) — в этом порядке, дословно.
```python
import logging
import os
import random
import re
import subprocess
import tempfile
import time

import lifecycle_git
import lifecycle_push
from lifecycle_const import LIFECYCLE_DIR, MAX_CAS_RETRIES, _write_lock
from lifecycle_errors import LifecycleWriteRaceError

log = logging.getLogger(__name__)
```
   `_run(` → `lifecycle_git._run(`, `_push_best_effort(` → `lifecycle_push._push_best_effort(`.
   **Ленивый `import render_backlog` внутри `_atomic_write` (строка 326) оставить как есть.**
   Он тянет `from lifecycle import LIFECYCLE_DIR`, то есть фасад — но только в рантайме,
   когда `lifecycle` уже в `sys.modules`. Статического цикла нет, И-4 не нарушен.
   Опасность в другом: весь блок обёрнут в `except Exception` с `log.warning("backlog
   sync skipped")`, поэтому сломанный импорт не уронит ни одного теста. Отсюда шаг 5.
3. `lifecycle.py`: удалить 270-404, 407-554, 557-583, 806-876; добавить
   `import lifecycle_cas`, `import lifecycle_push`; в `write_file_atomic` заменить
   `_atomic_write_file(` → `lifecycle_cas._atomic_write_file(` и `_push_best_effort(` →
   `lifecycle_push._push_best_effort(`; в `write_lifecycle` / `create_initial`
   `_cas_loop(` → `lifecycle_cas._cas_loop(`. Убрать из импортов `os`, `re`,
   `subprocess`, `tempfile`; убрать `_PUSH_REBASE_RETRIES` из списка `from lifecycle_const import`.
   `_write_lock`, `MAX_CAS_RETRIES`, `random`, `time` остаются — их держит `write_file_atomic`.
4. Тесты — перенацеливание:
   - `test_lifecycle_push_rebase.py:30`: `import lifecycle  # noqa: E402` →
     `import lifecycle_push  # noqa: E402` (**замена, не добавление** — других обращений
     к `lifecycle` в файле нет, иначе ruff F401)
   - `128, 151, 182, 205`: `lifecycle._push_best_effort` → `lifecycle_push._push_best_effort`
   - `229`: `lifecycle._rebase_onto_origin` → `lifecycle_push._rebase_onto_origin`
   - `247, 251, 255`: `lifecycle._local_ahead_is_lifecycle_only` → `lifecycle_push._local_ahead_is_lifecycle_only`
   - `test_lifecycle.py`: добавить `import lifecycle_cas`, `import lifecycle_push`
     (`# noqa: E402`); **354, 363**: `lifecycle._push_best_effort` →
     `lifecycle_push._push_best_effort`; **377-379**: `patch.object(lifecycle,
     "_atomic_write", …)` → `patch.object(lifecycle_cas, "_atomic_write", …)`
5. `test_lifecycle.py` — один новый тест на молчаливую дыру из шага 2 (сейчас
   fold-in-commit backlog-синхронизации не покрыт ничем: `render_backlog.sync_status`
   тестируется отдельно, а вызов из `_atomic_write` — нет):
```python
def test_backlog_fold_survives_the_split(tmp_git_repo, caplog):
    """_atomic_write imports render_backlog lazily and swallows any failure.

    After the split that import crosses a module boundary; a breakage would only
    surface as a WARNING nobody reads. Assert the fold actually happened.
    """
    import logging

    backlog = tmp_git_repo / "ai" / "backlog.md"
    backlog.write_text(
        "| ID | Status | Kind | Updated | Spec |\n"
        "|----|--------|------|---------|------|\n"
        "| TECH-777 | queued | tech | 2026-07-28 | x |\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "ai/backlog.md"], cwd=str(tmp_git_repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "seed backlog"],
        cwd=str(tmp_git_repo), check=True, capture_output=True,
    )

    with caplog.at_level(logging.WARNING, logger="lifecycle_cas"):
        lifecycle.write_lifecycle(tmp_git_repo, "TECH-777", "done", by="callback")

    assert not [r for r in caplog.records if "backlog sync skipped" in r.message]
    head = subprocess.run(
        ["git", "show", "HEAD:ai/backlog.md"],
        cwd=str(tmp_git_repo), capture_output=True, text=True, check=True,
    ).stdout
    assert "| TECH-777 | done |" in head
```

**Acceptance:**
- [ ] `test_lifecycle_wt_sync.py` — 3/3 зелёных **без правок файла** (инвариант «No dirty
      WT», TECH-194 Layer D)
- [ ] `test_lifecycle_push_rebase.py` — 6/6, `test_lifecycle.py` — все, включая новый
- [ ] `test_lifecycle.py::test_cas_loop_treats_timeout_as_retry` зелёный —
      `LifecycleWriteRaceError` после `MAX_CAS_RETRIES`, lock отпущен
- [ ] `grep -c "backlog sync skipped" <прогон>` = 0 (см. новый тест)
- [ ] И-4: grep из инвариантов пуст

### Task 4: Recovery
**Type:** code
**Files:**
  - create: `scripts/vps/lifecycle_recovery.py` (~265 LOC)
  - modify: `scripts/vps/lifecycle.py`
  - ~~`test_lifecycle.py`~~ — **правок не требует**: 613/628/629/639/640/647 зовут
    `lifecycle.recover_false_reconciliation`, который реэкспортируется
**Pattern:** Task 1

**Шаги:**
1. `lifecycle_recovery.py`: строки **901-989** (`recover_bootstrap_artifact`) и
   **992-1114** (`recover_false_reconciliation`) дословно.
```python
import lifecycle_cas
import lifecycle_git
from lifecycle_const import _ALLOWED_WRITERS
from lifecycle_errors import NotBootstrapArtifactError, NotFalseReconciliationError
```
   Внутри: `_read_yaml_from_head(` / `_current_branch(` / `_build_yaml_content(` / `_run(`
   → через `lifecycle_git.`, `_cas_loop(` → `lifecycle_cas._cas_loop(`.
2. **`reconcile_orphans` (879-898) НЕ переезжает** — остаётся в `lifecycle.py`.
   Она зовёт `list_by_status` и `write_lifecycle`, а обе живут в фасаде: перенос дал бы
   `lifecycle_recovery → lifecycle`, то есть ровно Approach 2 (цикл), отвергнутый в
   секции Approaches. +20 LOC к фасаду, DAG цел. Секция Design этого не учла.
3. `lifecycle.py`: удалить 901-1114; добавить
   `from lifecycle_recovery import (  # noqa: F401 — re-export
       recover_bootstrap_artifact, recover_false_reconciliation)`.
   Потребители (`recover_bootstrap_as_done.py:95,103`,
   `recover_false_reconciliation.py:79`) не правятся — они вне Allowed Files by design.

**Acceptance:**
- [ ] `test_lifecycle.py` (BUG-460 сценарии, 592-651) зелёный **без правок файла**
- [ ] `NotBootstrapArtifactError` / `NotFalseReconciliationError` по-прежнему видны как
      `lifecycle.<Error>`: `python -c "import lifecycle; lifecycle.NotBootstrapArtifactError"`
- [ ] `test_orchestrator_bootstrap.py:492-502` (recovery-тесты, вне Allowed Files) зелёные
- [ ] `python -c "import recover_bootstrap_as_done, recover_false_reconciliation, spec_operator"` — exit 0

### Task 5: Фасад — заголовок, импорты, структурные тесты
**Type:** code
**Files:**
  - modify: `scripts/vps/lifecycle.py`
  - modify: `scripts/vps/tests/test_lifecycle.py`
**Pattern:** —

**Шаги:**
1. Переписать docstring `lifecycle.py`: `Role` — «facade: public API + Rule 7
   (ADR-025) + re-exports»; `Uses` — шесть siblings с ролями; `Used by` — оставить,
   добавить `salvage.py: run_git`. Строку `Glossary:` не трогать (её чинит ARCH-209).
2. Финальная прополка импортов. Должно остаться ровно:
   `logging`, `random`, `time`, `from glob import glob`, `from pathlib import Path`,
   `from typing import Optional`, `import yaml`, шесть локальных модулей/имён.
   Не должно остаться: `os`, `re`, `subprocess`, `tempfile`, `threading`, `datetime`.
3. Дописать в `test_lifecycle.py` структурный класс — EC-1/EC-7/EC-10/EC-11 сейчас не
   покрыты ничем (прецедент: TECH-212 добавил такие же в `test_db.py`):
```python
class TestSplitContract:
    """Structural invariants of the TECH-214 split (EC-1, EC-7, EC-10, EC-11)."""

    def test_write_lock_is_a_single_instance(self):
        import lifecycle_cas
        import lifecycle_const

        assert lifecycle._write_lock is lifecycle_const._write_lock
        assert lifecycle_cas._write_lock is lifecycle_const._write_lock

    def test_bound_imports_still_resolve(self):
        import migrate_backlog_to_lifecycle
        import render_backlog
        import salvage

        assert salvage._git is lifecycle.run_git
        assert render_backlog.LIFECYCLE_DIR == lifecycle.LIFECYCLE_DIR
        assert migrate_backlog_to_lifecycle.build_initial_yaml is lifecycle.build_initial_yaml

    def test_no_sibling_imports_the_facade(self):
        siblings = ["const", "errors", "git", "cas", "push", "recovery"]
        for name in siblings:
            src = (Path(lifecycle.__file__).parent / f"lifecycle_{name}.py").read_text(
                encoding="utf-8"
            )
            for line in src.splitlines():
                stripped = line.strip()
                assert not stripped.startswith("from lifecycle import"), f"{name}: {line}"
                assert stripped != "import lifecycle", f"{name}: {line}"

    def test_every_module_under_the_loc_limit(self):
        vps = Path(lifecycle.__file__).parent
        names = ["lifecycle.py"] + [
            f"lifecycle_{n}.py" for n in ["const", "errors", "git", "cas", "push", "recovery"]
        ]
        for name in names:
            loc = len((vps / name).read_text(encoding="utf-8").splitlines())
            assert loc <= 400, f"{name}: {loc} LOC > 400"
```
4. Если `lifecycle.py` вышел за 400 (оценка ~330 — запас есть): резать нечего, кроме
   `write_file_atomic` (45 LOC) — переносить её в `lifecycle_cas` **нельзя** без правки
   `callback.py:1110`, который вне Allowed Files. В этом случае — BLOCKED, не импровизировать.

**Acceptance:**
- [ ] `wc -l scripts/vps/lifecycle*.py` — каждый из семи ≤ 400
      (`lifecycle_audit.py` = 254, тоже попадает под glob и лимит проходит)
- [ ] `cd scripts/vps/tests && python -m pytest -q` — 0 failed, число прошедших ≥ базовой
      линии + новые
- [ ] `python -m pytest tests/ -q` — падений не больше базовой линии (3 предсуществующих)
- [ ] `python -m pytest tests/integration/test_lifecycle_identity.py -q` — зелёный,
      файл не правился
- [ ] `ruff check scripts/vps/` чист
- [ ] AV-S1, AV-S2 из секции Acceptance Verification

### Execution Order
```
Task 1 (const, errors) → Task 2 (git) → Task 3 (push, cas) → Task 4 (recovery) → Task 5 (фасад)
```
Строго последовательно: каждый следующий модуль импортирует предыдущий. Каждая задача —
отдельный коммит, перед коммитом полный прогон `scripts/vps/tests` зелёный. Порядок снизу
вверх по графу: лист первым, фасад последним.

**Итоговый граф импортов** (проверено по вызовам, не по namespace):
```
lifecycle_const  ← лист, только threading
     ↑
lifecycle_errors ← const (MAX_CAS_RETRIES в default arg)
     ↑
lifecycle_git    ← const
     ↑
lifecycle_push   ← const, git
     ↑
lifecycle_cas    ← const, errors, git, push
     ↑
lifecycle_recovery ← const, errors, git, cas
     ↑
lifecycle.py (фасад) ← все шесть
```
Ни одна функция в `lifecycle_git` не зовёт cas/push/recovery — проверено пофункционально
(`_now_iso`, `_run`, `_current_branch`, `_read_yaml_from_head`, `_build_yaml_content`
используют только stdlib, yaml и `LIFECYCLE_DIR`). Нарушение DAG нашлось в другом месте —
`reconcile_orphans`, см. Task 4 шаг 2.

### Отклонения от секции Design (зафиксированы, Design не правился)

| # | Что в Design | Что в плане | Почему |
|---|---|---|---|
| 1 | `reconcile_orphans` → `lifecycle_recovery` | остаётся в `lifecycle.py` | зовёт `list_by_status` + `write_lifecycle` из фасада → перенос = цикл (Approach 2) |
| 2 | `_decode` — отдельный символ `lifecycle_git` | вложенная функция внутри `_run` (178-179) | так в коде; переезжает вместе с `_run` |
| 3 | `_PUSH_REBASE_RETRIES` не упомянут нигде | → `lifecycle_const` | это седьмая модульная константа (48-51), читает её `_push_best_effort` |
| 4 | «`lifecycle_errors` ← только stdlib» | `errors → const` | `MAX_CAS_RETRIES` в default arg `LifecycleWriteRaceError` (80) |
| 5 | `test_lifecycle_wt_sync.py` — «перенацелить monkeypatch» | правок не требует | в файле ноль моков и ноль приватных ссылок |
| 6 | `test_lifecycle.py` правится в Task 4 | правится в Task 2 и Task 3 | ломает его выемка `_run` и `_atomic_write`, а не recovery |
| 7 | Task 2 не включал `test_lifecycle.py` | включает | там 5 из 8 приватных ссылок — на `_run` |

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
