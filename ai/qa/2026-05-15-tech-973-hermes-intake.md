# QA Report: TECH-973 Hermes intake contract

**Date:** 2026-05-15
**Environment:** local-only (doc + regression test feature)
**Trigger:** `/qa TECH-973`

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 6     | 6    | 0    | 0       |

Spec is documentation + regression-test only — no UI / API / bot surface to
exercise. QA reduces to acceptance verification per spec §Verify Command and
§Eval Criteria.

## Passed

| # | Scenario | Evidence |
|---|----------|----------|
| 1 | AV-S1: `ai/inbox/README.md` exists | `test -f` exit 0; file has 7-row status table, references `scan_inbox` and `_VALID_STATUSES` as SSOT |
| 2 | AV-S2 / AV-F1: regression tests collect + green | `pytest -k scan_inbox -q` → **7 passed, 26 deselected** (incl. `test_scan_inbox_ignores_draft`, `test_scan_inbox_ignores_clarifying_stale_rejected[clarifying/stale/rejected]`, `test_scan_inbox_dispatches_queued`) |
| 3 | EC-4 / AV-F2: OpenClaw rename done | `grep -rn "OpenClaw" .claude/` → 1 hit, and it is the explicit footnote inside ADR-022 row referencing the old name (allowed by spec: «или одна строка-сноска «бывший OpenClaw»»). Same allowed footnote in README.md line 8. |
| 4 | ADR-022 present in architecture.md | Row found at line 104 with date 2026-05 and TECH-973 reason. |
| 5 | 4 target files use "Hermes" | reflect/SKILL.md, audit/night-mode.md, bughunt/completion.md, rules/dependencies.md — all reference Hermes; no stale OpenClaw mentions. |
| 6 | EC-5: README contains `queued` row | `grep "\| queued \|" ai/inbox/README.md` → hit; row marks Hermes as sole writer, eligible ✅. |

## Failures

none.

## Blocked

none.

## Fixes Applied

none.

## Notes

- Spec is still `Status: queued` in the file header, but all DoD items are
  satisfied on disk — looks like implementation landed without callback flipping
  the status to `done` (callback writes spec/backlog status after pueue
  completion; this run is manual QA, not autopilot, so no auto-flip is expected
  here).
- Recommend operator promote TECH-973 to `done` via
  `python3 scripts/vps/spec_operator.py mark-done dld TECH-973 "QA verified"`
  or rely on the next autopilot/callback cycle.
