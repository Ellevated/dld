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
- Проверено на месте (2026-09-24), без веба: боевой venv `scripts/vps/venv` = `claude_agent_sdk-0.1.63`.
  `types.py:896-903` (`AssistantMessageError` содержит `"rate_limit"`), `:917-928` (`AssistantMessage.error`),
  `:1037-1081` (`RateLimitInfo(status, resets_at, rate_limit_type, utilization, overage_status, overage_resets_at,
  overage_disabled_reason, raw)`, `RateLimitEvent(rate_limit_info, uuid, session_id)`), `:1006-1023` (`ResultMessage`
  без `api_error_status`). `_internal/message_parser.py:233-252` выдаёт `rate_limit_event` как `RateLimitEvent`.
  Конструкторы из AV-F1 валидны как есть.

### Drift Log

**Verdict: light → auto_fix.** Все функции, на которые опирается дизайн, существуют с ожидаемыми сигнатурами;
сдвинулись строки, LOC и пара деталей контракта. Остальные разделы спеки не правились (по заданию) — правильные
ссылки ниже и в задачах.

| # | Спека говорит | Код на 2026-09-24 | Действие |
|---|---|---|---|
| D1 | LOC: runner_loop 281, claude-runner 368, callback 371 | 297 / 370 / 358; runner_result 390, db 376, db_decisions 169 — совпадают | бюджеты ниже пересчитаны |
| D2 | `runner_loop.py:161-200` consume, `:187-189` refusal, `:278-281` generic → exit 1 | consume `:159-216`, refusal-сбор `:203-205`, generic `:294-297`, BUG-188 блок `:269-289` | якоря ниже |
| D3 | `claude-runner.py:273-290` refusal / exit 4 | summary `:274`, exit 4 `:287-291`, salvage `:293`, `build_log_data` `:295-311`, `headless_guards` `:312` | якоря ниже |
| D4 | Step 7 `callback.py:333-360` | Step 7 `:307-340`, `if sid:` `:316`, `verify_status_sync` `:330-336`; Step 7b `:342-349` — `autopilot_event(project_path, task_label, status, verdict, why)`, вердикт `(status, reason) \| None` | `requeue` возвращает тот же кортеж и ставит `why` |
| D5 | `bash scripts/check-loc-limit.sh` (Task 2, Verify Command) | файл — `scripts/vps/check-loc-limit.sh` | везде: `bash scripts/vps/check-loc-limit.sh` |
| D6 | `requeue(project_path, sid, pueue_id, project_id, preview)` | `preview` не используется; `callback_decisions.project_id` пишется как `Path(project_path).name` (`callback_sync.py:330`), а не как project_id из label | `requeue(project_path, spec_id, pueue_id)`, project_id выводится внутри тем же способом |
| D7 | `count_requeues_since(spec_id, hours)` | spec-id уникальны только внутри проекта (флот: awardybot TECH-1535, dowry TECH-526 — диапазоны пересекаются) | `count_requeues_since(project_id, spec_id, hours)` — то же количество кода, без ложных совпадений между проектами |
| D8 | дизайн `requeue` сразу вызывает `write_lifecycle` | без `lifecycle.yaml` запись **создаст** файл (Rule 3, `lifecycle_git.py:108-132`); открытый circuit (TECH-169) не проверяется | переиспользовать `callback_sync._read_existing_status` (`:87-118`: circuit / Rule 3 / Rule 7) и `_write_status` (`:255-298`: Rule 7 race → noop `rule_7_saved`) |
| D9 | абзац LOC называет `runner_ratelimit.decide(state, summary)` | в Design — `decide_exit(state, rl)` | `decide_exit` |
| D10 | Task 3 без тестового файла, EC-10 без места | `test_db.py` вне Allowed Files | EC-10 — в `tests/integration/test_callback_rate_limit_requeue.py`, файл создаётся в Task 3 |
| D11 | «следующий свободный EXP» | максимум в `ai/experiments/` — EXP-013 (`2026-09-23-headless-no-background-wait.md`) | **EXP-014** |
| D12 | — | `.github/workflows/test.yml:62` «split callback.py into seven modules»; `.claude/rules/dependencies.md` «binds 12 names» (на деле уже 13) | Task 4 / Task 6 правят числа |
| D13 | — | причина пишется в `blocked_reason` и для `queued` (`lifecycle_git.py:144-145`; так же делает `reconcile_orphans`); в `transitions` причины нет | EC-8 проверяет `blocked_reason` |

