# Domain Architecture Cross-Critique

**Persona:** Eric (Domain Modeler)
**Phase:** 2 — Peer Review
**Date:** 2026-05-23
**Scope:** callback/lifecycle/orchestrator retrofit

---

## Peer Analysis Reviews

### Analysis A — Operations (Charity lens)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

A correctly identifies that `callback.py` cannot be meaningfully observed because it bundles 7 responsibilities under one roof. The statement "operations requires named operations, and named operations require identifiable boundaries" is, from a domain lens, precisely a bounded context argument. Where A says "metric namespace per module," I say "ubiquitous language per context" — these are the same claim stated differently.

A's SLO-4 (Bootstrap Accuracy) implicitly acknowledges that `bootstrap_new_specs` exists in a different "context" than the lifecycle writer — one that reads from a rendered view (backlog.md WT) rather than the source of record. A treats this as an observability gap. I read it as a context boundary violation: the runtime dispatch context is consuming the output of the render context as if it were input. This is precisely the anti-pattern that corrupts language.

**Missed gaps:**

- A does not ask why `bootstrap_new_specs` reads `backlog.md` instead of lifecycle YAML HEAD. The answer is a domain boundary failure: the bootstrap function straddles two contexts (spec creation and runtime dispatch) and borrows its data from a third (the render context). No amount of alerting fixes a context that is reading from the wrong SoR.
- The 5-SLO proposal maps to 5 different business capabilities, each of which corresponds to a bounded context. A catalogs them as metrics without drawing the domain lines that would make each independently measurable and independently deployable.

---

### Analysis B — Evolutionary Architecture (Neal lens)

**Agreement:** Agree

**Reasoning from domain perspective:**

B's "fix train anti-pattern" is one of the strongest characterizations in the peer set. What B describes as "Conway's Law manifestation" — callback.py reflecting 5 different implicit authors with 5 different mental models — is exactly what I call ubiquitous language collapse. When the word "callback" can mean any of: pueue signal handler, spec gate, lifecycle writer, backlog renderer, or circuit breaker, the ubiquitous language has been lost. The code cannot speak the language of the business because it speaks 5 languages simultaneously.

B's fitness function suite (FF-01 through FF-08) is the most technically grounded enforcement proposal. FF-03 (sole-writer check) and FF-07 (convention drift test) are the two that directly enforce bounded context invariants at the code level. B's "ADR Kill Section" proposal is important: ADR supersession without artifact cleanup is how dead language persists in code.

**Missed gaps:**

- B identifies that `callback.py` needs to be decomposed into `gate | dispatcher | audit | circuit` but does not derive this decomposition from a linguistic boundary test. The correct question: does "gate" and "dispatcher" share any terms that mean different things? If "done" means something different to the gate (work merged to develop) versus the dispatcher (trigger QA/reflect), these are two separate bounded contexts with a translation requirement between them, not merely two modules.
- FF-08 (GROWTH prefix consistency) is a shared kernel smell. The fact that `callback.py` and `orchestrator.py` have divergent `_SPEC_ID_RE` definitions is evidence that they share a concept (spec identity) without sharing a definition. A shared kernel contract — a single `common.py` constant — would resolve this.

---

### Analysis D — LLM Architect (Erik Schluntz lens)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

D's `GateResult` dataclass proposal is — unknowingly — a domain event definition. `GateResult` with its `GateReason` enum is exactly the structure I would design for the "SpecStatusEvaluated" domain event: it has a source context (the gate), a trigger (pueue completion), a payload (all fields of GateResult), and it is consumed by downstream contexts (dispatcher, audit).

D's `AuditPayload` dataclass and the 12-argument `_emit_audit` critique are ergonomics observations that point to a missing value object. In DDD terms, the audit record is a value object that should be constructed gradually as gate evaluation proceeds. The current 12-argument positional API fails because it treats a value object as a bag of parameters passed all at once.

**Missed gaps:**

