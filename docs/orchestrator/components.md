# Components Reference

Покомпонентный справочник оркестратора. Путь записи статуса вынесен в [status-model.md](status-model.md).

---

## <a name="orchestratorpy"></a>orchestrator.py — главный цикл

systemd user-unit `dld-orchestrator.service`. Каденс `POLL_INTERVAL` env, **default 300с (5 мин)**
(`:938`), сон через прерываемый `_stop.wait()` (`:971`). Heartbeat в конце цикла → `.orchestrator-heartbeat`
(ISO, `:964-969`). PID-файл, SIGTERM/SIGINT → graceful.

**Порядок цикла** (`main:948-961`): `release_orphan_slots` → `sync_projects` → `dispatch_night_review`
→ per-project `process_project`. `process_project`: `git_pull` → `scan_inbox` →
`bootstrap_new_specs` → сброс инварианта `qa_pending`.

**Какую спеку запускать, оркестратор не решает.** С 2026-09-07 это скилл `/dispatcher`
(`~/ops/dispatcher.sh` → `dispatcher.timer`, 15 мин): вход — `dispatch_summary.py`, единственный
глагол — `dispatch_one.py`. Встроенная цепочка (`scan_queued`, `orchestrator_ci_gate.py`,
`DISPATCH_MODE=builtin`) снята 2026-09-27 — см. `docs/2026-09-27-snyatie-relsov-dispetchera.md`.

| Функция | Что делает | file:line |
|---------|-----------|-----------|
| `scan_inbox` | Hermes intake: только `**Status:** queued` (ADR-021/022), route по `_ROUTE_SKILL_MAP` | `:662-722` |
| `bootstrap_new_specs` | Создаёт yaml для новых spec.md. Column-aware parser, читает HEAD не WT (CWE-367), safe default `queued` | `:402-495` |
| `startup_reconcile` | На старте: `cleanup_stale_stashes` → `assert_clean_lifecycle_tree` (abort на dirty) → `reconcile_orphans` | `:572-593` |
| `git_pull` | `fetch` + `merge --ff-only origin/develop` (не `pull` — FETCH_HEAD race fix). Skip пока агент работает | `:254-308` |
| `release_orphan_slots` | BUG-162: освобождает слоты без живого pueue_id. `get_live_pueue_ids() is None` → release 0 (no false release) | `:204-227` |
| `sync_projects` | Hot-reload `projects.json` по mtime → `db.seed_projects_from_json` | `:83-97` |
| `dispatch_night_review` | `.review-trigger` → `pueue add --group night-reviewer` | `:901-915` |

**Ключевые детали:**
- **Зависимости (BUG-206 + TECH-222, рёбра — `spec_deps.declared`):** ребро объявляется в
  трёх местах, читаются все три: `depends_on: [ID]` в lifecycle YAML (SoT; пишет Spark в
  `create_initial`, ретрофит — `lifecycle.set_depends_on`), `**AFTER <ID>**` в первых 15 строках
  спеки (что пишет сам Spark — тот же regex, что в `skills/spark/completion.md`) и backlog-`AFTER`
  (deprecated). Ребро не из YAML логируется как `DEP_VIA: … deps_via=header|backlog`. Рёбра видит
  **сводка LLM-диспетчера** (`dispatch_summary._depends_on`: `waits on X=status`, ссылка вне
  lifecycle — `=missing`); решает диспетчер. До 2026-09-23 сводка читала только YAML, а шапку не
  читал никто — 25 спек флота с ребром только в шапке выглядели свободными (EXP-012).
- **`dispatch_one.py` — стены у запуска:** нет свободного слота; спека уже живая в pueue
  (`pueue_has_active_label` project:spec + `pueue_has_active_spec`, Rule 8 — кросс-проектный
  double-dispatch одного spec_id); нет тела спеки; флот на паузе по лимиту (TECH-226). Каждая
  печатает причину, exit 2.
- **CLAUDE_CURRENT_SPEC_PATH (BUG-199):** `dispatch_one.py` кладёт путь спеки в pueue env — pre-edit
  hook по нему держит Allowed Files; без него `inferSpecFromBranch()` на develop даёт null и хук
  открывается.
