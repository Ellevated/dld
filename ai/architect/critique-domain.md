# Domain Architecture Cross-Critique

**Persona:** Eric (Domain Modeler)
**Phase:** 2 — Peer Review (Karpathy Protocol)

---

## Peer Analysis Reviews

### Analysis A — DX Architect (Dan)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

Dan raises a legitimate concern when he says "8 bounded contexts for a 2-person team" is excessive overhead. He is right that team size affects how many context boundaries can be actively maintained. But there is a critical conflation happening here: Dan is using "bounded context" and "microservice" interchangeably, which is an error.

A bounded context is a linguistic boundary — a place where the meaning of terms is stable. It is not a deployment unit. You can implement 7 bounded contexts as a single monolith with clean module boundaries, without a message broker, without microservices overhead. The cost of naming a thing correctly is nearly zero. The cost of not naming it — letting "order" mean different things in different parts of the codebase — compounds over time.

Dan's recommendation to reduce to 4 domains (briefing, sources, memory, billing) collapses what I called "Workspace," "Identity," "Notification," and parts of "Priority" into the remaining four. That is fine as a deployment strategy. It is not fine as a naming strategy — the ubiquitous language still needs to be clear about what a "workspace" is versus a "user," what a "channel" is versus a "briefing."

Where I agree with Dan: Clerk as an Auth bounded context wrapper is correct. The ACL pattern (Clerk speaks its own language; we translate to our domain's `User` concept at the boundary) is exactly right, and Dan names this correctly even without using the DDD terminology.

Where Dan has a blind spot: he says "auth is handled by Clerk — not a domain." This is precisely backwards. Because Clerk handles auth, we need a domain boundary around it MORE, not less. The ACL must exist so that Clerk concepts (Organizations, Sessions, JWTs) do not leak into the briefing domain. "Not a domain" would mean importing Clerk directly throughout the codebase — which is the mistake we are trying to prevent.

**Missed gaps:**

- Dan treats "4 domains" as a simpler alternative to "7 contexts" without acknowledging that the linguistic boundaries exist regardless of whether we name them. Unnamed boundaries create the same coupling problems as explicit ones — they are just invisible until they break.
- The proposed `briefing/` domain in Dan's model collapses synthesis, delivery, and pipeline into one. This conflates "what is in the briefing" with "how the briefing is sent" — the exact boundary violation I flagged. Adding WhatsApp as a channel should not require touching the briefing synthesis logic.

**Rank: Moderate**

---

### Analysis C — Data Architect (Martin)

**Agreement:** Agree

**Reasoning from domain perspective:**

Martin's work is the strongest complement to my domain model. Where I define the conceptual boundaries and the language, Martin specifies the physical schema that enforces those boundaries. The alignment is precise.

The most important DDD-relevant insight in Martin's analysis is the explicit separation of `preferences` (user-authored, explicit) from `memory_signals` (system-inferred, behavioral). In my Phase 1 analysis I named these `DeclaredPriority` and `LearnedSignal` within the Priority context. Martin's schema is the physical implementation of exactly this distinction. The two-table design with separate write paths is not a database optimization — it is a domain invariant made durable. A `DeclaredPriority` is user-owned. A `LearnedSignal` is system-owned. Conflating them into a single "preferences" table would create the dual-SoR problem Martin correctly identifies.

Martin's `briefing_feedback` table and `memory_signals` table also reflect a domain modeling principle I named but did not fully specify: engagement (what the user did with a past briefing) is the input to the learning loop in the Priority context. Martin's schema makes this explicit: `briefing_feedback` is the event log (raw behavior), `memory_signals` is the derived state (inference). This is DDIA chapter 11's "derived data" pattern applied correctly to a domain aggregate.

The `usage_ledger` as an append-only ledger is the correct data model for the `UsageLedger` entity within my Workspace context. Append-only is not just a database pattern here — it reflects a domain truth: a task consumption is an immutable fact about what happened. You cannot un-consume a task. The ledger models this correctly.

One area of slight concern: Martin scopes everything under `workspace_id` as the aggregate root for all Phase 2 entities. While workspace isolation is correct, I want to be precise: `workspace_id` is the tenant boundary, not the aggregate root. Each bounded context has its own aggregate root (Briefing, Source, PriorityProfile, etc.). The `workspace_id` foreign key is the tenant isolation key that appears on all tables — it is not a DDD aggregate root in the technical sense. This conflation could lead to "query everything through the workspace" patterns that violate context boundaries.

**Missed gaps:**

- Martin's schema has `source_configs` with `config_json` as a JSON blob. In my domain model, the Source context has specific entities: SourceType, FetchSchedule, SourceCredential. These should be typed columns or a strict schema, not an open JSON blob. A JSON blob for source config is a domain model that defers to runtime what should be compile-time validated.
- Martin's `billing_cache` table correctly separates Stripe's truth from our local cache, but the analysis does not address how the domain communicates a tier change to the Workspace context aggregate. In my model, the Billing context publishes a `SubscriptionChanged` event that the Workspace context reacts to. Martin's schema update flow (webhook → billing_cache → workspaces.task_cap_monthly) is the implementation — but the event as a domain concept is missing.

**Rank: Strong**

---

### Analysis D — Evolutionary Architect (Neal)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

Neal's fitness functions are a remarkable translation of architectural quality requirements into executable tests. From a domain perspective, the most relevant fitness function is the dependency direction check: `shared ← infra ← domains ← api`. This is not just an import hygiene rule. It IS the domain model enforced as code. When a domain module imports from an infra module only (never from another domain directly), you have enforced the bounded context boundary mechanically.

Neal's change vector analysis correctly identifies that the `sources` domain is the highest-change-velocity component. This aligns with my recommendation that the Source context requires the most aggressive Anti-Corruption Layer work from day one. External APIs (Gmail, HN, RSS, Calendar) change on their own schedule. Without the ACL, every API change propagates into the briefing domain. Neal names this the "isolation strategy" requirement without using the ACL term — but the structural recommendation is identical.

Where I have a significant disagreement: Neal (like Dan) recommends starting with 4 domains rather than my 7 contexts. He writes: "Phase 2 needs 4 core domains at launch, not 8. briefing, sources, memory, delivery are the load-bearing walls. auth, billing, workspace are infra concerns, not domains."

This is the same categorical error as Dan's analysis, but Neal expresses it more sharply. The claim that "auth, billing, workspace are infra concerns, not domains" is simply incorrect from a DDD perspective. Workspace ownership, tier enforcement, and usage cap logic ARE domain logic — they encode business rules (Solo tier gets 500 tasks, Pro tier gets 2000) that change when the business model changes. These are not infrastructure concerns. They are not the same as "the database" or "the Fly.io deployment." They are business decisions encoded in the domain model.

Neal's recommendation to "start simple, extract domains when coupling becomes visible" is operationally sound. But it assumes you can add domain boundaries later without the linguistic chaos that accumulates in the meantime. In my experience, the naming pollution that occurs when "workspace" is just a field on the user table and "tier" is just an enum embedded in the billing module is very hard to clean up. The cost of naming correctly from day one is small. The cost of renaming is enormous.

**Missed gaps:**

- Neal's fitness function for behavioral memory focuses on schema migration safety but does not address the domain invariant: declared priorities take precedence over learned signals when scoring. This is a business rule, not a data rule. No fitness function currently tests this invariant.
- Neal correctly defers LangGraph.js, but his alternative ("simple async pipeline") does not name what the pipeline actually is in domain terms. The briefing compilation is a domain process within the Briefing context — it should be named as such in the code even if the implementation is a simple function. `compileBriefing()` as a domain service, not `runPipeline()` as an infrastructure function.

**Rank: Moderate**

---

### Analysis E — LLM Systems Architect (Erik)

**Agreement:** Agree

**Reasoning from domain perspective:**

Erik's analysis is primarily technical (model routing, context budgeting, eval strategy), but several insights have direct domain model implications that I want to affirm.

The two-stage pipeline design — per-source summarization with Haiku (extraction), followed by synthesis with Sonnet — maps precisely to my Signal→Item transformation. A Signal is the raw material from a source (Erik's "raw article"). The extraction step (Haiku summarization) produces the structured `SourceItem` — this is the Signal being evaluated and summarized. The synthesis step takes these structured summaries and produces Items within a Briefing Section. Erik has independently derived the same two-entity distinction I identified (Signal vs Item) through the cost optimization lens.

Erik's `UserPreferenceSnapshot` design maps directly to my Priority context's PriorityProfile aggregate with the `compact_text` field serving as the Published Language between the Priority context and the Briefing context. The 300-token bounded context injection is the correct way for the Priority context to provide its output to the Briefing context without the Briefing context needing to query and understand the full PriorityProfile aggregate structure. This is an excellent example of Published Language in practice.

The eval strategy (three tiers: deterministic, LLM-as-judge, human sample) is domain-significant because it operationalizes what "briefing quality" means. In my domain model, the Briefing aggregate has an invariant: "A Briefing must have at least one Section to be marked Ready." Erik's deterministic checks make this invariant testable. The LLM-as-judge checks the semantic quality — whether the relevance scoring in the Priority context actually matched the content in the Briefing context.

One domain model note: Erik's `BriefingOutput` schema has `top_items`, `full_digest`, and `action_items`. In my Briefing context, I named these constructs as Sections (grouped by type) containing Items. Erik's schema is a flat ranking view. These are different semantic structures — one is organized by section (topic grouping), the other by priority (ranked list). The domain should pick one and name it consistently. If the business says "briefing has sections," the schema should use sections, not ranked arrays.

**Missed gaps:**

- Erik's preference snapshot generation (weekly Haiku job) is a domain event in disguise. The `PriorityUpdated` event I named in my context map happens both when a user explicitly updates priorities AND when the system regenerates the learned preference snapshot. Erik does not surface this as a domain event — it is described as a technical background job. The domain model should name when a PriorityProfile is updated and who gets notified.
- The `why_relevant` field on `BriefingItem` is a critical domain concept Erik buries in a schema detail. This is the explanation of relevance — why a particular signal became an item. This is not just a UX field; it is the feedback data that closes the learning loop in the Priority context. It deserves first-class treatment in the domain model.

**Rank: Strong**

---

### Analysis F — Devil's Advocate (Fred)

**Agreement:** Partially Agree

**Reasoning from domain perspective:**

Fred's most powerful critique — the one I cannot dismiss — is Contradiction #1: the behavioral memory moat thesis conflicts with the 30-day build timeline and the 14-day trial conversion measurement.

Let me engage with this directly from the domain perspective. Fred says: "On day 1 of the free trial, behavioral memory is EMPTY. The moat does not exist at the point where the kill gate is measured."

This is correct. But it does not mean the domain model for behavioral memory should be abandoned. It means the PHASE of the domain development is different from what the business blueprint implies.

The Priority context I designed has two sub-components: DeclaredPriority (available on day 1 of the trial) and LearnedSignal (available after 14-90 days of engagement). The Phase 2 MVP needs the DeclaredPriority side fully built and working well to convert trial users. The LearnedSignal side needs to be designed but can be minimally implemented — even just capturing engagement events and storing them is sufficient to start accumulating the data for the moat.

Fred's proposed fix — "a JSON file of explicit preferences is sufficient for the trial" — is acceptable for the DeclaredPriority half but catastrophically wrong for the LearnedSignal half. If we use a JSON blob for explicit preferences at launch, we will later need to migrate that blob into a structured schema at the exact moment when users have accumulated engagement data that we cannot retroactively attach to the new schema. This is the migration nightmare I named in my Critical Issues section. The schema must be correct from day one even if the learning algorithm is minimal.

Fred's Contradiction #5 (8 bounded contexts for a 2-person team) repeats the conflation of domain model with deployment model. He quotes Sam Newman's "start with a monolith" rule — but Newman is talking about microservices deployment topology, not DDD bounded contexts. A monolith WITH clean domain boundaries is not a contradiction; it is Newman's preferred alternative to microservices. Fred is arguing against the wrong thing.

Fred's critique of "DDD theater" is earned when the context boundaries are enforced via separate services, separate databases, and asynchronous messaging. It is not earned when the boundaries are enforced via module structure and naming conventions within a monolith.

Fred's stress test #5 (kill gate fires at day 90) is the most useful challenge for me personally. He asks: "What is the minimum implementation that would let you MEASURE trial-to-paid conversion without building the full infrastructure?" From a domain perspective, the answer is: you need the Briefing context fully working (compilation, delivery), the Priority context working for declared preferences, the Workspace context with tier enforcement, and the Notification context for Telegram delivery. You can defer the Source ACL completeness (start with RSS and HN only, no Gmail), defer LearnedSignal implementation (capture events but don't use them yet), and defer multi-workspace support for Pro tier. That is still 4-5 context implementations, not the 3-table monolith Fred proposes — because the briefing compilation and the workspace tier enforcement are genuinely separate concerns with separate invariants.

**Missed gaps:**

- Fred's proposed counter-architecture (3 tables: users, source_configs, briefings) has a fatal domain flaw: it has no Usage Ledger. The Board mandated hard caps at the infrastructure level. Without the UsageLedger domain concept, cap enforcement is either missing (costs spiral) or embedded as a column on the users table (race condition on concurrent briefings). This is not an academic concern — it is a financial control that the business explicitly requires.
- Fred's claim that "behavioral memory is not the moat — prompt quality is the moat" may be correct for the 90-day kill gate, but it is not correct for the 12-24 month retention story. The moat at month 12 is the 10 months of learned user behavior that a competitor would need to replicate. Fred dismisses this in one paragraph without engaging with the data portability and retention design questions I raised.

**Rank: Moderate**

---

### Analysis G — Security Architect (Bruce)

**Agreement:** Agree

**Reasoning from domain perspective:**

Bruce's analysis has one critical domain modeling implication that reinforces my architecture: his insistence that `oauth_tokens` belong to the auth domain (my Identity context), NOT the sources domain.

Bruce writes: "The `sources` domain receives a decrypted access token injected at task start — it never touches the encrypted storage layer. This is critical for blast-radius containment."

This is exactly the Anti-Corruption Layer pattern applied for security. The Source context does not know how credentials are stored or encrypted. It receives a decrypted access token as an input to the ingestion process. The encrypted token storage is an infrastructure concern within the Identity/Auth context. Mixing credential storage into the Source context would create a coupling where source configuration changes could inadvertently affect credential access patterns — and vice versa.

Bruce's prompt injection threat (Contradiction #3 from Fred's analysis reframed as a security concern) is also a domain modeling issue. The sanitization layer he proposes is the ACL for RSS content: untrusted external content must be translated into a Signal (our internal concept) BEFORE it enters the domain. Raw RSS content is not a Signal — it is external data. The ACL translates it. Bruce's sanitization function is the implementation of that translation step.

