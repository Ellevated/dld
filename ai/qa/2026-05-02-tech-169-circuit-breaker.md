# QA Report: TECH-169 Orchestrator Circuit-Breaker

**Date:** 2026-05-02
**Environment:** VPS local (scripts/vps/, sqlite test DB в /tmp/qa-tech169)
**Trigger:** `/qa TECH-169`
**Surface:** backend infra (callback.py CLI + DB behavior). UI/bot/API нет.

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 6     | 6    | 0    | 0       |

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | `schema.sql` создаёт `callback_decisions` + 2 индекса | EC-6 ✓ |
| 2 | После 3 demote `is_circuit_open()=False`, после 4-го → `True` (threshold `> 3`) | EC-1 ✓ |
| 3 | `clear_decisions(30)` сбрасывает счётчик, circuit закрывается | EC-2 ✓ |
| 4 | `python3 callback.py --reset-circuit` exit 0, лог `CIRCUIT_RESET: cleared N`, `pueue start --group claude-runner` вызван | EC-2 / EC-5 ✓ |
| 5 | Event-файл записан в `ai/openclaw/pending-events/` с `"skill": "circuit_breaker"` и сообщением `CIRCUIT_RESET: operator reset…` | EC-4 ✓ |
| 6 | `pueue group` показывает `claude-runner ... running` после reset | EC-5 ✓ |

## Failures

Нет функциональных багов.

## Issues / Notes (не блокеры)

### N1: Spec status не обновлён после deploy
**Severity:** Minor (процесс)
Frontmatter `status: queued` и body `**Status:** queued`, при этом код в develop (commit `8d8756a`). Backlog тоже показывает `queued`. Оператор видит задачу как "не сделана", риск double-pickup автопилотом.

### N2: `DB_PATH` env var имеет generic имя
**Severity:** Cosmetic (DX)
Для override DB локально нужно `DB_PATH=...` (db.py:18). Легко спутать с другими переменными — я сам в первой попытке не подставил, спасло резолвинг через `__file__`. Предложение: `DLD_DB_PATH`.

## Out of scope

- End-to-end через `verify_status_sync` 5×demote — покрыто Task 8 интеграционных тестов.
- Реальная доставка Telegram-события (нужен прод OpenClaw bot) — проверил только запись JSON.
- Auto-heal после 30 мин idle (нужен time-travel или мок datetime).

## Fixes Applied

Нет.