- **`in_progress` при запуске (BUG-218):** `orchestrator_queue.record_dispatch` после успешного
  `pueue add` — слот, task_log, lifecycle `in_progress` с `pueue_id`. Отказ записи запуск не откатывает.
- **Crash recovery:** `reconcile_orphans` (by=orchestrator) демоутит `in_progress` без живого pueue_id.
- **Снято 2026-09-27 вместе с builtin-путём:** TOCTOU re-check (BUG-205), reconciliation gate
  («уже на develop → `done` без запуска» и TECH-221 `"continue"` + `CLAUDE_CONTINUE_BRANCH`),
  CI stop-the-line (выключен с 07.09), гейты allowlist и тела спеки (у диспетчера это строки
  `PROBLEM` в сводке, allowlist он чинит сам), `provider:` из шапки спеки. Продолжение ветки после
  таймаута не пострадало: autopilot-промпты сами находят `origin/<type>/<ID>` через
  `git ls-remote` в PHASE 0 — см. [status-model.md](status-model.md#guard) `branch_pushed_not_merged`.

---

## <a name="run-agentsh"></a>run-agent.sh — provider dispatcher

`run-agent.sh <project_dir> <provider> <skill> <task...>` (`:12-16`). Шаги:

1. **RAM floor gate** (`:29-43`): `/proc/meminfo` MemAvailable; `< 3GB` → JSON error
   `insufficient_ram` + `exit 78` (EX_CONFIG). Запуск под памятью = OOM на полпути =
   потраченные токены.
2. `SKIP` env (TECH-178): bypass косметических pre-commit fixers.
3. **Fleet-pause guard (TECH-226), только ветка `claude)`:** перед `exec` — `fleet_pause.py --check`.
   Пауза открыта → **exit 75** (`EX_TEMPFAIL`), ни разу не дозвонившись до Claude API; любой другой
   код из проверки — fail-open, запуск продолжается как обычно. codex/gemini эту проверку не видят —
   маркер про лимит подписки Claude. См. [runbook.md Сценарий 8](runbook.md#сценарий-8-флот-на-паузе-по-лимиту-подписки-tech-226).
4. Dispatch (case по provider): `claude` → `venv/bin/python3 claude-runner.py <dir> <task> <skill>`;
   `codex` → `codex-runner.sh`; `gemini` → `gemini-runner.sh`. Unknown → error exit 1.

> Порядок аргументов у runner'ов отличается: run-agent.sh принимает `(dir, provider, skill, task)`,
> а runner'ы — `(dir, task, skill)`.

---

## <a name="claude-runnerpy"></a>claude-runner.py — autopilot-сессия (Agent SDK)

Аргументы `main`: `<project_dir> <task> [skill]`. С TECH-213 это точка входа на 329 строк;
сам цикл и разбор результата живут в шести соседних модулях (см. `.claude/rules/dependencies.md`
→ claude-runner.py). Цитаты ниже — по символам, а не по номерам строк: номера тут уже врали
один раз, после расколов TECH-210..216.

| Параметр | Значение | Где |
|----------|----------|-----|
| `MODEL` | `AUTOPILOT_MODEL` env, default **`claude-opus-5-5`** (с 23.09.2026; было `claude-opus-5`, откат — `AUTOPILOT_MODEL=claude-opus-5`). Нужен CLI ≥ 2.1.280 | `runner_models.py::DEFAULT_MAIN_MODEL` |
| `effort` | `AUTOPILOT_EFFORT` env, default **`high`**, enum `{low,medium,high,max}` (xhigh нет в SDK) | `claude-runner.py::AUTOPILOT_EFFORT` |
| `max_turns` | **300** (ADR-031; было 120 — стало бы новым узким местом после подъёма таймаута) | `claude-runner.py::MAX_TURNS` |
| `setting_sources` | `["user","project"]` — грузит CLAUDE.md + .claude/skills/ | `runner_loop.py::build_options` |
| `permission_mode` | `bypassPermissions` | `runner_loop.py::build_options` |
| `cli_path` | НОВЕЙШИЙ `claude` на машине, не первый в PATH (иначе тихо резолвится модель прошлого поколения) | `runner_cli.py::_resolve_cli_path` |
| `TIMEOUT_SECONDS` | **10800 (3 ч)** hard limit (`asyncio.timeout`) → exit 124 (ADR-031; на 5400 падал верхний дециль нормальных прогонов) | `claude-runner.py::TIMEOUT_SECONDS` |
| Bash-таймаут внутри сессии | `BASH_DEFAULT_TIMEOUT_MS=900000`, `BASH_MAX_TIMEOUT_MS=1800000` — дефолт CLI 120 с убивал прогон тестов внутри tool call, и подъём внешнего таймаута этого не лечил | `runner_loop.py::build_options` |
| `disallowed_tools` | `ScheduleWakeup`, `Monitor`, `CronCreate`, `CronDelete`, `CronList`, `RemoteTrigger` — снято у **всех** headless-скиллов (TECH-223): будить некого, будильник = зависший ход | `runner_cli.py::HEADLESS_DISALLOWED_TOOLS` |
| Фоновый `Bash`/`Agent` | Только у autopilot (`NO_BACKGROUND_SKILLS`): `env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"`, если не выставлен рычаг отката `HEADLESS_BACKGROUND_TASKS=on` в `.env` (EXP-009-style, ключ должен отсутствовать, не `"0"`). QA сохраняет фон прозой (devil EC-8) — TECH-223 / EXP-013 | `runner_loop.py::build_options` |

- **Heartbeat (TECH-198):** на КАЖДОМ SDK-сообщении (не только Assistant) пишет
  `logs/{project}-{ts}.heartbeat.json` (поля: `turn`, `elapsed_s`, `last_tool`, `started_at`, `model`,
  `updated_at`). Этот файл читает reaper. — `runner_heartbeat.py::_write_heartbeat`
- **stderr CLI на диске (аудит 30.08.2026, причина 3):** каждая строка stderr subprocess'а пишется
  в `logs/{project}-{ts}.stderr.txt` НЕМЕДЛЕННО, а не доживает до сборки run-лога — четыре прогона
  25–26.08 умерли с `Command failed with exit code 1 … Check stderr output for details`, и собранный
  в памяти stderr был пуст (SDK отменяет свой stderr-reader в `close()`). Файл создаётся с шапкой
  сразу: пустой файл отличает «CLI ничего не сказал» от «мы не подписались». Путь и число строк —
  в run-логе (`stderr_log`, `stderr_lines`). Расширение НЕ `.log` намеренно: `callback_logs`
  берёт свежайший `{project}-*.log` по mtime и разобрал бы его как JSON.
  — `runner_loop.py::make_stderr_collector`
- **exit_code contract (ADR-024, BUG-188):** после `ResultMessage(is_error=False)` ран —
  успешен; последующее SDK-исключение → **WARNING** (не ERROR) + телеметрия в `sdk_post_result_errors`,
  `exit_code=0` не оверрайдится. Нарушение = ре-блок готовой спеки + ретрай (+$5).
  — `runner_loop.py::handle_sdk_exception`
- **Classifier refusal (ADR-029):** отказ приходит как HTTP 200 с `stop_reason: "refusal"`, поэтому
  не попадает ни в один except. `unrecovered > 0` → **exit 4**, но только с нуля: таймаут и
  process error сохраняют свой код. — `runner_refusal.py::_refusal_summary`
- **Rate limit (TECH-225):** CLI шлёт синтетический `AssistantMessage.error == "rate_limit"` и,
  когда сервер его включает, `RateLimitEvent` — ничего не бросает, поэтому без этой логики прогон
  тихо становится обычным `exit_code: 1` с пустым stderr (найдено 23.09 только чтением транскрипта
  вручную). `decide_exit` поднимает код до **exit 5** (`rate_limited`), если отказ был и успешного
  результата нет (ADR-024 — успешный `ResultMessage` не перебивается); коды 124/4/143 не трогает.
  Callback на exit 5 у autopilot зовёт `callback_ratelimit.requeue` вместо `verify_status_sync` —
  см. [status-model.md](status-model.md#rate-limit--queued-tech-225). — `runner_ratelimit.py::decide_exit`
- **Fleet pause (TECH-226):** на exit 5, `main()` зовёт `runner_ratelimit.on_rejected` — открывает/
  продлевает окно `fleet_pause.set_pause(resets_at)` (или `+60 мин`, если `resets_at` неизвестен) и
  шлёт **ровно один** алерт в Hermes (`event_writer.notify`, только если этот вызов сам открыл окно).
  Пока окно открыто, следующий claude-запуск выходит **exit 75** прямо в `run-agent.sh`, не доходя до
  этого модуля; callback на 75 зовёт тот же `callback_ratelimit.requeue`, но без потолка 3/24ч —
  см. [status-model.md](status-model.md#rate-limit--queued-tech-225). — `runner_ratelimit.py::on_rejected`
- **JSON-контракт вывода:** `exit_code`, `turns`, `cost_usd`, токены, `task_status` (`complete`/
  `blocked`/`needs_review`), `result_preview`, `refusal`, `salvage`, `rate_limit` (TECH-225).
  — `runner_result.py::build_log_data`

**Прочие runner'ы:** `codex-runner.sh` (timeout 900с/15м, `--sandbox workspace-write --json`);
`gemini-runner.sh` (timeout 1800с/30м, требует `GEMINI_API_KEY`).

---

## <a name="db"></a>db.py + schema.sql — рантайм-состояние (SQLite WAL)

`DB_PATH` env, default `scripts/vps/orchestrator.db`. **Локальный запуск ВСЕГДА с `DB_PATH=/tmp/...`** —
иначе откроешь circuit-breaker в prod. WAL, `busy_timeout=5000`, `BEGIN IMMEDIATE` на slot-операциях.
Идемпотентные runtime-миграции `_ensure_migrations` (self-upgrade старых БД).

**TECH-212 (2026-07-28):** `db.py` (602 → 373 LOC) split into three pure-leaf sibling
modules — `db_decisions.py` (127 LOC: decisions + gate_health + sdk telemetry),
`db_findings.py` (105 LOC: night_findings CRUD), `db_cli.py` (88 LOC: argv dispatcher).
The leaves take the sqlite connection as their first parameter and never `import db`;
`db.py` re-exposes all 12 of their functions via a `_delegate(fn, immediate=...)` factory,
so `db.<name>` and `from db import get_db` are byte-identical for every caller below.
`db_cli.main(sys.argv, sys.modules[__name__])` avoids `import db` deliberately — under
`python3 db.py` that module is `__main__`, and importing `db` would create a second module
object with its own `DB_PATH` / `_MIGRATIONS_APPLIED`.

**7 таблиц:**

| Таблица | Назначение |
|---------|-----------|
| `project_state` | Per-project SoT рантайма: path, chat_id, topic_id, provider, phase, current_task, enabled |
| `compute_slots` | Слоты параллелизма. Seeded: **2× claude, 1× codex, 1× gemini** |
| `task_log` | Лог задач: task_label, skill, status, pueue_id, branch (TECH-170), exit_code |
| `night_findings` | Dedup-стор находок night-review (`UNIQUE(project_id, fingerprint)`) |
| `callback_decisions` | Аудит circuit-breaker (TECH-169): verdict, reason, demoted |
| `sdk_post_result_errors` | Телеметрия BUG-188: post-result SDK-исключения |
| `gate_health` | Per-cycle метрики gate-daemon (ARCH-190). Писателя нет с 2026-09-27 — демон снят, таблица оставлена, чтобы схема не расходилась |

Функции по группам: **slots** (`try_acquire_slot`/`release_slot`/`get_available_slots`/
`get_occupied_slots`, in `db.py`), **task_log** (`log_task`/`finish_task`/`get_task_by_pueue_id`,
in `db.py`), **decisions** (`record_decision`/`count_demotes_since`/`clear_decisions`, in
`db_decisions.py`), **findings**
(`save_finding` INSERT OR IGNORE, in `db_findings.py`).

---

## <a name="event_writerpy"></a>event_writer.py — события в Hermes

`notify(project_path, skill, status, message, artifact_rel="")`: пишет pending-event JSON в
`{project}/ai/openclaw/pending-events/{ts}-{skill}.json` и будит Hermes (`wake_hermes`) —
`hermes -z "<prompt>"`, отсоединённым процессом. Промпт называет **один** только что
записанный файл: `pending-events/` никто не чистит (к 23.09 там 911 файлов у awardybot), это
история, а не очередь. Агент сам решает, писать ли в Telegram: сбой, блокировка, решение
Олега — да; рядовое успешное завершение — нет. Цель — `HERMES_NOTIFY_TARGET` из окружения или
из `scripts/vps/.env` (на VPS — топик «DLD Orch»), иначе домашний канал Hermes.
`notify_circuit_event(action, count, window)` — события circuit-breaker (TECH-169).
`runner_ratelimit.on_rejected` (TECH-226) зовёт тот же общий `notify(..., "rate_limit", "failed",
...)` напрямую — нового типа события нет, ровно один вызов за окно паузы гарантирует
`fleet_pause.set_pause` своим `bool`-возвратом, не что-то в этом модуле.

> ⚠️ **Доставка по-прежнему fire-and-forget:** код оркестратора не видит, отправил ли агент
> сообщение. Видно другое — вывод каждого пробуждения дописывается в `scripts/vps/logs/hermes-wake.log`.
> **С 13.08 по 23.09.2026 не дошёл ни один алерт.** Hermes 2026.8 убрал флаг `-q`, пробуждение
> падало на ошибке argparse, вывод уходил в `/dev/null`; одновременно модель в
> `~/.hermes/config.yaml` (`gpt-5.6-tr`) перестала приниматься провайдером (HTTP 400).
> Проверка звена: `hermes -z "ответь: ок"` и `tail scripts/vps/logs/hermes-wake.log`.

---

## <a name="gate-logic"></a>gate_logic.py + gate_ancestry.py — ядро гейта

Чистые функции гейта, общие для callback и оркестратора. Статус пишет только callback.

- `gate_logic`: `fetch_develop` (15s timeout, fail-soft), `parse_allowed_files` (TECH-167 v1/legacy),
  `find_implementation_commit` (path-фильтр + `match_subject`, fail-closed, DEPRECATED — reached only
  as `gate_ancestry`'s subject fallback), `match_subject` (subject-only, TECH-177).
- `gate_ancestry.find_implementation` (TECH-220): ancestry primary — `<type>/<ID>` предок
  `origin/develop` И принесла ≥1 allowed-файл — before falling back to `find_implementation_commit`.

> **gate-daemon.py (ARCH-190) снят 2026-09-27.** Теневой демон с 23.08 раз в 60 с пересчитывал тот же
> вердикт и писал JSONL; переход к Wave 3 так и не согласовали, потребителя у журнала не было, а
> процесс 34 дня крутил код 23.08 без поля `gate_via`. Разбор —
> `docs/2026-09-27-snyatie-relsov-dispetchera.md`.

---

## Side monitors (cron, kill-only / alert-only — статус не пишут)

| Демон | Триггер | Что делает | Fail-режим |
|-------|---------|-----------|-----------|
| `heartbeat_reaper.py` | cron */5 | Убивает зависшие claude-runner: stale heartbeat >25мин **И** idle CPU (`/proc/*/stat` сэмпл) → `pueue kill` + notify. Grace 5мин | **fail-open** (любая неоднозначность → не killить) |
| `heartbeat_monitor.py` | cron */5 | Алерт если `.orchestrator-heartbeat` > 10 мин (оркестратор завис) | fail-open (нет файла → молча) |
| `orchestrator_monitor.py` | cron */30 | 4 проверки: service alive, circuit-breaker paused, running/queued counts, ≥3 демоута/35мин → alert | service+pueue fail-closed (сбой → alert) |

Ключевая асимметрия: gate-логика и `orchestrator_monitor` консервативны (fail-closed → лишний
alert/blocked), оба heartbeat-инструмента fail-open (никогда не убивают/не спамят при неопределённости).

---

## CI-parity merge gate (TECH-206)

Живёт в autopilot-скиллах (не в `scripts/vps/`): `autopilot-git.md` §5, `finishing.md`, `escalation.md`.

- **Проблема:** autopilot мержил в **красный develop**, т.к. локальный `./test fast` ⊊ CI (CI гоняет
  ~9 проверок: lint, spec-compliance, file-size…), а `ci-status.sh` игнорил CI-only red. Branch
  protection на этих репах недоступен → merge-gate его структурный заменитель.
- **Гейт (`autopilot-git.md` §5.4):** ПОСЛЕ `git merge --ff-only`, ПЕРЕД push: `./test ci`; red →
  `git reset --hard origin/develop` (откат merge, develop остаётся на origin) + `task_status=needs_review`,
  **не пушить**. REGRESSION-ONLY: считаются только НОВЫЕ падения vs PHASE-0 baseline.
- **needs_review → callback маппит в `blocked`, SKIP QA+reflect.**
- **Escalation:** `./test ci` red после **3** попыток → STOP, ask human (`escalation.md`).
- **CI_PARITY_UNAVAILABLE fallback:** `./test ci` отсутствует (exit 127) → log + `./test` (full) →
  needs_review на red. **Никогда не деградировать молча до `./test fast`.**

---

## <a name="инварианты-диспатча"></a>Инварианты диспатча (нарушение = сгоревшие зря токены)

1. **Не диспатчить spec, чей lifecycle-статус ≠ queued/resumed** (SoT = yaml@HEAD, не backlog.md).
   Сводка диспетчера показывает только такие; решает он. Кодом не проверяется: `dispatch_one.py`
   статус не читает.
2. ~~Авторитетный TOCTOU re-check перед каждым `pueue add` (BUG-205)~~ — снят 2026-09-27 вместе с
   builtin-путём. На пути диспетчера его не было и с 07.09; второй запуск живой спеки держит стена
   «уже живая в pueue» в `dispatch_one.py`.
3. **Не bootstrap-ить в терминальный статус** — unparsable/missing → `queued`, никогда `done`
   (иначе спека «исчезает»: never dispatched + Rule 7 не даст восстановить).
4. **Bootstrap читает backlog из HEAD, не WT** (CWE-367) — параллельные render/правки делают WT гонкой.
5. **Зависимости видны диспетчеру** — `depends_on` ∪ шапка `AFTER` ∪ backlog `AFTER` (BUG-206,
   TECH-222, `spec_deps.declared`) печатаются в сводке как `waits on X=status`; решение за ним.
6. **Hermes intake gate** — `scan_inbox` диспатчит только `Status: queued`.
7. **RAM floor ≥3GB** перед запуском LLM-агента (exit 78).
8. **Slot discipline** — не диспатчить без слота; orphan-слоты освобождать, но НИКОГДА при недостижимом
   pueue (`get_live_pueue_ids() is None → release 0`, BUG-162).
9. **Dup-guard на двух уровнях** — `pueue_has_active_label` + `pueue_has_active_spec` (Rule 8).
10. **No-dirty-WT — startup abort.** `assert_clean_lifecycle_tree` raises → FATAL abort daemon.
11. **Crash recovery** — `reconcile_orphans` демоутит `in_progress` без живого pueue_id.
12. **Timeout как hard-limit** (claude 90м/codex 15м/gemini 30м) + heartbeat-reaper добивает зависшие.
13. **exit_code contract (ADR-024)** — post-result Exception не оверрайдит `exit_code=0`.
14. ~~Reconciliation перед диспатчем~~ — снят 2026-09-27 вместе с builtin-путём и **не заменён**
    (так было и с 07.09). Ранний выход autopilot (BUG-188) ищет ID в заголовке коммита и промахивается
    на `feat(managed): …`; слитая спека в `queued` (exit 5 после мержа, сироты при рестарте) уходит на
    полный прогон, который закрывает `done` callback-гейт. Закрывать — фактом «уже на develop» в сводке
    диспетчера.
15. **Диспатч обязан оставить след в SoT.** После `pueue add` статус спеки — `in_progress` с
    записанным `pueue_id`; без этого `reconcile_orphans` не видит кандидатов, а `started_at` остаётся
    null навсегда (BUG-218).
16. **Запись статуса не отменяет диспатч.** Любой отказ `write_lifecycle` на этом пути — WARNING в
    лог, не `return False`.
17. **`startup_reconcile` fail-closed.** `get_live_pueue_ids() is None` (pueue недоступен) —
    восстановление пропускается целиком; демоут по предположению снёс бы живую очередь.
18. **Fleet pause режет `claude`-диспатч (TECH-226).** Пока `fleet_pause.active_pause()` открыт,
    `dispatch_one.py` отказывает `provider == "claude"` спеке ещё до `pueue add` — тот же маркер, что
    `run-agent.sh` проверяет перед `exec`. codex/gemini диспатч не затронут. (До 2026-09-27 ту же
    проверку дублировал builtin-путь.)