**Sync zones:** нет. `.claude/rules/dependencies.md` в корне расходится с `template/` намеренно
(`.claude/rules/template-sync.md:97`); `scripts/vps/` в template не поставляется. Задача синхронизации не нужна.

> Номера строк ниже — на момент **до** соответствующей задачи. Задачи 2 и 4 правят разные файлы, так что сдвиги
> не пересекаются.

### Task 1: `runner_ratelimit` — детектор, сводка, решение exit 5

**Type:** code
**Files:**
- Create: `scripts/vps/runner_ratelimit.py` (≤ 110 LOC)
- Test: `scripts/vps/tests/test_runner_ratelimit.py` (create)

**Context:** модуль по образцу `runner_refusal.py:1-13` (докстринг Module/Role/Uses/Used by): только stdlib,
утиная типизация, SDK **не импортировать** — `runner_loop` должен остаться единственным модулем, импортирующим SDK
(фикстуры перезагружают только его, `dependencies.md` «The split line is the SDK»).

**Contract:**
- `from_message(message) -> dict | None`
  - `info = getattr(message, "rate_limit_info", None)`; не `None` → `{"source": "event", "status", "resets_at",
    "rate_limit_type", "utilization", "overage_status"}`, каждое через `getattr(info, …, None)`. Любой статус пишется,
    `allowed_warning` тоже.
  - иначе `getattr(message, "error", None) == "rate_limit"` → ровно `{"source": "assistant_error", "status": "rejected"}`
    (EC-1 сравнивает весь dict — лишних ключей нет).
  - иначе `None`. Текст сообщения не читается вообще (EC-3).
- `summary(events: list) -> dict` — ключи всегда все восемь: `detected` (`bool(events)`), `rejected` (любой
  `status == "rejected"`; `assistant_error` всегда даёт `"rejected"`), `rate_limit_type` и `resets_at` (последнее
  непустое), `resets_at_iso` (`datetime.fromtimestamp(resets_at, tz=timezone.utc).isoformat()` или `None`),
  `utilization_max` (max непустых или `None`), `sources` (sorted, без повторов), `events` (`[:10]`).
- `decide_exit(state: dict, rl: dict) -> int` — `5`, если `rl["rejected"]` и
  `not (state["result_received"] and not state["result_is_error"])` (ADR-024) и `state["exit_code"] in (0, 1, 2, 3)`;
  иначе `state["exit_code"]` без изменений (124, 4, 143 не трогаются). `state` не мутирует. При возврате 5 —
  `logger.warning("RATE_LIMITED type=%s resets_at=%s exit %d→5", …)`, `logging.getLogger("claude-runner")`.

**Tests (red today: `ModuleNotFoundError: runner_ratelimit`)** — стабы через `types.SimpleNamespace`, фикстура раннера не нужна:
- EC-1 `test_synthetic_message_is_rejected` — `from_message(NS(content=[…], model="<synthetic>", error="rate_limit")) == {"source": "assistant_error", "status": "rejected"}`.
- EC-2 `test_rejected_event_summary` — событие `rejected / 1790161200 / five_hour` → `summary(...)["rejected"] is True`, `resets_at == 1790161200`, `resets_at_iso == "2026-09-23T11:00:00+00:00"`, `rate_limit_type == "five_hour"`.
- EC-1/EC-2 на настоящих типах: `test_real_sdk_types` — `pytest.importorskip("claude_agent_sdk")`, `AssistantMessage(content=[], model="<synthetic>", error="rate_limit")` и `RateLimitEvent(rate_limit_info=RateLimitInfo(status="rejected", resets_at=1790161200, rate_limit_type="five_hour"), uuid="u", session_id="s")` дают те же результаты (ловит переименование полей в SDK — главный риск утиной типизации).
- EC-3 `test_agent_text_about_limits_is_not_detected` — parametrize: ассистент с текстом «You've hit your session limit» и `error=None`; result-подобный объект; `NS(subtype="init", data={})` → `None`.
- EC-4 `test_allowed_warning_is_detected_not_rejected` — `status="allowed_warning", utilization=0.91` → `detected True`, `rejected False`, `utilization_max == 0.91`.
- EC-5 `test_empty_summary_has_every_key` — `summary([])`: `detected False`, `rejected False`, `resets_at None`, `events == []`, набор ключей = восемь из контракта.
- `test_decide_exit_*` (EC-6/EC-7 на уровне функции) — rejected + exit 1 без результата → 5; rejected + `result_received=True, result_is_error=False` → 0; exit 124 / 4 / 143 → без изменений; `rejected=False` → без изменений.