- D proposes a `vps-orch.py status SPEC-ID` CLI tool to expose lifecycle status. This is a Read Model in CQRS terms: the lifecycle YAML is the write model, the CLI is the read projection. D does not make this distinction explicit, but it matters: if the CLI reads from the lifecycle YAML directly (not from a derived view), then changes to the YAML schema will silently break the CLI's output format. A proper read model is explicitly decoupled from the write model with a translation layer.
- D's `orchestrator_client.signal_completion()` proposal is the most interesting one for domain modeling: it inverts the control direction. Instead of the callback inferring "is work done?" from git artifacts, the agent explicitly signals completion. This is a domain event push model (agent publishes "WorkCompleted" event) versus the current pull model (gate polls git). D does not develop the implications: in the push model, the gate becomes a verifier, not a discoverer — a structurally different and simpler role.

---

### Analysis E — DX Architect (Dan/Pragmatist lens)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

E's "innovation token" metaphor is pragmatically useful but domain-blind. The argument that git-as-lifecycle-DB should be replaced with SQLite is a technology argument, not a domain argument. The real question is: what is the ubiquitous language for spec status in this business? If the answer is "spec status is a fact about whether work was merged to the develop branch," then git IS the natural source of record — not because git is innovative, but because the business fact literally lives in git.

E's 1-rule gate proposal (`git log origin/develop --grep SPEC-ID`) is closer to the correct domain model than the 8-rule gate precisely because it is stated in business terms: "a spec is done when its implementation is merged." The 8-rule gate is an over-inference — it adds rules about LOC diffs, file paths, commit subject format — none of which are business facts. They are technical proxies for a business fact. E arrives at the right simplification from a DX angle; I arrive at the same simplification from the domain angle.

**Missed gaps:**

- E proposes removing `spec_operator.py` because "no real user needs it." This is not a YAGNI argument — it is a domain boundary argument. `spec_operator.py` exists because the system has no "Operator" bounded context: the operator's language (demote, force-done, reset-circuit) is not represented as a first-class context with its own ubiquitous language. If it were, the CLI would be a thin adapter into that context, not a cross-module private-function caller.
- E's SQLite migration removes the lifecycle YAML files but does not address what happens to the transition history. The lifecycle YAML transitions list is an event log — a domain event ledger. SQLite `spec_transitions` table is the correct equivalent, but E should explicitly name this as a domain event store, not just a relational table, to preserve the append-only audit property.

---

### Analysis F — Data Architecture (Martin lens)

**Agreement:** Agree

**Reasoning from domain perspective:**

F's entity relationship analysis is the most rigorous mapping of data ownership to bounded context in the peer set. The table showing "Declared SoR" vs "Actual SoR" for each entity is exactly the context map entry I would draw: where the declared and actual SoR diverge, there is a context boundary violation.

F's key insight — "orchestrator.bootstrap_new_specs reads backlog.md (render output) as if it were lifecycle truth — this is a cross-context data-flow violation" — is stated in domain terms. The render context is downstream of the lifecycle context. Reading data back from a downstream context's output as input to an upstream context reverses the context map relationship. This is the structural root of the 15 fake-done flips.

F's VALID_TRANSITIONS state machine is a good start at making invalid states unrepresentable — a core aggregate invariant. However, the transition `queued → done` is listed as invalid in the proposed model, while `verify_status_sync` currently performs it. F is correct that this transition should not exist: the spec aggregate should pass through `in_progress` before reaching `done`. This invariant, enforced at the aggregate root, eliminates an entire class of stale-status bugs.

**Missed gaps:**

- F's `blocked_code` enum addition (`blocked_reason` free-text + `blocked_code` machine code) is a good data design but misses the domain event implication. Each `blocked_code` value corresponds to a different domain event: `gate_reject` is "SpecGateRejected", `orphaned_crash` is "SpecOrphaned", `circuit_open` is "CircuitBreakerOpened". If these were modeled as domain events rather than YAML field values, the consumers (alerting, dashboards, downstream dispatchers) could subscribe to specific event types rather than polling and filtering the `blocked_code` field.
- F accepts the lifecycle YAML as the permanent SoR. This is defensible, but F does not address the translation contract: when the lifecycle context publishes a domain event (e.g., "SpecStatusChanged"), what is the contract for the render context (backlog.md) to consume it? Currently there is no contract — the render is called synchronously from within the lifecycle writer. A proper context boundary would have the lifecycle publish an event and the render context subscribe asynchronously.

