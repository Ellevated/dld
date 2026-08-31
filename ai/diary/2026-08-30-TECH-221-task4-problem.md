# TECH-221 Task 4/5 — 2026-08-30

## Problem
- No debug retries. The defect was found by PHASE 3 Exa verification, AFTER the task
  had passed tester, pre-check, spec compliance and code quality review.

## Context
- Error: the continuation push shipped as `git push --force-with-lease`. A bare lease is
  satisfied by a BACKGROUND fetch that updated `refs/remotes/origin/<branch>` without
  integrating it. `orchestrator.py:106` already documents that the gate-daemon fetches
  these repos concurrently — so this was a live race on this machine, not theoretical.
- Files: .claude/skills/autopilot/{worktree-setup,autopilot-git}.md + both template copies
- Attempts: reproduced on a throwaway repo — third party pushes a reviewed commit to the
  branch, background fetch runs, then our push. Bare lease: exit 0, human commit DESTROYED.
  With `--force-if-includes`: exit 1, rejected.
- Resolution: added `--force-if-includes` (git 2.30+, host runs 2.43) to all 6 push sites
  across both trees, plus a fail-closed `|| { echo PUSH_REJECTED; exit 2; }` handler —
  a rejected push previously fell through and continued on a diverged branch.

## Category
architecture
