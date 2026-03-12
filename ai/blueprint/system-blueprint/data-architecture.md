# Data Architecture: Morning Briefing Agent

**Architecture:** Alternative B — Domain-Pure
**Date:** 2026-02-28
**Source:** Data Architect (Martin) research + Architect Board synthesis

---

## Storage Strategy

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Primary | SQLite WAL on Fly.io persistent volume | Zero server. Microsecond reads. Single-writer serialization at <1ms per write. Sufficient for <2000 users |
| Backup | Litestream -> S3/Tigris | Continuous replication. Point-in-time recovery at 1-second granularity. ~$5/month |
| Future | Turso (per-tenant sharding) | At 500+ users or multi-region need. Schema pre-designed for migration (workspace_id on every table) |

**Critical SQLite Configuration:**
```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;          -- MUST be set per-connection
PRAGMA busy_timeout = 5000;        -- 5s wait on write lock
PRAGMA wal_autocheckpoint = 100;   -- tighter checkpoint control
```

---

## System of Record Map

| Entity | SoR | Consistency | Notes |
|--------|-----|-------------|-------|
| User identity | Clerk | External | Our DB stores only `clerk_user_id` as FK |
| Workspace | Our SQLite | Strong | Owns tier, caps, settings |
| Preferences (explicit) | Our SQLite | Strong | User-authored, user-editable |
| Memory signals (learned) | Our SQLite | Eventual | System-derived from feedback events |
| Source configs | Our SQLite | Strong | Versioned rows, soft-delete |
| OAuth tokens | Our SQLite | Strong | AES-256-GCM encrypted at rest |
| Briefings | Our SQLite | Strong | Immutable once delivered |
| Usage ledger | Our SQLite | Strong | Append-only, idempotency key |
| Billing state | Stripe | External | Local `billing_cache` via webhook |

---

## Schema by Context

### Workspace Context Tables

```sql
-- workspaces: product-level tenant unit
-- SoR: our DB (not Clerk)
-- Naming: workspace_* prefix
CREATE TABLE workspace_workspaces (
    id              TEXT PRIMARY KEY,        -- UUID v7 (time-sortable)
    clerk_org_id    TEXT,                    -- NULL for Solo tier
    clerk_user_id   TEXT NOT NULL,           -- owner
    name            TEXT NOT NULL,
    tier            TEXT NOT NULL CHECK (tier IN ('trial', 'solo', 'pro')),
    trial_ends_at   TIMESTAMPTZ,            -- NULL after conversion
    task_cap_monthly INTEGER NOT NULL,       -- 50 trial / 500 solo / 2000 pro
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One workspace per Solo user
CREATE UNIQUE INDEX idx_workspace_solo_user
    ON workspace_workspaces(clerk_user_id)
    WHERE tier IN ('trial', 'solo');

-- Usage ledger: append-only. Never UPDATE, never DELETE.
CREATE TABLE workspace_usage_ledger (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    event_type      TEXT NOT NULL CHECK (event_type IN (
                        'task_consumed',
                        'task_reversed',
                        'cap_reset'
                    )),
    amount          INTEGER NOT NULL DEFAULT 1,
    idempotency_key TEXT NOT NULL UNIQUE,
    briefing_id     TEXT,
    billing_period  TEXT NOT NULL,           -- "2026-02" (YYYY-MM)
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usage_ledger_workspace_period
    ON workspace_usage_ledger(workspace_id, billing_period, occurred_at);

-- Materialized view for fast cap checks
CREATE TABLE workspace_usage_summary (
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    billing_period  TEXT NOT NULL,
    tasks_consumed  INTEGER NOT NULL DEFAULT 0,
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, billing_period)
);
```

### Billing Context Tables

