# Feature: [TECH-213] Раскол claude-runner.py и разбор run_task

**Priority:** P1 | **Date:** 2026-07-27

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`claude-runner.py` — 717 LOC при лимите 400, и **310 из них — одна функция**, `run_task`
(строки 363-673), внутри которой ещё вложена `_stderr_collector`. Это самая крупная
функция среди всех восьми файлов.

Здесь особенно ясно, почему перенос файлов не решает задачу: даже если унести из файла всё
остальное, `run_task` в 310 строк останется единственным телом, которое надо держать в
голове целиком. Лимит по файлу будет удовлетворён, а причина, по которой лимит существует,
никуда не денется.

Дополнительный аргумент за то, чтобы взяться именно за этот файл: у него **самая
неудобная тестовая связка в дереве**. Имя `claude-runner.py` содержит дефис, значит модуль
невозможно импортировать (`import claude-runner` — синтаксическая ошибка). Тесты обходят
это, парся AST файла и исполняя отдельные `FunctionDef` через `exec` в подготовленном
пространстве имён — см. `test_claude_runner_cli_resolution.py:22-35`. Каждое такое место
привязано к тому, что функция физически лежит в этом файле.

## Context

### Карта ответственностей

| Группа | Строки | Функции | ~LOC |
|---|---|---|---|
| `env` | 28-104 | `load_env` | 77 |
| `cliresolve` | 105-184 | `_cli_version`, `_resolve_cli_path` | 80 |
| `heartbeat` | 184-235 | `_write_heartbeat` | 52 |
| `resultparse` | 235-336 | `_extract_task_status`, `_usage_field`, `_session_totals` | 101 |
| `salvage` | 336-363 | `_salvage_if_needed` | 28 |
| `run` | 363-673 | **`run_task`** + вложенная `_stderr_collector` (409) | 310 |
| `main` | 674-717 | синхронная точка входа, `asyncio.run` | 44 |

### Контракты, которые нельзя ломать

| Контракт | Где | Почему хрупкий |
|---|---|---|
| `run-agent.sh:64` | `exec "$VENV_PY" "${SCRIPT_DIR}/claude-runner.py" ...` | абсолютный путь, зашит при развёртывании |
| ADR-024 (exit_code) | `run_task` | после `ResultMessage(is_error=False)` прогон успешен, что бы ни случилось дальше |
| `TIMEOUT_SECONDS`/`MAX_TURNS` | `run_task` | 5400 / 120 — гейт Session Budget всей системы опирается на эти числа |
| формат heartbeat-файла | `_write_heartbeat` | `heartbeat_reaper.py` читает **файлы**, не модуль: поля `turn`, `elapsed_s`, `last_tool`, `started_at`, `model`, `updated_at` |
| source-ассерты | `test_claude_runner_timeout.py:40,45,50,73,78,175` | читают текст `claude-runner.py` и ищут в нём подстроки |

Связь с `heartbeat_reaper.py` — через формат файла, а не через импорт. Это значит, что
TECH-211 и TECH-213 не конфликтуют и могут идти параллельно, но поля heartbeat в этой
задаче неприкосновенны.

---

## Scope

**In scope:** вынос `env`, `cliresolve`, `heartbeat`, `resultparse` в импортируемые
sibling-модули; разбор `run_task` на именованные шаги; `claude-runner.py` ≤400 LOC;
перевод AST/`exec`-тестов на обычный импорт там, где функция переехала.

