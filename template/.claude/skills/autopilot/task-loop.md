# Task Loop — PHASE 2 Execution

SSOT for task execution. Runs once per task from the Implementation Plan.

```
CODER → TESTER → PRE-CHECK → SPEC CHECK → CODE QUALITY → COMMIT → DIARY → LOCAL VERIFY → NEXT
```

## Who runs each step

Two steps dispatch a subagent on every task; the rest you run yourself.
"Yourself" means the autopilot loop reading this file, in its own context, with
no Task tool call. The conditional dispatches are not absent, only occasional:
the `debugger` when a test fails in scope, the coder again at Step 2.5 to write
a regression test, and the coder again wherever a check below sends work back.

| Step | Runs where |
|---|---|
| 1. Coder | subagent `coder` |
| 2. Tester | subagent `tester` (`debugger` on failure) |
| 2.5 Regression capture (conditional) | subagent `coder` |
| 3. Pre-check | you — shell commands |
| 4. Spec compliance | you |
| 5. Code quality | you — checklist in `.claude/agents/review.md` |
| 6. Commit / 6.5 Diary / 7 Local verify | you |

## What the loop never runs

The loop does not run pytest, `./test *`, `tests/architecture/`, or any project gate
that wraps them. Tests are Step 2's job (tester, one targeted set per task) and PHASE
3's (full suite, once per spec). Steps 3 and 5 are `grep`/`wc`/the named scripts —
seconds each — and they run **once per task**: when a check sends work back to the
coder, re-run that one check on return, not the set. Measured 2026-09-02 across 11
runs: the loop spent 14–60 min per spec in its own Bash calls, most of them test
sweeps and "all gates" re-runs after every coder return.

## Why those two, and not the others

A subagent starts cold. Before it can act it rebuilds the task context you are
already holding — the spec, the plan, the diff — and that rebuild is billed as
cache creation, which is where the money in a run actually goes. Measured across
production runs, cost tracks cache-creation volume almost linearly; a spec that
cost $20 built 1.3M tokens of context doing it.

So the test is whether a step needs **something you do not have**:

- **Coder** writes on a cheaper model while you orchestrate — a real division of
  labour, not ceremony.
- **Tester** carries the test-selection tables, the immutable-test rules and
  eval-judge dispatch. Knowledge you do not hold, and should not be inlined into
  every task.
- **Debugger** is dispatched only on a failure, because reasoning about the
  failure is the part that needs a model.
- **Spec compliance** needs neither. You are holding the spec and the diff, so a
  fresh agent would only re-read both to reach the position you are already in.
- **Code quality** was the last step still dispatched, on the argument that its
  independence is load-bearing. Read precisely, that argument guards against
  *self*-review — and you did not write this code. The coder did, in a context
  that no longer exists by the time you review. What a separate reviewer buys on
  top of that is ignorance of the plan, which is a thinner claim than "the author
  cannot see their own blind spots". The rest of what it brought is a checklist,
  and a checklist can be read (`.claude/agents/review.md`) without paying for a
  second context to hold it.

The cut is specific, not a policy of "fewer agents". Anthropic's guidance for
this model generation is explicit that a separate subagent asked to verify work
already done produces over-verification rather than better verification — so the
steps that only re-derive what this context knows are folded in, and the steps
that divide labour or carry knowledge you lack are left alone.

**Folding code quality in is an experiment, and it has a stated exit.** Measured
2026-08-23 over 62 runs: subagents build 82% of the context in a run, and cost
follows context built at r = 0.945 — so dropping one dispatch of three per task
is the largest single lever available. What it risks is review quality, and that
has a baseline to be judged against: 0.30 BUG specs per delivered spec since
2026-07-26. If that number climbs, revert the commit that inlined this step
instead of patching Step 5 — a review that needs propping up has already failed
the experiment.

## State tracking

Write `autopilot-state.json` (worktree root) after each step — helpers in
`.claude/scripts/autopilot-state.mjs`. Hooks read this file for the plan-before-code
gate, so a stale state file breaks the gate. Initialize with `initState()`, then
`setPlan()` once the planner returns the task list.

Per step, record: `coder` (files_changed), `tester` (`pass` | `fail_out_of_scope`),
`reviewer` (`approved`), `status` + `commit` hash, `diary`, `verify`.

---

## Step 1: CODER

```yaml
Task tool:
  subagent_type: "coder"
  prompt: |
    task: "Task {N}/{M} — {title}"
    ...
```

Returns `files_changed`.

---

## Step 2: TESTER

```yaml
Task tool:
  subagent_type: "tester"
  prompt: |
    files_changed: [{list}]
    task_scope: "{TASK_ID}: {description}"
    test_command: "node .claude/scripts/test-wrapper.mjs pytest {Test: files of this task} -q"
    # the task's own test files from the plan; the tester adds positional
    # selections from agents/tester.md and never widens to ./test fast
```

