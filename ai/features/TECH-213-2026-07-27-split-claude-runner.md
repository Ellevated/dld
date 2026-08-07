# Feature: [TECH-213] Раскол claude-runner.py и разбор run_task

**Priority:** P1 | **Date:** 2026-07-27

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`claude-runner.py` — **875 LOC** при лимите 400 (было 717 на дату спеки; `90086204`
добавил ~158 строк детекта classifier-refusal), и **363 из них — одна функция**,
`run_task` (строки 467-829), внутри которой ещё вложена `_stderr_collector`. Это самая
крупная функция среди всех восьми файлов.

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

Перепроверена по файлу в worktree 2026-08-07 (875 LOC). Прежняя таблица описывала
baseline 717 LOC и во всех строках, кроме имён функций, была неверна.

| Группа | Строки | Символы | LOC |
|---|---|---|---|
| `header` | 1-25 | docstring модуля + stdlib-импорты | 25 |
| `env` | 28-47 | `load_env` + вызов на module scope (строка 47) | 20 |
| `deps` | 49-72 | импорт SDK, ленивые `_orch_db` (db), `_salvage` (salvage) | 24 |
| `config` | 74-92 | `MAX_TURNS`, `TIMEOUT_SECONDS`, `MODEL`, `AUTOPILOT_EFFORT`, `_VALID_EFFORT` | 19 |
| `cliresolve` | 95-172 | `_MIN_CLI_VERSION`, `_SYSTEM_CLI_FALLBACK`, `_cli_version` (105-120), `_resolve_cli_path` (123-169), `CLI_PATH, CLI_VERSION = …` (172) | 78 |
| `logging` | 174-181 | `LOG_DIR`, `basicConfig`, `logger` | 8 |
| `heartbeat` | 184-209 | `_write_heartbeat` | 26 |
| `tools` | 212-225 | `ALLOWED_TOOLS` | 14 |
| `taskstatus` | 228-246 | `_TASK_STATUS_RE`, `_extract_task_status` | 19 |
| `refusal` **(новое, `90086204`)** | 249-349 | `_REFUSAL_STOP_REASON/_TEXT_LIMIT/_EVENT_LIMIT`, `_message_text` (263), `_refusal_from_message` (273-322), `_refusal_summary` (325-349) | 101 |
| `usage` | 352-428 | `_EXPECTED_MODELS`, `_usage_field` (367), `_session_totals` (378-428) | 77 |
| `exit` | 431-437 | `_EXIT_REASONS` (включая `4: "classifier_refusal"`) | 7 |
| `salvage` | 440-461 | `_salvage_if_needed` | 22 |
| `run` | 467-829 | **`run_task`** + вложенная `_stderr_collector` (513) | 363 |
| `main` | 832-875 | синхронная точка входа, SIGTERM-хендлер, `asyncio.run` | 44 |

Внутренняя разбивка `run_task` (для §Design «Разбор»):

| Шаг | Строки | LOC |
|---|---|---|
| пролог: пути, ts_label, prompt | 472-483 | 12 |
| стартовый `logger.info` | 485-495 | 11 |
| предупреждение о стухшем CLI (`_MIN_CLI_VERSION`) | 496-508 | 13 |
| `stderr_lines` + `_stderr_collector` | 510-517 | 8 |
| `ClaudeAgentOptions(...)` (включая `env={...}` с `CLAUDE_CURRENT_SPEC_PATH`) | 519-544 | 26 |
| инициализация 12 переменных состояния | 546-564 | 19 |
| `asyncio.timeout` + `async for message in query(...)` | 566-645 | 80 |
| цепочка `except` (Timeout / CLIConnection / Process / Exception+BUG-188) | 650-714 | 65 |
| `turns` fallback | 716-721 | 6 |
| `_refusal_summary` + WARNING + апгрейд exit 4 | 723-741 | 19 |
| `_salvage_if_needed` | 743 | 1 |
| cache-rate, `log_data`, session totals, drift WARNING | 745-794 | 50 |
| телеметрия refusal (`_orch_db.log_classifier_refusal`) | 795-815 | 21 |
| запись лог-файла + финальный `logger.info` | 816-827 | 12 |

### Контракты, которые нельзя ломать

| Контракт | Где | Почему хрупкий |
|---|---|---|
| `run-agent.sh:64` | `exec "$VENV_PY" "${SCRIPT_DIR}/claude-runner.py" ...` | абсолютный путь, зашит при развёртывании (проверено 2026-08-07 — строка та же) |
| ADR-024 (exit_code) | `run_task`, строки 682-707 | после `ResultMessage(is_error=False)` прогон успешен, что бы ни случилось дальше |
| exit 4 (`classifier_refusal`) | `run_task`, строки 736-741 | апгрейд только с 0; таймаут/process error сохраняют свой более конкретный код |
| `TIMEOUT_SECONDS`/`MAX_TURNS` | строки 77-78 | 5400 / 120 — гейт Session Budget всей системы опирается на эти числа |
| формат heartbeat-файла | `_write_heartbeat` | `heartbeat_reaper.py` читает **файлы**, не модуль: поля `turn`, `elapsed_s`, `last_tool`, `started_at`, `model`, `updated_at` |
| module-атрибуты рантайма | `LOG_DIR`, `query`, `ClaudeAgentOptions`, `_orch_db`, `_salvage`, `_EXIT_REASONS`, `run_task` | их патчат `monkeypatch.setattr(claude_runner, …)` три тестовых файла; **должны остаться глобалами `claude-runner.py`, вызываемыми по голому имени** |
| source-ассерты по тексту `claude-runner.py` | `test_claude_runner_timeout.py:41,47,52,77,82,185`; `test_claude_runner_refusal.py:468,475`; `test_autopilot_scope_guard.py:117,120` | читают текст файла и ищут подстроки — спека называла строки 40,45,50,73,78,175 и не знала про два последних файла |

Связь с `heartbeat_reaper.py` — через формат файла, а не через импорт. Это значит, что
TECH-211 и TECH-213 не конфликтуют и могут идти параллельно, но поля heartbeat в этой
задаче неприкосновенны.

---

## Scope

**In scope:** вынос `env`, `cliresolve`, `heartbeat`, `refusal`, `resultparse` в
импортируемые sibling-модули (пять, не четыре — арифметика при 875 LOC, §Design);
вынос состояния прогона и сборки лог-данных из тела `run_task`; разбор `run_task` на
именованные шаги; `claude-runner.py` ≤400 LOC; перевод AST/`exec`-тестов на обычный
импорт там, где функция переехала.

**Out of scope:** переименование `claude-runner.py` (ломает `run-agent.sh` на всех VPS);
изменение `TIMEOUT_SECONDS`/`MAX_TURNS`; изменение формата heartbeat-файла; трогать
`salvage.py` (уже 237 LOC, под лимитом).

---

## Impact Tree Analysis

> Перезапущено 2026-08-07 против текущего develop (875 LOC). Прежний прогон
> не знал о `test_claude_runner_refusal.py` (533 LOC, создан `90086204`) и
> о source-ассерте в `test_autopilot_scope_guard.py`. Обе находки меняют границы
> задачи — см. §Blocker ниже.

### Step 1: UP — who uses?

- `grep -rn "import claude" scripts/vps/ --include="*.py"` → **0**; импортировать
  невозможно из-за дефиса
