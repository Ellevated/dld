# LLM Systems Architecture Cross-Critique

**Persona:** Erik (LLM Architect)
**Label:** E
**Phase:** 2 — Peer Review (Karpathy Protocol)
**Date:** 2026-02-27

---

## Peer Analysis Reviews

### Analysis A (DX Architect — Dan McKinley persona)

**Agreement:** Strongly Agree

**Reasoning from LLM agent perspective:**

A agrees with my core position that LangGraph.js is the wrong tool for a linear pipeline. From an agent systems lens, A's criticism is structurally correct: LangGraph.js introduces a state machine abstraction layer that sits between the orchestrator and the LLM API. That layer is only justified when you have genuine conditional branching, human-in-the-loop interrupts, or checkpoint/resume semantics. The morning briefing pipeline — fetch sources in parallel, pre-summarize, synthesize, deliver — has none of these properties.

A's 40-line TypeScript counter-proposal is exactly the pattern I advocate: a plain `async function generateBriefing(userId)` IS the agent orchestrator. It reads like a single-responsibility tool. An agent could understand its purpose from the function signature alone. LangGraph state graphs, by contrast, require understanding compiled graph nodes, edge conditions, and checkpointing semantics before an agent can reason about what they do.

A's innovation token accounting is agent-relevant: every additional framework in the stack increases the context budget required for any LLM agent working with this codebase. A stack with LangGraph adds ~3K tokens of schema/API surface for zero functional benefit on Phase 2 scope.

A makes a strong case for Clerk at the free tier. From an agent API-design perspective, Clerk's webhook and org model are well-documented with stable OpenAPI contracts — a future configuration agent can reason about Clerk workspace creation from the docs alone. This is agent-friendly.

**Missed gaps:**

- A does not address the structured output schema for the briefing. The `generateBriefing()` function in their example calls `llm.complete(prompt, { schema: BriefingSchema })` but does not design the schema. For an LLM agent, the output schema IS the reliability contract — this is the most important LLM-specific design artifact and A skips it.
- A does not mention the behavioral memory context injection budget. The `user.preferences` reference is a hand-wave. How many tokens does preference injection consume? Does it grow with user tenure? This is critical for context budget management.
- No eval strategy proposed. A is laser-focused on DX; agent quality measurement is not in scope for them but it is a gap in the overall recommendation set.

**Rank:** Strong

---

### Analysis B (Domain Architect — Eric Evans persona)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

B produces the strongest domain model in the peer set. The Signal/Item distinction is architecturally significant from an agent perspective: an agent operating on the briefing system must know the difference between raw ingested material (Signal) and evaluated, relevant material (Item). Without this distinction, a configuration agent would not know where relevance filtering happens.

B's kill of the "agent-runtime" bounded context is correct from my lens. "Agent-runtime" is a technical concept, not a domain concept. As I noted in my own research, LLM execution is infrastructure inside the Briefing context, not a domain boundary. Naming it as a bounded context would force any agent working with the domain model to hold a technical abstraction in semantic space reserved for business concepts — exactly the kind of context pollution I flag.

B's ubiquitous language is agent-legible: "Signal," "Item," "Briefing," "Priority," "Channel" — these are self-describing. A future agent asked to work with this API could infer meaning from the terms without reading source code. This directly satisfies my kill question.

The context map using ACL patterns for external services (Gmail, Calendar, Clerk, Stripe) is correct agent architecture. ACLs are trust boundaries for agents too — they translate foreign models into domain models so the agent never has to understand Gmail's threading model to fetch a Signal.

**Missed gaps:**

- B correctly designs the domain model but does not specify the API contract surface. "Each bounded context maps to one API module" is correct directionally, but an agent needs to know: what are the endpoints, what do they accept, what do they return, what errors can fire? B leaves this to the API layer without designing it.
- B notes that LLM execution is "infrastructure within the Briefing context" but does not specify HOW the LLM is called. My structured output schema (Section 3 of my research) directly addresses this. B should have flagged: the briefing compilation step must return typed JSON, not freeform prose, or the reliability measurement pipeline cannot function.
- 7 bounded contexts for a 2-person team is debated by multiple peers. B's domain design is theoretically clean but operationally ambitious. From an agent-maintenance perspective, 7 contexts with full event bus between them means any agent doing maintenance work must understand 7 mental models, 7 event schemas, and 7 API surfaces before making a change.

