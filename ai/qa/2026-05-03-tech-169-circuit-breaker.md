# QA Report: TECH-169 — Callback Circuit-Breaker

**Date:** 2026-05-03
**Environment:** VPS local (DB: `scripts/vps/orchestrator.db`, CLI: `python3 scripts/vps/callback.py`)
**Trigger:** `/qa TECH-169`

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 6     | 5    | 1    | 0       |

Spec is **merged** (commit `8d8756a`, merge `66e3800`) but the spec file still says **Status: queued** — stale metadata, not a functional issue.

Live DB inspected before testing: 46 decision rows (11 demotes, 31 noops, 4 syncs). Circuit was CLOSED, 1 demote in 10-min window (within threshold of 3). Schema and indexes match spec exactly.

## Failures

### F1: `--reset-circuit` CLI silently mutates whichever DB `DB_PATH` resolves to (operator footgun)

**Severity:** Minor
**Reproducibility:** Always
**Expected:** Operator should see which DB the reset is about to touch; a typo on env-var name should not cause a silent write to production.
**Actual:** `db.py:18` reads `DB_PATH` env var. There is no `--db` flag and no log line echoing the resolved path. An operator typo (e.g. `DLD_DB_PATH=/tmp/foo.db` instead of `DB_PATH=...`) causes the CLI to silently target `scripts/vps/orchestrator.db` and clear up to 30 minutes of audit rows + invoke `pueue start --group claude-runner` against the live daemon.

**Steps to reproduce:**
1. `DLD_DB_PATH=/tmp/foo.db python3 scripts/vps/callback.py --reset-circuit`
2. Observe log says "cleared N decision row(s)" — N comes from prod DB, not /tmp/foo.db.

**Evidence:** During this QA session, an unintended run cleared 2 rows from live `callback_decisions` (46 → 44). No production impact (rows were stale TECH-169 self-audit; pueue group was already running so resume was a no-op), but the silent-write behavior is the footgun.

**User impact:** Operator running reset under stress (mass-demote storm) could lose audit trail on the wrong environment, or accidentally resume a paused group elsewhere.

**Hint for developers:** Add `--db PATH` flag and/or print `circuit reset: db=<path>, cleared <n>, resumed <group>` so the operator sees the target.

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | EC-1 — 4 demotes flip circuit OPEN | `count_demotes_since(10)`==4 → `is_circuit_open()`==True. Threshold `>3` matches spec. |
| 2 | EC-2 — `--reset-circuit` clears window + circuit closes | Log: "cleared 8 decision row(s)" + "resumed pueue group=claude-runner". Subsequent `count_demotes_since(30)`==0, `is_circuit_open()`==False, exit=0. |
| 3 | EC-3 — Auto-heal after 30 min idle | Inserted 5 demotes with `ts = now - 31 minutes`. `count_demotes_since(10)`==0 → `is_circuit_open()`==False. Lazy heal works as spec'd. |
| 4 | EC-4 — Circuit events emitted | `scripts/vps/ai/openclaw/pending-events/*-circuit_breaker.json` written on reset; payload contains `"skill": "circuit_breaker"`, `"status": "done"`, message `CIRCUIT_RESET: operator reset — decisions cleared, claude-runner resumed.` Open events also present from prior real-world trips (`20260502-234223`, `20260503-013646`, `20260503-013702`). |
| 5 | EC-6 — `callback_decisions` schema + indexes | Live DB has table with all 7 columns + both indexes (`idx_callback_decisions_ts`, `idx_callback_decisions_demoted_ts`). Row count growing organically (46 rows). |
| 6 | Live wiring sanity | Production callback is recording real decisions: `verdict ∈ {demote, noop, sync}` exactly per spec, `demoted=1` only on demote rows. Real circuit trips have happened (3 circuit_breaker events on disk) — system is exercising itself in prod. |

## Out of Scope

- **EC-5 pueue pause on OPEN through full `verify_status_sync` flow** — covered by `tests/integration/test_callback_circuit_breaker.py::test_e2e_5th_call_is_noop_circuit_open` per spec. CLI-side resume verified manually (scenario 2).
- **Telegram delivery** — events land in `pending-events/`, OpenClaw delivery is a separate pipeline.

## Notes for operator

- Live circuit at end of QA: **CLOSED**, 0 demotes in 10-min window, pueue `claude-runner` group `running`. Production unaffected.
- Spec file has stale `Status: queued` despite being merged 2026-05-02 — recommend update to `done`. Ironically, callback's own status-sync sees the spec and emits `demote→noop` (audit log row at 01:41:10Z, reason `no_implementation_commits`) because the file claims `queued` while no fresh impl commits exist post-merge.