The IDOR (Insecure Direct Object Reference) threat maps directly to my workspace isolation invariant. Bruce writes: "ALWAYS join workspace_id to user_id in every DB query." In domain terms: the Workspace context is the authorization boundary. Every other context must verify workspace ownership before operating. This is the `WorkspaceReady` event pattern I designed — downstream contexts only act within a workspace that has been authorized.

**Missed gaps:**

- Bruce identifies Google App Verification as a critical launch blocker (4-6 week review for Gmail scopes) but does not map this to the domain model. In domain terms: a Source with type `Gmail` is not activatable until the workspace's OAuth grant has been verified by Google. This is a domain state transition (Source status: pending-verification → verified) that should be modeled in the Source aggregate, not just in operations notes.
- Bruce's data retention policy specifies that Gmail content should "never be stored" — only the briefing output persists. This has a direct implication for my Signal entity: Signals from Gmail are ephemeral (in-memory only, consumed during compilation, never persisted). This contradicts my Source context design where I modeled `Signal` as a persisted entity with a 48-hour garbage collection window. For Gmail specifically, the Signal is never persisted. This is an important domain rule that needs to be explicit: Signal persistence policy varies by SourceType.

**Rank: Strong**

---

### Analysis H — Operations Engineer (Charity)

**Agreement:** Agree