```
TESTER result?
├─ PASSED → Step 3
├─ FAILED (in-scope)
│   └─ debug_attempts < 3?
│       ├─ YES → [Debugger] → [Coder fix] → re-test
│       └─ NO  → ESCALATE (escalation.md)
└─ FAILED (out-of-scope) → log, continue to Step 3
```

**In-scope:** test file path contains any of the `files_changed` directories.

### Step 2a: Integration test check (conditional)

Fires when `files_changed` touches `src/infra/db/`, `src/infra/external/`, or
`src/domains/*/repository*`:

```
Integration test in tests/integration/ for the changed module?
├── YES, no mocks → continue
├── YES, has mocks → CODER removes mocks → re-test
└── NO             → CODER creates it → TESTER verifies → continue
```

### Step 2.5: Regression capture (conditional)

Fires when `debug_attempts > 0 AND tester == "pass"` — a real bug was found and fixed.

1. Take the `regression` field from the debugger's last fix output (missing → skip silently)
2. Dispatch coder: create `{regression.test_file}` with `{regression.test_code}`, touch nothing else
3. Verify: `pytest {test_file}::{test_name} -v` (or stack equivalent)

Test-only change — skips the review cycle. Lands in `tests/regression/` (immutable once created).

---

## Step 3: PRE-REVIEW CHECK

Deterministic checks before AI review — cheaper to catch the obvious here.

**3a — Code quality** (if `scripts/pre-review-check.py` exists):
`python scripts/pre-review-check.py {files_changed}`
Catches `# TODO`/`# FIXME`, bare `except:` without re-raise, files over 400 LOC (600 for tests).

**3b — Blueprint compliance** (if `ai/blueprint/system-blueprint/` exists):
`node .claude/scripts/validate-blueprint-compliance.mjs ai/features/{TASK_ID}*.md ai/blueprint/system-blueprint`
Catches type violations (float for money), import direction, domain placement, missing Blueprint Reference.

Either failing → CODER fixes → re-run that check. Either absent → skip it.
`precheck_loop < 2`? retry : ESCALATE — these checks are deterministic, so one
that still fails after two fixes is not going to pass on the third attempt; it
is a spec or an environment problem and belongs with a human.

---

## Step 4: SPEC COMPLIANCE — check it yourself

Re-read this task's requirements in `ai/features/{TASK_ID}*.md` and hold them
against `files_changed` and the diff. Two questions, both answerable from what
you already have:

- Is anything the task asked for **missing**?
- Is anything there that the task did **not** ask for?

```
├─ matches              → Step 5
├─ missing something    → CODER adds it → re-check
└─ extra beyond scope   → CODER removes it → re-check
                          spec_review_loop < 2? retry : ESCALATE
```

Quote the spec line and the file:line you are matching it against, for each
requirement. Naming both ends is what keeps this a check rather than a feeling —
and it is the same evidence a separate reviewer would have produced, at the
cost of re-reading a spec you have had in context since PHASE 1.

---

## Step 5: CODE QUALITY — run it yourself

