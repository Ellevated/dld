# Feature: [TECH-223] Headless-прогон не заканчивает ход ожиданием фоновой работы

**Priority:** P1 | **Date:** 2026-09-23 | **Risk:** R1 (конфиг раннера — каждый прогон флота; промпты в двух деревьях)
**Size:** 5 tasks / 11 files — индивидуально мелкие правки; делимое по смыслу разделено на TECH-224..226.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

С 23.09 прогоны оркестратора идут с системным промптом Claude Code (`runner_loop.py:106-108`,
EXP-009). Этот промпт учит модель запускать долгое в фоне и ждать уведомления. В headless-прогоне
уведомлять некого: ход закончен — сессия закончена. CLI 2.1.280 в print-режиме ждёт фоновых
субагентов не дольше 600 с, фоновый Bash убивает через ~5 с после финального результата.

Замер 23.09 (Opus 5.5, `~/projects/dld/scripts/vps/logs`, транскрипты `~/.claude/projects/*/`):

| Прогон | Как закончил ход | Цена |
|---|---|---|
| awardybot FTR-1515 #2 (автопилот) | два `Agent`-кодера задач 3 и 4 **в фоне** + `ScheduleWakeup(1800)` + «Coder'ы работают в фоне. Продолжу, как только придут результаты» → stderr `Background tasks still running after 600s; terminating.` | $14.16, 73 мин, спека в `blocked`, задачи 3–5 переделывал третий прогон |
| dowry QA BUG-520 | отчёт записал, потом `Bash run_in_background` с `until grep … dowry-ci.log` и «CI ещё крутит BUG-520, пришлю финальный отчёт» | вердикт CI в отчёт не попал |
| QA всего | 5 из 15 прогонов закончились на фоновом ожидании (FTR-1525, FTR-1526, BUG-515, BUG-520, FTR-434) | на Opus 5 было 2 из 48 (01–22.09) |

Проза уже запрещает это автопилоту (`.claude/skills/autopilot/SKILL.md:182-186`,
`safety-rules.md` «Ход не заканчивается ожиданием» — $58.80 и ~$115 прошлых потерь), и FTR-1515
всё равно ушёл в фон. У QA такого правила нет вовсе.

**Решение основателя (Phase 1, `ai/diary/corrections.md` 2026-09-23 During TECH-223):**
- речь о headless-прогонах вообще, а не о «ночных»;
- headless-прогон **никогда не ждёт CI** (пост-мерж CI идёт 60–150 мин) — ни синхронно, ни в фоне;
- автопилот на основных спеках и QA — разные случаи: у автопилота фон убивает сессию и теряет
  работу, у QA теряется хвост отчёта. Автопилот закрываем механикой, QA — правилом.
- потолки ожидания (`BASH_MAX_TIMEOUT_MS`, `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`) **не поднимаем**:
  долгий `./test ci` лечится в репо проекта, а не лимитами раннера.

## Context

- Разбор суток: `C:\Users\Oleg\.claude\task-journal\2026-09-23-dld-orch24h.md`; пробы CLI —
  `ai/.spark/20260923-TECH-223/probe-results.md`.
- Соседние спеки той же сессии: TECH-224 (Hermes по вердикту lifecycle), TECH-225 (распознать
  лимит подписки), TECH-226 (пауза флота до сброса лимита). Файлы с этой спекой не пересекаются.
- «CI», которого не ждём, — пост-мерж CI (локальные таймеры `~/.local/log/ci/*-ci.log`, GitHub
  Actions, выкатка на dev). Синхронный `./test ci` внутри автопилота (PHASE 3, TECH-206) — это
  ворота качества самой спеки, **эта спека его не трогает**.

---

## Scope

**In scope:**
1. Раннер для skill `autopilot` ставит `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`: фоновый Bash
   исчезает как параметр, `Agent` с `run_in_background` исполняется синхронно.
2. Раннер для **всех** headless-прогонов убирает инструменты ожидания/расписания через
   `disallowed_tools`: `ScheduleWakeup`, `Monitor`, `CronCreate`, `CronDelete`, `CronList`,
   `RemoteTrigger`. Ни одному headless-скиллу они не нужны: будить некому.
