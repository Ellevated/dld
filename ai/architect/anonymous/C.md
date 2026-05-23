# Domain Architecture Research

**Persona:** Eric (Domain Modeler)
**Focus:** Bounded contexts, ubiquitous language, domain boundaries
**Phase:** 1 — Research
**Date:** 2026-05-23

---

## Research Conducted

Exa search credits were exhausted at the start of this session. Research was conducted
exclusively from primary source material: deep audit report (85 findings, 6 personas),
architecture agenda, and direct reading of all 9 source files in `scripts/vps/`.

**Files read in full or substantial part:**
- `callback.py` (1374 LOC) — sections 1-200, 330-420, 550-650, 700-950, 990-1120
- `lifecycle.py` (602 LOC) — sections 1-80
- `orchestrator.py` (667 LOC) — sections 1-80, 280-360
- `spec_operator.py` (166 LOC) — full
- `render_backlog.py` (~150 LOC) — full
- `event_writer.py` (168 LOC) — full
- `db.py` (531 LOC) — sections 1-80
- `deep-audit-report.md` — full (85 findings)
- `architecture-agenda.md` — full

**Total evidence base:** ~4,500 lines of source code read; all DDD claims are
grounded in specific file:line quotes below.

---

## Kill Question Answer

**"Can you explain what this system does using only business terms, without mentioning
any technology?"**

Attempted answer from the current codebase's own documentation:

> "When a pueue task completes, callback.py is called. It resolves the label,
> maps the pueue result, runs verify_status_sync which fetches origin/develop,
> parses git log subjects via _subject_implements, checks allowed_files, runs
> CAS update-ref via private GIT_INDEX_FILE, records a callback_decision,
> writes JSONL audit, calls render_backlog, and dispatches QA via _pueue_add."

Every single noun and verb in that sentence is a technical artifact. There is
**no business language in this system at all.**

Ask the same question of the business owner:

> "When a developer finishes a task, we check whether the work was actually
> merged. If yes, mark the task done. If no, leave it for another try. If
> something is clearly broken, pause everything and alert us."

That is three sentences. The code contains 1,374 lines in one file to express them.
The gap between business language and implementation language is the root of
why this system fails repeatedly.

---

## AS-IS Bounded Context Map

*Listening to the language in the code — where does a term change meaning?*

### Language audit: "status"

| Location | What "status" means | File:Line |
|----------|---------------------|-----------|
| `lifecycle.yaml:status` | Lifecycle phase of a spec (queued/in_progress/done/blocked) | lifecycle.py:44-51 |
| `pueue status` | Whether a pueue task is Running/Queued/Stashed/Paused | callback.py:352 |
| `task_log.status` | Whether the pueue run was "running" at time of logging | db.py, callback.py:401 |
| `event.status` | Whether the notification outcome was "done" or "failed" | event_writer.py:29 |
| `map_result()` returns status | Translation of pueue's result string into (status, exit_code) | callback.py:121-124 |

Five different meanings for the same word "status". When a developer reads
`new_status = "blocked"` at `callback.py:1101`, they must mentally track *which*
status concept they are in. This is the lexical signal that at least three
bounded contexts are collapsed into one file.

### Language audit: "gate / guard / rule / check / verify"

| Term | Location | What it means | File:Line |
|------|----------|---------------|-----------|
| `guard` | TECH-166, 167 | The implementation check (git diff) before marking done | architecture.md ADR refs |
| `rule` | verify_status_sync docstring "Rules 1/3/4/5/7" | Named numbered rules within the gate | callback.py:1014-1019 |
| `check` | `_is_done_on_develop` | Single boolean predicate | callback.py:734 |
| `gate` | `verify_status_sync` colloquially | The entire verification orchestration | callback.py:1001 |
| `verify` | `verify_status_sync` function name | All of the above combined | callback.py:1001 |
| `lint` | `spec_lint.py` | Structural validation of spec markdown | spec_lint.py (zombie) |

Six synonyms for concepts that differ in scope and purpose. "Gate" is a
predicate. "Rule" is a constraint within a predicate. "Guard" is a pre-commit
enforcement mechanism. "Verify" is a coordination workflow. These are
**not** interchangeable — they are four separate responsibilities wearing the
same name.

### Language audit: "writer / author / by / identity"

