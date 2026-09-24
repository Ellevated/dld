# Feature: [TECH-226] Флот встаёт на паузу до сброса лимита подписки и присылает один алерт

**Priority:** P1 | **Date:** 2026-09-23 | **Risk:** R1 (все пути запуска Claude на VPS) | **AFTER TECH-225**
**Size:** 8 tasks / 15 files — неделимо: пауза, которую уважает только один путь запуска, не
пауза (диспетчер ходит своим таймером, QA/reflect — из callback, автопилот — из dispatch_one);
сторож в `run-agent.sh` без возврата спеки в очередь снова уводит её в `blocked`.

> **Почему AFTER TECH-225:** пауза ставится по сводке `runner_ratelimit.summary(...)` и exit 5,
> которые вводит TECH-225, и расширяет его `callback_ratelimit.py` и `runner_ratelimit.py`.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

23.09 лимит подписки кончился в 10:31Z (13:31 по Хельсинки) и сбросился в 11:00Z. Флот об этом
не знал и продолжал запускать Claude: прогон за прогоном получал 429 в первые секунды.

| Время (EEST) | Что запустилось в закрытое окно | Итог |
|---|---|---|
| 13:07→13:31 | dowry TECH-526 (autopilot) | exit 1, спека `blocked` |
| 13:21→13:30 | dowry QA BUG-521 | exit 1, отчёта нет |
| 13:30, 13:45 | два прохода диспетчера (`dld-20260923-133021`, `-134521`) | exit 1 оба |
| 13:31 | dowry reflect | exit 1, 1 ход, $0 |

Оповещения не было: Hermes получил «qa failed» с чужим артефактом и не знал, что причина —
лимит (`logs/hermes-wake.log` 10:31:12Z). TECH-225 научит раннер распознавать лимит и
возвращать спеку в очередь; эта спека не даёт флоту стучаться в закрытое окно и говорит о нём
основателю один раз.

Решение основателя (Phase 1): реактивно — пауза после упора, до `resets_at`, один алерт; без
проактивного торможения.

## Context

- Разбор суток: `C:\Users\Oleg\.claude\task-journal\2026-09-23-dld-orch24h.md`.
- Пути запуска Claude на VPS (все идут через `scripts/vps/run-agent.sh` → `claude-runner.py`):
  - автопилот: LLM-диспетчер → `dispatch_one.py` → `pueue add` (`dispatch_one.py:51-103`, `pueue add` на `:74-82`);
    встроенный путь `DISPATCH_MODE=builtin` → `orchestrator_queue.gate_before_pueue_add` (`:109`) —
    сейчас выключен (`orchestrator.py:282`, дефолт `llm`), но обязан уважать паузу;
  - диспетчер: systemd `dispatcher.timer` каждые 15 мин → `~/ops/dispatcher.sh` → `pueue add
    --group dispatcher … run-agent.sh … dispatcher /dispatcher` (проверено на VPS 23.09);
  - QA/reflect: callback Step 6 → `callback_dispatch._pueue_add` → `run-agent.sh`;
  - support-nightly: `~/ops/support-nightly.sh` → `run-agent.sh`.
  Единственное общее место — `run-agent.sh`, ветка `claude)` (`run-agent.sh:71-76`, `exec` на `:75`).
- Circuit breaker (`callback_circuit._pueue_pause/_resume`, TECH-169) ставит на паузу pueue-группу
  `claude-runner`. **Эта спека pueue-группы не трогает**: два независимых «почему пауза» на одном
  булевом состоянии pueue — гонка при снятии (research-devil.md, Hidden Coupling).
- Hermes работает на gpt-5.6-terra, не на подписке Claude — алерт дойдёт и при закрытом окне.

---

## Scope

**In scope:**
1. `fleet_pause.py` (NEW, stdlib): файл-маркер `scripts/vps/.rate-limited-until` (JSON: `until`,
   `until_iso`, `rate_limit_type`, `set_at`, `source`); `set_pause(...) -> bool` (True = окно
   открыто этим вызовом), `active_pause(now=None) -> dict | None`, CLI `--check` (exit 0 — свободно,
   exit 75 — пауза, печатает JSON).
2. Раннер при exit 5 (TECH-225) ставит паузу до `resets_at`; `resets_at` неизвестен → `now + 60 мин`.
   Алерт отправляется **только** если этот вызов открыл окно (маркера не было или он истёк).
3. `run-agent.sh`: для провайдера `claude`, до `exec`, `fleet_pause.py --check`; пауза → JSON
   `{"skipped":"fleet_paused","until":…}` в stderr и **exit 75**, Claude не вызывается.
4. `dispatch_one.py`: четвёртый отказ «физики» — `fleet paused until <iso> (<type>)`, exit 2.
5. Встроенный путь: та же проверка в `orchestrator_queue.gate_before_pueue_add`.
6. `dispatch_summary.py`: верхняя строка брифинга `**PAUSED until <iso> (<type>)** — не диспатчить`.
7. Callback: autopilot с exit 75 → спека в `queued` с причиной `fleet_paused`, **не** считается в
   потолок TECH-225 (`count_requeues_since` считает только решения с причиной `rate_limited`).
8. Алерт: `event_writer.notify(SCRIPT_DIR, "rate_limit", "failed", <текст>)`; текст называет тип
   окна и длительность словами: `five_hour` — «до 14:00 (через 29 мин)», `seven_day` — «до чт 26.09
   11:00 (2 д 14 ч)»; `unknown` — «время сброса неизвестно, повторная проверка через 60 мин».