Read `.claude/agents/review.md` and apply it to `files_changed`. That file is the
SSOT for what a code-quality review is here, whether a subagent or this loop
performs it — do not restate it, follow it. Run every bash check it names against
the real files; answering them from what you remember the coder doing is the
failure mode this step exists to catch. Those checks are `grep`/`wc`/the named
scripts — do not add pytest, architecture suites or project gates to the list, and
run the list once: a coder fix re-triggers only the check that failed (see "What the
loop never runs").

Emit its `## Output` YAML in your reply before routing, `checks_performed`
included. That list is the only thing separating a review from a nod, and inline
is where a nod is cheapest to give: you have been watching this task for six
steps and already believe it is fine. Approving with an empty or vague list is a
self-reject — run the checks instead.

Every finding carries `severity`, by the test the file states: would you revert
this commit for it?

```
├─ approved        → Step 6 (COMMIT — approved means proceed, not stop)
├─ needs_refactor  → refactor_loop < 2? CODER fixes BLOCKING findings → re-test → re-review : ESCALATE to Council
└─ needs_discussion → STOP, ask human (status: blocked)
```

**Only `severity: blocking` findings enter the refactor loop.** Advisory
findings are appended to the diary and left there — they do not justify a
second code → test → review cycle, and acting on them pulls the coder into
files the task never owned. A review that returns only advisories is
`approved`; if it returns `needs_refactor` with no blocking finding, treat that
as a malformed review and re-dispatch it once rather than refactoring.

---

## Step 6: COMMIT

```bash
git add {files_changed}
git commit -m "{type}({SPEC_ID}): {description}"
```

Subject format matters — the callback gate matches the subject line only. See
`.claude/agents/coder.md` § Commit Format for the exact contract.

If the commit fails: read the error (pre-commit hook? disk? lock?), fix if you can, retry
once. Still failing → set spec status to `blocked`, add "ACTION REQUIRED: commit failure"
to the spec, stop. **Never increment the task counter on a failed commit.**

After commit: log to the Autopilot Log in the spec, record `status: done` + commit hash in state.

---

## Step 6.5: DIARY RECORD (inline, no subagent)

Every task gets an index row — successes and problems both. Per ADR-007 the caller writes.

Append to `ai/diary/index.md`:

```
| {YYYY-MM-DD} | {TASK_ID} | {type} | {summary} | {debug_N} | {files_N} | pending |
```

Types: `success` (debug_attempts == 0), `problem` (debug_attempts > 0), plus extra rows for
`escalation`, `regression` and `advisory` when those happened.

`advisory` fires when Step 5 returned findings with `severity: advisory`. This is
where they come to rest — they were deliberately kept out of the refactor loop,
so the diary is the only record that they were ever seen. Write
`ai/diary/{YYYY-MM-DD}-{TASK_ID}-task{N}-advisory.md`:

```markdown
# {TASK_ID} Task {N}/{M} — advisory findings

| File:line | Finding | Suggested action |
|-----------|---------|------------------|
| {file}:{line} | {issue} | {action} |
```

One line per finding, verbatim from the review. No commentary — `/reflect`
decides whether a recurring advisory deserves a spec.

For `problem`, also write `ai/diary/{YYYY-MM-DD}-{TASK_ID}-task{N}-problem.md`:

```markdown
# {TASK_ID} Task {N}/{M} — {YYYY-MM-DD}

## Problem
- debug retry ×{debug_attempts}

## Context
- Error: {last_error_message}
- Files: {files_changed}
- Attempts: {what_was_tried}
- Resolution: {what_finally_fixed_it}

## Category
{code_bug | spec_gap | environment | architecture}
```

Keep entries factual and brief — what happened, not what it means. `/reflect` does the analysis.

### Lesson extraction (fires only when debug_attempts > 0)

Inline, best-effort — never block the commit if it fails.

1. **Domain** from `files_changed`: first `src/domains/<X>/` segment. None → skip silently.
2. **root_cause_class** from diary category + error keywords:

   | Category + keywords | root_cause_class |
   |---|---|
   | code_bug + money\|kopeck\|rub\|float | money-precision |
   | code_bug + lock\|race\|concurrent | race-condition |
   | code_bug + transaction\|atomic\|partial | atomicity |
   | code_bug + webhook\|duplicate\|idempotent | idempotency |
   | code_bug + fsm\|state\|slot\|stuck | fsm-deadlock |
   | code_bug + migration\|schema\|column | migration-drift |
   | architecture + import\|layer\|circular | cross-layer-import |
   | spec_gap + ssot\|duplicate\|sync | ssot-violation |
   | no match | diary category as-is |

3. **prevention_rule** — one sentence from the Resolution line.
4. **severity** — critical (P0 spec) / high (P1) / medium (P2).
5. **Next L-ID:** `ls ai/lessons/{domain}/ | grep -oE "L-[0-9]+" | sort -t- -k2 -n | tail -1`, +1, zero-pad to 3.
6. **Write** `ai/lessons/{domain}/L-{NNN}.md`:

```markdown
---
id: L-{NNN}
domain: {domain}
root_cause_class: {class}
severity: {severity}
created: {YYYY-MM-DD}
occurrence_count: 1
related: [{TASK_ID}]
---

# {root_cause_class}: {brief title}

## Prevention Rule
{one sentence}

## Context
{error, 1-2 sentences}

## Keywords
{comma-separated terms}
```

7. **Append** to `ai/lessons/index.jsonl`:

```json
{"id":"L-NNN","domain":"...","root_cause_class":"...","prevention_rule":"...","keywords":[...],"severity":"...","related":["TASK_ID"],"created":"YYYY-MM-DD","occurrence_count":1}
```

Skip if `index.jsonl` already has this TASK_ID. No lessons for out-of-scope test failures.

---

## Step 7: LOCAL VERIFY (conditional)

Fires when the spec has an `## Acceptance Verification` section with AV-* checks.
Absent or "N/A" → skip.

**7a Smoke** (AV-S* rows) → **7b Functional** (AV-F* rows). Each retries twice; smoke
failure warns and continues, functional failure sends CODER to fix, re-commit, retry.
Stop any processes the checks started.

**Non-blocking by design** — verification failures produce warnings in the Autopilot Log,
never block task progression.

Then: `current_task += 1` → back to Step 1. When `current_task > total_tasks` → PHASE 3 (`finishing.md`).

---

## Loop counters

| Counter | Limit | On limit |
|---|---|---|
| `debug_attempts` | 3 | Escalate (escalation.md) |
| `spec_review_loop` | 2 | Escalate to Council |
| `refactor_loop` | 2 | Escalate to Council |
| `precheck_loop` | 2 | Escalate (escalation.md) |
| `verify_smoke_retry` | 2 | Warn, don't block |
| `verify_func_retry` | 2 | Coder fix, then warn |

Reset at the start of each task.

---

## Status Writes — Forbidden

Autopilot never edits `**Status:**` in the spec or the status column in `ai/backlog.md`.
Final task closure emits `task_status` in the result_preview JSON; callback writes status.
See `finishing.md` § "Status Writes — Callback Only".