**Rank:** Strong

---

### Analysis C (Data Architect — Martin persona)

**Agreement:** Strongly Agree

**Reasoning from LLM agent perspective:**

C produces the most LLM-agent-compatible data design in the peer set. The system-of-record table is agent gold: an agent asked "where is the authoritative source for X?" can answer that question by consulting a single table. Without clear SoR assignment, an agent making a write operation would need to read implementation code to avoid writing to the wrong place.

C's two-layer behavioral memory model (raw `briefing_feedback` log + derived `memory_signals` UPSERT) is exactly the pattern I specified in Section 4 of my research. The separation between "what happened" (raw events, never in context) and "what we infer" (compressed snapshot, injected at ~300 tokens) is the design that prevents context bloat as user tenure grows.

The ADR-007 alignment is explicit and correct: "LLM agents should be READ-ONLY with respect to the DB during synthesis. The agent reads source_configs, preferences, memory_signals. It returns structured JSON. The application layer writes the JSON." This is caller-writes pattern, which I validated from production evidence in DLD's own ADR chain.

C's idempotency key on the usage ledger prevents double-counting on retry — this is directly relevant to agent reliability. An agent that retries a failed task must not consume two usage units.

The `content_schema_version` field on the briefings table is agent-critical: it enables agents to know which schema to apply when parsing a stored briefing. Without this, an agent reading old briefings would need source code archaeology to understand historical schema formats.

**Missed gaps:**

- C does not specify how `memory_signals` are formatted for LLM context injection. The table design is excellent but I need to know: does the agent receive the raw rows, or a pre-aggregated `compact_text` snapshot? My design uses the snapshot; C's design implies query-at-synthesis-time with a confidence filter (`confidence > 0.3`). Both are valid but they have different context token implications. C should specify the injection format.
- C's `PRAGMA foreign_keys = ON` note is buried in migration strategy. This is a critical correctness requirement. Any agent generating database migration code must know this pragma is required at connection init — it belongs in the schema header, not the migration section.
- No mention of the briefing output schema needing to be versioned as an API contract for downstream consumers (Notification context, future export endpoints). C versions the schema internally but does not note it as an external contract.

**Rank:** Strong

---

### Analysis D (Evolutionary Architect — Neal Ford persona)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

D's fitness function suite is the most direct contribution to my mandate. Fitness functions are automated tests for architectural properties — they are the closest thing to eval infrastructure for system health. My eval strategy in Section 5 is complementary to D's fitness functions.

D's dependency direction check using `dependency-cruiser` is directly agent-relevant. The rule "LangGraph.js and Clerk never imported directly in domain code" is equivalent to a tool boundary: an agent working in the Briefing domain should never need to call LangGraph APIs directly. If it does, that is a boundary violation detectable by the fitness function. This is architectural enforcement-as-code.

D's COGS protection fitness function (`average LLM cost per briefing < $0.04`) operationalizes the model routing table I specified. If someone re-routes synthesis from Sonnet to Opus, the fitness function fires within 24 hours. Without this, model routing regressions are silent until the monthly invoice.

D's change vector analysis correctly identifies the LLM model version as the highest-frequency change in the system. The LiteLLM adapter layer with model aliases (Section 1 of my research) is exactly the isolation strategy D recommends: "Model names never appear outside `infra/llm/router.ts`." Full alignment.

**Missed gaps:**