9. Снятие паузы — само, по времени; ручное — `rm scripts/vps/.rate-limited-until` (runbook).

**Out of scope:**
- Проактивное торможение по `utilization`.
- Отложенный перезапуск QA/reflect, попавших в паузу (они завершаются exit 75 и не
  повторяются — редкий случай, отмечается в эксперименте).
- Интерактивные сессии основателя (делят то же окно; вне оркестратора).
- `~/ops/dispatcher.sh` и `~/ops/support-nightly.sh` (вне репо; оба идут через `run-agent.sh` — сторож их покрывает).

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `grep -rn "run-agent.sh" scripts/vps/*.py` → `dispatch_one.py:67`, `orchestrator_slots._pueue_add` (через `orchestrator_queue`), `callback_dispatch._pueue_add`; вне репо — `~/ops/dispatcher.sh`, `~/ops/support-nightly.sh`.
- `grep -rn "def dispatch\b\|_fail(" scripts/vps/dispatch_one.py` → отказы `:53-71`.
- `grep -rn "def build\|def render" scripts/vps/dispatch_summary.py` → `:172`, `:210`.

### Step 2: DOWN
- `event_writer.notify(project_path, skill, status, message, artifact_rel="")` — `event_writer.py:126-135`.
- TECH-225: `runner_ratelimit.summary(...)["resets_at"]`, `["rate_limit_type"]`; `callback_ratelimit.requeue(...)`.