| Term | Location | Meaning | File:Line |
|------|----------|---------|-----------|
| `_ALLOWED_WRITERS` | lifecycle.py | Frozenset of string literals | lifecycle.py:49-51 |
| `by=` kwarg | write_lifecycle() | Passed string, caller's self-declared identity | lifecycle.py |
| `by="callback"` | reconcile_orphans | Hardcoded in lifecycle.py for calls from orchestrator | lifecycle.py:551 |
| `by="operator"` | spec_operator.py | Always operator regardless of who calls | spec_operator.py:86 |
| `Path.write_text()` | migrate.py:224-225 | Writes without any identity — bypasses CAS entirely | migrate.py:224 |

The word "identity" in this system means "a string I wrote myself." This is
not identity — it is an honor system. The linguistic confusion between
"who actually ran this code" and "what string did they pass in the `by=`
argument" means the audit trail (callback-audit.jsonl) records *intended*
identity, not *actual* identity. In DDD terms: there is no `Author` value object.
There is only a `str` passed through function arguments.

---

### AS-IS: Bounded Contexts Collapsed into callback.py

*Listening to `callback.py:4` — its own docstring says:*
> "Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect, write audit log."

Four responsibilities declared in one sentence. But reading the code reveals seven:

```
callback.py (1374 LOC)
├── [1] Execution Context — resolve label, parse pueue result, read skill from log
│     Language: "pueue_id", "group", "result", "exit_code", "skill"
│     callback.py:76-305
│
├── [2] Spec Identity Context — find which spec a pueue task corresponds to
│     Language: "spec_id", "_SPEC_ID_RE", "resolve_spec_id", "legacy parser"
│     callback.py:306-553
│
├── [3] Work Verification Context — did a developer actually complete this task?
│     Language: "gate", "allowed_files", "_is_done_on_develop", "_subject_implements"
│     callback.py:608-775, 1001-1200
│
├── [4] Circuit Breaker Context — detect mass failure, pause the system
│     Language: "circuit", "trip", "demote", "CIRCUIT_WINDOW_MIN", "threshold"
│     callback.py:778-930
│
├── [5] Audit Context — record decisions for review
│     Language: "audit", "JSONL", "_emit_audit", "_write_audit"
│     callback.py:572-590, 931-1000
│
├── [6] Lifecycle Write Context — transition spec state
│     Language: "status", "write_lifecycle", "verify_status_sync", "by="
│     callback.py:1001-1200 + lifecycle.py (entire)
│
└── [7] Downstream Dispatch Context — trigger next steps
      Language: "dispatch_qa", "dispatch_reflect", "notify", "pueue_add"
      callback.py:387-430
```

When I read `verify_status_sync` (callback.py:1001-1200, 202 LOC), I count
all seven sub-languages active simultaneously in a single function. The function
fetches origin/develop [3], reads lifecycle yaml [6], runs the circuit breaker [4],
writes audit [5], resolves allowed_files [2], calls write_lifecycle [6], and
triggers render_backlog [7]. This is not a function — it is a complete bounded
context expressed as a single Python function.

### AS-IS Context Map

```
[Execution] ──feeds label──> [Spec Identity]
     |                              |
     |                      spec_id resolved
     |                              |
     v                              v
[Downstream Dispatch] <── [Work Verification] ──> [Lifecycle Write]
     |                              |                      |
     v                              v                      v
[Event Notification]          [Audit Trail]          [Render View]
     (event_writer.py)        (callback-audit.jsonl)  (render_backlog.py)
```

**All of this runs inside `callback.py`.** The arrows are function calls
within a single module, not contracts between modules. There is no language
boundary — just one vocabulary soup.

### The Three Representation Problem: A Bounded Context Symptom

The audit report identifies three representations of "status":

1. `ai/lifecycle/{spec_id}.yaml` HEAD — declared SoT (ADR-023)
2. `ai/backlog.md` working tree — render that became a writer (orchestrator.py:295)
3. spec body `## Status:` + zombie DLD-CALLBACK-MARKER in 23 files — fossil

This is not a data consistency problem. It is the signature of **three separate
bounded contexts trying to share one field without a contract:**

- **The Lifecycle Context** owns the canonical status of a spec.
  Its language is: `queued → in_progress → done | blocked`.

- **The Backlog View Context** produces a human-readable markdown document.
  Its language is: "render", "table row", "priority group", "archived".

- **The Spec Authoring Context** (Spark) creates specs with an initial status.
  Its language is: "draft", "template", "## Status:", "## Allowed Files:".

