# Feature: [TECH-216] Раскол callback.py и разбор verify_status_sync

**Priority:** P1 | **Date:** 2026-07-27
**Size:** 6 tasks / 11 files — неделимо: `verify_status_sync` вызывает четыре из пяти
выносимых групп, поэтому границы модулей и разбор функции — одно решение, а не два.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`callback.py` — 1698 LOC, самый крупный файл дерева и единственный writer статусов спек
(ADR-023). После TECH-210 (дедупликация гейта) в нём остаётся ~1430 при лимите 400.

`verify_status_sync` — **293 строки в одной функции** (1123-1415). Это семишаговый конвейер
guard → dispatch → write, и он вызывает `gate`, `allowlist`, `scope`, `circuit` и `render` —
то есть является точкой интеграции, а не листом. Любой раскол, который уносит её в
отдельный файл от вызываемых групп, превращает каждый внутренний вызов в межмодульный.

Доказательство того, что файл уже нечитаем целиком, лежит в доках: `docs/orchestrator/
status-model.md:169` цитирует `verify_status_sync` как `callback.py:1067-1357`, а функция
начинается на 1123. Цитата была верна, когда её писали, и промахнулась на 56 строк по мере
роста файла — никто этого не заметил.

## Context

### Зависимость от TECH-210

Эта задача идёт **после** TECH-210 (`AFTER TECH-210` в backlog-строке). Причина не в
удобстве: TECH-210 удаляет из `callback.py` шесть функций и семь регэкспов, включая весь
блок `gate` (741-894) и `allowlist` (441-574). Резать файл до этого удаления — значит
провести границы модулей вокруг кода, который через задачу исчезнет.

### Карта после TECH-210

| Группа | Содержимое | ~LOC |
|---|---|---|
| `bootstrap` | `_load_env`, `_setup_logging` | 30 |
| `labels` | `resolve_label`, `parse_label`, `map_result` | 50 |
| `logs` | `_find_log_file`, `_skill_from_pueue_command`, `_parse_log_file`, `extract_agent_output` | 197 |
| `dispatch` | `resolve_spec_id`, `is_already_queued`, `_pueue_add`, `dispatch_qa`, `dispatch_reflect` | 148 |
| `scope` | `_get_started_at`, `_audit_log_path`, `_write_audit`, `_is_test_path`, `_commit_stats`, `_detect_out_of_scope_files` | 166 |
| `circuit` | `CIRCUIT_*`, `is_circuit_open`, `_pueue_pause`, `_pueue_resume`, `_trip_circuit`, `_reset_circuit_cli`, `_emit_audit`, `_record` | 198 |
| `render` | `_render_and_commit_backlog` | 28 |
| `sync` | **`verify_status_sync` (293)** | 293 |
| `events` | `write_event_for_skill` | 27 |
| `step6` | `_step6_dispatch_qa_reflect` (TECH-207) | 115 |
| `main` | CLI-вход, `# pragma: no cover` | 141 |

### Контракты

| Контракт | Где | Замечание |
|---|---|---|
| pueue callback | `setup-vps.sh:315` | `python3 callback.py {{ id }} '{{ group }}' '{{ result }}'` — зашито в `~/.config/pueue/pueue.yml` на каждом VPS, **шаблона в репозитории нет** |
| «Always exit 0» | `main` | pueue не должен видеть падение callback'а |
| единственный writer | ADR-023 | статусы пишет только `callback` через `lifecycle.write_lifecycle` |
| CI coverage-гейт | `.github/workflows/test.yml:69,72` | `--cov=callback --cov-fail-under=54` — **привязан к имени модуля** |
| operator-инструмент | `spec_operator.py:118` | `callback._reset_circuit_cli()`, приватное имя, **нулевое автоматическое покрытие** |

Coverage-гейт — тихая мина. `--cov=callback` считает покрытие модуля с именем `callback`.
Код, уехавший в `callback_logs.py`, под этот шаблон не попадает: он не станет «непокрытым»,
он просто исчезнет из измерения. Порог 54% при этом останется, и пройдёт или упадёт
непредсказуемо.

---

## Scope

**In scope:** вынос `logs`, `dispatch`, `scope`, `circuit`, `sync`+`step6` в flat
sibling-модули; разбор `verify_status_sync` на семь именованных шагов; починка
coverage-гейта под новые имена модулей; `callback.py` ≤400 LOC.

