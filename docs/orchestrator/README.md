# DLD Orchestrator — Single Source of Truth

> **Канонический док оркестратора живёт здесь, в репозитории** (`docs/orchestrator/`),
> версионируется вместе с кодом и виден агентам. `~/.claude/projects/-root/memory/`
> содержит только тонкий указатель сюда.
>
> Последняя сверка с кодом: 2026-06-26 (актуально на `lifecycle.py`@22.06, `orchestrator.py`/`callback.py`/`claude-runner.py`@20.06).

| Файл | О чём |
|------|-------|
| **README.md** (этот) | Что/зачем, архитектура, поток задачи, два контракта, ADR-индекс, глоссарий |
| [status-model.md](status-model.md) | **Сердце.** Lifecycle-SoT, запись статуса (CAS), write-once-done, контракт callback, guard, circuit-breaker, инварианты статуса |
| [components.md](components.md) | Покомпонентный справочник + инварианты диспатча |
| [runbook.md](runbook.md) | Операционка: старт/стоп, инцидент-восстановление, drift-инструменты |
| [verification.md](verification.md) | Протокол ручной верификации спеки |
| [callback-lifecycle-contour-to-be.md](callback-lifecycle-contour-to-be.md) | **TO-BE, не AS-IS.** Retrofit-дизайн контура `scripts/vps/` (Alternative C, 2026-05-23). Переехал сюда 2026-08-03 из `ai/blueprint/`, где лежал вперемешку с блюпринтом чужого продукта и раздавался скаутам как constraint. Читать как проект, а не как описание текущего состояния — актуальное состояние в `status-model.md` и `components.md` |

---

## §1 Что такое DLD Orchestrator

DLD Orchestrator — per-VPS демон (systemd user-unit `dld-orchestrator.service`), который автономно
крутит multi-project AI-конвейер: превращает спеки в смёрженный, протестированный код сразу по
нескольким проектам без человека на каждом шаге. **Он не пишет код сам** — это **планировщик +
статус-машина** вокруг AI-сессий.

- **Вход:** спеки в статусе `queued`/`resumed` (из `/spark` или Hermes-intake; только `queued`
  проходит intake-gate — ADR-021/022), список проектов `projects.json`, свободные compute-слоты.
- **Нутро:** главный цикл (`orchestrator.py`, каждые 5 мин) — `git pull`, intake, bootstrap yaml,
  слоты. **Что запускать, решает модель:** скилл `/dispatcher` (с 2026-09-07, таймер 15 мин) читает
  сводку `dispatch_summary.py` и запускает через `dispatch_one.py` → занять слот → `pueue add
  run-agent.sh` → autopilot-сессия (`claude-runner.py` на Agent SDK). По завершении pueue дёргает
  `callback.py`. Встроенная цепочка гейтов (`scan_queued`) снята 2026-09-27.
- **Выход:** смёрженный код на `develop` + авторитетный статус в `ai/lifecycle/{spec}.yaml`
  (рендерится в `ai/backlog.md`), авто-QA и reflect после autopilot, события в Hermes/Telegram.

Состояние рантайма — в SQLite (WAL) `orchestrator.db`. **Состояние статусов спек — в git**
(`ai/lifecycle/*.yaml`), это разные SoT: рантайм (слоты/фазы/лог) эфемерен, статусы — durable.

---

## §2 Архитектура

```
Founder ── inbox / git push ──┐
                              v
            Hermes intake ────►  (Status: draft → queued)   [ADR-021/022]
                              │
                              v
   projects.json ──hot-reload──►  orchestrator.py  ──reads──►  ai/lifecycle/*.yaml  (status SoT, @HEAD)
                              │   (5-min loop)                          ▲
                              │        │                                │ (sole writer)
   orchestrator.db ◄──────────┘        │ pueue add                      │
   (slots, phases, task_log)           v                                │
                              pueue groups: claude×2, codex×1, gemini×1  │
                                        │                                │
                                        v                                │
                              run-agent.sh  (RAM≥3GB gate, provider dispatch)
                                        │                                │
                                        v                                │
                              claude-runner.py  (Agent SDK, /autopilot)  │
                                        │  heartbeat → logs/*.heartbeat.json
                                        │  git merge --ff-only develop + ./test ci gate (TECH-206)
                                        v                                │
                              pueue completion ──► callback.py ──────────┘
                                                   (guard → write_lifecycle → push;
                                                    circuit-breaker; dispatch QA+reflect)
                                                          │
                                                          v
                                                  event_writer.py → Hermes/Telegram

   Side daemons / cron (read-only or kill-only — NEVER write status):
     • heartbeat_reaper   cron */5       — убивает зависшие claude-runner сессии (fail-open)
     • heartbeat_monitor  cron */5       — алерт если orchestrator-heartbeat > 10 мин
     • orchestrator_monitor cron */30    — service alive + circuit-breaker + demote-burst
```

