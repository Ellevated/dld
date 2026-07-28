# Feature: [TECH-215] Раскол orchestrator.py и разбор scan_queued

**Priority:** P1 | **Date:** 2026-07-27

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`orchestrator.py` — 1117 LOC при лимите 400, из них `scan_queued` — **226 строк в одной
функции** (строки 786-1011). Это главный цикл: он читает lifecycle, проходит гейт
реконсиляции, проверяет зависимости и диспатчит автопилот. Каждая из четырёх обязанностей
внутри одного тела.

Именно в этой функции 2026-07-27 сработал баг реконсиляции: гейт закрывал спеку против её
собственного birth-коммита. Найти его удалось потому, что искали целенаправленно по
живым данным VPS — а не потому, что читая функцию, увидели проблему.

## Context

### Карта ответственностей

Проверено против `orchestrator.py` HEAD 2026-07-28 (1117 строк, после BUG-218 —
d3748b7 + 38d77d5).

| Группа | Строки | Содержимое (точные диапазоны) | ~LOC |
|---|---|---|---|
| `bootstrap` | 1-99 | docstring 1-10, импорты 12-30, `log`/`_stop`/`_projects_mtime` 32-34, `_load_env` 37-47, `_setup_logging` 50-71, `_signal_handler` 74-76, `_write_pid` 79-82, `sync_projects` 85-99 | 99 |
| `slots` | 102-311 | `_LIVE_PUEUE_STATES` 102, `BOOTSTRAP_ANOMALY_THRESHOLD` 104-108, `get_live_pueue_ids` 111-141, `pueue_has_active_label` 144-172, `pueue_has_active_spec` 175-203, `release_orphan_slots` 206-229, `is_agent_running` 232-253, `git_pull` 256-310 | 210 |
| `backlog` | 313-607 | `_VALID_STATUSES`/`_SPEC_ID_RE_BS` 313-316, `_parse_backlog` 319-391, `_bump_unparsable_counter` 394-401, `bootstrap_new_specs` 404-497, `_parse_priority_kind` 500-512, `cleanup_stale_stashes` 515-571, `startup_reconcile` 574-607 (fail-closed, BUG-218) | 295 |
| `inbox` | 610-736 | `_parse_inbox_file` 610-642, `_ROUTE_SKILL_MAP` 645-654, `_pueue_add` 657-673, `scan_inbox` 676-736 | 127 |
| `queue` | 739-1028 | комментарий BUG-206 739-745, `_AFTER_DEP_RE` 746, `_backlog_deps` 749-767, `_unmet_dependencies` 770-783, **`scan_queued` 786-1011 (226)**, `dispatch_night_review` 1014-1028 | 290 |
| `main` | 1031-1117 | `process_project` 1031-1040, `MIN_CYCLE_SLEEP` 1043, `_next_sleep` 1046-1056, `main` 1059-1113, `__main__` 1116-1117 | 87 |

Внутренняя карта `scan_queued` (786-1011) — по ней режется тело:

| Строки | Шаг | Зависит от имён `orchestrator.*` |
|---|---|---|
| 792-794 | `list_by_status`, ранний выход | `lifecycle` (объект модуля) |
| 796-811 | выбор кандидата по `AFTER`-зависимостям | **`_unmet_dependencies`** |
| 813-839 | гейт свежести по `callback-audit.jsonl` | **`SCRIPT_DIR`** |
| 841-845 | провайдер по умолчанию, glob спеки | `db` |
| 847-865 | spec-readiness gate | — |
| 867-892 | провайдер из тела спеки + проверка слотов | `db` |
| 894-900 | `pueue_has_active_label` / `_spec` | **обе** |
| 901-905 | `spec_path` + `pueue_env` | **`CLAUDE_CURRENT_SPEC_PATH` пиннится текстовым тестом** |
| 906-921 | TOCTOU-перечитка lifecycle | `lifecycle` |
| 922-956 | гейт реконсиляции | `gate_logic`, `lifecycle` |
| 957-968 | `_pueue_add(..., env=pueue_env)` | **`_pueue_add`, `SCRIPT_DIR`; `env=pueue_env` пиннится текстовым тестом** |
| 969-1011 | учёт в db + запись `in_progress` | `db`, `lifecycle` |

### Контракты

| Контракт | Где | Замечание |
|---|---|---|
| systemd `ExecStart` | `setup-vps.sh:456` | абсолютный путь к `orchestrator.py`, зашит при установке, **не перегенерируется push'ем** |
| «No dirty WT» на старте | `lifecycle.assert_clean_lifecycle_tree` в `startup_reconcile:597` | ADR-023, прерывает старт при грязном `ai/lifecycle/` |
| `AFTER <ID>` в backlog-строке | `_AFTER_DEP_RE`, строка 746 | единственное место, откуда берутся зависимости между спеками |
| bootstrap fail'ится в `queued` | `bootstrap_new_specs:453-462` | ADR-026: **никогда** не в `done` |
| `queued → in_progress` при диспатче | `scan_queued:994-1009` | BUG-218; отказ записи **не** откатывает диспатч |
| fail-closed реконсиляция орфанов | `startup_reconcile:589-599` | BUG-218; `get_live_pueue_ids() is None` ≠ `set()` |
| связанный импорт | `test_orchestrator_bootstrap.py:28` | `from orchestrator import _bump_unparsable_counter, _parse_backlog` |
| текст `def scan_queued` в файле | `test_autopilot_scope_guard.py:87-113` | читает **исходник** `scripts/vps/orchestrator.py` и ищет `def scan_queued`; тела в другом файле не увидит |

Две последние строки — жёсткие. Тест ADR-026 связывает два приватных имени при импорте:
уедут без реэкспорта — падение на сборке. А `test_autopilot_scope_guard.py` вообще не
импортирует модуль: он грепает текст файла, поэтому переезд `scan_queued` в sibling ломает
его независимо от любых реэкспортов.

### Правило совместимости monkeypatch (главное ограничение раскола)

`unittest.mock.patch("orchestrator.X")` подменяет атрибут на **объекте модуля
`orchestrator`**. Функция, чей код лежит в `orchestrator_queue`, ищет свободное имя `X`
в `orchestrator_queue.__dict__`, затем в builtins — в `orchestrator.__dict__` она не
заглядывает никогда. Реэкспорт копирует ссылку **внутрь** `orchestrator`; он не
перенаправляет разрешение имён **наружу** из sibling'а. Python docs, «Where to patch»:
«patch out `SomeClass` where it is used (or where it is looked up)».

Отсюда единственное работающее правило:

> Имя может уехать в sibling тогда и только тогда, когда **каждый вызывающий, который
> тест исполняет под патчем этого имени, остаётся в `orchestrator.py`** и обращается
> к реэкспортированному биндингу голым именем.