**Commands:** `pytest scripts/vps/tests/test_runner_ratelimit.py -v` — сначала падает на импорте, после реализации зелёный.

**Acceptance:** EC-1, EC-2, EC-3, EC-4, EC-5.

### Task 2: раннер собирает события и ставит exit 5

**Type:** code
**Files:**
- Modify: `scripts/vps/runner_loop.py:7,33-35,203-205` (297 → ≤ 302)
- Modify: `scripts/vps/claude-runner.py:29,291-293,312` (370 → ≤ 375; бюджет спеки ≤ 8 строк)
- Modify: `scripts/vps/runner_result.py:31` (390 → 391, **ровно одна строка**)
- Test: `scripts/vps/tests/test_runner_ratelimit.py` (extend)

**Context:** прогон с упором в лимит сейчас пишет `exit_code: 1` и ничего о причине.

**Steps:**
1. Тесты (красные: exit 1, нет ключа `rate_limit`). Взять фикстуру и фейки из соседнего теста — прецедент
   `test_orchestrator.py:22` (`from test_db import …`): `import test_claude_runner_refusal as base`, `runner = base.runner`
   (присваивание атрибута модуля регистрирует фикстуру и не даёт ruff F811 на параметр `runner`), драйверы
   `base.run` / `base.read_log`, `base.FakeAssistantMessage` (уже принимает `error=`, `:52`). Для события лимита —
   локальный класс `FakeRateLimitEvent` с атрибутом `rate_limit_info` (isinstance по нему в раннере нет).
   - EC-6 `test_rate_limit_then_sdk_exception_exits_5` — поток: `FakeAssistantMessage(content=[FakeTextBlock("You've hit your session limit · resets 2pm (Europe/Helsinki)")], model="<synthetic>", error="rate_limit")`, затем `raise RuntimeError("Command failed with exit code 1 … Check stderr output for details")` (патч `runner.runner_loop.query`, как `test_claude_runner_refusal.py:419-425`). Перед запуском `runner._salvage = SimpleNamespace(spec_id_from_path=lambda _p: "TECH-1", salvage_run=lambda _path, _sid, reason: {"reason": reason})`. Ожидание: `exit_code == 5`, `read_log(runner)["rate_limit"]["rejected"] is True`, `read_log(runner)["salvage"]["reason"] == "rate_limited"`, `runner._EXIT_REASONS[5] == "rate_limited"`.
   - EC-7 `test_rate_limit_after_successful_result_keeps_exit_0` — `FakeResultMessage(result='{"task_status": "complete"}')`, затем `FakeRateLimitEvent(status="rejected")` → `exit_code == 0`, `rate_limit.rejected is True` (записано, но не решает).
   - EC-5 на уровне лога: `test_clean_run_logs_rate_limit_block` — обычный прогон → `read_log(runner)["rate_limit"]["detected"] is False`.
2. `runner_loop.py`: импорт `import runner_ratelimit` между `runner_heartbeat` и `runner_refusal` (`:33-34`), строка `Uses:` (`:6-7`) дополняется им же. В `consume` сразу после добавления refusal-события (`:203-205`): `ev = runner_ratelimit.from_message(message)` → если не `None`, `state.setdefault("rate_limit_events", []).append(ev)`. `setdefault`, а не новый ключ в `new_run_state` — у `runner_result.py` нет запаса LOC.
3. `claude-runner.py`: `import runner_ratelimit  # noqa: E402 — rate-limit detection, exit 5 (TECH-225)` после `:29` (`runner_models`). Между концом exit-4 блока (`:291`) и `salvage_info = …` (`:293`): `rate_limit = runner_ratelimit.summary(state.get("rate_limit_events", []))`, `state["exit_code"] = runner_ratelimit.decide_exit(state, rate_limit)` — **до** salvage, чтобы причина salvage была `rate_limited`. После `log_data["headless_guards"] = …` (`:312`): `log_data["rate_limit"] = rate_limit`.
4. `runner_result.py:31`: после `4: "classifier_refusal",` добавить `5: "rate_limited",`.

