# Bug: [BUG-121] Orchestrator Post-Autopilot Tail Duplication + Broken Phase Ownership

**Status:** draft | **Priority:** P0 | **Date:** 2026-03-16

---

## Symptom

На AwardyBot и других проектах post-autopilot хвост оркестрации дублируется:

- Один и тот же spec/task получает повторные QA и reflect после уже успешного autopilot
- Reflect запускается впустую (`pending = 0`, `новых паттернов нет`)
- State machine допускает полусостояние `phase = qa_pending` + `current_task = NULL`
- QA PASS результат попадает обратно в Spark через inbox — бесконечный цикл
- Цикл тратит токены без полезной работы ($0.83 на пустые runs в одном BUG-685 цикле)

### Evidence (AwardyBot 2026-03-16)

| Timestamp | Skill | Содержание | Cost |
|-----------|-------|------------|------|
| 205604 | qa | BUG-685: 6/6 PASS | $0.36 |
| 205729 | reflect | `Pending = 0, Паттернов: 0` | $0.10 |
| 205812 | qa | BUG-685: 6/6 PASS повторно | $0.30 |
| 205813 | reflect | `Pending = 0` повторно | $0.09 |
| 205847 | spark | Получил QA PASS как inbox, обработал уже закрытый BUG-685 | $0.29 |

**callback-debug.log:** repeated `skill=qa` / `skill=reflect` completion callbacks после одного autopilot run.

**DB state:** `project_state` может оставаться `qa_pending + current_task=NULL` — нелегальное полусостояние.

---

## Why / Root Cause (5 Whys)

### Why 1: Почему QA запускается дважды?
Два независимых диспатчера оба реагируют на autopilot completion:
- `pueue-callback.sh` Step 7 (строка 406) — сразу после completion event
- `orchestrator.sh` `dispatch_qa()` (строка 330) — на следующем polling cycle по phase `qa_pending`

### Why 2: Почему orchestrator видит `qa_pending` если callback уже обработал?
Callback ставит `phase = qa_pending` через `db.py callback` (строка 330), но QA dispatched callback'ом ещё не завершился. Orchestrator на следующем цикле видит `qa_pending` и диспатчит свой QA через `qa-loop.sh`.

### Why 3: Почему reflect запускается с `pending = 0`?
`dispatch_reflect()` (строка 374) проверяет diary pending count >= 3, но `pueue-callback.sh` Step 7 (строка 432) диспатчит reflect безусловно. Callback-reflect не проверяет наличие работы.

### Why 4: Почему QA PASS попадает обратно в Spark?
`pueue-callback.sh` Step 6.5 (строка 357) записывает QA result в inbox с `Route: spark_bug`. QA PASS с 6/6 зелёных тестов — это не баг, но код не различает PASS и FAIL при записи в inbox.

### Why 5: Почему `current_task` обнуляется?
`db.py` `update_project_phase()` (строка 122) имеет `current_task: str = None` по умолчанию. Callback path (строка 330) вызывает `update_project_phase(project_id, new_phase)` без передачи current_task — SQL пишет `current_task = NULL`.

### Root Cause Summary

Два связанных бага:

1. **Phase ownership bug** — post-autopilot phase transitions размазаны по 5 компонентам без единого владельца
2. **Duplication bug** — callback-контур и orchestrator-контур оба диспатчат QA/reflect на одно completion event

---

## Reproduction

### Из логов AwardyBot (реальный кейс)

1. Autopilot завершает BUG-685
2. `pueue-callback.sh` Step 7 диспатчит QA + Reflect
3. `db.py callback` ставит `phase=qa_pending`, обнуляет `current_task`
4. Orchestrator cycle видит `qa_pending` → `dispatch_qa()` диспатчит второй QA через `qa-loop.sh`
5. Первый QA PASS → callback Step 6.5 пишет результат в inbox → Spark обрабатывает PASS
6. Reflect запускается дважды с `pending=0`

### Минимальное воспроизведение

1. Seed project с `current_task = BUG-XYZ`
2. Autopilot completion через callback path
3. `db.py callback` → `phase = qa_pending`, `current_task = NULL`
4. Orchestrator cycle: `dispatch_qa()` видит `qa_pending + current_task = empty` → force-reset to idle
5. Тем временем callback-dispatched QA + reflect уже running → их результаты попадают в inbox

---

