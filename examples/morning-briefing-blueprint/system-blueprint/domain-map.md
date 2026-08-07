# Domain Map: Morning Briefing Agent

**Architecture:** Alternative B — Domain-Pure (7 bounded contexts)
**Date:** 2026-02-28
**Source:** Architect Board synthesis (`ai/architect/architectures.md`)

---

## Philosophy

Name every concept correctly from day 1. Linguistic clarity prevents coupling. 7 bounded contexts as separate code modules within a monolith. Contexts communicate via typed domain events (in-process EventEmitter3), not direct imports.

---

## Bounded Contexts

### 1. Briefing Context (Core)

**Module:** `src/domains/briefing/`
**Responsibility:** Compilation, synthesis, quality measurement. Owns the definition of what a briefing IS — structure, sections, relevance scoring, readiness state machine.

**Core Entities:**
| Entity | Type | Description |
|--------|------|-------------|
| Briefing | Aggregate Root | Daily artifact for a workspace. Status machine: scheduled -> fetching_sources -> synthesizing -> delivering -> delivered/failed |
| Section | Entity | Named grouping within briefing (tech_news, email_triage, calendar, projects) |
| Item | Entity | Single surfaced piece of information. Has RelevanceScore, source reference, summary |
| RelevanceScore | Value Object | How strongly item matches user priorities. Encodes reasoning, not just a number |
| BriefingStatus | Value Object | Enum: scheduled, fetching_sources, synthesizing, delivering, delivered, failed, cancelled |
| TimeWindow | Value Object | The morning period this briefing covers |

**Invariants:**
- A Briefing must have >= 1 Section to be marked Ready
- Status transitions are forward-only (compiling -> ready/failed, never backward)
- No overlapping TimeWindows for same workspace
- Total items across all sections <= 50 (business rule: prevent information overload)
- Delivered briefing's content_json is IMMUTABLE

**Subdomain Type:** Core — primary value creation mechanism

---

### 2. Source Context (Supporting)

**Module:** `src/domains/source/`
**Responsibility:** Ingestion from external feeds. Knows how to read, tracks health, produces raw Signals. Does NOT score relevance. Does NOT know what a briefing is.

**Core Entities:**
| Entity | Type | Description |
|--------|------|-------------|
| Source | Aggregate Root | Configured connection to external feed (RSS, HN, Gmail, Calendar) |
| Signal | Aggregate Root | Raw ingested material. Immutable once created. NOT an Item — unevaluated |
| SourceHealth | Value Object | Fetch success rate, last-success time, error history |
| SourceCredential | Value Object | Reference to credential vault (never raw token) |

**Invariants:**
- Source must have valid credentials before activation
- Source in error state > 72 hours -> degraded status
- Signal is immutable once created
- Signals older than 48 hours eligible for GC

**ACL Adapters (Anti-Corruption Layer):**
- `GmailAdapter` — translates Gmail API to Signals
- `CalendarAdapter` — translates Google Calendar API to Signals
- `HNAdapter` — translates Hacker News API to Signals
- `RSSAdapter` — translates RSS feeds to Signals

**Subdomain Type:** Supporting — critical but not differentiating

---

### 3. Priority Context (Core)

**Module:** `src/domains/priority/`
**Responsibility:** Declared + learned preferences. Provides PriorityProfile to Briefing context during compilation. The behavioral memory moat.

**Core Entities:**
| Entity | Type | Description |
|--------|------|-------------|
| PriorityProfile | Aggregate Root | Per-workspace. Contains declared + learned signals |
| DeclaredPriority | Entity | Explicit user-set interest (topic, person, project) |
| LearnedSignal | Entity | System-inferred pattern from behavior |
| Engagement | Value Object | Record of user action on briefing item |

**Invariants:**
- One PriorityProfile per Workspace
- Declared priorities take precedence over learned signals (explicit > implicit)
- LearnedSignal requires min 5 engagement data points before influencing scoring
- Maximum 50 declared priorities per profile

**Subdomain Type:** Core — switching cost mechanism, behavioral moat

