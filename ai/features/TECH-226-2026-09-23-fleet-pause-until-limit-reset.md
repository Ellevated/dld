# Feature: [TECH-226] Флот встаёт на паузу до сброса лимита подписки и присылает один алерт

**Priority:** P1 | **Date:** 2026-09-23 | **Risk:** R1 (все пути запуска Claude на VPS) | **AFTER TECH-225**
**Size:** 7 tasks / 15 files — неделимо: пауза, которую уважает только один путь запуска, не
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
  - автопилот: LLM-диспетчер → `dispatch_one.py` → `pueue add` (`dispatch_one.py:52-77`);
    встроенный путь `DISPATCH_MODE=builtin` → `orchestrator_queue.gate_before_pueue_add` (`:109`) —
    сейчас выключен (`orchestrator.py:282`, дефолт `llm`), но обязан уважать паузу;
  - диспетчер: systemd `dispatcher.timer` каждые 15 мин → `~/ops/dispatcher.sh` → `pueue add
    --group dispatcher … run-agent.sh … dispatcher /dispatcher` (проверено на VPS 23.09);
  - QA/reflect: callback Step 6 → `callback_dispatch._pueue_add` → `run-agent.sh`;
  - support-nightly: `~/ops/support-nightly.sh` → `run-agent.sh`.
  Единственное общее место — `run-agent.sh`, ветка `claude)` (`run-agent.sh:69-73`).
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
- `grep -rn "def dispatch\b\|_fail(" scripts/vps/dispatch_one.py` → отказы `:56-71`.
- `grep -rn "def build\|def render" scripts/vps/dispatch_summary.py` → `:172`, `:210`.

### Step 2: DOWN
- `event_writer.notify(project_path, skill, status, message, artifact_rel="")` — `event_writer.py:126-135`.
- TECH-225: `runner_ratelimit.summary(...)["resets_at"]`, `["rate_limit_type"]`; `callback_ratelimit.requeue(...)`.

