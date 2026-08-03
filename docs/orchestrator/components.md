# Components Reference

Покомпонентный справочник оркестратора. Путь записи статуса вынесен в [status-model.md](status-model.md).

---

## <a name="orchestratorpy"></a>orchestrator.py — главный цикл

systemd user-unit `dld-orchestrator.service`. Каденс `POLL_INTERVAL` env, **default 300с (5 мин)**
(`:938`), сон через прерываемый `_stop.wait()` (`:971`). Heartbeat в конце цикла → `.orchestrator-heartbeat`
(ISO, `:964-969`). PID-файл, SIGTERM/SIGINT → graceful.

**Порядок цикла** (`main:948-961`): `release_orphan_slots` → `sync_projects` → `dispatch_night_review`
→ per-project `process_project`. `process_project` (`:918-928`): `git_pull` → `scan_inbox` →
`bootstrap_new_specs` → `scan_queued`.

| Функция | Что делает | file:line |
|---------|-----------|-----------|
| `scan_queued` | Источник — `lifecycle.list_by_status({queued,resumed})` (HEAD, не backlog.md). Dependency-gate, dup-guard, **TOCTOU re-check**, **reconciliation gate**, dispatch | `:772-898` |
| `scan_inbox` | Hermes intake: только `**Status:** queued` (ADR-021/022), route по `_ROUTE_SKILL_MAP` | `:662-722` |
| `bootstrap_new_specs` | Создаёт yaml для новых spec.md. Column-aware parser, читает HEAD не WT (CWE-367), safe default `queued` | `:402-495` |
| `startup_reconcile` | На старте: `cleanup_stale_stashes` → `assert_clean_lifecycle_tree` (abort на dirty) → `reconcile_orphans` | `:572-593` |
| `git_pull` | `fetch` + `merge --ff-only origin/develop` (не `pull` — FETCH_HEAD race fix). Skip пока агент работает | `:254-308` |
| `release_orphan_slots` | BUG-162: освобождает слоты без живого pueue_id. `get_live_pueue_ids() is None` → release 0 (no false release) | `:204-227` |
| `sync_projects` | Hot-reload `projects.json` по mtime → `db.seed_projects_from_json` | `:83-97` |
| `dispatch_night_review` | `.review-trigger` → `pueue add --group night-reviewer` | `:901-915` |

**Ключевые детали:**
- **TOCTOU re-check (BUG-205, `:855-870`):** прямо перед `pueue add` перечитывает
  `lifecycle.read_lifecycle(spec)` (HEAD); если статус уже не `queued/resumed` → abort. Snapshot из
  `list_by_status` устаревает (callback — отдельный процесс; git_pull пропущен пока агент работает).
- **Dependency gate (BUG-206, `:782-795`):** spec с `AFTER <ID>` в backlog-строке диспатчится только
  когда все зависимости `done` (status из lifecycle SoT). Отсутствующая зависимость = MET (анти-stall).
- **Reconciliation gate (2026-06-26):** ПЕРЕД `pueue add` — `gate_logic.find_implementation_commit`
  на `origin/develop` (та же проверка, что callback-guard и gate-daemon). Если работа уже на develop →
  orchestrator сам пишет `done` (`by="orchestrator"`, reason `already_implemented_on_develop:<sha>`),
  сессию НЕ запускает. Закрывает дыру single-writer (ADR-023): работа, пришедшая мимо callback (другой
  разработчик / другое окно / другой узел / сессия, чей callback не сработал), оставляла lifecycle
  `queued`, и оркестратор переделывал готовое. Fail-closed: реконсилит только при позитивном allowlist
  И позитивном совпадении коммита; иначе диспатчит как раньше.
- **Dup-guard:** `pueue_has_active_label` (project:spec) + `pueue_has_active_spec` (Rule 8 —
  кросс-проектный double-dispatch одного spec_id).
- **CLAUDE_CURRENT_SPEC_PATH (BUG-199):** pin spec path в pueue env для pre-edit hook Allowed Files.
- **Crash recovery:** `reconcile_orphans` (by=orchestrator) демоутит `in_progress` без живого pueue_id.

---

## <a name="run-agentsh"></a>run-agent.sh — provider dispatcher

