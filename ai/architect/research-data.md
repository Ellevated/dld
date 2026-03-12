# Data Architecture Research

**Persona:** Martin (Data Architect)
**Focus:** Schema, migrations, data flows, system of record
**Date:** 2026-02-27

---

## Research Conducted

Note: Exa MCP hit rate limit (free tier). Research below is drawn from internalized expertise in SQLite internals, DDIA, Turso/libSQL documentation, and production SaaS patterns — all cited by canonical source.

- [SQLite WAL Mode Documentation](https://www.sqlite.org/wal.html) — official WAL concurrency semantics
- [Turso/libSQL Architecture](https://turso.tech/blog/introducing-turso-a-distributed-database-built-on-libsql) — per-tenant DB model, replication semantics
- [Martin Kleppmann — Designing Data-Intensive Applications](https://dataintensive.net/) — consistency models, SoR patterns, log-structured storage
- [Litestream](https://litestream.io/) — SQLite replication patterns for production
- [Stripe Usage-Based Billing Schema](https://stripe.com/docs/billing/subscriptions/usage-based) — metering counter patterns
- [Anthropic Evals Cookbook](https://github.com/anthropics/evals) — LLM-as-judge reliability measurement
- [PostgreSQL SKIP LOCKED pattern](https://www.2ndquadrant.com/en/blog/what-is-select-skip-locked-for-in-postgresql-9-5/) — queue semantics in relational DBs (analogous pattern for SQLite)
- Deep research sessions: rate-limited; analysis proceeds from canonical sources above

**Total queries attempted:** 8 (6 web + 2 deep research) — rate limited after first burst. All findings from internalized canonical sources.

---

## Kill Question Answer

**"What is the system of record for each entity?"**

| Entity | System of Record | Justification |
|--------|-----------------|---------------|
| User identity | Clerk | Clerk owns auth. We never duplicate email/password. Our DB stores only `clerk_user_id` as FK. |
| Workspace | Our SQLite/Turso DB | Workspace is a product concept (not Clerk's). Owns tier, usage caps, settings. |
| User preferences (explicit) | Our SQLite/Turso DB — `preferences` table | User-entered preferences. Mutable via UI. Single writer: our API. |
| Behavioral memory (learned) | Our SQLite/Turso DB — `memory_signals` table | Derived from usage patterns. Different table from explicit prefs — different write path. |
| Source configurations | Our SQLite/Turso DB — `source_configs` table | User-configured integrations. Versioned rows, not in-place mutations. |
| OAuth tokens (Gmail, Calendar) | Our SQLite/Turso DB — `oauth_tokens` table | Encrypted at rest. Single SoR. Never cached elsewhere. |
| Briefing (scheduled/generated) | Our SQLite/Turso DB — `briefings` table | Full lifecycle state machine. Immutable once delivered. |
| Usage counters | Our SQLite/Turso DB — `usage_ledger` table | Append-only ledger (not a mutable counter). Prevents double-count race. |
| Billing state (subscription tier, status) | Stripe | Stripe owns billing truth. We cache `stripe_subscription_id` + current tier locally. Webhook-updated. |
| Stripe cached state | Our SQLite/Turso DB — `billing_cache` table | Read-through cache from Stripe webhooks. Authoritative Stripe, local cache for fast cap checks. |

**Conflicts identified:**

1. **Tier enforcement split**: Stripe owns billing truth, but we need fast cap checks at runtime without calling Stripe per-request. Resolved by local `billing_cache` table updated via Stripe webhooks. The SoR for billing IS Stripe; the cache is an explicitly labelled read replica. Staleness window: max 30 seconds (webhook delivery) — acceptable for usage caps.

2. **Behavioral memory vs explicit preferences**: These must be SEPARATE tables with separate write paths. Conflating them into a single "preferences" blob creates a dual-SoR problem — the user edits their explicit prefs, and the system overwrites behavioral signals, or vice versa. Explicit = user-owned, behavioral = system-owned.

3. **Usage counters — mutable vs ledger**: A mutable `tasks_used` counter with UPDATE is dangerous under concurrent briefing generation (lost update problem). Resolution: append-only `usage_ledger` with a `SUM()` read view. The ledger IS the SoR; the materialized count is a derived view.

---

## Proposed Data Decisions

### Core Schema Model

**Entity Relationship Diagram:**

```
┌──────────────┐       ┌──────────────────┐
│  clerk_users │──1:N──│   workspaces     │
│  (Clerk SoR) │       │  (our SoR)       │
└──────────────┘       └──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
             1:N              1:N              1:N
              │                │                │
              ↓                ↓                ↓
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  preferences │  │source_configs│  │usage_ledger  │
    │  (explicit)  │  │ (versioned)  │  │(append-only) │
    └──────────────┘  └──────────────┘  └──────────────┘
              │                │
             1:N              1:N
              │                │
              ↓                ↓
    ┌──────────────┐  ┌──────────────────────┐
    │memory_signals│  │    briefings         │
    │  (learned)   │  │  (state machine)     │
    └──────────────┘  └──────────────────────┘
                               │
                              1:N
                               │
                               ↓
                      ┌──────────────────┐
                      │ briefing_sources  │
                      │ (lineage/trace)   │
                      └──────────────────┘
```

---

### Schema per Domain

#### Auth / Workspace Schema

```sql
-- Workspaces: the product-level tenant unit
-- SoR: our DB (not Clerk)
CREATE TABLE workspaces (
    id          TEXT PRIMARY KEY,        -- UUID v7 (time-sortable)
    clerk_org_id TEXT,                   -- NULL for Solo tier (personal workspace)
    clerk_user_id TEXT NOT NULL,         -- owner
    name        TEXT NOT NULL,
    tier        TEXT NOT NULL CHECK (tier IN ('trial', 'solo', 'pro')),
    trial_ends_at TIMESTAMPTZ,           -- NULL after conversion
    task_cap_monthly INTEGER NOT NULL,   -- 50 trial / 500 solo / 2000 pro
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One workspace per Solo user (enforced by unique index)
CREATE UNIQUE INDEX idx_workspaces_solo_user
    ON workspaces(clerk_user_id)
    WHERE tier IN ('trial', 'solo');

-- Billing cache (read replica from Stripe webhooks)
-- SoR: Stripe. This is explicitly a cache.
CREATE TABLE billing_cache (
    workspace_id        TEXT PRIMARY KEY REFERENCES workspaces(id),
    stripe_customer_id  TEXT NOT NULL,
    stripe_sub_id       TEXT,
    current_tier        TEXT NOT NULL,
    period_start        TIMESTAMPTZ,
    period_end          TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Design notes:**
- `task_cap_monthly` is denormalized onto `workspaces` deliberately. The cap is a business rule that changes only on tier change (webhook). Joining billing_cache on every usage check adds a join that gains nothing.
- UUID v7 is time-sortable — important for SQLite where index fragmentation matters at scale.

---

#### Source Configurations Schema

```sql
-- Source configurations: user-configured data integrations
-- SoR: our DB. Versioned with soft-delete (never mutate, always insert new version).
CREATE TABLE source_configs (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    source_type     TEXT NOT NULL CHECK (source_type IN (
                        'rss', 'hackernews', 'twitter_list',
                        'gmail', 'google_calendar', 'custom_url'
                    )),
    config_json     TEXT NOT NULL,   -- JSON: {url, filters, keywords, etc.}
    version         INTEGER NOT NULL DEFAULT 1,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deactivated_at  TIMESTAMPTZ     -- set when replaced by new version
);

CREATE INDEX idx_source_configs_workspace_active
    ON source_configs(workspace_id, is_active, source_type);

-- OAuth tokens for Gmail / Calendar
-- SoR: our DB (encrypted at rest via application-layer encryption)
-- NEVER store in config_json — separate table, separate access path
CREATE TABLE oauth_tokens (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    provider        TEXT NOT NULL CHECK (provider IN ('google', 'microsoft')),
    access_token_enc TEXT NOT NULL,   -- AES-256 encrypted
    refresh_token_enc TEXT NOT NULL,  -- AES-256 encrypted
    token_expiry    TIMESTAMPTZ NOT NULL,
    scopes          TEXT NOT NULL,    -- comma-separated granted scopes
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_oauth_tokens_workspace_provider
    ON oauth_tokens(workspace_id, provider);
```

**Design notes:**
- Source configs are versioned with soft-delete, NOT in-place update. This is critical: if a briefing fails because of a bad source config, you need to know which version was active when the briefing ran. In-place UPDATE destroys this lineage.
- OAuth tokens are in their own table. They have a completely different access pattern (read on every briefing run, written only on auth/refresh) and different encryption requirements. Mixing them into `source_configs` JSON would be a serious security design error.

---

#### User Preferences + Behavioral Memory Schema

This is the most architecturally important distinction in the system. Explicit preferences (user-set) and behavioral memory (system-learned) must be separate entities with separate SoRs and separate write paths.

```sql
-- EXPLICIT PREFERENCES: user-authored, user-editable
-- SoR: our DB. Written by user via UI. Single writer: our API on user action.
CREATE TABLE preferences (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    pref_key        TEXT NOT NULL,    -- e.g. 'delivery_time', 'max_items', 'tone'
    pref_value      TEXT NOT NULL,    -- JSON-encoded value
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by      TEXT NOT NULL DEFAULT 'user' CHECK (updated_by IN ('user', 'system'))
);

CREATE UNIQUE INDEX idx_preferences_workspace_key
    ON preferences(workspace_id, pref_key);

-- Known preference keys (document as CHECK or in app-layer validation):
-- delivery_time: "06:00"                  -- local time for briefing
-- timezone: "America/New_York"
-- max_items_per_source: 5
-- briefing_tone: "concise" | "detailed"
-- excluded_keywords: ["crypto", "NFT"]
-- priority_senders: ["boss@co.com"]       -- for Gmail triage
-- protected_calendar_keywords: ["standup"]


-- BEHAVIORAL MEMORY: system-learned signals, never user-edited
-- SoR: our DB. Written by system only. Derived from usage events.
-- This is NOT a preferences table — it is an inference log.
CREATE TABLE memory_signals (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    signal_type     TEXT NOT NULL CHECK (signal_type IN (
                        'source_engagement',    -- user opened/read items from source
                        'topic_interest',       -- topic cluster that gets attention
                        'sender_priority',      -- email sender engagement pattern
                        'time_sensitivity',     -- how user responds to time-sensitive items
                        'dismissed_topic'       -- topic user consistently skips
                    )),
    signal_key      TEXT NOT NULL,   -- e.g. source_id, topic slug, sender email
    signal_value    REAL NOT NULL,   -- normalized 0.0–1.0 weight
    confidence      REAL NOT NULL DEFAULT 0.0,  -- grows with observations
    observation_count INTEGER NOT NULL DEFAULT 1,
    last_observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_memory_signals_workspace_type_key
    ON memory_signals(workspace_id, signal_type, signal_key);

CREATE INDEX idx_memory_signals_workspace_type
    ON memory_signals(workspace_id, signal_type);

-- Signal update is an UPSERT, not insert:
-- UPDATE SET signal_value = (old_value * observation_count + new_value) / (observation_count + 1),
--            confidence = MIN(1.0, confidence + 0.05),
--            observation_count = observation_count + 1,
--            last_observed_at = CURRENT_TIMESTAMP
-- This is a running weighted average — the compound learning mechanism.

-- Briefing feedback events: the raw input to memory_signals
CREATE TABLE briefing_feedback (
    id              TEXT PRIMARY KEY,
    briefing_id     TEXT NOT NULL REFERENCES briefings(id),
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    feedback_type   TEXT NOT NULL CHECK (feedback_type IN (
                        'opened',          -- user opened the briefing
                        'item_clicked',    -- user clicked through on a specific item
                        'item_dismissed',  -- user explicitly dismissed an item
                        'full_read',       -- user scrolled to bottom
                        'skipped'          -- briefing delivered, never opened
                    )),
    item_ref        TEXT,            -- JSON ref to specific briefing item (nullable)
    source_id       TEXT,            -- FK to source_configs (nullable)
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_briefing_feedback_workspace ON briefing_feedback(workspace_id, occurred_at);
```

**Why this two-table design for memory:**

DDIA Chapter 11 on "Derived Data" is the conceptual anchor. `memory_signals` is a derived dataset — it is computed from `briefing_feedback` events. The feedback table is the log (source of truth for events), and `memory_signals` is the materialized view of that log (the derived state).

This means:
- If we change our learning algorithm, we can recompute `memory_signals` from scratch using the raw `briefing_feedback` log.
- The `memory_signals` table is not the source of truth for what happened — it's the current inference. That's fine, as long as we keep the log.
- Never conflate "what the user did" (feedback events) with "what we think the user wants" (memory signals). These are different epistemic categories.

**How behavioral memory compounds over time:**

The `signal_value` is a running Bayesian-inspired weighted average:
```
new_value = (old_value * count + observed_value) / (count + 1)
confidence = min(1.0, old_confidence + 0.05)
```

After ~20 observations, confidence reaches 1.0 and the signal stabilizes. Low-confidence signals get lower weight in briefing generation context injection. This is the "compound" mechanism — not magic, just statistics encoded in a schema.

---

#### Briefings Schema (State Machine + Reliability Data)

```sql
-- Briefings: the core product artifact
-- SoR: our DB. State machine with explicit transitions.
-- IMMUTABLE once state = 'delivered'. Never update content after delivery.
CREATE TABLE briefings (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),

    -- Scheduling
    scheduled_for   TIMESTAMPTZ NOT NULL,   -- intended delivery time (6am local)
    timezone        TEXT NOT NULL,          -- user's timezone at schedule time

    -- State machine
    -- scheduled → fetching_sources → synthesizing → delivering → delivered
    -- Any state can transition to: failed, cancelled
    status          TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN (
                        'scheduled', 'fetching_sources', 'synthesizing',
                        'delivering', 'delivered', 'failed', 'cancelled'
                    )),
    status_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    failure_reason  TEXT,            -- NULL unless status = 'failed'
    retry_count     INTEGER NOT NULL DEFAULT 0,

    -- Content (structured JSON, NOT freeform text)
    content_schema_version INTEGER NOT NULL DEFAULT 1,
    content_json    TEXT,            -- NULL until synthesizing completes; see schema below
    word_count      INTEGER,         -- derived from content_json on insert
    item_count      INTEGER,         -- total items across all sections
    source_count    INTEGER,         -- distinct sources used

    -- Reliability measurement fields
    -- These allow deterministic checks without re-running LLM
    has_all_sections    INTEGER,     -- 1 if all required sections present
    all_items_have_sources INTEGER,  -- 1 if every item has a source citation
    delivery_latency_ms INTEGER,     -- actual_delivered_at - scheduled_for in ms
    synthesis_duration_ms INTEGER,   -- time to run LLM synthesis
    llm_model_used  TEXT,            -- which model handled synthesis
    llm_tokens_in   INTEGER,
    llm_tokens_out  INTEGER,
    llm_cost_usd    REAL,            -- cost in USD for this specific briefing

    -- Timestamps
    fetching_started_at  TIMESTAMPTZ,
    synthesizing_started_at TIMESTAMPTZ,
    delivered_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_briefings_workspace_status ON briefings(workspace_id, status, scheduled_for);
CREATE INDEX idx_briefings_scheduled ON briefings(scheduled_for, status) WHERE status = 'scheduled';

-- Source lineage: which source contributed what to this briefing
-- This is the data lineage table — critical for debugging wrong content
CREATE TABLE briefing_sources (
    id              TEXT PRIMARY KEY,
    briefing_id     TEXT NOT NULL REFERENCES briefings(id),
    source_config_id TEXT NOT NULL REFERENCES source_configs(id),
    source_type     TEXT NOT NULL,
    items_fetched   INTEGER NOT NULL DEFAULT 0,
    items_used      INTEGER NOT NULL DEFAULT 0,    -- after relevance filtering
    fetch_duration_ms INTEGER,
    fetch_status    TEXT NOT NULL CHECK (fetch_status IN ('ok', 'timeout', 'error', 'empty')),
    error_detail    TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_briefing_sources_briefing ON briefing_sources(briefing_id);

-- Briefing content JSON schema (stored in briefings.content_json):
-- {
--   "schema_version": 1,
--   "title": "Morning Briefing — Friday, Feb 28",
--   "generated_at": "2026-02-28T06:00:12Z",
--   "sections": [
--     {
--       "type": "tech_news" | "email_triage" | "calendar" | "projects" | "custom",
--       "title": "Tech News",
--       "items": [
--         {
--           "id": "uuid",
--           "headline": "OpenAI ships agents API",
--           "summary": "Two sentence summary...",
--           "relevance_score": 0.87,
--           "source": {
--             "source_config_id": "uuid",
--             "source_type": "hackernews",
--             "original_url": "https://...",
--             "source_title": "Hacker News"
--           },
--           "priority": "high" | "medium" | "low"
--         }
--       ]
--     }
--   ],
--   "meta": {
--     "total_sources_fetched": 8,
--     "total_items_considered": 127,
--     "total_items_included": 18,
--     "personalization_signals_used": 14
--   }
-- }
```

**Why structured JSON (not freeform Markdown):**

The `>90% reliability` requirement from the Business Blueprint is not achievable if the briefing content is Markdown prose. You cannot deterministically check Markdown for required sections, source citations, or item completeness. Structured JSON enables:

1. **Deterministic checks** (zero LLM cost): `has_all_sections`, `all_items_have_sources`, item count range checks.
2. **Source lineage**: every item in `content_json` has a `source_config_id` — this is the data lineage from fetch through synthesis to delivery.
3. **LLM-as-judge targeting**: when deterministic checks fail, the LLM judge gets a specific field to evaluate, not a freeform blob.
4. **Rendering flexibility**: same JSON renders to Telegram message, email HTML, or web dashboard without re-generating.

---

#### Usage Metering Schema

This is where most SaaS systems make the critical mistake: a mutable `tasks_used INTEGER` counter that gets `UPDATE workspaces SET tasks_used = tasks_used + 1`. Under concurrent briefing generation (multiple users' briefings running simultaneously), this is a classic lost-update problem.

**The correct pattern: append-only ledger.**

```sql
-- Usage ledger: append-only. Never UPDATE, never DELETE.
-- SoR: our DB. Each row is an immutable fact about resource consumption.
CREATE TABLE usage_ledger (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'task_consumed',     -- one task used (one briefing = one task)
                        'task_reversed',     -- refund for failed task (idempotency key match)
                        'cap_reset'          -- monthly cap reset (billing period rollover)
                    )),
    amount          INTEGER NOT NULL DEFAULT 1,   -- positive or negative
    idempotency_key TEXT NOT NULL UNIQUE,         -- prevents double-counting on retry
    briefing_id     TEXT REFERENCES briefings(id),
    billing_period  TEXT NOT NULL,                -- "2026-02" (YYYY-MM)
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usage_ledger_workspace_period
    ON usage_ledger(workspace_id, billing_period, occurred_at);

-- Materialized view for fast cap checks (updated after each ledger insert):
CREATE TABLE usage_summary (
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    billing_period  TEXT NOT NULL,
    tasks_consumed  INTEGER NOT NULL DEFAULT 0,
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, billing_period)
);
```

**How hard caps work (atomic, no lost-update):**

```sql
-- BEFORE starting a briefing task, execute in a single transaction:
BEGIN IMMEDIATE;  -- SQLite WAL: acquires write lock immediately

SELECT u.tasks_consumed, w.task_cap_monthly
FROM usage_summary u
JOIN workspaces w ON w.id = u.workspace_id
WHERE u.workspace_id = ? AND u.billing_period = ?
FOR UPDATE;  -- row lock (in SQLite: implicit with IMMEDIATE)

-- If tasks_consumed >= task_cap_monthly: ROLLBACK, return 429
-- Else:
INSERT INTO usage_ledger (id, workspace_id, event_type, amount, idempotency_key, billing_period, briefing_id)
VALUES (?, ?, 'task_consumed', 1, ?, ?, ?);

UPDATE usage_summary
SET tasks_consumed = tasks_consumed + 1, last_updated_at = CURRENT_TIMESTAMP
WHERE workspace_id = ? AND billing_period = ?;

COMMIT;
```

This pattern:
- `BEGIN IMMEDIATE` in SQLite WAL mode acquires the write lock at transaction start, preventing concurrent writers from racing on the cap check.
- `idempotency_key` on `usage_ledger` prevents double-counting if the task is retried.
- `usage_summary` is a write-through materialized view — updated atomically with the ledger insert.
- If the briefing fails after the task is counted, insert a `task_reversed` row with the same `briefing_id` and negate the charge.

---

### SQLite WAL Mode — Concurrency Analysis

**How WAL actually works for this system:**

SQLite WAL (Write-Ahead Log) gives us:
- **Multiple concurrent readers, one writer at a time.** Readers never block writers; writers never block readers.
- **Writer serialization**: only one write transaction runs at a time. If two briefing jobs try to write simultaneously, the second one blocks until the first commits (with configurable `busy_timeout`).
- **Checkpoint**: WAL entries are periodically checkpointed back to the main DB file. Default: every 1000 pages. In production: configure `PRAGMA wal_autocheckpoint = 100` for tighter control.

**Concurrent briefing generation — what actually happens:**

At <500 users, briefings run as a daily cron at 6am per timezone. Even at 500 users across 4–6 time zones, peak simultaneous briefing jobs = ~100–150. Each briefing:
1. Reads source_configs (read — non-blocking, all reads are concurrent).
2. Fetches external data (I/O-bound, not DB-bound — SQLite is idle during this phase).
3. Writes briefing state transitions (write — serialized, but fast: single row update, <1ms).
4. Inserts usage_ledger entry (write — serialized, <1ms).

**The write operations are not the bottleneck.** The bottleneck is the external HTTP fetches and LLM synthesis (seconds to minutes). SQLite write serialization at <1ms per write means 150 concurrent briefings create a write queue of ~150ms total — invisible to users.

**When WAL becomes a problem:**

WAL write serialization becomes a bottleneck when:
- Write transactions are long (hold the write lock for seconds). Solution: keep writes short. Never do external I/O inside a write transaction.
- Checkpoint lag: WAL file grows large if checkpointing falls behind. Solution: monitor WAL file size, configure `wal_autocheckpoint`.
- Turso replication lag: writes go to primary, reads from replicas. If a briefing writes state and immediately reads it back from a replica, stale read is possible. Solution: use `PRAGMA read_your_own_writes = true` (Turso-specific) or always read briefing status from primary.

**Turso multi-tenant model for this system:**

Two viable approaches:

| Approach | Schema | When |
|----------|--------|------|
| Single shared DB | All tenants in one DB, workspace_id FK everywhere | <1000 users, simple ops |
| Per-tenant DB | One Turso DB per workspace | >1000 users, or when tenant isolation is critical |

**Recommendation: start with single shared DB.** At <500 users, the operational overhead of per-tenant DB management (provisioning, migrations across N databases) is not justified. Migrate to per-tenant at 1000+ users using Turso's branching feature. The schema is designed with `workspace_id` on every table precisely to make this migration mechanical — no data model changes needed, only a sharding key extraction.

---

### Data Flow Architecture

**Flow Diagram:**

```
User signup (Clerk webhook)
    ↓
[API] creates workspace + billing_cache row
    ↓
[workspaces DB]

User configures sources
    ↓
[API] inserts source_configs (versioned, never mutates)
    ↓
[source_configs DB]

Daily cron (6am per timezone)
    ↓
[Scheduler] reads workspaces WHERE delivery_time matches
    ↓
[Briefing Runner]:
  1. BEGIN IMMEDIATE → check cap → insert usage_ledger → COMMIT
  2. Update briefing status → 'fetching_sources'
  3. Fetch all sources in parallel (external I/O, NOT in transaction)
  4. Insert briefing_sources rows (one per source, with fetch results)
  5. Update briefing status → 'synthesizing'
  6. LLM synthesis (external call, NOT in transaction)
  7. Insert content_json + computed reliability fields
  8. Update briefing status → 'delivering'
  9. Deliver via Telegram/email
  10. Update briefing status → 'delivered', delivered_at = NOW()
    ↓
[briefings DB + briefing_sources DB]

User opens/clicks briefing
    ↓
[API] inserts briefing_feedback rows
    ↓
[Memory signal updater] (async, after feedback batch):
  UPSERT memory_signals with running average
    ↓
[memory_signals DB]

Stripe webhook (subscription change)
    ↓
[API] updates billing_cache + workspaces.task_cap_monthly + workspaces.tier
    ↓
[billing_cache DB]
```

**Patterns:**

- **Briefing generation → DB writes**: All state transitions are synchronous writes to the briefing row. This gives us a reliable audit trail of where a briefing failed.
- **External I/O (source fetch, LLM)**: Always outside DB transactions. Transactions must be short. External I/O inside a transaction holds the write lock — catastrophic for WAL concurrency.
- **Feedback → memory signals**: Async batch. Feedback is written immediately (low latency). Memory signal updates run asynchronously (e.g., every 15 minutes via a background job). This decouples user interaction latency from the learning loop.
- **Stripe webhook → billing_cache**: Synchronous write, idempotent (Stripe retries webhooks). The billing_cache must be updated atomically with `workspaces.task_cap_monthly`.

---

### Migration Strategy

**Approach: Expand-Contract for all schema changes**

SQLite does not support `ALTER COLUMN`, `DROP COLUMN` (before SQLite 3.35.0), or adding NOT NULL columns without defaults. Every schema change must be backwards-compatible at write time before old code is retired.

**Standard migration steps for this system:**

1. **Expand**: Add new column with DEFAULT or NULL. Old code ignores it. New code writes to it.
2. **Deploy new code**: Now both old and new columns are populated.
3. **Backfill** (if needed): Background job fills nulls in old rows.
4. **Contract**: Remove old column (only after verifying no reads from old column).

**Migration tooling:** `drizzle-kit` for TypeScript/Node.js stack with SQLite. Generates migration SQL files that are committed to git and applied at deploy time. Never apply migrations from developer laptops — CI/CD only (consistent with CLAUDE.md architecture rules).

**Zero-downtime for this scale:**

At <500 users, the briefing cron runs at predictable times (6am per timezone). Migrations can be applied during off-peak hours (10pm–4am UTC) when no briefings are running. This is simpler than blue-green for a 2-person team. Document in runbook: "Never deploy during 5am–8am UTC."

**SQLite-specific rules:**
- Never run `ALTER TABLE ... RENAME COLUMN` while briefing jobs are in flight (SQLite locks the entire DB during schema operations).
- Use `WITHOUT ROWID` for tables that are UUID-keyed (slightly more efficient for UUID primary keys without integer rowid).
- `PRAGMA foreign_keys = ON` must be set per-connection — SQLite does NOT enforce foreign keys by default. This must be in the connection initialization code.

---

### Consistency Models

**Transaction Boundaries:**

| Operation | Scope | Pattern | Justification |
|-----------|-------|---------|---------------|
| Cap check + usage increment | Single SQLite transaction (BEGIN IMMEDIATE) | ACID | Lost-update would allow users to exceed caps — direct revenue impact |
| Briefing state transitions | Single row UPDATE | ACID (implicit) | State machine must be consistent; intermediate states observable |
| Source fetch + briefing_sources insert | Non-transactional (multiple small writes) | Best-effort | External I/O between steps; cannot hold write lock |
| Memory signal update | UPSERT with running average | ACID (single row) | Concurrent memory updates would skew the running average |
| Stripe webhook processing | SQLite transaction wrapping billing_cache + workspaces update | ACID | Tier change must update both tables atomically |
| Feedback logging | Fire-and-forget INSERT | Eventual | Low-priority, high-volume; losing one feedback event is acceptable |

**Invariants that must never be violated:**

1. **Usage cap invariant**: `SUM(usage_ledger.amount) <= workspaces.task_cap_monthly` for any billing_period. Enforced by BEGIN IMMEDIATE + cap check before ledger insert.
2. **Briefing state monotonicity**: A delivered briefing's `content_json` must never be modified. Status can only advance (no backwards transitions except to 'failed'). Enforced by application-layer state machine + NOT NULL constraint on `delivered_at` once set.
3. **Source lineage completeness**: Every item in `briefings.content_json` must have a `source_config_id` that exists in `briefing_sources` for the same `briefing_id`. Enforced by the structured JSON schema + insertion order (briefing_sources rows inserted before content_json is finalized).
4. **OAuth token isolation**: An `oauth_token` row is accessible only via its `workspace_id`. Application layer must verify workspace ownership before decrypting. Never cache decrypted tokens in memory beyond a single request.

**CAP trade-off:**

This system chooses **CP over AP** for usage caps (consistency + partition tolerance, sacrificing availability). If the DB is unreachable, briefing generation halts rather than running without cap enforcement. This is correct: the alternative (running without cap enforcement during partition) would cause unbounded LLM cost — existential for a pre-$10K MRR startup.

For **briefing delivery**, availability is preferred over consistency: if the DB is slow, best to deliver the briefing even if the state transition write fails and we retry the status update later. A delivered briefing with a temporarily inconsistent `status` row is better than a user who wakes up with no briefing.

---

## Cross-Cutting Implications

### For Domain Architecture (Eric Evans)

- `workspace_id` is the aggregate root for all Phase 2 entities. The bounded context boundary runs at the workspace level. All queries within a context start with `WHERE workspace_id = ?`.
- The `preferences` and `memory_signals` tables belong to the **Memory** bounded context. The **Briefing** context reads from Memory but never writes to it — the briefing generation process is a reader of memory, not an author.
- The **Billing** bounded context owns `billing_cache` and the cap enforcement logic. It exposes one query: `canConsumeTask(workspaceId, billingPeriod) → boolean`. The Briefing context calls this but never touches billing tables directly.
- Anti-corruption layer: external API responses (HN API JSON, Gmail API payload) must be mapped to internal types BEFORE any DB write. Never store raw external API response in `briefing_sources` — store only the fields the domain actually uses.

### For API Design

- Every API endpoint that modifies data must declare which table it writes to, and whether that write is the SoR or a cache update. This should be in API route comments, not just documentation.
- The briefing content JSON schema (`content_schema_version`) must be versioned in the API response. When the JSON schema changes (adding a new section type), old mobile/Telegram clients must still parse it. Schema evolution = API contract.

### For Agent / LLM Architecture

- **Context injection for behavioral memory**: Do NOT dump the entire `memory_signals` table into the LLM context. Query only signals with `confidence > 0.3` and `signal_type` relevant to the current briefing phase. This keeps the context injection to ~20–50 signals per user at steady state, not 500 rows.
- **Structured output enforcement**: The LLM must output the briefing content JSON schema exactly. Use function calling / structured outputs (not Markdown parsing) to get the JSON. The deterministic reliability checks (`has_all_sections`, `all_items_have_sources`) run against this JSON before the briefing is marked as delivered.
- **Read vs write separation**: LLM agents should be READ-ONLY with respect to the DB during synthesis. The agent reads `source_configs`, `preferences`, `memory_signals`. It returns structured JSON. The application layer writes the JSON to `briefings.content_json`. Agents do not write to the DB directly. (ADR-007 pattern from DLD.)

### For Operations

- **Backup**: Litestream for continuous SQLite replication to S3 (or Tigris on Fly.io). WAL mode + Litestream = point-in-time recovery at 1-second granularity. Cost: ~$5/month for small DB. Non-negotiable.
- **Data retention**: `briefing_feedback` rows can be archived after 90 days (memory_signals derived data is durable; raw events are only needed for recomputation). `briefings.content_json` can be archived after 30 days. `usage_ledger` must be retained for minimum 1 year (billing audit trail).
- **Query monitoring**: WAL mode writes serialize, so slow write queries directly impact briefing throughput. Any write taking >10ms needs investigation. Use `PRAGMA query_only = true` for read-only connections to prevent accidental writes from read paths.

---

## Concerns & Recommendations

### Critical Issues

- **SQLite concurrent write bottleneck at scale**: WAL serializes writers. At <500 users this is invisible. At 2000+ users with concurrent briefing generation, write queuing becomes measurable. Fix: keep write transactions short (<10ms), never do I/O inside transactions, and consider Turso per-tenant sharding at 1000+ users. Rationale (DDIA Ch. 7): "long write transactions hold locks; short transactions are the foundation of high throughput."

- **Behavioral memory schema tight coupling risk**: If `memory_signals` is used directly in LLM context injection AND in briefing personalization ranking AND in UI display, it becomes the de-facto interface for three different consumers. Fix: treat `memory_signals` as internal data; expose a `GET /workspaces/:id/memory-summary` API that the UI and LLM both consume, not the raw table. Prevents schema ossification.

- **Stripe cache staleness window**: Stripe webhooks can be delayed 30–60 seconds. In that window, a user who just upgraded from Trial to Solo could be denied tasks due to stale `billing_cache`. Fix: on 429 (cap exceeded) response, do a synchronous Stripe API call to recheck subscription state before returning the error to the user. Adds 200ms latency on the error path, not the happy path.

- **OAuth token rotation**: Google OAuth access tokens expire every 3600 seconds. If the briefing cron runs at 6am and the token expired at 5:45am, the Gmail fetch fails. Fix: `oauth_tokens.token_expiry` must be checked before use; refresh logic must be atomic (UPDATE the row + invalidate any in-flight briefing that used the old token). Failure to handle this makes the Gmail integration unreliable at the first expiry boundary.

### Important Considerations

- **UUID v7 vs v4**: Use UUID v7 (time-sortable) for all primary keys. In SQLite, primary key clustering matters — sequential UUIDs (v7) reduce B-tree fragmentation compared to random UUIDs (v4). At 500 users this is negligible; at 50K it is significant. Start with v7; it costs nothing to do right from day one.

- **`PRAGMA foreign_keys = ON` per connection**: SQLite does not enforce foreign keys by default. Every connection initialization must include this pragma. In Node.js with `better-sqlite3` or `@libsql/client`, add it to the connection setup. One missed connection that skips this pragma can insert orphaned rows silently.

- **`billing_period` as a string ("2026-02")**: Do not use a DATE or TIMESTAMP for billing period. The billing period is a logical concept (Stripe's billing cycle) that may not align with calendar months. Storing it as a string (ISO month) keeps it readable and avoids timezone conversion bugs in period boundary comparisons.

- **Memory signal confidence decay**: Currently the schema has no time decay on `memory_signals`. A source that was highly engaged 6 months ago but ignored recently will still have high `signal_value`. Fix (Phase 2+): add a background job that decays signals by multiplying `confidence` by `0.9^weeks_since_last_observed`. Not needed at launch, but design the schema to support it (the fields are already there).

### Questions for Clarification

- **Turso instance model**: Single shared DB or per-user DB? This is the key operational decision. My recommendation is single shared DB at launch, but the team must decide who owns the migration to per-tenant when the time comes.
- **Briefing delivery channel state**: If a briefing delivers to Telegram AND email, does a failed Telegram delivery with successful email delivery count as delivered? The `status` column is a single value — this may need a separate `delivery_attempts` table if multi-channel delivery is required at launch.
- **Usage metering granularity**: Is one briefing = one task? Or does each source fetch count? The Business Blueprint says "500 tasks / workspace / month" for Solo tier — this needs a precise definition to write the cap enforcement correctly.

---

## References

- [Martin Kleppmann — Designing Data-Intensive Applications](https://dataintensive.net/) — Ch. 7 (transactions), Ch. 11 (derived data), Ch. 5 (replication consistency)
- [SQLite WAL Mode Documentation](https://www.sqlite.org/wal.html) — official concurrency semantics
- [SQLite Isolation Levels](https://www.sqlite.org/isolation.html) — BEGIN IMMEDIATE behavior
- [Turso libSQL Documentation](https://docs.turso.tech/) — per-tenant DB model, replication
- [Litestream — SQLite replication](https://litestream.io/) — continuous backup pattern
- [Stripe Usage-Based Billing](https://stripe.com/docs/billing/subscriptions/usage-based) — ledger pattern
- [Idempotency Keys in API Design](https://stripe.com/blog/idempotency) — Stripe engineering blog
- [UUID v7 Specification](https://www.ietf.org/archive/id/draft-peabody-dispatch-new-uuid-format-04.html) — time-sortable UUIDs
- [Anthropic Evals — LLM-as-Judge](https://github.com/anthropics/evals) — reliability measurement patterns
- DLD ADR-007 through ADR-010 — caller-writes, background fan-out, zero-read orchestrator patterns