**Must NOT change:** строка `claude-runner.py:287` `if refusal["unrecovered"] and state["exit_code"] == 0:` (её текст проверяет
`test_claude_runner_refusal.py:486`); BUG-188 ветка `runner_loop.py:269-289` без присваиваний `exit_code`
(`test_claude_runner_refusal.py:473-480`); `runner_result.new_run_state` и `build_log_data` — не трогать.

**Commands:** `pytest scripts/vps/tests/test_runner_ratelimit.py scripts/vps/tests/test_claude_runner_refusal.py scripts/vps/tests/test_claude_runner_timeout.py -v` зелёный; `bash scripts/vps/check-loc-limit.sh` → exit 0; `grep -n '5: "rate_limited"' scripts/vps/runner_result.py` → 1 строка.

**Acceptance:** EC-6, EC-7.

### Task 3: счётчик возвратов в БД

**Type:** code
**Files:**
- Modify: `scripts/vps/db_decisions.py:9,30,53` (169 → ≤ 186)
- Modify: `scripts/vps/db.py:353` (376 → 377, одна строка)
- Modify: `scripts/vps/schema.sql:80` (только комментарий)
- Test: `tests/integration/test_callback_rate_limit_requeue.py` (create)

**Steps:**
1. Тест (красный: `AttributeError: module 'db' has no attribute 'count_requeues_since'`): фикстура `tmp_db` — копия
   `tests/integration/test_callback_blocked_no_dispatch.py:43-53` (в `tests/integration/` нет прецедента импорта между
   тестовыми модулями). EC-10 `test_count_requeues_since_window_and_scope` — через `db.record_decision`: 2 строки
   `("proj", "TECH-1", "requeue", "rate_limited")` сейчас; 1 такая же строка с `ts` на 25 ч назад (сырой
   `INSERT` с `strftime('%Y-%m-%dT%H:%M:%SZ','now','-25 hours')`); 1 для `TECH-2`; 1 для `("other", "TECH-1")`;
   1 `requeue` с `reason="fleet_paused"` → `db.count_requeues_since("proj", "TECH-1", 24) == 2`.
2. `db_decisions.py`: после `count_demotes_since` (`:41-52`) — `count_requeues_since(conn, project_id: str, spec_id: str, hours: int) -> int`,
   по образцу `:46-52`: `COUNT(*)` при `project_id = ? AND spec_id = ? AND verdict = 'requeue' AND reason = 'rate_limited'
   AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)` с параметром `f"-{int(hours)} hours"` (ADR-017, только `?`).
   Дописать имя в «Used by» (`:9`), `'requeue'` — в список вердиктов (`:30`).
3. `db.py`: после `:353` — `count_requeues_since = _delegate(db_decisions.count_requeues_since)`.
4. `schema.sql:80`: комментарий → `-- 'demote' | 'sync' | 'noop' | 'circuit_open' | 'requeue'`. Таблица и индексы не меняются.

**Commands:** `pytest tests/integration/test_callback_rate_limit_requeue.py -v -n0` зелёный; `pytest scripts/vps/tests/test_db.py -q` зелёный.

**Acceptance:** EC-10.

### Task 4: callback возвращает спеку в очередь

**Type:** code
**Files:**
- Create: `scripts/vps/callback_ratelimit.py` (≤ 90 LOC)
- Modify: `scripts/vps/callback.py:11,41,316` (358 → ≤ 366)
- Modify: `.github/workflows/test.yml:62,78`
- Test: `tests/integration/test_callback_rate_limit_requeue.py` (extend)

**Context:** exit 5 у autopilot — не провал работы; спека должна уйти в `queued`, а не в `blocked`.

**Contract — `callback_ratelimit.requeue(project_path: str, spec_id: str, pueue_id: int | None) -> tuple[str, str] | None`:**
шапка модуля и `sys.path` — по образцу `callback_circuit.py:1-32`; `log = logging.getLogger("callback")`; константы
`REQUEUE_CEILING = 3`, `REQUEUE_WINDOW_HOURS = 24`, `REQUEUE_REASON = "rate_limited"`. Соседние модули вызываются
как атрибуты модуля (контракт TECH-216: так их достаёт monkeypatch).
1. `project_id = Path(project_path).name`; `audit = callback_sync._Audit(project_id, spec_id, pueue_id, "queued", time.monotonic())`.
2. `callback_sync._read_existing_status(project_path, spec_id, audit)` вернул `None` → вернуть `None` (circuit open /
   нет yaml / уже `done` — noop и строку аудита он пишет сам). Это покрывает EC-11.
