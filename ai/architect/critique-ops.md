# Operations Architecture Cross-Critique

**Persona:** Charity (Operations Engineer)
**Phase:** 2 — Peer Review
**Date:** 2026-05-23
**System under review:** scripts/vps/ orchestrator/callback/lifecycle contour

---

## Peer Analysis Reviews

### Analysis B — Neal (Evolutionary Architect)

**Agreement:** AGREE — strongest peer analysis from an ops perspective

**Reasoning from ops perspective:**

B is the only peer who builds executable tests alongside the analysis and asks
the exact right ops question: "what fitness functions protect this architectural
decision?" The answer — none, or inverted — is the correct diagnosis.

The fix-train detector (`check_fix_train.py`) is exactly what I would build after
an incident like this. Five iterations of fixes on one file in 30 days IS the signal.
That is your leading indicator. Not "how many bugs did we find" but "how many times
did we touch this file in response to an incident." If `git log --grep=fix
scripts/vps/callback.py` returns 12 commits in 30 days, you do not add another fix.
You call a post-mortem.

The FF-07 (commit convention test that currently fails) is the right artifact. Making
a test fail in CI because `_subject_implements` rejects 460 out of 636 real commits
is not a test failure — it is the CI finally telling you what production has been
trying to tell you for weeks. B's approach of "make the test fail NOW, then track
passing it as the acceptance criterion" is textbook SRE incident response.

**Missed gaps from ops lens:**

- B's fitness functions are all static analysis or unit-level checks. There is no
  discussion of what fires at 3 AM. The `check_fix_train.py` script is a health
  signal, but it outputs to a shell. Who reads it? When? There is no alerting path
  from the fitness function to an on-call human or Hermes notification. Without
  that path, the signal exists but does not reach the responder.

- FF-04 (all test dirs in CI) is important but B frames it only as "makes 100 tests
  runnable." The operational framing is stronger: those 100 tests currently do NOT
  protect callback.py. Any commit that breaks callback behavior right now can land
  on develop and stay there until a human notices. That is not a test coverage issue;
  that is a production protection issue.

---

### Analysis C — Eric (Domain Modeler)

**Agreement:** PARTIAL AGREE

**Reasoning from ops perspective:**

C correctly identifies that five different meanings of "status" in one codebase is a
diagnostic problem. When you are paged at 3 AM and you grep for "status" in the logs,
you get noise from all five contexts. That is not just DDD philosophy — it is a real
debuggability failure.

The observation that `verify_status_sync` is simultaneously in the Execution Context
AND the Lifecycle Context is operationally important. When that function fails, the
logs are ambiguous: did pueue fail, or did the lifecycle write fail? Those require
different responses. You cannot triage from the current log output because the same
function is doing both.

The proposed event model (SpecCreated, WorkCompleted, WorkVerified) is sound from an
ops perspective specifically because events are observable. You can set up an alert on
"WorkVerified but no StatusChanged within 30s." You cannot set up that alert against
the current inline function-call architecture.

**Missed gaps from ops lens:**

- C says nothing about what breaks at 3 AM. The bounded context diagram is clean but
  it does not address the operational question: in the TO-BE world, if a StatusChanged
  event is emitted but the Notification Context fails to consume it, how long before
  someone knows? The event-sourcing proposal trades one class of silent failure (inline
  function calls with bare except) for another (unconsumed events). Both are silent.

- The `started_at` always-null finding is mentioned but the ops implication is skipped.
  When you have an SLI for "spec cycle time" (how long from queued to done), a null
  `started_at` means your SLI metric is broken and you do not know it. You are reporting
  zero cycle time for specs, which looks great in dashboards and is completely wrong.

---

### Analysis D — Erik Schluntz (LLM Architect)

**Agreement:** AGREE — strongest companion to B from an ops lens

**Reasoning from ops perspective:**

D's silent failure catalogue (section 6.2) is exactly the kind of analysis I do after
an incident. The ratio — 2 of 8 failures produce findable agent signals — is the
production readiness verdict on this system. A system where 75% of failure modes are
invisible is not production-ready, regardless of what the architecture diagrams look like.

The `vps-orch.py gate-check SPEC-ID` dry-run tool proposal is the single most
operationally valuable concrete proposal in all seven analyses. Right now, if a spec is
stuck blocked, the debugging path is:

1. Find the lifecycle yaml (know the path format)
2. Read it manually
3. Find the audit JSONL
4. Grep for the spec_id across potentially thousands of lines
5. Interpret the reason string (free text, not enum)
6. Run git log manually to verify

That is a 15-minute debugging path for a simple question. D proposes collapsing it to
one CLI call that returns structured JSON. That is the 3 AM fix. When you are paged at
3 AM, you do not want to construct shell pipelines. You want a tool that answers "why
is this blocked?"

The `BOOTSTRAP_ANOMALY: 15 lifecycle yaml created in 30s` warning (section 6.1) is
operationally precise. This is the alert that would have surfaced the incident at 11:19
instead of 16:00. Four hours and forty-one minutes of MTTD reduction from one
`log.warning` call with a threshold check. That is concrete.

**Missed gaps from ops lens:**

- D focuses heavily on agent ergonomics but light on human on-call ergonomics. The
  `vps-orch.py` tools are excellent for an agent debugger. But the on-call human at
  3 AM needs a dashboard or a Hermes message, not a CLI. D does not propose how the
  structured gate output flows into an observable surface.

- The error taxonomy (InfrastructureError, ConfigurationError, GateEvaluationError,
  LifecycleWriteConflict, DataIntegrityError) is correct, but D does not map each error
  class to an alert severity. InfrastructureError should auto-retry silently.
  ConfigurationError should page the on-call immediately — it means the system is
  misconfigured and no amount of retrying will fix it. DataIntegrityError should pause
  the pipeline and page. This mapping is the runbook, and it is missing.

---

### Analysis E — Dan (DX Pragmatist)

**Agreement:** PARTIAL AGREE — directionally correct, too aggressive on migration

**Reasoning from ops perspective:**

E's "innovation token" accounting is a useful mental model. From an ops perspective,
every "innovative" technology choice is also an ops burden: it has custom failure modes,
custom debugging procedures, and custom runbooks. The git-as-DB choice (ADR-023) has
at least four unique failure modes that do not exist in SQLite: stale-index race, CAS
retry exhaustion, push failure, and stale WT read. Each of those requires a different
debugging path. You cannot use "check if the database is up" as a health check — you
have to know about git object store consistency, private GIT_INDEX_FILE semantics, and
`git update-ref` CAS semantics.

E's 1-rule gate proposal (`git log origin/develop --grep SPEC-ID`) is operationally
attractive because it is debuggable by any engineer who knows git. The current 8-rule
gate requires knowing the specific regex in `_subject_implements`, the convention
history of awardybot, the circuit-breaker state, the `started_at` null behavior — none
of which appear in the logs.

**Missed gaps from ops lens:**

- E proposes migrating lifecycle state to SQLite in Wave 2 as a "boring" alternative.
  This is correct in principle but the operational risk of this migration is understated.
  You currently have 190+ lifecycle YAML files in git with a CAS write history. If you
  migrate to SQLite and the migration fails halfway through (partial state migration),
  you have split-brain between the old git state and the new SQLite state with no
  automatic reconciliation. E does not address the migration failure mode at all.
  ADR-023 at least has the property that a failed write leaves the old state intact
  (CAS failure = no write). A half-migrated SQLite schema does not have this property.

- The SQLite proposal makes single-machine observability easier (SQL queries are instant,
  no git log parsing) but makes multi-node visibility harder. E correctly notes that
  multi-machine may be theoretical. If it ever becomes real, you need a plan. E proposes
  "periodic backup to git" as the answer — that is hand-waving on an ops-critical
  question. What is the RPO on that backup? What is the reconciliation procedure when
  the backup is stale?

---

### Analysis F — Martin (Data Architect)

**Agreement:** PARTIAL AGREE — excellent on schema, underweights operational failure modes

**Reasoning from ops perspective:**

The SoR conflict table (what is declared SoT vs what the code actually reads) is the
most useful single table in all seven analyses from an operational standpoint. When you
are debugging a false-done flip at 3 AM, you need to know which of three representations
is "real." Right now, that question has no documented answer. F makes it explicit.

The `blocked_code` enum proposal (orphaned_crash, gate_reject, circuit_open,
manual_hold, qa_fail, convention_miss) directly enables the SLI dashboard I would want:
"what percentage of blocked specs are blocked due to convention_miss vs actual gate
failures?" Right now that query is impossible because blocked_reason is free text. With
an enum, you can alert on "convention_miss rate > 10% in the last hour" — which is
exactly the leading indicator for the false-blocked problem.

The `dispatched_at` rename (from `started_at`) is operationally correct. You cannot
compute mean time from dispatch to completion with a field that is always null. That
is your SLI for pipeline throughput, and it is broken.

**Missed gaps from ops lens:**

- F proposes Wave 0 through Wave 3 data migrations but does not address the rollback
  procedure for any of them at the operational level. "Rollback mechanism: revert
  orchestrator.py commit" is a code-level answer. The ops question is: if Wave 0.1
  (killing bootstrap_new_specs) is reverted at 2 AM because it caused a regression,
  what happens to the 15 specs that were already bootstrapped incorrectly? Do they get
  cleaned up? How? That is the operational gap in the migration plan.

- The PRAGMA user_version proposal is correct, but F does not address what happens if
  the orchestrator starts and finds a database at version 3 when the code expects version
  5. The current code (process-global flag) would re-apply migrations. With PRAGMA
  user_version, a version mismatch means the code either refuses to start or applies
  migrations automatically. F describes the happy path but not the operational procedure
  for "we deployed a new version of the code and the DB migration failed."

---

### Analysis G — Fred (Devil's Advocate / Brooks)

**Agreement:** PARTIAL AGREE — philosophically correct, operationally vague

**Reasoning from ops perspective:**

G's most important observation is not architectural — it is operational: the incident
took from 11:19 to 16:00 to detect. That is 4 hours and 41 minutes of undetected
production failure. G cites this but does not frame it as the ops verdict it is. A
system that fails silently for 4 hours and 41 minutes does not have an architecture
problem — it has an observability problem. The architecture problems created the failure
mode, but the 4:41 gap is a pure observability gap.

G's 0-rule callback design (section II) is operationally important because it isolates
the gate into a separate, independently observable process. A 60-second polling daemon
has a health check endpoint. A callback script called by pueue does not. "Is the gate
running?" is currently unanswerable without pueue integration knowledge. In a separate
gate.py daemon, it is `systemctl status gate.service`.

The Evaporating Cloud (section VIII) correctly identifies that the perceived binary
choice (patch vs rewrite) is false. But from an ops perspective, the constraint is not
"rewrite cost" — it is "who absorbs production risk during the transition?" G does not
address this. A strangler fig migration means running two gate implementations in
parallel. What is the consistency strategy during that period? If both gates disagree
on a spec's status, which wins?

**Missed gaps from ops lens:**

- G's "gate.py polls every 60 seconds" proposal is architecturally clean but introduces
  a new failure mode: what happens if gate.py fails silently? Right now, callback.py
  runs synchronously in response to every pueue completion event. If it fails, pueue
  records a non-zero exit code (or catches exit 0 with an error log). Gate.py as a
  daemon can die silently between poll cycles and nothing will notice until specs stop
  transitioning. G needs a health check + alert for gate.py.

- The "60-second delay is acceptable" argument is made on the basis that the current
  system had 4:41 detection latency. That comparison is correct but the implication is
  wrong: 60 seconds is acceptable for STATUS detection, but what is the latency for
  QA/reflect dispatch? Currently those fire synchronously after verify_status_sync.
  In G's model, the gate polls every 60s and presumably fires dispatch after detecting
  done status. If a spec finishes at 11:19:01 and the gate polls at 11:19:00 and then
  again at 11:20:00, QA dispatch happens at 11:20:00 — a 59-second delay on QA. At
  high volume (10 projects, rapid completions), this creates a 59-second pipeline
  stall per task. G should address the dispatch latency implication.

---

### Analysis H — Bruce (Security Architect)

**Agreement:** PARTIAL AGREE — security findings are correct, ops implications overstated

**Reasoning from ops perspective:**

H's TELEGRAM_BOT_TOKEN exposure is correctly identified as P0. But from an ops
perspective, the reason it is P0 is not primarily security — it is operational
integrity. If an attacker is reading all bot messages, they have full visibility into
what the operator is doing with the pipeline. That is an ops confidentiality issue as
much as a security issue.

H's audit JSONL HMAC proposal (section data protection) is an ops win beyond the
security win. If every audit line has an HMAC and you find a line without a valid HMAC,
you know exactly when the log was tampered with (the break in the chain). That is
forensic capability, not just prevention. After the 4:41 undetected incident, being
able to answer "was this log entry written by the callback or by something else?" is
operationally valuable.

The git plumbing timeout proposal (P1 DoS fix) is the most immediately actionable
security recommendation from an ops standpoint. An unresponsive `git push` silently
holding `_write_lock` is also an ops incident: all subsequent pueue completions queue
up, slots are not released, the orchestrator effectively stalls. Timeout=30 in
`lifecycle.py:_run()` is a two-line change that prevents a class of operational stalls.

**Missed gaps from ops lens:**

- H identifies the backlog.md WT read as "an active exploit path" (P0) but frames it
  primarily as a security attack vector. The operational framing is equally important:
  this is not a theoretical attack — it happened today, at 11:19, and produced 15
  false-done transitions that were undetected until 16:00. The mitigation (read from
  HEAD instead of WT) is the same regardless of whether you frame it as security or ops,
  but the priority justification is stronger when you cite the actual incident.

- H's defense-in-depth Layer 4 (alert when bootstrap creates > N yamls) is exactly
  right but buried. This should be the headline recommendation from a security+ops
  perspective: the one control that would have caught today's incident is a threshold
  alert on mass-bootstrap events.

---

## Convergence

All seven analyses converge on the following points, and the convergence is itself
evidence of production-readiness issues:

**C1: bootstrap_new_specs reads dirty WT — must die.**
B, C, D, E, F, G, H all identify `orchestrator.py:295` as the root cause of the 15
fake-done flips. No peer defends this code path. This is the clearest P0 consensus
in the entire council.

**C2: callback.py at 1374 LOC is the central source of ops brittleness.**
Every analysis notes this. The reasons differ (domain boundaries for C, agent ergonomics
for D, innovation tokens for E, DDIA for F, Brooks conceptual integrity for G, attack
surface for H) but the verdict is unanimous.

**C3: scripts/vps/tests/ not in CI is a one-line fix with maximum ops return.**
B, D, E identify this. From an ops perspective: you are running 100 tests manually that
CI does not run. Every deploy to develop happens without that test safety net. This is
the cheapest production protection improvement available.

**C4: _push_best_effort at DEBUG is a monitoring anti-pattern.**
B, D, E, F, G all flag this. Multi-machine convergence failures are invisible. This is
not a "nice to have" — it is a broken alert that should be firing and is not.

**C5: _subject_implements at ~28% accuracy for awardybot is a systematic false-blocked
generator.**
B, C, D, E, F, G, H all identify this in some form. The gate is producing wrong
outcomes at production scale.

---

## Divergence

**D1: SQLite vs git as lifecycle SoT.**

E (Dan) argues strongly for migrating to SQLite — the "boring" choice. G (Fred)
also leans SQLite by implication (simpler, fewer failure modes). B (Neal) accepts
ADR-023 git-YAML and argues for fixing the implementation bug rather than replacing
the design. F (Martin) works within the git-YAML framework and proposes schema
improvements to it.

From an ops perspective: the git-YAML approach has unique failure modes (CAS retry
exhaustion, stale-index race) that SQLite does not have. But SQLite-as-SoT has its own
failure modes that git-YAML avoids: a corrupt SQLite file is not recoverable by git
history alone. A corrupt lifecycle YAML git tree IS recoverable — `git fsck` and the
commit history are your backup. The divergence is real and has operational substance.

**D2: "60-second gate polling" vs "synchronous callback gate."**

G proposes separating the gate into a polling daemon. D (Erik) implicitly supports this
via the `gate-check` dry-run tool concept. B, C, E, F, H work within the synchronous
callback model. From an ops perspective, the polling daemon has better isolation but
worse latency guarantees and requires its own health monitoring. This is a genuine
design trade-off, not a clear win either direction.

**D3: Complexity of circuit breaker.**

E argues the circuit breaker is justified ("innovation token: keep"). G argues it should
be simplified to a log warning + alert, not a pueue pause. B accepts it as a useful
operational control. From an ops perspective: a circuit breaker that pauses the entire
orchestrator when triggered is a blunt instrument that converts a data problem (mass
false-done) into an availability problem (nothing runs). A warning + alert preserves
observability without adding a second failure mode.

---

## Ranking: Top 3 Proposals by Ops Leverage

**Rank 1: D (Erik / LLM Architect)**

Reason: D is the only peer who explicitly addresses the MTTD problem (from 11:19 to
16:00) and proposes concrete operational tooling to close it. The `vps-orch.py status`
CLI, the `BOOTSTRAP_ANOMALY` threshold warning, and the silent failure catalogue
(section 6.2) are directly actionable runbook components. D's proposals reduce MTTD
from 4:41 to minutes for the specific incident class that occurred today.

**Rank 2: B (Neal / Evolutionary Architect)**

Reason: B's fitness functions are executable and immediately deployable. The fix-train
detector is a leading indicator that does not exist anywhere else in the seven analyses.
A system where "more than 3 incident commits to callback.py in 30 days" triggers a
mandatory architect review is a system that self-signals architectural distress before
the next incident. FF-07 (convention tests that currently fail) makes the false-blocked
problem a CI gate rather than a production surprise.

**Rank 3: E (Dan / DX Pragmatist)**

Reason: E's 1-rule gate proposal (`git log origin/develop --grep SPEC-ID`) reduces the
debuggability surface from 8 inference rules to 1 verifiable git command. Any on-call
engineer can run that command. You cannot run `_subject_implements` manually in the
current system — it is an internal function with no CLI exposure. Ops observability
is proportional to the debuggability of individual components.

---

## Ops-Specific Analysis

### Which proposals are HARDER to debug in production than current state?

**G's 60-second polling gate.py daemon:**

The current callback.py runs synchronously and exits. If it fails, pueue records it.
A polling daemon can fail silently between cycles with no pueue visibility. If gate.py
crashes at 11:20 and no one checks until 16:00, specs sit in `in_progress` forever —
the same MTTD problem that occurred today, now applied to the gate process itself.
G's proposal requires gate.py to have its own health monitoring (systemd service,
heartbeat alert) before it is operationally equivalent to the synchronous callback.
Without that monitoring, it is harder to debug, not easier.

**C's event-sourcing domain events:**

Emitting domain events (SpecCreated, WorkCompleted, WorkVerified, StatusChanged) adds
an asynchronous consumption path between status determination and status recording.
If a StatusChanged event is emitted but the consumer fails, the spec status is not
updated. That failure is silent by default. The current synchronous inline path has
the same silent-failure problem (bare except) but at least the failure occurs in a
single traceable code path. With events, you need to trace across the event bus,
check consumer lag, verify delivery. C's proposal adds operational complexity without
addressing the observability gap that makes the current system hard to debug.

**H's HMAC audit JSONL:**

This is the right idea operationally (tamper-evident logs are essential for forensics)
but the implementation adds a new failure mode: if the HMAC key is rotated, all existing
audit entries fail validation and `scan_queued` drops them. H does not address key
rotation procedure. A HMAC implementation without a documented key rotation runbook is
a future 3 AM incident.

### Which proposals would have caught the incident at 11:19 vs 16:00?

**Would have fired at 11:19 (within minutes of the incident):**

1. D's `BOOTSTRAP_ANOMALY: N lifecycle yaml created in 30s` warning. This fires
   immediately when bootstrap creates > 5 yamls in rapid succession. The 15 fake-done
   flips would have produced this warning at the moment they occurred.

2. B's FF-07 (convention test suite that currently fails). This does not prevent the
   bootstrap incident directly, but running `scripts/vps/tests/` in CI (FF-04) would
   have caught the bootstrap_new_specs WT read bug if a test existed for it. B's
   FF-06 (incident regression bank) explicitly proposes `test_bootstrap_new_specs_skips_done_specs`
   as the required test.

3. H's alert: "bootstrap creates > N yamls in one pass." H proposes this in Layer 4
   but it is essentially the same alert as D's.

**Would have reduced detection from 16:00 to ~hours:**

4. Any of the proposals that upgrade `_push_best_effort` from DEBUG to WARNING. If git
   push failures were logging at WARNING, the operator would have seen anomaly signals
   sooner — though not necessarily within minutes.

**Would NOT have caught this incident regardless:**

- B's LOC fitness function (FF-01) — the incident is not about LOC.
- C's bounded context decomposition — the incident is caused by a specific code path
  (WT read in bootstrap), not by bounded context violations.
- E's SQLite migration — the incident would still occur if bootstrap read dirty WT
  from an SQLite source.
- H's TELEGRAM_BOT_TOKEN rotation — entirely unrelated to the bootstrap incident.

### Are any peers adding silent failure modes?

**Yes: C's event model without delivery guarantees.**

If StatusChanged events are emitted but not consumed (consumer crash, queue full,
delivery timeout), the spec status is never updated. C does not propose a delivery
guarantee mechanism (at-least-once delivery, dead letter queue, consumer health check).
The current synchronous call is bad (bare except, no retry) but the failure is locally
visible. An unconsumed event is invisible without event bus monitoring.

**Potentially: F's `dispatched_at` field rename.**

F proposes renaming `started_at` to `dispatched_at` and setting it on pueue dispatch
rather than on in_progress transition. This is a schema change. If the migration runs
partially (some yamls updated, some not), you have a mixed schema in production. Reads
that check `dispatched_at` will find null on old yamls (because the field was formerly
`started_at`). F's rollback procedure for this is "revert code to use `started_at`" —
but the old yamls that were already renamed to `dispatched_at` will then return null on
every read. F should address the mixed-schema operational window.

---

## One Thing Peers Missed About Operability

**No peer proposed SLOs.**

Seven analyses identify failure modes, propose fixes, debate architecture — but not a
single analysis defines what "healthy" looks like quantitatively. An SLO is not a
philosophical statement. It is an operational contract: "99.X% of task completions
produce a correct lifecycle transition within Y seconds."

For this system, the SLIs that matter are:

| SLI | What it measures | Target |
|-----|-----------------|--------|
| Gate accuracy | % of correct lifecycle transitions (no false-done, no false-blocked) | 99.5% |
| MTTD on false-done | Time from first fake-done to detection alert | < 5 minutes |
| Gate latency | Time from pueue completion to lifecycle write | < 30 seconds (p99) |
| Commit recognition rate | % of commits on develop correctly matched by gate | > 99% |

None of these SLIs are currently measurable. The gate accuracy metric requires the
`blocked_code` enum (F's proposal). The commit recognition rate requires the audit JSONL
to record `commits_scanned` and `commits_matched` counts (D's `GateResult` dataclass).
MTTD on false-done requires the bootstrap threshold alert (D's section 6.1).

Without SLOs, you cannot define what "fixed" looks like. The 8-rule redesign (cefaa55)
was shipped without an SLO for gate accuracy. If it had been shipped with "gate accuracy
must be > 99% on a representative commit sample" as an acceptance criterion, the
trajectory convention test (FF-07 in B's analysis) would have been required before
deploy, and the false-blocked problem on awardybot/dowry would have been caught in
CI rather than discovered through a 4-hour production incident.

**The specific SLO I would commit to as an acceptance criterion for the gate rewrite:**

`_subject_implements` or its replacement must correctly classify ≥ 99% of commits
in a golden test dataset containing both canonical-scope commits and trailer-convention
commits from all managed projects. This dataset must be version-controlled and run in
CI. Any gate change that regresses below 99% accuracy on this dataset is blocked.

Without this SLO, the fix-train will resume. The next gate redesign (call it cefaa56)
will optimise for a different subset of commit formats and break a third. The only way
to stop the cycle is to define what "correct" means numerically before writing the code.

---

## Revised Position

**Revised Verdict:** Refined from Phase 1

**Change Reason:**

Reading seven analyses confirms the ops gaps I would have flagged independently
(MTTD too long, no leading indicators, silent failures dominate) but adds two
refinements:

1. The fix-train pattern (B) is a better leading indicator than any individual alert.
   I would add fix-train monitoring to my ops toolkit.

2. The `vps-orch.py gate-check` dry-run tool (D) is the single highest-leverage ops
   improvement available. It makes the gate debuggable without side effects — something
   that currently does not exist and costs about 80 lines of Python.

**Final Ops Recommendation:**

**P0 (before next callback/lifecycle commit):**
- One line: `pyproject.toml testpaths` adds `scripts/vps/tests`
- Five lines: `bootstrap_new_specs` reads HEAD not WT (or kills the function)
- One line: `_push_best_effort` promoted from DEBUG to WARNING
- Five lines: `bootstrap_new_specs` fires `log.warning BOOTSTRAP_ANOMALY` if `created_count > 3`

These four changes are the minimum viable ops improvement. They close the MTTD gap
for the specific incident class that occurred today and provide the basic observability
foundation everything else builds on.

**P1 (within this sprint):**
- `vps-orch.py status SPEC-ID` CLI (D's proposal, ~50 LOC)
- Fix-train detector integrated with Hermes alert (B's proposal, ~30 LOC)
- blocked_code enum field in lifecycle YAML (F's proposal)
- Add `commits_scanned`/`commits_matched` to audit JSONL (enables gate accuracy SLI)

**P2 (architectural sprint):**
- Gate accuracy SLO defined and enforced in CI via golden dataset test (the missing SLO)
- B's convention test suite (FF-07) — makes gate regression a CI failure
- D's full `vps-orch.py` CLI suite with structured gate output

The architectural questions (SQLite vs git-YAML, polling gate vs synchronous callback,
domain event model) are real but secondary. You cannot architect your way out of a
4-hour MTTD. Fix the observability first. Then redesign from a position of visibility.

---

## References

- Peer analyses B through H (anonymized): `/home/dld/projects/dld/ai/architect/anonymous/`
- Deep audit report: `/home/dld/projects/dld/ai/audit/deep-audit-report.md`
- Architecture agenda: `/home/dld/projects/dld/ai/architect/architecture-agenda.md`
- callback.py (1374 LOC): `/home/dld/projects/dld/scripts/vps/callback.py`
- lifecycle.py (602 LOC): `/home/dld/projects/dld/scripts/vps/lifecycle.py`
- orchestrator.py (667 LOC): `/home/dld/projects/dld/scripts/vps/orchestrator.py`