### Step 3: BY TERM
- `grep -rn "rate-limited-until\|fleet_pause" .` → 0 до спеки.
- `grep -rn "exit 75\|== 75" scripts/vps` → 0 (EX_TEMPFAIL свободен; `run-agent.sh` уже использует 78 для RAM).

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/run-agent.sh` | 67-74 | ветка `claude)` сразу `exec` | modify (сторож) |
| `scripts/vps/dispatch_one.py` | 56-71 | три отказа | modify (+ четвёртый) |
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

**LOC headroom:** `orchestrator_queue.py` 373/400 — проверка ≤ 6 строк, логика в `fleet_pause`;
`claude-runner.py` — после TECH-223/225 около 382/400, здесь ≤ 2 строк (вызов в `runner_ratelimit`);
`callback.py` — условие `exit_code in (5, 75)` вместо `== 5`, 0 новых строк.

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

run-agent.sh (claude):  venv/bin/python3 fleet_pause.py --check || { rc=$?; [[ $rc -eq 75 ]] && exit 75; }
dispatch_one.dispatch:  p = fleet_pause.active_pause(); if p: return _fail(f"fleet paused until …")
orchestrator_queue.gate_before_pueue_add: то же → не диспатчить
dispatch_summary.build/render: summary["paused"] = active_pause() → верхняя строка
callback Step 7: autopilot и exit_code in (5, 75) → callback_ratelimit.requeue(..., counted = exit_code == 5)
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

## Implementation Plan

### Research Sources
- `scripts/vps/orchestrator.py:350-354` — образец файла-состояния рядом со скриптами (`.orchestrator-heartbeat`)
- `scripts/vps/event_writer.py:138-170` — `notify_circuit_event` как образец системного алерта

### Task 1: fleet_pause.py + тесты
**Type:** code
**Files:**
  - create: `scripts/vps/fleet_pause.py`
  - create: `scripts/vps/tests/test_fleet_pause.py`
**Acceptance:** EC-1..EC-5.

### Task 2: раннер ставит паузу и алертит один раз
**Type:** code
**Files:**
  - modify: `scripts/vps/runner_ratelimit.py` — `on_rejected(rl, source)`, текст алерта
  - modify: `scripts/vps/claude-runner.py` — вызов после `decide_exit`, только при exit 5
  - modify: `scripts/vps/tests/test_fleet_pause.py` — EC-6, EC-7
**Acceptance:** EC-6, EC-7; `bash scripts/check-loc-limit.sh` exit 0.

### Task 3: сторож в run-agent.sh
**Type:** code
**Files:**
  - modify: `scripts/vps/run-agent.sh`
**Acceptance:** `bash -n scripts/vps/run-agent.sh`; EC-8 проверяется на VPS пробой AV-F1 (скрипт
зовёт боевой `venv/bin/python3`, локальный тест его не воспроизводит честно).

### Task 4: отказ диспатча и строка брифинга
**Type:** code
**Files:**
  - modify: `scripts/vps/dispatch_one.py`, `scripts/vps/orchestrator_queue.py`, `scripts/vps/dispatch_summary.py`
  - create: `scripts/vps/tests/test_dispatch_one_pause.py`
**Acceptance:** EC-9, EC-10, EC-11.

### Task 5: callback — exit 75 в очередь вне потолка
**Type:** code
**Files:**
  - modify: `scripts/vps/callback_ratelimit.py`, `scripts/vps/callback.py`
  - modify: `tests/integration/test_callback_rate_limit_requeue.py`
**Acceptance:** EC-12.

### Task 6: эксперимент
**Type:** code (docs)
**Files:**
  - create: `ai/experiments/2026-09-23-fleet-pause-on-rate-limit.md` — id: следующий свободный EXP; metric: для каждого окна лимита (маркер открыт → `until`) — сколько прогонов Claude **стартовало** внутри окна и получило 429 (run-логи с exit 5 после первого в окне) и сколько алертов ушло (`grep "rate_limit failed" logs/hermes-wake.log`); baseline 23.09: окно 10:31–11:00Z, внутри него 5 прогонов упали с exit 1 (TECH-526, QA BUG-521, reflect, 2 диспетчера), алертов про лимит 0; expected: 0 прогонов Claude стартует внутри окна после первого упора (только сторожевые exit 75 без вызова API), ровно 1 алерт на окно; check_after_runs 40; check_after_date +21 день (нет события — `inconclusive`). Тело: если диспетчер продолжает стартовать внутри окна — сторож не на том пути (проверить `~/ops/dispatcher.sh`); если алертов больше одного на окно — гонка в `set_pause`.
**Acceptance:** `python scripts/check-experiments.py` exit 0.

### Task 7: доки
**Type:** code (docs)
**Files:**
  - modify: `docs/orchestrator/runbook.md` — раздел «Флот на паузе по лимиту подписки»: признаки (`cat scripts/vps/.rate-limited-until`, строка PAUSED в брифинге, exit 75 в pueue), снятие вручную (`rm` маркера), что пауза не трогает pueue-группы
  - modify: `.claude/rules/dependencies.md` — `fleet_pause.py` (Uses/Used by), сторож в разделе `run-agent.sh`
**Acceptance:** runbook описывает, как увидеть и снять паузу.

### Execution Order
1 → 2 → 3 → 4 → 5 → 6 → 7

---

## Flow Coverage Matrix (REQUIRED)

| # | Шаг | Covered by Task | Status |
|---|-----|-----------------|--------|
| 1 | Прогон упёрся в лимит, exit 5 | - | TECH-225 |
| 2 | Раннер открывает окно паузы и шлёт один алерт | Task 1, 2 | ✓ |
| 3 | Новые запуски (диспетчер, QA, reflect, support) выходят 75 без вызова API | Task 3 | ✓ |
| 4 | LLM-диспетчер и встроенный путь не диспатчат, брифинг говорит PAUSED | Task 4 | ✓ |
| 5 | Спека, стартовавшая в окно, возвращается в очередь без счёта в потолок | Task 5 | ✓ |
| 6 | После `until` пауза снимается сама | Task 1 | ✓ |
| 7 | Замер и вердикт | Task 6 | ✓ |

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
3. EC-9..EC-11 → Task 4
4. EC-12 → Task 5; EC-8 → AV-F1

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
[Auto-populated by autopilot during execution]
