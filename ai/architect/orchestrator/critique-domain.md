# Domain Architecture Cross-Critique

**Persona:** Eric (Domain Modeler)
**Phase:** 2 — Peer Review
**Date:** 2026-03-10

---

## Peer Analysis Reviews

### Analysis A (Operations — Charity)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

Charity's research is the most empirically grounded of all seven analyses. The Claude CLI memory numbers (2-16 GB per extended session) are critical production facts that every other analysis underweights. The dead man's switch design, the systemd cgroup limits, and the structured logging strategy are all sound operational recommendations.

From a domain perspective, however, Charity makes a subtle but important error: the analysis treats the orchestrator's process architecture as the primary artifact. The `orchestrator.sh` script, the `flock` semaphore, the heartbeat — these are all described in process terms rather than domain terms. The ConcurrencyBudget concept I identified as a Portfolio domain concept appears in Charity's analysis as a hardware constraint encoded in a bash variable. That is the difference between a domain rule ("the Portfolio may never activate more projects than its ConcurrencyBudget allows") and an operational parameter (`MAX_CONCURRENT_CLAUDE=2`). Both produce the same behavior but only one is a domain boundary.

Charity's recovery protocol is excellent from an ops standpoint: detect interrupted `autopilot` phase, mark as `idle`, allow retry. This maps correctly onto my Pipeline context invariant that a phase transition is recoverable to `idle` on crash. Good alignment.

The assertion "The orchestrator is NOT a domain service. It is infrastructure" in the Cross-Cutting Implications section is exactly right and directly validates my Phase 1 position.

**Missed gaps:**