---

### Analysis G — Devil's Advocate (Fred Brooks lens)

**Agreement:** Agree

**Reasoning from domain perspective:**

G's conceptual integrity verdict ("D — no unifying idea, five unifying ideas in conflict") is correct and important. From a DDD perspective, "5 unifying ideas in conflict" means the system has no ubiquitous language. When ADR-023 says "callback is sole writer" but `_ALLOWED_WRITERS` has 8 entries, the word "sole" has lost meaning. When `by="callback"` can be written by the orchestrator without consequence, the word "callback" has lost meaning. A language without stable definitions is not a language.

G's "0-rule callback" hypothesis (50 LOC dispatcher + separate gate daemon) is the most radical domain decomposition proposed by any peer. In domain terms, G is proposing to separate two bounded contexts that are currently merged: the "Task Completion Context" (receives pueue signal, releases slot, dispatches QA/reflect) and the "Spec Lifecycle Context" (evaluates whether work is done and transitions spec status). These are genuinely different capabilities with different rates of change: the former changes when pueue integration changes, the latter changes when the business definition of "done" changes.

G's Evaporating Cloud is valuable. The hidden assumption it surfaces — "we know all the edge cases now" — is precisely what a ubiquitous language prevents: if the language is clear, "done" has a single, unambiguous definition and edge cases are not about the language, they are about the implementation.

**Missed gaps:**

- G proposes "gate.py polls origin/develop every 60 seconds." This is a pull model. From a domain events perspective, a push model would be cleaner: when `git push` succeeds for a managed project, the merge to develop is the domain event ("WorkMergedToDevelop"). The gate daemon could subscribe to this event rather than polling. G's 60-second polling is pragmatically fine but misses the opportunity to make the domain event explicit.
- G's question "Is the gate's job to determine status, or to record status?" is exactly the CQRS question. The gate is a query (read git, evaluate predicate). The write (lifecycle YAML update) is a command. G identifies the conceptual distinction but does not name it as CQRS, which would clarify why `verify_status_sync` doing both is a violation of single responsibility at the domain level, not just the module level.

---

### Analysis H — Security (Bruce lens)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

H's STRIDE analysis maps threat categories to components, but the most interesting security finding — from a domain lens — is the `_ALLOWED_WRITERS` "theater" observation. H correctly notes that `_ALLOWED_WRITERS` is a string check, not a cryptographic assertion, and therefore constitutes security theater. In domain terms, this is an identity attribute masquerading as an aggregate invariant. The lifecycle aggregate accepts writes from any caller that passes the right string — which means the aggregate boundary is enforced by convention, not by the domain model.

H's recommendation to use git signed commits as identity is the correct long-term answer: identity is not a field in the YAML, it is a property of the git commit that writes the YAML. The git object store provides cryptographic identity as a first-class feature of the underlying infrastructure. Deriving `updated_by` from git author rather than the Python `by=` parameter aligns the identity model with the natural language of the system.

**Missed gaps:**

- H identifies that `_parse_allowed_files` has no validation against cross-directory paths but does not connect this to the aggregate boundary question. The `allowed_files` list in a spec is an assertion about which files belong to the spec's implementation. This is a domain concept — "files within scope of this spec's work" — not just a security constraint. The aggregate invariant should be: a spec's allowed files are a subset of the project's files, and the gate only validates commits touching files within this set. Expressing this as a domain invariant (not just a security check) makes the enforcement natural.
- H's "process token" recommendation for `lifecycle.write_lifecycle()` is a security control. From a domain lens, it is also a bounded context boundary enforcement: only processes within the "Lifecycle Write Context" should hold the token. This is the same as saying "only the lifecycle bounded context can write lifecycle state." The token is an implementation of context isolation.

---

## Convergence — Where Multiple Peers Agree

