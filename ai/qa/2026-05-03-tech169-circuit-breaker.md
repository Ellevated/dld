# QA Report: TECH-169 Orchestrator Circuit-Breaker

**Date:** 2026-05-03
**Environment:** local sandbox `/tmp/qa-tech169` (callback.py + db.py + event_writer.py + schema.sql copied from `scripts/vps/`)
**Trigger:** `/qa TECH-169` — verify circuit-breaker behaviour

## Pre-flight

- Implementation merged: commit `66e3800 Merge TECH-169` on develop. Spec status `blocked` в backlog (callback auto-fix), но код в проде.
- Это backend/CLI фича без UI и без deploy URL — `/qa` deploy-gate skipped (orchestrator runs локально на VPS).
- CI status: не проверял (нет deploy-target для VPS-orchestrator; тестируется через unit/integration suite).

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 10    | 10   | 0    | 0       |

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1a | Schema: `callback_decisions` table created with all 7 columns | id, ts, project_id, spec_id, verdict, reason, demoted |
| 1b | Schema: 2 indexes created | idx_callback_decisions_ts + idx_callback_decisions_demoted_ts |
| 2 | `record_decision()` returns positive rowid | rowid=1 |
| 3 | `count_demotes_since(10)` correctly counts in window | 3 inserts → returns 3 |
| 4a | `is_circuit_open()` False at 3 demotes | threshold is `> 3` |
| 4b | `is_circuit_open()` True at 4 demotes | trips above threshold |
| 5 | Auto-heal: 5 demotes inserted 31 min ago → circuit CLOSED | EC-3 confirmed |
| 6 | `python3 callback.py --reset-circuit` exits 0 | stdout: `circuit reset: cleared decisions, resumed claude-runner` |
| 7 | Reset works без `pueue` в PATH (best-effort) | log warning, no crash, exit 0; cleared 12 rows |
| 8 | `notify_circuit_event(count=0)` does not raise | reset path safe |

## Failures

(none)

## Coverage Notes

- EC-1 ✅ covered by S4a/S4b
- EC-2 ✅ covered by S6 (reset → decisions cleared)
- EC-3 ✅ covered by S5
- EC-4 ⚠️ smoke-checked via S8 (function callable); full Telegram event routing не воспроизводил — это integration в `tests/integration/test_callback_circuit_breaker.py`
- EC-5 ⚠️ pueue pause/resume best-effort путь покрыт S7; happy-path с реальным pueue не воспроизводил
- EC-6 ✅ covered by S1a/S1b + S3

## Fixes Applied

(none — все сценарии прошли)

## Recommendation

Implementation TECH-169 ведёт себя корректно с точки зрения "оператора, дёргающего CLI и наблюдающего DB". Threshold logic (>3 в 10 мин), auto-heal (30 мин), и --reset-circuit работают. Spec в backlog можно перевести `blocked → done` после ручной верификации (TECH-174 protocol).
