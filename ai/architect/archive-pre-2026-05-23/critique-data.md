# Data Architecture Cross-Critique

**Persona:** Martin (Data Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-02-27

---

## My Phase 1 Position (Reference)

My core positions from the Phase 1 research:

1. **System of Record must be explicit for every entity.** Clerk owns identity, Stripe owns billing truth, our DB owns everything else. Ambiguity here = data integrity bugs in production.
2. **Explicit preferences and behavioral memory are SEPARATE tables with SEPARATE write paths.** Conflating them is a dual-SoR problem that corrupts both.
3. **Usage metering must be an append-only ledger, not a mutable counter.** Lost-update under concurrent writes is a silent revenue leak.
4. **Briefing content must be structured JSON, not freeform text.** Deterministic reliability measurement is impossible without it.
5. **SQLite WAL write serialization is not the bottleneck at <500 users.** The concern is valid at scale, but not at launch.
6. **The `billing_cache` / Stripe staleness window is a real issue** requiring a synchronous fallback on 429.
7. **OAuth tokens need atomic refresh logic.** Race between two concurrent tasks both seeing an expired token is a predictable failure at scale.

---

## Peer Analysis Reviews

---

### Analysis A — DX Architect (Dan McKinley persona)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

Analysis A correctly identifies that Turso at launch solves no problem. The data argument is the same as mine: at <500 users, a SQLite WAL file on a persistent volume is local disk I/O (microseconds), zero network dependencies, zero third-party failure modes. Turso's value proposition is edge replication for geographically distributed reads — a problem that does not exist until you have users in multiple regions.

The LangGraph rejection is also correct from a data lineage perspective: LangGraph's checkpointing infrastructure introduces a second write path for briefing state (its checkpoint store), creating a potential conflict with the `briefings` table as the SoR for briefing lifecycle. If LangGraph checkpoints say "step 3 complete" but the `briefings` table says "status=fetching_sources," you have two SoRs disagreeing. A simple async pipeline has one state store: the `briefings` table. Cleaner.

The counter-proposal of a monolith with `users`, `source_configs`, `briefings` tables captures the essential data model. However, Analysis A understates the importance of the usage ledger (append-only vs mutable counter) and the explicit preferences vs behavioral memory separation. The counter-proposal uses a `preferences JSON` column — this is exactly the design that collapses two distinct SoRs into one blob. When the system writes a behavioral signal AND the user edits a preference, which write wins? A JSON blob has no answer.

**Missed gaps:**

- The `preferences JSONB` column as a single blob conflates user-owned explicit prefs with system-derived behavioral signals. This looks simple at day 1 and becomes a consistency nightmare at month 6 when the learning loop starts updating the same column the user is editing.
- No analysis of the `billing_cache` staleness window — the Clerk-Stripe sync failure SPOF identified is real, but the data solution (Stripe as authoritative SoR with local cache + synchronous fallback on cap exceeded) is not addressed.
- No discussion of the usage cap enforcement data pattern (append-only ledger vs mutable counter). The SPOF analysis correctly identifies the problem; the data solution is absent.

**Rank: Moderate**

---

### Analysis B — Domain Modeler (Eric Evans persona)

**Agreement:** Agree

**Reasoning from data perspective:**

Analysis B is the strongest complement to my data architecture work. The distinction between `Signal` (raw ingested material) and `Item` (evaluated, relevant content in a briefing) is critical and maps directly to my `briefing_sources` table design — each row in `briefing_sources` captures `items_fetched` vs `items_used`, encoding exactly the Signal-to-Item transformation. The domain model validates the data model.

The Priority Context's aggregate design — `DeclaredPriority` and `LearnedSignal` as separate entities within `PriorityProfile` — directly confirms my architectural decision to use separate tables (`preferences` for declared, `memory_signals` for learned). This is the domain model telling us the schema must be this way. When the domain model and the data model agree on entity separation, that is strong evidence the design is correct.

The `BriefingEngaged` domain event (user clicks → Priority context updates learned signals) maps cleanly to my `briefing_feedback` table (raw event log) → `memory_signals` UPSERT (derived state). The DDIA Chapter 11 "derived data" framing I used is validated by the domain event architecture.

The concern about Signal garbage collection ("Signals older than 48 hours are eligible for garbage collection") is one I did not address explicitly and is important. My `briefing_sources` table stores lineage but not the raw signals themselves — if the system fetches 127 raw items to produce 18 briefing items, where do those 127 items live? My schema stores the per-source aggregate counts (`items_fetched`, `items_used`) but not the individual signal records. For analytics and quality debugging, those raw items may be valuable for a short retention window.

**Missed gaps:**

- No explicit analysis of table ownership and FK constraints across context boundaries. The domain says "Source context never knows about briefings" — but in a single SQLite DB, a FK from `briefing_sources.source_config_id` to `source_configs.id` crosses context boundaries at the DB layer. This is a tension between DDD purity and practical schema design for a 2-person team monolith. The resolution is: in a monolith, cross-context FKs are acceptable; the boundary is enforced in application code, not DB constraints.
- The `WorkspaceMember` entity placeholder (for future Pro multi-user) is noted but the schema implication is not analyzed: the `workspaces` table will need a `workspace_members` join table when Pro tier enables team access. This migration path should be designed now even if not built.

**Rank: Strong**

---

### Analysis D — Evolutionary Architect (Neal Ford persona)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

Analysis D's fitness function for schema migration safety is exactly right: apply migration to test DB, run tests, roll back, run tests again. Both passes must succeed. This is the "expand-contract" approach I described as the migration strategy, operationalized as a CI gate.

The identification of behavioral memory schema as "the only Phase 2 architectural decision that cannot be deferred past day 1 of building" aligns with my position. Analysis D frames it in terms of irreversibility (correct) but does not specify WHAT the schema should be, only that it must be append-only events. My Phase 1 research provides the specifics: `briefing_feedback` (raw event log) + `memory_signals` (materialized running average) is the pattern. Analysis D says "PreferenceEvent schema" — this is a slightly different framing. Event sourcing for preferences gives you full replayability but adds query complexity (you must always project state from events). My design uses a hybrid: raw events (log) + materialized current state (memory_signals). This is a deliberate trade-off: full replayability (via log) with O(1) read performance (via materialized table).

The change vector analysis correctly identifies behavioral memory schema and external source integrations as the highest-change areas. The fitness function for COGS protection (daily LiteLLM log query) matches my operational recommendation. The emphasis on additive-only migrations for the first 90 days is exactly the right constraint for a 2-person team moving fast.

**Missed gaps:**

- The recommended "4 domains at launch" simplification (briefing, sources, memory, delivery) does not address data ownership boundaries. Memory is identified as a domain but its write paths (user action vs system inference) are not separated in the evolutionary framing. "Memory domain" with two writers is still a dual-SoR problem even if it's one domain.
- No analysis of the billing_period string ("2026-02") vs DATE type trade-off. I flagged this as a subtle but important decision: Stripe billing periods are logical concepts that may not align with calendar months. Analysis D's fitness function for billing math (no floats) is correct but does not address the period boundary definition.
- The fitness function for "behavioral memory schema immutability" is flagged as missing but no solution proposed.

**Rank: Moderate**

---

### Analysis E — LLM Systems Architect (Erik Schluntz persona)

**Agreement:** Agree

**Reasoning from data perspective:**

Analysis E and my Phase 1 research are the strongest data-layer converging pair in the council. The two-layer behavioral memory architecture (raw signal log + compressed preference snapshot) directly validates my `briefing_feedback` + `memory_signals` design, though with a different implementation approach.

Analysis E proposes regenerating a `UserPreferenceSnapshot` weekly using a background Haiku job — a compact text representation (~300 tokens) injected into synthesis context. My design uses a real-time UPSERT running average on `memory_signals` with confidence scores. These are complementary, not contradictory:

- My `memory_signals` table is the **operational** store: queried per-briefing for relevance filtering, updated on each feedback event via UPSERT.
- Analysis E's `preference_snapshot` is the **context injection** layer: a weekly-regenerated LLM compression of the signal table for use in synthesis prompts.

Both are needed. The signal table alone is not the right shape for context injection (too many rows, wrong format). The snapshot alone loses the per-signal confidence tracking needed for relevance filtering. The complete design is: signal table (operational SoR) → snapshot generation job → snapshot (context SoR for LLM).

The structured output schema (`BriefingOutput` with typed fields) validates my `content_json` design and my argument that deterministic reliability checks require structured output. The `has_all_sections` and `all_items_have_sources` derived fields in my schema map directly to Analysis E's `DeterministicChecks` interface.

The cost analysis ($0.066/briefing, $1.98/user/month) provides the concrete COGS validation my data model's usage ledger needs to set reasonable task caps. The idempotency key pattern in my `usage_ledger` table prevents double-counting on retry — Analysis E identifies retry logic as necessary but does not address the double-counting data integrity concern.

**Missed gaps:**

- The `preference_signals` table in Analysis E uses `user_id` but the rest of the system uses `workspace_id` as the tenant isolation key. If a Pro user has 3 workspaces, are preferences per-workspace or per-user? This SoR ownership question is unresolved. My design explicitly uses `workspace_id` on all preference tables — preferences belong to the workspace (the product context), not the user (the identity). Analysis E's `user_id` on signals is a subtle SoR conflict.
- The `compact_text` field in `UserPreferenceSnapshot` is a human-readable string generated by an LLM. If the generation LLM's interpretation of "what the user cares about" changes between weekly runs, the snapshot may lose context that was previously captured. There is no version control on the snapshot content. This is a data durability concern.

**Rank: Strong**

---

### Analysis F — Devil's Advocate (Fred Brooks persona)

**Agreement:** Partially Agree

**Reasoning from data perspective:**

Analysis F's challenge to the behavioral memory moat is partially correct from a data perspective, but the conclusion is wrong.

Correct: At day 90, behavioral memory has at most 14 days of trial data per user. The moat has not compounded. The kill gate measures something the moat cannot yet affect. This is true and important. My schema was designed for steady-state operation; it does not change the fact that signals are sparse at trial time.

Incorrect: "Memory is not a bounded context. It is a column." A `preferences JSONB` column solves day-1 simplicity at the cost of day-90 data integrity. The core problem is not whether preferences are in a separate table or a JSON column — it is whether the write paths are separate. If a JSON column is written by both the user (via UI) and the system (via behavioral inference), you have a lost-update problem under any concurrent write scenario. Analysis F's proposed minimum viable schema (`users` with `preferences JSON`) has this problem.

The distinction between explicit preferences (user-authored) and learned signals (system-derived) is not DDD theater. It is a practical data integrity constraint: two different writers, two different update frequencies, two different retention policies (user-owned data is deletable on demand; derived signals may be retained for algorithmic purposes). These cannot share a column without a write-coordination protocol.

The SPOF analysis on Clerk-Stripe sync is correct from a data perspective. The solution I proposed (Stripe as SoR, local cache updated via webhooks, synchronous fallback on cap exceeded) addresses this directly.

Analysis F's minimum viable schema is useful as a starting point but is not production-safe for:
1. The explicit vs behavioral memory separation (dual-writer problem)
2. The usage cap enforcement (mutable counter lost-update under concurrent briefings)
3. The briefing state machine (no status history, no idempotency)

**Missed gaps:**

- The "preferences JSONB column" counter-proposal does not address concurrent write semantics. On a concurrent update (user edits preferences while system updates behavioral signal), which write wins? Last-write-wins on a JSON blob causes silent data loss.
- The argument that "behavioral memory is not the moat at day 90" is strategically correct but architecturally irrelevant. The schema must be designed for day-90+ operation from day 1; you cannot retrofit it without migrating accumulated user data.
- No analysis of the usage cap enforcement data pattern. The identified SPOF (cap race condition) is real; the fix is not mentioned.

**Rank: Moderate**

---

### Analysis G — Security Architect (Bruce Schneier persona)

**Agreement:** Agree

**Reasoning from data perspective:**

Analysis G's security analysis maps precisely onto my data architecture decisions in several critical ways.

The OAuth token table design in Analysis G (separate encryption columns: `encrypted_refresh_token`, `encrypted_access_token`, `token_iv`, `token_auth_tag`) is more precise than my schema where I specified "AES-256 encrypted" at the column level without detailing the GCM authentication tag. The GCM auth tag is not optional — without it, you have unauthenticated encryption (AES-CBC style), which is vulnerable to padding oracle attacks. Analysis G's explicit `token_auth_tag` column is the correct schema.

The IDOR analysis (Workspace Insecure Direct Object Reference) directly validates my architectural decision to put `workspace_id` on every table with a FK to `workspaces(user_id)`. The SQL example in Analysis G showing the WRONG vs CORRECT query pattern is the exact enforcement my schema design requires at the application layer. The schema provides the FK; the application must always join through it.

The data classification table (Gmail email content: "Do NOT store persistently") is a critical data architecture decision I implicitly made (briefing content is stored; source email data is not) but did not state explicitly as a security constraint. Analysis G makes it explicit: email subjects/snippets live in memory only during synthesis. This affects the schema (no `raw_email_content` column anywhere) and the data flow (no write of Gmail data to any table).

The `SELECT FOR UPDATE` semantics on OAuth token refresh is exactly the race condition I flagged in my Phase 1 "OAuth token rotation" concern. Analysis G names the fix: row-level lock on the refresh operation to prevent two concurrent tasks both seeing an expired token and both attempting refresh.

**Missed gaps:**

- No analysis of the `briefing_feedback` table and its privacy implications. Each row in `briefing_feedback` links `briefing_id`, `source_id`, and `occurred_at` — this is implicit behavioral tracking data. A GDPR-adjacent analysis would require this table to be deleted on account deletion and excluded from any analytical exports.
- The data retention table specifies "briefing_feedback: does not appear." The raw feedback signals that power behavioral memory need explicit retention policy. I specified 90 days for briefing_feedback in my schema; this needs to be documented in the security/compliance data map.
- The `usage_counters` table increment strategy (after successful task start, not before) is mentioned operationally but the double-counting prevention mechanism (idempotency key on ledger) is not addressed from a security standpoint. An attacker who can replay a task completion event could manipulate the usage counter.

**Rank: Strong**

---

### Analysis H — Operations Engineer (Charity Majors persona)

**Agreement:** Agree

**Reasoning from data perspective:**

Analysis H's operational design has the most direct data architecture implications of any peer analysis.

The BullMQ recommendation over node-cron is correct from a data durability standpoint. node-cron is in-memory. If the Fly.io machine restarts between the 5:59 AM briefing queue load and the 6:00 AM execution, jobs are silently lost. BullMQ with Redis persistence means the briefing job exists as a durable record until it is explicitly dequeued. This is a write-before-execute data pattern: the job is a record, not an ephemeral in-memory callback. This aligns with my `briefings` table state machine — the job record (BullMQ) and the briefing record (SQLite) must be consistent. A briefing in `status='scheduled'` in SQLite must have a corresponding job in BullMQ; if they diverge, the briefing is orphaned.

The distributed trace schema (structured log with `trace_id`, `briefing_id`, `scheduled_at`, `sources_failed[]`) maps directly to my `briefing_sources` table's `fetch_status` column per source and the `briefings` table's state machine fields. The operational observability and the data schema are aligned.

The timeout strategy (10s per source, 60s synthesis) and the graceful degradation decision tree (partial briefing when sources fail) has a data implication I did not address: if a briefing is generated with only 3/5 sources due to failures, is it a `delivered` briefing or a `degraded_delivered` briefing? My current status machine has no `degraded_delivered` state. Analysis H implies this distinction matters ("partial briefing is better than no briefing") but the data model needs a way to record it. Adding a `delivery_quality` field (`full`, `degraded`, `failed`) to the `briefings` table captures this without changing the state machine.

The LLM cost per-user tracking (every LLM call carries `user_id` metadata → Prometheus → Grafana) requires the application to associate LLM calls with the briefing and workspace. My `briefings` table already captures `llm_tokens_in`, `llm_tokens_out`, `llm_cost_usd` per briefing — this is the source of truth for usage-based billing audit. LiteLLM's Prometheus metrics are the real-time operational view; the `briefings` table is the durable audit record. Both are needed.

**Missed gaps:**

- No analysis of the BullMQ Redis job record and the SQLite `briefings` table consistency. If BullMQ marks a job complete but the SQLite write fails (e.g., DB connection drop during the final state update), the job is dequeued but `status` remains `delivering` indefinitely. This is a two-phase commit problem between two data stores (Redis and SQLite). The mitigation: the BullMQ job completion should be idempotent-safe, and a background reconciliation job should detect stale `delivering` statuses and retry the delivery step.
- The Upstash Redis free tier limits (10K req/day) are mentioned for job queue operations. But LiteLLM also uses Redis for its budget tracking if configured that way. Two Redis use cases (job queue + cost tracking) on the same free-tier instance need to be accounted for — or separated into two Redis instances.
- No discussion of the SQLite WAL checkpoint and its interaction with rolling deploys. When a new Fly.io machine starts (rolling deploy), it mounts the same persistent volume. If the old machine's WAL had uncommitted pages, the new machine sees a database in an intermediate state. Fly.io's rolling deploy + SQLite WAL requires the old machine to checkpoint before the new machine starts. This is not automatic and must be part of the deploy script.

**Rank: Strong**

---

## Ranking

**Best Analysis:** B (Domain Modeler — Eric Evans persona)

**Reason:** Analysis B provides the strongest cross-validation of my data architecture decisions. The Signal vs Item distinction maps directly to my `briefing_sources` table design. The `DeclaredPriority` vs `LearnedSignal` entity separation within `PriorityProfile` validates my two-table explicit/behavioral memory architecture at the domain level. When the domain model demands the same entity separation as the data model, the design is correct from both directions. Analysis B also asks the right business questions (engagement granularity, task definition) that the data model depends on.

**Worst Analysis:** F (Devil's Advocate — Fred Brooks persona)

**Reason:** Analysis F correctly identifies real complexity risks (LangGraph, Turso, 9 contexts) but the proposed data solution (preferences JSONB column) is architecturally unsafe. The "simplify to 3 tables" counter-proposal silently introduces the dual-SoR problem for preferences and the lost-update problem for usage caps — exactly the two data integrity bugs that would require a painful migration to fix at month 6 with real user data. The strategic critique (behavioral memory moat not testable at day 90) is valid, but the tactical data recommendation would trade architecture complexity for data integrity bugs. In data engineering, that is not a good trade.

---

## Revised Position

**Revised Verdict:** Refined (not changed in direction, but sharpened in three areas)

**What peer analyses added:**

**1. GCM authentication tag on OAuth tokens (Analysis G).**
My Phase 1 schema specified AES-256 encryption without specifying the cipher mode details. Analysis G correctly notes that GCM auth tag is mandatory — without it, you have unauthenticated encryption vulnerable to ciphertext manipulation. The `oauth_tokens` schema must add `token_auth_tag TEXT NOT NULL` as a separate column.

**2. Preference snapshot as distinct layer from signal table (Analysis E).**
My Phase 1 design had `memory_signals` as both the operational SoR and the context injection source. Analysis E correctly introduces a third artifact: a weekly-generated `preference_snapshot` compressed by a Haiku call for context injection. The complete three-layer design is: `briefing_feedback` (raw event log) → `memory_signals` (operational running average) → `preference_snapshot` (context injection representation). I will add this to my data model.

**3. `delivery_quality` field on `briefings` table (Analysis H).**
My state machine status values (`scheduled`, `fetching_sources`, `synthesizing`, `delivering`, `delivered`, `failed`, `cancelled`) do not distinguish between a full briefing and a degraded briefing that delivered with only 3/5 sources. Analysis H's graceful degradation design implies this distinction matters for user communication and SLO measurement. I will add `delivery_quality TEXT CHECK (delivery_quality IN ('full', 'degraded', 'failed'))` to the `briefings` table.

**4. workspace_id vs user_id as tenant key (from Analysis E gap).**
Analysis E uses `user_id` on preference tables. My position is confirmed: `workspace_id` is the correct tenant isolation key for all product data. A Pro user with 3 workspaces has 3 independent priority profiles. Identity (user) and product context (workspace) are different keys. This must be consistent across ALL tables.

**5. BullMQ/SQLite two-store consistency (from Analysis H gap).**
The two-phase commit problem between BullMQ Redis (job complete) and SQLite (briefing status updated) is a real gap in my Phase 1 design. The mitigation: a background reconciliation job that detects `briefings WHERE status IN ('delivering', 'synthesizing') AND status_updated_at < NOW() - INTERVAL 30 minutes` and retries the terminal step. This is the "compensating transaction" pattern from DDIA Chapter 8.

**Final Data Recommendation:**

The core schema decisions from Phase 1 hold:
- Append-only `usage_ledger` with idempotency key (not mutable counter)
- Separate `preferences` (user-owned) and `memory_signals` (system-derived)
- Structured `content_json` for deterministic reliability checks
- `billing_cache` as explicitly-labelled Stripe read-through cache
- `briefing_sources` for data lineage from fetch through synthesis
- UUID v7 primary keys throughout

Three additions from cross-critique:
1. `token_auth_tag` column on `oauth_tokens` table (GCM authentication tag)
2. `preference_snapshot` table for weekly-generated context injection representation
3. `delivery_quality` field on `briefings` table for degraded vs full delivery distinction

One confirmed architectural choice from cross-critique:
- `workspace_id` (not `user_id`) as the tenant isolation key on ALL product data tables. Preferences, signals, briefings, sources — all scoped to workspace, not user. Confirmed by Domain Model (Analysis B) and validated against Security IDOR analysis (Analysis G).

The data architecture is sound. The risks are in operational edge cases (BullMQ/SQLite consistency, OAuth token rotation race, Stripe webhook staleness) — all addressable with specific patterns, none requiring schema redesign.
