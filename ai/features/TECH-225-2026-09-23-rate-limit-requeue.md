# Feature: [TECH-225] Упор в лимит подписки распознаётся, и спека возвращается в очередь, а не в blocked

**Priority:** P1 | **Date:** 2026-09-23 | **Risk:** R1 (новый путь записи статуса в callback) | **AFTER TECH-223, AFTER TECH-224**
**Size:** 6 tasks / 15 files — индивидуально неделимо: детектор без реакции callback оставляет спеки в
`blocked` (сегодняшний вред), реакция без детектора не имеет входа. Пауза флота вынесена в TECH-226.

> **Почему AFTER:** с TECH-224 общий `scripts/vps/callback.py` (371/400, Step 7), с TECH-223 —
> `scripts/vps/runner_loop.py` и `scripts/vps/claude-runner.py` (368/400). Параллельный запуск
> даёт конфликт мержа и пробитый потолок файла. Ребро TECH-223 объявлено в шапке (lifecycle
> `depends_on` содержит только TECH-224 — диспетчер читает объединение, `spec_deps.declared`).

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

23.09 в 10:31Z флот упёрся в пятичасовой лимит подписки Max. Транскрипт сессии
(`~/.claude/projects/-home-dld-projects-awardybot/4f526d54-….jsonl`, хвост):

```
"model":"<synthetic>", "content":[{"type":"text","text":"You've hit your session limit · resets 2pm (Europe/Helsinki)"}],
"quotaLimits":{"status":"rejected","resetsAt":1790161200,"rateLimitType":"five_hour",
               "overageStatus":"rejected","overageDisabledReason":"org_level_disabled"},
"error":"rate_limit","isApiErrorMessage":true,"apiErrorStatus":429
```

А раннер записал в run-лог `exit_code: 1`, `result_preview: "Command failed with exit code 1 …
Check stderr output for details"`, stderr пуст (`awardybot-20260923-124922`, `dowry-20260923-130727`).
Callback увёл обе спеки в `blocked` (`branch_pushed_not_merged:2 ahead`: TECH-1535 awardybot,
TECH-526 dowry). Причину нашли только чтением транскрипта в интерактивном окне.

Решение основателя (Phase 1): **реактивно** — распознать, вернуть спеку в очередь, остановить
диспатч до сброса, один алерт. Проактивного троттлинга нет. Пауза и алерт — TECH-226; эта спека —
распознавание и возврат в очередь.

## Context

- Разбор суток: `C:\Users\Oleg\.claude\task-journal\2026-09-23-dld-orch24h.md`.
- SDK в боевом venv — `claude_agent_sdk 0.1.63` (`scripts/vps/run-agent.sh:73` → `venv/bin/python3`;
  `requirements.txt: claude-agent-sdk>=0.1.63,<0.2.0`). В нём уже есть всё нужное
  (`ai/.spark/20260923-TECH-223/probe-results.md` P5):
  - `AssistantMessage.error: Literal["authentication_failed","billing_error","rate_limit",…] | None` (`types.py:896-928`);
  - `RateLimitEvent(rate_limit_info=RateLimitInfo(status, resets_at, rate_limit_type, utilization, overage_status, …))`,
    `status ∈ allowed | allowed_warning | rejected` (`types.py:1044-1078`, парсер `message_parser.py:233-252`).
  - `ResultMessage.api_error_status` в 0.1.63 **нет** (есть с 0.1.81) — не опираться.
- Образец модуля: `scripts/vps/runner_refusal.py` (duck-typed, stdlib-only, своё решение об exit 4).
- Прецедент «вернуть в queued»: `lifecycle.reconcile_orphans` (`lifecycle.py:331-350`,
  `write_lifecycle(…, "queued", reason="orphaned from crash", by="orchestrator")`).
- Соседние спеки: TECH-223, TECH-224, **TECH-226 (AFTER TECH-225)** — пауза флота до `resets_at`
  и один алерт; ставит паузу по сводке `runner_ratelimit.summary(...)`, которую вводит эта спека.

---

## Scope

**In scope:**
1. `runner_ratelimit.py` (NEW): детектор по двум структурным сигналам — `AssistantMessage.error ==
   "rate_limit"` и `RateLimitEvent.rate_limit_info.status == "rejected"`; сводка для run-лога.
2. Новый exit-код **5 = `rate_limited`**: ставится, когда был отказ по лимиту и прогон не получил
   успешного результата (ADR-024: `result_received and not result_is_error` → остаётся 0).
   Перекрывает 1/2/3; не трогает 124, 4, 143.
