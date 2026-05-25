# Evolutionary Architecture Cross-Critique

**Persona:** Neal (Evolutionary Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-05-23
**Scope:** scripts/vps/ contour — 7 peer analyses (A, C, D, E, F, G, H)

---

## Research Basis

All claims below are grounded in direct codebase evidence read during the peer analyses
and anchored to specific file:line references from the codebase. External search was
unavailable (Exa 402) — the code IS the primary evidence.

---

## Peer Analysis Reviews

### Analysis A — Charity (Operations Engineer)

**Agreement:** AGREE

**Reasoning from evolutionary perspective:**

A is the closest to producing actual fitness functions. The metrics catalog (M-01 through
M-15) reads like a partial fitness function suite: specific, measurable, automatable.
The SLO-4 (Bootstrap Accuracy) is the most important one from an evolutionary lens —
it directly protects the `bootstrap_new_specs → lifecycle.yaml` architecture decision
made in ARCH-186.

From a change-vector perspective, A correctly identifies the "5 incidents, same pattern"
trajectory. This is a textbook evolutionary architecture signal: the failure mode is
repeating because there is no automated check to prevent re-occurrence. Each incident
adds prevention code but no fitness function. The codebase is accreting rules without
accreting their protection.

The ALERT-001 proposal (mass-bootstrap-as-done rate > 3 in 5 minutes) would have
been a genuine fitness function protecting ADR-023's invariant. Today it does not
exist. ARCH-186 introduced lifecycle.yaml as SoT but produced zero automated checks
that this SoT remains the sole source. The drift happened immediately.

**Missed gaps from evolutionary lens:**

- A catalogs metrics but does not articulate which metrics ARE fitness functions vs
  which are operational dashboards. Fitness functions protect architectural decisions;
  monitoring dashboards detect symptoms. M-12 (bootstrap_volume_per_cycle) is a fitness
  function for ADR-023. M-09 (poll_cycle_duration) is an ops metric. The distinction
  matters for ownership: fitness functions go in CI/CD, dashboards go in ops.
- A does not address the change vector: what is going to change next that the ops
  stack is NOT ready to observe? Answer from code: `scan_queued` in orchestrator.py
  uses callback-audit.jsonl as anti-recency signal. This is an undocumented coupling
  that no alert covers. When it breaks, it will be as invisible as today's incident.
- The "minimum viable ops hardening" (~160 LOC) is correctly scoped for LLM-native
  execution, but A doesn't distinguish between one-off fixes and architectural
  protections. Paying the 160 LOC debt once is not enough if the next ADR produces
  another unobservable path.

---

### Analysis C — Eric (Domain Modeler)

**Agreement:** AGREE — particularly strong on the ACL violation diagnosis

**Reasoning from evolutionary perspective:**

C identifies the evolutionary architecture root cause that others approach obliquely:
the lack of bounded context boundaries means every change to the system touches
everything. This is the primary driver of the 5-incident pattern. When Work
Verification, Lifecycle Write, Circuit Breaker, and Dispatch all live in `callback.py`,
any change vector that hits one of these touches all four. The coupling multiplies
the blast radius of every change.

The "domain events" section is the evolutionary architect's natural conclusion: events
are the canonical way to isolate what changes. If `SpecCreated` is an event, the
Execution Context's bootstrap_new_specs goes away entirely — a major change vector
(new spec creation) no longer requires a daemon-level polling loop reading stale
working-tree files.

The language audit (five meanings for "status", six synonyms for "gate/guard/rule") is
a fitness function signal in disguise. Martin Fowler's observation applies: when a
term means different things in different contexts, you have an implicit bounded context
boundary that has not been made explicit. The linguistic confusion IS the drift.

**Missed gaps from evolutionary lens:**

- C proposes the TO-BE bounded context map but provides no fitness functions to protect
  it. The map will drift without automated checks. Specifically: what detects when code
  in `dispatcher.py` starts importing from `lifecycle_writer.py` directly? Dependency
  direction tests (madge, dependency-cruiser, or import-linter for Python) are the
  canonical fitness function here. Without them, the new bounded context map will be
  violated within weeks of implementation — the same way the current ADR-023 "sole
  writer" invariant was violated almost immediately.
- C does not assign change frequencies to bounded contexts. From evolutionary lens,
  the Work Verification Context is the highest-change area (5 rounds of gate rule
  changes in 2.5 months). The Spec Lifecycle Context should be the most stable (it
  is the SoT). Isolation strategy should reflect this asymmetry.
- The `SpecCreated` event proposal solves bootstrap_new_specs, but C does not ask:
  what fitness function ensures Spark emits this event? If Spark stops emitting it
  (e.g., a prompt engineering change), the orchestrator silently stops seeing new specs.
  A monitoring check on "zero new lifecycle yamls for N days on an active project"
  would catch this.

---

### Analysis D — Erik (LLM Architect)

**Agreement:** PARTIAL

**Reasoning from evolutionary perspective:**

D's framing of "context budget" as an architectural concern is genuinely novel from an
evolutionary perspective. The observation that callback.py requires 10,000 tokens of
context to safely modify is a quantifiable fitness function target: after decomposition,
modifying the gate module should require no more than 3,000 tokens of context load.
This is testable — you can measure it. It is the evolutionary architect's dream: an
architectural property expressed as a number with a threshold.

The `GateResult` dataclass proposal is a reversibility improvement: once verify_status_sync
returns a typed result rather than communicating via side effects, it becomes possible
to swap the gate implementation without touching callers. This is the "defer irreversible
decisions" principle applied at function granularity.

**Missed gaps from evolutionary lens:**

- D focuses on the current state of ergonomics but does not assess the change vector.
  The gate logic has been rewritten 5 times in 2.5 months. The evolutionary question
  is: given that this component changes quarterly, how do we isolate it so the next
  change does NOT require 10,000 tokens of context? D proposes the solution (bounded
  module decomposition) but frames it as a static quality improvement rather than a
  dynamic isolation strategy.
- The `AGENT_REFERENCE.md` proposal is good documentation but is not a fitness function.
  Documentation drifts. The fitness function protecting the agent reference document
  would be a test that verifies every public function in gate.py has a corresponding
  entry in AGENT_REFERENCE.md. Without that, the reference will be stale within two
  months of the first gate change — the same pattern we see with the ADR chain today.
- D does not address the irreversibility question. The `_subject_implements` regex has
  been patched 3+ times. Each patch is a small reversible decision. But the cumulative
  effect (divergent commit conventions across 10 projects) is becoming irreversible.
  After enough projects adopt the trailer format, standardizing to the canonical format
  is no longer a trivial migration. D identifies the symptom but not this trajectory.

---

### Analysis E — Dan (DX Architect / Pragmatist)

**Agreement:** PARTIAL — strong on boring tech, weak on fitness functions

**Reasoning from evolutionary perspective:**

E's "innovation token" accounting is the best single analytical framework in the peer
set for the evolutionary architect's reversibility question. Framing git-as-lifecycle-DB
as "one token spent on infrastructure" and quantifying the bug debt it has produced is
exactly the kind of decision archaeology that evolutionary architecture requires.

The SQLite migration proposal directly increases reversibility: SQLite WAL transactions
are simpler, faster, and more debuggable than 8-subprocess git plumbing CAS. The
decision to use git-as-DB was an irreversible commitment to a specific consistency
mechanism that has produced two production bugs. Migrating to SQLite restores
optionality: SQLite can be replaced with Postgres without changing the lifecycle
semantics; git-as-DB cannot be replaced without a full lifecycle contract rewrite.

The Wave ordering (Zero-Innovation Fixes → Boring Stack Migration → DX Hardening) is
an evolutionary migration strategy, not a big-bang rewrite. Martin Fowler's Strangler
Fig pattern applied to data storage.

**Missed gaps from evolutionary lens:**

- E's entire analysis has zero fitness functions. The boring stack is a better
  foundation, but "boring" without "verified" is just an opinion. After migrating
  to SQLite, what prevents the next engineer from adding another git-based state store
  "just for this one thing"? An import-checker fitness function (`no subprocess in db.py
  for status writes`, `lifecycle status reads must go through db.get_spec()`) would
  protect the boring architecture automatically.
- E correctly identifies that `bootstrap_new_specs` reads WT rather than HEAD, but
  frames it as a DX pain point. The evolutionary frame is stronger: this WT read is a
  change vector. The backlog.md file is edited by humans, by render_backlog, and by
  Spark. Any of these writers can inadvertently trigger a mass-bootstrap event. The
  fitness function protecting against this is not "read HEAD instead of WT" — it is
  a test that verifies `bootstrap_new_specs` raises an error when backlog.md is dirty.
- E proposes removing spec_operator.py but does not ask: what is its replacement? If
  the answer is "direct SQLite mutations," that is an operator workflow change that
  will be reversed the first time the operator makes a typo and has no undo mechanism.
  The evolutionary position is: retain a thin operator CLI (< 50 LOC) that wraps
  SQLite, logs mutations to the audit trail, and is tested.

---

### Analysis F — Martin (Data Architect)

**Agreement:** AGREE — the most precise technical analysis in the peer set

**Reasoning from evolutionary perspective:**

F's kill question answer ("What is the system of record for each entity?") is
structurally equivalent to the evolutionary architect's "what fitness functions protect
this decision?" For each entity, F provides: declared SoR, actual SoR, and conflict.
This is a fitness function audit in everything but name.

The state machine transition table (VALID_TRANSITIONS dict) is the exact pattern I
would call a fitness function for the lifecycle architecture. Once encoded, a test
suite can enumerate all (old_status, new_status) pairs that should be invalid and
assert they raise ValueError. No drift from this invariant is possible without a
failing test.

The `dispatched_at` rename (from `started_at`) addresses the evolutionary concern
about the queued→done shortcut: by capturing dispatch time rather than status-change
time, the schema remains valid even when the pipeline completes faster than expected.
This is a schema design that accommodates known change vectors.

**Missed gaps from evolutionary lens:**

- F proposes the differential renderer for backlog.md (sentinel-based) but does not
  flag that the backlog.md file is now a change vector with no owner. Who is allowed
  to edit the narrative sections? If a Claude agent edits the narrative sections during
  an autopilot task, is that acceptable? A fitness function protecting the sentinel
  boundaries (`grep "AUTO-GENERATED-START" ai/backlog.md | wc -l` == expected count)
  would catch renderer bugs. Without it, the sentinel approach will drift.
- F recommends keeping git-as-lifecycle-DB (aligned with ADR-023) while E recommends
  migrating to SQLite. This is the central divergence in the peer set. From the
  evolutionary lens: the reversibility question matters most. Git-as-DB is harder to
  reverse than SQLite-as-DB. But F's proposed improvements (schema_version, VALID_TRANSITIONS,
  remove allowed_files_hash) make the git-as-DB approach more maintainable. The
  evolutionary answer is: F's improvements should be done regardless of which storage
  wins, because they are schema-level invariants, not storage-level.