## Impact

| Тип | Описание |
|-----|----------|
| **Токены** | ~$0.83 wasted на один BUG-685 цикл (повторные QA + пустые reflect + spark на PASS) |
| **UX** | Лишние Telegram уведомления, непонятно — живой цикл или шум |
| **State machine** | Нарушен инвариант: `qa_pending + current_task=NULL` — нелегальное состояние |
| **Масштаб** | Каждый autopilot completion у каждого проекта потенциально дублирует tail |
| **Архитектура** | Без единого owner любые локальные фиксы дают временное улучшение |

---

## Scope

**In scope:**
- Централизация post-autopilot ownership в `pueue-callback.sh`
- Fix `update_project_phase()` API (не стирать `current_task` по умолчанию)
- Удаление дублирующих dispatch из orchestrator
- Guard: reflect не запускается при отсутствии работы
- Guard: QA PASS не попадает в inbox/Spark
- Invariant checks в orchestrator (warning-only)

**Out of scope:**
- Новая таблица `post_autopilot_tail` (можно в следующей итерации)
- Полный redesign state machine phases
- Night reviewer flow
- Telegram notification changes (кроме устранения дублей)

---

## Design Decision

Сделать **одного canonical owner** для post-autopilot transitions.

**Canonical owner: `pueue-callback.sh`** — именно callback обладает фактом завершения конкретного pueue task и может принять exactly-once решение.

| Компонент | Новая роль |
|-----------|-----------|
| `pueue-callback.sh` | Owns: post-autopilot dispatch (QA + reflect), dedup, phase transition |
| `orchestrator.sh` | Owns: polling, inbox, backlog, drafts. **NOT** QA/reflect dispatch |
| `qa-loop.sh` | Owns: single QA execution. PASS → terminal. FAIL → inbox |
| `db.py` | Owns: primitive state mutations, no hidden side effects |

---

## Task 1: Fix `update_project_phase()` — не стирать `current_task` по умолчанию

**File:** `scripts/vps/db.py`

**Что сделать:**
- Изменить `update_project_phase()` — использовать sentinel `_UNSET` вместо `None` по умолчанию
- Если `current_task` не передан явно — сохранить текущее значение в DB (не перезаписывать)
- Если передан `None` явно — только тогда стирать
- Обновить CLI path `callback` (строка 330) — передавать `current_task=None` явно (terminal transition для `failed`) или сохранять task (для `qa_pending`)
- Обновить CLI path `update-phase` (строка 386) — без изменений (не трогает current_task)

**Acceptance:**
- `update_project_phase(pid, 'qa_pending')` НЕ стирает `current_task`
- `update_project_phase(pid, 'idle', current_task=None)` стирает `current_task`
- Orchestrator `scan_backlog()` (строка 295) продолжает работать — передаёт `current_task` явно

---

## Task 2: Fix callback phase transition — сохранять current_task для qa_pending

**File:** `scripts/vps/pueue-callback.sh`, `scripts/vps/db.py`

**Что сделать:**
- Step 1-3 (строка 88-97): при `STATUS=done`, передавать `TASK_LABEL` как current_task в `db.py callback`
- Обновить `db.py` CLI `callback` — принять 7-й аргумент `current_task`
  - При `new_phase=qa_pending` → `update_project_phase(project_id, new_phase)` (current_task сохраняется — Task 1)
  - При `new_phase=failed` → `update_project_phase(project_id, new_phase, current_task=None)`

**Acceptance:**
- После autopilot success: `phase=qa_pending`, `current_task` сохранён (не NULL)
- После autopilot failure: `phase=failed`, `current_task=NULL`

---

## Task 3: Удалить дублирующие dispatcher'ы из orchestrator

**File:** `scripts/vps/orchestrator.sh`

**Что сделать:**
- `dispatch_qa()` (строка 330): превратить из dispatcher в invariant checker
  - Если `qa_pending + current_task` существует — log info, не диспатчить (callback уже dispatched)
  - Если `qa_pending + current_task = NULL` — log warning, reset to `idle` (recovery)
  - Удалить вызов `qa-loop.sh`
- `dispatch_reflect()` (строка 374): удалить полностью
  - Reflect уже диспатчится callback Step 7, orchestrator — дублирующий owner
- Обновить `process_project()`: убрать Step 6 (dispatch_reflect), переименовать Step 5 в invariant check

