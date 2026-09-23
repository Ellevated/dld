# Feature: [TECH-224] Hermes будится по вердикту lifecycle, а не по коду выхода pueue

**Priority:** P1 | **Date:** 2026-09-23 | **Risk:** R1 (callback — порядок шагов единственного писателя статуса)
**Size:** 4 tasks / 9 files.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Hermes узнаёт о результате прогона из события, которое пишет callback. Событие пишется из
**кода выхода процесса**, а вердикт по спеке callback выносит позже:

- `callback.py:307-316` — Step 5 `write_event_for_skill(project_path, skill, status, task_label)`,
  где `status` = `map_result(...)` от pueue;
- `callback.py:332-362` — Step 7 `verify_status_sync(...)` уже после этого может перевести спеку
  `in_progress → blocked` (`autopilot_signaled_blocked`, `branch_pushed_not_merged:N ahead`).

Факт 23.09 (`scripts/vps/logs/hermes-wake.log`, `callback-debug.log`):

| Спека | Вердикт callback | Что получил Hermes | Что ответил Hermes |
|---|---|---|---|
| dowry TECH-526 | 15:48:25 `in_progress → blocked (autopilot_signaled_blocked)` | 12:48:20Z `dowry autopilot done` | «Обычное успешное завершение… сообщение в Telegram не отправлял» |
| dowry BUG-523 | 16:46:50 `in_progress → blocked (autopilot_signaled_blocked)` | 13:46:44Z `dowry autopilot done` | «Рядовое успешное завершение… В Telegram ничего не отправлял» |

Хуже: `write_event_for_skill` (`callback.py:190-194`) для автопилота пишет событие **только при
`status == "done"`**. Упавший автопилот (таймаут, exit≠0) не будит Hermes вообще. Блоки и падения —
ровно то, ради чего Hermes существует, — до основателя не доходят; 23.09 их разбирали руками в
интерактивных окнах.

Попутно: артефакт QA берётся как `sorted(p.glob("ai/qa/[0-9]*-*.md"))[-1]` (`callback.py:200`) —
последний **по имени**, не свежий и не свой. Имена QA — `ai/qa/{YYYY-MM-DD}-{area-slug}.md`
(`qa/SKILL.md:543`), в один день сортируются по слагу. Hermes 23.09 дважды получил
«qa-BUG-522 → артефакт FTR-282».

## Context

- Разбор суток: `C:\Users\Oleg\.claude\task-journal\2026-09-23-dld-orch24h.md`.
- Hermes будится снова только с 23.09 (`4e1f493`, `hermes -z`); до этого все пробуждения молча
  падали с 13.08 — поэтому дыра не была видна.
- Соседние спеки: TECH-223 (фон в headless), TECH-225 (распознать лимит подписки, **AFTER
  TECH-224** — правит тот же `callback.py`), TECH-226 (пауза флота до сброса лимита).

---

## Scope

**In scope:**
1. `verify_status_sync` возвращает свой вердикт `(status, reason)` вместо `None` там, где он его
   вынес; `None` — где вердикта нет (circuit open, нет lifecycle-записи, спека уже `done`).
2. Для `skill == "autopilot"` событие пишется **после** Step 7 и несёт вердикт: `done` или
   `blocked` + причина. Одно событие на прогон автопилота.
3. Автопилот, упавший с exit≠0, тоже будит Hermes (вердикт Step 7 для `status == "failed"`).
4. Если вердикта нет (Step 7 бросил исключение или вернул `None`) — событие всё равно пишется,
   со статусом pueue и пометкой «вердикт lifecycle недоступен: <почему>». Молчание — не вариант.
5. QA-артефакт: файл этой спеки (spec_id из `qa-<ID>` в имени, без учёта регистра), свежий по
   mtime; нет такого — самый свежий по mtime. Reflect — самый свежий по mtime.
6. Для `qa`/`reflect`/`spark` порядок не меняется: событие на месте Step 5.
7. `write_event_for_skill` переезжает в новый модуль `callback_event.py` (callback.py 371/400 —
   места под новую логику нет), в `callback.py` остаётся ре-экспорт (контракт TECH-216).

**Out of scope:**
- Текст пробуждения Hermes и его решение слать/не слать Telegram (`event_writer.wake_hermes`) — не
  меняются; Hermes получает правильный `status` и сам решает.
- Дедупликация и шум Hermes (одно пробуждение на прогон — как сейчас).
- Лимит подписки — TECH-225/226.

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `grep -rn "write_event_for_skill" scripts/vps tests` → определение `callback.py:190`, вызов
  `callback.py:314`; тестов нет (0 совпадений в `tests/`, `scripts/vps/tests/`).
