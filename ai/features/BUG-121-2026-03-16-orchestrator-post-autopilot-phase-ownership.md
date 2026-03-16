# Bug: [BUG-121] Orchestrator Post-Autopilot Tail Duplication + Broken Phase Ownership

**Status:** queued | **Priority:** P0 | **Date:** 2026-03-16

## Symptom

На AwardyBot и других проектах post-autopilot хвост оркестрации местами гоняет воздух:

- один и тот же spec/task получает повторные хвосты после уже успешного autopilot
- после успешного autopilot повторно стартуют QA и reflect
- reflect часто запускается впустую и сам пишет `pending = 0`, `новых паттернов нет`
- state machine допускает полусостояние `phase = qa_pending` + `current_task = NULL`
- из-за этого цикл становится непредсказуемым и тратит токены без полезной работы

### Evidence

**AwardyBot logs (2026-03-16):**
- `awardybot-20260316-205604.log` — QA по `BUG-685` завершён успешно
- `awardybot-20260316-205729.log` — reflect сразу после этого: `Pending = 0`, `Паттернов новых: 0`
- `awardybot-20260316-205812.log` — QA по `BUG-685` снова завершён успешно
- `awardybot-20260316-205813.log` — reflect снова: `Pending = 0`, `Паттернов новых: 0`
- `awardybot-20260316-205847.log` — spark получил QA PASS как новый inbox/headless input и ещё раз обработал уже закрытый `BUG-685`

**callback-debug.log:**
- AwardyBot уже раньше показывал паттерн `autopilot -> reflect -> qa -> spark`, а также повторные хвосты у других проектов
- repeated `skill=qa` / `skill=reflect` completion callbacks after same work unit indicate non-canonical post-autopilot ownership

**DB / runtime state:**
- `project_state` historically could be left as `qa_pending + current_task=NULL`
- current code in `db.py callback` still calls `update_project_phase(project_id, new_phase)` without preserving `current_task`
- current orchestrator contains recovery hack: if `qa_pending` and `current_task` is empty, force-reset to `idle`

## Why / Root Cause

Это не один баг, а два связанных бага сразу:

### 1. Phase ownership bug

Post-autopilot phase transition logic сейчас размазана по нескольким владельцам:

- `pueue-callback.sh`
- `db.py callback`
- `orchestrator.sh dispatch_qa()`
- `orchestrator.sh dispatch_reflect()`
- `qa-loop.sh`

В результате нет одного canonical owner для переходов:

- callback ставит `qa_pending`
- `db.py callback` при этом обнуляет `current_task`, потому что `update_project_phase()` по умолчанию пишет `current_task = NULL`
- `dispatch_qa()` зависит от `current_task`, но часто получает пустое значение
- orchestrator вынужден держать recovery-ветку `qa_pending with no current_task -> idle`

Это уже само по себе показывает, что state machine сломана: она зависит от неявного поля, которое другой участок кода стирает.

### 2. Duplication bug

После autopilot хвост запускается не из одной точки, а фактически из двух параллельных контуров:

- callback-контур (`pueue-callback.sh`) инициирует post-autopilot действия сразу после completion
- orchestrator-контур (`dispatch_qa()` / `dispatch_reflect()`) тоже реагирует на `qa_pending` / `qa_running`

Из-за этого возможны:

- повторный QA на тот же spec
- повторный reflect на тот же project state
- повторная обработка уже завершённого результата через inbox/spark

### Concrete code-level causes

1. **`db.py` erases `current_task` during callback phase update**
   - `db.py` CLI path `callback` -> `update_project_phase(project_id, new_phase)`
   - `update_project_phase()` default argument is `current_task=None`
   - SQL blindly writes `current_task = NULL`
   - this creates illegal / half-broken state for downstream dispatchers

2. **`orchestrator.sh dispatch_qa()` still exists as active fallback owner**
   - it dispatches QA on `qa_pending`
   - but code comment already says QA+Reflect are “already dispatched by pueue-callback.sh Step 7”
   - this means current implementation already has split ownership

3. **`orchestrator.sh dispatch_reflect()` reacts to phase instead of canonical completion event**
   - it runs on `qa_pending` or `qa_running`
   - its dedup guard only checks queued/running pueue tasks, not whether reflect for the same autopilot completion was already consumed
   - reflect can therefore re-run later on phase-based re-entry even when there is nothing to process

4. **`qa-loop.sh` and inbox feedback can re-open the cycle even on PASS-like/no-op outcomes**
   - logs show `spark` got `/spark [headless] Source: qa ... BUG-685 ... 6/6 PASS`
   - this means QA success content was treated as new Spark work instead of terminal completion
   - that is a second duplication vector: even if QA itself is single-run, its success result can still re-enter the loop