`run-agent.sh <project_dir> <provider> <skill> <task...>` (`:12-16`). Шаги:

1. **RAM floor gate** (`:29-43`): `/proc/meminfo` MemAvailable; `< 3GB` → JSON error
   `insufficient_ram` + `exit 78` (EX_CONFIG). Запуск под памятью = OOM на полпути =
   потраченные токены.
2. `SKIP` env (TECH-178): bypass косметических pre-commit fixers.
3. Dispatch (case по provider): `claude` → `venv/bin/python3 claude-runner.py <dir> <task> <skill>`;
   `codex` → `codex-runner.sh`; `gemini` → `gemini-runner.sh`. Unknown → error exit 1.

> Порядок аргументов у runner'ов отличается: run-agent.sh принимает `(dir, provider, skill, task)`,
> а runner'ы — `(dir, task, skill)`.

---

## <a name="claude-runnerpy"></a>claude-runner.py — autopilot-сессия (Agent SDK)

`query()` + `ClaudeAgentOptions` (`:222-247`). Аргументы `main`: `<project_dir> <task> [skill]`.

| Параметр | Значение | file:line |
|----------|----------|-----------|
| `MODEL` | `AUTOPILOT_MODEL` env, default **`claude-opus-4-8`** | `:73` |
| `effort` | `AUTOPILOT_EFFORT` env, default **`high`**, enum `{low,medium,high,max}` (no xhigh в SDK) | `:77-80` |
| `max_turns` | **120** | `:68` |
| `setting_sources` | `["user","project"]` — грузит CLAUDE.md + .claude/skills/ | `:227` |
| `permission_mode` | `bypassPermissions` | `:229` |
| `cli_path` | force system `claude` над bundled SDK копией (иначе stale-Opus резолв) | `:83-104` |
| `TIMEOUT_SECONDS` | **5400 (90 мин)** hard limit (`asyncio.timeout`) → exit 124 | `:69, 269` |

- **Heartbeat (TECH-198, `:277-289`):** на КАЖДОМ SDK-сообщении (не только Assistant) пишет
  `logs/{project}-{ts}.heartbeat.json` (поля: `turn`, `elapsed_s`, `last_tool`, `started_at`, `model`,
  `updated_at`). Этот файл читает reaper.
- **exit_code contract (ADR-024, BUG-188, `:375-399`):** после `ResultMessage(is_error=False)` ран —
  успешен; последующее SDK-исключение → **WARNING** (не ERROR) + телеметрия в `sdk_post_result_errors`,
  `exit_code=0` не оверрайдится. Нарушение = ре-блок готовой спеки + ретрай (+$5).
- **JSON-контракт вывода:** `exit_code`, `turns`, `cost_usd`, токены, `task_status` (`complete`/
  `blocked`/`needs_review`), `result_preview`.

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
| `gate_health` | Per-cycle метрики gate-daemon (ARCH-190) |

Функции по группам: **slots** (`try_acquire_slot`/`release_slot`/`get_available_slots`/
`get_occupied_slots`, in `db.py`), **task_log** (`log_task`/`finish_task`/`get_task_by_pueue_id`,
in `db.py`), **decisions** (`record_decision`/`count_demotes_since`/`clear_decisions`, in
`db_decisions.py`), **gate_health** (`log_gate_cycle`, in `db_decisions.py`), **findings**
(`save_finding` INSERT OR IGNORE, in `db_findings.py`).

---

## <a name="event_writerpy"></a>event_writer.py — события в Hermes ⚠️

`notify(project_path, skill, status, message, artifact_rel="")` (`:95-104`): пишет pending-event JSON в
`{project}/ai/openclaw/pending-events/{ts}-{skill}.json` + будит Hermes (`wake_hermes`, `:62-92`).
`notify_circuit_event(action, count, window)` — события circuit-breaker (TECH-169).