Провал этого правила — не красный тест, а зелёный: патч молча не применяется, тест
уходит в живой pueue / живой `callback-audit.jsonl` и «проходит» против непропатченного
кода.

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
- **Семь** тест-файлов, не четыре (спека знала о четырёх):

| Файл | LOC | В Allowed Files? | Как связан |
|---|---|---|---|
| `tests/test_orchestrator.py` | ~1335 | **да** | 20 патчей `orchestrator._pueue_add`, 15 `orchestrator.SCRIPT_DIR`, 13 `orchestrator._unmet_dependencies`, 8 `orchestrator.get_live_pueue_ids`, `pueue_has_active_label/_spec` |
| `tests/test_orchestrator_bootstrap.py` | 690 | **да** | связанный импорт `:28`; вызывает `bootstrap_new_specs`; **патчей на `orchestrator.*` нет** |
| `tests/test_orchestrator_lifecycle.py` | 141 | **да** | вызывает `bootstrap_new_specs`; патчей нет |
| `tests/test_orchestrator_git_pull.py` | 189 | **НЕТ** | 7× `orchestrator.is_agent_running`, 6× `orchestrator.log`, `orchestrator.subprocess.run` |
| `tests/test_orchestrator_in_progress.py` | 225 | **НЕТ** (появился после спеки, BUG-218) | `orchestrator.SCRIPT_DIR`, `_pueue_add`, `pueue_has_active_label/_spec`, `get_live_pueue_ids`, `cleanup_stale_stashes` |
| `tests/test_autopilot_scope_guard.py` | — | **НЕТ** | `:89` читает **текст** `scripts/vps/orchestrator.py`, ищет `def scan_queued` |
| `tests/test_lifecycle.py` | 649 | **НЕТ** | `:182` `import orchestrator`, `:191` `patch("orchestrator.subprocess.run")`, `:197` `orchestrator.git_pull` |

Четыре из семи править нельзя. План обязан оставить их зелёными **без единой правки** —
см. § Design «Что обязано остаться в `orchestrator.py`».

### Step 2: DOWN — what depends on?

