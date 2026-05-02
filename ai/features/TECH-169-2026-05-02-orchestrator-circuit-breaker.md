---
id: TECH-169
type: TECH
status: queued
priority: P0
risk: R1
created: 2026-05-02
---

# TECH-169 — Orchestrator circuit-breaker on mass-demote

**Status:** blocked
**Priority:** P0
**Risk:** R1 (затрагивает callback и orchestrator decision flow)

---

## Problem

Если завтра в `callback.py` появится regression (regex-tweak, refactor, неудачный merge) — за 1-2 часа автомат может перевернуть 50+ спек в `blocked`. Это **обратимо в принципе** (status-fix руками + git revert), но трудоёмко: придётся пройти 50 спек по 5 проектам, локально править, форсить через operator-mode.

**Live precedent (02.05):** TECH-166 v1 deploy в 22:47 — за следующие 24h в логах callback мог демоутить любую спеку без heading-варианта, плюс ARCH-176a/b/c/d на wb, плюс кучу awardybot. Если бы ничего не сдерживало — масштаб был бы больше.

**Корень:** Callback fires per-task в pueue без global rate limit. Нет signal'а "что-то идёт не так глобально, остановись".

---

## Goal

**Circuit-breaker** на уровне callback'а:

1. Каждый demote-действие (target=`done` → `blocked` через guard, или resync) пишется в `compute_slots`-adjacent table `callback_decisions`:
   ```
   id | timestamp | project_id | spec_id | verdict | reason | demoted: bool
   ```

2. **Трешхолд**: если в окне 10 минут количество `demoted=true` записей > **3** — circuit OPEN:
   - callback продолжает читать pueue results, но `verify_status_sync` no-op'ит для **всех** проектов.
   - В логе: `CIRCUIT_OPEN: N demotes in 10min, refusing further status mutations until reset`.
   - Telegram-алёрт через `event_writer.notify` (новый event-kind `circuit_breaker`).
   - Параллельно — pueue group `claude-runner` ставится на pause (`pueue group --pause claude-runner`), чтобы остановить генерацию новых задач.

3. **Reset**: ручной — оператор запускает `python3 scripts/vps/callback.py --reset-circuit`. Скрипт:
   - Чистит `callback_decisions` за последние 30 мин.
   - Пингует Telegram о reset.
   - Делает `pueue group --resume claude-runner`.

4. **Healing window**: после 30 мин без demote — circuit auto-closes. Защита от "забыли reset'нуть".

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/db.py`
- `scripts/vps/schema.sql`
- `scripts/vps/event_writer.py`
- `scripts/vps/orchestrator.py`
- `tests/integration/test_callback_circuit_breaker.py`
- `.claude/rules/dependencies.md`

---

## Tasks

1. **Schema**: новая таблица `callback_decisions(id, ts, project_id, spec_id, verdict, reason, demoted)` в `schema.sql`. Migration в `db.py::init_schema()`.
2. **db.py CRUD**: `record_decision()`, `count_demotes_since(min_ago: int)`, `clear_decisions(min_ago: int)`.
3. **Circuit state**: lightweight in-memory + DB-backed flag. `is_circuit_open()` — проверяет за каждый callback. Threshold константа.
4. **Wiring в `verify_status_sync`**: каждый demote → `record_decision(demoted=True)`. На входе — `if is_circuit_open(): log + return`.
5. **`event_writer.py`**: новый `notify_circuit_event(action, count, window_min)`.
6. **CLI**: `python3 callback.py --reset-circuit` flag.
7. **Pueue pause/resume**: subprocess вызовы из circuit-open и --reset-circuit.
8. **Auto-heal**: ленивый — `is_circuit_open()` дополнительно чекает "был ли demote в последние 30 мин"; если нет — auto-resume.
9. **Tests**: симулировать 4 demote'а подряд, проверить что 5-й no-op'ится; reset; auto-heal.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | После 4-х demote за <10мин circuit OPEN, 5-й demote no-op |
| EC-2 | deterministic | После reset — следующий demote проходит |
| EC-3 | deterministic | После 30мин без demote — auto-heal закрывает circuit |
| EC-4 | integration | Telegram event получен на open + reset (mocked event_writer) |
| EC-5 | integration | Pueue claude-runner group pauses на open, resumes на reset |
| EC-6 | deterministic | `callback_decisions` table растёт корректно, indexed по ts |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Threshold=3 слишком жёсткий — обычная legacy-зачистка триггерит false alarm | Counter учитывает только demote-with-reason, не любой sync. + Auto-heal 30мин. |
| Circuit OPEN в момент когда autopilot реально провалился — застревает blocked-цепочка | Operator получает Telegram, видит причину, делает reset. Это UX feature, не bug. |
| Pueue pause не сработает (binary missing) | callback продолжает no-op'ить — это safest default. Pause — best effort. |