3. Run-лог всегда содержит блок `rate_limit` (`{"detected": false}` без событий) — отсутствие
   ключа = старый раннер, как у `refusal`.
4. Callback: autopilot с exit 5 → спека `in_progress → queued`, `by="callback"`,
   `reason="rate_limited"` (тип окна и `resets_at` — в блоке `rate_limit` run-лога, callback их не
   перечитывает), решение пишется в `callback_decisions`
   с `verdict='requeue'` (`demoted=0` — в счётчик circuit breaker не попадает, по имени, а не случайно).
5. Потолок: третий возврат одной спеки по лимиту за 24 часа → `blocked` с причиной
   `repeated_rate_limit:<n>` через тот же путь, что и обычный demote (`note_demote` учитывает его).
6. `salvage` на exit 5 — как на любом ненулевом: ветка пушится, повторный запуск продолжает её
   (TECH-221, `git ls-remote --heads origin <type>/<ID>`).

**Out of scope:**
- Пауза диспатча до `resets_at`, пропуск прогонов во время паузы, один алерт — **TECH-226**.
- Проактивное торможение по `utilization` / `allowed_warning` (данные пишутся в лог, решений нет).
- QA / reflect / dispatcher с exit 5: у них нет lifecycle-записи, только run-лог (пауза — TECH-226).
- Разбор транскриптов `~/.claude/projects/*.jsonl` — не нужен, SDK отдаёт то же структурно.

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `grep -rn "_EXIT_REASONS" scripts/vps` → `runner_result.py:27-33` (определение), `claude-runner.py:50,167` (salvage reason).
- `grep -rn "refusal_events" scripts/vps` → `runner_loop.py:187-189`, `claude-runner.py:273` — образец сбора событий в `state`.
- `grep -rn "record_decision\|count_demotes_since" scripts/vps` → `db_decisions.py`, `db.py` delegate (`db.py:335-358`), `callback_circuit.py:185,198`.
- `grep -rn "verify_status_sync(" scripts/vps/callback.py` → Step 7, `callback.py:354` (после TECH-224 — Step 7/7b).

### Step 2: DOWN
- `claude_agent_sdk` 0.1.63 типы — через duck typing (`getattr(message, "error", None)`, `getattr(message, "rate_limit_info", None)`), модуль SDK не импортирует (контракт `runner_refusal`).
- `lifecycle.write_lifecycle` (`lifecycle.py:97-138`) — Rule 7 (`done` терминален) ловится как в `callback_sync._write_status`.