**Out of scope:** изменение логики гейта (сделано в TECH-210); изменение контракта callback
с pueue; переименование `callback.py`; изменение порогa 54% в сторону понижения.

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "import callback" scripts/vps/ --include="*.py"` → `spec_operator.py:40`,
  `tests/test_callback.py:24`, `tests/test_callback_dispatch.py:33`
- `grep -n "callback\._" scripts/vps/spec_operator.py` → строка 118, `_reset_circuit_cli`
- `grep -n "callback.py" scripts/vps/setup-vps.sh` → строка 315
- Корневые тесты: `tests/unit/test_callback_*.py` (5), `tests/integration/test_callback_*.py` (6),
  `tests/regression/test_callback_spec_corpus.py`

### Step 2: DOWN — what depends on?

```
callback.py → db, event_writer, gate_logic, lifecycle (строки 36-39)
```

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/setup-vps.sh` | 315 | pueue callback-строка | **не трогать** — имя сохраняется |
| `scripts/vps/spec_operator.py` | 118 | `callback._reset_circuit_cli()` | реэкспорт-делегат в `callback.py` |
| `.github/workflows/test.yml` | 69 | `--cov=callback` | расширить на новые модули |
| `scripts/vps/tests/test_callback.py` | 73 приватные ссылки | monkeypatch | перенацелить |
| `scripts/vps/tests/test_callback_dispatch.py` | 19 | monkeypatch | перенацелить |
| `docs/orchestrator/status-model.md` | 169 | `callback.py:1067-1357`, **уже неверна** | чинит ARCH-209 |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — два файла
- [x] `tests/**` (корень) — 12 файлов. `tests/regression/` и `tests/contracts/`
      **не редактируются** (правило иммутабельных тестов); они работают через публичный
      контракт `callback.main`, а не через приватные имена
