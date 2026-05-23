# Domain Architecture Research

**Persona:** Eric (Domain Modeler)
**Focus:** Bounded contexts, ubiquitous language, domain boundaries

---

## Research Conducted

*Note: Exa MCP rate limit was reached during parallel search launch. Research below is conducted
from first principles using the full business blueprint, architecture agenda, and deep DDD
pattern knowledge. The analysis is grounded in the domain descriptions provided — not in
technical assumptions.*

- [Eric Evans — Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/) — core bounded context and context mapping patterns
- [Vaughn Vernon — Implementing Domain-Driven Design](https://vaughnvernon.com/?page_id=168) — aggregate design and ubiquitous language construction
- [Martin Fowler — BoundedContext](https://martinfowler.com/bliki/BoundedContext.html) — context boundaries follow team and language, not technology
- [Martin Fowler — ContextMap](https://martinfowler.com/bliki/ContextMap.html) — relationship patterns between contexts
- [DDD Community — Context Mapping Patterns](https://github.com/ddd-crew/context-mapping) — ACL, OHS, Published Language, Customer-Supplier
- [Alberto Brandolini — Event Storming](https://www.eventstorming.com/) — discovering domain events through business language
- Deep Research: Morning briefing domain model — structured data synthesis, user preference learning, source aggregation (analysis from blueprint + domain principles)
- Deep Research: Phase 1/Phase 2 code sharing boundary — consulting IP vs. product domain separation

**Total queries attempted:** 6 parallel (rate-limited) + 2 deep research via first-principles analysis from full blueprint context

---

## Kill Question Answer

**"Can you explain the architecture using only business terms?"**

Let me try: "A user tells the system which information sources matter to them and what topics
they care about. Every morning, the system reads those sources, filters for what is relevant
to that specific user's work, and sends them a summary. The system gets smarter over time
because it remembers what the user has found useful in the past."

**Assessment: PASSES.** The core Phase 2 domain can be described entirely in business language.
No technical abstraction is required for the briefing loop.

**Warning sign detected:** The architecture agenda uses the term "agent-runtime" as a bounded
context. This is a **technical term masquerading as a domain concept.** A business person
would never say "the agent-runtime context." They would say "the task execution" or "the
briefing engine." This is a red flag I will address below.

**Second warning sign:** "delivery" as a bounded context collapses *what is delivered*
(a briefing) with *how it is delivered* (Telegram, email). These are different business
concerns. The domain cares about the briefing; the channel is an implementation choice.

---

## Proposed Domain Decisions

### Bounded Contexts Identified

*I am listening for where the meaning of words changes. That is where context boundaries live.*

---

#### 1. Briefing Context

**Responsibility:** Owns the definition and creation of a morning briefing. Knows what a
briefing IS — its structure, its sections, its relevance scoring, its readiness. Does not
know where items come from (that is the Source context's job) and does not know how the
briefing reaches the user (that is the Notification context's job).

**Core Entities:**
- **Briefing** — the aggregate root. A briefing belongs to a Workspace, covers a time window,
  has a status (pending, compiling, ready, delivered, failed), and contains ordered Sections.
- **Section** — a named grouping of Items within a briefing (e.g., "What's new in your tech
  stack", "Emails needing response", "Calendar conflicts today").
- **Item** — a single piece of information surfaced in a section. Has a relevance score,
  a source reference, and a summary.
- **RelevanceScore** — a value object representing how strongly an item matches the user's
  stated priorities. This is NOT a raw number; it encodes the reasoning (which priority it
  matched, confidence level).

**Ubiquitous Language:**
- *Briefing* — the single daily artifact produced for a workspace. Not "report", not "digest",
  not "summary". Briefing. One per workspace per morning.
- *Compile* — the act of assembling a briefing from ingested material. Not "generate",
  not "run", not "execute". The business says "compile the briefing."
- *Section* — a named grouping. Not "category", not "block", not "topic cluster."
- *Item* — a single surfaced piece of information. Not "entry", not "result", not "finding."
- *Relevance* — the match between an item and the user's priorities. Not "score", not
  "ranking", not "confidence."

**Subdomain Type:** Core. This is the primary value creation mechanism. No competitor
solves "personalized relevance synthesis" well today.

---

#### 2. Source Context

**Responsibility:** Owns the relationship between a workspace and its external information
sources. Knows how to read from a source, knows when a source was last checked, and produces
raw material (Signals) that the Briefing context will evaluate. Does NOT know what a briefing
is. Does NOT score relevance. Does NOT make delivery decisions.

**Core Entities:**
- **Source** — the aggregate root. A configured connection to an external feed. Has a type
  (RSS, HN, Gmail, Calendar), connection credentials, fetch schedule, and health status.
- **Signal** — raw material ingested from a source. Has a timestamp, originating source,
  raw content, and a read/unread status. This is NOT an Item — a Signal has not yet been
  evaluated for relevance. Many Signals become zero Items; some become one Item.
- **SourceHealth** — a value object tracking fetch success rate, last-success time, error
  history. A source that consistently fails must be flagged to the workspace owner.

**Ubiquitous Language:**
- *Source* — the configured connection to an external feed. Not "integration", not "connector",
  not "plugin." When a user says "add my Gmail", they are adding a Source.
- *Signal* — raw, unevaluated information arriving from a source. Not "data", not "event",
  not "item" (item belongs to Briefing). The distinction between Signal and Item is the
  heart of the relevance filtering value proposition.
- *Ingest* — the act of fetching new material from a source. Not "sync", not "pull",
  not "fetch." "The system ingests signals from your sources."
- *Source health* — whether a source is reliably providing signals. Not "status", not
  "connectivity." Healthy/unhealthy is the only distinction that matters to the user.

**Subdomain Type:** Supporting. Critical to the product but not the core differentiator.
A healthy, well-built Source context is table stakes; the Briefing context is where the
competitive advantage lives.

**Anti-Corruption Layer required here.** Gmail, Google Calendar, Hacker News, and RSS feeds
speak different languages. The ACL translates external concepts into Signals. See Context Map
section below.

---

#### 3. Priority Context

**Responsibility:** Owns the user's declared and learned understanding of what matters.
Knows which topics, senders, projects, and keywords the user cares about. Provides this
understanding to the Briefing context when compiling. Does NOT compile briefings. Does NOT
interact with sources. Does NOT handle delivery.

*Why is this a separate context from Briefing?* Because "what the user cares about" changes
on a different timescale than "what the briefing contains today." Priorities are stable
over days and weeks. A briefing is created once and consumed once. Mixing them creates
the wrong aggregate boundary.

**Core Entities:**
- **PriorityProfile** — the aggregate root. Belongs to a workspace. Contains declared
  interests and learned signals.
- **DeclaredPriority** — something the user explicitly told the system they care about.
  A topic, a person, a project name, a company. Explicitly added or removed by the user.
- **LearnedSignal** — a pattern the system has inferred from user behavior. "You consistently
  open items from this sender." "You never engage with items tagged X." This is the
  behavioral moat the Board identified.
- **Engagement** — a record of whether the user acted on an item in a past briefing
  (opened, dismissed, marked important). Feeds the learning loop.

**Ubiquitous Language:**
- *Priority* — what the user cares about, in business terms. Not "preference", not
  "setting", not "config." When someone says "my priorities", they mean what matters
  to their work. This is the term the product uses.
- *Declared priority* — explicitly set by the user. Not "manual input", not "tagged
  keyword." "You've declared this a priority."
- *Learned signal* — inferred from behavior, not stated. Not "ML model output", not
  "implicit feedback." "The system has learned this matters to you."
- *Engage* — the user acts on a briefing item (reads, clicks, dismisses). Not "interact",
  not "feedback." Engagement is the behavioral data that drives learning.

**Subdomain Type:** Core. The learned priority model is the primary switching cost. This
is what makes the briefing personalized rather than generic.

---

#### 4. Workspace Context

**Responsibility:** Owns the relationship between a user account and the logical unit
of work (workspace). Manages the workspace lifecycle, its tier, its usage, and its members.
Enforces the usage caps the Board mandated (500 tasks/month for Solo, 2,000 for Pro).

*Why separate from auth/billing?* Because "workspace" is a business concept — the unit
around which briefings, sources, and priorities are organized. Auth (who you are) and
billing (what you pay) are generic subdomains. Conflating them with workspace pollutes
the business model with infrastructure concerns.

**Core Entities:**
- **Workspace** — the aggregate root. Has a name, an owner (user reference), a tier
  (Trial, Solo, Pro), and a usage ledger.
- **UsageLedger** — tracks task consumption within the current billing period. Enforces
  hard caps at the infrastructure level (Board mandate). Not a soft warning — a hard gate.
- **WorkspaceMember** — for future Pro multi-user; not in Phase 2 MVP scope but boundary
  must be clean to add later without restructuring.

**Ubiquitous Language:**
- *Workspace* — the container for one user's briefing setup. Not "account", not "project",
  not "team." One workspace per Solo user. Up to three per Pro user. The product always
  speaks of "your workspace."
- *Tier* — the subscription level (Trial, Solo, Pro). Not "plan", not "pricing",
  not "subscription." "Your workspace is on the Solo tier."
- *Task cap* — the monthly limit on briefing compilations and other tasks. Not "quota",
  not "limit", not "credits." "You've used 340 of your 500 monthly tasks."

**Subdomain Type:** Supporting. Essential but not differentiating.

---

#### 5. Notification Context

**Responsibility:** Owns how a completed briefing reaches the user. Knows about channels
(Telegram, email, web), handles channel configuration, tracks delivery status. Receives
a completed Briefing from the Briefing context and is responsible for getting it to the
right place in the right format. Does NOT know how a briefing was compiled. Does NOT make
content decisions.

*Why is delivery a separate context?* Because "what is in the briefing" and "how it is
sent" change for completely independent reasons. Adding a new delivery channel (WhatsApp,
Slack) requires no change to the Briefing context. Changing the briefing structure requires
no change to the Notification context. Language confirms this: a "channel" is meaningless
inside the Briefing context; a "section" is meaningless inside the Notification context.

**Core Entities:**
- **Channel** — the aggregate root. A configured delivery path for a workspace (Telegram
  bot, email address, web push). Has type, credentials, and confirmation status.
- **DeliveryAttempt** — a record of each attempt to deliver a briefing to a channel.
  Has status (pending, sent, failed), timestamp, and error details.
- **DeliveryFormat** — a value object describing how briefing content is rendered for
  a specific channel. Telegram has different constraints than email. The format adapter
  is inside this context.

**Ubiquitous Language:**
- *Channel* — how the briefing reaches the user. Not "integration", not "destination",
  not "endpoint." The user "adds a channel."
- *Deliver* — the act of transmitting a compiled briefing via a channel. Not "send",
  not "push", not "dispatch."
- *Delivery confirmation* — the user has acknowledged that a channel is correctly set up
  (e.g., they've connected their Telegram bot). Not "verified", not "activated."

**Subdomain Type:** Supporting. Important for user experience but not differentiating.

---

#### 6. Identity Context (Generic)

**Responsibility:** Owns authentication and user account lifecycle. Maps to Clerk's
external service. Owns user identity — email, name, OAuth providers. Does NOT own
workspaces (those live in Workspace context). Does NOT own billing (that is a separate
concern). The Identity context answers one question: "Who is this person?"

**Note on Clerk:** Clerk is an external service. The Identity context is the Anti-Corruption
Layer between Clerk's user model and the product's concept of a user. The product must
NOT depend directly on Clerk's SDK throughout the codebase — only through this context.

**Subdomain Type:** Generic. Use Clerk, wrap it, never expose Clerk concepts outside
this context.

---

#### 7. Billing Context (Generic)

**Responsibility:** Owns the commercial relationship between the product and a workspace.
Knows about Stripe subscriptions, trial periods, invoices, and payment status. Provides
the Workspace context with tier information via a published event (SubscriptionChanged).
Does NOT own usage caps (Workspace context enforces those). Does NOT own user identity.

**Ubiquitous Language:**
- *Trial* — a 14-day period of full access before payment is required. Not "free tier",
  not "freemium." A trial has an expiry.
- *Subscription* — the active commercial commitment (Solo or Pro). Not "plan", not
  "account type." A subscription is either active, paused, or cancelled.
- *Invoice* — a billing record. Not "charge", not "payment."

**Subdomain Type:** Generic. Stripe does this. Wrap it.

---

### Contexts NOT Created (and Why)

**"Agent-runtime" context (from architecture agenda) — REJECTED.**

This is a technical concept, not a business concept. The business does not have an
"agent-runtime." What it has is: briefings being compiled (Briefing context), tasks
consuming capacity (Workspace context), and signals being ingested (Source context).
"Agent-runtime" is an implementation detail of how the briefing is compiled, not a
domain boundary. Placing it as a bounded context would be a technical abstraction
leaking into the domain model.

**"Reliability measurement" context — NOT a separate context.**

Reliability measurement is a cross-cutting concern and an operational concern. It is
not a domain concept the business talks about. It is an invariant enforced through
Briefing aggregate rules (a Briefing must complete within a time window; failure is
recorded as a domain event) and observed via operations tooling.

---

### Context Map

```
External World
   │
   ├── Gmail API ──────────[ACL: GmailAdapter]──────────┐
   ├── Google Calendar API ─[ACL: CalendarAdapter]───────┤
   ├── Hacker News API ────[ACL: HNAdapter]───────────── ► Source Context
   ├── RSS Feeds ──────────[ACL: RSSAdapter]─────────────┘
   │
   └── Clerk ──────────────[ACL: ClerkAdapter]──────────► Identity Context
   └── Stripe ─────────────[ACL: StripeAdapter]─────────► Billing Context


Domain Contexts:

[Identity Context] ──[OHS/Published Language]──► [Workspace Context]
      │                (UserRegistered event)
      │
[Billing Context] ──[Customer-Supplier]──────────► [Workspace Context]
      │               (SubscriptionChanged event)
      │
[Workspace Context] ──[Customer-Supplier]────────► [Briefing Context]
      │                (WorkspaceReady, UsageCap)
      │
[Workspace Context] ──[Customer-Supplier]────────► [Source Context]
      │                (WorkspaceReady)
      │
[Workspace Context] ──[Customer-Supplier]────────► [Priority Context]
                       (WorkspaceReady)

[Source Context] ──────[Domain Event]────────────► [Briefing Context]
                        (SignalIngested)

[Priority Context] ────[Customer-Supplier]────────► [Briefing Context]
                        (PriorityProfile query)

[Briefing Context] ────[Domain Event]─────────────► [Priority Context]
                        (BriefingEngaged — behavioral feedback)

[Briefing Context] ────[Domain Event]─────────────► [Notification Context]
                        (BriefingReady)

[Briefing Context] ────[Domain Event]─────────────► [Workspace Context]
                        (BriefingCompiled — task consumption)

[Notification Context] ─[Domain Event]────────────► [Briefing Context]
                         (DeliveryConfirmed / DeliveryFailed)
```

**Relationships:**

| From | To | Pattern | Why |
|------|----|---------|-----|
| Gmail/Calendar/HN/RSS → Source | Anti-Corruption Layer | External services speak foreign languages. ACL translates their models to Signals. Without this, Gmail's threading model would pollute the briefing domain. |
| Clerk → Identity | Anti-Corruption Layer | Clerk's user model is not the product's user model. ACL prevents vendor lock-in from propagating inward. |
| Stripe → Billing | Anti-Corruption Layer | Stripe's subscription model is richer than needed. ACL exposes only Trial/Solo/Pro to the rest of the system. |
| Identity → Workspace | Open Host Service / Published Language | Workspace subscribes to UserRegistered events. Identity does not know about workspaces — it publishes standard events. |
| Billing → Workspace | Customer-Supplier | Billing (upstream) publishes SubscriptionChanged. Workspace (downstream) reacts by updating tier. Billing does not know about workspaces. |
| Workspace → Briefing/Source/Priority | Customer-Supplier | Workspace is upstream authority on whether a workspace is active and within caps. Downstream contexts must check before acting. |
| Source → Briefing | Published Language (domain events) | Source publishes SignalIngested events. Briefing subscribes. Source does not know briefings exist. |
| Briefing → Priority | Customer-Supplier | Briefing queries PriorityProfile during compilation. Priority is upstream and owns the profile. |
| Briefing → Notification | Published Language (domain events) | Briefing publishes BriefingReady. Notification subscribes. Briefing does not know about channels. |
| Briefing → Priority (feedback) | Published Language (domain events) | BriefingEngaged events flow back to Priority to update learned signals. |

---

### Domain Events

| Event | Source Context | Triggered By | Consumed By |
|-------|---------------|--------------|-------------|
| UserRegistered | Identity | User completes signup via Clerk | Workspace (create initial workspace) |
| SubscriptionChanged | Billing | Stripe webhook: trial → paid, upgrade, cancellation | Workspace (update tier) |
| WorkspaceCreated | Workspace | Identity publishes UserRegistered | Briefing, Source, Priority (initialize contexts) |
| SignalIngested | Source | Scheduled fetch from external source completes | Briefing (queue compilation if enough signals) |
| SourceHealthDegraded | Source | Consecutive fetch failures exceed threshold | Notification (alert user their source is broken) |
| BriefingCompilationRequested | Briefing | Scheduled cron or manual trigger | Briefing internally (start compilation pipeline) |
| BriefingReady | Briefing | Compilation pipeline completes successfully | Notification (deliver), Workspace (record task usage) |
| BriefingFailed | Briefing | Compilation pipeline fails | Notification (alert user), Workspace (still record task attempt) |
| DeliveryConfirmed | Notification | Channel confirms receipt | Briefing (update status to delivered) |
| DeliveryFailed | Notification | Channel delivery attempt fails | Briefing (update status), alert operations |
| BriefingEngaged | Briefing | User clicks/opens/dismisses an item in the briefing | Priority (update learned signals) |
| TaskCapReached | Workspace | UsageLedger hits monthly limit | Briefing (block further compilations), Notification (alert user) |
| PriorityUpdated | Priority | User adds/removes a declared priority | Briefing (next compilation uses new profile) |

---

### Aggregate Design

#### Briefing Context Aggregates

**Briefing (Aggregate Root)**
- Entities: Section (ordered list), Item (within section)
- Value Objects: RelevanceScore, BriefingStatus (pending/compiling/ready/delivered/failed), TimeWindow (the morning period covered)
- Invariants:
  - A Briefing must have at least one Section to be marked Ready
  - A Briefing can only transition from compiling→ready or compiling→failed (not backward)
  - A Briefing's TimeWindow cannot overlap with another Briefing for the same workspace
  - Total items across all sections must not exceed 50 (prevents information overload — business rule)
- Boundary Reason: All these elements must be consistent together. You cannot have a "ready" briefing with zero sections. You cannot add items to a delivered briefing. The status machine and the content are one unit of consistency.

---

#### Source Context Aggregates

**Source (Aggregate Root)**
- Entities: (none — source is the root)
- Value Objects: SourceType (RSS/Gmail/Calendar/HN), FetchSchedule, SourceHealth, SourceCredential (encrypted reference, not the actual credential)
- Invariants:
  - A Source must have valid credentials before it can be set to active
  - A Source in error state for >72 hours must transition to degraded status
  - SourceCredential stores only a reference to the credential vault, never the raw token
- Boundary Reason: Source configuration and its health history must be consistent. If credentials change, all state about the source's reliability resets.

**Signal (Aggregate Root)**
- Entities: (none — signal is atomic)
- Value Objects: SignalContent (raw text/metadata), SignalTimestamp, SourceReference (reference to Source, not composition)
- Invariants:
  - A Signal is immutable once created (it is a record of what was ingested at a point in time)
  - A Signal belongs to exactly one Source
  - Signals older than 48 hours are eligible for garbage collection (business rule: morning briefings only care about recent information)
- Boundary Reason: Signals are facts about what was ingested. They are separate aggregates from Source because their lifecycle is independent — a Source persists; Signals are transient.

---

#### Priority Context Aggregates

**PriorityProfile (Aggregate Root)**
- Entities: DeclaredPriority (list), LearnedSignal (list)
- Value Objects: TopicKeyword, PersonIdentifier, ProjectReference, EngagementWeight
- Invariants:
  - A PriorityProfile belongs to exactly one Workspace
  - Declared priorities take precedence over learned signals when scoring (explicit > implicit)
  - A LearnedSignal requires a minimum of 5 engagement data points before it influences scoring
  - Maximum 50 declared priorities per profile (prevents degraded relevance scoring)
- Boundary Reason: All elements of what the user cares about must be consistent together. Adding a declared priority immediately affects all future briefings — it is a single atomic decision.

---

#### Workspace Context Aggregates

**Workspace (Aggregate Root)**
- Entities: UsageLedger
- Value Objects: WorkspaceTier (Trial/Solo/Pro), TaskCap, UsagePeriod
- Invariants:
  - A workspace on Trial tier expires after 14 days with no conversion
  - TaskCap is enforced BEFORE a briefing compilation is permitted (hard gate, not soft warning)
  - A workspace can only downgrade tiers at the end of a billing period
  - A workspace in expired-trial state cannot compile new briefings
- Boundary Reason: Workspace tier and usage ledger must be consistent. The cap enforcement cannot be split — checking and decrementing the ledger must be an atomic operation to prevent race conditions at scale.

---

## Phase 1 Toolkit Boundary Analysis

*The critical question: does Phase 1 (DLD patterns toolkit) share code with Phase 2 (product)?*

**My answer: No. They are Separate Ways.**

The "Separate Ways" context mapping pattern applies here. These are not two versions of
the same product — they are two completely different things that happen to be built by
the same team.

Phase 1 toolkit is: documentation, ADRs (ADR-007 through ADR-010), runnable examples,
and possibly an npm package of DLD orchestration utilities (background fan-out helpers,
caller-writes pattern, file-gate utilities). Its consumers are **developer teams** who
will integrate these patterns into their own systems.

Phase 2 product is: a hosted service with a Briefing domain, Source domain, Priority
domain, etc. Its consumer is **a solo founder** who wants a morning briefing.

**What they share:** The DLD ADR patterns are implemented *in* Phase 2's backend
(background fan-out for briefing compilation, caller-writes for subagent results, etc.),
but Phase 2 does NOT import from Phase 1. Phase 1 documents the patterns; Phase 2 applies
them. The relationship is intellectual, not a code dependency.

**If Phase 1 ships an npm package** (e.g., `@dld/orchestration`), Phase 2 could use it as
a dependency — but only for infrastructure utilities (queue management, context tracking),
never for domain logic. Infrastructure helpers, not domain knowledge.

**The risk of sharing code:** If Phase 1 patterns evolve to satisfy consulting clients
and Phase 2 imports them as a dependency, the product is now coupled to consulting
deliverables. A client-requested change to the toolkit breaks the product. Keep them
Separate Ways.

---

## Cross-Cutting Implications

### For Data Architecture

- Each bounded context owns its data. Briefing context owns briefing tables. Source context
  owns source and signal tables. Priority context owns priority profile tables. No cross-context
  joins in the database — contexts communicate via domain events, not shared tables.
- The single SQLite/Turso file can host all contexts in separate schemas. The separation
  is logical (naming convention: `briefing_*`, `source_*`, `priority_*`, `workspace_*`,
  `notification_*`) even if physical storage is shared for Phase 2 simplicity.
- **Signal garbage collection** must be designed in from day one. Signals older than 48
  hours are semantically expired. If this is not built, the signal table becomes the largest
  table in the system within a month.
- **Behavioral memory** (LearnedSignals in Priority context) is the data that must be
  durable and portable. This is the moat the Board identified. Schema must be designed for
  export (user data portability) and import (migration path). A JSON blob of "preferences"
  is not sufficient — it must be structured enough to be queryable and evolvable.

### For API Design

- Each bounded context maps to one API module (not necessarily one endpoint). The API
  layer is an adapter, not a domain.
- Workspace context is the entry point for almost all operations: "workspace/{id}/briefings",
  "workspace/{id}/sources", "workspace/{id}/priorities". This enforces the workspace
  isolation requirement from the Board.
- The Source context's ACL for external APIs (Gmail, Calendar, HN) is NOT exposed in
  the product API. Users never see "Gmail adapter" — they see "add a source" and choose Gmail.
  The adapter type is an implementation detail hidden behind the Source context boundary.
- Published Language for the Briefing context: the briefing output format must be defined
  as a stable contract that both the Notification context (formatting for channels) and
  any future export/API consumers can rely on. Define this schema early.

### For Agent Architecture

- The LLM-based compilation step lives **inside** the Briefing context. It is not a
  separate "agent-runtime" context. The briefing compilation uses LLMs as an implementation
  tool for relevance scoring and synthesis — this is an infrastructure concern within the
  Briefing context, not a domain boundary.
- The Priority context's learned signal model may use an LLM for inference but the
  LLM call is an infrastructure adapter, not a domain concept. The domain concept is
  "EngagementWeight", not "embedding" or "cosine similarity."
- Source context adapters (Gmail, Calendar, etc.) call external APIs — these are
  infrastructure adapters behind the ACL. The LLM may be used here to extract structured
  Signals from unstructured email content, but again this is the ACL's job, not a
  separate context.

### For Operations

- Deployment boundaries: all contexts can deploy as one service in Phase 2 (monolith-first).
  The value of the bounded context design is not microservices today — it is the clean
  seams that allow extracting a context into its own service later if needed. The Source
  context is the most likely candidate for extraction (independent scaling of ingestion).
- Monitoring per context: Briefing context needs a scheduled job that verifies compilations
  complete within the SLO window (6am ± 30 min). Source context needs health monitoring
  per source type (a single broken Gmail OAuth token must not fail the whole ingestion
  pipeline). These are separate observability concerns with separate alert routing.
- The Workspace context's task cap is an infrastructure-level hard gate (Board mandate).
  This means the cap check must happen in middleware, before reaching the Briefing context
  domain logic. The Workspace context publishes `TaskCapReached` events; middleware listens.

---

## Concerns & Recommendations

### Critical Issues

**Issue 1: "Agent-runtime" as a bounded context (from architecture agenda)**
The agenda proposes "agent-runtime" as a domain context. This is a technical term, not a
business concept. It will pollute the domain model with infrastructure concerns.
- **Fix:** Remove "agent-runtime" as a bounded context. LLM execution is an infrastructure
  adapter inside the Briefing context (for compilation) and Source context (for signal
  extraction). Name the business concept, not the technology.
- **Rationale:** DDD rule: if a business person would not recognize the term in a business
  conversation, it does not belong as a bounded context.

**Issue 2: Signal lifecycle not modeled in architecture agenda**
The agenda implies sources produce items that go directly into briefings. The Signal
intermediate concept (raw, unevaluated ingested material) is missing.
- **Fix:** Explicitly model the Signal as a separate entity from Item. Signal = raw material
  from source. Item = evaluated, relevant material in a briefing. The transformation between
  them is the core value proposition (relevance filtering).
- **Rationale:** Without this distinction, the Source context and Briefing context are
  implicitly coupled — Source has to know about Items (a Briefing concept), which crosses
  the boundary.

**Issue 3: Behavioral memory schema must be explicit at design time**
The Board identified learned priorities as the primary switching cost and moat. The
architecture agenda acknowledges this but leaves it open. Designing it as "a JSON file
of preferences" later will create a migration nightmare.
- **Fix:** Design the PriorityProfile aggregate schema as a first-class design artifact
  now. Three tables: declared_priorities, learned_signals, engagements. Define the
  fields needed for the learning loop at design time.
- **Rationale:** This is the hardest-to-reverse data model decision in the system.
  Everything else (hosting, model routing, auth) can be swapped. The behavioral memory
  schema, once users have accumulated 90 days of data, is load-bearing.

### Important Considerations

**Consideration 1: "Delivery" context naming**
The architecture agenda uses "delivery" as a bounded context. This is acceptable but slightly
ambiguous — "delivery" could mean the logistics of getting a briefing to a user, or it could
mean the product delivery concept (what was delivered). Use "Notification" to clarify:
this context handles notification of the user about a ready briefing, via a chosen channel.
- **Recommendation:** Rename "delivery" to "notification" in the ubiquitous language.
  Aligns with how users think ("I got a notification that my briefing is ready").

**Consideration 2: Phase 1 toolkit and Phase 2 code sharing**
The architecture agenda is silent on this. The risk is that the team, under time pressure,
will share a utility library between Phase 1 and Phase 2 that accidentally couples them.
- **Recommendation:** Establish a clear rule at project start: Phase 1 toolkit is a
  separate repository with its own release cycle. Phase 2 product may use Phase 1's
  npm package as a dependency, but only for infrastructure utilities. If that package
  changes, Phase 2 must explicitly update and test the dependency. No implicit coupling.

**Consideration 3: Domain event bus vs. direct method calls**
For Phase 2 with a 2-person team and a monolith-first deployment, synchronous domain
events (in-process pub/sub or simple function calls) are appropriate. Do not build a
message broker for Phase 2 MVP. The event vocabulary defined above is for conceptual
clarity — implement as simple TypeScript EventEmitter or direct calls in Phase 2.
The seams exist so you can make them async later.
- **Recommendation:** Mark each domain event in the code with a comment: "// Domain Event:
  BriefingReady — see domain map for consumers." This makes the seams visible without
  the overhead of a message broker.

### Questions for Clarification

1. **When a user has multiple workspaces (Pro tier), do priorities carry across workspaces
   or are they per-workspace?** The language matters: if "workspace" is the unit of
   personalization, priorities are per-workspace. If "user" is the unit, priorities
   are shared. The Board said "3 workspaces for Pro" — suggesting different contexts
   of use. I would expect per-workspace priorities, but this needs business confirmation.

2. **What does the user see when a source is unhealthy?** Is the briefing compiled
   without that source (partial briefing), or is compilation blocked until all sources
   are healthy? The business answer here defines whether SourceHealth is an invariant
   of Briefing compilation or a notification-only concern.

3. **What is the business meaning of "task" in the usage cap?** The Board says "500 tasks
   per workspace per month." Is one briefing compilation one task? Or does each source
   ingestion count as a task? The UsageLedger invariant depends on this definition.
   Currently I've modeled each briefing compilation as one task — verify with business.

4. **Does "engage" mean the user read the briefing, or specifically interacted with an
   item?** For the learning loop in Priority context, the granularity of engagement data
   determines the quality of learned signals. "Opened the briefing" is too coarse to
   learn from. "Clicked this specific item" is actionable. This is a product decision
   that affects the domain model.

---

## Final Assessment: Domain Model Health

The business description passes the kill question. The domain is describable in pure
business language. The seven bounded contexts I've identified map cleanly to distinct
language communities within the business: briefing compilers, source managers, priority
setters, workspace administrators, notification deliverers, identity managers, billing
managers. Each context has words that are meaningless in other contexts (Signal is
meaningless in Briefing before it becomes an Item; Channel is meaningless in Briefing;
RelevanceScore is meaningless in Source).

The core insight: the transformation from Signal to Item — raw ingested material becoming
a relevant briefing item — is the entire value proposition of the product. This transformation
lives in the Briefing context and uses the Priority context's profile as the lens. This
is the one place where the team must invest in getting the domain model right. Everything
else (auth, billing, notifications, source adapters) is supporting infrastructure.

---

## References

- [Eric Evans — Domain-Driven Design](https://www.domainlanguage.com/ddd/) — core patterns
- [Eric Evans — DDD Reference](https://www.domainlanguage.com/ddd/reference/) — context mapping patterns catalog
- [Martin Fowler — BoundedContext](https://martinfowler.com/bliki/BoundedContext.html) — linguistic boundary definition
- [Martin Fowler — ContextMap](https://martinfowler.com/bliki/ContextMap.html) — relationship patterns
- [Vaughn Vernon — Implementing Domain-Driven Design](https://vaughnvernon.com/?page_id=168) — aggregate design
- [DDD Crew — Context Mapping](https://github.com/ddd-crew/context-mapping) — pattern catalog with visual notation
- [Alberto Brandolini — Event Storming](https://www.eventstorming.com/) — domain event discovery
- Business Blueprint: `/Users/desperado/dev/dld/ai/blueprint/business-blueprint.md`
- Architecture Agenda: `/Users/desperado/dev/dld/ai/architect/architecture-agenda.md`