- `grep -n "claude-runner.py" scripts/vps/run-agent.sh` → строка 64, единственный вызов
- Тесты в `scripts/vps/tests/`, грузящие или парсящие файл — **пять**, не четыре:

  | Файл | LOC | Как достаёт код | В Allowed Files? |
  |---|---|---|---|
  | `test_claude_runner_cli_resolution.py` | 272 | `ast.parse` + `exec` двух `FunctionDef` (строки 40-50, `exec` в 65) | да |
  | `test_claude_runner_heartbeat.py` | 195 | `ast.parse` + `exec` одной `FunctionDef` (34-62, `exec` в 51 и 61) | да |
  | `test_claude_runner_session_totals.py` | 175 | `ast.parse` + `exec` двух `FunctionDef` (35-53, `exec` в 51) | да |
  | `test_claude_runner_timeout.py` | 223 | `importlib` загрузка модуля (96-129) + `mod._write_heartbeat` (136,161,171) + текстовые ассерты (41,47,52,77,82,185) | да |
  | **`test_claude_runner_refusal.py`** | **533** | `importlib` загрузка модуля целиком под фейковым SDK + `runner._refusal_from_message`, `runner._refusal_summary`, `runner._REFUSAL_TEXT_LIMIT`, `runner._REFUSAL_EVENT_LIMIT`, `runner._EXIT_REASONS[4]`, `runner._orch_db`, `runner._salvage`, `runner.LOG_DIR`, `runner.query` + текстовые ассерты (468, 475) | **НЕТ** |

- `scripts/vps/tests/test_autopilot_scope_guard.py:113-122` — читает текст
  `claude-runner.py` и требует наличия литералов `"CLAUDE_CURRENT_SPEC_PATH"` и
  `os.environ.get("CLAUDE_CURRENT_SPEC_PATH"`. **Не в Allowed Files.** Следствие:
  словарь `env={...}` внутри `ClaudeAgentOptions` (строки 528-542) остаётся в
  `claude-runner.py`. Формально ассерт прошёл бы и от строки 450 в
  `_salvage_if_needed`, поэтому перенос env-словаря был бы *молчаливым* обходом
  теста — запрещено.
- `tests/integration/test_claude_runner_post_result_exception.py` — `importorskip`
  на `claude_agent_sdk`, на этой машине **скипается**, на VPS/CI выполняется.
  Патчит `claude_runner.LOG_DIR`, `.query`, `.ClaudeAgentOptions`, `._orch_db`;
  добавляет `scripts/vps` в `sys.path` (строки 60-61) → sibling-импорты
  разрешатся. Правок **не требует**, если перечисленные имена остаются глобалами
  `claude-runner.py`.
- `tests/integration/test_sdk_post_result_errors_telemetry.py` — через subprocess,
  правок не требует.

### Step 2: DOWN — what depends on?

```
claude-runner.py → claude_agent_sdk (module scope, строки 50-57), stdlib
                 → db.py         (опциональный import as _orch_db, строка 63)
                 → salvage.py    (опциональный import as _salvage,  строка 70)
```