- The RAM-floor admission check in the `acquire_claude_slot` function enforces a business rule (don't launch Claude if memory is too low) but it lives in a bash function with no domain identity. From a domain perspective, this is a `ConcurrencyBudget` policy that belongs in the Portfolio context's scheduling logic, not hardcoded in a shell function.
- Charity does not address what happens when a paused project's inbox receives a new idea. Is the founder notified? Does the inbox queue and process later? This is an important Inbox -> Pipeline -> Notification invariant that the ops model cannot answer because it requires domain knowledge.
- The multi-LLM question (Claude + Codex) is completely unaddressed. No mention of what "two LLM providers" means for the slot management model.

---

### Analysis B (Devil's Advocate — Fred)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

Fred raises the most important business-level concern: this orchestrator may be anti-pattern #2 ("optimizes tooling instead of product"). That challenge stands on its own merits and no domain model can answer it — only the founder can. I respect the critique as a legitimate business concern.

However, Fred's alternative proposal — "tmux + Pueue + 50-line Python" — makes the same category error as the original spec but from the opposite direction. Fred correctly identifies that the spec's components are mechanistic rather than principled, but then proposes replacing one set of mechanisms with another without addressing the underlying domain question: what ARE the concepts in this business?

The critique of the "alternatives considered" table is valid: "no API coordination, dead end" dismisses tmux without defining what business problem "API coordination" solves. But the proposed solution (Pueue groups = project isolation) also substitutes a technical concept for a business concept. Pueue groups are not projects. A `Portfolio` is not a Pueue daemon. The domain exists independently of whether the implementation uses Pueue, bash, or Python.

Fred's Contradiction #1 (complexity justification vs. actual problem size) and Contradiction #2 (Telegram vs. GitHub Issues) are both valid and both come down to a single missing decision: the canonical interface. From a domain perspective, this is actually a context mapping question: is Telegram an Anti-Corruption Layer adapter for the Inbox context, or is it the primary domain channel? The spec has not answered this, and that ambiguity produces exactly the contradictions Fred identifies.

The framing "mechanism vs. architecture" is the correct DDD critique. Fred is right that "listing components is not design." But the conclusion — that the architecture should be simpler — is not the only possible resolution. The alternative resolution is: clearly identify the domains, THEN see how simple the mechanisms can be.

**Missed gaps:**

- Fred does not propose what the business language description should be. The critique identifies that the spec fails the Kill Question but does not offer a passing answer. Without a domain model, "simpler" still has no principled stopping point.
- The "Pueue groups = project domain boundary" suggestion (from Dan's analysis, which Fred's position implicitly supports) conflates an infrastructure concept with a domain concept. This is the same error Fred correctly diagnoses in the original spec.
- The question "what happens at 3am" is asked from an ops perspective. The domain-level version of that question is: "what is the correct system behavior when a pipeline run is interrupted?" That question has an answer in the Pipeline context state machine. Fred does not reach it.

---

### Analysis C (DX Architect — Dan)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

Dan's proposal is the most pragmatic of the seven analyses and the one most aligned with the founder's anti-pattern profile (tooling over product). The Pueue recommendation eliminates real custom code and I do not object to it on DX grounds. Pueue's group model, parallel limits, and task state are all useful operational primitives.

However, the statement "Pueue groups ARE the project domain boundary" is where I must push back clearly. Pueue groups are infrastructure primitives. A domain boundary is defined by where language changes meaning, not by where a tool places its namespace. If "project" in Pueue means a scheduling namespace and "project" in the business means a named body of work with a lifecycle, an inbox, a backlog, and a priority — those are two different things sharing a name. Using Pueue groups as the domain boundary means the domain is wherever the infrastructure puts it, which is the inverse of domain-driven design.

The practical recommendation of Pueue for the concurrency layer is sound. The philosophical claim that Pueue groups define the domain is not.

Dan's 3-day build plan is valuable for scoping. The division between "core to business (build)" and "buy/use existing" is exactly the right framework for this project. I would add one item to the "core to business" column: the domain event definitions. What events fire when an idea is captured? When a pipeline phase completes? When a project is paused? These events are the boundary contracts between contexts and they are not something Pueue, systemd, or any off-the-shelf tool provides.

The Telegram control plane scope limit ("Telegram = notifications + simple commands") is correct domain guidance. Telegram is an ACL adapter for the Inbox and Notification contexts, not the domain itself. Dan reaches the right conclusion from a DX perspective without necessarily framing it in domain terms.

**Missed gaps:**

- The Multi-LLM question (Claude + Codex) is unaddressed. From a DX perspective this matters enormously: two different CLI tools with different invocation patterns, auth, and resource profiles need separate handling. Is "LLM Provider" a configuration parameter or a context boundary?
- Dan's domain note says "the `ai/inbox/` file convention maps cleanly to Pueue task." This is wrong in domain terms. An `ai/inbox/` file is an InboxItem — a captured, unclassified founder input. A Pueue task is an execution unit. These are not the same concept. An InboxItem may become a Pueue task after spark processing turns it into a backlog entry, but the mapping is not direct.
- The separate question of what events fire when a new project is added (the Practical Bootstrap question from the updated agenda) is not addressed.

---

### Analysis D (Security — Bruce)

**Agreement:** Agree

**Reasoning from domain perspective:**

Bruce's threat model is the clearest trust boundary analysis in the set. The identification of six specific risks — Telegram compromise, prompt injection, cross-project data bleed, secret exfiltration, VPS compromise, runaway process — maps almost exactly onto my bounded context boundaries.

Cross-project data bleed (Bruce's risk #3) is the same as what I called the Pipeline context invariant failure: if Claude running for Project A can read Project B's secrets, the pipeline context boundary has been violated at the filesystem level. Bruce's recommendation of separate Unix users per project is the infrastructure enforcement of what I described as "a Claude process for Project A should only have access to Project A's data." This is not a security constraint imposed on top of the domain — it is the domain boundary enforced at the OS level.

The prompt injection defense section is directly relevant to domain integrity. A voice transcription or GitHub Issue title that contains adversarial instructions is an attack on the Inbox context's anti-corruption function. The Inbox ACL is supposed to translate raw founder inputs into clean InboxItems. Prompt injection attacks that translation layer. Bruce's XML structural separation in prompts is the technical implementation of what I described as the Inbox ACL's responsibility to sanitize inputs before they become domain objects.

Bruce's classification of the orchestrator Unix user ("should have NO read access to project directories — it only dispatches jobs") is a perfect security expression of my architectural claim that the orchestrator is an application service that coordinates domains without containing domain data. The orchestrator user dispatches; the project user executes. Domain responsibility and file system permissions aligned.

**Missed gaps:**

- The multi-LLM question: if Claude Code runs as `user-project-a` and Codex CLI runs as the same user, the Unix user isolation does not help. Different LLM tools need the same isolation model applied consistently. Bruce does not address whether Claude and Codex CLIs can coexist under the same per-project user account without contamination.
- The trust model for cross-context communication is not addressed. When the Notification context needs to send a Telegram message, it must know the project's DeliveryChannel (topic ID). If that information lives in `projects.json` which is owned by the orchestrator user, and the notification function runs as the orchestrator user, then the orchestrator user DOES need read access to that mapping. Bruce's "orchestrator has NO read access to project directories" needs to be scoped more precisely: the orchestrator cannot read project code or secrets, but it can read the routing configuration.

---

### Analysis E (LLM Architect — Erik)

**Agreement:** Agree

**Reasoning from domain perspective:**

Erik's research is the most technically specific and the most directly relevant to the Pipeline context design. The confirmation that Agent Teams cannot span projects validates my finding that the orchestrator is the only mechanism for cross-project coordination — there is no native Claude Code feature that does it.

The `CLAUDE_CODE_CONFIG_DIR` per-project recommendation is the infrastructure implementation of what I described as the Pipeline context's session isolation requirement. Each project needs its own session state to prevent the cross-session contamination bug (#30348). This is not merely a technical fix — it is enforcing the Pipeline context invariant that a PipelineRun belongs to exactly one project and cannot share state with another project's PipelineRun.

Erik's hybrid routing model (rule-based for structured commands, Haiku for unstructured general-topic messages) maps cleanly onto my Inbox context design. The RoutingKey concept I defined (the abstraction over `message_thread_id`) is what makes this routing deterministic: if a `RoutingKey` is known, route is determined. Only messages without a `RoutingKey` (General topic, ambiguous) need LLM classification.

The `--max-turns` per phase recommendation also aligns with my Phase value object. Different phases have different complexity budgets: inbox processing is simpler than autopilot, which is simpler than spark. The phase concept carries not just state identity but also operational parameters.

**Missed gaps:**

- Multi-LLM question: Erik addresses Claude Code's architecture in depth but says nothing about what changes when Codex CLI is added. Both the session isolation strategy (`CLAUDE_CODE_CONFIG_DIR`) and the RAM model change when a second LLM tool is in play. Are Codex sessions subject to the same memory leak profile? Do they need separate slot management?
- Erik's "self-describing API contract" table is valuable but frames the contract in tool flags rather than domain language. The orchestrator's contract with Claude is not "pass `--max-turns 30`" — it is "invoke the Pipeline context's autopilot phase for Project X." The flags are implementation details. The domain contract is what phase is being requested for which project.
- The question of what domain events fire when a project is added (Practical Bootstrap) is not addressed.

---

### Analysis F (Evolutionary Architect — Neal)

**Agreement:** Agree

**Reasoning from domain perspective:**

Neal's fitness function framework is the closest any of the seven analyses gets to what I would call domain invariants expressed as automated checks. The difference between a fitness function and a domain invariant is small: a domain invariant is a business rule that must always hold ("the Portfolio may not have more active projects than its ConcurrencyBudget"); a fitness function is an automated test that verifies the invariant holds ("count running Claude processes, alert if >max_concurrent_claude").

Neal's semaphore slot correctness fitness function — count running Claude processes, compare to config — is the runtime enforcement of the ConcurrencyBudget invariant from my Portfolio aggregate. This is domain discipline expressed as infrastructure. I appreciate it.

The strangler fig migration path (Phase 0: run alongside current manual flow, Phase 1: migrate Telegram routing, Phase 2: migrate automation) is the correct incremental approach. From a domain perspective, each phase corresponds to handing over responsibility for one context: Phase 1 hands Inbox routing to the new context; Phase 2 hands Pipeline execution to the new context.

The "reversible vs irreversible decisions" table is excellent. The note that "Telegram as primary UI" is irreversible because "topic IDs are baked into projects.json, users habituated" confirms my concern that Telegram topics leaking into the domain model creates coupling. Neal's mitigation (build TelegramAdapter interface from day 1) is the ACL approach I recommended. Good convergence.

The 400-LOC tripwire for `orchestrator.sh` is a proxy fitness function for domain integrity: once the application service layer exceeds 400 LOC, it has likely absorbed domain logic that belongs in the bounded contexts.

**Missed gaps:**

- The multi-LLM question and the infrastructure topology question are both absent from Neal's analysis despite being explicitly added to the agenda as cross-cutting concerns.
- Neal's scaling inflection points (3-4 projects: RAM; 5-6: loop time; 8-10: complexity) are framed in operational terms. The domain inflection points are different: the system changes character when Project dependencies emerge (a Portfolio concern), when the founder wants cross-project reporting, or when a project needs to delegate to another project's context. These are domain scaling concerns that are separate from the operational ones.
- The "escape hatch for Claude Code native multi-project" section rightly identifies that `claude-runner.sh` is the change point. But the more important escape hatch is the domain model itself: if the bounded contexts (Portfolio, Inbox, Pipeline, Notification) are clearly defined, ANY underlying orchestration mechanism — bash, Pueue, Claude native, GitHub Actions — can be swapped in at the application layer without changing the domain logic. Neal identifies this implicitly through the "stable vs disposable components" analysis but does not make the domain model itself the primary stable artifact.

---

### Analysis G (Data Architect — Martin)

**Agreement:** Agree

**Reasoning from domain perspective:**

Martin's analysis is the strongest of the seven from an architectural rigor standpoint. The identification of the `.orchestrator-state.json` race condition via the Claude Code GitHub #29158 evidence (335 corruption events in 7 days) is critical and validates the instinct to separate config (JSON, human-written, rare writes) from state (SQLite, daemon-written, frequent writes). This is a data integrity argument that directly supports my domain separation: `projects.json` is the Portfolio context's configuration; `orchestrator.db` is the Pipeline context's operational state.

Martin's entity-relationship model maps almost exactly onto my bounded context design:

- `projects.json` (config) = Portfolio context's project registry
- `project_state` (SQLite) = Pipeline context's aggregate state
- `claude_slots` (SQLite) = Portfolio context's ConcurrencyBudget enforcement
- `ai/inbox/` (filesystem) = Inbox context's storage
- GitHub Issues (optional, async) = cross-context narrative layer

The only refinement I would offer: the `claude_slots` table enforces the ConcurrencyBudget invariant of the Portfolio aggregate. Martin places it in the database layer for the right operational reasons, but it is worth naming it explicitly as Portfolio context state — not orchestrator infrastructure. This distinction matters because if the Portfolio context later needs richer scheduling (priority-weighted slots, time-windowed activation), the natural extension is to add Portfolio domain logic, not to patch the database schema.

The use of SQLite BEGIN IMMEDIATE for slot acquisition is the correct ACID implementation of what I described as the Portfolio aggregate invariant: "Active project count <= ConcurrencyBudget." The invariant cannot be maintained by application logic alone; it must be enforced transactionally. Martin gets this right.

The GitHub Issues as "project context narrative, not operational state" is exactly the right scope. GitHub Issues are a long-lived, human-readable view of the project — closer to the Portfolio's narrative description than to the Pipeline's operational state. Martin's boundary here is sound.

**Missed gaps:**

- The multi-LLM question: how does the `usage_ledger` table handle tracking costs for two different LLM providers (Claude and Codex)? The current `event_type` CHECK constraint is Claude-specific. Adding Codex requires schema migration. Martin should have flagged this as a forward-compatibility concern in the schema design.
- The `claude_slots` table only accommodates a fixed number of slots (1 or 2, hardcoded in the CHECK constraint). If different LLM providers have different resource profiles — Claude: 4 GB per session; Codex: 2 GB per session — the slot model needs to be provider-aware. A flat slot count does not capture heterogeneous resource consumption.
- The domain event layer is completely absent. Martin models the data storage well but does not address how domain events cross context boundaries. The `project_state` table update when a phase completes is a side effect, not an event. The Notification context cannot subscribe to SQLite row updates — it needs a domain event. Martin does not address this integration pattern.

---

## Ranking

**Best Analysis:** G (Martin — Data Architect)

**Reason:** Martin's analysis is the most architecturally rigorous. It correctly identifies the race condition that invalidates the current spec's state model, provides a clean separation between config and state that maps onto domain boundaries, and reaches sound conclusions about each storage decision. The entity-relationship model is the most precise structural artifact in all seven analyses. Martin also correctly limits GitHub Issues to the narrative layer (eventual consistency, non-critical path) while using SQLite for operational state (ACID, critical path). This is the most disciplined data modeling in the set.

**Worst Analysis:** B (Fred — Devil's Advocate)

**Reason:** While Fred correctly identifies the absence of conceptual integrity, the analysis does not provide a constructive alternative that improves it. The "D grade for conceptual integrity" followed by "the honest version is simpler: tmux + Pueue + Python" replaces one set of mechanisms with another without addressing the domain question at all. Pueue groups have no more conceptual integrity than flock semaphores — they are both infrastructure primitives masquerading as domain concepts. Fred rightly asks "what is the one thing this system IS?" but does not attempt to answer it. A devil's advocate that identifies the right question but refuses to engage with the answer is less useful than an analysis that reaches an imperfect answer by the right process.

---

## Revised Position

**Revised Verdict:** Changed (partially)

**Change Reason:**

Two pieces of evidence from the peer analyses meaningfully updated my Phase 1 position:

1. Martin's evidence of the `.orchestrator-state.json` race condition (GitHub #29158) strengthens my recommendation that Portfolio and Pipeline context state must be separated into different storage mechanisms. In Phase 1 I said "the existing `projects.json` is a valid persistence mechanism for Portfolio context." I now refine that: `projects.json` is valid as the Portfolio config store (human-written, atomic rename pattern). But the Pipeline context's operational state MUST be SQLite, not JSON. This is not a preference — it is a correctness requirement demonstrated by production evidence.

2. The Multi-LLM question (Claude + Codex from the updated agenda) was not in my Phase 1 analysis. I need to address it now.

**Final Domain Recommendation:**

### On Multi-LLM (Claude Code + ChatGPT Codex GPT-5.4)

*Listening carefully to the business description of multi-LLM orchestration.*

The question "is LLM Provider a domain or infra?" has a clear answer from DDD principles: LLM Provider is infrastructure. The domain says "run the autopilot phase for Project X." How the autopilot is executed — whether by Claude, Codex, or a future GPT-6 — is an implementation detail invisible to the domain model.

However, the presence of two LLM providers DOES create a new domain concept that was absent before: **LLM Capability**. The founder says "GPT-5.4 is very good at coding." This means different tasks have different LLM preferences. That preference is a business rule ("for coding tasks in this project, prefer Codex") not an infrastructure parameter.

This suggests a refinement to the Pipeline context:

- The `Phase` value object needs a `preferred_provider` attribute (Claude | Codex | auto)
- The `ProjectPipeline` aggregate can have per-phase provider preferences
- The `ConcurrencyBudget` in the Portfolio context must be provider-aware: Claude slots and Codex slots may have different RAM profiles and should be tracked separately

Context map implication: both Claude Code CLI and Codex CLI are Anti-Corruption Layer adapters in the Pipeline context. They both speak the domain language of "run phase X for project Y, report outcome Z." The ACL translates that into different CLI invocations per provider.

The LLM Provider is NOT a bounded context. It is an adapter in the Pipeline context's ACL layer. The word "provider" does not appear in the domain language — the domain speaks "phase," "run," and "outcome."

### On Infrastructure Topology (Same VPS vs Separate)

*From a domain perspective, VPS topology is invisible to the domain model.*

Whether the orchestrator runs on the same VPS as project Docker containers or on a separate lightweight VPS is a deployment decision with no domain implications. The domain boundaries (Portfolio, Inbox, Pipeline, Notification) exist regardless of where the processes run.

That said, the domain does have a perspective on isolation. The Pipeline context invariant is: "a PipelineRun for Project A must not be affected by the execution environment of Project B." On the same VPS, this invariant is enforced by the ConcurrencyBudget (RAM floor checks) and per-project Unix user isolation. On separate VPS instances, the invariant is enforced by network topology. Both are valid implementations of the same domain rule.

From domain health: a single VPS creates operational coupling between the orchestrator and project runtimes. If project Docker containers consume RAM, the ConcurrencyBudget for Claude processes shrinks. This coupling does not violate domain boundaries, but it means the Portfolio context's ConcurrencyBudget must be dynamically calculated from available system resources, not statically configured. A separate orchestrator VPS keeps the Portfolio context's resource model clean and independent of project runtime activity.

The business recommendation: start with same-VPS (lower cost, simpler operations), but model the ConcurrencyBudget as dynamic (read available RAM before each slot acquisition) from day one. This makes the eventual split to separate VPS a deployment change, not a domain model change.

### On Practical Bootstrap: Domain Events When a New Project Is Added

*This is the most important test of whether the domain model is real.*

When the founder sends `/addproject "SaaS App" /home/user/saas-app` via Telegram, what domain events fire?

Tracing through the context model:

1. **Telegram ACL** receives the raw command. Validates: syntax, sender whitelist, path safety. This is ACL work — no domain event yet.

2. **Portfolio Context** receives `ProjectRegistrationRequested(name="SaaS App", path="/home/user/saas-app")`. The Portfolio aggregate applies its invariants: is the name unique? Does the path exist? Is there capacity in the Portfolio (some founders cap their active project count)? If all pass, it creates a new `Project` entity and emits:
   - **`ProjectRegistered`** (Portfolio → everyone)

3. **Pipeline Context** consumes `ProjectRegistered` and creates a new `ProjectPipeline` aggregate in `idle` state. No event yet — just initialization.

4. **Inbox Context** consumes `ProjectRegistered` and creates the routing entry: `RoutingKey` for the project (initially null until a Telegram topic is created). It also creates the inbox directory.

5. **Notification Context** consumes `ProjectRegistered` and creates the delivery channel configuration. It needs to CREATE the Telegram topic now. This triggers:
   - Telegram API call: create forum topic named "SaaS App"
   - Telegram API returns `topic_id`
   - Notification context stores `DeliveryChannel(project_id="saas-app", telegram_topic_id=<new_id>)`
   - Notification context emits **`DeliveryChannelCreated`** (Notification → Inbox)

6. **Inbox Context** consumes `DeliveryChannelCreated` and updates its routing: now `RoutingKey(telegram_topic_id=<new_id>)` maps to `project_id="saas-app"`. The inbox is now ready to receive messages.

7. **Notification Context** sends a confirmation message to the new topic: "Project 'SaaS App' is ready. Send ideas here."

8. **Portfolio Context** finalizes: `Project.status = ProjectStatus.IDLE`. The project is registered and schedulable.

The full sequence in domain event language:
```
ProjectRegistrationRequested
  → ProjectRegistered
  → [Pipeline init: idle]
  → [Inbox routing: pending]
  → DeliveryChannelCreated (topic created in Telegram)
  → [Inbox routing: active]
  → ConfirmationDelivered (founder notified in new topic)
  → [Project: schedulable]
```

This sequence reveals an important ordering constraint: the Inbox context cannot route messages to a project until after the Notification context has created the Telegram topic and the Inbox context has received `DeliveryChannelCreated`. This is a saga, not a single transaction. The orchestrator must handle partial failures: what if Telegram topic creation fails? The `ProjectRegistered` event has already fired. The Portfolio knows the project exists. But the Inbox cannot route to it yet. The project must remain in a `registering` state (not `idle`) until all contexts have completed their initialization. This is a non-trivial workflow that the current spec does not address.

**Conclusion:** The practical bootstrap question exposes that "adding a project" is a multi-context saga with ordering constraints and failure modes, not a single database write. This is exactly why domain events matter — they make the coordination visible.

---

## References

- [Eric Evans — Domain-Driven Design: Tackling Complexity in the Heart of Software](https://www.domainlanguage.com/ddd/)
- My Phase 1 research: `ai/architect/orchestrator/research-domain.md`
- Martin's data analysis: `ai/architect/orchestrator/anonymous/peer-G.md`
- Bruce's threat model: `ai/architect/orchestrator/anonymous/peer-D.md`
- Neal's fitness functions: `ai/architect/orchestrator/anonymous/peer-F.md`
- Erik's LLM architecture: `ai/architect/orchestrator/anonymous/peer-E.md`
