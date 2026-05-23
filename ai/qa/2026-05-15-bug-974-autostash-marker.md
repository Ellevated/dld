# QA Report: BUG-974 — Autostash callback marker overwrite

**Date:** 2026-05-15
**Environment:** local orchestrator (`scripts/vps/orchestrator.py`) + temp git repos
**Trigger:** `/qa BUG-974` — verify fix prevents stash-pop revert of callback Status

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 5     | 5    | 0    | 0       |

## CI / Deploy gate

- Local HEAD `af63f6a` (BUG-974 closed); merge commit `6664191`, fix `c3b179b` present on develop.
- No deployed environment for orchestrator (in-process daemon). Tested locally.

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | spec_verify.py BUG-974 | heuristic-OK; all 6 allowed files present with recent commits |
| 2 | pytest test_marker_utils.py + test_orchestrator.py | 41/41 pass in 2.73s |
| 3 | Behavioral repro #1 (untracked junk dirty tree, remote `Status: done`) | After `git_pull`: working tree shows `Status: done` — callback commit preserved |
| 4 | Behavioral repro #2 (stale local SPEC with `queued` while remote `done`, dirty tree forces autostash) | After `git_pull`: `Status: done` restored from HEAD — exact bug scenario neutralised |
| 5 | Commit chain on develop | `4abedbf` spec → `c3b179b` fix → `6664191` merge → `af63f6a` mark done — clean history |

## Verdict

Фикс работает: после `stash pop` блоки `DLD-CALLBACK-MARKER-START/END` принудительно возвращаются к HEAD-варианту. Re-dispatch loop (6 pueue ранов на одну спеку) воспроизвести в локальном репро не удалось — `Status: done` сохраняется. ADR-018 (callback = sole writer) теперь enforced и в orchestrator path.

## Manual steps still needed (Steps 4-6 of spec verification)

- [x] Tests pass (Step 4 ✓)
- [n/a] Migrations (Step 5 — no schema changes)
- [x] Acceptance: behavioral repro confirms fix (Step 6 ✓)

## Out of scope for this QA

- Production VPS pueue cycle — нужен оператор для подтверждения, что после деплоя на VPS повторного дёргания done-спек не происходит. Рекомендую мониторить `journalctl -u dld-orchestrator -g AUTOSTASH_CALLBACK_RESTORE` следующие 24-48ч.
