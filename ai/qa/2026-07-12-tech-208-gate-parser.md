# QA Report: TECH-208 — Gate Allowed Files Numbered-List Parser

**Date:** 2026-07-12
**Environment:** VDS, orchestrator + gate-daemon (both active), develop branch
**Trigger:** `/qa TECH-208` — spec verification (status: done)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 8     | 8    | 0    | 0       |

## Failures

None.

## Blocked

None.

## Passed

| # | Scenario | Type | Notes |
|---|----------|------|-------|
| 1 | Numbered-list format (`1. \`path\``) parsed correctly | HAPPY PATH | 3/3 files extracted from numbered-list spec |
| 2 | Dash-bullet format (`- \`path\``) still works | REGRESSION | 3/3 files — no regression in canonical format |
| 3 | Mixed format (dash + numbered in one spec) | EDGE | 4/4 files parsed from mixed-format spec |
| 4 | Root `bug-mode.md` template uses dash-bullets | VERIFY | `## Allowed Files` section uses `- \`path\`` format |
| 5 | Template `bug-mode.md` uses dash-bullets | VERIFY | Identical to root — both synced to canonical format |
| 6 | callback + gate_logic parsers produce identical output | CONSISTENCY | Both return same 3-file list for numbered-list input |
| 7 | Real-world BUG-355 style spec (5 numbered files) | ACCEPTANCE | 5/5 files parsed — previously falsely-blocked format now works |
| 8 | Full test suite (test_gate_logic.py) | GATE | 39/39 passed (3.85s), including 3 new numbered-list tests |

## Verification Against Definition of Done

| # | Criterion | Verdict |
|---|-----------|---------|
| 1 | Parser accepts both dash and numbered list formats | PASS (scenarios 1-3, 6-7) |
| 2 | `bug-mode.md` (root + template) uses dash-bullets | PASS (scenarios 4-5) |
| 3 | Regression test added for numbered-list parsing | PASS (3 new tests in test_gate_logic.py) |
| 4 | Existing dash-format tests have no regression | PASS (all 39 tests pass) |
| 5 | No new failures in test suite | PASS (scenario 8) |

## Conclusion

TECH-208 fully delivered. The root cause (parser rejecting numbered-list format) is fixed in both `callback.py` and `gate_logic.py`. The template drift in `bug-mode.md` is corrected. The 6 previously falsely-blocked specs (plpilot BUG-355, TECH-342/343/345, awardybot BUG-1395/FTR-1394) would no longer be blocked by this parser limitation.