3. `prior = db.count_requeues_since(project_id, spec_id, REQUEUE_WINDOW_HOURS)`; ошибка БД → `log.warning`, `prior = 0`
   (возврат в очередь не должен ломаться на счётчике).
4. `prior >= REQUEUE_CEILING - 1` → `("blocked", f"repeated_rate_limit:{prior + 1}")` + `callback_circuit.note_demote(project_id, spec_id, reason)`
   (`demoted=1`, в окно circuit breaker попадает); иначе `("queued", REQUEUE_REASON)` +
   `callback_circuit._record(project_id, spec_id, "requeue", REQUEUE_REASON)` (`demoted=0`).
5. `log.warning("REQUEUE_RATE_LIMIT %s → %s (%s)", spec_id, status, reason)` — по этой строке считает эксперимент.
6. `callback_sync._write_status(project_path, spec_id, status, reason, audit)` вернул False → `None` (гонка по Rule 7 →
   noop `rule_7_saved`, это уже сделано внутри). Иначе `audit.emit(status, reason)`, вернуть `(status, reason)`.
Порядок «записать решение → записать статус» повторяет `verify_status_sync` (`callback_sync.py:362-373`).

**Steps:**
1. Тесты (красные: спека уходит в `blocked` через `verify_status_sync`). Хелперы копируются из
   `test_callback_blocked_no_dispatch.py:60-148` (`stub_event_writer`, `_git`, `_make_project`, `_seed_db`, label
   `autopilot-<ID>`, project dir `proj`). Драйвер: `monkeypatch.setattr(callback, "extract_agent_output", lambda *a, **kw: ("autopilot", "", ""))`,
   `monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))` (иначе аудит пишется в `scripts/vps/`),
   `patch("sys.argv", ["callback.py", str(pid), "claude-runner", "Failed", "5"])`, `patch("sys.exit")`. События Hermes
   записываются подменой `event_writer.notify` на функцию-регистратор (`callback_event` вызывает его как атрибут модуля).
   - EC-8 `test_exit5_requeues_spec` — lifecycle: `status == "queued"`, `updated_by == "callback"`, `blocked_reason == "rate_limited"`, `transitions[-1]` = `in_progress → queued`, `by: callback`; `callback_decisions`: одна строка `verdict='requeue'`, `reason='rate_limited'`, `demoted=0`; `db.count_demotes_since(10) == 0`; в записанном событии есть `"autopilot queued"` и `"rate_limited"`.
   - EC-9 `test_third_requeue_in_24h_blocks` — заранее 2 × `db.record_decision("proj", sid, "requeue", "rate_limited", demoted=False)` → `status == "blocked"`, `blocked_reason == "repeated_rate_limit:3"`, последняя строка решений `verdict='demote'`, `demoted=1`.
   - EC-11 `test_already_done_is_noop` — перед `main()` `lifecycle.write_lifecycle(repo, sid, "done", by="callback")` → статус остаётся `done`, есть строка `noop` / `already_done_terminal`, строк `requeue` нет, `sys.exit` вызван с `0`.
2. `callback_ratelimit.py` — по контракту выше.
3. `callback.py`: `import callback_ratelimit  # noqa: E402  — exit 5 → queued (TECH-225)` после `:41` (`callback_logs`);
   в `Uses:` после `:11` — `  - callback_ratelimit: requeue  (TECH-225)`. Строку `:316` `if sid:` заменить на
   `if sid and exit_code == 5:` → `verdict = callback_ratelimit.requeue(project_path, sid, int(pueue_id) if pueue_id else None)`,
   `why = "no_decision"`; затем `elif sid:` — существующее тело `:317-337` остаётся как есть, без смены отступов.
   `exit_code` уже есть в области видимости (`:234`, `map_result`).