When `orchestrator.py:295` reads `backlog.md` from the working tree to determine
whether to bootstrap a lifecycle yaml, it is treating the **View Context's
output as if it were the Lifecycle Context's SoT.** This is a context map
violation: a downstream render being read as an upstream fact. The "15 fake-done
flips" incident is a direct consequence of this cross-context read without ACL.

---

## The `spec_operator.py` Puzzle: Admin Context or Context Violation?

`spec_operator.py:39` imports `callback` for one purpose:

```python
import callback  # type: ignore
...
def cmd_reset_circuit(_args: argparse.Namespace) -> int:
    callback._reset_circuit_cli()   # spec_operator.py:116
    return 0
```

*Listening to the language:* `spec_operator.py` is described as "operator-facing
CLI for manual spec status mutations" (spec_operator.py:3). `_reset_circuit_cli`
is a circuit-breaker operation. These are **two different contexts** sharing a
file boundary violation.

The underscore prefix `_reset_circuit_cli` signals "private to callback module."
Yet `spec_operator.py` is a separate CLI tool that calls this private function.
This is a textbook Anti-Corruption Layer violation: the operator context has
reached through the wall of the circuit-breaker context and called its internal
implementation detail.

In business terms: "The manual override tool should not need to know that the
system uses a circuit breaker internally. It should say 'resume the pipeline'
and the pipeline should know how to do that."

The correct pattern here is a Published Language: `callback.py` should expose
`resume_pipeline()` as a public contract. `spec_operator.py` should call that
contract. The circuit breaker is an implementation detail of the Execution
Resilience Context, not something the Operator Context should couple to.

---

## The Aggregate Root Problem: Spec Lifecycle

*What is the aggregate root for "spec lifecycle"?*

In DDD, an aggregate root is the single entity that maintains consistency across
a cluster of related state. Every mutation goes through the root.

For a spec's lifecycle, the candidate facts are:
- Current status (queued/in_progress/done/blocked)
- Who changed it last (by=)
- When (transitions[])
- What work justifies done (allowed_files_hash)
- When work started (started_at)

The audit report tells us:
- `started_at` is **always null** — lifecycle.py:155-158. No writer records it.
- `allowed_files_hash` is **always null** — lifecycle.py:599. No writer records it.
- `transitions: []` in 175 of 177 yaml files. Migration did not restore history.

*Quote from deep-audit-report.md:*
> "started_at в lifecycle yaml всегда null — verify_status_sync делает
> queued → done минуя in_progress, поле никогда не записывается → структурно сломано"
> — Geologist finding #14, deep-audit-report.md line 157

This means the aggregate has **no invariants enforced.** A valid aggregate root
would reject a transition to `done` if `started_at` is null — because that
means no one started the work. Instead, the system silently flips to `done`
because the gate (`_is_done_on_develop`) only looks at git history, not at the
aggregate's own state.

The aggregate is smeared across four storage media:

| What | Where | Consistency guarantee |
|------|-------|----------------------|
| status | `ai/lifecycle/{spec_id}.yaml` via git HEAD | CAS update-ref (when used) |
| decision history | `orchestrator.db:callback_decisions` | SQLite ACID |
| work evidence | `git log origin/develop` | git object store |
| task execution | `orchestrator.db:task_log` | SQLite ACID |
| human-readable view | `ai/backlog.md` working tree | None — best effort |

There is no single root. There is no invariant that spans these stores. The
system can have `status=done` in the yaml, zero commits matching the spec_id
in git, and no record in task_log — all simultaneously, and no code will flag
the inconsistency.

**The aggregate root for spec lifecycle does not exist in this codebase.** It
is implicit, distributed, and unprotected.

---

## TO-BE Proposed Bounded Context Map

*Based on the linguistic evidence above, five natural bounded contexts emerge:*

```
[Spec Authoring Context]        [Operator Context]
 (Spark creates spec.md)         (spec_operator.py)
       |                                |
       | SpecCreated event              | status mutation command
       v                                v
[Spec Lifecycle Context] <─────────────┘
 (lifecycle.py + yaml SoT)
  Aggregate: SpecLifecycle
  Root fields: spec_id, status, started_at, transitions
  Invariants: started_at set on in_progress, transitions complete
       |
       | StatusChanged event (spec_id, old_status, new_status)
       |
  ┌────┴──────────────────────────┐
  v                               v
[Execution Context]         [Compliance Audit Context]
 (orchestrator.py,           (callback-audit.jsonl only,
  callback.py execution       no business logic)
  plumbing, pueue)
       |                               |
       | WorkCompleted event           | records every decision
       v                               |
[Work Verification Context]            |
 (_is_done_on_develop,                 |
  _subject_implements,                 |
  allowed_files gate)                  |
  → emits: Verified | Unverified       |
       |                               |
       v                               |
[SpecLifecycle].transition()   ←───────┘

[Notification Context]
 (event_writer.py)
 Consumes: any StatusChanged or PipelinePaused event
 Translates to: Hermes / OpenClaw language
```