Sibling-импорт по голому имени уже является рабочим паттерном этого файла (`import db`,
`import salvage`) — он работает, потому что каталог скрипта попадает в `sys.path[0]`
при `exec`-запуске из `run-agent.sh`, а все тестовые файлы кладут `scripts/vps` в
`sys.path` вручную. Новым `runner_*` модулям отдельная страховка не нужна.

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/run-agent.sh` | 64 | зашитый путь | **не трогать** — имя сохраняется |
| `scripts/vps/tests/test_claude_runner_cli_resolution.py` | 40-50, 53-66 | AST + `exec` | `import runner_cli`, `monkeypatch.setattr(runner_cli, "_SYSTEM_CLI_FALLBACK", …)` вместо инъекции в namespace |
| `scripts/vps/tests/test_claude_runner_heartbeat.py` | 23-62 | AST + `exec` | `import runner_heartbeat` |
| `scripts/vps/tests/test_claude_runner_session_totals.py` | 35-53 | AST + `exec` | `import runner_result`, `monkeypatch.setattr(runner_result, "_EXPECTED_MODELS", …)` |
| `scripts/vps/tests/test_claude_runner_timeout.py` | 41,47,52,77,82,136,161,171,185 | текст + `mod._write_heartbeat` | heartbeat-кейсы → `import runner_heartbeat`; текстовые ассерты перенацелить на файл, где код осел |
| `scripts/vps/tests/test_claude_runner_refusal.py` | 221-338 (атрибуты), 468/475 (текст) | **вне Allowed Files** | требует правки — см. §Blocker |
| `scripts/vps/tests/test_autopilot_scope_guard.py` | 113-122 | **вне Allowed Files** | правок **не требует** при условии, что `env={...}` остаётся в `claude-runner.py` |
| `.claude/rules/dependencies.md` | секция `claude-runner.py` | вне Allowed Files | останется без строк про новые модули (в TECH-212/TECH-215 такие строки добавлялись). Отдельно: там указан `run-agent.sh:47`, фактический вызов на **64** — предсуществующий дрейф, не этой задачи |
| `.claude/rules/model-capabilities.md` | §«What claude-runner now catches» | вне Allowed Files | фраза «`claude-runner.py` inspects every SDK message (`_refusal_from_message`)» остаётся операционно верной (вызов по-прежнему в `run_task`), но функция физически переезжает |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — **шесть** файлов затронуто (пять грузят код, шестой читает текст); правки нужны пяти
- [x] `tests/**` (корень) — два интеграционных файла, правок не требуют
- [x] `template/**` — `scripts/vps/` не зеркалится в `template/`, sync-таска не нужна
- [x] `db/migrations/**` — нет
- [x] `ai/glossary/**` — не существует

### Step 5: DUAL SYSTEM

Источник данных не меняется. Единственная «двойная система» — heartbeat: файл пишет
`claude-runner.py`, читает `heartbeat_reaper.py`, связь по формату, а не по импорту.
Формат неприкосновенен.

### Verification

- [x] Имя `claude-runner.py` сохранено
- [ ] **Все найденные файлы в Allowed Files — НЕТ.** Не хватает двух записей, см. §Blocker

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
**Cons:** арифметика не сходится, и при 875 LOC не сходится с большим запасом:
875 − 342 (всё, что можно вынести целыми группами) + 6 = **539**, и это при условии,
что вынесено вообще всё, кроме `run_task`, `main`, конфига и `_salvage_if_needed`.
Уложиться можно только вынув часть тела `run_task` — см. Task 7

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

Пересчитано против 875 LOC (2026-08-07). **Четырёх модулей арифметически не хватает:**
вынос `env`+`cliresolve`+`heartbeat`+`resultparse` снимает 342 строки, оставляя
875 − 342 + 6 = **539**, а разбор `run_task` на шаги внутри файла LOC не уменьшает
(скорее добавляет ~15 на сигнатуры). Нужен пятый модуль **и** вынос части тела
`run_task` в `runner_result.py`.

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `runner_env.py` | `load_env` | ~40 |
| `runner_cli.py` | `_MIN_CLI_VERSION`, `_SYSTEM_CLI_FALLBACK`, `_cli_version`, `_resolve_cli_path`, `ALLOWED_TOOLS`, `log_startup`, `warn_if_stale` | ~130 |
| `runner_heartbeat.py` | `_write_heartbeat` | ~45 |
| `runner_refusal.py` **(новый, вне Allowed Files)** | `_REFUSAL_*`, `_message_text`, `_refusal_from_message`, `_refusal_summary`, `warn`, `log_telemetry` | ~145 |
| `runner_result.py` | `_TASK_STATUS_RE`, `_extract_task_status`, `_EXPECTED_MODELS`, `_usage_field`, `_session_totals`, `RunState`, `absorb_assistant`, `absorb_result`, `build_log_data`, `log_completion`, `log_post_result_error` | ~290 |
| `claude-runner.py` | импорты, `MAX_TURNS`/`TIMEOUT_SECONDS`/`MODEL`/`AUTOPILOT_EFFORT`/`_VALID_EFFORT`, `LOG_DIR`/`logger`, `CLI_PATH`/`CLI_VERSION`, `_EXIT_REASONS`, `_salvage_if_needed`, разобранная `run_task`, `main` | **≤400** (расчёт: ~382) |

### Куда садится детект refusal — и почему не в `runner_result.py`

Решение планировщика: **отдельный `runner_refusal.py`**.

1. **Размер.** `runner_result.py` и так забирает ~290 LOC. Добавить туда 101 строку
   refusal — это 390 LOC, то есть ровно тот же «файл, который надо держать в голове
   целиком», от которого спека избавляется, только этажом ниже.
2. **Разный предмет.** `runner_result` отвечает на вопрос «что прогон произвёл и
   сколько это стоило». `runner_refusal` отвечает на «отказала ли модель и делает ли
   это прогон провальным» — он владеет решением об exit-коде 4 и контрактом
   безопасности из ADR-029. Это не подвид парсинга usage.
3. **Своя тестовая поверхность.** У refusal 533 строки собственных тестов
   (`test_claude_runner_refusal.py`), у session totals — свои 175. Держать их
   предметы в одном модуле значит склеить два независимых набора.
4. **Направление зависимостей чистое.** `runner_refusal` — лист на stdlib, duck-typed
   по сообщению, SDK не импортирует. `claude-runner.py` вызывает его напрямую из
   цикла; `runner_result` его не импортирует. Циклов нет.

Цена решения одна и она не зависит от выбора модуля: как только эти функции покидают
`claude-runner.py`, обращения `runner._refusal_from_message` в
`test_claude_runner_refusal.py` перестают резолвиться. Тот же ремонт потребовался бы
и при посадке в `runner_result.py`.

### Что физически обязано остаться в `claude-runner.py`

Не стилистика — на этом стоят ассерты в файлах, которые править нельзя:

- `LOG_DIR`, `query`, `ClaudeAgentOptions`, `_orch_db`, `_salvage`, `_EXIT_REASONS`,
  `run_task` — глобалы модуля, вызываемые **по голому имени**
- цепочка `except` с литералами `result_received and not result_is_error` и
  `elif "timeout"`, и между ними ни одного `exit_code =`
- строка `if refusal["unrecovered"] and exit_code == 0:` дословно
- `except TimeoutError:` с `exit_code = 124` (AST-ассерт)
- `asyncio.timeout`, и ни одного `asyncio.wait_for`
- словарь `env={...}` в `ClaudeAgentOptions` с `CLAUDE_CURRENT_SPEC_PATH`
- `TIMEOUT_SECONDS = 5400`, `MAX_TURNS = 120`, `_VALID_EFFORT`

### Разбор `run_task`

363 строки раскладываются на шаги с говорящими именами **внутри того же файла** —
это `research-devil.md` § Alternative 2 применённый там, где он прав:

| Функция | Что держит | ~LOC |
|---|---|---|
| `_RunContext` (dataclass) | `project_path`, `project_name`, `ts_label`, `log_file`, `started_at_iso`, `started_mono`, `prompt` | 12 |
| `_prepare_run(project_dir, task, skill)` | пролог + стартовый лог + предупреждение о стухшем CLI | 18 |
| `_build_options(ctx, stderr_collector)` | `ClaudeAgentOptions(...)` целиком, включая `env={...}` | 35 |
| `_enrich_error(exc, stderr_lines)` | склейка stderr в текст ошибки | 11 |
| `async _execute(ctx, state, options, stderr_lines)` | `asyncio.timeout` + `async for message in query(...)` + вся цепочка `except`; возвращает `(exit_code, result_text)` | ~70 |
| `_finalize(ctx, state, exit_code, task, skill)` | refusal-сводка и апгрейд до 4, salvage, `build_log_data`, запись лог-файла, финальный лог | ~40 |
| `async run_task(project_dir, task, skill)` | обёртка: имя, сигнатура и `async`-природа сохранены | ~20 |

Ни одно тело не длиннее 80 строк (EC-7).

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

> Перегенерирован 2026-08-07 против develop @ 875 LOC. Прежний план (baseline 717,
> четыре модуля, четыре таски) не учитывал `90086204` и арифметически не сходился.
> Ветку `tech/TECH-213` @ `4eddf296` **не переиспользовать** — планировать с нуля.

### BLOCKER — Allowed Files не покрывает фактическую поверхность

План требует два файла, которых нет в `## Allowed Files`. Оба неизбежны:

| Файл | Что с ним | Почему нельзя обойтись |
|---|---|---|
| `scripts/vps/runner_refusal.py` (NEW) | создать | без пятого модуля `claude-runner.py` садится на ~485 LOC (см. §Design «Раскол»). Посадка refusal в `runner_result.py` вместо этого уводит тот файл на ~390 LOC и **не снимает вторую строку** |
| `scripts/vps/tests/test_claude_runner_refusal.py` | modify (~20 точечных правок) | 533 строки тестов обращаются к `runner._refusal_from_message`, `runner._refusal_summary`, `runner._REFUSAL_TEXT_LIMIT`, `runner._REFUSAL_EVENT_LIMIT`. Как только эти имена покидают `claude-runner.py` — любым маршрутом — обращения перестают резолвиться. Оставить их в `claude-runner.py` = отказаться от DoD «≤400 LOC» |

Единственная альтернатива, не требующая расширения: держать refusal в
`claude-runner.py` и принять ~473 LOC, то есть провалить главный пункт DoD.
Обходной путь через `from runner_refusal import _refusal_from_message` запрещён
правилом импорта (§Design) — связанное имя ломает `monkeypatch.setattr`.

**Действие оператора:** дописать две строки в `## Allowed Files`:

```
- `scripts/vps/runner_refusal.py` — детект classifier-refusal (NEW)
- `scripts/vps/tests/test_claude_runner_refusal.py` — импорт вместо атрибутов модуля (modify)
```

До этого Task 5 и Task 8b выйдут за периметр. Остальные таски внутри периметра.

### Research Sources
- `research-codebase.md` §1 (`claude-runner.py`) — карта с диапазонами строк (**устарела**, заменена таблицей в §Context)
- `research-devil.md` § Alternative 2 — extract-function против extract-module
- `.claude/rules/architecture.md` ADR-024 — контракт exit_code
- `.claude/rules/model-capabilities.md` §Breaking Changes — контракт exit 4 / `classifier_refusals`

Веб-исследование не проводилось: задача целиком о внутренней структуре файла,
внешних API не касается, а поведение `asyncio.timeout` и `importlib` за
последний год не менялось. Отказ от 6 разрешённых вызовов сознательный.

---

### Правило, действующее во всех тасках

Импорт sibling-модулей — **только** `import runner_x` + атрибутный вызов.
`from runner_x import y` и присваивания-алиасы (`_y = runner_x._y`) запрещены:
связанное имя ломает `monkeypatch.setattr` на модуле (`research-devil.md` DA-4).
Имена переезжающих функций **не меняются** — `_cli_version`, `_resolve_cli_path`,
`_write_heartbeat`, `_extract_task_status`, `_usage_field`, `_session_totals`,
`_message_text`, `_refusal_from_message`, `_refusal_summary` сохраняют написание,
включая ведущее подчёркивание. Это держит в силе ссылки в
`.claude/rules/dependencies.md` и `model-capabilities.md`, которые править нельзя.

Каждая таска = один коммит, и после каждой `python3 -m pytest scripts/vps/tests/ -q`
должен быть зелёным. Ни одна таска не оставляет suite красным «до следующей».

---

### Task 1: Зафиксировать характеризационный baseline

**Type:** test
**Files:** ничего не изменяется (замер)
**Context:** прежде чем резать самый опасный файл в дереве, надо знать точное число
проходящих кейсов — иначе «42 passed» после рефакторинга нечем сверить, и потерянный
кейс не отличим от кейса, которого не было.

**Steps:**
```bash
cd /home/dld/projects/dld/.worktrees/TECH-213
python3 -m pytest scripts/vps/tests/ -q 2>&1 | tail -3
python3 -m pytest scripts/vps/tests/ -q -k claude_runner 2>&1 | tail -3
python3 -m pytest tests/integration/test_claude_runner_post_result_exception.py -q 2>&1 | tail -3
wc -l scripts/vps/claude-runner.py
```
Записать три числа в тело коммита следующей таски.
Ожидаемо: третья команда — `1 skipped` (нет `claude_agent_sdk` на этой машине,
`importorskip`, предсуществующая дыра окружения — **не** регрессия).
Четвёртая: `875`.

**Acceptance:** три числа зафиксированы; `wc -l` = 875 (если нет — develop уехал
ещё раз, план пересчитать).

---

### Task 2: `runner_env.py`

**Type:** code
**Files:**
- Create: `scripts/vps/runner_env.py`
- Modify: `scripts/vps/claude-runner.py:28-47`

**Context:** самый безопасный первый разрез — `load_env` ни от чего не зависит, и ни
один тест не обращается к нему по атрибуту.

**Steps:**

1. Создать `scripts/vps/runner_env.py`:
```python
#!/usr/bin/env python3
"""
Module: runner_env
Role: .env loading for claude-runner. Zero I/O beyond the read it is asked for.
Uses: os, pathlib
Used by: claude-runner.py
"""

import os
from pathlib import Path


def load_env() -> None:
    """Load KEY=VALUE pairs from .env file next to claude-runner into os.environ.

    Uses setdefault so existing env vars win (e.g., systemd EnvironmentFile).
    """
    env_path = Path(__file__).parent / ".env"
    ...  # тело — строки 33-44 claude-runner.py дословно
```
   `Path(__file__).parent` даёт тот же каталог: модуль лежит рядом с
   `claude-runner.py`. Проверить это явно (см. Acceptance).

2. В `claude-runner.py` удалить `def load_env` (28-45), заменить строку 47:
```python
import runner_env

runner_env.load_env()
```
   `import runner_env` кладётся **после** stdlib-импортов и **до** блока
   `try: from claude_agent_sdk ...`, потому что `load_env()` обязан отработать раньше,
   чем что-либо читает окружение.

**Acceptance:**
```bash
python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import runner_env; print(runner_env.load_env())"   # None, exit 0
python3 -m py_compile scripts/vps/claude-runner.py
python3 -m pytest scripts/vps/tests/ -q          # столько же passed, сколько в Task 1
grep -c "def load_env" scripts/vps/claude-runner.py   # 0
```
EC-покрытие: подготовка, собственных EC нет.

---

### Task 3: `runner_heartbeat.py` + два его теста

**Type:** code + test
**Files:**
- Create: `scripts/vps/runner_heartbeat.py`
- Modify: `scripts/vps/claude-runner.py:184-209` и вызов в цикле (578-587)
- Modify: `scripts/vps/tests/test_claude_runner_heartbeat.py`
- Modify: `scripts/vps/tests/test_claude_runner_timeout.py` (только класс `TestHeartbeatWriter`)

> Четыре файла вместо трёх — сознательно. `test_claude_runner_timeout.py:136,161,171`
> вызывает `mod._write_heartbeat` на загруженном `claude-runner.py`; разнести это на
> отдельную таску значит оставить suite красным между коммитами, что запрещено
> жёстче, чем «≤3 файла».

**Context:** формат heartbeat-файла читает `heartbeat_reaper.py` — по файлу, не по
импорту. Поля неприкосновенны (EC-4).

**Steps:**

1. `scripts/vps/runner_heartbeat.py` — `_write_heartbeat` (строки 184-209) дословно,
   плюс шапка модуля и импорты `json`, `os`, `datetime`, `pathlib.Path`. Тело менять
   нельзя: ключи `turn`, `elapsed_s`, `last_tool`, `started_at`, `model`, `updated_at`,
   запись через `.tmp` + `os.replace`, `except Exception: pass` (ADR-004).

2. В `claude-runner.py`: удалить функцию, добавить `import runner_heartbeat`, вызов в
   цикле стал:
```python
                runner_heartbeat._write_heartbeat(
                    LOG_DIR,
                    ctx.project_name,
                    ctx.ts_label,
                    state.turn_count,
                    int(time.monotonic() - ctx.started_mono),
                    state.last_tool_name,
                    ctx.started_at_iso,
                    MODEL,
                )
```
   (на этой таске `ctx`/`state` ещё не существуют — использовать текущие локальные
   имена `project_name`, `ts_label`, `turn_count`, `last_tool_name`, `started_mono`,
   `started_at_iso`; переименование придёт в Task 7/8.)

3. `test_claude_runner_heartbeat.py`: удалить строки 15-62 (весь блок
   `importlib`/`ast`/`exec`), заменить на:
```python
import sys
from pathlib import Path

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import runner_heartbeat  # noqa: E402

_write_heartbeat = runner_heartbeat._write_heartbeat
```
   Модульный алиас в **тесте** допустим (тест ничего не монкейпатчит на этом имени) и
   сохраняет все пять кейсов без правки их тел. Правило «не связывать имена»
   относится к продакшн-модулям.

4. `test_claude_runner_timeout.py`: класс `TestHeartbeatWriter` — выбросить
   `_load_module` (строки 96-129) и заменить `mod._write_heartbeat(...)` на
   `runner_heartbeat._write_heartbeat(...)` в трёх кейсах (136, 161, 171).
   Кейс `test_heartbeat_called_per_message_in_source` (178-192) на этой таске
   **не трогать** — он про `claude-runner.py`, чинится в Task 8b.

**Acceptance:**
```bash
python3 -m pytest scripts/vps/tests/test_claude_runner_heartbeat.py -q     # 5 passed
python3 -m pytest scripts/vps/tests/test_claude_runner_timeout.py -q       # столько же, сколько в Task 1
grep -n "ast.parse\|exec(" scripts/vps/tests/test_claude_runner_heartbeat.py   # пусто
python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import runner_heartbeat, inspect; print(sorted(inspect.signature(runner_heartbeat._write_heartbeat).parameters))"
```
Последняя команда должна напечатать ровно
`['elapsed_s', 'last_tool', 'log_dir', 'model', 'project_name', 'started_at_iso', 'ts_label', 'turn']`.
EC-покрытие: **EC-4**.

---

### Task 4: `runner_cli.py` + его тест

**Type:** code + test
**Files:**
- Create: `scripts/vps/runner_cli.py`
- Modify: `scripts/vps/claude-runner.py:94-172, 212-225, 485-508`
- Modify: `scripts/vps/tests/test_claude_runner_cli_resolution.py`

**Context:** это регрессия 2026-07-26 (34 автокомпакции, прогон без merge). Тест —
самый ценный в связке, и именно он сейчас держится на `exec` двух `FunctionDef`.

**Steps:**

1. `scripts/vps/runner_cli.py` содержит, дословно перенесённые:
   - `_MIN_CLI_VERSION = (2, 1, 190)` с комментарием (95-98)
   - `_SYSTEM_CLI_FALLBACK = "/usr/local/bin/claude"` с комментарием (100-102)
   - `_cli_version` (105-120)
   - `_resolve_cli_path` (123-169) — включая весь docstring про инцидент
   - `ALLOWED_TOOLS` (212-225)

   плюс две новые функции, забирающие логирование из `run_task`:
```python
def log_startup(logger, project_name, skill, prompt, project_path,
                cli_path, cli_version, model, effort) -> None:
    """The one line that says which binary, which model, which effort actually ran."""
    logger.info(
        "project=%s skill=%s prompt=%s cwd=%s cli=%s v=%s model=%s effort=%s",
        project_name, skill, prompt, project_path, cli_path,
        ".".join(map(str, cli_version)) if cli_version else "unknown",
        model, effort,
    )


def warn_if_stale(logger, cli_path, cli_version, model) -> None:
    """A CLI predating the pinned model runs its own default and says nothing."""
    if cli_version is not None and cli_version < _MIN_CLI_VERSION:
        logger.warning(...)   # текст строк 500-508 дословно
```
   Модуль **не импортирует** `claude_agent_sdk` — от этого зависит возможность
   импортировать его в окружении без SDK, ради чего тест и переписывается.

2. `claude-runner.py`: `import runner_cli`; строка 172 становится
```python
CLI_PATH, CLI_VERSION = runner_cli._resolve_cli_path()
```
   `ALLOWED_TOOLS` в `ClaudeAgentOptions` → `allowed_tools=runner_cli.ALLOWED_TOOLS`.
   Строки 485-508 → два вызова `runner_cli.log_startup(...)` и
   `runner_cli.warn_if_stale(logger, CLI_PATH, CLI_VERSION, MODEL)`.

3. `test_claude_runner_cli_resolution.py`: удалить строки 37-66 (`ast`/`exec`/`_build_ns`),
   заменить на импорт + фикстуру, патчащую константу на модуле:
```python
import runner_cli  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    return {"tmp": tmp_path, "home": home, "nowhere": str(tmp_path / "nowhere" / "claude")}


def _use_fallback(monkeypatch, path: str) -> None:
    """Point the distro-install probe somewhere hermetic (was `_build_ns(...)`)."""
    monkeypatch.setattr(runner_cli, "_SYSTEM_CLI_FALLBACK", path)
```
   В каждом из 13 кейсов `ns = _build_ns(X)` → `_use_fallback(monkeypatch, X)`, а
   `ns["_resolve_cli_path"]()` → `runner_cli._resolve_cli_path()`,
   `ns["_cli_version"](p)` → `runner_cli._cli_version(p)`,
   `ns["_MIN_CLI_VERSION"]` → `runner_cli._MIN_CLI_VERSION`.
   В `test_same_binary_reached_twice_is_probed_once` подмена счётчика становится
   `monkeypatch.setattr(runner_cli, "_cli_version", spy)` — работает потому,
   что `_resolve_cli_path` зовёт `_cli_version` по голому имени, то есть через
   глобаль своего модуля. Это и есть причина правила импорта.
   Фейковые исполняемые CLI (`_fake_cli`) остаются реальными файлами — не моки (ADR-013).
   Кейсам, которым `monkeypatch` раньше не был нужен, добавить его в параметры.

**Acceptance:**
```bash
python3 -m pytest scripts/vps/tests/test_claude_runner_cli_resolution.py -q   # 13 passed
grep -n "ast.parse\|textwrap\|exec(" scripts/vps/tests/test_claude_runner_cli_resolution.py  # пусто
python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import runner_cli; print(runner_cli._MIN_CLI_VERSION, len(runner_cli.ALLOWED_TOOLS))"   # (2, 1, 190) 11
grep -n "claude_agent_sdk" scripts/vps/runner_cli.py   # пусто
```
EC-покрытие: **EC-1**.

---

### Task 5: `runner_refusal.py` + его тест  ⚠ требует расширения Allowed Files

**Type:** code + test
**Files:**
- Create: `scripts/vps/runner_refusal.py` *(вне текущего периметра)*
- Modify: `scripts/vps/claude-runner.py:248-349, 723-741, 795-815`
- Modify: `scripts/vps/tests/test_claude_runner_refusal.py` *(вне текущего периметра)*

**Context:** самый молодой и самый чувствительный код в файле — отказ классификатора
приходит внутри HTTP 200 и без него пустой security-отчёт читается как чистый.
Переезжает целиком, поведение не меняется ни на строку.

**Steps:**

1. `scripts/vps/runner_refusal.py`: строки 249-349 дословно (комментарий-преамбула,
   три константы, `_message_text`, `_refusal_from_message`, `_refusal_summary`),
   плюс два выноса из `run_task`:
```python
def warn(logger, refusal: dict) -> None:
    """Say out loud that a decline happened (text of claude-runner.py:725-735)."""
    if not refusal["detected"]:
        return
    logger.warning(...)


def log_telemetry(db, logger, refusal, *, project_id, task, skill, model, exit_code) -> None:
    """Its own table, never sdk_post_result_errors (claude-runner.py:795-815).

    `db` is passed in rather than imported so that the caller's patched
    `_orch_db` is what gets used — tests set it on the claude-runner module.
    """
    if not refusal["detected"] or db is None:
        return
    try:
        db.log_classifier_refusal(...)
    except Exception as log_exc:
        logger.warning("Failed to log classifier_refusal: %s", log_exc)
```

2. `claude-runner.py`: `import runner_refusal`; в цикле
   `refusal_event = runner_refusal._refusal_from_message(message)`;
   строки 723-741 становятся
```python
    refusal = runner_refusal._refusal_summary(state.refusal_events)
    runner_refusal.warn(logger, refusal)
    if refusal["unrecovered"] and exit_code == 0:
        # ADR-024 governs SDK exceptions raised AFTER a successful ResultMessage;
        # this is an in-stream observation. Only upgrade from 0.
        exit_code = 4
```
   **Строка `if refusal["unrecovered"] and exit_code == 0:` — дословно**, её ищет
   ассерт `test_claude_runner_refusal.py:475`.
   Строки 795-815 →
```python
    runner_refusal.log_telemetry(
        _orch_db, logger, refusal,
        project_id=ctx.project_name, task=task, skill=skill,
        model=MODEL, exit_code=exit_code,
    )
```
   `_orch_db` читается как глобаль `claude-runner.py` **в момент вызова** — значит
   `runner._orch_db = RecordingDB()` в тесте продолжает работать.

3. `test_claude_runner_refusal.py` — минимальная правка, тела кейсов не трогать:
   - добавить `import runner_refusal` рядом с `sys.path.insert` (строки 33-35);
   - `runner._refusal_from_message` → `runner_refusal._refusal_from_message` (10 мест);
   - `runner._refusal_summary` → `runner_refusal._refusal_summary` (6 мест);
   - `runner._REFUSAL_TEXT_LIMIT` / `runner._REFUSAL_EVENT_LIMIT` →
     `runner_refusal.…` (2 места);
   - `runner._EXIT_REASONS[4]`, `runner._orch_db`, `runner._salvage`, `runner.LOG_DIR`,
     `runner.query`, `runner.run_task` — **не трогать**, они остаются в `claude-runner.py`;
   - ассерты по тексту (466-476) — **не трогать**, оба маркера остаются в
     `claude-runner.py`.

**Acceptance:**
```bash
python3 -m pytest scripts/vps/tests/test_claude_runner_refusal.py -q   # все кейсы passed, ни одного deselect
grep -c "runner\._refusal" scripts/vps/tests/test_claude_runner_refusal.py   # 0
grep -n 'if refusal\["unrecovered"\] and exit_code == 0:' scripts/vps/claude-runner.py   # 1 совпадение
grep -n '4: "classifier_refusal"' scripts/vps/claude-runner.py                            # 1 совпадение
grep -n "claude_agent_sdk" scripts/vps/runner_refusal.py                                  # пусто
```
EC-покрытие: контракт exit 4 (Design §«Что обязано остаться»), поддерживает **EC-2**.

---

### Task 6: `runner_result.py`, часть A — чистый разбор

**Type:** code + test
**Files:**
- Create: `scripts/vps/runner_result.py`
- Modify: `scripts/vps/claude-runner.py:227-247, 351-428`
- Modify: `scripts/vps/tests/test_claude_runner_session_totals.py`

**Steps:**

1. `scripts/vps/runner_result.py`: `_TASK_STATUS_RE` + `_extract_task_status` (228-246),
   `_EXPECTED_MODELS` (352-364), `_usage_field` (367-375), `_session_totals` (378-428) —
   дословно. Импорты: `os`, `re`. SDK не импортировать.

2. `claude-runner.py`: `import runner_result`; вызовы →
   `runner_result._extract_task_status(...)`, `runner_result._session_totals(...)`.

3. `test_claude_runner_session_totals.py`: удалить строки 20-53 (`ast`/`exec`/
   `types.SimpleNamespace`), заменить на:
```python
import sys
from pathlib import Path

VPS_DIR = Path(__file__).resolve().parent.parent
if str(VPS_DIR) not in sys.path:
    sys.path.insert(0, str(VPS_DIR))

import pytest  # noqa: E402
import runner_result  # noqa: E402

_EXPECTED = frozenset({"claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"})


@pytest.fixture(autouse=True)
def pinned_expected_models(monkeypatch):
    """Hermetic against AUTOPILOT_EXPECTED_MODELS in the ambient environment."""
    monkeypatch.setattr(runner_result, "_EXPECTED_MODELS", _EXPECTED)
```
   В кейсах `cr._session_totals` → `runner_result._session_totals`,
   `cr._EXPECTED_MODELS` → `_EXPECTED`. Все 9 кейсов сохраняются дословно.

**Acceptance:**
```bash
python3 -m pytest scripts/vps/tests/test_claude_runner_session_totals.py -q  # 9 passed
grep -n "ast.parse\|exec(\|types.SimpleNamespace" scripts/vps/tests/test_claude_runner_session_totals.py  # пусто
python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import runner_result; print(runner_result._extract_task_status('x \"task_status\": \"complete\" y'))"   # complete
```
EC-покрытие: подготовка к EC-6.

---

### Task 7: `runner_result.py`, часть B — состояние прогона и сборка лога

**Type:** code
**Files:**
- Modify: `scripts/vps/runner_result.py`
- Modify: `scripts/vps/claude-runner.py:546-564, 598-644, 692-706, 745-794, 816-827`

**Context:** это таска, которая делает арифметику ≤400 возможной: 12 локальных
переменных состояния, разбор `ResultMessage` и вся сборка `log_data` — 137 строк —
уезжают из тела `run_task`. Всё переносимое **duck-typed через `getattr`**, поэтому
`runner_result` по-прежнему не импортирует SDK, а `isinstance`-ветвление остаётся
в `claude-runner.py`, где живут импортированные типы.

**Steps:**

1. В `runner_result.py` добавить:
```python
@dataclass
class RunState:
    """Everything the SDK stream accumulates. Was 12 locals in run_task."""

    result_text: str = ""
    last_assistant_text: str = ""
    turns: int = 0
    cost_usd: float = 0.0
    turn_count: int = 0
    last_tool_name: str | None = None
    result_received: bool = False
    result_is_error: bool = False
    model_usage: dict = field(default_factory=dict)
    refusal_events: list = field(default_factory=list)
    usage_metrics: dict = field(default_factory=lambda: {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_1h_input_tokens": 0,
        "cache_creation_5m_input_tokens": 0,
    })


def absorb_assistant(state: RunState, message) -> None:
    """Assistant turn: bump the counter, remember the text and the last tool."""
    # тело — строки 600-608 claude-runner.py


def absorb_result(state: RunState, message) -> None:
    """ResultMessage: turns, cost, flat + nested usage, per-model breakdown."""
    # тело — строки 618-644 дословно, включая коммент про cache_creation nesting.
    # exit_code здесь НЕ трогается — is_error отдаётся через state.result_is_error.


def build_log_data(ctx, state, *, exit_code, skill, task, prompt,
                   cli_path, cli_version, model, effort, refusal, salvage_info,
                   logger) -> dict:
    """Cache rate + the run-log dict + session totals + the drift warning.

    Тело — строки 745-794 дословно, `usage_metrics[...]` → `state.usage_metrics[...]`.
    """


def log_completion(logger, log_data: dict) -> None:
    """Final `done project=… exit=…` line (строки 817-827)."""


def log_post_result_error(db, logger, *, project_id, task, state, error_msg, stderr_lines) -> None:
    """BUG-188 Layer 4 telemetry (строки 692-706).

    `db` is a parameter, not an import: the caller passes its own `_orch_db`,
    which the integration test patches on the claude-runner module.
    """
```

2. В `claude-runner.py`:
   - строки 546-564 → `state = runner_result.RunState()`;
   - в цикле:
```python
                if isinstance(message, AssistantMessage):
                    runner_result.absorb_assistant(state, message)

                if isinstance(message, TaskNotificationMessage):
                    summary = getattr(message, "summary", "")
                    if summary:
                        state.result_text = summary

                if isinstance(message, ResultMessage):
                    runner_result.absorb_result(state, message)
                    if state.result_is_error:
                        exit_code = 1
```
     `isinstance`-проверки и присвоение `exit_code = 1` остаются здесь — типы
     импортированы в этом модуле, а фейковый SDK тестов подменяется в `sys.modules`
     до загрузки именно `claude-runner.py`;
   - в BUG-188-ветке вместо 15 строк телеметрии:
```python
            runner_result.log_post_result_error(
                _orch_db, logger,
                project_id=project_name, task=task, state=state,
                error_msg=str(e)[:2000], stderr_lines=stderr_lines,
            )
```
     **между `result_received and not result_is_error` и `elif "timeout"` не должно
     появиться ни одного `exit_code =`** — это ассерт в двух тестовых файлах;
   - строки 745-794 → `log_data = runner_result.build_log_data(...)`;
   - строки 817-827 → `runner_result.log_completion(logger, log_data)`.

**Acceptance:**
```bash
python3 -m pytest scripts/vps/tests/ -q          # столько же passed, сколько в Task 1
grep -n "claude_agent_sdk" scripts/vps/runner_result.py     # пусто
wc -l scripts/vps/runner_result.py                          # ≤ 300
wc -l scripts/vps/claude-runner.py                          # ожидаемо ~400±20
python3 - <<'PY'
import ast, pathlib
src = pathlib.Path("scripts/vps/claude-runner.py").read_text()
i = src.index("result_received and not result_is_error")
j = src.index('elif "timeout"', i)
assert "exit_code =" not in src[i:j] and "exit_code=" not in src[i:j], "BUG-188 block reassigns exit_code"
print("ADR-024 block clean")
PY
```
EC-покрытие: **EC-2**.

---

### Task 8a: Разобрать `run_task`

**Type:** code
**Files:**
- Modify: `scripts/vps/claude-runner.py`

**Context:** после Task 7 файл под лимитом, но `run_task` всё ещё ~190 строк — то
есть причина, по которой лимит существует, никуда не делась. Разложить по таблице
из §Design «Разбор `run_task`».

**Steps:** ввести `_RunContext`, `_prepare_run`, `_build_options`, `_enrich_error`,
`_execute`, `_finalize`; `run_task` остаётся `async def run_task(project_dir, task,
skill) -> dict` с прежним именем и сигнатурой.

Жёсткие ограничения, каждое из которых проверяется ассертом:
- `query(...)` и `ClaudeAgentOptions(...)` вызываются **по голому имени** (их патчат
  `monkeypatch.setattr(claude_runner, …)`);
- `async with asyncio.timeout(TIMEOUT_SECONDS)` — внутри `_execute`; `asyncio.wait_for`
  не появляется нигде;
- `except TimeoutError:` с `exit_code = 124` — в `_execute`;
- цепочка `except` целиком в одном теле, литералы
  `result_received and not result_is_error` и `elif "timeout"` сохранены;
- словарь `env={...}` с `"CLAUDE_CURRENT_SPEC_PATH": os.environ.get("CLAUDE_CURRENT_SPEC_PATH", "")`
  остаётся внутри `_build_options`, то есть в `claude-runner.py`;
- `LOG_DIR` читается **в момент вызова** (`ctx.log_file = LOG_DIR / …` внутри
  `_prepare_run`), а не на уровне модуля — тесты подменяют `LOG_DIR` перед запуском.

**Резерв, если файл всё же >400:** перенести SIGTERM-хендлер из `main` (строки
848-864) в `runner_env.install_sigterm_handler(logger, on_term)`, оставив сам вызов
`_salvage_if_needed` в `claude-runner.py` замыканием. Даёт ещё ~14 строк. Других
резервов нет — всё остальное закреплено ассертами.

**Acceptance:**
```bash
wc -l scripts/vps/claude-runner.py            # ≤ 400
python3 - <<'PY'
import ast, pathlib
src = pathlib.Path("scripts/vps/claude-runner.py").read_text()
tree = ast.parse(src)
worst = max(
    ((n.name, n.end_lineno - n.lineno + 1) for n in ast.walk(tree)
     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
    key=lambda p: p[1],
)
print(worst)
assert worst[1] <= 80, worst
PY
grep -c "asyncio.wait_for" scripts/vps/claude-runner.py     # 0
grep -c "asyncio.timeout" scripts/vps/claude-runner.py      # ≥1
grep -n "TIMEOUT_SECONDS = 5400\|MAX_TURNS = 120" scripts/vps/claude-runner.py   # обе строки
python3 -m pytest scripts/vps/tests/ -q
```
EC-покрытие: **EC-3, EC-5, EC-6, EC-7, EC-8**.

---

### Task 8b: Перенацелить оставшиеся source-ассерты

**Type:** test
**Files:**
- Modify: `scripts/vps/tests/test_claude_runner_timeout.py`

**Context:** шесть ассертов читают текст `claude-runner.py`. Пять из них по-прежнему
про `claude-runner.py` и остаются как есть; шестой сравнивал позицию
`_write_heartbeat(` с позицией `isinstance(message, AssistantMessage)` и после
переезда сравнивал бы вызов в одном модуле с проверкой в другом — то есть проходил бы
случайно.

| Текущая строка | Ассерт | Что делать |
|---|---|---|
| 41 | нет `asyncio.wait_for` | оставить, файл тот же |
| 47 | есть `asyncio.timeout` | оставить |
| 52-70 | AST: `except TimeoutError` → `exit_code = 124` | оставить |
| 77 | `result_received and not result_is_error` присутствует | оставить |
| 82-90 | в BUG-188-блоке нет `exit_code =` | оставить |
| 185-192 | heartbeat вызывается **до** ветки `AssistantMessage` | переписать: сравнивать индекс `runner_heartbeat._write_heartbeat(` с индексом `isinstance(message, AssistantMessage)` **в том же файле** `claude-runner.py`, с сообщением про TECH-198 Layer A |

Класс `TestVariantCNeverIntroduced` (198-222) читает `callback.py` — **не трогать**.

**Acceptance:**
```bash
python3 -m pytest scripts/vps/tests/test_claude_runner_timeout.py -q   # столько же passed, сколько в Task 1
grep -n "heartbeat" scripts/vps/tests/test_claude_runner_timeout.py    # ссылки только на claude-runner.py и runner_heartbeat
```
EC-покрытие: **EC-3, EC-8**.

---

### Task 9: Финальная сверка

**Type:** test
**Files:** ничего не изменяется

**Steps:**
```bash
cd /home/dld/projects/dld/.worktrees/TECH-213
python3 -m py_compile scripts/vps/claude-runner.py                                    # AV-S1
python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import runner_env, runner_cli, runner_heartbeat, runner_refusal, runner_result"   # AV-S2
wc -l scripts/vps/claude-runner.py scripts/vps/runner_*.py                            # EC-6
grep -rn "^from runner_" scripts/vps/*.py                                             # EC-9 → пусто
grep -rn "^_[a-z_]* = runner_" scripts/vps/claude-runner.py                           # алиасов нет → пусто
python3 -m pytest scripts/vps/tests/ -q                                               # AV-F2
python3 -m pytest tests/ -q                                                           # корневой набор
ruff check scripts/vps/ && ruff format --check scripts/vps/
```

**Acceptance:**
- `claude-runner.py` ≤ 400; каждый `runner_*.py` ≤ 400 (и ни один > 300, кроме
  осознанно допущенного `runner_result.py` ≈ 290)
- количество passed в `scripts/vps/tests/` **не меньше** зафиксированного в Task 1
- `grep "^from runner_"` пуст (EC-9)
- EC-10 / EC-11 (живой прогон и reaper) выполняются оператором на VPS после merge —
  локально невоспроизводимы, отмечены в DoD как AV-F3

---

### Execution Order

```
1 (baseline)
└─ 2 (runner_env)
   └─ 3 (runner_heartbeat + 2 теста)
      └─ 4 (runner_cli + тест)
         └─ 5 (runner_refusal + тест)   ⚠ ждёт расширения Allowed Files
            └─ 6 (runner_result A + тест)
               └─ 7 (runner_result B — состояние и лог)   ← зависит от 6
                  └─ 8a (разбор run_task)   ← зависит от 7: без него >400 недостижимо
                     └─ 8b (source-ассерты) ← зависит от 8a: ассерт про heartbeat
                                              проверяет форму цикла после разбора
                        └─ 9 (сверка)
```

Порядок не произвольный:
- 2 → 3 → 4 идут от наименее связанного к наиболее — если что-то ломается, ломается
  на маленьком разрезе;
- 5 перед 6/7, потому что `absorb_*` из Task 7 живёт в том же цикле, где вызывается
  детект refusal: сначала стабилизировать вызов, потом двигать соседей;
- 8a **обязан** идти после 7 — до него файл ~490 LOC, и «разбор ради ≤400» без
  выноса состояния не сходится;
- 9 последней, потому что только она видит все пять модулей сразу.

**Соответствие TDD-порядку спеки:** EC-4 закрывается на Task 3, EC-2 — на Task 5/7
(характеризация опасного кода до разбора `run_task`), EC-1 — на Task 4, форма
(EC-5..EC-9) — на 8a/8b/9. Инверсия против буквы спеки одна: EC-4 идёт первым, а не
EC-2, потому что heartbeat — наименее связанный разрез и даёт дешёвый зелёный сигнал
перед тем, как трогать exit-код.

---

## Drift Log

**Итог: light drift, исправлено на месте.** Эскалация в `/council` не требуется —
ни один файл не удалён, ни одна API не сломана; сместились числа и появился один
новый файл.

| # | Что спека утверждала | Что на develop 2026-08-07 | Действие |
|---|---|---|---|
| D-1 | `claude-runner.py` = 717 LOC | **875 LOC** | §Why и §Context переписаны |
| D-2 | `run_task` = 310 строк, 363-673 | **363 строки, 467-829** | §Why, §Context, §Design обновлены |
| D-3 | Карта ответственностей: 7 групп, диапазоны 28-717 | 15 групп, диапазоны 1-875; группы `refusal` (249-349) не существовало вовсе | таблица заменена целиком |
| D-4 | source-ассерты в `test_claude_runner_timeout.py:40,45,50,73,78,175` | **41,47,52,77,82,185** (сдвиг от `5a8bff42`, lint/format sweep) | §Context и Task 8b используют новые номера |
| D-5 | четыре тестовых файла затронуто | **пять** (+ `test_claude_runner_refusal.py`, 533 LOC, создан `90086204`) | Impact Tree Step 1 переписан; см. §Blocker |
| D-6 | «все найденные файлы в Allowed Files» ✓ | **ложно**: не хватает `runner_refusal.py` и `test_claude_runner_refusal.py` | §Blocker, статус `blocked` до правки оператором |
| D-7 | четырёх модулей достаточно для ≤400 | арифметически нет: 875−342+6 = 539 | §Design «Раскол» пересчитан, добавлен пятый модуль + вынос состояния в Task 7 |
| D-8 | (не упоминалось) | `test_autopilot_scope_guard.py:113-122` читает текст `claude-runner.py` и требует `CLAUDE_CURRENT_SPEC_PATH` | зафиксировано как контракт: `env={...}` не переезжает |
| D-9 | (не упоминалось) | `tests/integration/test_claude_runner_post_result_exception.py` патчит `ClaudeAgentOptions`, `LOG_DIR`, `query`, `_orch_db` на модуле | зафиксировано в §Design «Что обязано остаться» |
| D-10 | `dependencies.md`: `run-agent.sh:47` | фактически **:64** | предсуществующий дрейф документации, вне периметра этой задачи — зафиксирован, не правится |

**Sync zones:** нет. `scripts/vps/` не имеет двойника в `template/` — зеркалится
только `.claude/`, а `template/scripts/` содержит агентские гейты (`pre-review-check.py`
и др.), но не оркестратор. Sync-таска не нужна.

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Вспомогательные группы импортируемы | Tasks 2, 3, 4, 5, 6 | ✓ |
| 2 | Тесты не парсят AST | Tasks 3, 4, 6 | ✓ |
| 3 | Детект refusal живёт в собственном модуле, exit 4 цел | Task 5 | ✓ |
| 4 | `run_task` читается по частям | Tasks 7, 8a | ✓ |
| 5 | `claude-runner.py` под 400 | Tasks 7 + 8a | ✓ |
| 6 | Регрессионные сторожа живы и целятся в правильный файл | Task 8b | ✓ |
| 7 | Ни один существующий кейс не потерян | Task 1 (baseline) + Task 9 | ✓ |
| 8 | `run-agent.sh` не правится | — | имя файла сохранено |
| 9 | `test_autopilot_scope_guard` и интеграционные тесты не правятся | Task 8a (контракт `env={...}` и глобалов) | ✓ |

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
| EC-12 | Контракт exit 4 цел | `stop_reason: "refusal"` без fallback | `exit_code=4`, `refusal.unrecovered=1`; при `ProcessError` код остаётся 3 | deterministic | `90086204`, ADR-029 | P0 |
| EC-13 | Refusal-телеметрия не мигрирует в чужую таблицу | прогон с отказом | вызван `log_classifier_refusal`, **не** `log_sdk_post_result_error` | deterministic | `90086204` | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-10 | Реальный вызов из `run-agent.sh` | дословная строка 64 с тестовой задачей | процесс стартует, пишет heartbeat, exit 0 | integration | devil SA-7 | P0 |
| EC-11 | Reaper читает свежий heartbeat | запущенный runner + `heartbeat_reaper.py` | живая сессия не убита | integration | TECH-198 | P0 |

### Coverage Summary
Deterministic: 11 | Integration: 2 | LLM-Judge: 0 | Total: 13 (min 3 ✓)

EC-12 и EC-13 уже покрыты существующими кейсами в `test_claude_runner_refusal.py`
(`test_unrecovered_refusal_fails_the_run`, `test_refusal_does_not_mask_a_more_specific_exit_code`,
`test_refusal_is_written_to_its_own_table`). Новых тестов писать не нужно — нужно, чтобы
они пережили переезд.

### TDD Order
1. EC-4 — heartbeat, наименее связанный разрез (Task 3)
2. EC-1 — переезд `_resolve_cli_path` (Task 4)
3. EC-2, EC-12, EC-13 — характеризация самого опасного кода до разбора `run_task` (Tasks 5, 7)
4. EC-3, EC-5..EC-9 — форма (Tasks 8a, 8b, 9)
5. EC-10, EC-11 — интеграция на VPS после merge

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
- [ ] `claude-runner.py` ≤ 400 LOC, **пять** новых модулей ≤ 400 каждый
- [ ] Ни одна функция не длиннее 80 строк
- [ ] Имя `claude-runner.py` не изменилось

### Tests
- [ ] EC-1..EC-13 проходят
- [ ] AST/`exec`-загрузка заменена импортом там, где функция переехала
- [ ] Ни один существующий кейс не потерян при переписывании (сверка с baseline Task 1)
- [ ] `test_autopilot_scope_guard.py` и оба интеграционных теста **не правились**

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2 локально
- [ ] AV-F3 на VPS — живой прогон, не только импорт

### Technical
- [ ] `TIMEOUT_SECONDS` и `MAX_TURNS` не изменены
- [ ] Формат heartbeat-файла не изменён
- [ ] ADR-024 соблюдён
- [ ] Контракт exit 4 (`classifier_refusal`) цел: апгрейд только с 0
- [ ] Ни одного `from runner_*` и ни одного алиаса `_x = runner_y._x` в `scripts/vps/*.py`
- [ ] `LOG_DIR`, `query`, `ClaudeAgentOptions`, `_orch_db`, `_salvage`, `_EXIT_REASONS`,
      `run_task` остались глобалами `claude-runner.py`

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