**Reasoning from domain perspective:**

Charity's most domain-relevant insight is the BullMQ recommendation over node-cron. From a domain perspective, the shift from in-memory cron to persistent job queue is a domain state management decision. A scheduled briefing compilation is not just a scheduled function call — it is a domain event (`BriefingCompilationRequested`) with a specific workspace, a specific time window, and a durable commitment to execute. If that commitment is lost on process restart, it is a data integrity failure, not an infrastructure failure.

BullMQ with Redis persistence is the implementation of that commitment durability. When Charity says "a cron job that fails silently and produces no output is a conversion killer during a 14-day trial," she is making a domain reliability argument. The Briefing aggregate's invariant — "A scheduled briefing must either compile successfully or fail explicitly (and the failure must be visible)" — requires that the scheduling mechanism be durable. node-cron fails this invariant silently.

The degraded mode delivery strategy Charity describes ("deliver something, always") maps to a domain design decision in the Briefing context. In my aggregate design, I said a Briefing must have at least one Section to be marked Ready. Charity's recommendation implies a "degraded" briefing status: compiled with fewer sources than configured, but still delivered. This may require adding a `BriefingStatus.degraded` state to my aggregate — delivered, but with explicit note of missing sources.

The circuit breaker per source maps to the SourceHealth aggregate I designed in the Source context. Each Source has a SourceHealth value object. When the circuit breaker opens (3 consecutive failures), that is SourceHealth transitioning to "unhealthy." The `SourceHealthDegraded` domain event I defined fires at this transition, not just when delivery fails.