### Step 3: BY TERM
- `grep -rn "rate-limited-until\|fleet_pause" .` → 0 до спеки.
- `grep -rn "exit 75\|== 75" scripts/vps` → 0 (EX_TEMPFAIL свободен; `run-agent.sh` уже использует 78 для RAM).

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/run-agent.sh` | 71-76 | ветка `claude)` сразу `exec` | modify (сторож) |
| `scripts/vps/dispatch_one.py` | 53-71 | три отказа | modify (+ четвёртый) |
| `scripts/vps/orchestrator_queue.py` | 109 | `gate_before_pueue_add` | modify (+ пауза) |
| `scripts/vps/dispatch_summary.py` | 172-250 | брифинг | modify (строка PAUSED) |

### Step 4: CHECKLIST
- [x] `scripts/vps/tests/` — новые `test_fleet_pause.py`, `test_dispatch_one_pause.py` (у `dispatch_one`/`dispatch_summary` тестов нет вовсе — research-codebase.md Risks 5)
- [x] `tests/integration/test_callback_rate_limit_requeue.py` (из TECH-225) — случай exit 75
- [x] `db/migrations/**` — N/A

### Verification
- [x] Все найденные файлы в Allowed Files

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/fleet_pause.py` — маркер паузы, set/active, CLI --check (NEW)
- `scripts/vps/runner_ratelimit.py` — при exit 5 поставить паузу и отправить алерт, если окно открыто этим вызовом (modify, из TECH-225)
- `scripts/vps/claude-runner.py` — один вызов runner_ratelimit после decide_exit (modify, ≤ 2 строк)
- `scripts/vps/run-agent.sh` — сторож перед exec для claude, exit 75 (modify, 87 LOC)
- `scripts/vps/dispatch_one.py` — четвёртый отказ (modify, 118 LOC)
- `scripts/vps/orchestrator_queue.py` — пауза в gate_before_pueue_add (modify, 373 LOC)
- `scripts/vps/dispatch_summary.py` — строка PAUSED в брифинге (modify, 262 LOC)
- `scripts/vps/callback_ratelimit.py` — exit 75 → queued `fleet_paused`, вне потолка (modify, из TECH-225)
- `scripts/vps/callback.py` — Step 7 направляет exit 75 туда же, куда exit 5 (modify)
- `scripts/vps/tests/test_fleet_pause.py` — маркер, окно, один алерт на N одновременных (NEW)
- `scripts/vps/tests/test_dispatch_one_pause.py` — отказ dispatch_one и строка брифинга (NEW)
- `tests/integration/test_callback_rate_limit_requeue.py` — случай exit 75 (modify, из TECH-225)
- `ai/experiments/2026-09-23-fleet-pause-on-rate-limit.md` — эксперимент (NEW)
- `docs/orchestrator/runbook.md` — «флот на паузе по лимиту»: как увидеть, как снять руками (modify)
- `.claude/rules/dependencies.md` — fleet_pause.py и сторож в run-agent.sh (modify)

**LOC headroom (замерено 2026-09-24, после TECH-225):** `orchestrator_queue.py` 373/400 — проверка
≤ 7 строк, логика в `fleet_pause`; `claude-runner.py` 375/400, здесь ≤ 3 строк (вызов в
`runner_ratelimit`); `callback.py` 365/400 — условие `exit_code in (5, 75)` + kwarg, ≤ 3 строк;
`runner_ratelimit.py` 105, `callback_ratelimit.py` 71, `dispatch_one.py` 118, `dispatch_summary.py` 262.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

N/A — в DLD нет `ai/blueprint/system-blueprint/`. Домен: запуск прогонов оркестратора.

---

## Historical Risks

<!-- lessons-binding v1 -->

none — `ai/lessons/` пуст. Прецедент конфликта пауз: circuit breaker TECH-169 управляет pueue-группой
`claude-runner`; эта спека её не трогает намеренно.

---

## Approaches

### Approach 1: файл-маркер + сторож в `run-agent.sh` + отказ в точках диспатча
**Source:** research-codebase.md (`.orchestrator-heartbeat` — образец файла-состояния рядом со скриптами), research-devil.md (EC-4, EC-5, Hidden Coupling).
**Summary:** один источник («закрыто до X»), три читателя: сторож на единственном общем пути
запуска и два диспетчера, чтобы не плодить заведомо пустые задачи.
**Pros:** закрывает и диспетчер, и QA/reflect, и support-nightly без правки `~/ops/*`; не трогает
pueue-группы → не конфликтует с circuit breaker; снимается само по времени.
**Cons:** задачи, уже стоявшие в pueue до паузы, стартуют и сразу выходят с 75 (дёшево, 0 токенов).

### Approach 2: `pueue pause --group claude-runner --group dispatcher` до `resets_at`, возобновление оркестратором
**Cons:** гонка с circuit breaker за одно состояние группы; кто-то обязан снять паузу (демон должен
быть жив); SIGSTOP бегущих задач без `--wait`.

### Selected: 1

---

## Design

### Как будет
```
claude-runner (exit 5, TECH-225)
   └─ runner_ratelimit.on_rejected(rl, source=f"{project}:{skill}")
        ├─ until = rl.resets_at or now+3600
        ├─ opened = fleet_pause.set_pause(until, rl.rate_limit_type or "unknown", source)
        └─ opened → event_writer.notify(SCRIPT_DIR, "rate_limit", "failed", text)

run-agent.sh (claude):  rc=0; "$VENV_PY" fleet_pause.py --check >&2 || rc=$?; [[ $rc -eq 75 ]] && exit 75
                        (fail-open: любой другой rc — запуск идёт дальше; см. Drift Log D5)
dispatch_one.dispatch:  p = fleet_pause.active_pause(); if p: return _fail(f"fleet paused until …")
orchestrator_queue.gate_before_pueue_add: то же → не диспатчить
dispatch_summary.build/render: summary["paused"] = active_pause() → верхняя строка
callback Step 7: autopilot и exit_code in (5, 75) → callback_ratelimit.requeue(..., paused=exit_code == 75)
```

**`set_pause`** атомарна: запись во временный файл + `os.replace`. «Окно открыл этот вызов» =
маркера не было или его `until` в прошлом; если маркер активен, `until` продлевается до большего из
двух, алерт не шлётся. Одновременные вызовы: создание маркера — через `os.open(O_CREAT|O_EXCL)`
временного lock-файла `.rate-limited-until.lock` (удаляется в `finally`); проигравший повторяет
проверку «активен ли маркер» и не алертит. Кроссплатформенно (тесты идут и на Windows).

**`active_pause`** читает маркер; битый JSON → считается отсутствующим (лог WARNING) — сторож
никогда не останавливает флот из-за мусора в файле.

**Сторож в `run-agent.sh`** стоит после проверки RAM и `PROJECT_DIR`, внутри ветки `claude)` до
`exec`. Exit 75 = `EX_TEMPFAIL` (рядом с уже используемым 78 для RAM). Кавычки на всех переменных,
`set -euo pipefail` не нарушается (`|| rc=$?`).

### Database Changes
Нет.

---

## Drift Log

**Checked:** 2026-09-24, worktree `.worktrees/TECH-226` after TECH-225 was merged (`eba410c5`).
**Result:** light drift, fixed in place. Nothing is heavy: every file, function and signature the spec leans on exists.

| # | Spec assumed | Reality | Action |
|---|---|---|---|
| D1 | `dispatch_one.py:52-77`, refusals `:56-71`; `run-agent.sh:69-73` | refusals `:53-71`, `pueue add` `:74-82`; `claude)` branch `:71-76`, `exec` `:75` | references fixed above |
| D2 | `claude-runner.py` ≈382 LOC | 375 LOC; `callback.py` 365; `orchestrator_queue.py` 373 (matches) | LOC headroom line updated |
| D3 | Verify command `bash scripts/check-loc-limit.sh` | the gate is `scripts/vps/check-loc-limit.sh` (CI `ci.yml:108`) | fixed in Verify Command |
| D4 | `on_rejected` is called in `run_task` right after `decide_exit` (`claude-runner.py:294-295`) | `test_runner_ratelimit.py::test_rate_limit_then_sdk_exception_exits_5` runs `run_task` and ends in exit 5. A call there would write the real `scripts/vps/.rate-limited-until` and call the real `event_writer.notify`, which wakes Hermes on the VPS, every time the suite runs. That test file is not in Allowed Files | the call moves to `main()` after `asyncio.run` (`:367`). Only a real process reaches `main()`, and no test calls it (grep `\.main\(` in `test_claude_runner*` → 0) |
| D5 | the guard is `fleet_pause.py --check \|\| { rc=$?; [[ $rc -eq 75 ]] && exit 75; }` | under `set -e` the `{…}` group is the last command of the `\|\|` list, so any rc other than 75 (a traceback, a broken venv) returns 1 from the group and **stops every claude launch with exit 1** | fail-open form: `rc=0; … \|\| rc=$?; if [[ $rc -eq 75 ]]; then exit 75; fi` |
| D6 | `requeue(project_path, spec_id, pueue_id)` cannot say why it is requeuing | `count_requeues_since` already filters `reason = 'rate_limited'` (`db_decisions.py:66`), and the TECH-225 test EC-10 already puts in a `fleet_paused` row and checks that it is not counted | add keyword `paused: bool = False` to `requeue`; `paused=True` writes reason `fleet_paused`, does not read the counter, does not escalate |
| D7 | pause refuses dispatch for all providers | the marker records the **Claude subscription** window, and codex/gemini have nothing to do with it. The `run-agent.sh` guard is already claude-only | `dispatch_one` and `gate_before_pueue_add` refuse only when `provider == "claude"`; the briefing line says the pause is claude-only |
| D8 | exit 75 reaches callback | confirmed: pueue fills `{{ exit_code }}` since 2026-09-01 (`callback-debug.log` shows `exit_code=124/4/1`). With no run log, `runner_exit_code` would return None, so the pueue argument is the only source, and it works | none |
| D9 | — | QA/reflect that exit 75 still reach callback Step 5 → `write_event_for_skill` → Hermes «qa failed» (`callback_event.py:60`). That is the 23.09 noise from Why, and it is one wake per paused QA | Task 6 skips Step 5 when `exit_code == 75` (condition change, 0 new lines) |
| D10 | — | `scripts/vps/.rate-limited-until` is not in `.gitignore` (`:39-51` ignore `.orchestrator-heartbeat` and similar). `.gitignore` is not an Allowed File | warning only: while a pause is active, the marker shows as untracked in the VPS main checkout. It does not affect `git pull` or the worktrees |

Allowlist block untouched (autopilot already started). No `template/` counterparts: `scripts/vps/*` exists
only in root, and `rules/dependencies.md` is deliberately root-specific (`template-sync.md:97`), so no sync task.

## Implementation Plan

### Research Sources
- `scripts/vps/orchestrator.py:349-354` — state file next to the scripts (`.orchestrator-heartbeat`)
- `scripts/vps/event_writer.py:138-168` — `notify_circuit_event`: system alert with `project_path = scripts/vps`
- `scripts/vps/tests/conftest.py:10-37` — `scripts/vps` is on `sys.path`, fixtures `isolated_db` / `seed_project`
- No external research needed: stdlib only (`os.open(O_CREAT|O_EXCL)`, `os.replace`, `zoneinfo`).

**Invariant for the whole plan:** every reader calls `fleet_pause.active_pause()` **as a module attribute**, and
`fleet_pause` reads the module global `MARKER` **at call time** (never as a default argument).
Tests move the marker with a single `monkeypatch.setattr(fleet_pause, "MARKER", tmp_path / ".rate-limited-until")`.

### Task 1: fleet_pause.py — marker, window, CLI
**Type:** code
**Files:**
- Create: `scripts/vps/fleet_pause.py` (~90 LOC, stdlib only: json, logging, os, sys, time, pathlib)
- Create: `scripts/vps/tests/test_fleet_pause.py`

**Context:** the single source of «closed until X». `run-agent.sh` runs it on every claude launch, so it must not
import `db` or the SDK.

**Steps:**
1. Tests (red: `ModuleNotFoundError: fleet_pause`):
   - `test_set_pause_opens_window` (EC-1): `set_pause(now+1800, "five_hour", "x", now=now) is True`, `active_pause(now=now)["until"] == now+1800`
   - `test_repeat_in_open_window_does_not_reopen_or_shrink` (EC-2): a second `set_pause(now+1200, …)` → `False`, `until` is still `now+1800`. A third call with `now+2400` → `False`, `until == now+2400`
   - `test_expired_marker_is_absent_and_reopens` (EC-3): marker with `until = now-1` → `active_pause(now=now) is None`, `set_pause(now+600, …) is True`
   - `test_garbage_marker_is_absent_with_warning` (EC-4): `MARKER.write_text("{not json")` → `active_pause() is None`, `caplog` has a WARNING
   - `test_cli_check` (EC-5): `main(["--check"])` → `0` with no marker; with an active marker → `75`, and `capsys` stdout is JSON with `skipped == "fleet_paused"` and `until`
2. `pytest scripts/vps/tests/test_fleet_pause.py -v` → red.
3. Implementation:
   - `SCRIPT_DIR = Path(__file__).resolve().parent`; `MARKER = SCRIPT_DIR / ".rate-limited-until"`; `EX_TEMPFAIL = 75`
   - `active_pause(now: float | None = None) -> dict | None` — read `MARKER`. Missing file → None. JSON/`KeyError`/`ValueError` → `log.warning` + None. `until <= now` → None
   - `set_pause(until: float, rate_limit_type: str, source: str, now: float | None = None) -> bool`:
     - `until <= now` → False, nothing written
     - the whole «read → decide → write» runs under the lock file `MARKER.parent / (MARKER.name + ".lock")`, taken with `os.open(O_CREAT|O_EXCL|O_WRONLY)` and retried up to ~2 s at 0.02 s steps. If the lock is older than 30 s it is stale: unlink and retry. Lock not taken → `log.warning`, return False. The lock is unlinked in `finally`
     - under the lock: `cur = active_pause(now)`. If `cur` exists, write only when `until > cur["until"]`, and return False. If `cur` is None, write and return True
     - write = `json.dumps({until, until_iso (UTC isoformat), rate_limit_type, set_at, source})` to `MARKER.name + ".tmp"`, then `os.replace`
   - `main(argv: list[str]) -> int`: `--check` → prints `{"skipped":"fleet_paused", **pause}` and returns 75, otherwise 0. `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`
4. `pytest scripts/vps/tests/test_fleet_pause.py -v` → 5 passed.

**Acceptance:** EC-1, EC-2, EC-3, EC-4, EC-5.

### Task 2: the runner sets the pause and alerts once
**Type:** code
**Files:**
- Modify: `scripts/vps/runner_ratelimit.py` (append after `decide_exit`, `:90-105`; docstring `Uses/Used by` gets `fleet_pause, event_writer`)
- Modify: `scripts/vps/claude-runner.py:367-371` (`main()`, between `asyncio.run` and `print`)
- Test: `scripts/vps/tests/test_fleet_pause.py`

**Context:** only the call that opens the window sends the alert. N parallel runs hitting 429 must produce exactly one alert.

**Steps:**
1. Tests (red: `AttributeError: on_rejected`). `event_writer.notify` is replaced by a counter through
   `monkeypatch.setattr(runner_ratelimit.event_writer, "notify", …)`:
   - `test_five_threads_one_alert` (EC-6): `threading.Barrier(5)`, 5 threads call `on_rejected({"resets_at": now+1800, "rate_limit_type": "five_hour"}, "p:autopilot")` → counter `== 1`, marker `until == now+1800`
   - `test_unknown_reset_pauses_one_hour` (EC-7a): `resets_at=None`, `now=` fixed → `active_pause()["until"] == now+3600`, alert text contains `время сброса неизвестно`
   - `test_seven_day_text_has_weekday_and_days` (EC-7b): `rate_limit_type="seven_day"`, `resets_at = now + 2*86400 + 14*3600` → text contains `2 д 14 ч` and matches `r"(пн|вт|ср|чт|пт|сб|вс) \d\d\.\d\d"`
2. `pytest scripts/vps/tests/test_fleet_pause.py -v` → 3 red.
3. Implementation in `runner_ratelimit.py`:
   - `import event_writer`, `import fleet_pause` at module level (both stdlib-only, never import the SDK, and the split line stays intact)
   - `on_rejected(rl: dict, source: str, now: float | None = None) -> None`: `until = rl.get("resets_at") or now + 3600`; `opened = fleet_pause.set_pause(until, rl.get("rate_limit_type") or "unknown", source, now=now)`; `opened` → `event_writer.notify(str(fleet_pause.SCRIPT_DIR), "rate_limit", "failed", _alert_text(...))`. **The whole body sits in `try/except Exception` → `logger.warning`.** A failed alert must not turn exit 5 into a crashed `main()` and exit 1: callback would read that as `blocked`
   - `_alert_text(until, rate_limit_type, known: bool, now) -> str`: the time is local `Europe/Helsinki` (`zoneinfo`; on `ZoneInfoNotFoundError`, e.g. Windows without tzdata, fall back to UTC). A different day adds `«<пн..вс> DD.MM »` before `HH:MM`. The duration is written in words (`N д M ч` / `N ч M мин` / `N мин`). The text names `rate_limit_type`, «флот на паузе до …» and «снять: rm scripts/vps/.rate-limited-until». When the reset time is unknown: «время сброса неизвестно, повторная проверка через 60 мин»
4. `claude-runner.py`, after `result = asyncio.run(...)` (`:367`): `if result["exit_code"] == 5:` → `runner_ratelimit.on_rejected(result["rate_limit"], f"{Path(project_dir).name}:{skill}")`. That is ≤3 lines, and nothing else in the file changes.
5. `pytest scripts/vps/tests/test_fleet_pause.py scripts/vps/tests/test_runner_ratelimit.py -v` → green. After that, `git status --short scripts/vps` must not show `.rate-limited-until` (proves D4: the runner test does not reach `on_rejected`). Then `bash scripts/vps/check-loc-limit.sh` → `LOC limit OK`.

**Acceptance:** EC-6, EC-7. `claude-runner.py` ≤ 378 LOC.

### Task 3: guard in run-agent.sh
**Type:** code
**Files:**
- Modify: `scripts/vps/run-agent.sh:74-75` (between the `VENV_PY` check and `exec`, inside `claude)`)

**Context:** the only path shared by the dispatcher, QA/reflect, support-nightly and autopilot.

**Steps:**
1. Insert 3-4 lines: `rc=0`; `"$VENV_PY" "${SCRIPT_DIR}/fleet_pause.py" --check >&2 || rc=$?`; `if [[ $rc -eq 75 ]]; then exit 75; fi`.
   Any other `rc` → continue with `exec` (fail-open, D5). Quote every variable; `set -euo pipefail` is unchanged.
2. `bash -n scripts/vps/run-agent.sh` → exit 0. The codex/gemini branches are untouched.

**Acceptance:** EC-8 is checked on the VPS with probe AV-F1 (the script calls the production `venv/bin/python3`, so a local test cannot reproduce it honestly).

### Task 4: dispatch refusal (LLM path and builtin path)
**Type:** code
**Files:**
- Modify: `scripts/vps/dispatch_one.py:63-64` (after `provider = …`, before the slot check); docstring `:13-18` «Three refusals» → «Four», plus the reason; `Uses:` gets `fleet_pause`
- Modify: `scripts/vps/orchestrator_queue.py:171-175` (after `resolve_provider`, before `get_available_slots`); `import fleet_pause  # noqa: E402` next to `:30-34`
- Create: `scripts/vps/tests/test_dispatch_one_pause.py`

**Steps:**
1. Tests (red: dispatch goes further, gate returns a tuple):
   - `test_dispatch_one_refuses_when_paused` (EC-9): `isolated_db`, `db.seed_projects_from_json([{project_id:"p", path:str(tmp_path), provider:"claude", …}])`, spec body `tmp_path/ai/features/TECH-1-x.md`, active pause → `dispatch_one.dispatch("p","TECH-1","autopilot",None,"")  == 2`, and `json.loads(capsys stdout)["reason"].startswith("fleet paused until")`
   - `test_dispatch_one_pause_is_claude_only`: same setup, `provider="codex"`, `monkeypatch.setattr(dispatch_one.db, "get_available_slots", lambda p: 0)` → reason `== "no free codex slot"`. This refuses before `pueue add`, so real pueue is never called
   - `test_builtin_gate_refuses_when_paused` (EC-10): spec with `## Allowed Files` + `<!-- callback-allowlist v1 -->` + a bullet (as in `test_orchestrator.py:1486-1502`), `patch("orchestrator_queue.db.get_available_slots", return_value=1)` and `get_project_state → {"provider":"claude"}`, active pause → `gate_before_pueue_add(...) is None`, and `caplog` contains `fleet paused`
2. `pytest scripts/vps/tests/test_dispatch_one_pause.py -v` → red.
3. `dispatch_one`: `if provider == "claude" and (pause := fleet_pause.active_pause()):` → `return _fail(f"fleet paused until {pause['until_iso']} ({pause['rate_limit_type']})")`. `orchestrator_queue`: the same condition → `log.info("skip dispatch: %s fleet paused until %s (%s)", …)`; `return None`. ≤7 lines, final count ≤ 380.
4. `pytest scripts/vps/tests/test_dispatch_one_pause.py scripts/vps/tests/test_orchestrator.py -q` → green.

**Acceptance:** EC-9, EC-10.

### Task 5: PAUSED line in the dispatcher briefing
**Type:** code
**Files:**
- Modify: `scripts/vps/dispatch_summary.py:201-207` (`build` return dict gets `"paused": fleet_pause.active_pause()`), `:212` (`render`, right after `["# Dispatch briefing", ""]`); import next to `:36-38`; `Uses:` in the docstring
- Test: `scripts/vps/tests/test_dispatch_one_pause.py`

**Steps:**
1. Test `test_briefing_leads_with_paused` (EC-11): `isolated_db`, active pause, `out = dispatch_summary.render(dispatch_summary.build([]))`. The non-empty lines of `out`: `[0] == "# Dispatch briefing"`, `[1].startswith("**PAUSED until")`. Control: without a marker, no line contains `PAUSED`.
2. Red → implementation: `if p := summary.get("paused"):` → `out += [f"**PAUSED until {p['until_iso']} ({p['rate_limit_type']})** — не диспатчить claude-спеки", ""]` before the provider lines. Use `.get`, so an old/hand-built summary without the key still renders.
3. `pytest scripts/vps/tests/test_dispatch_one_pause.py scripts/vps/tests/test_spec_deps.py -q` → green.

**Acceptance:** EC-11.

### Task 6: callback — exit 75 goes back to the queue, outside the ceiling
**Type:** code
**Files:**
- Modify: `scripts/vps/callback_ratelimit.py:41-66` (`requeue` signature + branch; constant `PAUSED_REASON = "fleet_paused"` next to `:38`; docstring `Used by` → `exit_code in (5, 75)`)
- Modify: `scripts/vps/callback.py:290` (Step 5) and `:318-321` (Step 7)
- Test: `tests/integration/test_callback_rate_limit_requeue.py`

**Context:** a spec whose task was already queued in pueue before the pause returns to `queued`, not `blocked`, and does not use up the 3/24h ceiling from TECH-225.

**Steps:**
1. Tests (real git + sqlite, same fixtures; `_run_main_exit5` is generalised to a code argument, or a sibling `_run_main_exit75` is added with argv `…, "Failed", "75"`):
   - `test_exit75_requeues_without_counting` (EC-12): `in_progress` → after `main()`: `status == "queued"`, `blocked_reason == "fleet_paused"`, there is a row `verdict='requeue', reason='fleet_paused'`, `db.count_requeues_since("proj", spec_id, 24) == 0`
   - `test_exit75_ignores_ceiling`: seed 2 rows `requeue/rate_limited` → exit 75 → `queued` (not `blocked repeated_rate_limit:3`)
   - `test_qa_exit75_sends_no_event` (D9): `task_log.skill='qa'`, `extract_agent_output → ("qa","","")`, exit 75 → the `event_writer.notify` counter `== 0`
2. `pytest tests/integration/test_callback_rate_limit_requeue.py -v` → the 3 new tests are red. Today exit 75 → `verify_status_sync` → `blocked`.
3. `requeue(project_path, spec_id, pueue_id, *, paused: bool = False)`: `paused` → `status, reason = "queued", PAUSED_REASON` + `callback_circuit._record(..., "requeue", reason)`, and the `count_requeues_since` block (`:53-64`) is skipped. `paused=False` behaves exactly as today (EC-8/9/11 of TECH-225 stay green).
4. `callback.py:318`: `if sid and exit_code in (5, 75):` → `callback_ratelimit.requeue(project_path, sid, <pueue_id as now>, paused=exit_code == 75)`. `:290`: `if project_path and exit_code != 75:`. That is ≤3 new lines. Step 7b (`autopilot_event`) is unchanged: the event carries `queued/fleet_paused`.
5. `pytest tests/integration/test_callback_rate_limit_requeue.py tests/ -q` → green.

**Acceptance:** EC-12.

### Task 7: experiment
**Type:** docs
**Files:**
- Create: `ai/experiments/2026-09-23-fleet-pause-on-rate-limit.md` — front matter follows `2026-09-23-rate-limit-requeue.md:1-13`

**Steps:** `id: EXP-015` (last is EXP-014), `opened: 2026-09-24`, `status: open`,
`check_after_runs: 40`, `check_after_date: 2026-10-15`, `verdict:` empty. Metric, baseline and expected are the ones from the
previous draft of this task: for each window, starts with 429 after the first hit and the number of alerts (`grep "rate_limit failed" logs/hermes-wake.log`).
Baseline 23.09: window 10:31–11:00Z, 5 runs with exit 1, 0 alerts. Expected: 0 API starts after the first hit, 1 alert per window. No event by the date → `inconclusive`.
Body: dispatcher still starting inside the window → the guard is on the wrong path (`~/ops/dispatcher.sh`); >1 alert → race in `set_pause`; QA/reflect that hit the pause are not retried (Out of scope, count them).
`python scripts/check-experiments.py` → exit 0.

**Acceptance:** DoD Technical «check-experiments exit 0».

### Task 8: docs
**Type:** docs
**Files:**
- Modify: `docs/orchestrator/runbook.md` — new `## Сценарий 8: Флот на паузе по лимиту подписки (TECH-226)` before `## Остановка` (`:233`)
- Modify: `.claude/rules/dependencies.md` — new section `## scripts/vps/fleet_pause.py` (Uses: stdlib; Used by: run-agent.sh guard, runner_ratelimit.on_rejected, dispatch_one, orchestrator_queue.gate_before_pueue_add, dispatch_summary.build); the `run-agent.sh` Uses row gets «fleet_pause.py --check → exit 75»; the `runner_ratelimit.py` row in the claude-runner table gets `on_rejected`; the `callback_ratelimit.py` row gets `paused=True → fleet_paused, outside the ceiling`

**Steps:** runbook section contents: symptoms (`cat scripts/vps/.rate-limited-until`, the PAUSED line in `dispatch_summary.py`, `Failed (75)` in `pueue status`, `fleet_paused` in lifecycle); manual lift (`rm scripts/vps/.rate-limited-until`); the pause does NOT touch pueue groups (the circuit breaker is separate); codex/gemini keep running. Verify: `grep -n "rate-limited-until" docs/orchestrator/runbook.md .claude/rules/dependencies.md` → ≥1 hit in each.

**Acceptance:** DoD «ручное снятие описано в runbook».

### Execution Order
1 → 2 (needs `fleet_pause`) → 3 (needs the CLI from 1) → 4 → 5 (4 and 5 share the test file; do them in sequence) → 6 (independent of 2-5; after 1 only for consistency) → 7 → 8.
Final gate: the Verify Command block in full (`pytest tests/ scripts/vps/tests/ -q`, `bash -n`, `bash scripts/vps/check-loc-limit.sh`, ruff 0.16.1, `check-experiments`).

---

## Flow Coverage Matrix (REQUIRED)

| # | Шаг | Covered by Task | Status |
|---|-----|-----------------|--------|
| 1 | Прогон упёрся в лимит, exit 5 | - | TECH-225 |
| 2 | Раннер открывает окно паузы и шлёт один алерт | Task 1, 2 | ✓ |
| 3 | Новые запуски (диспетчер, QA, reflect, support) выходят 75 без вызова API | Task 3 | ✓ |
| 4 | LLM-диспетчер и встроенный путь не диспатчат, брифинг говорит PAUSED | Task 4, 5 | ✓ |
| 5 | Спека, стартовавшая в окно, возвращается в очередь без счёта в потолок | Task 6 | ✓ |
| 6 | После `until` пауза снимается сама | Task 1 | ✓ |
| 7 | Замер и вердикт | Task 7 | ✓ |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Окно открыто | `set_pause(now+1800, "five_hour", "x")` на чистом каталоге | `True`; `active_pause()` → `until` = переданное | deterministic | — | P0 |
| EC-2 | Повтор в открытом окне | второй `set_pause(now+1200, …)` | `False`; `until` не уменьшился | deterministic | devil EC-4 | P0 |
| EC-3 | Окно истекло | маркер с `until` в прошлом | `active_pause()` → `None`; новый `set_pause` → `True` | deterministic | — | P0 |
| EC-4 | Мусор в маркере | маркер `{not json` | `active_pause()` → `None`, WARNING в логе | deterministic | devil EC-3 | P1 |
| EC-5 | CLI | `python fleet_pause.py --check` при активной паузе / без | exit 75 + JSON / exit 0 | deterministic | — | P0 |
| EC-6 | Один алерт на N | 5 потоков одновременно вызывают `on_rejected` с одинаковым `resets_at` | ровно 1 вызов `event_writer.notify` | deterministic | devil EC-4 | P0 |
| EC-7 | Неизвестный сброс и недельное окно | `resets_at=None` / `rate_limit_type="seven_day"`, `resets_at` через 2 д 14 ч | `until = now+3600`, текст «время сброса неизвестно»; текст с днём недели и «2 д 14 ч» | deterministic | devil EC-2, EC-3 | P1 |
| EC-8 | Сторож в run-agent.sh | маркер активен, `run-agent.sh <dir> claude autopilot /autopilot X` | exit 75, `claude-runner.py` не запускался (нет нового run-лога) | integration | incident 23.09 | P0 |
| EC-9 | dispatch_one | активная пауза | exit 2, JSON `reason` начинается с `fleet paused until` | deterministic | — | P0 |
| EC-10 | Встроенный путь | активная пауза, `gate_before_pueue_add(...)` | не пускает, причина в логе | deterministic | devil (DISPATCH_MODE dual) | P1 |
| EC-11 | Брифинг | активная пауза | первая содержательная строка `render()` — `**PAUSED until …` | deterministic | — | P1 |
| EC-12 | Callback, exit 75 | реальный репо, спека `in_progress`, exit 75 | lifecycle `queued`, причина `fleet_paused`, `count_requeues_since` не вырос | integration | devil EC-7 | P0 |

### Coverage Summary
- Deterministic: 10 | Integration: 2 | LLM-Judge: 0 | Total: 12

### TDD Order
1. EC-1..EC-5 → Task 1
2. EC-6, EC-7 → Task 2
3. EC-9, EC-10 → Task 4; EC-11 → Task 5
4. EC-12 → Task 6; EC-8 → Task 3 / AV-F1

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | CLI в боевом venv | `cd ~/projects/dld/scripts/vps && venv/bin/python3 fleet_pause.py --check; echo $?` | `0` (паузы нет) | 30s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Сторож на VPS | `venv/bin/python3 -c "import fleet_pause,time; fleet_pause.set_pause(time.time()+120,'probe','manual')"` | `pueue add --group dispatcher --label pause-probe -- ~/projects/dld/scripts/vps/run-agent.sh ~/projects/dld claude dispatcher /dispatcher`; затем `pueue status` | задача `Failed (75)` за секунды, нового `dld-*.log` нет; маркер удалить `rm .rate-limited-until` |
| AV-F2 | Первое боевое окно | ближайший упор в лимит | `hermes-wake.log`, pueue, lifecycle | один алерт, стартов с 429 внутри окна нет |

### Verify Command (copy-paste ready)

```bash
pip install -r scripts/vps/requirements.txt
pytest scripts/vps/tests/test_fleet_pause.py scripts/vps/tests/test_dispatch_one_pause.py tests/integration/test_callback_rate_limit_requeue.py -v
pytest tests/ scripts/vps/tests/ -q
bash -n scripts/vps/run-agent.sh
bash scripts/vps/check-loc-limit.sh
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
- [ ] Первый упор открывает окно паузы до `resets_at` (или +60 мин), алерт ровно один
- [ ] Внутри окна ни один путь не вызывает Claude API; спеки возвращаются в очередь вне потолка
- [ ] Пауза снимается сама; ручное снятие описано в runbook
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] EC-1..EC-12 pass
- [ ] `pytest tests/ scripts/vps/tests/ -q` зелёные

### Acceptance Verification
- [ ] AV-S1, AV-F1 pass (маркер после пробы удалён); AV-F2 — при первом боевом окне

### Technical
- [ ] ruff 0.16.1; LOC-гейт; `bash -n run-agent.sh`; check-experiments exit 0
- [ ] No regressions

---

## Autopilot Log

Planner (2026-09-24): plan re-validated, 8 tasks, 10 drift items auto-fixed (D1–D10): guard fail-open (D5), claude-only pause (D7), `requeue(paused=)` (D6), Step 5 event skipped on exit 75 (D9), `on_rejected` called from `main()` not `run_task` (D4).

### Task 1/8: fleet_pause.py — 2026-09-24
- Coder: completed (2 files) · Tester: passed 5/5 · Spec compliance: matches EC-1..5 · Code Quality: approved (1 advisory) · Commit: 36745e2f

### Task 2/8: on_rejected + claude-runner call — 2026-09-24
- Coder: completed (3 files) · Tester: passed (372 incl. venv SDK-gated runner tests; marker not leaked) · Spec compliance: matches EC-6, EC-7 · Code Quality: approved (1 advisory) · Commit: 2c6a3846

### Task 3/8: run-agent.sh guard — 2026-09-24
- Coder: completed (1 file) · Tester: bash -n + /tmp probe (claude → rc 75, runner not started; no marker → runs; broken check → fail-open; codex unaffected) · Spec compliance: matches · Code Quality: approved · Commit: 918d7826
- Local Verify: EC-8/AV-F1 require production venv + pueue on VPS — deferred to QA

### Task 4-5/8: dispatch refusal + PAUSED briefing line — 2026-09-24
- Coder: completed (4 files) · Tester: passed 178 · Spec compliance: matches EC-9..11 · Code Quality: approved (advisory: pre-existing bare except orchestrator_queue.py:92) · Commit: d66b214c

### Task 6/8: callback exit 75 → queued/fleet_paused — 2026-09-24
- Coder: completed (3 files) · Tester: passed 228 (venv) + mutation check (reverting callback.py → 3 new tests red) · Spec compliance: matches EC-12 · Code Quality: approved (advisory: pre-existing bare excepts callback.py:113,362) · Commit: 1477a7dd

### Task 7/8: EXP-015 — Coder: completed · check-experiments exit 0 · Commit: a43478ef
### Task 8/8: runbook Сценарий 8 + dependencies.md — Coder: completed · Commit: a26d1cf0

### PHASE 3 — 2026-09-24
- Final test: CI_PARITY_UNAVAILABLE (no ./test in dld) → `pytest tests/ scripts/vps/tests/` once (venv): 1250 passed, 1 failed, 3 skipped. The failure is `test_worktree_hook_blocks.py::test_installer_leaves_guard_active_from_relative_legacy_state` — env leak of `CLAUDE_CURRENT_SPEC_PATH` from the runner (passes with it unset; SIGNAL-2026-09-24-0010/0400), not this spec.
- Gates: ruff 0.16.1 clean, bash -n ok, LOC OK (orchestrator_queue 380, claude-runner 378, callback 369), check-experiments OK, prompt-integrity clean.
- Exa Verify: no issues (O_CREAT|O_EXCL lock + os.replace is the standard local-FS pattern; stale-lock break at 30 s is safe for a ms-long critical section)
- Documenter: completed — components.md, status-model.md, README.md (9b4bd9c6)
- Post-Deploy Verify: skip (DEPLOY_URL=local-only); AV-S1/AV-F1 on VPS → QA