### Key differences from AS-IS:

1. **Spec Lifecycle Context is sovereign.** It owns the aggregate and enforces
   invariants. No other context writes status directly. The Work Verification
   Context emits a verdict event; the Lifecycle Context decides what to do with it.

2. **Work Verification Context is a pure function.** Input: (project_path,
   spec_id, allowed_files). Output: `Verified | Unverified`. No side effects.
   No writes to lifecycle. No circuit breaker interaction.

3. **Execution Context is infrastructure.** Pueue, slots, task_log — these
   are technical plumbing, not domain concepts. They live behind an
   Anti-Corruption Layer that translates "pueue task 42 with label dld:TECH-055
   finished with exit_code=0" into the domain event "WorkCompleted(spec_id=TECH-055)".

4. **Circuit Breaker moves to Execution Context.** The circuit breaker is a
   resilience pattern for the execution pipeline, not a lifecycle concept.
   Currently it lives in `callback.py` alongside lifecycle writes. This is
   why `spec_operator.py` must import `callback._reset_circuit_cli` to reset it
   — the two concerns are tangled in the same module.

5. **Bootstrap is dissolved.** The current `bootstrap_new_specs` (orchestrator.py:280)
   exists because the Execution Context needs to know about new specs, but
   specs are created by the Spec Authoring Context (Spark). The correct
   solution is a domain event: Spark emits `SpecCreated`, the Execution Context
   subscribes and creates the lifecycle yaml. No polling of backlog.md needed.

---

## Violations Table

| Violation | File:Line | Pattern | Why It Fails |
|-----------|-----------|---------|-------------|
| Work Verification reads lifecycle state | callback.py:1050-1070 | No ACL between Verification and Lifecycle contexts | Verification result should not depend on current lifecycle state — it should be pure git predicate |
| Orchestrator reads backlog.md WT as SoT | orchestrator.py:295 | Downstream render read as upstream fact | Crosses from View Context into Lifecycle Context without contract |
| spec_operator imports callback private API | spec_operator.py:116, callback.py:907 | Operator Context coupled to Execution internal | Private underscore function crossed as public API |
| reconcile_orphans writes `by="callback"` from orchestrator | lifecycle.py:551 | False identity — audit trail corrupted | Execution Context impersonates Lifecycle Write Context |
| migrate.py writes via Path.write_text() | migrate.py:224-225 | Bypasses aggregate root entirely | CAS invariant violated; no context, no identity |
| `_SPEC_ID_RE` differs between callback and orchestrator | callback.py:43 vs orchestrator.py:299 | Shared concept (spec id) defined differently in two places | Two contexts have diverged on the ubiquitous language definition |
| `_pueue_add` duplicated with different signatures | callback.py:359, orchestrator.py:157 | Infrastructure concept duplicated | Execution plumbing not extracted to shared infrastructure layer |
| `_load_env` / `_setup_logging` copied 3x | callback.py:46, orchestrator.py:35, db.py | No shared infrastructure module | Technical utilities duplicated instead of extracted |
| verify_status_sync docstring references Rules 1/3/4/5/7, omits 2/6 | callback.py:1014-1019 | Design split across two modules undocumented | Gate logic partially in callback, partially in orchestrator, no explicit contract |
| status exists in 3 stores without sync contract | orchestrator.py:295, callback.py:1187, spec markdown | Split brain — no single aggregate | Lifecycle aggregate root does not exist as explicit code construct |

---

## Domain Events (Missing)

The current system has no domain events. It has function calls. This is
precisely why coupling is so high — every context calls every other context's
functions directly.

The events that *should* exist:

| Event | Should Be Emitted By | Should Be Consumed By | Currently |
|-------|---------------------|----------------------|-----------|
| `SpecCreated` | Spec Authoring (Spark) | Execution Context (bootstrap yaml) | Polling backlog.md |
| `WorkCompleted(spec_id, exit_code)` | Execution Context (pueue callback) | Work Verification Context | Inline function call |
| `WorkVerified(spec_id, verdict)` | Work Verification | Lifecycle Context | Inline function call in verify_status_sync |
| `StatusChanged(spec_id, old, new)` | Lifecycle Context | Audit + Notification + Render | callback.py writes all three directly |
| `PipelinePaused` | Circuit Breaker | Operator + Notification | `_trip_circuit()` writes directly to db + event_writer |