3. Рычаг отката в `.env`, как у EXP-009: `HEADLESS_BACKGROUND_TASKS=on` возвращает фон автопилоту.
4. Run-лог пишет, с какими ограничениями шёл прогон (`headless_guards`) — чтобы эксперимент резал
   по полю, а не по дате (урок EXP-009).
5. QA-скилл (оба дерева): правило «CI и выкатку не ждать — посмотреть один раз, записать, что
   увидел, закончить отчёт».
6. `safety-rules.md` автопилота (оба дерева): абзац о том, что запрет теперь механический, — чтобы
   модель не гадала, куда делся `run_in_background`.
7. Скрипт замера и файл эксперимента.

**Out of scope:**
- `./test ci` внутри автопилота (длительность 20–30 мин в awardybot — задача репо awardybot).
- Лимиты `BASH_*_TIMEOUT_MS` и `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` — не меняются.
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` для QA, spark и прочих скиллов: QA может законно держать
  dev-сервер в фоне (devil EC-8), spark в headless фанит скаутов в фоне по дизайну.
- Codex/gemini-раннеры.

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `grep -rn "build_options" scripts/vps tests` → вызывается только в `scripts/vps/claude-runner.py:211`;
  тесты — `scripts/vps/tests/test_runner_models.py:193` (`_options`).
- `grep -rn "ALLOWED_TOOLS" scripts/vps` → `runner_cli.py:119-131` (определение), `runner_loop.py:111`.

### Step 2: DOWN — what depends on?
- `claude_agent_sdk.ClaudeAgentOptions(disallowed_tools=…, env=…)` — поле `disallowed_tools` есть в
  установленном SDK (research-codebase.md, Verified References: docstring «removed from the model's
  context and cannot be used»). VPS: `claude_agent_sdk 0.1.63` (probe-results.md P5).
- CLI 2.1.280: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` в бинарнике
  (`function zl(){return xq().backgroundTasksDisabled||a.CLAUDE_CODE_DISABLE_BACKGROUND_TASKS}`).

### Step 3: BY TERM
- `grep -rn "run_in_background" .claude/skills/autopilot template/.claude/skills/autopilot` →
  `SKILL.md:182`, `safety-rules.md:41` (оба дерева) — проза, не меняется, дополняется.