**Out of scope:** переименование `claude-runner.py` (ломает `run-agent.sh` на всех VPS);
изменение `TIMEOUT_SECONDS`/`MAX_TURNS`; изменение формата heartbeat-файла; трогать
`salvage.py` (уже 237 LOC, под лимитом).

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "import claude" scripts/vps/ --include="*.py"` → **0**; импортировать
  невозможно из-за дефиса
- `grep -n "claude-runner.py" scripts/vps/run-agent.sh` → строка 64, единственный вызов
- Тесты: `test_claude_runner_cli_resolution.py` (271), `test_claude_runner_heartbeat.py` (182),
  `test_claude_runner_session_totals.py` (174), `test_claude_runner_timeout.py` (222)
- `tests/integration/test_claude_runner_post_result_exception.py` — **не собирается**
  на этой машине (`ModuleNotFoundError: claude_agent_sdk`), предсуществующая дыра окружения

### Step 2: DOWN — what depends on?

```
claude-runner.py → db (ленивый import внутри функции, строка 63), claude_agent_sdk, stdlib
                 → salvage.py (опциональный импорт, строка ~336)
```

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/run-agent.sh` | 64 | зашитый путь | **не трогать** — имя сохраняется |
| `scripts/vps/tests/test_claude_runner_cli_resolution.py` | 22-35 | AST + `exec` для `_resolve_cli_path` | перевести на `import runner_cli` |
| `scripts/vps/tests/test_claude_runner_heartbeat.py` | — | тестирует `_write_heartbeat` | перевести на `import runner_heartbeat` |
| `scripts/vps/tests/test_claude_runner_session_totals.py` | — | тестирует `_session_totals` | перевести на `import runner_result` |
| `scripts/vps/tests/test_claude_runner_timeout.py` | 40,45,50,73,78,175 | ассерты по тексту исходника | перенацелить на файл, где код осел |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — четыре файла
- [x] `tests/**` (корень) — `tests/integration/test_sdk_post_result_errors_telemetry.py`
      **не правится**, работает через subprocess