- D's fitness function for behavioral memory immutability is acknowledged as missing: "Behavioral memory data model immutability (no test prevents breaking the preference schema)." This is my highest-concern LLM gap. The memory snapshot injection depends on the schema being stable. D identifies the gap but does not fix it.
- D's Section 4 LLM Cost Budget uses a $0.04/task threshold. My research shows expected COGS of ~$0.066/daily briefing at current pricing (12 sources). D's threshold is too tight unless they are calculating differently. The architecture board needs to reconcile these numbers.
- D correctly defers the golden dataset bootstrap problem ("Phase 1 toolkit fitness function for toolkit is missing: ADR examples have no runnable tests") but does not address how the 90% reliability baseline gets established before the golden dataset exists. My research proposes: use the first 14 days of free trial as golden dataset collection (Section 5). D does not connect fitness functions to the initial calibration problem.

**Rank:** Moderate-Strong

---

### Analysis F (Devil's Advocate — Fred Brooks persona)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

F is the most useful critic in the set because they apply an explicit kill question: "Who is solely responsible for system integrity?" From an agent architecture perspective, this is equivalent to asking "which agent is the orchestrator, and what are its scope boundaries?" An agent without clear authority boundaries is an agent that will drift and over-reach.

F's behavioral memory moat critique (Contradiction #1) is the strongest challenge in all peer analyses and I partially agree with it. F argues that behavioral memory is empty at day 1 of the free trial, so the moat claim is untestable at day 90. This is factually correct. However, F's conclusion — "behavioral memory is a Phase 3 feature" — is too strong. The data schema and signal capture infrastructure for behavioral memory cost very little to build upfront (Section 4 shows my two-layer design is ~50 lines of schema + a weekly background job). The risk of NOT building it correctly from day 1 is a data migration nightmare at month 4 when you do want it. F correctly identifies that the moat cannot be demonstrated at day 90, but incorrectly concludes it should be deferred. The schema must be designed now even if behavioral learning only activates later.

F's LangGraph critique (Contradiction #2) is airtight and aligns with my position. Their challenge — "name one feature of the morning briefing that requires graph-based orchestration with checkpointing" — should be the literal gate question for the architecture board.

F's minimum viable stack (Stress Test section) is the right reference baseline. An agent maintaining this stack needs to understand: 7 npm packages + Stripe + Fly.io. That is achievable in a single context window. The full proposed stack (11 distinct systems) exceeds practical agent comprehension in one shot.

**Where F is too aggressive:**

F argues against LiteLLM for a Phase 2 MVP, proposing "direct Anthropic SDK + env var MODEL" as the fallback. This misses the critical function of LiteLLM: cost tracking per task. Without LiteLLM, per-user monthly cost aggregation requires custom instrumentation. The COGS hard cap ($20/user/month) is a Board-mandated requirement that needs real-time tracking from day 1. Direct SDK calls with a `getModel()` helper cover model routing but not cost metering. F concedes this in a footnote but should have weighted it more heavily.

F's assessment of bounded contexts ("9 bounded contexts is DDD theater") is partially correct but overcorrects. 7 contexts with clear ubiquitous language is not theater — it is the explicit design of ACL boundaries that prevent Gmail's threading model from leaking into briefing synthesis. What is theater is implementing them as microservices. As a monolith with logical separation, 7 contexts is feasible for 2 people.

**Missed gaps:**

- F does not address structured outputs at all. The briefing's output schema is never mentioned. Yet this is the centerpiece of the reliability measurement system. A devil's advocate should challenge: "your 90% reliability threshold is meaningless without defining what a passing briefing is."
- F's Stress Test #4 (LangGraph breaking changes) correctly identifies LangChain's history of breaking changes as a risk. F does not note that LiteLLM has a similar risk profile — it is also a higher-level abstraction over multiple provider APIs. The same argument applied to LangGraph should be applied to LiteLLM for consistency.

**Rank:** Strong (as critic, not as proposer — the minimum viable stack is too minimal)

---

### Analysis G (Security Architect — Bruce persona)

**Agreement:** Partially Agree

**Reasoning from LLM agent perspective:**