- `grep -rn "verify_status_sync(" tests scripts/vps` → единственный продакшн-вызов
  `callback.py:354`; 20+ интеграционных тестов вызывают его и **не читают** возвращаемое значение
  (`grep -rn "= callback.verify_status_sync\|assert callback.verify_status_sync" tests` → 0) —
  добавление возврата обратно совместимо.
- `grep -rn "event_writer.notify" scripts/vps` → `callback.py:208`, `callback_sync.py:284`
  (rule_7_saved — не трогаем), `audit_digest.py:184` (не связан).

### Step 2: DOWN
- `event_writer.notify(project_path, skill, status, message, artifact_rel="")` — `event_writer.py:126-135`, сигнатура не меняется.
- `callback_sync._read_existing_status`, `_decide_status`, `_write_status` — `callback_sync.py:255-379`.

### Step 3: BY TERM
- `grep -rn "Step 5\|write_event_for_skill\|event_writer.notify → Hermes" docs/ .claude/rules/` →
  `docs/orchestrator/status-model.md:170` (таблица 7 шагов, текущий неверный порядок),
  `docs/orchestrator/README.md:112-127` (та же схема), `.claude/rules/dependencies.md` раздел callback.
- CI: `.github/workflows/test.yml:72-77` — `--cov` перечисляет модули callback по имени; новый
  `callback_event` надо добавить, иначе он выпадет из покрытия.

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/callback.py` | 190-214, 307-316, 332-362 | событие до вердикта; autopilot failed без события | modify |
| `scripts/vps/callback_sync.py` | 304-379 | `-> None` | modify (return verdict) |
| `.github/workflows/test.yml` | 72-77 | список `--cov` | modify |

### Step 4: CHECKLIST
- [x] `tests/**` — новый `tests/integration/test_callback_event_verdict.py` (харнес как в `test_callback_blocked_no_dispatch.py:158-190`: реальный git-репо, реальный lifecycle, `event_writer` перехвачен monkeypatch)
- [x] `scripts/vps/tests/` — новый `test_callback_event_artifact.py` (выбор артефакта)
- [x] `db/migrations/**` — N/A

### Verification
- [x] Все найденные файлы в Allowed Files
- [x] После спеки `grep -n "def write_event_for_skill" scripts/vps/callback.py` = 0 (переехала), `grep -n "write_event_for_skill" scripts/vps/callback.py` ≥ 1 (ре-экспорт + вызов)

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/callback_event.py` — write_event_for_skill + выбор артефакта + сборка события по вердикту (NEW)
- `scripts/vps/callback.py` — ре-экспорт, событие автопилота после Step 7, fallback без вердикта (modify, 371 LOC)
- `scripts/vps/callback_sync.py` — verify_status_sync возвращает (status, reason) | None (modify, 379 LOC)
- `tests/integration/test_callback_event_verdict.py` — main() end-to-end: блок/done/failed/нет вердикта (NEW)
- `scripts/vps/tests/test_callback_event_artifact.py` — выбор артефакта QA/reflect (NEW)
- `.github/workflows/test.yml` — `--cov=callback_event` (modify)
- `docs/orchestrator/status-model.md` — таблица шагов callback (modify)
- `docs/orchestrator/README.md` — схема шагов callback (modify)
- `.claude/rules/dependencies.md` — раздел callback: новый модуль, порядок событий (modify)

**LOC headroom:** `callback.py` 371/400 — после выноса `write_event_for_skill` (~25 строк) в
`callback_event.py` чистый прирост должен быть ≤ 0; `callback_sync.py` 379/400 — изменение ≤ 8
строк (сигнатура + 3–4 `return`), без новой логики внутри.

---

## Environment

nodejs: false
docker: false
database: true   # orchestrator SQLite через tmp_db фикстуру

---

## Blueprint Reference

N/A — в DLD нет `ai/blueprint/system-blueprint/`. Домен: callback оркестратора (`scripts/vps/`).

---

## Historical Risks

<!-- lessons-binding v1 -->

none — `ai/lessons/` пуст (только `.gitkeep`). Близкий прецедент в коде: `callback_sync.py:277-294`
(Rule 7 structural save шлёт своё событие) — его поведение не меняется.

---

## Approaches

### Approach 1: `verify_status_sync` возвращает вердикт; событие автопилота после Step 7
**Source:** research-codebase.md §Risks 1, research-devil.md §Argument 1 (Counter).
**Summary:** Вердикт возвращается тем, кто его вынес; событие строится из него.
**Pros:** нет второго чтения lifecycle (гонка с другим писателем исключена); NOOP-случаи явно
определены; обратно совместимо для 20+ тестов.
**Cons:** +несколько строк в `callback_sync.py` при запасе 21.

### Approach 2: после Step 7 перечитать `lifecycle.read_lifecycle()`
**Summary:** Не трогать `callback_sync`, прочитать статус из git после записи.
**Cons:** гонка «запись → чтение» с конкурирующим писателем (devil Hidden Coupling), и нет
причины блока (transitions не хранят `reason` на запись — research-devil EC-7).

### Selected: 1
**Rationale:** вердикт уже вычислен внутри `verify_status_sync`; вернуть его дешевле и точнее,
чем восстанавливать по косвенным признакам.

---

## Design

### Как сейчас
`callback.main()` (`callback.py:217-367`): Step 4 `extract_agent_output` → **Step 5 событие по
pueue-статусу** → Step 6 QA/reflect → **Step 7 вердикт** (только `skill == "autopilot" and status
in ("done","failed")`, `callback.py:333`). Каждый шаг в своём `try/except`, `main` всегда `exit 0`.

### Как будет
```
Step 4 extract_agent_output
Step 5 событие  — для qa / reflect / spark как раньше (callback_event.write_event_for_skill)
                  для autopilot — НЕ здесь
Step 6 QA/reflect dispatch — без изменений
Step 7 verdict = verify_status_sync(...)       # (status, reason) | None
Step 7b событие автопилота (свой try/except):
        verdict есть  → status = verdict.status ("done"/"blocked"), сообщение
                        "autopilot {status} for {label}: {reason}"
        verdict нет   → status = pueue-статус, сообщение
                        "autopilot {status} for {label} — вердикт lifecycle недоступен: {why}"
```
`why` — `"exception: <тип>"`, `"no_decision"` (verify вернул `None`), `"no_spec_id"`,
`"no_project_path"`. Событие автопилота пишется **ровно один раз** за вызов callback, в том числе
при `status == "failed"` и при падении Step 7.

`verify_status_sync` возвращает:
- `(new_status, reason or "ok")` после успешной записи (`callback_sync.py:370-379`);
- `(new_status, "already_correct")` на NOOP совпадения (`:353-358`);
- `("done", "rule_7_saved")` если `_write_status` поймал Rule 7 — сейчас `_write_status` возвращает
  `False` на обоих путях; различить через аудит нельзя без роста файла, поэтому на `False` вернуть
  `None` (событие скажет «вердикт недоступен»), а Rule 7 и так шлёт своё событие (`:284-290`);
- `None` там, где `_read_existing_status` вернул `None` (`:332-334`).

### Выбор артефакта (`callback_event.py`)
- `qa`: spec_id = `task_label` без префикса `qa-`; кандидаты `ai/qa/[0-9]*-*.md`, сначала те, чьё
  имя содержит spec_id (casefold), среди них — max по `st_mtime`; иначе max по `st_mtime` среди всех.
- `reflect`: `ai/reflect/findings-*.md`, max по `st_mtime` (как `callback_logs.py:44`).

### Database Changes
Нет.

---

## Implementation Plan

### Research Sources
- `scripts/vps/callback_logs.py:44` — образец выбора по mtime
- `tests/integration/test_callback_blocked_no_dispatch.py:59-63, 158-190` — харнес `callback.main()` и заглушка `event_writer`

### Task 1: verify_status_sync возвращает вердикт
**Type:** code
**Files:**
  - modify: `scripts/vps/callback_sync.py`
**Acceptance:** все существующие `tests/integration/test_callback_*.py` зелёные без правок; `wc -l` ≤ 400.

### Task 2: callback_event.py и событие автопилота по вердикту
**Type:** code
**Files:**
  - create: `scripts/vps/callback_event.py` — `write_event_for_skill(project_path, skill, status, task_label, reason="")`, `pick_artifact(...)`, `autopilot_event(project_path, task_label, pueue_status, verdict, why)`
  - modify: `scripts/vps/callback.py` — ре-экспорт `write_event_for_skill` (callers `callback.<name>`), Step 5 пропускает autopilot, Step 7b
  - create: `tests/integration/test_callback_event_verdict.py` — EC-1..EC-5, EC-8
**Acceptance:** EC-1..EC-5, EC-8; `bash scripts/check-loc-limit.sh` exit 0.

### Task 3: выбор артефакта
**Type:** test
**Files:**
  - create: `scripts/vps/tests/test_callback_event_artifact.py` — EC-6, EC-7
**Acceptance:** EC-6, EC-7.

### Task 4: CI и доки
**Type:** code (docs/ci)
**Files:**
  - modify: `.github/workflows/test.yml` — `--cov=callback_event`
  - modify: `docs/orchestrator/status-model.md`, `docs/orchestrator/README.md` — порядок: событие автопилота после вердикта, для остальных скиллов на месте Step 5
  - modify: `.claude/rules/dependencies.md` — таблица модулей callback + `callback_event.py`
**Acceptance:** `grep -n "callback_event" .github/workflows/test.yml` ≥ 1; доки описывают новый порядок.

### Execution Order
1 → 2 → 3 → 4

**Эксперимент не заводится:** это исправление доставки уведомления, а не изменение того, как
прогоны флота исполняются (промпт, модель, конфиг раннера, политика диспатча). Проверка —
детерминированные EC-1..EC-8 и AV-F1 на первом блоке после выкатки.

---

## Flow Coverage Matrix (REQUIRED)

| # | Шаг | Covered by Task | Status |
|---|-----|-----------------|--------|
| 1 | pueue завершил autopilot, callback стартовал | - | existing |
| 2 | Step 7 выносит вердикт и возвращает его | Task 1 | ✓ |
| 3 | Событие автопилота по вердикту (done / blocked + причина) | Task 2 | ✓ |
| 4 | Упавший автопилот тоже будит Hermes | Task 2 | ✓ |
| 5 | Нет вердикта → событие с пометкой, не тишина | Task 2 | ✓ |
| 6 | QA/reflect получают свой артефакт | Task 2, 3 | ✓ |
| 7 | Hermes читает событие и решает про Telegram | - | existing |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Автопилот сигналит blocked | pueue Success, `task_status=blocked` в run-логе, гейт видит мерж | ровно одно событие: `skill=autopilot`, `status=blocked`, в сообщении `autopilot_signaled_blocked` | deterministic | incident TECH-526/BUG-523 | P0 |
| EC-2 | Штатный done | pueue Success, `task_status=complete`, ветка слита | одно событие `status=done` | deterministic | regression | P0 |
| EC-3 | Упавший автопилот | pueue Failed (exit 124), ветка запушена, не слита | одно событие `status=blocked`, в сообщении `branch_pushed_not_merged` (раньше событий 0) | deterministic | callback.py:193 | P0 |
| EC-4 | Step 7 бросил исключение | `verify_status_sync` поднимает `RuntimeError` | одно событие со статусом pueue и текстом «вердикт lifecycle недоступен: exception: RuntimeError»; `main` exit 0 | deterministic | devil Argument 1 | P0 |
| EC-5 | Нет вердикта | lifecycle-записи спеки нет (`verify_status_sync` → `None`) | одно событие с пометкой `no_decision` | deterministic | callback_sync.py:332-334 | P1 |
| EC-6 | Свой QA-артефакт | `ai/qa/2026-09-23-bug-520-a.md` (старше) и `2026-09-23-zzz-other.md` (новее), label `qa-BUG-520` | `artifact_rel` = файл bug-520 | deterministic | Hermes «FTR-282» | P1 |
| EC-7 | Нет файла спеки | два QA-файла без spec_id в имени, у «a…» mtime новее, чем у «z…» | выбран «a…» (по mtime, не по имени) | deterministic | callback.py:200 | P1 |
| EC-8 | QA/reflect не ждут Step 7 | skill `qa`, pueue Success | событие пишется, Step 7 не вызывается; число событий = 1 | deterministic | regression | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 0 (EC-1..EC-5, EC-8 — через реальный `callback.main()` и git) | LLM-Judge: 0 | Total: 8

### TDD Order
1. EC-1, EC-3 → FAIL на текущем коде → Task 1–2 → PASS
2. EC-4, EC-5, EC-2, EC-8
3. EC-6, EC-7

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | callback импортируется и ре-экспорт жив | `cd ~/projects/dld/scripts/vps && venv/bin/python3 -c "import callback; print(callback.write_event_for_skill.__module__)"` | `callback_event`, exit 0 | 30s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Первый блок автопилота после выкатки | любой прогон, который callback переведёт в `blocked` | `grep -A3 "<spec> autopilot blocked" ~/projects/dld/scripts/vps/logs/hermes-wake.log` | строка события со `status=blocked` и ответ Hermes, не «рядовое успешное завершение» |

### Verify Command (copy-paste ready)

```bash
pip install -r scripts/vps/requirements.txt
pytest tests/integration/test_callback_event_verdict.py scripts/vps/tests/test_callback_event_artifact.py -v
pytest tests/ scripts/vps/tests/ -q
bash scripts/check-loc-limit.sh
ruff check . && ruff format --check .
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Блок и падение автопилота доходят до Hermes со статусом `blocked` и причиной
- [ ] Ровно одно событие на прогон автопилота
- [ ] QA-событие указывает на артефакт своей спеки
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] EC-1..EC-8 pass
- [ ] `pytest tests/ scripts/vps/tests/ -q` зелёные (с `scripts/vps/requirements.txt`)

### Acceptance Verification
- [ ] AV-S1 pass; AV-F1 — на первом блоке после выкатки (записать в Autopilot Log)

### Technical
- [ ] ruff 0.16.1 check + format
- [ ] LOC-гейт exit 0 (`callback.py`, `callback_sync.py` ≤ 400)
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