- [x] `db/migrations/**` — нет
- [x] `ai/glossary/**` — не существует

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] `callback._reset_circuit_cli` резолвится после раскола

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/callback.py` — labels, render, events, main, реэкспорты (modify)
- `scripts/vps/callback_logs.py` — поиск и разбор лог-файлов агента (NEW)
- `scripts/vps/callback_dispatch.py` — диспатч QA и reflect (NEW)
- `scripts/vps/callback_scope.py` — детектор выхода за allowlist и audit-лог (NEW)
- `scripts/vps/callback_circuit.py` — circuit-breaker (NEW)
- `scripts/vps/callback_sync.py` — семишаговый конвейер и Step 6 (NEW)
- `scripts/vps/tests/test_callback.py` — перенацелить 73 ссылки (modify)
- `scripts/vps/tests/test_callback_dispatch.py` — перенацелить 19 ссылок (modify)
- `.github/workflows/test.yml` — coverage-гейт на новые модули (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** orchestrator — единственный writer статусов
**Cross-cutting:** Errors — «Always exit 0»; guard fail-closed (неоднозначность → `blocked`)
**Data model:** пишет `ai/lifecycle/*.yaml` только через `lifecycle.write_lifecycle`

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

Дефектный след из git-истории: BUG-185 (autostash race), TECH-166/170/176 (эволюция
guard'а), TECH-169 (circuit-breaker после массового demote), TECH-194 Layer E
(диспатч жёг $2.50 на blocked-задачу), ложная реконсиляция 2026-07-27.

---

## Risk Classification

**R1, не R0.** Рассмотрено и отклонено: публичный контракт с pueue сохраняется дословно,
формат lifecycle не меняется, откат — `git revert` плюс рестарт. Необратимость появляется
только если дефект просочится и запишет ошибочный `done` — но это свойство любой правки
`callback.py`, а не этого раскола.

Практическое следствие: 13 EC, из них шесть характеризационных, снимаются **до** резки;
деплой включает рестарт демонов и прогон `lifecycle_audit.py` до и после.

---

## Approaches

### Approach 1: Пять siblings, `verify_status_sync` уезжает вместе со своими вызываемыми (выбран)
**Source:** `research-web.md` § Approach 1; `research-codebase.md` §1 (заметка о графе вызовов)
**Summary:** `callback_sync.py` содержит и конвейер, и `_step6`; `scope`/`circuit`/`logs`/
`dispatch` — отдельные модули, которые он зовёт через атрибут
**Pros:** `monkeypatch.setattr(callback_scope, "...")` перехватывает корректно, потому что
вызов — атрибутный поиск; `callback.py` остаётся исполняемым файлом по тому же пути
**Cons:** 92 ссылки в двух тест-файлах требуют перенацеливания

### Approach 2: `verify_status_sync` остаётся в `callback.py`
**Summary:** унести всё остальное, конвейер оставить на месте
**Pros:** самый чувствительный код не переезжает
**Cons:** 293 + 141 (`main`) + 50 (`labels`) + 28 (`render`) + 27 (`events`) + импорты ≈ 570.
Над лимитом. Уложиться можно только разобрав саму функцию — а разобрав, нет причины
не унести её вместе с шагами

### Approach 3: Пакет `callback/` с `__init__.py`
**Source:** `research-web.md` § Approach 2 (отклонён там же), `research-devil.md` DA-4
**Cons:** два независимых отказа. Первый — `pueue.yml` на каждом VPS зашивает
`callback.py` буквальным путём, и шаблона в репозитории нет, то есть откатывать нечем.
Второй — реэкспорт через `__init__.py` связывает имя, и `monkeypatch.setattr(callback, ...)`
перестаёт перехватывать **молча**, при 92 живых местах в тестах

### Selected: 1
**Rationale:** Approach 2 не проходит по арифметике. Approach 3 воспроизводит ровно тот
новый класс отказа, который devil назвал главным риском всей затеи, и добавляет
невосстановимую поверхность развёртывания.

---

## Design

### Раскол

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `callback_logs.py` | `_find_log_file`, `_skill_from_pueue_command`, `_parse_log_file`, `extract_agent_output` | ~205 |
| `callback_dispatch.py` | `resolve_spec_id`, `is_already_queued`, `_pueue_add`, `dispatch_qa`, `dispatch_reflect` | ~155 |
| `callback_scope.py` | `_get_started_at`, `_audit_log_path`, `_write_audit`, `_is_test_path`, `_commit_stats`, `_detect_out_of_scope_files` | ~175 |
| `callback_circuit.py` | `CIRCUIT_*`, `is_circuit_open`, `_pueue_pause`, `_pueue_resume`, `_trip_circuit`, `_reset_circuit_cli`, `_emit_audit`, `_record` | ~205 |
| `callback_sync.py` | `verify_status_sync` (разобранная на 7 шагов), `_step6_dispatch_qa_reflect` | ~330 |
| `callback.py` | `_load_env`, `_setup_logging`, `resolve_label`, `parse_label`, `map_result`, `_render_and_commit_backlog`, `write_event_for_skill`, `main`, реэкспорты | ~290 |

### Разбор `verify_status_sync`

Функция уже описана как семь шагов в `docs/orchestrator/README.md:114-126`. Разбор
следует этому описанию — не изобретает новое членение, а делает существующее исполнимым:

| Шаг | Обязанность |
|---|---|
| 1 | резолв spec_id и чтение lifecycle |
| 2 | разбор allowlist (`gate_logic.parse_allowed_files`) |
| 3 | guard: реализация на origin/develop (`gate_logic.find_implementation_commit`) |
| 4 | детектор выхода за allowlist (`callback_scope`) |
| 5 | решение о статусе |
| 6 | запись через `lifecycle.write_lifecycle` |
| 7 | audit-JSONL (TECH-171) |

Обёртка `verify_status_sync` сохраняет имя, сигнатуру и возврат.

### Реэкспорт для operator-инструмента

```python
# callback.py — spec_operator.py:118 зовёт это имя, автоматического покрытия у него нет
_reset_circuit_cli = callback_circuit._reset_circuit_cli
```

Единственный реэкспорт-присваивание. Он допустим здесь, потому что обслуживает внешнего
потребителя, а не внутренний вызов: `verify_status_sync` зовёт
`callback_circuit._reset_circuit_cli` напрямую через модуль.

### Coverage-гейт

```yaml
--cov=callback --cov=callback_logs --cov=callback_dispatch \
--cov=callback_scope --cov=callback_circuit --cov=callback_sync
```

Порог 54% сохраняется. Если после расширения он не достигается — это настоящая дыра в
покрытии, вскрытая переносом, и её закрывают тестами, а не понижением порога.

---

## Implementation Plan

### Research Sources
- `research-codebase.md` §1 (`callback.py`) — карта групп и заметка о графе вызовов `verify_status_sync`
- `research-devil.md` DA-4, SA-2, SA-3 — ловушка monkeypatch, operator-инструмент, coverage
- `docs/orchestrator/README.md:114-126` — существующее описание семи шагов

### Task 1: Логи и диспатч
**Type:** code
**Files:**
  - create: `scripts/vps/callback_logs.py`
  - create: `scripts/vps/callback_dispatch.py`
  - modify: `scripts/vps/callback.py`
  - modify: `scripts/vps/tests/test_callback_dispatch.py`
**Pattern:** `gate_logic.py` — модуль без I/O на импорте
**Acceptance:** `test_callback_dispatch.py` зелёный; диспатч по-прежнему gated на
`task_status in ('blocked','needs_review')` (TECH-194 Layer E)

### Task 2: Scope и circuit
**Type:** code
**Files:**
  - create: `scripts/vps/callback_scope.py`
  - create: `scripts/vps/callback_circuit.py`
  - modify: `scripts/vps/callback.py`
**Pattern:** Task 1
**Acceptance:** `python3 scripts/vps/spec_operator.py reset-circuit` работает; порог
circuit-breaker'а (>3 demote за 10 минут) не изменён

### Task 3: Разбор `verify_status_sync`
**Type:** code
**Files:**
  - create: `scripts/vps/callback_sync.py`
  - modify: `scripts/vps/callback.py`
  - modify: `scripts/vps/tests/test_callback.py`
**Pattern:** семь шагов из `docs/orchestrator/README.md:114-126`
**Acceptance:** ни одна функция не длиннее 80 строк; audit-JSONL пишется ровно один раз
на вызов (TECH-171)

### Task 4: Coverage-гейт
**Type:** code
**Files:**
  - modify: `.github/workflows/test.yml`
**Pattern:** —
**Acceptance:** `--cov` покрывает все шесть модулей; `--cov-fail-under=54` **не понижен**

### Task 5: Довести до лимита
**Type:** code
**Files:**
  - modify: `scripts/vps/callback.py`
**Pattern:** —
**Acceptance:** все шесть файлов ≤ 400 LOC

### Task 6: Живая верификация
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_callback.py`
**Pattern:** `docs/orchestrator/verification.md`
**Acceptance:** дословный вызов из `pueue.yml` (`python3 callback.py <id> '<group>' '<result>'`)
на реальной завершённой задаче даёт тот же статус и тот же audit-JSONL, что до раскола

### Execution Order
1 → 2 → 3 → 4 → 5 → 6

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | TECH-210 закрыта | — | зависимость (`AFTER TECH-210`) |
| 2 | Логи и диспатч вынесены | Task 1 | ✓ |
| 3 | Scope и circuit вынесены, operator жив | Task 2 | ✓ |
| 4 | Конвейер читается по шагам | Task 3 | ✓ |
| 5 | Coverage измеряет весь код | Task 4 | ✓ |
| 6 | Все файлы под 400 | Task 5 | ✓ |
| 7 | Контракт с pueue не изменился | Task 6 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Всегда exit 0 | callback на несуществующем pueue_id | exit 0 | deterministic | контракт pueue | P0 |
| EC-2 | Guard fail-closed | git-ошибка при чтении origin/develop | статус `blocked`, не `done` | deterministic | TECH-166 | P0 |
| EC-3 | Выход за allowlist ловится | коммит трогает файл вне списка | `blocked` с указанием файла | deterministic | BUG-199 | P0 |
| EC-4 | Circuit при массовом demote | 4 demote за 10 минут | цепь открыта, pueue-группа на паузе | deterministic | TECH-169 | P0 |
| EC-5 | Диспатч gated | `task_status: complete` | QA/reflect **не** диспатчатся | deterministic | TECH-194 Layer E | P0 |
| EC-6 | audit-JSONL один раз | один вызов `verify_status_sync` | ровно одна строка | deterministic | TECH-171 | P0 |
| EC-7 | Monkeypatch перехватывает | `monkeypatch.setattr(callback_scope, "_detect_out_of_scope_files", fake)` | вызывается `fake` | deterministic | devil DA-4 | P0 |
| EC-8 | Operator-имя резолвится | `hasattr(callback, "_reset_circuit_cli")` | `True` | deterministic | devil SA-2 | P0 |
| EC-9 | Rule 7 не обойдена | попытка demote `done` | `LifecycleAlreadyDoneError` наружу | deterministic | ADR-025 | P0 |
| EC-10 | Ни одной длинной функции | AST-обход `callback_sync.py` | max тело ≤ 80 строк | deterministic | Why | P1 |
| EC-11 | Все файлы под лимитом | `wc -l scripts/vps/callback*.py` | каждый ≤ 400 | deterministic | user | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-12 | Реальная завершённая pueue-задача | дословный вызов из `pueue.yml` | статус и audit-JSONL совпадают с прогоном до раскола | integration | devil DA-6 | P0 |
| EC-13 | Coverage-гейт CI | `pytest ... --cov=callback --cov=callback_*` | ≥54%, порог не понижен | integration | devil SA-3 | P0 |

### Coverage Summary
Deterministic: 11 | Integration: 2 | LLM-Judge: 0 | Total: 13 (min 3 ✓)

### TDD Order
1. EC-12 — снять эталон (статус + audit-JSONL) **до** любой правки
2. EC-7 — доказать, что паттерн не ломает перехват; при провале менять паттерн, не тесты
3. EC-1..EC-6, EC-9 — характеризация конвейера
4. EC-8, EC-13 — внешние потребители
5. EC-10, EC-11 — форма

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Скрипт компилируется | `python -m py_compile scripts/vps/callback.py` | exit 0 | 15s |
| AV-S2 | Модули импортируемы | `PYTHONPATH=scripts/vps python -c "import callback"` | exit 0 | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты callback | — | `cd scripts/vps/tests && python -m pytest -q -k callback` | 0 failed |
| AV-F2 | Корневые тесты | — | `python -m pytest tests/ -q --ignore=tests/integration/test_claude_runner_post_result_exception.py` | не больше 6 предсуществующих Windows-падений |
| AV-F3 | Coverage-гейт | — | команда из `test.yml:65-72` с расширенным `--cov` | ≥54% |
| AV-F4 | Operator-инструмент | — | `python3 scripts/vps/spec_operator.py reset-circuit` | exit 0 |
| AV-F5 | Живой callback на VPS | VPS | завершить одну pueue-задачу, посмотреть lifecycle | статус записан, audit-строка есть |
| AV-F6 | Демоны на новом коде | VPS | `systemctl --user restart dld-orchestrator dld-gate-daemon && systemctl --user is-active dld-orchestrator dld-gate-daemon` | `active` дважды |

### Verify Command

```bash
python -m py_compile scripts/vps/callback.py
PYTHONPATH=scripts/vps python -c "import callback, callback_logs, callback_dispatch, callback_scope, callback_circuit, callback_sync"
wc -l scripts/vps/callback*.py
cd scripts/vps/tests && python -m pytest -q
python -m pytest tests/ -q --ignore=tests/integration/test_claude_runner_post_result_exception.py
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `callback.py` и пять новых модулей ≤ 400 LOC
- [ ] `verify_status_sync` разобрана на семь шагов, ни одной функции длиннее 80 строк
- [ ] `callback._reset_circuit_cli` резолвится
- [ ] Имя `callback.py` не изменилось

### Tests
- [ ] EC-1..EC-13 проходят
- [ ] `tests/regression/` и `tests/contracts/` зелёные **без правок**
- [ ] Coverage-гейт покрывает все шесть модулей, порог 54% не понижен

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2, AV-F3, AV-F4 локально
- [ ] AV-F5, AV-F6 на VPS — живой прогон, не только импорт

### Technical
- [ ] Контракт с pueue дословно тот же
- [ ] ADR-023 соблюдён: callback остаётся единственным writer'ом
- [ ] Внутренние вызовы через атрибут модуля; единственный реэкспорт — `_reset_circuit_cli`

---

## Autopilot Log

### 2026-08-30 — interactive (founder decision 29.08: not dispatched to autopilot)

Commits on develop: `148a3b5` Task 1 (logs + dispatch), `d11d8a5` Task 2 (scope + circuit),
`684fb59` Task 3 (gate → `callback_sync`, step 6 → `callback_dispatch`), plus Task 4-5.

| Check | Result |
|---|---|
| EC-10 max function body | 75 lines (`verify_status_sync`, `extract_agent_output`) |
| EC-11 `wc -l callback*.py` | 397 / 349 / 260 / 241 / 227 / 202 |
| EC-12 live callback on VPS (`callback.py 1251 claude-runner Success`, before vs after) | audit JSONL identical (only `ts`/`duration_ms` differ) |
| EC-13 coverage gate, six modules | **66 %** (threshold 54 unchanged; old single-module baseline was 65) |
| AV-F1 `scripts/vps/tests -k callback` | 83 passed |
| AV-F2 root `tests/` callback set incl. `regression/` untouched | 169 passed |
| AV-F4 `spec_operator.py reset-circuit` (local + VPS) | exit 0 |

Deviations from Design, both deliberate: `_emit_audit` lives in `callback_scope` (with its
only sink `_write_audit`), not in `callback_circuit`; `_step6_dispatch_qa_reflect` lives in
`callback_dispatch`, not `callback_sync` — it is the dispatch decision, and `callback_sync`
would have been 462 LOC otherwise. Re-exports in `callback.py` are all names root `tests/`
and `spec_operator.py` reach as `callback.<name>` (the spec counted only `_reset_circuit_cli`;
`tests/unit/test_callback_helpers.py` and `tests/integration/*` were missed by its Step 1).
The "seven steps in `docs/orchestrator/README.md:114-126`" citation in § Design is wrong —
those are the seven steps of `main()`, not of `verify_status_sync`.