The operations persona's recommendation that each domain boundary should correspond to a trace span boundary is important for practical domain visibility. It makes the domain model observable at runtime.

One tension worth noting: Charity recommends using BullMQ + Redis as an "agent-runtime" domain concern, and even says "agent-runtime domain owns the BullMQ queue." I rejected "agent-runtime" as a bounded context in my Phase 1 analysis because it is a technical term. Charity is using it in a narrower sense — as the module that owns job scheduling infrastructure. This is a legitimate infrastructure module, but it is not a domain bounded context. The scheduling of a briefing compilation is triggered by the Briefing context (a `BriefingCompilationRequested` event). How that scheduling is implemented (BullMQ, cron, direct function call) is an infrastructure detail inside the Briefing context's infra adapter.

**Missed gaps:**

- Charity's graceful degradation decision tree does not distinguish between SourceType behavior. A Gmail failure is more significant than an RSS feed failure because Gmail failure means the user's email triage section is missing — which is specifically what many users will configure as their primary use case. The degradation policy should be weighted by source type importance, not just "required source" flag.
- The observability model captures `sources_failed` as a log field but does not emit this as a domain event. `SourceHealthDegraded` should be a first-class domain event that the Notification context consumes to alert the user. Currently it appears as an operational alert to the founder's phone — the user who owns the source is not notified through the product.