**Strong consensus (5+ peers):**

1. **callback.py (1374 LOC) must be decomposed.** A, B, D, E, F, G, H all reach this conclusion independently from different angles. The decomposition axes proposed: gate + dispatcher + audit + circuit (B, D, E, G). This is a consensus recommendation with high structural soundness.

2. **`bootstrap_new_specs` reading `backlog.md` WT is the structural root of today's incident.** A, B, D, E, F, G, H all identify this. The remediation paths differ (remove bootstrap, read from HEAD, have Spark write lifecycle YAML directly) but the diagnosis is unanimous.

3. **`_push_best_effort` at DEBUG is a silent failure.** A, B, D, E, F, H all flag this specific 1-line fix. This is the highest-signal low-cost change in the entire analysis.

4. **`scripts/vps/tests/` not in CI is the cheapest high-impact fix.** A, B, D, E all name `pyproject.toml:19` as a 1-line fix with 100-test payoff.

5. **`_subject_implements` rejects the dominant commit convention (460/636 awardybot commits).** B, D, E, G all flag this as Root 3. The fix paths differ: extend regex (B, D), replace with `git log --grep` (E, G), build golden test dataset first (D).

**Moderate consensus (3–4 peers):**

6. **spec_lint.py is a zombie validator.** B, D, E, G all flag this. The DLD-CALLBACK-MARKER validator now tests for a format that was deliberately removed. Should be deleted or repurposed.

7. **`lifecycle._run()` needs `timeout=30`.** A, D, H all flag the unbounded subprocess hang risk under `_write_lock`.

8. **TELEGRAM_BOT_TOKEN must be rotated immediately.** D, H name this explicitly. It is a P0 action independent of architecture decisions.

---

## Divergence — Where Peers Contradict

**Divergence 1: git-as-DB vs SQLite**

E (Dan) argues that ADR-023 (lifecycle YAML in git) should be replaced with SQLite for spec status. The argument: simpler, no CAS complexity, no push/pull divergence risk, already in the codebase.

F (Martin) and G (Fred) argue that git-as-SoT for spec status is conceptually correct — the status is a fact about what was committed to git, so git is the natural SoR. F proposes keeping lifecycle YAML but fixing the implementation (stale-index race). G agrees: "ADR-023a (status SoT is ai/lifecycle/*.yaml) — KEEP. ADR-023b (writes use private GIT_INDEX_FILE CAS) — REPLACE with simpler atomic write."

**My domain verdict:** The divergence is between implementation and concept. The concept (spec status as a git-resident fact) is correct from a ubiquitous language perspective: in this business, "done" means "merged to develop," and that fact lives in git history. SQLite status would be a derived representation of a git truth, which reintroduces the two-representation problem from the other direction. However, the CAS implementation is over-engineered and should be simplified. F and G's middle path (keep YAML SoT, simplify the write mechanism) is the stronger domain recommendation.

**Divergence 2: How to fix `_subject_implements`**

B proposes extending the regex to accept both canonical and trailer conventions, verified by FF-07.
D proposes building a golden test dataset first, then fixing.
E proposes replacing the entire function with `git log --grep SPEC-ID` which ignores subject format entirely.
G agrees with E's approach as the conceptually purest solution.

**My domain verdict:** E and G's single-rule approach (`git log origin/develop --grep SPEC-ID`) is correct from a ubiquitous language perspective. The business meaning of "done" is "the spec ID appears in the commit history of the main branch." Subject format is a technical convention, not a business fact. A gate that tests subject format is testing an implementation artifact, not a business concept. The 1-rule gate aligns the gate's language with the business language.

**Divergence 3: Remove bootstrap_new_specs vs fix it**

F proposes killing `bootstrap_new_specs` entirely by having Spark write `lifecycle.create_initial()` at spec creation time (making bootstrap dead code).
G agrees: "KILL. If Spark writes lifecycle yaml at spec creation, bootstrap has no purpose post-migration."
E proposes the same but frames it as an innovation token removal.
A and B focus on observable symptoms (mass bootstrap anomaly alert) without prescribing removal.