- [x] `db/migrations/**` — нет
- [x] `ai/glossary/**` — не существует

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] Имя `claude-runner.py` сохранено

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/claude-runner.py` — оставить `run_task` (разобранную) и `main` (modify)
- `scripts/vps/runner_env.py` — загрузка окружения (NEW)
- `scripts/vps/runner_cli.py` — резолв бинаря CLI по версии (NEW)
- `scripts/vps/runner_heartbeat.py` — запись heartbeat-файла (NEW)
- `scripts/vps/runner_result.py` — разбор ResultMessage и подсчёт токенов (NEW)
- `scripts/vps/tests/test_claude_runner_cli_resolution.py` — импорт вместо AST/exec (modify)
- `scripts/vps/tests/test_claude_runner_heartbeat.py` — импорт вместо AST/exec (modify)
- `scripts/vps/tests/test_claude_runner_session_totals.py` — импорт вместо AST/exec (modify)
- `scripts/vps/tests/test_claude_runner_timeout.py` — перенацелить source-ассерты (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — ADR-024: после успешного `ResultMessage` исключения логируются
как WARNING и не переопределяют `exit_code=0`
**Data model:** не затрагивается

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

Дефектный след взят из git-истории напрямую: BUG-188 (ложный fail на post-result
исключении, $258/неделю на ретраях), стухший CLI 2026-07-26 (34 автокомпакции, прогон
без merge).

---

## Approaches

### Approach 1: Импортируемые sibling-модули + разбор `run_task` (выбран)
**Source:** `research-web.md` § Approach 1; `research-devil.md` § Alternative 2
**Summary:** четыре новых модуля с подчёркиваниями в именах (импортируемы), `run_task`
остаётся в `claude-runner.py`, но её тело раскладывается на именованные шаги
**Pros:** побочно чинит самую неудобную тестовую связку в дереве — AST/`exec` заменяется
обычным импортом; `run-agent.sh` не трогается
**Cons:** четыре тестовых файла переписываются

### Approach 2: Только вынести модули, `run_task` не трогать
**Summary:** унести env/cli/heartbeat/result, оставить 310-строчную функцию как есть
**Pros:** меньше риска в самом опасном коде — SDK-цикле
**Cons:** арифметика не сходится. 717 − 310 (вынесенное) = 407, всё ещё над лимитом,
и это при условии, что вынесено вообще всё, кроме `run_task` и `main`. Формально уложиться
можно только урезав `run_task`

### Approach 3: Переименовать в `claude_runner.py` и сделать импортируемым
**Summary:** убрать дефис, тесты импортируют модуль напрямую
**Pros:** самая чистая тестовая история
**Cons:** `run-agent.sh:64` зашивает имя, и `run-agent.sh` развёрнут на каждом VPS
отдельно. Переименование = скоординированная правка на всех узлах без атомарного отката

### Selected: 1
**Rationale:** Approach 2 не достигает цели арифметически. Approach 3 достигает, но платит
той же монетой, что отвергнутая упаковка в пакеты: ломает поверхность развёртывания ради
удобства тестов. Approach 1 получает то же удобство (переехавшие функции импортируются
нормально) не трогая имя точки входа.

---

## Design

### Раскол

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `runner_env.py` | `load_env` | ~80 |
| `runner_cli.py` | `_cli_version`, `_resolve_cli_path` | ~85 |
| `runner_heartbeat.py` | `_write_heartbeat` | ~55 |
| `runner_result.py` | `_extract_task_status`, `_usage_field`, `_session_totals` | ~105 |
| `claude-runner.py` | `run_task` (разобранная), `_salvage_if_needed`, `main` | ~300 |

### Разбор `run_task`

310 строк раскладываются на шаги с говорящими именами **внутри того же файла** —
это `research-devil.md` § Alternative 2 применённый там, где он прав. Кандидаты на шаги,
по структуре текущего тела:

- построение опций SDK и резолв бинаря
- цикл приёма сообщений (тик heartbeat на сообщение)
- сбор stderr (сейчас вложенная `_stderr_collector`, строка 409 — выносится на уровень модуля)
- обработка `ResultMessage` и гейт ADR-024
- ветка таймаута и `_salvage_if_needed`

Функция-обёртка `run_task` сохраняет имя, сигнатуру и `async`-природу.

### Что запрещено менять

- `TIMEOUT_SECONDS = 5400`, `MAX_TURNS = 120` — на них опирается Session Budget всего Spark
- Поля heartbeat-файла — их читает `heartbeat_reaper.py`
- Семантика ADR-024: `exit_code=0` после успешного `ResultMessage` не переопределяется
  ничем; post-result исключения идут в `sdk_post_result_errors` как WARNING

### Правило импорта

`import runner_cli` + атрибутный вызов. Не `from runner_cli import _resolve_cli_path` —
связанное имя ломает `monkeypatch.setattr` на модуле (`research-devil.md` DA-4).

---

## Implementation Plan

### Research Sources
- `research-codebase.md` §1 (`claude-runner.py`) — карта с диапазонами строк
- `research-devil.md` § Alternative 2 — extract-function против extract-module
- `.claude/rules/architecture.md` ADR-024 — контракт exit_code

### Task 1: Вынести четыре модуля
**Type:** code
**Files:**
  - create: `scripts/vps/runner_env.py`
  - create: `scripts/vps/runner_cli.py`
  - create: `scripts/vps/runner_heartbeat.py`
  - create: `scripts/vps/runner_result.py`
  - modify: `scripts/vps/claude-runner.py`
**Pattern:** `gate_logic.py` — чистые модули, ноль I/O на импорте
**Acceptance:** `PYTHONPATH=scripts/vps python -c "import runner_env, runner_cli, runner_heartbeat, runner_result"` exit 0

### Task 2: Переписать три тестовых файла на импорт
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_claude_runner_cli_resolution.py`
  - modify: `scripts/vps/tests/test_claude_runner_heartbeat.py`
  - modify: `scripts/vps/tests/test_claude_runner_session_totals.py`
**Pattern:** `test_gate_logic.py` — прямой импорт модуля
**Acceptance:** ни одного `ast.parse` / `exec` для переехавших функций; **каждый
существующий кейс сохранён**, включая фейковые исполняемые CLI (реальные, не моки — ADR-013)