**Rank: Strong**

---

## Ranking

**Best Analysis:** C (Martin, Data Architect)

**Reason:** Martin's schema design is the most faithful physical implementation of the domain model I designed. The separation of `preferences` from `memory_signals`, the append-only `usage_ledger`, and the `briefing_feedback` event log are all direct implementations of domain invariants I named (DeclaredPriority vs LearnedSignal, UsageLedger as a fact ledger, Engagement as behavioral data). Martin worked from the same truth about what the business requires and arrived at consistent structural conclusions. He also correctly identified the most dangerous data design mistake (mutable task counter under concurrency) and provided the atomically correct fix.

**Worst Analysis:** A (Dan, DX Architect)

**Reason:** Dan makes the most consequential architectural error: he concludes that "auth is not a domain" because Clerk handles it, and therefore no domain boundary is needed around it. This is precisely backwards. Because Clerk is an external vendor with its own concepts (Organizations, Sessions, Members), a domain boundary with an Anti-Corruption Layer is MORE necessary, not less. Dan's recommendation to import Clerk directly throughout the codebase without a wrapper would be the most expensive technical debt in the system — the kind that requires a full rewrite when Clerk changes its pricing or API, or when you need to switch to BetterAuth. The briefing system's dependency on Clerk would be woven through every part of the codebase rather than isolated to a single adapter.