---

### 4. Workspace Context (Supporting)

**Module:** `src/domains/workspace/`
**Responsibility:** Workspace lifecycle, tier enforcement, usage caps. The container for one user's briefing setup.

**Core Entities:**
| Entity | Type | Description |
|--------|------|-------------|
| Workspace | Aggregate Root | Has name, owner, tier (Trial/Solo/Pro), usage ledger |
| UsageLedger | Entity | Append-only task consumption tracking |
| TaskCap | Value Object | Monthly limit per tier (50 trial / 500 solo / 2000 pro) |
| UsagePeriod | Value Object | Billing period (YYYY-MM) |

**Invariants:**
- Trial expires after 14 days with no conversion
- TaskCap enforced BEFORE briefing compilation (hard gate, not soft warning)
- Cap check + usage increment is atomic (BEGIN IMMEDIATE)
- Downgrade only at end of billing period

**Subdomain Type:** Supporting — essential but not differentiating

---

### 5. Notification Context (Supporting)

**Module:** `src/domains/notification/`
**Responsibility:** How a completed briefing reaches the user. Channel management, delivery tracking, format adaptation.

**Core Entities:**
| Entity | Type | Description |
|--------|------|-------------|
| Channel | Aggregate Root | Configured delivery path (Telegram, email, web push) |
| DeliveryAttempt | Entity | Record of each delivery attempt with status |
| DeliveryFormat | Value Object | How briefing content renders for specific channel |

**Ubiquitous Language:**
- *Channel* — not "integration", not "destination"
- *Deliver* — not "send", not "push"
- *Delivery confirmation* — channel correctly set up and verified

**Subdomain Type:** Supporting

---

### 6. Identity Context (Generic)

**Module:** `src/domains/identity/`
**Responsibility:** Authentication and user lifecycle. ACL wrapper around Clerk. Answers: "Who is this person?"

**Key Rule:** Clerk SDK imported ONLY in this context. Never exposed outside. Product does NOT depend on Clerk's user model — only on this context's published interface.

**Subdomain Type:** Generic — use Clerk, wrap it, never expose Clerk concepts

---

### 7. Billing Context (Generic)

**Module:** `src/domains/billing/`
**Responsibility:** Commercial relationship. Stripe subscriptions, trial periods, invoices, payment status.

**Core Entities:**
| Entity | Type | Description |
|--------|------|-------------|
| Subscription | Entity | Active commercial commitment (Solo/Pro) |
| BillingCache | Entity | Read-through cache from Stripe webhooks |

**Ubiquitous Language:**
- *Trial* — 14-day full access, not "free tier"
- *Subscription* — active/paused/cancelled, not "plan"

**Subdomain Type:** Generic — Stripe does this, wrap it

---

## Contexts NOT Created

| Rejected Context | Why |
|-----------------|-----|
| Agent-runtime | Technical term, not business concept. LLM execution is infrastructure inside Briefing context |
| Reliability measurement | Cross-cutting operational concern, not a domain boundary |

---

## Ubiquitous Language (enforced in code)

| Term | Context | NOT called |
|------|---------|-----------|
| Briefing | Briefing | report, digest, summary |
| Compile | Briefing | generate, run, execute |
| Section | Briefing | category, block, topic cluster |
| Item | Briefing | result, finding, entry |
| Signal | Source | data, event, item |
| Ingest | Source | sync, pull, fetch |
| Source | Source | integration, connector, plugin |
| Priority | Priority | preference, setting, config |
| Engage | Priority | interact, feedback |
| Workspace | Workspace | account, project, team |
| Tier | Workspace | plan, pricing, subscription |
| Task cap | Workspace | quota, limit, credits |
| Channel | Notification | integration, destination |
| Deliver | Notification | send, push, dispatch |

---

## Context Map