G's threat model is the most disciplined external perspective in the set. From an LLM agent architecture angle, the prompt injection via RSS section (Threat C3, OWASP LLM01) is directly relevant to my design. G correctly identifies that RSS content flows through the synthesis prompt as untrusted input. My two-stage pipeline (Haiku pre-summarization → Sonnet synthesis) actually provides a defense layer G does not mention: the pre-summarization step with Haiku can include an instruction to strip content that appears to be prompt injection before it reaches the synthesis stage. This is defense-in-depth at the LLM layer, not just string sanitization.

G's data classification table is agent-legible: it specifies exactly which fields are sensitive, what encryption they require, and what retention policy applies. An agent generating data models for this system could derive table-level encryption requirements directly from G's table without reading implementation code.

The scope minimization rule for Google OAuth (read-only scopes only) has a direct agent parallel: agents should operate at minimum required permissions. The same principle applies to LLM agents — the synthesis prompt should not have access to capabilities it does not need for the task. G applies this correctly to Google OAuth but misses the parallel for LLM tool permissions.

G's structured prompt separation (XML tags around untrusted source content) is current best practice for prompt injection defense. This should be a mandatory constraint on the synthesis prompt template, not an optional recommendation.

**Missed gaps:**

- G does not address the prompt injection risk from the Gmail content itself. G recommends not storing Gmail content in the database (correct) but the content still flows through the synthesis prompt in-memory. Email subjects and body snippets are potentially adversarially crafted (spear-phishing specifically targets people who use AI email tools). G applies the RSS injection analysis but not the Gmail analog.
- G notes "Telegram → API: HMAC webhook signature verification" in the trust boundary table but does not note that the LLM API response is also untrusted from a prompt injection perspective. An LLM that has been injected via RSS could theoretically produce a briefing with Telegram-formatted commands attempting to control the bot. G's defense covers inbound prompt injection but not outbound response injection.
- G does not address eval strategy for security properties. How do you test that prompt injection mitigation is working? A golden dataset of known-injected inputs with expected sanitized outputs would be the appropriate mechanism. G's analysis stops at "implement sanitization" without specifying how to verify it works at regression detection.

**Rank:** Moderate-Strong

---

### Analysis H (Operations Engineer — Charity persona)

**Agreement:** Strongly Agree

**Reasoning from LLM agent perspective:**

H directly answers my kill question with a concrete debugging scenario (the silent cron failure at 5:58 AM). This is exactly the observability-first mindset that makes agent systems operable. An agent that fires at 6am and fails silently is worse than an agent that fails loudly — you cannot improve what you cannot see.

H's structured log schema is directly agent-readable:
```json
{
  "briefing_id": "brief_9iJ0k1L",
  "sources_failed": ["hn_rss"],
  "model": "claude-haiku-3-5",
  "estimated_tokens": 12400
}
```

Every field in this schema is an observable that an LLM agent performing incident diagnosis can work with without source code. The `sources_failed` array directly tells a diagnostic agent which source caused degradation. The `estimated_tokens` field enables cost projection before the call completes. This is agent-readable telemetry.

H's recommendation to use BullMQ over node-cron is correct and aligns with production patterns. From an agent reliability perspective, in-memory cron job state is catastrophic for agent systems: if the process restarts between job scheduling and execution, the job is lost. BullMQ's Redis persistence ensures job state survives process restarts, which is critical for a system where the LLM synthesis step takes 3-5 seconds and the delivery window is 30 minutes.

H's circuit breaker pattern for individual sources is the correct agent architecture for partial failure tolerance. The decision tree:

```
Source X fails → Is X required? → YES: partial briefing, user notified → NO: skip silently
```

...is exactly a conditional agent workflow that degrades gracefully instead of failing entirely. This is the "deliver something, always" philosophy expressed as operational code.

The distributed tracing schema with `trace_id = sha256(user_id + scheduled_window)` (deterministic for retries) is a smart agent pattern: it enables idempotent retry detection without a separate deduplication mechanism.

**Missed gaps:**