5. **State machine is phase-based, but tail execution is event-based**
   - autopilot completion is an event
   - QA/reflect tail should run exactly once per autopilot completion event
   - current code partly models it as “phase says qa_pending”, which is too weak and allows re-entry, resets, and orphan states

## Reproduction

### Real reproduction from AwardyBot

1. Run autopilot for a spec (`BUG-685` observed in logs)
2. Wait for post-autopilot tail
3. Observe:
   - first QA pass
   - reflect run with `pending=0`
   - second QA pass for same spec
   - second reflect run with `pending=0`
   - spark re-processing QA success text as new work

### Minimal deterministic reproduction

1. Seed project with valid `project_state.current_task = BUG-XYZ`
2. Complete autopilot via callback path
3. Let `db.py callback` set `phase = qa_pending`
4. Observe that `current_task` becomes `NULL`
5. Let orchestrator cycle run
6. Depending on timing:
   - `dispatch_qa()` sees broken state and resets to idle
   - or callback-owned tail and orchestrator-owned tail overlap
   - or reflect runs again because phase still matches its dispatch condition

### What to log during repro

- callback invocation / completion in `callback-debug.log`
- project state snapshots before and after callback
- pueue labels for autopilot / qa / reflect tasks
- exact phase/current_task transitions in SQLite

## Impact

### User impact

- лишние Telegram хвосты после уже завершённой задачи
- непредсказуемый pipeline: непонятно, живой это цикл или уже шум
- в логах/чатах тяжело отличить реальную работу от дубликатов

### System impact

- лишние вызовы QA и reflect
- лишние Spark headless runs на уже закрытые PASS-результаты
- потеря инварианта state machine
- wasted Claude/Codex/Gemini turns, tokens and queue capacity

### Architectural impact

Главная проблема не только в дублях, а в том, что у post-autopilot transitions нет единственного владельца.
Пока ownership не централизован, любые локальные фиксы будут давать только временное улучшение.

## Proposed Fix

## Design decision

Сделать **одного canonical owner** для post-autopilot transitions.

### Recommended owner

**Canonical owner: `pueue-callback.sh` for completion-triggered transitions.**

Почему:
- именно callback обладает фактом завершения конкретного pueue task
- callback видит `PUEUE_ID`, `LABEL`, `SKILL`, `RESULT`
- callback может принять exactly-once решение на основании completion event
- orchestrator должен заниматься polling / inbox / backlog, но не вторично разруливать completion tails

### New ownership model

#### `pueue-callback.sh` owns:
- autopilot completion -> decide whether to launch QA tail
- autopilot completion -> decide whether to launch reflect tail
- exact-once tail dedup / correlation
- post-autopilot phase transition into a terminal or explicit tail state

#### `orchestrator.sh` owns:
- polling projects
- inbox scan
- backlog scan
- draft notification scan
- **NOT** QA/reflect dispatch for autopilot completion

#### `qa-loop.sh` owns:
- only QA execution for a single explicit spec
- PASS -> terminal state update
- FAIL -> write inbox bug and terminal state update
- it must not be a second owner of generic phase routing

#### `db.py` owns:
- primitive state mutations only
- no hidden destructive side effects on `current_task`

## Required changes

### 1. Remove split ownership from orchestrator

- retire `dispatch_qa()` as active dispatcher for autopilot tails
- retire `dispatch_reflect()` as active dispatcher for autopilot tails
- if they remain as safety code, they must only detect broken state and log warnings, never enqueue new work

### 2. Make callback exactly-once per autopilot completion

For every completed autopilot task, callback must create one correlation unit:

- `project_id`
- `spec_id`
- `autopilot_pueue_id`
- `tail_id` / completion fingerprint

And before dispatching QA/reflect, callback must check whether tail already exists.

Recommended options:
- add `post_autopilot_tail` table in SQLite
- or add fields to `task_log` linking child QA/reflect tasks to parent autopilot task

### 3. Fix phase state machine

Replace ambiguous `qa_pending` semantics with explicit states, for example:

- `autopilot_running`
- `tail_pending`
- `qa_running`
- `tail_done`
- `tail_failed`
- `idle`

Critical invariant:
- if phase implies spec-bound tail work, `current_task` must be non-null
- `db.py` must not null out `current_task` unless transition explicitly wants terminal idle/done state

### 4. Fix `update_project_phase()` API

Current API is unsafe because omitted `current_task` means “erase it”.

Change contract to one of:

- preserve current value unless explicitly overridden
- or split into two functions:
  - `update_phase(project_id, phase)`
  - `update_phase_and_task(project_id, phase, current_task)`

But do **not** silently null `current_task` on callback path.

