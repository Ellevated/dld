# QA Report: TECH-182 — Orchestrator rebase --autostash data loss

**Date:** 2026-05-10
**Environment:** /home/dld/projects/dld (develop @ 7003341)
**Trigger:** `/qa TECH-182` — verify spec delivered

> Note: TECH-182 is a pure infra/orchestrator fix (Python scripts, no UI/API/bot surface).
> Per /qa boundaries, did NOT run pytest — verification limited to product-observable
> artefacts (HEAD code, status, callback log, working-tree behaviour).

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 5     | 4    | 1    | 0       |

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | Task 1 — `--autostash`/`rebase --abort` removed from `git_pull` | `grep` on `scripts/vps/orchestrator.py` finds these tokens only in docstring/log message, not in any subprocess call. `pull --ff-only origin develop` present at one site. |
| 2 | Task 2 — `_append_blocked_reason` no longer mutates working tree | `spec_path.write_text` reference in `callback.py` only inside docstring (TECH-182 explanatory comment). New body uses `_read_head_blob` + `_git_commit_push`. Signature unchanged: `(spec_path: Path, reason: str) -> bool`. |
| 3 | Task 3 — `git push` failures now logged | `callback.py:526` — `if push.returncode != 0: log.warning("STATUS_FIX: push failed for %s (rc=%d): %s", ...)`. Success log gated behind same branch. |
| 4 | Task 4 — unit test file shipped | `scripts/vps/tests/test_orchestrator_git_pull.py` exists on develop (commit `dd6e6c0`). Not executed (out of /qa scope). |

## Failures

### F1: Spec/backlog status drift — TECH-182 marked `queued` in working tree although merged

**Severity:** Major
**Reproducibility:** Always (current state on disk)
**Expected:** With all fixes merged (commit 06baad6) and explicit "mark as done" commit 7003341 on HEAD, both spec front-matter and backlog row should show `Status: done`.
**Actual:**
- HEAD blob of spec/backlog says `done` (commit 7003341).
- Working tree (`git status`) shows both files modified: `**Status:** queued`, backlog row `| ... | queued | P1 |`.
- Earlier commit `2e918d7 "remote"` already flipped them done→queued once; 7003341 reverted them; the working-tree reverts them again.

**Steps to reproduce:**
1. `cd /home/dld/projects/dld`
2. `git log --oneline -3` → tip is 7003341 "mark TECH-182 as done"
3. `head -5 ai/features/TECH-182-*.md` → shows `**Status:** queued`
4. `git status -s ai/features/TECH-182-*.md ai/backlog.md` → both modified
5. `git diff ai/features/TECH-182-*.md` → `done` → `queued`

**Evidence:** see commit log diff of `2e918d7` and current `git status` output.
**User impact:** Orchestrator's `scan_inbox` only dispatches `Status: queued` (ADR-021). Once these uncommitted edits get committed (or read by any consumer that reads the working tree), TECH-182 will be re-dispatched as if not done — same false-done / re-loop pattern documented in project memory (TECH-176/177/179 family).
**Hint for developers:** Investigate who is rewriting these files in working tree on a tip that already has them `done`. Suspects: a callback path that still reads the *file* instead of HEAD blob, or a stale autopilot worktree pushing/pulling. Check `scripts/vps/callback-audit.jsonl` (28 new entries since `2e918d7`) for recent `verify_status_sync` calls on TECH-182.

## Fixes Applied

None. Status drift is out of TECH-182 scope (it's an orchestrator-state question, not a code change to the tasks listed in the spec).

## Out of scope (not run)

- `python3 -m pytest scripts/vps/tests/test_orchestrator_git_pull.py` — belongs to `/tester`, not `/qa`.
- End-to-end reproduction of original BUG-972/BUG-973 data-loss scenario — would require a controlled dirty-tree + remote rebase setup; recommend integration test instead.

## Recommendation

1. Resolve working-tree drift: either `git checkout -- ai/features/TECH-182-*.md ai/backlog.md` (accept HEAD `done`) or commit the revert with an explanatory message.
2. Run `/tester scripts/vps/tests/test_orchestrator_git_pull.py` to confirm Task 4 acceptance criteria.
3. If status drift recurs after checkout — open a follow-up TECH spec; this is the false-done auto-close pattern continuing despite TECH-176/177/179.
