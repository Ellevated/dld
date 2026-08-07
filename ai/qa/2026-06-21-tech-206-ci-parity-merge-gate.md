# QA Report: TECH-206 — Autopilot CI-parity merge gate

**Date:** 2026-06-21
**Environment:** dld repo / autopilot skill prompt (`.claude/skills/autopilot/` + `template/` mirror) — prompt-only spec, no runtime UI
**Trigger:** `/qa TECH-206` — verify the closed spec was actually delivered
**Spec status:** lifecycle `done` (by callback, pueue_id 678, 2026-06-21T20:25:18Z)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 7     | 6    | 0    | 1*      |

*1 finding is Minor (robustness), not a functional fail. The spec's deliverables are present and coherent — **TECH-206 is genuinely delivered, not a false-done.** B1 is a pre-existing, out-of-scope project issue.

## Method

Prompt-only spec → "the product" = the autopilot skill prompt that an autopilot
run consumes. QA = run the spec's own acceptance checks (EC-1..EC-6 grep/diff) +
behavioral dry-read of the merge-gate logic (EC-7), per the Spec Verification
Protocol. No source code reviewed for quality; only the delivered prompt artifacts
were exercised against the spec contract.

## Passed

| # | Scenario | Result |
|---|----------|--------|
| EC-1 | Final gate is CI-parity (`./test ci`) | 28 refs ≥ 6 ✓ |
| EC-2 | Merge rollback `git reset --hard origin/develop` present | 4 ≥ 2 ✓ |
| EC-3 | CI-only red no longer silent-continue (regression-only mode) | present (2) ✓ |
| EC-4 | `./test ci` in escalation.md | 2 ≥ 2 ✓ |
| EC-5 | No silent fast fallback (`CI_PARITY_UNAVAILABLE`) | 8 ≥ 2 ✓ |
| EC-6 | root/template parity (3 files) | all 3 **IDENTICAL** ✓ |

All deliverables confirmed present:
- §5.4 merge gate (post-merge, pre-push `./test ci` → reset → needs_review)
- §5.6 `CI_PARITY_UNAVAILABLE` fallback (no silent `./test fast` degradation)
- PHASE 0 CI Health Check table → REGRESSION-ONLY mode on CI-only red (line 74)
- finishing.md Flow step 1 + step 8 merge gate + Pre-Done Checklist
- escalation.md `./test ci` rows

## Failures

### F1: Merge gate relies on a comment, not control flow, to skip the push [EC-7 dry-read]

**Severity:** Minor
**Reproducibility:** Always (in the prompt logic)
**Expected:** When `./test ci` is red on the merged tree, the run aborts the merge,
does NOT push, and emits `needs_review`.
**Actual:** The §5.4 block resets develop to origin, then **falls straight through**
to the unconditional `git push origin develop` block — there is no `CI_OK` /
`MERGE_BLOCKED` flag gating it. The "Do NOT push / set needs_review" instruction
lives only in a `#` comment, so enforcement depends entirely on the model reading
and obeying the comment.

```bash
if ! ./test ci; then
  git reset --hard origin/develop   # abort
  echo "BLOCKED: ... emitting needs_review"
  # Set task_status="needs_review"... Do NOT push.   <-- comment only, no `fi`-level guard
fi
# Push with retry — runs UNCONDITIONALLY
git push origin develop && PUSH_OK=true || { ... }
```

**Why it's only Minor (not Major):** the primary goal — *never land a red develop
on origin* — is still **structurally** achieved. After `git reset --hard
origin/develop`, local develop == origin, so the subsequent `git push` is a
no-op (nothing new to push). And `task_status` emission is comment-driven
*everywhere* in this skill (it's always an LLM-emitted JSON field, never
deterministic) — so this is consistent with the existing pattern, not a regression.

**User impact:** Low. Red merge is still discarded before reaching origin. The
residual risk is purely that `needs_review` may not be emitted if the model
ignores the comment — meaning a blocked task could be reported as `complete`.
**Hint for developers (out of QA scope — for a future tightening spec):** mirror
the TECH-197 PUSH GUARD pattern just below it — set `CI_OK=false` in the `if`,
guard the push block on `[ "$CI_OK" = true ]`, exactly like `PUSH_OK`.

## Blocked / Observations

### B1: dld `develop` CI is red — pre-existing, OUT OF TECH-206 SCOPE

**What:** `gh run list --branch develop` → CI `failure` on the TECH-206 impl commit
(`f222821`): `python-test` (Run tests with coverage) + `python-lint` (ruff check).
HEAD run on `38b1035` still `in_progress`.
**Attribution:** TECH-206 touched **only markdown** in `.claude/skills/autopilot/`.
Markdown edits cannot break ruff or pytest → this redness is **not** a TECH-206
deliverable defect. The spec explicitly lists "fixing the current red develop" as
**out of scope** (founder deferred). This is the very treadmill the spec exists to
stop — but the fix is prompt-guidance for *future* autopilot runs, not a cleanup
of the existing red. Tracked separately (memory: `autopilot ci-parity gap`).
**Action:** none for TECH-206. Needs the deferred one-shot "fix red dld develop".

### O1: Orphan/draft spec was dispatched despite "founder review required" [process]

**What:** The spec body says *"STATUS: draft — NOT in backlog. Orphan spec by
design… Founder review required before adding a queued backlog row."* Yet the
lifecycle shows `queued → done` via pueue_id 678 — it **was** dispatched, executed,
and merged. The founder gate was bypassed somewhere between authoring and dispatch.
**Impact:** The work itself landed clean and matches the spec, so no damage — but
the "orphan = won't dispatch" assumption (orchestrator skips spec.md without a
backlog row) did not hold here. Worth a glance at how TECH-206 acquired a backlog
row / queued lifecycle without founder sign-off.

## Verdict

**TECH-206 is correctly delivered (done is valid — no demote).** All 7 acceptance
criteria are satisfied (EC-7 with a Minor robustness caveat). The two non-pass
items are a pre-existing out-of-scope project issue (B1) and a process note (O1),
neither attributable to the spec's implementation.