| Компонент | Роль | Детали |
|-----------|------|--------|
| `orchestrator.py` | Main poll-daemon: pull → scan → dispatch | [components.md](components.md#orchestratorpy) |
| `run-agent.sh` | Provider dispatcher + RAM gate (3GB) | [components.md](components.md#run-agentsh) |
| `claude-runner.py` | Agent SDK wrapper, heartbeat, exit_code contract | [components.md](components.md#claude-runnerpy) |
| `callback.py` | **Единственный writer статусов**, guard, circuit-breaker | [status-model.md](status-model.md) |
| `lifecycle.py` | Примитив записи статуса (CAS git-plumbing) | [status-model.md](status-model.md) |
| `db.py` + `schema.sql` | SQLite рантайм-состояние (7 таблиц) | [components.md](components.md#db) |
| `event_writer.py` | События в Hermes (⚠ silent-fail, см. ниже) | [components.md](components.md#event_writerpy) |
| `heartbeat_reaper.py` | Жнец зависших сессий (TECH-198) | [components.md](components.md#heartbeat_reaper) |

---

## §3 Поток задачи (полный жизненный цикл)

```
/spark (или Hermes intake → scan_inbox)
  └─ Создаёт ai/features/SPEC-NNN-*.md + строку в ai/backlog.md
     Клеймит ID через lifecycle.create_initial (CAS, ADR-027) → ai/lifecycle/SPEC-NNN.yaml: queued

orchestrator.py · process_project (каждые ≤5 мин):
  git_pull (ff-only)                              # пропускается пока агент работает
  scan_inbox      → Hermes Status: queued → /spark|/architect|/bughunt|...
  bootstrap_new_specs → создать yaml для новых spec.md без него (safe default=queued)

/dispatcher · пасс раз в 15 мин (~/ops/dispatcher.sh → run-agent.sh claude dispatcher):
  dispatch_summary.py → сводка: слоты, здоровье провайдеров, живые задачи,
    queued/resumed из lifecycle.list_by_status   # SoT = yaml@HEAD, НЕ backlog.md
    + проблемы спеки и `waits on X=status` — `depends_on` ∪ шапка `**AFTER <ID>**` ∪
      backlog `AFTER` (spec_deps.declared; ребро не из YAML → метрика DEP_VIA)
  модель решает: что готово, что починить (allowlist), что пропустить — не больше 2 запусков
  dispatch_one.py <project> <SPEC-NNN> --reason "…"   # единственный глагол
    стены: нет слота · уже живая в pueue (label + spec_id) · нет тела спеки · флот на паузе
    pueue add → run-agent.sh <dir> claude autopilot "/autopilot SPEC-NNN"
    record_dispatch: try_acquire_slot + log_task(branch=<type>/SPEC-NNN) + phase=autopilot
                     + lifecycle in_progress с pueue_id   [BUG-218]

claude-runner.py · /autopilot:
  План → коммиты в feature/SPEC-NNN → git merge --ff-only develop
  Финальный гейт ./test ci (CI-parity, TECH-206): red → reset --hard origin/develop + needs_review
  exit 0 + JSON {task_status: complete | blocked | needs_review}

pueue completion → callback.py (всегда exit 0):
  1. release_slot
  2. finish_task (task_log)
  3. update_project_phase
  4. extract_agent_output → skill / preview / task_status
  5. callback_event.write_event_for_skill → Hermes   ── только qa/reflect/spark;
     событие автопилота здесь НЕ пишется   [TECH-224]
  6. dispatch QA + reflect   ── ТОЛЬКО если task_status == "complete"   [TECH-194 Layer E]
  7. verify_status_sync → (status, reason) | None:
       guard gate_ancestry.find_implementation (branch <type>/<ID> — предок origin/develop
       И принесла allowed-файл; deprecated subject-regex — fallback, TECH-220)
       → lifecycle.write_lifecycle(by="callback")  → done | blocked
       task_status blocked/needs_review перебивает pueue Success → blocked
  7b. callback_event.autopilot_event → Hermes: вердикт есть → status = вердикт Step 7
      (done / blocked + причина); вердикта нет → pueue-статус + «вердикт lifecycle
      недоступен: <why>». Ровно одно событие на прогон автопилота, включая exit≠0   [TECH-224]

QA → ai/qa/*.md   ·   Reflect → ai/reflect/*.md   →  callback → phase=idle
```

**Переходы статуса** (пишет только `callback`/`operator`/`orchestrator`, см. [status-model.md](status-model.md)):

| Переход | Триггер |
|---------|---------|
| `→ queued` | spark `create_initial` / orchestrator bootstrap (safe default) |
| `* → in_progress` | `orchestrator_queue.record_dispatch` (зовёт `dispatch_one.py`) после успешного `pueue add`: `write_lifecycle(..., "in_progress", by="orchestrator", pueue_id=<id>)`. `started_at` ставится на ЛЮБОМ входе в `in_progress`, а не только из `queued`/`resumed` — спека, поднятая из `blocked`, иначе теряла начало навсегда (замер 31.08.2026: 75 done-спек из 183 за две недели без `started_at`) |
| `in_progress → done` | guard видит реализующий коммит на origin/develop |
| `in_progress → blocked` | guard не нашёл реализацию ИЛИ autopilot сигналит blocked/needs_review |
| `blocked → resumed` | оператор (`spec_operator demote --blocked`/правка backlog → resumed) |
| `done` — **терминал** | write-once (Rule 7); откат только `operator` через narrow escape |

До BUG-218 этот переход документировался за `callback` и не выполнялся вовсе: callback
срабатывает на **завершении** pueue-задачи, и в этот момент пишет уже `done`/`blocked`, а не
`in_progress`.

---

## §4 Два контракта (зачем всё это)

Корректная работа оркестратора = два набора инвариантов целы. Их нарушение — это ровно те два
провала, которые жгут: «сломанный статус» и «сгоревшие зря токены».

### Контракт A — целостность статусов («не ломать статус»)

Полностью в [status-model.md](status-model.md#инварианты-статуса). Кратко:

1. **Single-writer per transition.** Не «пишет только callback» — пишут `callback`, `orchestrator`
   (диспатч `→ in_progress` в `record_dispatch` и `reconcile_orphans` → `queued`; reconciliation
   gate, писавший `done`, снят 2026-09-27) и `operator`, но всегда через один и тот же примитив,
   `lifecycle.write_lifecycle(by=<writer>)`, никогда напрямую в yaml. Инвариант — не имя писателя,
   а то, что на каждый переход есть ровно один легитимный путь записи. Writers ограничены
   `{callback, orchestrator, operator, qa, audit, migration}`. `autopilot`/`spark` — **не** writers
   (autopilot сигналит JSON `task_status`).
2. **SoT = yaml @ HEAD.** Истина — `ai/lifecycle/{spec}.yaml` в git-объектах HEAD. Markdown (спека,
   `backlog.md`) — read-only render. Ручная правка WT-yaml невидима (читается HEAD).
3. **Write-once-done (Rule 7, структурно в примитиве).** `done → !done` запрещён всем; escape —
   только `recover_bootstrap_artifact` при точной 4-criteria подписи.
4. **CAS-атомарность.** Запись = приватный `GIT_INDEX_FILE` + pin-HEAD-once + `commit-tree` +
   `update-ref <new> <head_sha>`. Working tree в записи не участвует.
5. **Degrade-closed guard.** Нет/пустой allowlist → `blocked`, не `done`. `done` — только при
   позитивном совпадении на origin/develop.
6. **Mass-demote circuit-breaker.** >3 демоутов/10 мин → пауза группы `claude-runner`.

### Контракт B — дисциплина диспатча («не жечь зря токены»)

Полностью в [components.md](components.md#инварианты-диспатча). Кратко:

1. **Не диспатчить spec, чей lifecycle-статус ≠ queued/resumed** (SoT = yaml@HEAD, не backlog.md) —
   сводка диспетчера показывает только такие.
2. ~~TOCTOU re-check перед `pueue add` (BUG-205)~~ — снят 2026-09-27 с builtin-путём; повторный
   запуск живой спеки держит стена «уже живая в pueue» в `dispatch_one.py`.
3. **Не bootstrap-ить в терминальный статус** — unparsable → `queued`, никогда `done`.
4. **Зависимости видны диспетчеру** — `depends_on`, шапка `**AFTER <ID>**`, backlog-строка
   (BUG-206 + TECH-222; backlog-`AFTER` — deprecated-фолбэк, снимается после 30 дней без
   `deps_via=backlog`) идут в сводку через `spec_deps.declared`; решение за диспетчером.
5. **RAM floor ≥3GB** перед запуском LLM-агента (иначе OOM на полпути = потраченные токены).
6. **Slot discipline + dup-guard** — не диспатчить без слота / дубликат spec_id.
7. **Timeout как hard-limit** (claude 90м / codex 15м / gemini 30м) + heartbeat-reaper добивает зависшие.
8. **exit_code contract (ADR-024)** — post-result Exception не оверрайдит `exit_code=0` (иначе ре-блок готовой спеки).
9. **CI-parity merge-gate (TECH-206)** — не мержить в красный develop.
10. **Fleet pause (TECH-226)** — пока `fleet_pause.active_pause()` открыт, `dispatch_one.py` не
    запускает `claude`-спеки, а `run-agent.sh` выходит exit 75 до вызова API, если что-то всё же
    успело просочиться в pueue.

---

## §5 ADR-индекс оркестратора

> Полные формулировки project-wide ADR — в `.claude/rules/architecture.md`. Здесь —
> оркестратор-специфичные решения и их текущий статус. **Где запись помечена `[SUPERSEDED]`
> — поведение кода уже другое, не верь старой формулировке.**

| ID | Решение | Статус |
|----|---------|--------|
| ADR-017 | SQL только через Python parameterized queries | актуально |
| ADR-018 | Callback status enforcement через **markdown editing** | **[SUPERSEDED by ADR-023]** |
| ADR-021 | Hermes intake gate: `scan_inbox` диспатчит только `Status: queued` | актуально |
| ADR-022 | Hermes — единственный writer `queued` в `ai/inbox/` | актуально |
| ADR-023 | **Lifecycle state SoT = git per-spec YAML.** callback пишет yaml через atomic plumbing, не markdown | актуально (amended by 025) |
| ADR-024 | claude-runner exit_code contract: post-result Exception не оверрайдит exit 0 | актуально |
| ADR-025 | Write-once-done (Rule 7) структурно в `lifecycle.write_lifecycle`; autopilot/spark убраны из writers | актуально |
| ADR-026 | Bootstrap parser safety: column-aware, fail в `queued` не `done` | актуально |
| ADR-027 | Spec-first ID generation через `create_initial` CAS (Kafka pattern) | актуально |
| ADR-028 | Opus 4.8 config alignment: `AUTOPILOT_EFFORT` env (default high) | актуально |
| ARCH-190 | Shadow merge-gate (`gate-daemon.py`), `SHADOW_ONLY_MODE=True` | **[СНЯТ 2026-09-27]** — 34 дня в тени без потребителя, Wave 3 не согласован; `gate_logic.py` остался как общее ядро гейта. См. `docs/2026-09-27-snyatie-relsov-dispetchera.md` |
| TECH-166 | Implementation guard: git-diff verify перед mark-done | актуально (механика переписана — см. ниже) |
| TECH-169 | Circuit-breaker на mass-demote (>3/10мин) | актуально |
| TECH-170 | Guard видит feature-branch коммиты через `--all` | **[SUPERSEDED]** — текущий guard = branch-ancestry gate (`gate_ancestry.find_implementation`, TECH-220), без `--all` |
| TECH-176 | Guard auto-close «already merged before started_at» | **[SUPERSEDED]** — auto-close убран при редизайне guard 2026-05-21 |
| TECH-194 | hooksPath absolute + WT-sync через `checkout HEAD --` + dispatch-gate на task_status | актуально |
| TECH-195 | `lifecycle_audit.py` (14 категорий) + `recover_bootstrap_as_done.py` | актуально |
| TECH-197 | claude-runner graceful timeout 5400s + push-local-before-gate + grace-retry | актуально |
| TECH-198 | Per-session heartbeat + `heartbeat_reaper.py` | актуально |
| TECH-204 | night-reviewer notify cap (10) + confidence filter (medium+) | актуально |
| TECH-206 | CI-parity merge-gate (`./test ci` перед push, needs_review на red) | актуально |
| TECH-220 | Implementation guard: branch-ancestry primary (`gate_ancestry.find_implementation`), subject-regex deprecated fallback, `gate_via` telemetry | актуально |
| TECH-221 | Re-dispatch after a timeout continues the salvaged branch: `gate_ancestry.branch_state()`, `blocked_reason=branch_pushed_not_merged:<N>`, three-way `orchestrator_queue.reconcile()` ("done"\|"continue"\|"fresh"), `CLAUDE_CONTINUE_BRANCH` env | актуально, кроме `reconcile()` и `CLAUDE_CONTINUE_BRANCH` — **сняты 2026-09-27** с builtin-путём; продолжение ветки autopilot находит сам через `git ls-remote` |
| TECH-222 | Dependency edge moves onto lifecycle YAML: `depends_on: [ID]` in the dependent spec's yaml (Spark writes it at claim time via `create_initial`; `lifecycle.set_depends_on` retrofits existing specs). `spec_deps.declared` reads it as SoT (was `orchestrator_queue._spec_deps` until the builtin gate was removed 2026-09-27; the dispatcher's briefing is the reader now), backlog `AFTER` demoted to deprecated fallback logged as `DEP_VIA` (30-day zero-`DEP_VIA` telemetry gate before deletion, same shape as TECH-220's `gate_via`) | актуально |
| TECH-225 | Rate-limit hit recognised structurally: runner exit 5 (`rate_limited`, `runner_ratelimit.decide_exit`, ADR-024-respecting) instead of a bare `exit_code: 1`; callback routes it through `callback_ratelimit.requeue` (`in_progress → queued`, not `blocked`), 3rd requeue of the same spec in 24h escalates to `blocked repeated_rate_limit:<n>`. Fleet-wide dispatch pause added by TECH-226 | актуально (EXP-014 open) |
| TECH-226 | Fleet-wide pause on subscription rate limit: first exit 5 in a closed window opens `scripts/vps/.rate-limited-until` (`runner_ratelimit.on_rejected` → `fleet_pause.set_pause`) and sends exactly one Hermes alert; while open, `run-agent.sh` exits **75** before the `claude)` branch ever calls the API, and `dispatch_one.py` refuses `claude` specs ahead of `pueue add` (the builtin path's copy of that refusal went with the path, 2026-09-27). Callback treats exit 75 as `callback_ratelimit.requeue(paused=True)` — `queued`/`fleet_paused`, never counted toward the 3/24h ceiling. codex/gemini unaffected | актуально (EXP-015 open) |

> ⚠️ **Известный дрейф в in-repo ADR-таблице** (`.claude/rules/architecture.md`): TECH-170/176
> там описаны как актуальные, но текущий код (`gate_ancestry.find_implementation`, TECH-220) их не
> реализует — guard переписан сначала 2026-05-21 на origin/develop subject-gate, затем 2026-08-30
> на branch-ancestry. Подробности — [status-model.md](status-model.md#guard).

---

## §6 Глоссарий

| Термин | Определение |
|--------|-------------|
| **lifecycle yaml** | `ai/lifecycle/{spec}.yaml` — авторитетный статус спеки (SoT). Читается из git HEAD. |
| **callback** | `scripts/vps/callback.py` — единственный writer статусов. Вызывается pueue по завершении задачи. Всегда `exit 0`. |
| **CAS write** | Запись статуса через `commit-tree` + `update-ref <new> <head_sha>` — фейлится если HEAD сдвинулся (compare-and-swap). |
| **write-once-done (Rule 7)** | `done` — терминал; `done → !done` бросает `LifecycleAlreadyDoneError` для всех writers. |
| **degrade-closed** | Нет/пустой allowlist → `blocked`, не `done`. Безопасный отказ. |
| **slot** | Запись в `compute_slots`. Один слот = одна параллельная задача провайдера (2 claude, 1 codex, 1 gemini). |
| **phase** | `project_state.phase` в SQLite: `idle`/`autopilot`/`qa_pending`/... — рантайм, не статус спеки. |
| **task_status** | JSON-сигнал autopilot → callback: `complete`/`blocked`/`needs_review`. Единственный способ autopilot повлиять на статус (он не writer). |
| **reaper** | `heartbeat_reaper.py` — cron-жнец зависших сессий (stale heartbeat + idle CPU → `pueue kill`). |
| **Hermes** | Conversational layer founder↔pipeline. Получатель событий из `event_writer.py`. ⚠ см. [components.md](components.md#event_writerpy) — текущий silent-fail. |
| **Agent SDK** | `claude-agent-sdk` — официальный SDK запуска Claude Code. Skills работают нативно через `setting_sources=["user","project"]`. |