### Task 3: Разобрать `run_task`
**Type:** code
**Files:**
  - modify: `scripts/vps/claude-runner.py`
**Pattern:** пошаговая структура, описанная в § Design
**Acceptance:** ни одна функция в файле не длиннее 80 строк; `wc -l scripts/vps/claude-runner.py` ≤ 400

### Task 4: Перенацелить source-ассерты
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_claude_runner_timeout.py`
**Pattern:** —
**Acceptance:** каждый из шести ассертов (строки 40, 45, 50, 73, 78, 175) читает тот файл,
где код теперь живёт, и сохраняет исходный смысл: нет `asyncio.wait_for`, есть
`asyncio.timeout`, exit 124 на таймауте, гейт BUG-188 на месте, heartbeat тикает на каждое сообщение

### Execution Order
1 → 2 → 3 → 4

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Вспомогательные группы импортируемы | Task 1 | ✓ |
| 2 | Тесты не парсят AST | Task 2 | ✓ |
| 3 | `run_task` читается по частям | Task 3 | ✓ |
| 4 | `claude-runner.py` под 400 | Task 3 | ✓ |
| 5 | Регрессионные сторожа живы | Task 4 | ✓ |
| 6 | `run-agent.sh` не правится | — | имя файла сохранено |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Резолв CLI по версии, не по PATH | два фейковых `claude` (2.1.72 первым в PATH, 3.x вторым) | выбран 3.x | deterministic | инцидент 2026-07-26 | P0 |
| EC-2 | Гейт ADR-024 цел | `ResultMessage(is_error=False)`, затем исключение | `exit_code=0`, запись в `sdk_post_result_errors` | deterministic | BUG-188 | P0 |
| EC-3 | Таймаут даёт 124 | прогон дольше `TIMEOUT_SECONDS` | exit 124, вызван `_salvage_if_needed` | deterministic | codebase §1 | P0 |
| EC-4 | Поля heartbeat не изменились | вызов записи | ключи `turn`, `elapsed_s`, `last_tool`, `started_at`, `model`, `updated_at` | deterministic | контракт reaper | P0 |
| EC-5 | Константы бюджета не тронуты | `grep "TIMEOUT_SECONDS\|MAX_TURNS" scripts/vps/claude-runner.py` | `5400` и `120` | deterministic | Session Budget | P0 |
| EC-6 | Файл под лимитом | `wc -l scripts/vps/claude-runner.py` | ≤ 400 | deterministic | user | P0 |
| EC-7 | Ни одной длинной функции | AST-обход файла | max длина тела ≤ 80 строк | deterministic | Why | P1 |
| EC-8 | Нет `asyncio.wait_for` | текст файла | 0 попаданий | deterministic | существующий сторож | P1 |
| EC-9 | Нет связанных имён | `grep "^from runner_" scripts/vps/*.py` | 0 попаданий | deterministic | devil DA-4 | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-10 | Реальный вызов из `run-agent.sh` | дословная строка 64 с тестовой задачей | процесс стартует, пишет heartbeat, exit 0 | integration | devil SA-7 | P0 |
| EC-11 | Reaper читает свежий heartbeat | запущенный runner + `heartbeat_reaper.py` | живая сессия не убита | integration | TECH-198 | P0 |

### Coverage Summary
Deterministic: 9 | Integration: 2 | LLM-Judge: 0 | Total: 11 (min 3 ✓)

### TDD Order
1. EC-2, EC-3, EC-4 — характеризация самого опасного кода до всякой резки
2. EC-1 — переезд `_resolve_cli_path`, тест переписывается первым
3. EC-10, EC-11 — интеграция
4. EC-5..EC-9 — форма

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Скрипт компилируется | `python -m py_compile scripts/vps/claude-runner.py` | exit 0 | 15s |
| AV-S2 | Новые модули импортируемы | `PYTHONPATH=scripts/vps python -c "import runner_env, runner_cli, runner_heartbeat, runner_result"` | exit 0 | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты зелёные | — | `cd scripts/vps/tests && python -m pytest -q -k claude_runner` | 0 failed |
| AV-F2 | Весь VPS-набор | — | `cd scripts/vps/tests && python -m pytest -q` | 0 failed |
| AV-F3 | Живой прогон на VPS | VPS | dispatch одной мелкой спеки через `run-agent.sh` | задача доходит до `ResultMessage`, heartbeat пишется |

### Verify Command

```bash
python -m py_compile scripts/vps/claude-runner.py
PYTHONPATH=scripts/vps python -c "import runner_env, runner_cli, runner_heartbeat, runner_result"
wc -l scripts/vps/claude-runner.py scripts/vps/runner_*.py
cd scripts/vps/tests && python -m pytest -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `claude-runner.py` ≤ 400 LOC, четыре новых модуля ≤ 400 каждый
- [ ] Ни одна функция не длиннее 80 строк
- [ ] Имя `claude-runner.py` не изменилось

### Tests
- [ ] EC-1..EC-11 проходят
- [ ] AST/`exec`-загрузка заменена импортом там, где функция переехала
- [ ] Ни один существующий кейс не потерян при переписывании

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2 локально
- [ ] AV-F3 на VPS — живой прогон, не только импорт

### Technical
- [ ] `TIMEOUT_SECONDS` и `MAX_TURNS` не изменены
- [ ] Формат heartbeat-файла не изменён
- [ ] ADR-024 соблюдён

---

## Autopilot Log

### 2026-08-07 — operator: previous attempt is stale, do not reuse or force-done

Cycle 1 (2026-07-28 11:44) produced real, working code in worktree `.worktrees/TECH-213`
(branch `tech/TECH-213`, pushed to origin, HEAD `4eddf296`): all four `runner_*.py`
modules created, `claude-runner.py` cut to 399 LOC, tests rewritten. The 42
`claude_runner`-scoped tests pass in isolation (`pytest -q -k claude_runner` → 42 passed).
Final commit `wip(TECH-213): salvaged after timeout — not reviewed, not tested` landed at
13:18:52, ~94 minutes after dispatch — matches the known 90-minute `claude-runner`
timeout pattern (`TIMEOUT_SECONDS=5400`), not a deliberate stop.

**Do not `force-done` this.** Verified with `git merge-tree --write-tree develop
tech/TECH-213`: **CONFLICT** in `claude-runner.py`, `test_claude_runner_heartbeat.py`,
`test_claude_runner_timeout.py`. Develop moved on since the branch point
(`787af5d5`, 2026-07-28 11:44):

- `90086204` (2026-07-30) — classifier-refusal detection, +158 LOC directly inside
  `claude-runner.py` (`_refusal_from_message`, `_REFUSAL_*` constants, new exit code 4).
  This is a **safety-relevant feature the branch predates entirely** — it exists on
  neither `runner_result.py` nor anywhere else on `tech/TECH-213`.
- `5a8bff42` (2026-08-02) — lint/format sweep touching both conflicting test files.

`claude-runner.py` is 875 LOC on develop now, not the spec's baseline 717 — the §Context
line-number map and Impact Tree in this spec are stale for the same reason.

**Verdict:** the split *shape* (four sibling modules, `run_task` decomposed) is still the
right design and the isolated test pass is encouraging, but merging the branch as-is would
either silently drop the refusal-detection safety code or require a real conflict
resolution I have not attempted. Redispatching instead of force-done: a fresh
Impact Tree Analysis against current develop must account for `90086204`'s addition
(where does refusal detection land in the new module map — most likely `runner_result.py`
alongside `_extract_task_status`, but that's a planner decision, not made here).
`tech/TECH-213` is pushed to origin, so the worktree-setup sweep will reclaim
`.worktrees/TECH-213` automatically on next dispatch (already-pushed branch condition) —
no manual cleanup needed. Recovery reference if ever wanted: commit `4eddf296`.