### Step 3: BY TERM
- `grep -rn "exit_code.*5\b\|== 5" scripts/vps/*.py` → только `spec_operator.py` (свой CLI, другое пространство кодов) — код 5 свободен в раннере/callback.
- `grep -rn "'demote' | 'sync'" scripts/vps/schema.sql` → `schema.sql:80` — комментарий списка вердиктов, дописать `'requeue'`.

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/runner_loop.py` | 182-196 | `consume` собирает refusal-события | modify (+ rate-limit события) |
| `scripts/vps/claude-runner.py` | 273-320 | решение exit 4, run-лог | modify (exit 5, блок `rate_limit`) |
| `scripts/vps/runner_result.py` | 27-33 | `_EXIT_REASONS` | modify (+1 строка) |
| `scripts/vps/callback.py` | 332-362 | Step 7 | modify (ветка exit 5) |

### Step 4: CHECKLIST
- [x] `scripts/vps/tests/` — новый `test_runner_ratelimit.py` (детектор + решение exit-кода на поддельных сообщениях, как `test_claude_runner_refusal.py`)
- [x] `tests/integration/` — новый `test_callback_rate_limit_requeue.py` (реальный git, реальный lifecycle, `callback.main()` — харнес `test_callback_blocked_no_dispatch.py:158-190`)
- [x] `db/migrations/**` — N/A; `schema.sql` меняется только комментарием, таблица та же

### Verification
- [x] Все найденные файлы в Allowed Files
- [x] После спеки `grep -n "5: \"rate_limited\"" scripts/vps/runner_result.py` = 1

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/runner_ratelimit.py` — детектор, сводка, решение exit 5 (NEW)
- `scripts/vps/runner_loop.py` — consume собирает rate-limit события в state (modify, 281 LOC)
- `scripts/vps/claude-runner.py` — применить решение exit 5, блок rate_limit в run-лог (modify, 368 LOC)
- `scripts/vps/runner_result.py` — `_EXIT_REASONS[5] = "rate_limited"` (modify, 390 LOC — ровно 1 строка)
- `scripts/vps/callback_ratelimit.py` — возврат в queued, потолок 3/24ч, запись решения (NEW)
- `scripts/vps/callback.py` — Step 7: exit 5 у autopilot идёт в callback_ratelimit (modify, 371 LOC)
- `scripts/vps/db_decisions.py` — count_requeues_since(spec_id, hours) (modify, 169 LOC)
- `scripts/vps/db.py` — delegate count_requeues_since (modify, 376 LOC)
- `scripts/vps/schema.sql` — комментарий вердиктов: + 'requeue' (modify)
- `scripts/vps/tests/test_runner_ratelimit.py` — детектор и exit-код (NEW)
- `tests/integration/test_callback_rate_limit_requeue.py` — callback.main() с exit 5 (NEW)
- `.github/workflows/test.yml` — `--cov=callback_ratelimit` (modify)
- `ai/experiments/2026-09-23-rate-limit-requeue.md` — эксперимент (NEW)
- `docs/orchestrator/status-model.md` — путь «лимит → queued» и exit 5 (modify)
- `.claude/rules/dependencies.md` — runner_ratelimit, callback_ratelimit, exit 5 (modify)

**LOC headroom:** `runner_result.py` 390/400 — **только** одна строка в `_EXIT_REASONS`; всё
остальное — в новых модулях. `claude-runner.py` 368/400 (после TECH-223 ≈ 374) — правка ≤ 8 строк:
вызов `runner_ratelimit.decide(state, summary)` и присваивание `log_data["rate_limit"]`; логика в
модуле. `callback.py` — ветка в Step 7 ≤ 6 строк, логика в `callback_ratelimit.py`. `db.py` 376/400 —
одна строка delegate. Вышел за эти числа — перенести в новый модуль, не расти файл.

---

## Environment

nodejs: false
docker: false
database: true   # orchestrator SQLite через tmp_db

---

## Blueprint Reference

N/A — в DLD нет `ai/blueprint/system-blueprint/`. Домен: раннер и callback оркестратора.

---

## Historical Risks

<!-- lessons-binding v1 -->

none — `ai/lessons/` пуст. Прецеденты в коде: ADR-024 (не ломать успешный прогон пост-событием,
BUG-188 — $258/нед на ложных ретраях), `runner_refusal.py` (свой exit-код и телеметрия для отказа
внутри HTTP 200).

---

## Approaches

### Approach 1: структурные сигналы SDK (`AssistantMessage.error`, `RateLimitEvent`)
**Source:** research-web.md §2 ([PR #648](https://github.com/anthropics/claude-agent-sdk-python/pull/648)), probe-results.md P5, `types.py:896-1078` в venv VPS.
**Summary:** детектор смотрит поля сообщений, которые SDK 0.1.63 уже парсит.
**Pros:** не зависит от текста («session/weekly/usage limit»), не срабатывает, когда агент сам
пишет про лимиты (эта спека — пример); даёт `resets_at` и тип окна.
**Cons:** если CLI не пришлёт `rate_limit_event`, `resets_at` неизвестен → `unknown` (TECH-226 берёт запасной интервал).

### Approach 2: разбор транскрипта `~/.claude/projects/<slug>/<session>.jsonl`
**Cons:** раннер не знает путь сессии (research-codebase.md: нет plumbing `session_id`), формат
транскрипта не контракт; SDK отдаёт то же структурно.

### Approach 3: регэксп по тексту ассистента
**Cons:** ложные срабатывания на тексте самого агента; формат фразы менялся («Claude AI usage limit reached|…»).

### Selected: 1

---

## Design

### Как сейчас
- `runner_loop.consume` (`runner_loop.py:161-200`) смотрит на каждое сообщение `runner_refusal._refusal_from_message`
  и копит `state["refusal_events"]`; `RateLimitEvent` и `AssistantMessage.error` не читаются нигде
  (`grep -rn "rate_limit" scripts/vps/*.py` → 0).
- Исключение SDK после синтетического сообщения падает в общий путь `handle_sdk_exception`
  (`runner_loop.py:278-281`) → `exit_code = 1`.
- `claude-runner.py:273-290` — после прогона считает `_refusal_summary` и поднимает exit до 4.
- Callback Step 7 (`callback.py:333-360`): `status == "failed"` → `target="blocked"` → `verify_status_sync`.

### Как будет
```
runner_loop.consume:  ev = runner_ratelimit.from_message(message)
                      if ev: state.setdefault("rate_limit_events", []).append(ev)
claude-runner.py:     rl = runner_ratelimit.summary(state.get("rate_limit_events", []))
                      state["exit_code"] = runner_ratelimit.decide_exit(state, rl)   # 5 или без изменений
                      log_data["rate_limit"] = rl
callback.py Step 7:   if skill == "autopilot" and exit_code == 5:
                          verdict = callback_ratelimit.requeue(project_path, sid, pueue_id, project_id, preview)
                      else: (как раньше / TECH-224)
```

**`runner_ratelimit.from_message(message) -> dict | None`** (duck-typed):
- `getattr(message, "rate_limit_info", None)` есть → `{"source":"event","status","resets_at","rate_limit_type","utilization","overage_status"}` (любой статус — `allowed_warning` тоже пишется, для будущего замера);
- `getattr(message, "error", None) == "rate_limit"` → `{"source":"assistant_error","status":"rejected"}`.

**`summary(events)`** → `{"detected": bool, "rejected": bool, "rate_limit_type": str|None,
"resets_at": int|None, "resets_at_iso": str|None, "utilization_max": float|None, "sources": [...],
"events": [≤10]}`; `rejected` = был `status == "rejected"` из события **или** `assistant_error`;
`resets_at` — последний непустой из событий.

**`decide_exit(state, rl) -> int`:** `rl["rejected"]` и не `(state["result_received"] and not state["result_is_error"])`
и `state["exit_code"] in (0, 1, 2, 3)` → `5`; иначе текущий код. Логирует `RATE_LIMITED type=… resets_at=…`.

**`callback_ratelimit.requeue(...)`**:
1. Тип окна и `resets_at` callback не читает: они в блоке `rate_limit` run-лога, а паузу по ним
   ставит раннер (TECH-226). `callback_logs` не меняется — его разрешение лога
   (`extract_agent_output`, `callback_logs.py:153`) возвращает только `(skill, preview, task_status)`.
2. `n = db.count_requeues_since(spec_id, hours=24)`; `n >= 2` (этот — третий) → `blocked`, reason
   `repeated_rate_limit:<n+1>`, через `callback_circuit.note_demote` + `lifecycle.write_lifecycle(…, by="callback")`.
3. Иначе `lifecycle.write_lifecycle(project_path, spec_id, "queued", reason="rate_limited", by="callback", pueue_id=…)`
   и `callback_circuit._record(project_id, spec_id, "requeue", reason)` (`demoted=0`).
4. `LifecycleAlreadyDoneError` → NOOP (спека успела стать `done`), запись `noop`.
5. Лог `REQUEUE_RATE_LIMIT <spec> → queued (<reason>)` (строка для эксперимента).
6. Возвращает `(status, reason)` — формат вердикта TECH-224, чтобы событие Hermes сказало
   «autopilot queued: rate_limited…».

### Database Changes
Нет новых таблиц. `callback_decisions.verdict` получает значение `'requeue'` (колонка TEXT без
ограничения; `schema.sql:80` — только комментарий). `count_requeues_since` — `SELECT COUNT(*) FROM
callback_decisions WHERE spec_id=? AND verdict='requeue' AND reason='rate_limited' AND ts >= ?`
(причина в фильтре — чтобы возвраты с другой причиной, например `fleet_paused` из TECH-226, в потолок не шли) (параметризованно, ADR-017).

---

## Implementation Plan

### Research Sources
- [claude-agent-sdk-python PR #648 — RateLimitEvent](https://github.com/anthropics/claude-agent-sdk-python/pull/648)
- [Agent SDK reference — Python](https://code.claude.com/docs/en/agent-sdk/python) — `AssistantMessage.error`, `RateLimitEvent`
- `scripts/vps/runner_refusal.py` — образец модуля и тестов (`scripts/vps/tests/test_claude_runner_refusal.py`)

### Task 1: runner_ratelimit.py + тесты
**Type:** code
**Files:**
  - create: `scripts/vps/runner_ratelimit.py`
  - create: `scripts/vps/tests/test_runner_ratelimit.py`
**Acceptance:** EC-1..EC-5.

### Task 2: раннер собирает события и ставит exit 5
**Type:** code
**Files:**
  - modify: `scripts/vps/runner_loop.py` — сбор в `consume`
  - modify: `scripts/vps/claude-runner.py` — `decide_exit`, `log_data["rate_limit"]`
  - modify: `scripts/vps/runner_result.py` — `_EXIT_REASONS[5] = "rate_limited"`
  - modify: `scripts/vps/tests/test_runner_ratelimit.py` — EC-6, EC-7 (прогон через `run_task` с поддельным SDK, как в `test_claude_runner_refusal.py`)
**Acceptance:** EC-6, EC-7; `bash scripts/check-loc-limit.sh` exit 0.

### Task 3: счётчик возвратов в БД
**Type:** code
**Files:**
  - modify: `scripts/vps/db_decisions.py`, `scripts/vps/db.py`, `scripts/vps/schema.sql`
**Acceptance:** EC-10.

### Task 4: callback возвращает спеку в очередь
**Type:** code
**Files:**
  - create: `scripts/vps/callback_ratelimit.py`
  - modify: `scripts/vps/callback.py`
  - create: `tests/integration/test_callback_rate_limit_requeue.py`
  - modify: `.github/workflows/test.yml` — `--cov=callback_ratelimit`
**Acceptance:** EC-8, EC-9, EC-11.

### Task 5: эксперимент
**Type:** code (docs)
**Files:**
  - create: `ai/experiments/2026-09-23-rate-limit-requeue.md` — id: следующий свободный EXP; metric: autopilot-прогоны, упёршиеся в лимит (`grep -l '"exit_code": 5' scripts/vps/logs/*.log` с даты выкатки), и чем кончилась их спека (`grep REQUEUE_RATE_LIMIT scripts/vps/callback-debug.log` против `STATUS_SYNC … blocked` для тех же спек); baseline: 23.09 — 2 прогона упёрлись, 2 из 2 → `blocked` (exit 1, причина нигде не записана); expected: 100% упёршихся → `queued` с причиной `rate_limited`, 0 спек в `blocked` из-за лимита, кроме `repeated_rate_limit`; check_after_runs 40; check_after_date +21 день (событие редкое — если за срок лимит не случился, вердикт `inconclusive` с этой формулировкой). Тело: что делать, если `rate_limit_event` не приходит (детектор работает только по `assistant_error`, `resets_at` всегда unknown → TECH-226 живёт на запасном интервале; поднять SDK до версии с `api_error_status`).
**Acceptance:** `python scripts/check-experiments.py` exit 0.

### Task 6: доки
**Type:** code (docs)
**Files:**
  - modify: `docs/orchestrator/status-model.md` — exit 5, путь `in_progress → queued (rate_limited)`, потолок 3/24ч
  - modify: `.claude/rules/dependencies.md` — таблица модулей claude-runner (`runner_ratelimit.py`), модули callback (`callback_ratelimit.py`), `db_decisions.count_requeues_since`
**Acceptance:** доки называют exit 5 и новый путь.

### Execution Order
1 → 2 → 3 → 4 → 5 → 6

---

## Flow Coverage Matrix (REQUIRED)

| # | Шаг | Covered by Task | Status |
|---|-----|-----------------|--------|
| 1 | CLI получает 429 «session limit», шлёт синтетическое сообщение с `error: rate_limit` (+ `rate_limit_event`) | - | existing |
| 2 | Раннер распознаёт и ставит exit 5, пишет `rate_limit` в run-лог | Task 1, 2 | ✓ |
| 3 | Salvage пушит ветку | - | existing |
| 4 | Callback возвращает спеку в `queued`, решение `requeue` в БД | Task 3, 4 | ✓ |
| 5 | Третий возврат за сутки → `blocked repeated_rate_limit` | Task 3, 4 | ✓ |
| 6 | Hermes получает «autopilot queued: rate_limited…» (формат TECH-224) | Task 4 | ✓ |
| 7 | Повторный запуск продолжает запушенную ветку | - | existing (TECH-221) |
| 8 | Пауза флота до `resets_at`, один алерт | - | TECH-226 |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Синтетическое сообщение | объект с `error="rate_limit"`, `model="<synthetic>"` | `from_message` → `{"source":"assistant_error","status":"rejected"}` | deterministic | транскрипт 23.09 | P0 |
| EC-2 | Событие лимита | объект с `rate_limit_info(status="rejected", resets_at=1790161200, rate_limit_type="five_hour")` | `summary(...)["rejected"] is True`, `resets_at == 1790161200`, `resets_at_iso` = `2026-09-23T11:00:00+00:00` | deterministic | SDK types.py | P0 |
| EC-3 | Агент пишет про лимиты | `AssistantMessage` с текстом «You've hit your session limit», `error=None` | `from_message` → `None` | deterministic | devil (ложные срабатывания) | P0 |
| EC-4 | Предупреждение, не отказ | `rate_limit_info(status="allowed_warning", utilization=0.91)` | `detected=True`, `rejected=False`, `utilization_max=0.91` | deterministic | — | P1 |
| EC-5 | Пусто | `summary([])` | `{"detected": False, ...}`, ключ присутствует всегда | deterministic | контракт `refusal` | P1 |
| EC-6 | Отказ + исключение SDK | поддельный поток: синтетическое сообщение `error="rate_limit"`, затем исключение «Command failed with exit code 1» | итоговый `exit_code == 5`, run-лог `rate_limit.rejected == True`, salvage reason `rate_limited` | deterministic | incident 23.09 | P0 |
| EC-7 | ADR-024 | успешный `ResultMessage(is_error=False)`, затем `rate_limit_event(rejected)` | `exit_code == 0` | deterministic | ADR-024 / BUG-188 | P0 |
| EC-8 | Возврат в очередь | реальный репо, спека `in_progress`, callback `exit_code=5` | lifecycle `queued`, `by: callback`, причина `rate_limited`; строка `callback_decisions` `verdict='requeue'`, `demoted=0`; `count_demotes_since` не вырос | integration | devil Argument 3 | P0 |
| EC-9 | Потолок | две строки `requeue` для спеки за 24 ч, третий exit 5 | lifecycle `blocked`, причина `repeated_rate_limit:3`, `demoted=1` | integration | devil EC-7 | P0 |
| EC-10 | Счётчик | 2 строки `requeue` за 24 ч, 1 старше 24 ч, 1 другой спеки | `count_requeues_since(spec, 24) == 2` | deterministic | — | P1 |
| EC-11 | Уже done | спека стала `done` до callback | NOOP, lifecycle `done`, `main` exit 0 | integration | Rule 7 / ADR-025 | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 3 | LLM-Judge: 0 | Total: 11

### TDD Order
1. EC-1..EC-5 → Task 1
2. EC-6, EC-7 → Task 2
3. EC-10 → Task 3
4. EC-8, EC-9, EC-11 → Task 4

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Модули грузятся в боевом venv (SDK 0.1.63) | `cd ~/projects/dld/scripts/vps && venv/bin/python3 -c "import runner_ratelimit, callback_ratelimit, callback; print('ok')"` | `ok` | 30s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Детектор на настоящих типах SDK 0.1.63 | боевой venv | `venv/bin/python3 -c "from claude_agent_sdk import RateLimitEvent, RateLimitInfo, AssistantMessage; import runner_ratelimit as r; m=AssistantMessage(content=[], model='<synthetic>', error='rate_limit'); e=RateLimitEvent(rate_limit_info=RateLimitInfo(status='rejected', resets_at=1790161200, rate_limit_type='five_hour'), uuid='u', session_id='s'); print(r.summary([r.from_message(m), r.from_message(e)]))"` | `rejected: True`, `resets_at: 1790161200` |
| AV-F2 | Первый боевой упор в лимит | ближайший 429 | run-лог и lifecycle спеки | `exit_code 5`, блок `rate_limit`, спека `queued`, не `blocked` |

### Verify Command (copy-paste ready)

```bash
pip install -r scripts/vps/requirements.txt
pytest scripts/vps/tests/test_runner_ratelimit.py tests/integration/test_callback_rate_limit_requeue.py -v
pytest tests/ scripts/vps/tests/ -q
bash scripts/check-loc-limit.sh
ruff check . && ruff format --check .
python scripts/check-experiments.py
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Упор в лимит → exit 5 с причиной в run-логе, спека `queued`
- [ ] Третий упор одной спеки за сутки → `blocked repeated_rate_limit`
- [ ] Успешный прогон не ломается событием лимита после результата (ADR-024)
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] EC-1..EC-11 pass
- [ ] `pytest tests/ scripts/vps/tests/ -q` зелёные (с `scripts/vps/requirements.txt`)

### Acceptance Verification
- [ ] AV-S1, AV-F1 pass; AV-F2 — при первом боевом упоре (Autopilot Log / вердикт эксперимента)

### Technical
- [ ] ruff 0.16.1; LOC-гейт (`runner_result.py` ≤ 400 — одна строка), check-experiments exit 0
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