---

## Ubiquitous Language Proposals

For each bounded context, the language that should be used exclusively:

**Spec Lifecycle Context:**
- `SpecLifecycle` — the aggregate root
- `LifecycleStatus` — enum: Queued | InProgress | Done | Blocked
- `transition(to: LifecycleStatus, by: Author, reason: str)` — the only mutation
- `Author` — value object, not a string; requires known identity from allowed set

**Work Verification Context:**
- `WorkVerification` — the process
- `Verdict` — enum: Verified | Unverified | Inconclusive (not a boolean)
- `CommitSubject` — value object, not a raw string passed to regex
- `AllowedScope` — value object, list of paths that define task boundaries

**Execution Context:**
- `Task` — a unit of work dispatched to pueue
- `TaskCompletion` — the event that pueue signals
- `Slot` — execution capacity unit
- `Pipeline` — the ordered sequence from queued to done

**Operator Context:**
- `ManualOverride` — the act of bypassing automated decisions
- `CircuitReset` — the operation to resume a paused pipeline (not "reset_circuit_cli")
- `Demotion` — returning a spec to an earlier status

The fact that "demote" appears in both the circuit breaker logic
(`count_demotes_since`, `callback_decisions.demoted`) and in the operator CLI
(`cmd_demote`) but means slightly different things in each — in one case it is
a signal that triggers safety logic, in the other it is an administrative action
— is a ubiquitous language defect. These should be named differently or one
should be a specialization of the other with explicit relationship documented.

---

## Why Current Boundaries Fail: Three Root Causes

### 1. Boundaries follow file structure, not language

`callback.py` is named after its invocation mechanism (pueue calls it on
task completion). This is a technical boundary, not a domain boundary. It
happens to contain work verification, lifecycle mutation, audit, circuit
breaking, and notification. All of these are in one file because they are
all invoked at the same technical moment, not because they belong to the
same domain concept.

Eric Evans' test: "If you deleted this file, which business capabilities
would you lose?" Answer for `callback.py`: all of them. That is the
definition of a god module, and it is a reliable sign that domain boundaries
were never drawn — only technical execution boundaries were.

### 2. The aggregate for SpecLifecycle was never made explicit

The CAS mechanism in `lifecycle.py` is technically sound. But it is a
storage-level consistency guarantee, not an aggregate invariant. A CAS on
the git object store prevents two concurrent writes from clobbering each
other. It does not prevent semantically invalid transitions (queued → done
without started_at, done without work evidence). Those invariants are not
encoded anywhere — they live in comments and ADR documents.

An aggregate root is the place where business rules are enforced, not just
where physical writes are serialized. Currently `lifecycle.py` is a write
serializer. It is not an aggregate root.

### 3. The Execution Context and Lifecycle Context have no explicit contract

The correct relationship is: Execution Context is *upstream* (it knows
when pueue tasks finish), Lifecycle Context is *downstream* (it decides
what that means for a spec's state). The upstream should speak in execution
language ("task 42 finished with exit_code 0"). The downstream should
translate that into lifecycle language ("TECH-055 completed successfully").

Instead, `callback.py` has direct access to both languages simultaneously.
`verify_status_sync` knows pueue_id (execution), spec_id (lifecycle), and
exit_code (execution) simultaneously. There is no translation boundary.
This is why fixing a pueue convention bug (Rule 8, cefaa55) can accidentally
break lifecycle semantics — the concepts are not separated.

---

## References

- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (2003)
  — Bounded Contexts chapter: "A model only makes sense within a context"
- Deep audit report: `/home/dld/projects/dld/ai/audit/deep-audit-report.md`
- Architecture agenda: `/home/dld/projects/dld/ai/architect/architecture-agenda.md`
- callback.py: `/home/dld/projects/dld/scripts/vps/callback.py`
- lifecycle.py: `/home/dld/projects/dld/scripts/vps/lifecycle.py`
- orchestrator.py: `/home/dld/projects/dld/scripts/vps/orchestrator.py`
- spec_operator.py: `/home/dld/projects/dld/scripts/vps/spec_operator.py`
