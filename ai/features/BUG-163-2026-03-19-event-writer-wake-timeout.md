# BUG-163: Fix event_writer wake_openclaw() blocking callback for 23 seconds

**Status:** done
**Priority:** P1
**Risk:** R2
**Created:** 2026-03-19
**Source:** openclaw (headless)

---

## Problem

`openclaw system event --mode now` не работает с VPS — gateway закрывает WebSocket-соединение (code 1000). Функция `wake_openclaw()` в `event_writer.py` тратит ~23 секунд на каждую неудачную попытку, блокируя callback.py при каждом событии.

### 5 Whys

1. **Почему callback медленный?** → `notify()` вызывает `wake_openclaw()`, который блокирует на 23 сек
2. **Почему wake блокирует 23 сек?** → timeout=30s, а gateway рвёт соединение не сразу
3. **Почему wake не работает?** → VPS не поддерживает WebSocket tunnel к OpenClaw gateway
4. **Нужен ли wake вообще?** → OpenClaw уже сканирует pending-events через cron каждые 5 минут
5. **Какой ущерб?** → Каждый callback (autopilot done, QA done, reflect done) задерживается на 23 сек

### Root Cause

`wake_openclaw()` имеет timeout=30s для команды, которая всегда fail на VPS. OpenClaw cron-скан (каждые 5 мин) — достаточный механизм доставки событий.

---

## Solution

Уменьшить timeout `wake_openclaw()` до 5 секунд и логировать failure как DEBUG вместо WARNING. Wake — best-effort оптимизация, не критичный путь.

---

## Blueprint Reference

- **Domain:** scripts/vps (orchestrator infrastructure)
- **Pattern:** Fail-fast for non-critical operations

---

## Tasks

### Task 1: Reduce wake timeout and log level

**File:** `scripts/vps/event_writer.py`

**Changes:**
1. В `wake_openclaw()` строка 73: изменить `timeout=30` → `timeout=5`
2. В `wake_openclaw()` строка 82: изменить `log.warning("openclaw wake timed out")` → `log.debug("openclaw wake timed out (non-critical)")`
3. В `wake_openclaw()` строка 85: изменить `log.warning("openclaw wake failed: %s", exc)` → `log.debug("openclaw wake failed (non-critical): %s", exc)`
4. Обновить docstring: `Timeout 30s to match BUG-160 fix` → `Timeout 5s. Best-effort wake, non-critical (BUG-163).`

**Estimated:** ~4 line changes in 1 file

---

## Allowed Files

- `scripts/vps/event_writer.py` — MODIFY (timeout + log level)

---

## Tests

### Deterministic

1. **timeout value** — `grep "timeout=5" scripts/vps/event_writer.py` returns 1 match
2. **no WARNING in wake** — `grep -c "log.warning" scripts/vps/event_writer.py` returns 0 (all wake logs are debug)
3. **notify still calls wake** — `grep "wake_openclaw" scripts/vps/event_writer.py` returns at least 2 matches (definition + call in notify)

### Integration

4. **callback not blocked** — after deploying, callback.py completes in <10 seconds (previously ~25 seconds)

---

## Eval Criteria

- deterministic: timeout=5 in wake_openclaw, log.debug for timeout/failure
- integration: callback.py round-trip <10s with OpenClaw unreachable