```
orchestrator.py → db, gate_logic, lifecycle (строки 28-30)
                → event_writer (ленивый, строка 490)
```

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/setup-vps.sh` | 456 | `ExecStart=... orchestrator.py` | **не трогать** — имя сохраняется |
| `scripts/vps/tests/test_orchestrator_bootstrap.py` | 28 | связанный импорт двух приватных имён | реэкспорт в `orchestrator.py`, файл не правится |
| `scripts/vps/tests/test_orchestrator.py` | 8× `get_live_pueue_ids`, 5× блок `scan_inbox` | monkeypatch | **перенацелить** (файл в Allowed Files) |
| `scripts/vps/tests/test_orchestrator_git_pull.py` | 7+6 | monkeypatch `is_agent_running`, `log` | **править нельзя** → `git_pull`, `is_agent_running`-вызов и `log` остаются в `orchestrator.py` |
| `scripts/vps/tests/test_orchestrator_in_progress.py` | 66-76, 178-220 | monkeypatch | **править нельзя** → `scan_queued`, `startup_reconcile` остаются в `orchestrator.py` |
| `scripts/vps/tests/test_autopilot_scope_guard.py` | 87-113 | грепает исходник | **править нельзя** → `def scan_queued` физически остаётся в `orchestrator.py` |
| `scripts/vps/orchestrator.py` | 746 | `_AFTER_DEP_RE` | переезжает вместе с `_backlog_deps` |
| `docs/orchestrator/components.md` | — | описывает компоненты | чинит ARCH-209 |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — семь файлов (см. Step 1), три правятся
- [x] `tests/**` (корень) — `tests/integration/test_autopilot_no_status_write.py`
      косвенно; **не правится**
- [x] `db/migrations/**` — нет
- [x] `ai/glossary/**` — не существует
- [x] `template/scripts/vps/` — **не существует**, sync-задача не нужна

### Verification

- [x] Все правящиеся файлы в Allowed Files
- [x] Четыре файла вне Allowed Files остаются зелёными без правок — по построению
      (§ Design «Что обязано остаться»)
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
**Cons:** правится один тест-файл (`test_orchestrator.py`, 13 перенацеленных патчей);
`git_pull` и `startup_reconcile` остаются в фасаде вопреки семантике — цена за то,
чтобы четыре тест-файла вне Allowed Files не требовали правок

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

### Что обязано остаться в `orchestrator.py` (выводится, не выбирается)

Правило совместимости из § Context даёт замкнутый список. Это не предпочтение — это
следствие того, что четыре тест-файла править нельзя.

| Символ | Почему нельзя вынести |
|---|---|
| `SCRIPT_DIR`, `log`, `_stop` | патчатся (`SCRIPT_DIR`, `log`) и читаются функциями, которые остаются |
| `git_pull` | под патчем `orchestrator.is_agent_running` и `orchestrator.log` (git_pull-тесты) |
| `startup_reconcile` | под патчем `orchestrator.get_live_pueue_ids` и `orchestrator.cleanup_stale_stashes` (in_progress-тесты) |
| `scan_queued` (обёртка) | (а) под патчем `SCRIPT_DIR`/`_pueue_add`/`pueue_has_active_*`/`_unmet_dependencies`; (б) `test_autopilot_scope_guard.py` грепает `def scan_queued` **в этом файле** и требует внутри него строк с `CLAUDE_CURRENT_SPEC_PATH`+`pueue_env` и `env=pueue_env` |
| цикл выбора кандидата в `scan_queued` | вызывает `_unmet_dependencies` под патчем ×13 — оставить вызов здесь дешевле 13 правок |
| `main`, `process_project`, `_next_sleep`, `MIN_CYCLE_SLEEP` | точка входа + `_next_sleep` вызывается как `orchestrator._next_sleep` |
| `_load_env`, `_setup_logging`, `_signal_handler`, `_write_pid` | bootstrap процесса, дешевле оставить чем городить пятый модуль (его нет в Allowed Files) |

Всё остальное уезжает — включая имена, которые патчатся, при условии что их
единственный исполняемый-под-патчем вызывающий остался здесь. `cleanup_stale_stashes`
живёт в `orchestrator_backlog.py`, но `patch("orchestrator.cleanup_stale_stashes")`
работает, потому что зовёт её `startup_reconcile` из `orchestrator.py` — по
реэкспортированному биндингу.

### Раскол

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `orchestrator_slots.py` | `sync_projects`, `_projects_mtime`, `_LIVE_PUEUE_STATES`, `get_live_pueue_ids`, `pueue_has_active_label`, `pueue_has_active_spec`, `is_agent_running`, `release_orphan_slots`, `_pueue_add` | ~185 |
| `orchestrator_backlog.py` | `_VALID_STATUSES`, `_SPEC_ID_RE_BS`, `BOOTSTRAP_ANOMALY_THRESHOLD`, `_parse_backlog`, `_bump_unparsable_counter`, `bootstrap_new_specs`, `_parse_priority_kind`, `cleanup_stale_stashes` | ~265 |
| `orchestrator_inbox.py` | `_parse_inbox_file`, `_ROUTE_SKILL_MAP`, `scan_inbox` | ~120 |
| `orchestrator_queue.py` | `_AFTER_DEP_RE`, `_backlog_deps`, `_unmet_dependencies`, шесть шагов `scan_queued`, `dispatch_night_review` | ~230 |
| `orchestrator.py` | bootstrap процесса, `SCRIPT_DIR`/`log`/`_stop`, `git_pull`, `startup_reconcile`, обёртка `scan_queued`, `process_project`, `_next_sleep`, `main`, реэкспорты | ~370 |

`git_pull` и `startup_reconcile` остаются в `orchestrator.py`, хотя семантически они
принадлежат `slots` и `backlog`. Это цена, которую платит раскол за то, чтобы четыре
незатрагиваемых тест-файла остались зелёными. Альтернатива — расширить Allowed Files и
править тесты, чьё единственное назначение — ловить регрессии в этих самых функциях.

### Разбор `scan_queued`

226 строк → обёртка ~85 строк в `orchestrator.py` плюс шесть шагов в
`orchestrator_queue.py`. Шаги **не читают ни одного патчимого имени из `orchestrator`** —
всё, что патчится, передаётся параметром или живёт на объекте общего модуля
(`db`, `lifecycle`, `gate_logic` — их патчат как `orchestrator.db.X`, что мутирует
разделяемый объект модуля и потому работает из любого места).

| Шаг в `orchestrator_queue.py` | Сигнатура | Из строк |
|---|---|---|
| `recently_processed` | `(audit_log: Path, spec_id: str) -> str \| None` | 813-839 |
| `spec_body_files` | `(project_dir: str, spec_id: str) -> list[Path]` | 844-845 |
| `resolve_provider` | `(spec_file: Path, default_provider: str, spec_id: str) -> str` | 867-888 |
| `status_still_dispatchable` | `(project_dir: str, spec_id: str) -> bool` | 906-921 |
| `reconcile_if_implemented` | `(project_dir: str, spec_id: str, spec_file: Path) -> bool` | 922-956 |
| `record_dispatch` | `(project_id, project_dir, spec_id, provider, task_label, pueue_id) -> None` | 973-1009 |

`audit_log` **параметром**, а не через `SCRIPT_DIR` внутри шага: `SCRIPT_DIR` патчат из
`test_orchestrator_in_progress.py`, который править нельзя. Обёртка вычисляет
`SCRIPT_DIR / "callback-audit.jsonl"` у себя и передаёт вниз.

Обёртка `scan_queued` сохраняет имя, сигнатуру и контракт возврата (`bool` —
«задиспатчено ли»), и обязана удержать у себя: цикл выбора кандидата, вызовы
`pueue_has_active_label`/`pueue_has_active_spec`, конструирование `pueue_env` и вызов
`_pueue_add(..., env=pueue_env)`.

### Реэкспорты

```python
# orchestrator.py — хвост файла, после определения обёрток.
# Форма `from X import Y` здесь обязательна, а не стилистична: тесты патчат
# `orchestrator.<имя>`, и функции, оставшиеся в этом файле, обязаны разрешать имя
# в ЭТОМ словаре модуля. Атрибутный доступ (`orchestrator_slots.f()`) сломал бы патч.
from orchestrator_slots import (  # noqa: F401,E402
    _LIVE_PUEUE_STATES,
    _pueue_add,
    get_live_pueue_ids,
    is_agent_running,
    pueue_has_active_label,
    pueue_has_active_spec,
    release_orphan_slots,
    sync_projects,
)
from orchestrator_backlog import (  # noqa: F401,E402
    BOOTSTRAP_ANOMALY_THRESHOLD,
    _bump_unparsable_counter,
    _parse_backlog,
    _parse_priority_kind,
    bootstrap_new_specs,
    cleanup_stale_stashes,
)
from orchestrator_inbox import scan_inbox  # noqa: F401,E402
from orchestrator_queue import (  # noqa: F401,E402
    _AFTER_DEP_RE,
    _backlog_deps,
    _unmet_dependencies,
    dispatch_night_review,
)
```

Направление импортов жёсткое, как в TECH-214: **ни один sibling не импортирует
`orchestrator`**. Sibling'ам нужны только `db`, `lifecycle`, `gate_logic`, stdlib и
собственный `SCRIPT_DIR`/`log`. `log = logging.getLogger("orchestrator")` в каждом
sibling'е возвращает тот же объект логгера (кэш `logging`), так что journald-вывод не
меняется; патч `orchestrator.log` при этом на sibling'и не действует — и не должен,
потому что единственные ассерты на лог живут в git_pull-тестах, а `git_pull` остался.

---

## Implementation Plan

### Research Sources
- Python docs, `unittest.mock` § **Where to patch** — «patch out `SomeClass` where it is
  used (or where it is looked up)». Это тот факт, из которого выводится весь порядок
  задач ниже: реэкспорт **не** делает патч на фасаде видимым внутри sibling'а.
- `scripts/vps/db.py` + `db_decisions.py` (TECH-212, 2026-07-28) — рабочий прецедент
  раскола в этом же дереве: чистые листья, ноль обратных импортов, фасад ребиндит имена.
  Отличие: у `db` не было ни одного теста, патчащего `db.<имя>` для внутреннего вызова,
  поэтому там хватило голого делегирования. Здесь — не хватает.
- `.claude/rules/architecture.md` ADR-021, ADR-022, ADR-023, ADR-025, ADR-026
- BUG-218 (d3748b7, 38d77d5) — `startup_reconcile` fail-closed + запись `in_progress`;
  добавил `test_orchestrator_in_progress.py`, файл вне Allowed Files.

### Правила, обязательные для каждой задачи

1. **Перенос без правки логики.** Тела функций копируются посимвольно. Единственное
   допустимое изменение — `_` в начале имени сохраняется, комментарии и docstring'и
   едут целиком (в них сидят ADR-ссылки и разбор инцидентов).
2. **Ни один sibling не делает `import orchestrator`.** Проверяется EC-12.
3. **Каждый sibling начинается одинаково:**
   ```python
   SCRIPT_DIR = Path(__file__).resolve().parent
   if str(SCRIPT_DIR) not in sys.path:
       sys.path.insert(0, str(SCRIPT_DIR))
   log = logging.getLogger("orchestrator")
   ```
4. **Реэкспорты — в конце `orchestrator.py`**, форма `from X import Y` (см. § Design).
5. **После каждой задачи** — `cd scripts/vps/tests && python -m pytest -q` целиком,
   и отдельный коммит. Частичный прогон (`-k orchestrator`) недостаточен:
   `test_lifecycle.py` и `test_autopilot_scope_guard.py` тоже трогают `orchestrator`.

---

### Task 1: Сеть безопасности — контракт совместимости

**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_orchestrator.py` (добавить класс в конец файла)

**Context:** характеризационный тест. Он **зелёный и до, и после** раскола — красным он
станет ровно тогда, когда какая-то задача уронит имя с фасада или уведёт `scan_queued`
из файла. Пишется первым, потому что все остальные задачи проверяются им.

**Step 1: добавить в конец `scripts/vps/tests/test_orchestrator.py`**

```python
# ---------------------------------------------------------------------------
# TECH-215: compatibility surface of the orchestrator facade.
#
# Every name below is either imported by a bound `from orchestrator import ...`,
# or is a monkeypatch target in a test file that is NOT in this spec's Allowed
# Files. Losing one is not a red test somewhere else — it is a SILENT pass:
# `patch("orchestrator.X")` on a name the split moved away rebinds an attribute
# nothing reads, and the test then runs against unpatched production code.
# ---------------------------------------------------------------------------

_FACADE_NAMES = [
    # module-level state
    "SCRIPT_DIR",
    "log",
    "MIN_CYCLE_SLEEP",
    "BOOTSTRAP_ANOMALY_THRESHOLD",
    # slots / pueue
    "sync_projects",
    "get_live_pueue_ids",
    "pueue_has_active_label",
    "pueue_has_active_spec",
    "release_orphan_slots",
    "is_agent_running",
    "git_pull",
    "_pueue_add",
    # backlog / bootstrap
    "_parse_backlog",
    "_bump_unparsable_counter",
    "_parse_priority_kind",
    "bootstrap_new_specs",
    "cleanup_stale_stashes",
    "startup_reconcile",
    # inbox
    "scan_inbox",
    # queue
    "_AFTER_DEP_RE",
    "_backlog_deps",
    "_unmet_dependencies",
    "scan_queued",
    "dispatch_night_review",
    # main loop
    "process_project",
    "_next_sleep",
    "main",
]


class TestFacadeCompatSurface:
    """EC-7/EC-13: names the untouchable test files reach through `orchestrator`."""

    @pytest.mark.parametrize("name", _FACADE_NAMES)
    def test_name_resolves_from_orchestrator(self, name):
        assert hasattr(orchestrator, name), (
            f"orchestrator.{name} disappeared — a monkeypatch or bound import "
            f"in a non-editable test file now silently misses"
        )

    def test_bound_import_of_adr_026_names(self):
        """test_orchestrator_bootstrap.py:28 binds both at import time."""
        from orchestrator import _bump_unparsable_counter, _parse_backlog  # noqa: F401

    def test_scan_queued_body_lives_in_orchestrator_py(self):
        """test_autopilot_scope_guard.py:87 greps this file's TEXT, not its imports."""
        src = (Path(orchestrator.__file__)).read_text(encoding="utf-8")
        assert "def scan_queued" in src
        body, _, _ = src.partition("def scan_queued")[2].partition("\ndef ")
        assert "CLAUDE_CURRENT_SPEC_PATH" in body and "pueue_env" in body
        assert "env=pueue_env" in body

    def test_patched_facade_name_is_seen_by_its_caller(self):
        """The whole point: patching the facade must still reach the callee.

        git_pull stays in orchestrator.py precisely so that
        patch("orchestrator.is_agent_running") is observed by it.
        """
        with (
            patch("orchestrator.is_agent_running", return_value=True) as spy,
            patch("orchestrator.subprocess.run") as run_mock,
        ):
            orchestrator.git_pull("p", str(Path(orchestrator.__file__).parent))
        spy.assert_called_once()
        run_mock.assert_not_called()
```

**Step 2: прогон — обязан быть ЗЕЛЁНЫМ уже сейчас**

```bash
cd scripts/vps/tests && python -m pytest test_orchestrator.py::TestFacadeCompatSurface -q
```

Ожидается: `31 passed`. Если что-то падает **до** раскола — значит карта имён неверна,
остановиться и разобраться, а не чинить тест.

**Acceptance:**
- [ ] `TestFacadeCompatSurface` зелёный на неизменённом `orchestrator.py`
- [ ] Файл `test_orchestrator.py` не потерял ни одного существующего теста

---

### Task 2: `orchestrator_slots.py` — pueue-примитивы и слоты

**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_slots.py`
  - modify: `scripts/vps/orchestrator.py`
  - modify: `scripts/vps/tests/test_orchestrator.py`

**Context:** уезжают только те pueue-примитивы, чей вызывающий-под-патчем либо остаётся
в фасаде (`scan_queued`, `startup_reconcile`, `git_pull`), либо сам уезжает вместе с
ними (`release_orphan_slots` + `get_live_pueue_ids`). `git_pull` и `is_agent_running`
разделяются: вызов остаётся, вызываемое уезжает.

**Step 1: перенести в `scripts/vps/orchestrator_slots.py`** (посимвольно, из
`orchestrator.py` HEAD)

| Из строк | Символ |
|---|---|
| 34 | `_projects_mtime: float = 0.0` |
| 85-99 | `sync_projects` |
| 102 | `_LIVE_PUEUE_STATES` |
| 111-141 | `get_live_pueue_ids` |
| 144-172 | `pueue_has_active_label` |
| 175-203 | `pueue_has_active_spec` |
| 206-229 | `release_orphan_slots` |
| 232-253 | `is_agent_running` |
| 657-673 | `_pueue_add` |

Шапка модуля:

```python
#!/usr/bin/env python3
"""
Module: orchestrator_slots
Role: pueue primitives — liveness probe, duplicate-dispatch guards, slot watchdog,
      task submission, projects.json hot-reload.
Uses: db (import), subprocess (pueue CLI)
Used by: orchestrator (facade re-export), orchestrator_inbox
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402

log = logging.getLogger("orchestrator")
```

**Step 2: в `orchestrator.py`** — удалить перенесённые определения, добавить блок
реэкспорта `from orchestrator_slots import (...)` (см. § Design). `git_pull` (256-310)
**остаётся на месте** и продолжает звать `is_agent_running` голым именем — теперь оно
приходит из реэкспорта.

**Step 3: перенацелить 8 патчей в `test_orchestrator.py`**

`release_orphan_slots` уехала, значит она ищет `get_live_pueue_ids` в
`orchestrator_slots.__dict__`. Строки 249, 258, 266, 275, 281, 289, 299, 316 —
класс `TestReleaseOrphanSlots` и `TestWatchdogIntegration`:

```python
# было
with patch("orchestrator.get_live_pueue_ids", return_value=None):
    released = orchestrator.release_orphan_slots()
# стало
with patch("orchestrator_slots.get_live_pueue_ids", return_value=None):
    released = orchestrator.release_orphan_slots()
```

и добавить `import orchestrator_slots` рядом с `import orchestrator` (строка 19).

`TestGetLivePueueIds` (строки 48-140) **не трогать**: она патчит
`orchestrator.subprocess.run` (общий объект stdlib-модуля → видно отовсюду) и зовёт
`orchestrator.get_live_pueue_ids`, то есть реэкспортированную настоящую функцию.
`TestPueueHasActiveLabel` (187-238) — по той же причине не трогать.

**Step 4: прогон**

```bash
cd scripts/vps/tests && python -m pytest -q
```

Ожидается: 0 failed. Особенно проверить, что **не** правились и остались зелёными:
`test_orchestrator_git_pull.py` (7 патчей `orchestrator.is_agent_running`,
6× `orchestrator.log`) и `test_lifecycle.py::test_dirty_wt_does_not_revert_callback_write`.

**Acceptance:**
- [ ] `git diff --stat` не содержит `test_orchestrator_git_pull.py`
- [ ] `python -m pytest test_orchestrator_git_pull.py -q` → 7 passed
- [ ] `grep -c "^import orchestrator$" scripts/vps/orchestrator_slots.py` → 0
- [ ] `TestFacadeCompatSurface` зелёный

---

### Task 3: `orchestrator_backlog.py` — парсер backlog и bootstrap

**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_backlog.py`
  - modify: `scripts/vps/orchestrator.py`

**Context:** самая большая и самая безопасная группа: ни одного патча на `orchestrator.*`
во всём дереве тестов. `test_orchestrator_bootstrap.py` (690 LOC, 39 тестов ADR-026)
держится на реэкспорте двух приватных имён и **не правится**.

**Step 1: перенести в `scripts/vps/orchestrator_backlog.py`**

| Из строк | Символ |
|---|---|
| 104-108 | `BOOTSTRAP_ANOMALY_THRESHOLD` (+ комментарий TECH-189) |
| 313-315 | `_VALID_STATUSES` |
| 316 | `_SPEC_ID_RE_BS` |
| 319-391 | `_parse_backlog` (ADR-026) |
| 394-401 | `_bump_unparsable_counter` |
| 404-497 | `bootstrap_new_specs` |
| 500-512 | `_parse_priority_kind` |
| 515-571 | `cleanup_stale_stashes` |

Шапка — как в Task 2, плюс `import lifecycle`, `from datetime import datetime, timedelta,
timezone`, `import re`, `import subprocess`. Ленивый `from event_writer import notify`
внутри `bootstrap_new_specs` (строка 490) едет как есть.

**Step 2: `startup_reconcile` (574-607) ОСТАЁТСЯ в `orchestrator.py`.** Она зовёт
`cleanup_stale_stashes` и `get_live_pueue_ids` голыми именами — оба теперь
реэкспортированы, и `patch("orchestrator.cleanup_stale_stashes")` из
`test_orchestrator_in_progress.py:184` продолжает работать.

**Step 3: реэкспорт** `from orchestrator_backlog import (...)` в `orchestrator.py`.

**Step 4: прогон**

```bash
cd scripts/vps/tests && python -m pytest test_orchestrator_bootstrap.py test_orchestrator_lifecycle.py test_orchestrator_in_progress.py -q
```

Ожидается: 0 failed, ни один из трёх файлов не правился.

**Acceptance:**
- [ ] `python -c "import sys; sys.path.insert(0,'scripts/vps'); from orchestrator import _parse_backlog, _bump_unparsable_counter"` → exit 0
- [ ] ADR-026: неразобранный статус → `queued` + WARNING `BOOTSTRAP_UNPARSABLE` + инкремент `ai/.bootstrap-unparsable-count`
- [ ] `git diff --stat` не содержит `test_orchestrator_bootstrap.py`, `test_orchestrator_lifecycle.py`, `test_orchestrator_in_progress.py`

---

### Task 4: `orchestrator_inbox.py` — intake-гейт Hermes

**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_inbox.py`
  - modify: `scripts/vps/orchestrator.py`
  - modify: `scripts/vps/tests/test_orchestrator.py`

**Context:** `scan_inbox` уезжает — это стоит 5 перенацеленных патчей в редактируемом
файле и покупает ~120 строк, без которых фасад не влезает в 400.

**Step 1: перенести в `scripts/vps/orchestrator_inbox.py`**

| Из строк | Символ |
|---|---|
| 610-642 | `_parse_inbox_file` |
| 645-654 | `_ROUTE_SKILL_MAP` |
| 676-736 | `scan_inbox` (ADR-021/022) |

Шапка — как в Task 2, плюс `import db`, `from datetime import datetime, timezone`, и:

```python
from orchestrator_slots import _pueue_add, pueue_has_active_label  # noqa: F401
```

Именно связанная форма: тесты будут патчить `orchestrator_inbox._pueue_add`.

**Step 2: перенацелить патчи в `test_orchestrator.py`, класс `TestScanInboxStatusGate`**
(строки 346-421). Пять мест: 354-359, 378, 391, 404, 416.

```python
# было
patch("orchestrator._pueue_add", return_value=42) as mock_add,
patch("orchestrator.pueue_has_active_label", return_value=False),
# стало
patch("orchestrator_inbox._pueue_add", return_value=42) as mock_add,
patch("orchestrator_inbox.pueue_has_active_label", return_value=False),
```

Патчи `orchestrator.db.*` (356-359) **не трогать** — они мутируют общий объект модуля
`db`, который `orchestrator_inbox` тоже импортировал. Вызов `orchestrator.scan_inbox(...)`
не трогать — реэкспорт. Добавить `import orchestrator_inbox` рядом с `import orchestrator`.

**Step 3: прогон**

```bash
cd scripts/vps/tests && python -m pytest test_orchestrator.py -q -k ScanInbox
```

Ожидается: 7 passed (включая параметризацию `clarifying`/`stale`/`rejected`).

**Acceptance:**
- [ ] ADR-021: диспатчится только `**Status:** queued`; `new`/`draft`/`clarifying`/`stale`/`rejected` не двигают файл и не зовут `_pueue_add`
- [ ] `mock_add.called` истинно ровно в тесте `queued` — то есть патч **действительно применился** (иначе тест ушёл бы в живой pueue)
- [ ] `TestFacadeCompatSurface` зелёный

---

### Task 5: `orchestrator_queue.py` — зависимости и разбор `scan_queued`

**Type:** code
**Files:**
  - create: `scripts/vps/orchestrator_queue.py`
  - modify: `scripts/vps/orchestrator.py`

**Context:** ядро задачи. Обёртка `scan_queued` остаётся в `orchestrator.py` — иначе
падают `test_orchestrator_in_progress.py` (8 тестов) и
`test_autopilot_scope_guard.py::test_scan_queued_sets_spec_env_in_pueue_add`. Из тела
уезжают шесть шагов, ни один из которых не читает патчимое имя фасада.

**Step 1: перенести как есть в `orchestrator_queue.py`**

| Из строк | Символ |
|---|---|
| 739-746 | комментарий BUG-206 + `_AFTER_DEP_RE` |
| 749-767 | `_backlog_deps` |
| 770-783 | `_unmet_dependencies` |
| 1014-1028 | `dispatch_night_review` |

`dispatch_night_review` читает `SCRIPT_DIR / ".review-trigger"` и зовёт `_pueue_add` —
оба берутся из `orchestrator_queue`'s собственных `SCRIPT_DIR` и
`from orchestrator_slots import _pueue_add`. Тестов на неё нет; поведение идентично,
потому что `SCRIPT_DIR` в обоих модулях — один и тот же `scripts/vps/`.

**Step 2: вырезать шесть шагов из тела `scan_queued`** — сигнатуры и исходные строки
в § Design «Разбор `scan_queued`». Тела копируются без правок логики; меняется только
обвязка: ранние `return False` внутри шага превращаются в возврат значения, по которому
обёртка решает выйти.

Пример — шаг с гейтом свежести (строки 813-839), единственный, где параметризация
обязательна:

```python
def recently_processed(audit_log: Path, spec_id: str) -> str | None:
    """Reason this spec must not be re-dispatched yet, or None.

    `audit_log` is a parameter, not SCRIPT_DIR/"callback-audit.jsonl" resolved
    here: test_orchestrator_in_progress.py patches orchestrator.SCRIPT_DIR to a
    tmp repo and cannot be edited (not in Allowed Files). Resolving the path in
    this module would silently read the live daemon's audit log instead.

    - blocked within 30 min: the guard demoted it, a human is needed
    - done within 5 min: callback just wrote done, git pull may still be stale
    """
    if not audit_log.is_file():
        return None
    now = datetime.now(tz=timezone.utc).timestamp()
    cutoff_blocked = now - 30 * 60
    cutoff_done = now - 5 * 60
    try:
        for raw in audit_log.read_text().splitlines()[-200:]:
            entry = json.loads(raw)
            if entry.get("spec_id") != spec_id:
                continue
            ts_str = entry.get("ts", "")
            if not ts_str:
                continue
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            target_out = entry.get("target_out")
            reason = entry.get("reason", "")
            if target_out == "blocked" and reason != "fixed" and ts > cutoff_blocked:
                return f"demoted recently ({reason})"
            if target_out == "done" and ts > cutoff_done:
                return f"completed recently ({reason})"
    except Exception:  # noqa: BLE001
        pass
    return None
```

**Step 3: обёртка `scan_queued` в `orchestrator.py`.** Обязана удержать у себя
(иначе ломается непередактируемый тест): цикл выбора кандидата с вызовом
`_unmet_dependencies`; `pueue_has_active_label` / `pueue_has_active_spec`;
`SCRIPT_DIR`; конструирование `pueue_env` с `CLAUDE_CURRENT_SPEC_PATH`;
`_pueue_add(..., env=pueue_env)`.

```python
def scan_queued(project_id: str, project_dir: str) -> bool:
    """Find first queued/resumed spec via lifecycle.yaml and dispatch autopilot.

    Returns True if dispatched. Post-ARCH-186: reads ai/lifecycle/*.yaml
    (HEAD-based), not ai/backlog.md (which is now an auto-rendered read-only view).

    The body stays in this module on purpose (TECH-215): four test files reach
    into it through `orchestrator.<name>` monkeypatches or by grepping this
    file's source, and none of them are editable under this spec's Allowed Files.
    Steps with no such coupling live in orchestrator_queue.
    """
    queued_list = lifecycle.list_by_status(project_dir, {"queued", "resumed"})
    if not queued_list:
        return False

    # BUG-206: dependency-aware selection. _unmet_dependencies is resolved in
    # THIS module's globals (it is re-exported below) — 13 tests patch
    # orchestrator._unmet_dependencies and would silently miss otherwise.
    spec_id = None
    for cand in queued_list:
        cid = cand["spec_id"]
        unmet = _unmet_dependencies(project_dir, cid)
        if unmet:
            log.info("DEP_GATE: skip %s — unmet dependency %s (not done)", cid, ", ".join(unmet))
            continue
        spec_id = cid
        break
    if spec_id is None:
        return False

    skip_reason = orchestrator_queue.recently_processed(
        SCRIPT_DIR / "callback-audit.jsonl", spec_id
    )
    if skip_reason:
        log.info("skip dispatch: %s %s", spec_id, skip_reason)
        return False

    spec_files = orchestrator_queue.spec_body_files(project_dir, spec_id)
    if not spec_files:
        log.info(
            "skip dispatch: %s queued but no spec body in ai/features/ yet "
            "(spec-first ID claim not finished; orphan if it persists)",
            spec_id,
        )
        return False

    state = db.get_project_state(project_id)
    provider = orchestrator_queue.resolve_provider(
        spec_files[0], (state["provider"] if state else None) or "claude", spec_id
    )
    if db.get_available_slots(provider) < 1:
        log.info("no slots for %s provider=%s (busy)", project_id, provider)
        return False

    task_label = f"{project_id}:{spec_id}"
    if pueue_has_active_label(task_label):
        log.info("skip dispatch: %s already in pueue", task_label)
        return False
    if pueue_has_active_spec(spec_id):
        log.info("skip dispatch: %s live in pueue under another project (Rule 8)", spec_id)
        return False

    # BUG-199: pin spec path for the pre-edit hook's Allowed Files enforcement.
    spec_path = str(spec_files[0])
    pueue_env = {"CLAUDE_PROJECT_DIR": project_dir, "CLAUDE_CURRENT_SPEC_PATH": spec_path}

    if not orchestrator_queue.status_still_dispatchable(project_dir, spec_id):
        return False
    if orchestrator_queue.reconcile_if_implemented(project_dir, spec_id, spec_files[0]):
        return False

    pueue_id = _pueue_add(
        f"{provider}-runner",
        task_label,
        [
            str(SCRIPT_DIR / "run-agent.sh"),
            project_dir,
            provider,
            "autopilot",
            f"/autopilot {spec_id}",
        ],
        env=pueue_env,
    )
    if pueue_id is None:
        log.error("pueue submission failed: %s/%s", project_id, spec_id)
        return False

    orchestrator_queue.record_dispatch(
        project_id, project_dir, spec_id, provider, task_label, pueue_id
    )
    log.info("autopilot submitted: %s spec=%s pueue_id=%d", project_id, spec_id, pueue_id)
    return True
```

Обратить внимание: шаги зовутся **атрибутом** `orchestrator_queue.X`, а патчимые имена
(`_unmet_dependencies`, `pueue_has_active_*`, `_pueue_add`, `SCRIPT_DIR`) — **голым
именем**. Это не стилистика: голое имя разрешается в `orchestrator.__dict__`, куда
целится `patch`, атрибутный доступ — нет.

**Step 4: прогон**

```bash
cd scripts/vps/tests && python -m pytest -q
python -m pytest ../../tests/integration -q -k autopilot
```

**Acceptance:**
- [ ] `test_orchestrator_in_progress.py` — 11 passed, файл не правился
- [ ] `test_autopilot_scope_guard.py::TestFixBEnvWiring` — passed, файл не правился
- [ ] `test_orchestrator.py::TestReconciliationGate` зелёный (3 теста)
- [ ] BUG-218 цел: `write_lifecycle(..., "in_progress")` вызывается ровно один раз после успешного `_pueue_add`, и её отказ **не** превращает возврат в `False`
- [ ] EC-8: ни одна функция в `orchestrator_queue.py` не длиннее 80 строк

---

### Task 6: Верификация формы и инвариантов

**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_orchestrator.py`
  - modify: `scripts/vps/orchestrator.py` (только если Task 5 не уложился в 400)

**Step 1: добавить структурные тесты в `test_orchestrator.py`**

```python
class TestSplitStructuralInvariants:
    """EC-8, EC-9, EC-12: the shape the split exists to produce."""

    _MODULES = [
        "orchestrator.py",
        "orchestrator_slots.py",
        "orchestrator_backlog.py",
        "orchestrator_inbox.py",
        "orchestrator_queue.py",
    ]

    @pytest.mark.parametrize("name", _MODULES)
    def test_file_under_loc_limit(self, name):
        path = Path(orchestrator.__file__).parent / name
        loc = len(path.read_text(encoding="utf-8").splitlines())
        assert loc <= 400, f"{name}: {loc} LOC > 400"

    @pytest.mark.parametrize("name", _MODULES[1:])
    def test_sibling_never_imports_the_facade(self, name):
        """The invariant TECH-214 states for lifecycle: no cycle, ever."""
        src = (Path(orchestrator.__file__).parent / name).read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            assert s != "import orchestrator", f"{name}: cycle via `import orchestrator`"
            assert not s.startswith("from orchestrator import"), f"{name}: cycle"

    def test_no_function_body_over_80_lines(self):
        """EC-8: the reason the split exists — scan_queued hid a bug at 226 lines."""
        import ast

        offenders = []
        for name in self._MODULES:
            path = Path(orchestrator.__file__).parent / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    span = node.end_lineno - node.lineno
                    if span > 80:
                        offenders.append(f"{name}:{node.name} ({span})")
        assert not offenders, f"functions over 80 lines: {offenders}"
```

**Step 2: прогон**

```bash
cd scripts/vps/tests && python -m pytest test_orchestrator.py::TestSplitStructuralInvariants -q
wc -l ../orchestrator*.py
```

**Step 3 (условный):** если `orchestrator.py` > 400 — единственные разрешённые
кандидаты на вынос, в порядке возрастания риска:
1. `_setup_logging` (22) и `_load_env` (11) → `orchestrator_slots.py` + реэкспорт
   (ничего не патчит, `main` зовёт голым именем);
2. `sync_projects` уже уехала в Task 2;
3. **не выносить** `git_pull`, `startup_reconcile`, обёртку `scan_queued` — см. § Design.

**Acceptance:**
- [ ] `wc -l scripts/vps/orchestrator*.py` — каждый ≤ 400
- [ ] Ни одной функции длиннее 80 строк во всех пяти модулях
- [ ] Ни один sibling не импортирует `orchestrator`
- [ ] `cd scripts/vps/tests && python -m pytest -q` → 0 failed

---

### Execution Order

```
Task 1 (safety net)
   ↓
Task 2 (slots) → Task 3 (backlog) → Task 4 (inbox) → Task 5 (queue)
   ↓
Task 6 (form + limits)
```

Строго последовательно. Task 1 первым — он единственный, что ловит тихий провал
(патч не применился) в задачах 2-5. Task 5 последним из переносов, потому что
`orchestrator_queue` импортирует `_pueue_add` из `orchestrator_slots` (Task 2).

### Dependencies

- Task 2..6 зависят от Task 1 (сеть безопасности должна существовать до первой резки)
- Task 4 зависит от Task 2 (`orchestrator_inbox` импортирует `_pueue_add`, `pueue_has_active_label`)
- Task 5 зависит от Task 2 (`orchestrator_queue.dispatch_night_review` импортирует `_pueue_add`)
- Task 6 зависит от 2, 3, 4, 5 (проверяет итоговую форму всех пяти файлов)
- Параллелить нечего: все задачи правят `orchestrator.py`

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Поверхность совместимости зафиксирована до резки | Task 1 | ✓ |
| 2 | Слоты и pueue вынесены | Task 2 | ✓ |
| 3 | Bootstrap вынесен, ADR-026 цел | Task 3 | ✓ |
| 4 | Intake-гейт вынесен | Task 4 | ✓ |
| 5 | `scan_queued` читается по частям | Task 5 | ✓ |
| 6 | Все файлы под 400, ни одной функции >80 | Task 6 | ✓ |
| 7 | Четыре непередактируемых тест-файла зелены без правок | Task 1 (ловушка) + Acceptance задач 2-5 | ✓ |
| 8 | systemd не переустанавливается | — | имя сохранено |

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
| EC-8 | Ни одной длинной функции | AST-обход всех пяти модулей | max тело ≤ 80 строк | deterministic | Why | P1 |
| EC-9 | Все файлы под лимитом | `wc -l scripts/vps/orchestrator*.py` | каждый ≤ 400 | deterministic | user | P0 |
| EC-12 | Ни одного цикла импорта | grep `^import orchestrator$` / `^from orchestrator import` в четырёх sibling'ах | 0 попаданий | deterministic | TECH-214 § Направление импортов | P0 |
| EC-13 | Поверхность фасада цела | `hasattr(orchestrator, N)` для 28 имён | все True | deterministic | monkeypatch-инвентарь | P0 |
| EC-14 | Патч фасада виден вызывающему | `patch("orchestrator.is_agent_running", True)` → `git_pull` | `subprocess.run` не вызван | deterministic | Python docs «Where to patch» | P0 |
| EC-15 | Тело `scan_queued` в `orchestrator.py` | grep текста файла | `def scan_queued` + `CLAUDE_CURRENT_SPEC_PATH` + `env=pueue_env` внутри | deterministic | `test_autopilot_scope_guard.py:87` | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-10 | Проект с одной `queued` спекой | полный цикл `process_project` | pueue-задача создана, lifecycle → `in_progress` | integration | ADR-023 | P0 |
| EC-11 | systemd-юнит дословно | `ExecStart` из `setup-vps.sh:456` | демон стартует, пишет pid | integration | devil SA-7 | P0 |

### Coverage Summary
Deterministic: 13 | Integration: 2 | LLM-Judge: 0 | Total: 15 (min 3 ✓)

### TDD Order
1. EC-7, EC-13, EC-14, EC-15 — **первыми** (Task 1): поверхность совместимости.
   Единственный класс дефекта в этой задаче, который не даёт красного теста сам по
   себе — «патч молча не применился». Ловится только этими четырьмя.
2. EC-1, EC-2, EC-3, EC-5 — характеризация гейтов до резки
3. EC-6 — контракт старта
4. EC-10, EC-11 — интеграция
5. EC-4, EC-8, EC-9, EC-12 — форма

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
grep -n "^import orchestrator$\|^from orchestrator import" scripts/vps/orchestrator_{slots,backlog,inbox,queue}.py   # must be empty
git diff --stat -- scripts/vps/tests/test_orchestrator_git_pull.py \
                   scripts/vps/tests/test_orchestrator_in_progress.py \
                   scripts/vps/tests/test_autopilot_scope_guard.py \
                   scripts/vps/tests/test_lifecycle.py                # must be empty
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
- [ ] `scan_queued` разобрана, ни одной функции длиннее 80 строк ни в одном из пяти модулей
- [ ] Имя точки входа не изменилось

### Tests
- [ ] EC-1..EC-15 проходят
- [ ] `test_orchestrator.py::TestReconciliationGate` зелёный
- [ ] **Четыре файла вне Allowed Files зелены и не появляются в `git diff --stat`:**
      `test_orchestrator_git_pull.py`, `test_orchestrator_in_progress.py`,
      `test_autopilot_scope_guard.py`, `test_lifecycle.py`
- [ ] `test_orchestrator_bootstrap.py` и `test_orchestrator_lifecycle.py` — зелены **без правок**
      (они в Allowed Files, но план их не трогает)

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2 локально
- [ ] AV-F3, AV-F4 на VPS — демон держит код в памяти, рестарт обязателен

### Technical
- [ ] ADR-021/022/023/025/026 соблюдены
- [ ] BUG-218 цел: `in_progress` пишется после `_pueue_add`, отказ записи не откатывает диспатч; `startup_reconcile` fail-closed при `get_live_pueue_ids() is None`
- [ ] Ни один sibling не импортирует `orchestrator` (EC-12)
- [ ] В `orchestrator.py` патчимые имена вызываются **голым именем** (реэкспорт), шаги
      `orchestrator_queue` — **атрибутом модуля**. Наоборот — тихая поломка патча.

---

## Drift Log

**Checked:** 2026-07-28 UTC
**Result:** light_drift (AUTO-FIX applied)

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/orchestrator.py` | 1078 → **1117 LOC**; все диапазоны в «Карте ответственностей» сдвинулись | AUTO-FIX: карта перевыведена из HEAD, добавлена внутренняя карта `scan_queued` |
| `scripts/vps/orchestrator.py` | `scan_queued` 201 → **226 строк**, 774-975 → **786-1011** (BUG-218 добавил запись `in_progress`, 983-1009) | AUTO-FIX: § Why и § Design обновлены |
| `scripts/vps/orchestrator.py` | `startup_reconcile` 574-607 стал fail-closed (BUG-218, `get_live_pueue_ids() is None` больше не `or set()`) | AUTO-FIX: добавлен в § Контракты как инвариант, который раскол обязан сохранить |
| `scripts/vps/orchestrator.py` | `_AFTER_DEP_RE` 734 → **746** | AUTO-FIX: § Контракты |
| `scripts/vps/tests/test_orchestrator_in_progress.py` | **новый файл** (BUG-218, 225 LOC), вне Allowed Files, патчит 6 имён фасада | AUTO-FIX: добавлен в Impact Tree; Design перестроен так, чтобы файл не требовал правок |
| `scripts/vps/tests/test_autopilot_scope_guard.py` | **не был найден спекой вообще**; `:89` грепает текст `orchestrator.py` на `def scan_queued` | AUTO-FIX: добавлен в Impact Tree + § Контракты; пиннит `scan_queued` в фасаде |
| `scripts/vps/tests/test_lifecycle.py` | **не был найден спекой**; `:182` `import orchestrator`, `:197` `orchestrator.git_pull` | AUTO-FIX: добавлен в Impact Tree (правок не требует) |
| `scripts/vps/tests/test_orchestrator.py` | 1311 → ~1335 LOC | AUTO-FIX: цифра обновлена |
| `template/scripts/vps/` | не существует | sync-задача не нужна |

### References Updated

- § Why: `1078 LOC` → `1117 LOC`; `201 строка (774-975)` → `226 строк (786-1011)`
- § Context «Карта ответственностей»: все шесть групп перевыведены из HEAD
- § Context: добавлена внутренняя карта `scan_queued` и § «Правило совместимости monkeypatch»
- § Impact Tree Step 1: четыре тест-файла → **семь**, с пометкой «в Allowed Files / нет»
- § Design: добавлена таблица «Что обязано остаться в `orchestrator.py`»; `git_pull` и
  `startup_reconcile` перенесены из sibling'ов обратно в фасад; раскол пересчитан
- § Implementation Plan: 5 задач → **6**; Task 1 (сеть безопасности) — новая;
  Task 1 старой редакции («править `test_orchestrator_git_pull.py`») **удалён как
  недопустимый** — файл вне Allowed Files
- § Eval Criteria: EC-12..EC-15 добавлены; TDD Order переупорядочен

### Открытый вопрос из старой редакции — закрыт

Старый Task 1 предписывал править `test_orchestrator_git_pull.py`, которого нет в
Allowed Files. Разрешено **не расширением списка, а сужением раскола**: `git_pull`,
`is_agent_running`-вызов, `log`, `startup_reconcile` и обёртка `scan_queued` остаются
в `orchestrator.py`, поэтому оба спорных файла (и ещё два, которых спека не знала)
остаются зелёными без единой правки. Правится только `test_orchestrator.py` — он в
Allowed Files, и правки там мануальные и механические (8 + 5 перенацеленных патчей).

---

## Autopilot Log