- The `priority: p3` in 4 lifecycle files is a fitness function failure: the write-time
  validation for valid priorities was never implemented. F proposes adding it now — this
  is correct — but does not note that this failure pattern (schema declared, not
  enforced) is a recurring structural problem. The same pattern exists for `updated_by`
  (honor-system string), `blocked_reason` (free text), and `status` (no transition
  guard). A fitness function at the schema level (`validate_lifecycle_yaml(path)` run
  in CI) would catch all these violations in one pass.

---

### Analysis G — Fred (The Skeptic / Brooks' Lens)

**Agreement:** AGREE — strongest on conceptual integrity, weakest on implementation path

**Reasoning from evolutionary perspective:**

G's "0-rule design hypothesis" is the evolutionary architect's dream question: "what
is the minimal architecture that would prevent this class of failure?" The Option C
proposal (200-LOC callback + separate gate.py daemon) is not just a refactoring — it
is a change in architectural style from "reactive callback-driven status determination"
to "proactive poll-driven status determination." This has profound evolutionary
implications.

A poll-driven gate is easier to evolve. You can change the polling interval, add new
rules, swap the git log query — all without touching the pueue callback contract. The
current callback-driven design means every gate change must be deployed synchronously
with pueue task completions. A separate gate daemon decouples the deployment and change
vectors.

