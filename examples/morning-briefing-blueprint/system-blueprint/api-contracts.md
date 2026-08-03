# API Contracts: Morning Briefing Agent

**Architecture:** Alternative B — Domain-Pure
**Date:** 2026-02-28
**Source:** Domain + LLM + Security research + Architect Board synthesis

---

## API Design Principles

1. **Workspace-scoped:** All resource endpoints under `/api/v1/workspaces/{workspaceId}/...`
2. **Self-describing errors:** Every error has `code`, `message`, `action` fields
3. **Agent-friendly:** An agent can configure and trigger briefings using only the OpenAPI spec
4. **Context boundaries respected:** Each API module maps to one bounded context

---

## Auth Model

**Provider:** Clerk (free tier, 10K MAU)

| Aspect | Decision |
|--------|----------|
| Authentication | Clerk session JWT, verified per-request |
| Authorization | Workspace ownership check: `clerk_user_id` matches workspace owner |
| Middleware | `requireAuth()` -> `requireWorkspaceAccess(workspaceId)` |
| IDOR prevention | Every query: `WHERE workspace_id = ? AND verified_owner` |
| OAuth CSRF | Cryptographically random state param, server-side validation, 10-min expiry, one-time use |

---

## Error Contract

```typescript
interface APIError {
  code: string;           // "BRIEFING_SOURCE_UNAVAILABLE"
  message: string;        // "Source 'gmail' authentication expired"
  action: string;         // "Re-authenticate at /api/auth/gmail"
  retry_after_seconds: number | null;
}
```

**Standard Error Codes:**

| Code | HTTP | When |
|------|------|------|
| TASK_CAP_EXCEEDED | 429 | Monthly task limit reached |
| WORKSPACE_NOT_FOUND | 404 | Invalid workspace ID |
| WORKSPACE_TRIAL_EXPIRED | 403 | Trial ended, no subscription |
| SOURCE_AUTH_EXPIRED | 401 | OAuth token needs refresh |
| BRIEFING_NOT_FOUND | 404 | Invalid briefing ID |
| BRIEFING_IN_PROGRESS | 409 | Compilation already running |
| CHANNEL_NOT_CONFIRMED | 400 | Delivery channel not verified |
| RATE_LIMITED | 429 | Too many API requests |

---

## Endpoints by Context

### Workspace Context

```yaml
# Workspace management
GET    /api/v1/workspaces
  → WorkspaceList
  # List all workspaces for current user

POST   /api/v1/workspaces
  ← { name: string }
  → Workspace
  # Create workspace (Solo: max 1, Pro: max 3)

GET    /api/v1/workspaces/{workspaceId}
  → Workspace { id, name, tier, taskCap, tasksUsed, trialEndsAt }

GET    /api/v1/workspaces/{workspaceId}/usage
  → UsageSummary { tasksConsumed, taskCap, billingPeriod, daysRemaining }
```

### Source Context

```yaml
# Source management
GET    /api/v1/workspaces/{workspaceId}/sources
  → SourceConfig[]
  # List active sources for workspace

POST   /api/v1/workspaces/{workspaceId}/sources
  ← { sourceType: "rss" | "hackernews" | "gmail" | "google_calendar", config: {...} }
  → SourceConfig
  # Add new source (creates new version)

DELETE /api/v1/workspaces/{workspaceId}/sources/{sourceId}
  → { deactivated: true }
  # Soft-delete (deactivate) source

GET    /api/v1/workspaces/{workspaceId}/sources/{sourceId}/health
  → SourceHealth { status: "healthy" | "degraded" | "error", lastSuccess, errorCount }

# Source registry (agent-friendly, no auth required)
GET    /api/v1/source-types
  → SourceDefinition[] { id, displayName, description, supportsCustomFilter, configSchema }
```

### OAuth Flow (Source Context / Identity Context)

```yaml
# OAuth initiation
GET    /api/v1/auth/google/start?workspaceId={id}&scopes=gmail.readonly,calendar.readonly
  → 302 Redirect to Google OAuth
  # State param: crypto random, server-side, 10-min TTL, one-time use

# OAuth callback
GET    /api/v1/auth/google/callback?code={code}&state={state}
  → 302 Redirect to /dashboard?sourceAdded=gmail
  # Exchanges code, encrypts tokens, stores in source_oauth_tokens
```

### Priority Context