---

## Revised Position

**Revised Verdict:** Same as Phase 1, with two refinements.

**Refinement 1: Signal persistence policy varies by SourceType (from Bruce)**

Bruce's security analysis identified that Gmail email content must never be stored persistently. This is correct both for security and privacy reasons. My Phase 1 analysis modeled `Signal` as a persisted entity with 48-hour garbage collection. I need to refine this:

- RSS Signals: CAN be persisted (public content, no PII)
- HN Signals: CAN be persisted (public content)
- Gmail Signals: MUST NOT be persisted (private PII — email subjects, sender names, snippets)
- Calendar Signals: MUST NOT be persisted (private PII — meeting titles, attendee names)

The Signal entity needs a `persistencePolicy` value object that encodes this rule. Gmail and Calendar sources produce ephemeral Signals (consumed during compilation, never stored in the database). This affects the garbage collection logic — there is nothing to collect for ephemeral Signals because they are never written.

**Refinement 2: Briefing has a Degraded state (from Charity)**

My Phase 1 aggregate design had BriefingStatus: pending, compiling, ready, delivered, failed. Charity's degraded delivery pattern requires adding `degraded` as a valid terminal state: compilation completed with fewer sources than configured, but delivered. A `degraded` briefing is not a failed briefing. The user receives it with a note about unavailable sources. The Workspace context should still count it as a task consumed (the compilation ran). The Notification context should flag it visually (e.g., "partial briefing — 3 of 5 sources available").

**Final Domain Recommendation:**

The bounded context model stands with seven contexts as designed. The implementation approach should be monolith-first (single Fly.io deployment) with clean module boundaries enforcing the context separations. The specific implementation priorities for Phase 2 MVP are:

1. Briefing context (core domain — synthesis, Section/Item model, status machine including Degraded)
2. Source context (supporting — with ACL for each external source, Signal ephemeral-by-default for PII sources)
3. Priority context (core domain — DeclaredPriority first, LearnedSignal schema designed but minimally implemented)
4. Workspace context (supporting — tier enforcement, UsageLedger as append-only, atomic cap check)
5. Notification context (supporting — Telegram channel, DeliveryAttempt, graceful degradation notification)
6. Identity context (generic — Clerk ACL, only in infra/auth, never imported elsewhere)
7. Billing context (generic — Stripe ACL, SubscriptionChanged event)

The behavioral memory moat (LearnedSignal in Priority context) must have its schema designed correctly from day one (the feedback event table and signal table as Martin specified), even if the learning algorithm is minimal at launch. The data must be collected from the first user's first engagement. The algorithm can be improved later. You cannot retroactively collect data you did not design to collect.

The kill question passes: the architecture can be explained entirely in business terms. A workspace is set up with sources. Every morning the system reads those sources, filters for what matters to the user's declared priorities, compiles a briefing, and delivers it. The system learns from how the user engages with each briefing to improve future relevance. Tiers limit how many briefings a workspace can compile per month. None of these sentences require technical jargon.