> ⚠️ **АКТИВНЫЙ blind spot алертинга.** `wake_hermes` спавнит бинарь `hermes`; если его нет →
> `log.debug` + `return False`, а `notify()` **игнорирует возврат** (`:104`) — no fallback,
> ошибка не всплывает.
> Per memory `openclaw-gateway-down`: gateway снесён ~25 дней, Hermes/Telegram-алерты молча не доходят.
> Через `notify()` идут ВСЕ алерты: night-review, `CIRCUIT_OPEN`, reap. **Перед запуском оркестратора —
> проверить, что транспорт алертов жив** (см. [runbook.md](runbook.md#проверка-перед-запуском)).

---

## <a name="gate-daemon"></a>gate-daemon.py + gate_logic.py — shadow merge-gate (ARCH-190)

Отдельный systemd-демон `dld-gate-daemon.service`, цикл **60с**. **Read-only теневой наблюдатель:**
прогоняет ту же gate-логику, что callback (вынесена в чистые функции `gate_logic`), и **только логирует
вердикт** — статус НЕ трогает.

- **`SHADOW_ONLY_MODE = True`** (`:47`), двойной assert (импорт + старт `main`): «Wave 3 cutover not yet
  authorized». ZERO импортов callback, ZERO вызовов `write_lifecycle` (инвариант FF-09).
- `_evaluate_project` (`:160-275`): `fetch_develop` → SHA-кэш (develop не менялся → `skipped`) →
  `list_by_status({in_progress, queued})` → per-spec: `find_implementation_commit` → вердикт
  `done`/`in_progress`/`blocked`.
- `gate_logic` pure-функции: `fetch_develop` (15s timeout, fail-soft), `parse_allowed_files` (TECH-167
  v1/legacy), `find_implementation_commit` (path-фильтр + `match_subject`, fail-closed), `match_subject`
  (subject-only, TECH-177).
- Пишет: JSONL shadow-лог (`RotatingFileHandler`, 100 MiB × 5), `gate_health` (db), `.gate-daemon-heartbeat`.
  Per-project error isolation. **Не алертит.**

> Назначение: параллельно с callback независимо считать «что бы я сделал» и копить shadow-данные перед
> возможным cutover (Wave 3, не авторизован). Сейчас это диагностика, не enforcement.

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
2. **Авторитетный TOCTOU re-check перед каждым `pueue add`** (BUG-205) — snapshot устаревает.
3. **Не bootstrap-ить в терминальный статус** — unparsable/missing → `queued`, никогда `done`
   (иначе спека «исчезает»: never dispatched + Rule 7 не даст восстановить).
4. **Bootstrap читает backlog из HEAD, не WT** (CWE-367) — параллельные render/правки делают WT гонкой.
5. **Dependency gate** — не диспатчить spec с незакрытой `AFTER <ID>` (BUG-206).
6. **Hermes intake gate** — `scan_inbox` диспатчит только `Status: queued`.
7. **RAM floor ≥3GB** перед запуском LLM-агента (exit 78).
8. **Slot discipline** — не диспатчить без слота; orphan-слоты освобождать, но НИКОГДА при недостижимом
   pueue (`get_live_pueue_ids() is None → release 0`, BUG-162).
9. **Dup-guard на двух уровнях** — `pueue_has_active_label` + `pueue_has_active_spec` (Rule 8).
10. **No-dirty-WT — startup abort.** `assert_clean_lifecycle_tree` raises → FATAL abort daemon.
11. **Crash recovery** — `reconcile_orphans` демоутит `in_progress` без живого pueue_id.
12. **Timeout как hard-limit** (claude 90м/codex 15м/gemini 30м) + heartbeat-reaper добивает зависшие.
13. **exit_code contract (ADR-024)** — post-result Exception не оверрайдит `exit_code=0`.
14. **Reconciliation перед диспатчем** — не запускать сессию на спеке, чья работа уже на `origin/develop`
    (out-of-band completion). `scan_queued` помечает её `done` напрямую (`by="orchestrator"`) и пропускает.
15. **Диспатч обязан оставить след в SoT.** После `pueue add` статус спеки — `in_progress` с
    записанным `pueue_id`; без этого `reconcile_orphans` не видит кандидатов, а `started_at` остаётся
    null навсегда (BUG-218).
16. **Запись статуса не отменяет диспатч.** Любой отказ `write_lifecycle` на этом пути — WARNING в
    лог, не `return False`.
17. **`startup_reconcile` fail-closed.** `get_live_pueue_ids() is None` (pueue недоступен) —
    восстановление пропускается целиком; демоут по предположению снёс бы живую очередь.