```yaml
# Declared priorities
GET    /api/v1/workspaces/{workspaceId}/priorities
  → DeclaredPriority[]

POST   /api/v1/workspaces/{workspaceId}/priorities
  ← { type: "topic" | "person" | "project", value: string }
  → DeclaredPriority

DELETE /api/v1/workspaces/{workspaceId}/priorities/{priorityId}
  → { removed: true }

# Preferences
GET    /api/v1/workspaces/{workspaceId}/preferences
  → Preference[] { key, value }

PUT    /api/v1/workspaces/{workspaceId}/preferences/{key}
  ← { value: string }
  → Preference

# Memory summary (read-only, for UI + agent consumption)
GET    /api/v1/workspaces/{workspaceId}/memory-summary
  → MemorySummary { highPrioritySources, mutedSources, favoriteTags, compactText }
  # Exposed via API, not raw memory_signals table
```

### Briefing Context

```yaml
# Briefing management
GET    /api/v1/workspaces/{workspaceId}/briefings
  ?status=delivered&limit=10
  → Briefing[]

GET    /api/v1/workspaces/{workspaceId}/briefings/{briefingId}
  → Briefing { id, status, contentJson, deliveredAt, cost, sourceCount }

POST   /api/v1/workspaces/{workspaceId}/briefings/compile
  → { briefingId: string, status: "scheduled" }
  # Manual trigger (counts against task cap)

# Feedback capture
POST   /api/v1/workspaces/{workspaceId}/briefings/{briefingId}/feedback
  ← { type: "opened" | "item_clicked" | "item_dismissed" | "full_read" | "skipped", itemRef?: string }
  → { recorded: true }
```

### Notification Context

```yaml
# Channel management
GET    /api/v1/workspaces/{workspaceId}/channels
  → Channel[]

POST   /api/v1/workspaces/{workspaceId}/channels
  ← { type: "telegram" | "email", config: { chatId | email } }
  → Channel

DELETE /api/v1/workspaces/{workspaceId}/channels/{channelId}
  → { removed: true }

# Telegram webhook (from Telegram API)
POST   /api/v1/webhooks/telegram
  ← TelegramUpdate
  # Bot command handling (/start, /stop, /briefing)
```

### Billing Context

```yaml
# Subscription management
GET    /api/v1/workspaces/{workspaceId}/subscription
  → Subscription { tier, status, periodEnd }

POST   /api/v1/workspaces/{workspaceId}/subscribe
  ← { tier: "solo" | "pro" }
  → { checkoutUrl: string }
  # Creates Stripe Checkout session

# Stripe webhook
POST   /api/v1/webhooks/stripe
  ← StripeEvent
  # Handles: checkout.session.completed, customer.subscription.updated/deleted
  # Updates billing_cache + workspace tier atomically
```

### Tag Vocabulary (Agent-friendly)

```yaml
GET    /api/v1/tags
  → TagDefinition[] { id, displayName, relatedTags }
  # Controlled vocabulary for source extraction
  # Agent uses this to understand tag space
```

---

## Webhook Contracts

### Stripe Webhooks (incoming)

| Event | Handler | Action |
|-------|---------|--------|
| `checkout.session.completed` | Billing | Create billing_cache, update workspace tier |
| `customer.subscription.updated` | Billing | Update billing_cache + workspace.tier + task_cap |
| `customer.subscription.deleted` | Billing | Mark workspace as expired |
| `invoice.payment_failed` | Billing | Send warning via Notification |

**Idempotency:** Stripe event ID stored. Duplicate webhooks ignored.

### Telegram Webhooks (incoming)

| Command | Handler | Action |
|---------|---------|--------|
| `/start` | Notification | Register chat_id to workspace channel |
| `/stop` | Notification | Deactivate Telegram channel |
| `/briefing` | Briefing | Trigger manual compilation |
| `/settings` | Priority | Show current preferences inline |

---

## API Versioning

**Strategy:** URL versioning (`/api/v1/...`). Content JSON schema versioned via `content_schema_version` field.

**Rule:** Additive-only changes for first 90 days. No breaking changes to existing fields. New fields added with backwards-compatible defaults.

---

## Rate Limiting

| Endpoint Group | Limit | Window |
|---------------|-------|--------|
| Read endpoints | 100 req | 1 min |
| Write endpoints | 20 req | 1 min |
| Compile trigger | 5 req | 1 hour |
| Feedback capture | 50 req | 1 min |
| Webhooks | No limit | — |