### 5. Reflect should be gated by work, not by phase only

Reflect dispatch must require actual work signal, e.g.:

- pending diary entries >= threshold
- or new upstream signals since last processed cursor
- and no existing reflect task for same parent autopilot completion

If `pending = 0`, reflect must not enqueue at all.
Not “run and discover nothing”; simply not run.

### 6. QA success must not re-enter Spark

QA PASS / no-op summaries must be terminal notifications only.
They must not generate inbox files or headless Spark tasks.

Add explicit guard:
- only QA FAIL with actionable findings may produce inbox feedback
- QA PASS must close tail and stop

### 7. Add invariants and repair path

On each orchestrator cycle, add invariant checks:

- `phase=qa_pending && current_task IS NULL` => log violation
- `phase in tail states && no matching parent autopilot task` => log violation
- if auto-repair is needed, it should reset to `idle` and annotate the reason in logs

But repair must be a fallback, not normal control flow.

## Allowed Files

**Modify only:**
1. `/home/dld/projects/dld/scripts/vps/pueue-callback.sh`
2. `/home/dld/projects/dld/scripts/vps/orchestrator.sh`
3. `/home/dld/projects/dld/scripts/vps/qa-loop.sh`
4. `/home/dld/projects/dld/scripts/vps/db.py`
5. `/home/dld/projects/dld/scripts/vps/schema.sql` *(if new tail-tracking table/index is needed)*
6. `/home/dld/projects/dld/scripts/vps/notify.py` *(only if terminal notification semantics need adjustment)*

**Read-only evidence sources:**
1. `/home/dld/projects/dld/scripts/vps/callback-debug.log`
2. `/home/dld/projects/dld/scripts/vps/logs/awardybot-*.log`
3. `/home/dld/projects/dld/ai/features/FTR-146-2026-03-10-multi-project-orchestrator-phase1.md`
4. `/home/dld/projects/dld/ai/features/FTR-149-2026-03-12-orchestrator-cycle-v2.md`
5. `/home/dld/projects/dld/ai/features/TECH-150-2026-03-12-orchestrator-e2e-fixes.md`

## Tests

### Deterministic assertions

1. **Callback must not erase current_task implicitly**
   - given `project_state.current_task = BUG-685`
   - when callback updates phase after autopilot success
   - then `current_task` is preserved unless explicitly cleared by terminal transition

2. **Exactly one QA dispatch per autopilot completion**
   - given one autopilot task completion event
   - when callback runs twice or orchestrator cycle overlaps
   - then only one QA child task exists in pueue/task_log

3. **Exactly one reflect dispatch per autopilot completion**
   - given one autopilot completion and eligible diary work
   - then only one reflect child task exists

4. **Reflect skip on empty work**
   - given `pending = 0` and no new upstream signals
   - then reflect is not enqueued at all

5. **Illegal half-state cannot persist**
   - `phase=qa_pending && current_task IS NULL` must never be produced by normal flow

6. **QA PASS is terminal**
   - given QA result with 0 actionable failures
   - then no inbox file is created and no Spark task is spawned

### Integration assertions

1. **AwardyBot replay**
   - replay/log-driven test of BUG-685 path
   - expected sequence: `autopilot -> qa (once) -> reflect (0 or 1 depending on work) -> idle`
   - forbidden: second QA, second reflect, Spark on QA PASS

2. **Overlap tolerance**
   - trigger orchestrator cycle while callback is running
   - expected: no duplicate tail dispatches

3. **DB invariant check**
   - after full cycle, `project_state` ends in valid terminal state:
     - `idle` with `current_task = NULL`, or
     - explicit running state with non-null task

## Definition of Done

- [ ] There is one canonical owner for post-autopilot tail dispatch
- [ ] QA tail runs at most once per autopilot completion
- [ ] Reflect tail runs at most once per autopilot completion
- [ ] Reflect does not start when there is no new work (`pending = 0` / no new signals)
- [ ] `qa_pending + current_task = NULL` is eliminated as normal state
- [ ] `db.py` no longer nulls `current_task` as an implicit side effect of phase update
- [ ] QA PASS cannot loop back into Spark
- [ ] AwardyBot reproduction no longer shows repeated QA/reflect tails
- [ ] Logs clearly show parent autopilot task and child tail ownership/correlation

## Summary

This is **both bugs at once**:

1. **duplication bug** — QA/reflect tails can be launched more than once for the same work unit
2. **phase ownership bug** — phase transitions are owned by multiple components, and `current_task` can be destroyed mid-transition

Primary architectural fix: **centralize post-autopilot ownership in `pueue-callback.sh` and downgrade orchestrator tail dispatchers from owners to observers/repair guards.**