- `grep -rn "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS\|disallowed_tools" scripts/ .claude/` → 0 (до спеки).

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/runner_loop.py` | 87-140 | `build_options` без `disallowed_tools`, env без флага фона | modify |
| `scripts/vps/runner_cli.py` | 119-131 | `ALLOWED_TOOLS` | modify (+ константа запрета) |
| `scripts/vps/claude-runner.py` | 211-220, 294-320 | вызов `build_options`, сборка run-лога | modify |
| `scripts/vps/tests/test_runner_models.py` | 191-241 | `_options`, `TestBuildOptions` | modify |

### Step 4: CHECKLIST
- [x] `tests/**` — `scripts/vps/tests/test_runner_models.py` (241/600 LOC)
- [x] `db/migrations/**` — N/A в DLD
- [x] `template/` — `skills/qa/SKILL.md`, `skills/autopilot/safety-rules.md`

### Verification
- [x] Все найденные файлы в Allowed Files
- [x] `grep "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS" scripts/vps/runner_loop.py` ≥ 1 после спеки

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/runner_loop.py` — build_options: env-флаг фона для autopilot, disallowed_tools (modify, 281 LOC)
- `scripts/vps/runner_cli.py` — константа HEADLESS_DISALLOWED_TOOLS и набор скиллов без фона (modify, 131 LOC)
- `scripts/vps/claude-runner.py` — передать skill в build_options, поле headless_guards в run-лог (modify, 368 LOC)
- `scripts/vps/tests/test_runner_models.py` — тесты build_options и run-лога (modify, 241 LOC)
- `scripts/metrics/bg_turn_endings.py` — замер «ход кончился фоновым ожиданием» по run-логам (NEW)
- `.claude/skills/qa/SKILL.md` — правило «CI и выкатку не ждать» (modify)
- `template/.claude/skills/qa/SKILL.md` — то же, зеркало (modify)
- `.claude/skills/autopilot/safety-rules.md` — абзац о механическом запрете (modify)
- `template/.claude/skills/autopilot/safety-rules.md` — то же, зеркало (modify)
- `ai/experiments/2026-09-23-headless-no-background-wait.md` — эксперимент (NEW)
- `.claude/rules/dependencies.md` — строка runner_loop в таблице claude-runner (modify)

**LOC headroom:** runner_loop 281/400, runner_cli 131/400, claude-runner 368/400 (+≤10 строк),
test_runner_models 241/600. `runner_result.py` (390/400) **не трогать** — поле `headless_guards`
дописывается в `log_data` в `claude-runner.py` после `build_log_data`, до `write_run_log`
(`claude-runner.py:294-320`).
**W003 (claude-runner.py, 31 строка запаса) — ответ:** правка здесь — один kwarg в вызове
`build_options` и одно присваивание `log_data["headless_guards"]` (≤ 6 строк); расчёт полей
делает `runner_cli`/`runner_loop`, не раннер. Если выходит больше 10 строк — логика уезжает в
`runner_loop.py` (119 строк запаса), а не растёт раннер.

---

## Environment

nodejs: true   # node test/scripts harness, check-prompt-integrity
docker: false
database: false

---

## Blueprint Reference

N/A — в DLD нет `ai/blueprint/system-blueprint/`. Домен: оркестратор VPS (`scripts/vps/`) + промпты.

---

## Historical Risks

<!-- lessons-binding v1 -->

none — `ai/lessons/` содержит только `.gitkeep`. Ближайший аналог в прозе:
`.claude/skills/autopilot/safety-rules.md` §«Ход не заканчивается ожиданием» (TECH-1450, BUG-1448
×2 — $58.80 за ночь 21.08) и `ai/diary/corrections.md` 2026-09-23 (During TECH-223).

---

## Approaches

### Approach 1: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` для автопилота + deny инструментов ожидания для всех + правило для QA
**Source:** [Subagents: foreground/background](https://code.claude.com/docs/en/subagents), [Tools reference](https://code.claude.com/docs/en/tools-reference), [Agent SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions) (research-web.md §1); живые пробы probe-results.md P2–P3.
**Summary:** Флаг закрывает оба пути, которыми автопилот уходил в фон (фоновый Bash — параметр
исчезает, фоновый `Agent` — исполняется синхронно). `ScheduleWakeup`/`Monitor` флаг **не**
закрывает (P2) — их снимает `disallowed_tools` (P3: `AVAILABLE=NONE`).
**Pros:** механика, а не проза; проверено на CLI 2.1.280 флота; рычаг отката в `.env`.
**Cons:** автопилот теряет фоновый параллелизм субагентов (он и так запрещён прозой).

### Approach 2: только scoped deny `Bash(run_in_background:true)` + `Monitor`
**Source:** [Configure permissions](https://code.claude.com/docs/en/permissions) (research-web.md Approach 2).
**Summary:** Точечно запретить параметр, не трогая субагентов.
**Pros:** уже.
**Cons:** не закрывает именно случай FTR-1515 — фоновые **субагенты** + `ScheduleWakeup`.
При `permission_mode="bypassPermissions"` (`runner_loop.py:112`) permission-правила вида
`Tool(param:value)` не проверены на VPS — непроверенная механика.

### Approach 3: поднять потолки ожидания
**Summary:** `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`, выше `BASH_MAX_TIMEOUT_MS`.
**Cons:** прямо отклонено основателем; ожидание CI 60–150 мин съедает 3-часовой бюджет прогона.

### Selected: 1
**Rationale:** единственный вариант, который механически закрывает реальный путь FTR-1515
(фоновые субагенты + будильник), проверен пробой на флотовом CLI, и соответствует решению
основателя «автопилот — механикой, QA — правилом».

---

## Design

### Как сейчас (с цитатами)
- `runner_loop.build_options` (`runner_loop.py:87-140`) собирает `ClaudeAgentOptions` без
  `disallowed_tools`; `permission_mode="bypassPermissions"` (`:112`) делает `allowed_tools`
  (`runner_cli.py:119-131`) неограничивающим — инструменты вне списка (`Monitor`, `ScheduleWakeup`,
  `Cron*`) модели доступны (probe P2: `ScheduleWakeup` сработал, `MON=yes`).
- `claude-runner.py:211-220` вызывает `build_options` без skill; skill известен раннеру (argv[3]).
- Run-лог: `runner_result.build_log_data` (`claude-runner.py:294`) → `write_run_log` (`:320`).

### Architecture
```
run-agent.sh → claude-runner.py (skill из argv)
   └─ runner_loop.build_options(..., skill=skill)
        ├─ disallowed_tools = runner_cli.HEADLESS_DISALLOWED_TOOLS      (все скиллы)
        └─ env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"
              если skill in runner_cli.NO_BACKGROUND_SKILLS ({"autopilot"})
              и os.environ.get("HEADLESS_BACKGROUND_TASKS") != "on"
   └─ log_data["headless_guards"] = {"background_tasks_disabled": bool,
                                      "disallowed_tools": [...]}
```
`skill` — keyword-аргумент со значением по умолчанию `None` (= не автопилот): существующие вызовы
и тесты `_options(...)` не ломаются.

### QA-правило (оба дерева, `skills/qa/SKILL.md`)
1. В `### NEVER DO` раздела HARD BOUNDARIES — пункт: не ждать CI и выкатку — ни `sleep`/`until`
   циклом, ни в фоне, ни фразой «пришлю итог, когда CI закончится». QA идёт headless: ход,
   закончившийся ожиданием, заканчивает сессию, и итог не придёт никогда.
2. В Step 0c строка `in_progress` → «записать `CI: in_progress <sha>` в отчёт и продолжать; не
   ждать». В Step 0b строка «Deployed SHA is behind» остаётся BLOCKED — тоже без ожидания.
Текст правила по-русски, коротко; формулировка одинакова в обоих деревьях.

### safety-rules.md автопилота (оба дерева)
Под §«Ход не заканчивается ожиданием» — абзац: в headless-прогонах раннер выключает фон
механически (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, без `ScheduleWakeup`/`Monitor`/`Cron*`):
`run_in_background` у Bash отсутствует, `Agent` возвращает результат синхронно. Долгая команда
выполняется в переднем плане в пределах таймаута Bash; не влезает — сузить набор, а не искать обход.

### Замер `scripts/metrics/bg_turn_endings.py`
stdlib, CLI как у `run_metrics.py` (`--log-dir`, `--since`, `--until`, `--skill`, `--json`).
По каждому run-логу `<project>-<ts>.log` (+ соседний `.stderr.txt`) считает на скилл:
- `runs` — всего;
- `bg_killed` — в stderr есть `Background tasks still running after`;
- `ended_on_wait` — первая строка `result_preview` похожа на команду/ожидание (регэксп по началу:
  `until |while |for |sleep |export |cd |uv run|python|\.venv/|bash |tail |grep |Wait until`)
  **или** содержит обещание вернуться (`пришлю|вернусь|I'll send|will report`).
Печатает таблицу и (с `--json`) JSON. Отчётный инструмент — всегда exit 0.

### Database Changes
Нет.

---

## Implementation Plan

### Research Sources
- [Subagents — foreground/background](https://code.claude.com/docs/en/subagents) — семантика `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`
- [Agent SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions) — `disallowed_tools` удаляет инструмент из контекста
- [Run Claude Code programmatically](https://code.claude.com/docs/en/headless) — фоновый Bash в `-p` убивается через ~5 с, субагенты ждутся до потолка
- `ai/.spark/20260923-TECH-223/probe-results.md` — пробы на CLI 2.1.280 флота

### Task 1: build_options — фон выключен для автопилота, инструменты ожидания сняты для всех
**Type:** code
**Files:**
  - modify: `scripts/vps/runner_cli.py` — `HEADLESS_DISALLOWED_TOOLS = ["ScheduleWakeup", "Monitor", "CronCreate", "CronDelete", "CronList", "RemoteTrigger"]`, `NO_BACKGROUND_SKILLS = frozenset({"autopilot"})`, комментарий с датой и FTR-1515
  - modify: `scripts/vps/runner_loop.py` — kwarg `skill=None`, `disallowed_tools=`, env-флаг по правилу из Design
  - modify: `scripts/vps/tests/test_runner_models.py` — EC-1..EC-4, EC-6
**Acceptance:** EC-1..EC-4 и EC-6 зелёные; `pytest scripts/vps/tests/test_runner_models.py -q`.

### Task 2: раннер передаёт skill и пишет headless_guards в run-лог
**Type:** code
**Files:**
  - modify: `scripts/vps/claude-runner.py` — `build_options(..., skill=skill)`; `log_data["headless_guards"] = {...}` между `build_log_data` и `write_run_log`
  - modify: `scripts/vps/tests/test_runner_models.py` — EC-5
**Acceptance:** EC-5; `wc -l scripts/vps/claude-runner.py` ≤ 400; `bash scripts/check-loc-limit.sh` exit 0.

### Task 3: правило для QA и абзац для автопилота, оба дерева
**Type:** code (prompt)
**Files:**
  - modify: `template/.claude/skills/qa/SKILL.md`, затем `.claude/skills/qa/SKILL.md`
  - modify: `template/.claude/skills/autopilot/safety-rules.md`, затем `.claude/skills/autopilot/safety-rules.md`
**Acceptance:** EC-8; `node .claude/scripts/check-prompt-integrity.mjs --tree .claude` и `--tree template/.claude` без новых находок; `python scripts/check-tree-sync.py` clean.

### Task 4: скрипт замера
**Type:** code
**Files:**
  - create: `scripts/metrics/bg_turn_endings.py`
**Acceptance:** EC-9 на VPS: `python3 scripts/metrics/bg_turn_endings.py --log-dir ~/projects/dld/scripts/vps/logs --since 2026-09-23 --until 2026-09-23`.

### Task 5: эксперимент + dependencies.md
**Type:** code (docs)
**Files:**
  - create: `ai/experiments/2026-09-23-headless-no-background-wait.md` — id: следующий свободный EXP (`grep -h "^id:" ai/experiments/*.md`); metric: `bg_killed` автопилота и `ended_on_wait` QA по `bg_turn_endings.py`, срез по полю `headless_guards` в run-логе; baseline — вывод Task 4 за 23.09 (ожидается автопилот `bg_killed` 1 из 25, QA `ended_on_wait` ≈5 из 16); expected: автопилот `bg_killed` = 0, QA `ended_on_wait` ≤ 1 из 15; command — Task 4 с `--since` даты выкатки; check_after_runs 15; check_after_date +14 дней. Тело: что делать, если QA не сдвинулся (механика для QA: флаг фона и для `qa`), и если автопилот стал упираться в таймаут Bash (сужать набор в репо проекта, не поднимать лимит).
  - modify: `.claude/rules/dependencies.md` — строка `runner_loop.py` в таблице claude-runner: `build_options` также ставит `disallowed_tools` и флаг фона для autopilot (TECH-223)
**Acceptance:** `python scripts/check-experiments.py` exit 0 (новый файл не «просрочен»); `python scripts/check-rules-loading.py .` ok.

### Execution Order
1 → 2 → 3 → 4 → 5

---

## Flow Coverage Matrix (REQUIRED)

| # | Шаг | Covered by Task | Status |
|---|-----|-----------------|--------|
| 1 | pueue → run-agent.sh → claude-runner.py с skill | - | existing |
| 2 | Раннер строит опции: запрет инструментов ожидания для всех | Task 1 | ✓ |
| 3 | Для autopilot фон выключен флагом (рычаг отката в .env) | Task 1 | ✓ |
| 4 | Run-лог фиксирует, с какими ограничениями шёл прогон | Task 2 | ✓ |
| 5 | QA видит правило «CI не ждать», автопилот — объяснение механики | Task 3 | ✓ |
| 6 | Замер до/после и вердикт | Task 4, 5 | ✓ |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Автопилот без фона | `build_options(..., skill="autopilot")`, `HEADLESS_BACKGROUND_TASKS` не задан | `opts.env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"` | deterministic | founder / probe P2 | P0 |
| EC-2 | QA сохраняет фон | `skill="qa"` | ключа `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` нет в `opts.env` | deterministic | devil EC-8 | P0 |
| EC-3 | Инструменты ожидания сняты у всех | `skill` ∈ {autopilot, qa, reflect, dispatcher, None} | `set(opts.disallowed_tools) ⊇ {"ScheduleWakeup","Monitor","CronCreate","CronDelete","CronList","RemoteTrigger"}` | deterministic | probe P3 | P0 |
| EC-4 | Рычаг отката | `HEADLESS_BACKGROUND_TASKS=on`, `skill="autopilot"` | флага в env нет, `disallowed_tools` по-прежнему выставлен | deterministic | EXP-009 precedent | P1 |
| EC-5 | Run-лог режется по полю | собранный run-лог автопилота | `log["headless_guards"] == {"background_tasks_disabled": True, "disallowed_tools": [...]}`; у QA — `False` | deterministic | lesson EXP-009 | P1 |
| EC-6 | Регрессия | существующие `TestBuildOptions` (preset, empty, pins) | зелёные без изменений ожиданий | deterministic | — | P0 |
| EC-7 | `skill=None` (прямые вызовы без skill) | `build_options(...)` без skill | флага фона нет, `disallowed_tools` выставлен | deterministic | devil (blast radius) | P1 |
| EC-8 | Два дерева | `diff` изменённых секций qa/SKILL.md и safety-rules.md root vs template | правило присутствует в обоих, текст правила идентичен | deterministic | template-sync.md | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-9 | VPS, логи 23.09 | `bg_turn_endings.py --since 2026-09-23 --until 2026-09-23` | autopilot `bg_killed` ≥ 1 (FTR-1515 #2, `awardybot-20260923-115025`), qa `ended_on_wait` ≥ 4 | integration | journal 23.09 | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 1 | LLM-Judge: 0 | Total: 9

### TDD Order
1. EC-1, EC-3, EC-7 → FAIL → Task 1 → PASS
2. EC-2, EC-4, EC-6 → Task 1
3. EC-5 → Task 2
4. EC-8 → Task 3; EC-9 → Task 4

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Раннер импортируется в боевом venv | `cd ~/projects/dld && scripts/vps/venv/bin/python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import runner_loop, runner_cli; print(runner_cli.HEADLESS_DISALLOWED_TOOLS)"` | список из 6 имён, exit 0 | 30s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Механика на флотовом CLI | VPS, CLI 2.1.280 | `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 claude -p "<проба P2>" --disallowedTools ScheduleWakeup Monitor CronCreate CronDelete CronList RemoteTrigger --model claude-sonnet-5` (текст пробы — probe-results.md P2) | Bash `run_in_background` → `InputValidationError`; `Agent` фоновый → синхронный hand-back; `ScheduleWakeup` недоступен |
| AV-F2 | Первый боевой прогон после выкатки | ближайший autopilot-прогон | `jq .headless_guards` его run-лога | `background_tasks_disabled: true`, 6 инструментов; `grep -c "Background tasks still running" <его .stderr.txt>` = 0 |

### Verify Command (copy-paste ready)

```bash
# Smoke / unit
pytest scripts/vps/tests/test_runner_models.py -q
bash scripts/check-loc-limit.sh
python scripts/check-tree-sync.py
node .claude/scripts/check-prompt-integrity.mjs --tree .claude
node .claude/scripts/check-prompt-integrity.mjs --tree template/.claude
python scripts/check-experiments.py
# Functional (VPS)
python3 scripts/metrics/bg_turn_endings.py --log-dir ~/projects/dld/scripts/vps/logs --since 2026-09-23 --until 2026-09-23
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Автопилот в headless не может уйти в фон; инструменты ожидания недоступны ни одному headless-скиллу
- [ ] QA-скилл в обоих деревьях запрещает ждать CI и выкатку
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] EC-1..EC-9 pass
- [ ] `pytest scripts/vps/tests/ -q` и `pytest tests/ -q` зелёные (с `pip install -r scripts/vps/requirements.txt`)

### Acceptance Verification
- [ ] AV-S1, AV-F1 pass; AV-F2 — после первого боевого прогона (записать в Autopilot Log)

### Technical
- [ ] `ruff check . && ruff format --check .` на ruff 0.16.1
- [ ] LOC-гейт, tree-sync, prompt-integrity, check-experiments — exit 0
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