**Acceptance:**
- Orchestrator НЕ диспатчит QA/reflect
- Orchestrator логирует invariant violations
- `qa_pending + current_task=NULL` → recovery reset to idle с warning

---

## Task 4: Добавить guards в pueue-callback.sh

**File:** `scripts/vps/pueue-callback.sh`

**Что сделать:**
- **Step 7 reflect guard** (строка 432): перед dispatch reflect — проверить diary pending count
  - Получить project path из DB, проверить `grep -c '| pending |' diary/index.md`
  - Если pending < 1 → skip reflect, log: `[callback] Skipping reflect: no pending diary entries`
- **Step 6.5 QA PASS guard** (строка 357): не писать в inbox если QA PASS
  - Добавить в `EMPTY_RESULT` check паттерн: `'0 ✗|0 fail|все.*пройден|all.*pass'`
  - Или явно: если `$SKILL == "qa"` и preview содержит `0 ✗` → `EMPTY_RESULT=true`
- **Step 7 dedup guard**: перед dispatch QA — проверить что QA для этого label ещё не в pueue
  - `pueue status --json` → check label contains `qa-${TASK_LABEL}` → skip if queued/running

**Acceptance:**
- Reflect не запускается если diary `pending = 0`
- QA PASS не создаёт inbox файл
- Второй QA на тот же spec не диспатчится

---

## Allowed Files

**Modify:**
1. `scripts/vps/db.py` — Task 1, 2
2. `scripts/vps/orchestrator.sh` — Task 3
3. `scripts/vps/pueue-callback.sh` — Task 2, 4

**Read-only evidence:**
- `scripts/vps/callback-debug.log`
- `scripts/vps/logs/awardybot-*.log`
- `scripts/vps/qa-loop.sh`
- `scripts/vps/schema.sql`

---

## Eval Criteria

### Deterministic

1. **current_task preserved on qa_pending**
   - Given: `project_state.current_task = 'BUG-685'`
   - When: `db.py callback` sets `phase = qa_pending`
   - Then: `current_task = 'BUG-685'` (not NULL)

2. **Exactly one QA per autopilot completion**
   - Given: one autopilot completion event
   - When: callback runs AND orchestrator cycle overlaps
   - Then: only one QA task exists in pueue for that spec

3. **Reflect skipped on empty work**
   - Given: diary `pending = 0`
   - When: callback Step 7 runs
   - Then: reflect is NOT dispatched

4. **QA PASS is terminal**
   - Given: QA result with 0 failures
   - When: callback Step 6.5 runs
   - Then: no inbox file is created

5. **Illegal half-state cannot persist**
   - Given: `phase=qa_pending && current_task IS NULL`
   - When: orchestrator cycle runs
   - Then: state reset to `idle` with warning log

### Integration

6. **AwardyBot replay**
   - Replay BUG-685 path: `autopilot -> qa (once) -> reflect (0 or 1) -> idle`
   - Forbidden: second QA, second reflect, Spark on QA PASS

7. **DB invariant after full cycle**
   - After cycle: `project_state` ends in valid terminal state
   - Either `idle` with `current_task = NULL`, or running state with non-null task

---

## Definition of Done

- [ ] `update_project_phase()` не стирает `current_task` по умолчанию (sentinel pattern)
- [ ] Callback сохраняет `current_task` при transition на `qa_pending`
- [ ] Orchestrator НЕ диспатчит QA/reflect (только invariant checks)
- [ ] `dispatch_reflect()` удалён из orchestrator
- [ ] Reflect не запускается при `pending = 0` (callback guard)
- [ ] QA PASS не создаёт inbox файл (terminal guard)
- [ ] `qa_pending + current_task = NULL` не возникает в нормальном flow
- [ ] Логи AwardyBot: нет повторных QA/reflect хвостов

---

## Summary

Это **оба бага одновременно:**

1. **Duplication bug** — QA/reflect tails запускаются из двух параллельных контуров (callback + orchestrator), что приводит к повторным runs и wasted tokens (~$0.83/цикл)
2. **Phase ownership bug** — `current_task` стирается callback'ом при phase update, создавая нелегальное полусостояние `qa_pending + current_task=NULL`

**Architectural fix:** централизовать post-autopilot ownership в `pueue-callback.sh`, понизить orchestrator dispatch до invariant observer / recovery guard.