```sql
-- billing_cache: read replica from Stripe webhooks
-- SoR: Stripe. This is explicitly a cache.
CREATE TABLE billing_cache (
    workspace_id        TEXT PRIMARY KEY REFERENCES workspace_workspaces(id),
    stripe_customer_id  TEXT NOT NULL,
    stripe_sub_id       TEXT,
    current_tier        TEXT NOT NULL,
    period_start        TIMESTAMPTZ,
    period_end          TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Identity Context Tables

```sql
-- Minimal: just the mapping. Clerk owns all identity data.
CREATE TABLE identity_users (
    id              TEXT PRIMARY KEY,        -- our internal user ID
    clerk_user_id   TEXT NOT NULL UNIQUE,    -- Clerk's ID
    email           TEXT NOT NULL,           -- cached from Clerk for display
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Source Context Tables

```sql
-- Source configurations: versioned with soft-delete
CREATE TABLE source_configs (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    source_type     TEXT NOT NULL CHECK (source_type IN (
                        'rss', 'hackernews', 'twitter_list',
                        'gmail', 'google_calendar', 'custom_url'
                    )),
    config_json     TEXT NOT NULL,           -- JSON: {url, filters, keywords}
    version         INTEGER NOT NULL DEFAULT 1,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deactivated_at  TIMESTAMPTZ
);

CREATE INDEX idx_source_configs_workspace_active
    ON source_configs(workspace_id, is_active, source_type);

-- OAuth tokens: separate table, separate access path
-- AES-256-GCM encrypted at application layer
CREATE TABLE source_oauth_tokens (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    provider        TEXT NOT NULL CHECK (provider IN ('google', 'microsoft')),
    access_token_enc TEXT NOT NULL,
    refresh_token_enc TEXT NOT NULL,
    token_expiry    TIMESTAMPTZ NOT NULL,
    scopes          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_oauth_tokens_workspace_provider
    ON source_oauth_tokens(workspace_id, provider);
```

### Priority Context Tables

```sql
-- Explicit preferences: user-authored, user-editable
CREATE TABLE priority_preferences (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    pref_key        TEXT NOT NULL,
    pref_value      TEXT NOT NULL,           -- JSON-encoded
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by      TEXT NOT NULL DEFAULT 'user' CHECK (updated_by IN ('user', 'system'))
);

CREATE UNIQUE INDEX idx_preferences_workspace_key
    ON priority_preferences(workspace_id, pref_key);

-- Behavioral memory: system-learned signals
CREATE TABLE priority_memory_signals (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    signal_type     TEXT NOT NULL CHECK (signal_type IN (
                        'source_engagement',
                        'topic_interest',
                        'sender_priority',
                        'time_sensitivity',
                        'dismissed_topic'
                    )),
    signal_key      TEXT NOT NULL,
    signal_value    REAL NOT NULL,           -- normalized 0.0-1.0
    confidence      REAL NOT NULL DEFAULT 0.0,
    observation_count INTEGER NOT NULL DEFAULT 1,
    last_observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_memory_signals_workspace_type_key
    ON priority_memory_signals(workspace_id, signal_type, signal_key);

-- Preference snapshots: compressed for LLM injection
CREATE TABLE priority_snapshots (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    high_priority_sources TEXT NOT NULL,     -- JSON array
    muted_sources   TEXT NOT NULL,           -- JSON array
    urgent_senders  TEXT NOT NULL,           -- JSON array
    favorite_tags   TEXT NOT NULL,           -- JSON array
    compact_text    TEXT NOT NULL,           -- max 300 chars, for LLM injection
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Briefing Context Tables

```sql
-- Briefings: state machine + reliability measurement
-- IMMUTABLE once status = 'delivered'
CREATE TABLE briefing_briefings (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    scheduled_for   TIMESTAMPTZ NOT NULL,
    timezone        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN (
                        'scheduled', 'fetching_sources', 'synthesizing',
                        'delivering', 'delivered', 'failed', 'cancelled'
                    )),
    status_updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    failure_reason  TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    content_schema_version INTEGER NOT NULL DEFAULT 1,
    content_json    TEXT,                    -- structured JSON (see schema below)
    word_count      INTEGER,
    item_count      INTEGER,
    source_count    INTEGER,
    -- Reliability measurement fields
    has_all_sections    INTEGER,
    all_items_have_sources INTEGER,
    delivery_latency_ms INTEGER,
    synthesis_duration_ms INTEGER,
    llm_model_used  TEXT,
    llm_tokens_in   INTEGER,
    llm_tokens_out  INTEGER,
    llm_cost_usd    REAL,
    -- Timestamps
    fetching_started_at  TIMESTAMPTZ,
    synthesizing_started_at TIMESTAMPTZ,
    delivered_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_briefings_workspace_status
    ON briefing_briefings(workspace_id, status, scheduled_for);
CREATE INDEX idx_briefings_scheduled
    ON briefing_briefings(scheduled_for, status) WHERE status = 'scheduled';

-- Source lineage per briefing
CREATE TABLE briefing_sources (
    id              TEXT PRIMARY KEY,
    briefing_id     TEXT NOT NULL REFERENCES briefing_briefings(id),
    source_config_id TEXT NOT NULL REFERENCES source_configs(id),
    source_type     TEXT NOT NULL,
    items_fetched   INTEGER NOT NULL DEFAULT 0,
    items_used      INTEGER NOT NULL DEFAULT 0,
    fetch_duration_ms INTEGER,
    fetch_status    TEXT NOT NULL CHECK (fetch_status IN ('ok', 'timeout', 'error', 'empty')),
    error_detail    TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_briefing_sources_briefing ON briefing_sources(briefing_id);

-- Briefing feedback: raw input to behavioral memory
CREATE TABLE briefing_feedback (
    id              TEXT PRIMARY KEY,
    briefing_id     TEXT NOT NULL REFERENCES briefing_briefings(id),
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    feedback_type   TEXT NOT NULL CHECK (feedback_type IN (
                        'opened', 'item_clicked', 'item_dismissed',
                        'full_read', 'skipped'
                    )),
    item_ref        TEXT,                    -- JSON ref to specific item
    source_id       TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_briefing_feedback_workspace
    ON briefing_feedback(workspace_id, occurred_at);
```

### Notification Context Tables

```sql
-- Delivery channels per workspace
CREATE TABLE notification_channels (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspace_workspaces(id),
    channel_type    TEXT NOT NULL CHECK (channel_type IN ('telegram', 'email', 'web_push')),
    config_json     TEXT NOT NULL,           -- {chat_id, email, push_subscription}
    is_confirmed    INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_channels_workspace
    ON notification_channels(workspace_id, channel_type);

-- Delivery attempts per briefing per channel
CREATE TABLE notification_delivery_attempts (
    id              TEXT PRIMARY KEY,
    briefing_id     TEXT NOT NULL REFERENCES briefing_briefings(id),
    channel_id      TEXT NOT NULL REFERENCES notification_channels(id),
    status          TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
    attempt_number  INTEGER NOT NULL DEFAULT 1,
    error_detail    TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_delivery_attempts_briefing
    ON notification_delivery_attempts(briefing_id);
```

---

## Briefing Content JSON Schema

```json
{
  "schema_version": 1,
  "title": "Morning Briefing — Friday, Feb 28",
  "generated_at": "2026-02-28T06:00:12Z",
  "sections": [
    {
      "type": "tech_news | email_triage | calendar | projects | custom",
      "title": "Tech News",
      "items": [
        {
          "id": "uuid",
          "headline": "OpenAI ships agents API",
          "summary": "Two sentence summary...",
          "relevance_score": 0.87,
          "source": {
            "source_config_id": "uuid",
            "source_type": "hackernews",
            "original_url": "https://...",
            "source_title": "Hacker News"
          },
          "priority": "high | medium | low",
          "is_actionable": false,
          "why_relevant": "Matches your priority: AI agent tooling"
        }
      ]
    }
  ],
  "action_items": [
    {
      "item_ref": 3,
      "action_type": "reply | review | attend | decide",
      "deadline": "2026-02-28T10:00:00Z",
      "description": "Reply to investor email from John"
    }
  ],
  "meta": {
    "total_sources_fetched": 8,
    "total_items_considered": 127,
    "total_items_included": 18,
    "personalization_signals_used": 14,
    "estimated_read_time_seconds": 180
  }
}
```

**Why structured JSON (not Markdown):**
1. Deterministic reliability checks (zero LLM cost)
2. Source lineage: every item has `source_config_id`
3. LLM-as-judge targets specific fields, not freeform blob
4. Same JSON renders to Telegram, email, web without re-generation

---

## Cross-Context Data Rules

**CRITICAL: No direct SQL JOINs across context prefixes.**

| Rule | Enforcement |
|------|------------|
| No cross-context JOINs | Contexts communicate via domain events (in-process function calls at monolith scale) |
| Table naming: `{context}_*` | `briefing_*`, `source_*`, `priority_*`, `workspace_*`, `notification_*`, `billing_*`, `identity_*` |
| `workspace_id` on every table | Enables future Turso per-tenant sharding with zero data model changes |
| UUID v7 primary keys | Time-sortable, reduces B-tree fragmentation |

---

## Hard Cap Enforcement (Atomic)

```sql
-- BEFORE starting a briefing task:
BEGIN IMMEDIATE;  -- SQLite WAL: acquires write lock immediately

SELECT u.tasks_consumed, w.task_cap_monthly
FROM workspace_usage_summary u
JOIN workspace_workspaces w ON w.id = u.workspace_id
WHERE u.workspace_id = ? AND u.billing_period = ?;

-- If tasks_consumed >= task_cap_monthly: ROLLBACK, return 429
-- Else:
INSERT INTO workspace_usage_ledger (id, workspace_id, event_type, amount, idempotency_key, billing_period, briefing_id)
VALUES (?, ?, 'task_consumed', 1, ?, ?, ?);

UPDATE workspace_usage_summary
SET tasks_consumed = tasks_consumed + 1, last_updated_at = CURRENT_TIMESTAMP
WHERE workspace_id = ? AND billing_period = ?;

COMMIT;
```

---

## Behavioral Memory: Running Average Update

```sql
-- UPSERT on priority_memory_signals:
INSERT INTO priority_memory_signals (id, workspace_id, signal_type, signal_key, signal_value, confidence, observation_count, last_observed_at)
VALUES (?, ?, ?, ?, ?, 0.05, 1, CURRENT_TIMESTAMP)
ON CONFLICT (workspace_id, signal_type, signal_key) DO UPDATE SET
    signal_value = (priority_memory_signals.signal_value * priority_memory_signals.observation_count + excluded.signal_value) / (priority_memory_signals.observation_count + 1),
    confidence = MIN(1.0, priority_memory_signals.confidence + 0.05),
    observation_count = priority_memory_signals.observation_count + 1,
    last_observed_at = CURRENT_TIMESTAMP;
```

After ~20 observations, confidence reaches 1.0 and signal stabilizes.

---

## Consistency Models

| Operation | Scope | Pattern | Justification |
|-----------|-------|---------|---------------|
| Cap check + usage increment | Single SQLite transaction (BEGIN IMMEDIATE) | ACID | Lost-update = exceeded caps = revenue impact |
| Briefing state transitions | Single row UPDATE | ACID (implicit) | State machine consistency |
| Source fetch + briefing_sources | Non-transactional (multiple small writes) | Best-effort | External I/O between steps |
| Memory signal update | UPSERT single row | ACID | Concurrent updates would skew average |
| Stripe webhook processing | Transaction wrapping billing_cache + workspaces | ACID | Tier change must be atomic |
| Feedback logging | Fire-and-forget INSERT | Eventual | Low-priority, high-volume |

**CAP Trade-off:**
- **CP for usage caps** — if DB unreachable, halt briefings (unbounded LLM cost otherwise)
- **AP for delivery** — deliver even if status write fails (retry later)

---

## Migration Strategy

**Approach:** Expand-Contract. SQLite limitations respected.

1. **Expand:** Add new column with DEFAULT or NULL
2. **Deploy:** Both old and new columns populated
3. **Backfill:** Background job fills nulls
4. **Contract:** Remove old column after verification

**Tooling:** drizzle-kit. Migration SQL committed to git. CI/CD only applies.

**Rule:** Zero-downtime via off-peak deploys (10pm-4am UTC, no briefings running). Never ALTER TABLE during briefing window.

---

## Data Retention

| Data | Retention | Reason |
|------|-----------|--------|
| briefing_feedback | 90 days | Memory signals derived; raw events for recomputation |
| briefing content_json | 30 days | User-accessible history |
| usage_ledger | 1 year minimum | Billing audit trail |
| priority_memory_signals | Indefinite | The moat |
| Signals (raw ingested) | 48 hours | Only recent info relevant |