The Evaporating Cloud analysis (Part VIII) is the most rigorous conflict resolution in
the peer set. The hidden assumptions are correctly surfaced: "a rewrite must replace
everything at once" (broken), "the incremental path converges" (broken by 5-iteration
evidence). The Strangler Fig migration path is directly executable.

**Missed gaps from evolutionary lens:**

- G proposes the 200-LOC callback + gate.py architecture but provides no fitness
  functions for the TO-BE state. The ADR chain that produced callback.py's bloat existed
  precisely because there were no automated checks preventing accumulation of rules.
  Without fitness functions, gate.py will be at 600 LOC within 6 months through the
  same accretion pattern.
- The "who is the sole owner of callback/lifecycle architecture?" question (Part X) is
  important but not answered. In an LLM-maintained codebase, "sole owner" is the fitness
  function suite itself. The answer to G's question is: "the architecture is owned by
  the tests that enforce it." Without that answer, the next incident will produce the
  same reactive-patch response.
- G recommends removing _ALLOWED_WRITERS and replacing with git author identity. This
  is a stronger identity guarantee but creates an irreversible decision: once lifecycle
  writes are signed with a specific GPG key, rotating that key requires migrating all
  lifecycle history. From the reversibility lens, the process-token approach (Layer 1
  in H's security analysis) is more reversible: replace the env var, no git history
  migration needed.

---

### Analysis H — Bruce (Security Architect)

**Agreement:** PARTIAL

**Reasoning from evolutionary perspective:**

H's threat model surfaces the most dangerous evolutionary failure mode: the system
has accreted security declarations (identity enforcement, pre-commit hooks, ALLOWED_WRITERS)
that do not function anywhere. This is architectural drift in its purest form — the
declared architecture and the implemented architecture have diverged completely on
the security axis.

From the evolutionary lens, this is the fitness function gap in its most concrete form:
- Declared invariant: "only callback writes lifecycle status" (ADR-023)
- Fitness function to protect it: pre-commit hook on ai/lifecycle/*.yaml writes
- Status of fitness function: dead, not deployed anywhere (confirmed in deep-audit-report.md)

The pre-commit hook is the canonical example of a fitness function that was defined,
implemented, and then never deployed — and therefore never prevented any drift. The
H analysis correctly identifies this as an "active incident" rather than a potential
vulnerability.

**Missed gaps from evolutionary lens:**

- H's STRIDE analysis identifies threats but does not prioritize by change velocity.
  The TELEGRAM_BOT_TOKEN is a P0 acute incident. The `_ALLOWED_WRITERS` theater is
  a chronic drift problem. Evolutionary architecture distinguishes these: acute incidents
  need immediate fixes; chronic drift needs fitness functions. H treats them similarly.
- H proposes HMAC on callback-audit.jsonl, which is a security control, but does not
  flag the architectural implication: callback-audit.jsonl being read by scan_queued
  (orchestrator.py:520) for dispatch decisions is an undocumented cross-module data
  dependency. This is a hidden change vector — changing the JSONL format or rotation
  policy could silently affect dispatch behavior. A fitness function (integration test
  that exercises the scan_queued → anti-recency path with known JSONL content) would
  protect this coupling.
- H recommends process tokens (env vars in systemd units) as a Layer 1 security
  control. This is correct. But from the evolutionary perspective, the reversibility
  question: if tokens change, how many files need to be updated? If ORCHESTRATOR_PROCESS_TOKEN
  is used in 7 different call sites, token rotation becomes a coordinated multi-file
  change. The fitness function protecting token rotation is a test that enumerates all
  lifecycle.write_lifecycle call sites and verifies they all pass through the token
  validation path — not that they hardcode specific token values.

---

## Convergence (What All Peers Agree On)

**1. bootstrap_new_specs WT read is the root cause of today's incident (A, C, D, E, F, G, H all mention it)**

Universal convergence. The fix is equally universal: read from HEAD or remove bootstrap_new_specs.
From the evolutionary lens, this convergence indicates a clear fitness function target:
`assert bootstrap_new_specs never calls Path.read_text() on a WT file` — verifiable
with static analysis (ast.parse + visitor checking for Path.read_text calls in
orchestrator.py).

**2. callback.py is a god module that must be decomposed (A, C, D, E, F, G all agree)**

Universal minus H (H focuses on security surface, implies decomposition indirectly).
The decomposition is not optional from an evolutionary architecture perspective — it
is the change that makes all subsequent changes possible without cascading blast radius.

**3. pre-commit hook / identity enforcement is theatrical (C, G, H all confirm)**

The declared architecture (sole writer, identity-verified writes) has drifted from the
implemented architecture (any caller with filesystem access can write). This drift has
persisted undetected because there is no fitness function checking it.

**4. The three-store status split is a root structural problem (A, C, E, F, G, H all cite it)**

lifecycle.yaml HEAD + backlog.md WT + spec body = three representations of one fact.
This is the architectural source of today's incident and of BUG-185, ARCH-186, and
the TECH-166/176/177 chain. Every peer identifies it. The fix (single SoR) is
universally agreed upon.

**5. `_push_best_effort` at DEBUG is a production safety defect (A, E, F, H all flag it)**

A one-line change (DEBUG → WARNING) that would have made 3 of the 5 historical
incidents faster to detect. No peer disagrees.

---

## Divergence (Where Peers Disagree)

**1. Git-as-DB vs SQLite: E says replace, F says improve**

E (Dan): lifecycle.py is an innovation-token overrun. SQLite transactions replace 8
subprocess calls. Migration cost ~$10.

F (Martin): ADR-023 is correct. The CAS mechanism is sound. Fix the schema, add
transition validation, add schema_version. Keep git.

**Evolutionary position:** Both are partially right. E is right that git-as-DB has
generated an entire class of bugs (stale-index race, push-at-DEBUG, no timeout on
_run()). F is right that the CAS concept is sound and that the schema improvements
are needed regardless. The reversibility question resolves it: SQLite is more
reversible. The migration from lifecycle.yaml to SQLite is a 3-4 file change costing
~$10 in LLM compute. The migration from SQLite back to git is also feasible. Neither
decision is irreversible. From the evolutionary lens, E's proposal wins on boring-tech
grounds AND on the fitness function grounds: SQLite queries are easier to write fitness
functions for than git plumbing operations.

**2. Retain circuit breaker vs simplify to warning (G says simplify, E says keep)**

G: circuit breaker fires on self-induced problems (bootstrap mass-demotes). If bootstrap
is killed, the primary trigger disappears. Simplify to logging + alert.

E: Keep circuit breaker, it is a legitimate operational concern.

**Evolutionary position:** G is right that the circuit breaker is treating a symptom
(mass-demotes) rather than the cause (unguarded bootstrap). But E is right that operational
safety mechanisms have value even when imperfect. The evolutionary resolution: keep the
circuit breaker as a last-resort safety net, but add a fitness function upstream
(ALERT-001 in A's catalog) that fires before the circuit breaker threshold is reached.
The circuit breaker should almost never fire if upstream fitness functions are healthy.

**3. spec_operator.py: remove (E) vs thin wrapper (Neal's position) vs already dead (G)**

E: Remove. YAGNI, zero users.
G: Already dead (file does not exist on disk per G's reading, though C confirms it at spec_operator.py:116).

**Evolutionary position:** The operator CLI should exist as a thin wrapper over the SoR
(SQLite or lifecycle.write_lifecycle) with an audit trail. "Remove the tool" creates
a gap: the next time an operator needs to manually reset a spec, they will use the
most dangerous available mechanism (direct file edit or SQL without audit trail). A
50-LOC CLI with `--dry-run` and audit trail is better than no CLI. The evolutionary
test: does this CLI have 100% test coverage of every mutation it can perform?

---

## Ranking: Top 3 by Leverage for Evolutionary Architecture

**1. Analysis A (Operations/Charity) — highest evolutionary leverage**

Reason: A is the only peer that translates architectural decisions into measurable
fitness functions (SLO-4, ALERT-001, M-01). The metrics catalog provides 15 specific,
automatable checks that protect ARCH-186's architectural decisions. Without these,
every future change to the lifecycle contour will be evaluated only after a 5-hour
production incident. With them, drift is detected in under 5 minutes. This is the
foundational evolutionary contribution.

**2. Analysis G (Skeptic/Brooks) — highest conceptual leverage**

Reason: G's "0-rule design hypothesis" and Evaporating Cloud analysis provide the
architectural blueprint that should guide all decomposition decisions. The gate.py
separation (poll-driven, pure function of git history) eliminates the entire class
of "infer intent from artifacts" failures. G correctly identifies that the accumulation
of rules is the failure mode, not any specific rule. This is the evolutionary insight
that the other peers approach but do not state as directly.

**3. Analysis F (Data/Martin) — highest precision leverage**

Reason: F's VALID_TRANSITIONS dict, `_validate_transition` enforcement, and schema_version
proposal are directly implementable fitness functions. The transition guard is the
most important: once `queued → done` is rejected at write time, an entire class of
bugs (bootstrap-as-done, gate shortcut) becomes structurally impossible. F provides
the data-layer fitness functions that protect the lifecycle contract.

---

## Evolutionary-Specific Assessment

### Which proposals have no fitness function (will silently drift again)?

**Analysis C (Eric — Domain Modeler):**
The TO-BE bounded context map has no proposed fitness functions. C correctly draws the
boundaries but provides no automated check that the boundaries hold. In Python, import
direction is enforced by convention and code review. Without a tool like `import-linter`
or `dependency-cruiser` configured with the declared dependency rules, the new bounded
contexts will be crossed within months. Specifically: the "no direct import from
lifecycle_writer in gate.py" rule must be tested, or it will be violated.

**Analysis D (Erik — LLM Architect):**
The AGENT_REFERENCE.md is documentation, not a fitness function. The context-budget
reduction (10K → 3K tokens) is stated as a goal but has no measurement mechanism.
A fitness function would be: `wc -l scripts/vps/gate.py | awk '$1 > 200 {exit 1}'`.
Without line-count guards on the decomposed modules, each will grow back to 500+ LOC
through the same accretion pattern that produced callback.py.

**Analysis E (Dan — Pragmatist):**
The boring-stack migration removes technical complexity but produces no fitness functions
protecting the simplicity. The SQLite gate (`git log origin/develop --grep SPEC-ID`) is
elegant, but what prevents the next incident from adding a second flag (`--since`, a
LOC threshold, a file-path filter) until it is 8 rules again? A fitness function:
`grep -c "subprocess.run" scripts/vps/gate.py | awk '$1 > 1 {exit 1}'` — one subprocess
call in the gate, no more.

**Analysis H (Bruce — Security):**
The HMAC proposal for callback-audit.jsonl is a security control, not a fitness function.
A fitness function would be: CI test that writes a line to callback-audit.jsonl without
the HMAC key and verifies scan_queued rejects it. Without this test, the HMAC validation
code will be removed or bypassed the next time someone needs to debug the anti-recency
logic.

### Which proposals would FAIL the "would it have caught today's bug at PR-time?" test?

**The 8-rule redesign (cefaa55) passed code review but introduced a regression:**
The cross-project guard (Rule 8) fixed one problem while breaking `_subject_implements`
for the awardybot/dowry commit convention (460 of 636 commits now false-blocked). None
of the peer proposals include a fitness function that would catch this: a test suite
for `_subject_implements` with golden dataset covering both commit conventions. This is
specifically called out in D's analysis but framed as "build a test dataset first" —
not as a pre-merge CI gate that MUST pass before any `_subject_implements` change is merged.

**Today's bootstrap bug (bootstrap_new_specs reads WT) passed code review:**
The fix was implemented without a test that would catch a regression. No peer proposes
a specific test for this: `test_bootstrap_ignores_dirty_wt` — a test that modifies
backlog.md in the WT without committing, then verifies bootstrap_new_specs produces
zero lifecycle yaml changes. Until this test exists, the next person who "fixes"
bootstrap_new_specs can inadvertently reintroduce the WT read. A, F, G all identify
the root cause but none specify the regression test that would protect the fix.

**The `_push_best_effort` at DEBUG level:**
Every peer notes this. None propose a test that verifies push failures are logged at
WARNING or above. A fitness function: `grep -n "log.debug.*push" scripts/vps/lifecycle.py`
fails CI if any match is found. This is a 2-line git hook.

### Which proposals create new dimensions of drift?

**Analysis H's HMAC on audit JSONL:**
If callback-audit.jsonl becomes HMAC-protected, the HMAC key in the systemd environment
becomes a new secret that must be rotated. Rotation requires stopping callback,
re-generating the JSONL file with new HMACs, restarting. This is a new operational
complexity that H's proposal does not acknowledge. From the evolutionary lens, this is
a new change vector being introduced to solve a threat that is currently theoretical
(no evidence of audit JSONL injection in the incident history). The complexity cost
may exceed the security benefit.

**Analysis F's `schema_version` in lifecycle YAML:**
Adding `schema_version: 1` to lifecycle YAML is correct in principle. But it introduces
a migration obligation: every future schema change requires incrementing schema_version
and writing migration code. In an LLM-maintained codebase, this obligation will be
forgotten. A fitness function protecting it: `python3 -c "import yaml; d = yaml.safe_load(open('ai/lifecycle/TECH-001.yaml')); assert d.get('schema_version') == CURRENT_SCHEMA_VERSION"`
run in CI against a sample of lifecycle yamls. Without this test, schema_version becomes
another dead field like `allowed_files_hash` — always null, never meaningful.

**Analysis G's removal of _ALLOWED_WRITERS in favor of git author identity:**
Replacing the string-based identity check with GPG-signed commits is a higher-integrity
approach. But it creates an irreversible coupling: once lifecycle writes carry GPG
signatures, rotating the signing key requires migrating all historical lifecycle commits
or accepting a split history. This is a new architectural constraint that G's proposal
underweights. The process-token approach (H's Layer 1) is more reversible and achieves
80% of the security benefit at 20% of the irreversibility cost.

---

## My Addition: The Missing Evolutionary Insight — Temporal Coupling as the Core Drift Vector

The peer analyses collectively identify what is wrong (god module, three SoRs, theatrical
identity) and what to do about it (decompose, consolidate, enforce). What they miss is
WHY the architecture keeps drifting in the same way.

The root cause, from an evolutionary architecture perspective, is **temporal coupling
between the status determination event and the status write event**. Callback.py is a
synchronous pueue callback: it fires at task completion, determines status, writes status,
all in one execution. This temporal coupling means:

1. Every change to "how we determine done" must be deployed atomically with the write
   mechanism. The gate and the writer cannot evolve independently.
2. The determination logic (git log scan) runs once, at completion time, with whatever
   git state exists at that moment. If origin/develop has not been refreshed, the
   determination is wrong. (This is Root 4 in the audit — WT-sync race during atomic write.)
3. Bootstrap_new_specs exists because the Spark skill creates specs asynchronously,
   but the callback contract expects specs to exist before pueue tasks fire. This
   temporal mismatch between creation time and dispatch time is the source of the
   bootstrap logic.

The evolutionary fix — which G approaches but does not name as a temporal coupling fix —
is to decouple the determination event from the completion event:

```
Completion event (pueue callback, ~milliseconds):
  → release slot, dispatch QA/reflect, log task, exit
  (no git reads, no status writes, no coupling to git state)

Determination event (gate.py poll, every 60 seconds):
  → for each in_progress spec: git log origin/develop --grep=<spec_id>
  → if found: write_lifecycle(done)
  (no pueue coupling, no completion event timing, pure git-state function)
```

This decoupling eliminates the WT-sync race (no WT touch in callback), eliminates the
bootstrap race (gate.py finds specs regardless of when lifecycle yaml was created),
and makes the gate logic independently evolvable and testable.

The fitness function for this decoupling:
```bash
# Git hook or CI check:
# callback.py must not import lifecycle or contain git subprocess calls
grep -E "(import lifecycle|subprocess.*git)" scripts/vps/callback.py
# Fails CI if any match found after decoupling
```

This is one grep. It protects the most important architectural decision in the system.

No peer proposed it.

---

## Revised Position

**Revised Verdict:** Refined from Phase 1

**Change Reason:**

The peer analyses confirm the evolutionary diagnosis but add important nuance:

1. The git-as-DB vs SQLite debate is more nuanced than initially assessed. F's
   improvements to git-as-DB are valid and should be done regardless of storage choice.
   But E's boring-tech argument is stronger from an evolutionary lens: fewer moving
   parts means fewer fitness functions needed to maintain integrity.

2. G's Brooks analysis provides the historical explanation I was missing: the second-
   system effect explains why callback.py is a god module. The bash-era callback was
   simple. The Python rewrite accumulated all the "held-back ideas" from the first
   system. This pattern predicts that the third system (gate.py + callback.py split)
   will be over-engineered UNLESS fitness functions prevent feature creep from the
   start.

3. A's observability catalog provides the most immediately actionable fitness functions.
   The minimum viable hardening (~160 LOC) should be the first wave — not because it
   solves the architectural problem, but because it makes all subsequent changes safer
   to execute. You cannot safely evolve what you cannot observe.

**Final Evolutionary Recommendation:**

Three-wave evolutionary migration, ordered by reversibility risk and feedback speed:

**Wave 0 (immediate, ~$5, all reversible):**
- Promote `_push_best_effort` from DEBUG to WARNING (1 line)
- Add orchestrator heartbeat file (8 lines)
- Add bootstrap volume counter + ALERT-001 threshold check (15 lines)
- Add `test_bootstrap_ignores_dirty_wt` regression test
- Add `_subject_implements` golden dataset test with both commit conventions

These are all fitness functions protecting current architectural decisions. Zero
architectural change. Detects the next incident in minutes rather than hours.

**Wave 1 (this week, ~$20, reversible):**
- Decouple gate.py from callback.py (G's proposal + temporal coupling fix)
- Add dependency direction fitness function (Python import-linter rule: gate.py must
  not import lifecycle.py)
- Add module LOC fitness function (gate.py < 200 LOC, callback.py < 150 LOC)
- Kill bootstrap_new_specs from daemon loop (replace with Spark creating lifecycle yaml)

These changes reduce the blast radius of the Work Verification change vector.

**Wave 2 (next sprint, ~$30, partially reversible):**
- Migrate lifecycle.py to SQLite (E's proposal, increases reversibility of SoR choice)
- Add VALID_TRANSITIONS enforcement (F's proposal)
- Add bounded context dependency rules (C's proposal, enforced by import-linter)
- Add schema_version to lifecycle yaml with CI fitness function checking it

Each wave produces fitness functions that protect its own decisions. Architecture
cannot drift if the tests that define it are running on every commit.

The 5-incident pattern in the callback/lifecycle contour is not bad luck. It is the
predictable consequence of an architecture with no automated protection for its own
invariants. Every incident fixed one invariant and left the next one unprotected.
The evolutionary answer is not to fix the invariants faster. It is to test them
continuously.

---

## References

- Neal Ford et al., Building Evolutionary Architectures (O'Reilly, 2017)
- Martin Fowler, "Fitness Functions" (martinfowler.com)
- Martin Fowler, Strangler Fig Application (martinfowler.com/bliki/StranglerFigApplication)
- Fred Brooks, The Mythical Man-Month, ch. 5 (Second-System Effect)
- Dan McKinley, "Choose Boring Technology"
- scripts/vps/callback.py — 1374 LOC, 19 bare exceptions, 7 responsibilities
- scripts/vps/lifecycle.py — _push_best_effort at DEBUG (line 265)
- scripts/vps/orchestrator.py:295 — WT read of backlog.md (root cause of today's incident)
- deep-audit-report.md — 85 findings, 5 historical incident pattern
- architecture-agenda.md — per-persona scope