**My domain verdict:** The "kill bootstrap" path is the correct domain redesign. `bootstrap_new_specs` exists because Spark and Orchestrator share a responsibility boundary confusion: Spark creates spec.md but the Orchestrator bootstraps the lifecycle. In DDD terms, a spec should be created in one bounded context (the Spark/spec-creation context) and its lifecycle managed by another (the lifecycle context). If Spark creates the lifecycle YAML at spec creation, the bootstrap function has no domain role. The simplification is structural, not just operational.

---

## Ranking — 3 Highest-Leverage Peer Recommendations

**Rank 1: G's "200-LOC callback + separate gate daemon" (gate.py)**

Impact: Structural decomposition that eliminates the entire fix-train pattern. The fix-train exists because status determination (reading git, inferring done) and task signal handling (pueue callback, slot release, dispatch) are interleaved in one module. Separating them creates two independently testable, independently deployable components with clear domain language.

Structural soundness: High. The separation maps to two distinct bounded contexts with different triggers, different rates of change, and different failure modes. G provides a concrete migration path (Strangler Fig — parallel deployment to one test project).

**Rank 2: F's "Spark writes lifecycle.create_initial() — remove bootstrap_new_specs"**

Impact: Eliminates the structural root cause of the 15 fake-done flip incident and all future incidents of the same class. Bootstrap exists because there is no single owner of spec lifecycle creation. Assigning Spark as the sole creator closes the ownership gap.

Structural soundness: High. Consistent with ADR-023 (callback is the only status updater) extended to: Spark is the only lifecycle creator, callback is the only lifecycle updater. One creation path, one update path. This simplifies the context map from a tangled graph to a clean directed flow.

**Rank 3: B's Fitness Function Suite (FF-03 sole-writer + FF-07 convention drift)**

Impact: Converts architectural invariants from documentation claims to CI-enforced executable specifications. Without fitness functions, each architectural decision is an honor system. With fitness functions, ADR-023 ("callback is sole writer") is a test that fails on CI if violated.

Structural soundness: High. B provides ready-to-use code. The sole-writer check and convention test together prevent the two most common incident causes (false-blocked via wrong regex, unauthorized writers via migration script bypass) from recurring silently.

---

## Domain Lens: Bounded Context Violations in Peer Recommendations

**Recommendation that violates bounded context principles:**

H's "process token" proposal — adding an environment variable token required by `lifecycle.write_lifecycle()` — is a security improvement but risks becoming an implicit context boundary mechanism. If the token is shared between callback and orchestrator (because both are "allowed" to write lifecycle), the token enforces nothing about context boundaries; it merely authenticates the operating system user. For the token to enforce bounded context separation, each context (lifecycle-writer context, orchestrator-bootstrap context) would need its own token, and `write_lifecycle` would route based on which token is presented. H does not develop this, which means the recommendation as stated does not reinforce, and could obscure, the true context boundary.

**Recommendation that partially conflates contexts:**

D's `orchestrator_client.signal_completion()` proposal inverts control — agents signal completion explicitly rather than callback inferring it. This is a good domain event model, but D conflates two contexts: the "managed project agent context" (which knows it finished work) and the "spec lifecycle context" (which decides whether the spec is done). D's proposal has the agent call a completion API directly, coupling the managed project to the DLD orchestrator's internal API. A cleaner context map would have the agent publish a domain event ("WorkCompleted" with commit SHA) and the gate context subscribe to it — with an Anti-Corruption Layer translating the event into lifecycle terms.

---

## My Addition: The Missing Domain Event Model

All 7 peers analyze callback.py as a module decomposition problem. None of them frame it as a **domain event model** problem.

The fundamental issue: this system orchestrates work across multiple bounded contexts (spec creation, task execution, status management, QA, reflection, notification), but has no explicit domain event bus. Every cross-context interaction is implemented as a direct function call or file read — which means every context boundary is a coupling point.

The context map for this system, stated in domain events:

```
Spec Creation Context
  publishes: SpecCreated(spec_id, project_id, priority, kind)
  consumed by: Lifecycle Context (creates lifecycle YAML)

Task Execution Context
  publishes: TaskCompleted(spec_id, pueue_id, exit_code, commit_sha)
  publishes: TaskFailed(spec_id, pueue_id, reason)
  consumed by: Gate Context

Gate Context (formerly embedded in callback.py)
  subscribes to: TaskCompleted
  reads: git log origin/develop --grep spec_id
  publishes: SpecStatusEvaluated(spec_id, new_status, reason, evidence)
  consumed by: Lifecycle Context, Dispatch Context, Audit Context

Lifecycle Context
  subscribes to: SpecCreated, SpecStatusEvaluated
  writes: ai/lifecycle/{spec_id}.yaml (HEAD, CAS)
  publishes: LifecycleUpdated(spec_id, from_status, to_status, at)
  consumed by: Render Context

Dispatch Context (formerly embedded in callback.py)
  subscribes to: SpecStatusEvaluated(new_status=done)
  dispatches: QA task, Reflect task, Hermes notification

Render Context
  subscribes to: LifecycleUpdated
  writes: ai/backlog.md (generated view, never read as input)
```

In this model:
- `bootstrap_new_specs` disappears — Spec Creation Context owns creation
- `verify_status_sync` disappears — Gate Context is a separate process
- The 3-store status split disappears — only Lifecycle Context writes status
- The circuit breaker becomes an event subscriber, not a gate rule
- `_subject_implements` regex disappears — the gate asks git, not the commit subject

The commit subject convention problem (460 vs 176 commits) dissolves: `git log --grep SPEC-ID` searches the entire commit message, not just the subject. The trailer convention `(FTR-1053 Task 4)` is found without any regex.

This is not a rewrite proposal — it is a vocabulary correction. The code already has most of these pieces; they are just assembled without domain language guiding their arrangement. Name the events, draw the subscriptions, and the module decomposition follows naturally.

---

## Revised Position

**Revised Verdict:** Same as Phase 1, strengthened by peer evidence.

**Final Domain Recommendation:**

The primary intervention is not a code rewrite — it is a bounded context clarification. The codebase has all the required capabilities; they are assembled without domain language as the organizing principle. Three decisions, in order:

1. **Establish ownership**: Spec Creation → Spark owns lifecycle.create_initial(). Spec Status → Gate (new, standalone) owns status evaluation. Spec Recording → Lifecycle Context owns write_lifecycle. These three are currently tangled in one 1374-LOC file.

2. **Make events explicit**: Define SpecCreated, TaskCompleted, SpecStatusEvaluated, LifecycleUpdated as named domain events. Even without a formal event bus, naming these events in code (as dataclasses with clear source and consumer annotations) aligns the vocabulary.

3. **Kill the inference**: The 8-rule gate infers "done" from technical artifacts (commit subjects, LOC diffs, file paths). The 1-rule gate (`git log --grep SPEC-ID`) reads the business fact directly. The migration from inference to direct reading is not a performance trade-off — it is a domain language correction. "Done" means "merged to develop." Git says whether that is true. No rules needed.

The fitness functions proposed by B (FF-03, FF-07) should be implemented immediately as they enforce invariants the domain model depends on. The Strangler Fig migration proposed by G provides the safest path to the simplified architecture without a big-bang rewrite.

---

## References

- Peer analyses A, B, D, E, F, G, H (direct evidence, all claims cited by letter)
- Eric Evans — Domain-Driven Design (2003) — Bounded Contexts, Ubiquitous Language, Context Mapping, Aggregate invariants
- Vaughn Vernon — Implementing Domain-Driven Design (2013) — Domain Events, CQRS
- `scripts/vps/callback.py` — 1374 LOC, 7 responsibilities (direct measurement from B)
- `scripts/vps/lifecycle.py:551` — `by="callback"` misattribution from orchestrator (G, H)
- `scripts/vps/orchestrator.py:295` — WT read as SoR violation (consensus across all peers)
- `scripts/vps/lifecycle.py:266` — `_push_best_effort` at DEBUG (consensus across A, B, D, E, F, H)