```
External World
   |
   +-- Gmail API --------[ACL: GmailAdapter]--------+
   +-- Calendar API -----[ACL: CalendarAdapter]------+ --> Source Context
   +-- HN API -----------[ACL: HNAdapter]-----------+
   +-- RSS Feeds --------[ACL: RSSAdapter]----------+
   |
   +-- Clerk ------------[ACL: ClerkAdapter]---------> Identity Context
   +-- Stripe -----------[ACL: StripeAdapter]--------> Billing Context

Identity --[UserRegistered]--> Workspace
Billing --[SubscriptionChanged]--> Workspace
Workspace --[WorkspaceReady]--> Briefing, Source, Priority
Source --[SignalIngested]--> Briefing
Priority --[PriorityProfile query]--> Briefing
Briefing --[BriefingReady]--> Notification
Briefing --[BriefingEngaged]--> Priority (feedback loop)
Briefing --[BriefingCompiled]--> Workspace (task consumption)
```

**Relationship Patterns:**

| From | To | Pattern | Why |
|------|----|---------|-----|
| Gmail/Calendar/HN/RSS -> Source | Anti-Corruption Layer | External services speak foreign languages |
| Clerk -> Identity | Anti-Corruption Layer | Vendor lock-in prevention |
| Stripe -> Billing | Anti-Corruption Layer | Expose only Trial/Solo/Pro |
| Identity -> Workspace | Open Host Service | UserRegistered event |
| Billing -> Workspace | Customer-Supplier | SubscriptionChanged event |
| Workspace -> Briefing/Source/Priority | Customer-Supplier | Upstream authority on workspace status |
| Source -> Briefing | Published Language | SignalIngested events |
| Briefing -> Priority | Customer-Supplier | PriorityProfile query |
| Briefing -> Notification | Published Language | BriefingReady event |
| Briefing -> Priority (feedback) | Published Language | BriefingEngaged event |

---

## Domain Events

| Event | Source Context | Triggered By | Consumed By |
|-------|---------------|--------------|-------------|
| UserRegistered | Identity | Clerk signup | Workspace (create initial) |
| SubscriptionChanged | Billing | Stripe webhook | Workspace (update tier) |
| WorkspaceCreated | Workspace | UserRegistered | Briefing, Source, Priority |
| SignalIngested | Source | Scheduled fetch | Briefing (queue compilation) |
| SourceHealthDegraded | Source | Consecutive failures | Notification (alert user) |
| BriefingCompilationRequested | Briefing | BullMQ cron | Briefing (internal) |
| BriefingReady | Briefing | Compilation success | Notification (deliver), Workspace (record usage) |
| BriefingFailed | Briefing | Compilation failure | Notification (alert), Workspace (still record) |
| DeliveryConfirmed | Notification | Channel confirms | Briefing (status: delivered) |
| DeliveryFailed | Notification | Channel failure | Briefing (update status) |
| BriefingEngaged | Briefing | User clicks/opens/dismisses | Priority (update learned signals) |
| TaskCapReached | Workspace | Usage limit hit | Briefing (block), Notification (alert) |
| PriorityUpdated | Priority | User adds/removes priority | Briefing (next compilation) |

**Implementation:** EventEmitter3 (typed) in-process pub/sub. Zero infrastructure. Domain events are conceptual boundaries, not message broker queues. Seams exist for future extraction.

---

## Context Boundary Enforcement

```bash
# No cross-context imports (fitness function, pre-commit)
grep -rn "from.*domains/briefing" src/domains/source/ && exit 1
grep -rn "from.*domains/source" src/domains/briefing/ && exit 1
grep -rn "from.*domains/priority" src/domains/source/ && exit 1
# ... repeat for all context pairs

# Domain events are the ONLY cross-context communication
# Direct function calls within a context are fine
# Cross-context = via event bus or explicit interface
```

---

## Core Value Proposition

**Signal -> Item transformation.** Sources produce Signals (raw, unevaluated). Briefing context uses Priority context's profile as a lens to convert Signals into Items (evaluated, ranked, relevant). This transformation is the entire product.

- Signal lives in Source context
- Item lives in Briefing context
- The lens (PriorityProfile) lives in Priority context
- Three contexts collaborate to produce the one thing the user pays for