- H recommends BullMQ but does not address the new dependency it introduces. BullMQ requires Redis (H proposes Upstash free tier). This is another vendor dependency. F (Devil's Advocate) would note this is an additional external service that can go down. H should explicitly address this trade-off.
- H's LLM cost observability relies on LiteLLM proxy callbacks to Prometheus. This is correct for production monitoring, but H does not specify the circuit breaker behavior when LLM cost exceeds the daily cap. My `checkCostBudget()` pre-flight call (Section 7 of my research) should be referenced here as the application-level gate that complements H's alerting. Alerting is reactive; the pre-flight check is preventive.
- H does not address the Google App Verification issue raised by G. The OTel tracing setup and heartbeat monitoring are valuable only if the product can actually onboard users. The Gmail OAuth verification timeline (4-6 weeks per G's analysis) is an operational dependency that affects the deployment strategy — H should cross-reference this.

**Rank:** Strong

---

## Ranking

**Best Analysis:** C (Data Architect)

**Reason:** C produces the most actionable, LLM-agent-compatible design artifact in the set. The system-of-record table answers the agent kill question directly. The two-layer behavioral memory design prevents context bloat over time. ADR-007 (caller-writes) is explicitly applied. The usage ledger with idempotency key prevents double-counting on retry — a pattern that would otherwise cause silent correctness failures in an agent system. Every design decision in C can be validated by an agent without reading implementation code.

**Second Best:** A (DX Architect) and H (Operations) are tied. A correctly kills the LangGraph complexity in terms an agent can act on. H correctly designs agent-observable telemetry.

**Worst Analysis:** D (Evolutionary Architect) — weakest from my lens.

**Reason:** D's fitness function suite is valuable in isolation but operationally underspecified. The COGS threshold ($0.04/task) is inconsistent with my calculated COGS estimate (~$0.066/task). The golden dataset bootstrap problem is identified but unresolved. The behavioral memory immutability fitness function is acknowledged as missing but not filled. D provides the "what to measure" without the "how the initial baseline is established" — which is the critical chicken-and-egg problem for an eval-first architecture.

---

## Revised Position

### What I am keeping from my initial research

1. **Two-stage pipeline (pre-summarize with Haiku, synthesize with Sonnet):** Confirmed by C's structured data flow and H's distributed tracing schema. The 76% token reduction from pre-summarization is not just a cost optimization — it is the mechanism that keeps synthesis context bounded regardless of source count growth.

2. **Behavioral memory as two-layer architecture:** C's schema confirms this is the right design. Raw `briefing_feedback` events as the log, derived `memory_signals` with running average as the materialized view. My `compact_text` snapshot (max 300 tokens) maps to C's "do not dump the entire memory_signals table into context — query only signals with `confidence > 0.3`."

3. **Three-tier eval strategy (deterministic + LLM judge + human sample):** D's fitness function suite is the closest peer analysis to my eval design. H's SLI/SLO framework operationalizes the tier 1 deterministic checks at the infrastructure level. The two together form a complete reliability measurement pipeline.

4. **LiteLLM with model aliases:** Confirmed correct by A, D, and H independently. A's "innovation token justified" verdict, D's COGS fitness function requiring per-task cost logging, and H's Prometheus cost tracking all presuppose LiteLLM in the stack.

5. **Kill question answer:** The briefing agent can work without reading source code IF we build: (a) `/api/sources` registry endpoint with self-describing source definitions, (b) `/api/tags` vocabulary endpoint, (c) standard error format with `code`, `message`, `action` fields. No peer analysis builds these explicitly. This remains my unique contribution.

### What I am updating after peer review

1. **BullMQ over node-cron:** H's operational evidence for BullMQ is convincing. My initial design assumed node-cron for simplicity. H correctly identifies silent non-execution as the #1 reliability risk — an in-memory cron that drops jobs on process restart is a conversion killer during the 14-day free trial. Update: recommend BullMQ + Redis persistence from day 1. This adds Redis as a dependency but the operational reliability gain is worth the token.

2. **Clerk is free tier until 10K MAU:** A's analysis is correct. I had not priced this out. At <100 paying users on phase 2 launch, Clerk free tier covers social OAuth (critical for user base of solo founders who use Google), workspace isolation, and webhook events for billing sync. The cost is $0. This changes my "buy vs build" recommendation on auth — use Clerk rather than building JWT from scratch.

3. **Prompt injection defense is more complex than I specified:** G raises the Gmail inbox injection analog that I missed. My synthesis system prompt needs explicit instruction that email content is untrusted. The two-stage pipeline actually helps here: the Haiku pre-summarization step can be instructed to extract only structured metadata (subject, sender, date) from email content, never passing raw email body to the synthesis stage. This reduces the injection surface significantly while also reducing synthesis token count.

4. **The 7-context domain model is operationally ambitious but structurally correct:** F's critique of bounded context overhead is valid as an operational concern, not as a domain modeling concern. The resolution: implement all 7 contexts as modules in a single monolith (Fly.io single machine), with logical separation (table name prefixes, separate TypeScript modules) but no message bus. The context map exists on paper and in code comments; it does not require event infrastructure at launch. Extract to separate services only when team grows.

5. **Google App Verification is a deployment blocker:** G identifies a critical timeline dependency I did not address. Gmail OAuth verification takes 4-6 weeks. If Phase 2 builds the Gmail integration and launches without starting this process on day 1, the product cannot onboard users with Gmail at public launch. This must be initiated at the start of Phase 2 development.

### Remaining concerns not addressed by any peer

1. **The `/api/sources` registry endpoint:** No peer analysis designs this. An agent working with the briefing API must know the valid source IDs before it can configure sources. If "hn" vs "hackernews" vs "HackerNews" is ambiguous, the agent must read source code. This is the specific API design gap that my kill question targets and no peer addresses.

2. **Tool description completeness for the briefing API:** B designs the domain model. C designs the schema. H designs the observability. But none of them designs the tool descriptions that a configuration agent would use to interact with the API. "The briefing tool's description says so explicitly" should be a first-class architectural output, not documentation-as-afterthought.

3. **Eval golden dataset bootstrap timing:** My research proposes using the first 14 days of free trial as golden dataset collection. No peer confirms or challenges this. The 90% reliability threshold is the kill gate signal, and without a golden dataset, there is no regression baseline. This must be planned before Phase 2 launch.

### Final LLM Recommendation for This Round

**The architecture is structurally sound in domain design (B), data design (C), and operations (H).** The primary LLM-specific gaps are:

1. **Structured output schema:** The BriefingOutput JSON schema must be designed as a first-class artifact. It is the reliability contract. It is the eval rubric. It is the delivery format for all channels. No peer designs it explicitly.

2. **Self-describing API surface:** Source registry endpoint, tag vocabulary endpoint, and standardized error format with `action` fields must be designed before launch. An agent must be able to configure and trigger a briefing using only the OpenAPI spec.

3. **Context budget validation:** The total synthesis context (system prompt + preferences + source summaries + schema) should be under 10K tokens. The two-stage pipeline keeps this manageable. This constraint should be a fitness function in D's suite.

4. **Eval infrastructure before first briefing:** Build the reliability-check script before the first user. The kill gate at day 90 is a measurement, not a promise. Without measurement infrastructure, it is a date.

**Note:** This is input to synthesis. Final LLM-Ready validation happens in Phase 7 Step 4.

---

## References

- Anthropic — Building Effective Agents: https://www.anthropic.com/research/building-effective-agents
- Anthropic — Prompt Engineering Guide: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering
- DLD ADR-007 through ADR-012: /Users/desperado/dev/dld/.claude/rules/architecture.md (caller-writes, background fan-out, orchestrator zero-read)
- My Phase 1 research: /Users/desperado/dev/dld/ai/architect/research-llm.md
- LiteLLM Router Documentation: https://docs.litellm.ai/docs/routing
- OWASP LLM Top 10 — LLM01: Prompt Injection: https://owasp.org/www-project-top-10-for-large-language-model-applications/