4. `test.yml`: после `:78` — `--cov=callback_ratelimit \`; комментарий `:62` → «TECH-216/224/225 split callback.py into eight modules».

**Must NOT change:** условие Step 7 `skill == "autopilot" and status in ("done", "failed")` (`:308`), Step 7b (`:342-349`),
`finally: sys.exit(0)`; `callback_sync.py` (вне Allowed Files — только вызов его функций).

**Commands:** `PYTHONPATH=scripts/vps pytest tests/integration/test_callback_*.py -v -n0` зелёный;
coverage-гейт из `test.yml:67-81` локально → ≥ 54%; `bash scripts/vps/check-loc-limit.sh` → exit 0.

**Acceptance:** EC-8, EC-9, EC-11.

### Task 5: эксперимент EXP-014

**Type:** code (docs)
**Files:**
- Create: `ai/experiments/2026-09-23-rate-limit-requeue.md`

**Contract:** шапка по `ai/experiments/README.md:29-42` (обязательные поля — `scripts/check-experiments.py:32`):
`id: EXP-014`; `opened:` дата коммита; `status: open`;
`metric:` autopilot-прогоны с `"exit_code": 5` в `~/projects/dld/scripts/vps/logs/*.log` с даты выкатки и что стало с их
спекой (`grep REQUEUE_RATE_LIMIT scripts/vps/callback-debug.log` против `STATUS_SYNC … blocked` для тех же спек);
`baseline:` 23.09 — 2 прогона упёрлись в лимит, 2 из 2 → `blocked` (`branch_pushed_not_merged`), exit 1, причина нигде не записана;
`expected:` 100% упёршихся → exit 5 с блоком `rate_limit`; первый возврат каждой спеки → `queued` (`rate_limited`);
ни одного `blocked` из-за лимита, кроме `repeated_rate_limit:<n>`;
`command:` `find ~/projects/dld/scripts/vps/logs -name '*.log' -newermt <opened> | xargs grep -l '"exit_code": 5'`;
`check_after_runs: 40`; `check_after_date:` opened + 21 день; `verdict:` пусто.
Тело: (а) что меняется и зачем; (б) **без TECH-226 спека, возвращённая в очередь, сразу диспатчится снова и упирается
в тот же лимит — три таких круга за минуты дают `repeated_rate_limit:3`. Это известный потолок, а не опровержение;
вердикт выносится по срезу после выкатки TECH-226**; (в) что делать, если `rate_limit_event` не приходит: детектор
видит только `assistant_error`, `resets_at` всегда unknown → TECH-226 живёт на запасном интервале; поднять SDK до
версии с `ResultMessage.api_error_status` (≥ 0.1.81); (г) лимит за срок не случился → `inconclusive` с этой формулировкой.

**Commands:** `python scripts/check-experiments.py` → exit 0.

**Acceptance:** DoD «check-experiments exit 0».

### Task 6: доки

**Type:** code (docs)
**Files:**
- Modify: `docs/orchestrator/status-model.md:172` + новый подраздел между `:270` и `:272`
- Modify: `.claude/rules/dependencies.md` — разделы `scripts/vps/db`, `scripts/vps/claude-runner.py`, `scripts/vps/callback.py`

**Steps:**
1. `status-model.md:172` (строка Step 7 в таблице): добавить «autopilot с `exit_code == 5` → `callback_ratelimit.requeue` вместо `verify_status_sync` (TECH-225)».
2. Новый подраздел `### Rate limit → queued (TECH-225)` перед `### TECH-197 hardening`: exit 5 = `rate_limited`
   (раннер: `AssistantMessage.error == "rate_limit"` или `RateLimitEvent` `rejected` без успешного результата, ADR-024);
   `in_progress → queued`, `by=callback`, причина в `blocked_reason`; решение `requeue`, `demoted=0`; третий возврат за
   24 ч → `blocked repeated_rate_limit:<n>` через `note_demote`; noop-пути те же, что в Step 1 `verify_status_sync`;
   salvage пушит ветку, следующий диспатч её продолжает (TECH-221); пауза до `resets_at` — TECH-226.
3. `dependencies.md`: таблица модулей claude-runner — строка `runner_ratelimit.py` (`from_message`, `summary`,
   `decide_exit`, решение exit 5, только stdlib), актуальные LOC для `runner_loop.py` / `runner_result.py` /
   `claude-runner.py`, `_EXIT_REASONS` включает 5 = `rate_limited`; раздел callback — строка `callback_ratelimit.py`,
   «six flat siblings» → seven, «lists all seven modules» → eight, LOC `callback.py`; раздел db — `count_requeues_since`
   в строке `db_decisions.py`, «binds 12 names» → 14; «When changing API» (db) — «claude-runner exit 5 = `rate_limited`».

**Commands:** `grep -c "rate_limited" docs/orchestrator/status-model.md .claude/rules/dependencies.md` → ≥ 1 в каждом;
`python scripts/check-rules-loading.py .` → exit 0.

**Acceptance:** DoD — доки называют exit 5 и путь `in_progress → queued`.

### Execution Order

- **1 → 2:** Task 2 импортирует `runner_ratelimit`.
- **3 → 4:** `callback_ratelimit` вызывает `db.count_requeues_since`; Task 4 дописывает тестовый файл, созданный в Task 3.
- **2, 4 → 5:** эксперимент описывает уже работающее поведение и строку лога `REQUEUE_RATE_LIMIT`.
- **1–4 → 6:** доки описывают итоговые сигнатуры и LOC.
- Итоговый порядок: 1 → 2 → 3 → 4 → 5 → 6. Финальная проверка — Verify Command спеки, но LOC-гейт запускать как `bash scripts/vps/check-loc-limit.sh` (D5).

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

### Task 1/6: runner_ratelimit — 2026-09-24
- Coder: completed (2 files: scripts/vps/runner_ratelimit.py, scripts/vps/tests/test_runner_ratelimit.py)
- Tester: passed (16/16)
- Spec compliance: matches (EC-1..EC-5 + test_real_sdk_types)
- Code Quality Reviewer: approved (0 blocking, 1 advisory)
- Commit: be5a97da

### Task 2/6: exit 5 в раннере — 2026-09-24
- Coder: completed (4 files: runner_loop.py 302, claude-runner.py 375, runner_result.py 391 (+1 строка), test_runner_ratelimit.py)
- Tester: passed (144/144)
- Spec compliance: matches (EC-6, EC-7; decide_exit до salvage → reason rate_limited)
- Code Quality Reviewer: approved (0 blocking)
- Commit: 86e23e38

### Task 3/6: count_requeues_since — 2026-09-24
- Coder: completed (4 files: db_decisions.py, db.py, schema.sql, tests/integration/test_callback_rate_limit_requeue.py)
- Tester: passed (86/86)
- Spec compliance: matches (EC-10; + project_id scope, drift D7)
- Code Quality Reviewer: approved (0 blocking)
- Commit: ccf4835b

### Task 4/6: callback requeue — 2026-09-24
- Coder: completed (4 files: callback_ratelimit.py 71, callback.py 365, test.yml, integration test)
- Tester: passed (215/215; prod orchestrator.db не тронута)
- Spec compliance: matches (EC-8, EC-9, EC-11)
- Code Quality Reviewer: approved (0 blocking, 1 advisory)
- Commit: e2b576e8

### Task 5/6: EXP-014 — 2026-09-24
- Coder: completed (1 file); check-experiments exit 0
- Tester: skipped (docs)
- Spec compliance: matches
- Code Quality Reviewer: approved
- Commit: 0ae2232d

### Task 6/6: доки — 2026-09-24
- Coder: completed (2 files: status-model.md, dependencies.md); check-rules-loading exit 0
- Tester: skipped (docs)
- Spec compliance: matches
- Code Quality Reviewer: approved
- Commit: 60152337

### Finish — 2026-09-24
- Final test: CI_PARITY_UNAVAILABLE (нет ./test ci) → `pytest tests/ scripts/vps/tests/` одной командой: 1230 passed, 3 skipped, 1 failed — `test_worktree_hook_blocks.py::test_installer_leaves_guard_active_from_relative_legacy_state`, утечка CLAUDE_CURRENT_SPEC_PATH из окружения раннера (с `env -u` 4/4 passed; SIGNAL-2026-09-24-0010 + 0400), вне скоупа
- Gates: ruff check/format (0.16.1) OK, check-loc-limit OK, check-experiments OK, prompt-integrity clean
- Local Verify: AV-S1 pass (`ok`), AV-F1 pass (rejected True, resets_at 1790161200); AV-F2 — при первом боевом 429 (EXP-014)
- Exa Verify: no issues — issue #401 (error парсился из message.error) не касается 0.1.63: парсер читает `data.get("error")` верхнего уровня, как в транскрипте 23.09
- Documenter: completed (components.md, README.md, model-capabilities.md, status-model.md anchor) — d93b01eb
- Post-Deploy Verify: skip (local-only)
