# Integration Map: Morning Briefing Agent

**Architecture:** Alternative B — Domain-Pure
**Date:** 2026-02-28
**Source:** All 8 personas + Architect Board synthesis

---

## External Integrations

### Source Integrations (Source Context ACL)

| Integration | Provider | Auth | Scope | Data Flow |
|------------|----------|------|-------|-----------|
| Gmail | Google API | OAuth 2.0 | `gmail.readonly` | Inbox -> GmailAdapter -> Signal |
| Google Calendar | Google API | OAuth 2.0 | `calendar.readonly` | Events -> CalendarAdapter -> Signal |
| Hacker News | HN API | None (public) | Top 30 stories | JSON -> HNAdapter -> Signal |
| RSS Feeds | Various | None (public) | User-configured URLs | XML/Atom -> RSSAdapter -> Signal |

**Gmail/Calendar OAuth Flow:**
```
User clicks "Add Gmail"
  → GET /api/v1/auth/google/start?workspaceId=ws_123
  → 302 → Google OAuth consent screen (gmail.readonly)
  → User approves
  → GET /api/v1/auth/google/callback?code=xxx&state=yyy
  → Exchange code for tokens
  → Encrypt refresh_token with AES-256-GCM
  → Store in source_oauth_tokens
  → Create source_config for gmail
  → 302 → /dashboard?sourceAdded=gmail
```

**CRITICAL: Google OAuth App Verification**
- Must submit for verification on day 31 of Phase 2
- 4-6 week external review process
- Blocks public launch (>100 users)
- Requires: privacy policy, homepage, demo video, security questionnaire
- Pre-launch: use "Testing" mode (100 user limit)

---

### Auth Integration (Identity Context)

| Integration | Provider | Method | Purpose |
|------------|----------|--------|---------|
| Authentication | Clerk | Session JWT | User identity, login, signup |
| Organizations | Clerk | Org API | Maps to workspaces (Solo=1, Pro=3) |

**Data Flow:**
```
Signup → Clerk handles → Webhook → identity_users row → WorkspaceCreated event
Login  → Clerk session → JWT in cookie → requireAuth() middleware
```

**ACL:** `infra/auth/clerk.ts` wraps all Clerk SDK calls. Domain code never imports `@clerk/*`.

---

### Payment Integration (Billing Context)

| Integration | Provider | Method | Purpose |
|------------|----------|--------|---------|
| Checkout | Stripe | Checkout Session | Trial -> Paid conversion |
| Subscriptions | Stripe | Subscription API | Solo ($99/mo), Pro ($299/mo) |
| Webhooks | Stripe | HTTP POST | Tier changes, payment failures |

**Webhook Events Handled:**

| Stripe Event | Our Action |
|-------------|------------|
| `checkout.session.completed` | Create billing_cache, update workspace tier, emit SubscriptionChanged |
| `customer.subscription.updated` | Update billing_cache + workspace tier + task_cap |
| `customer.subscription.deleted` | Mark workspace expired, emit SubscriptionChanged |
| `invoice.payment_failed` | Emit warning to Notification context |

**Idempotency:** Stripe event ID stored. Duplicate webhooks silently ignored.

**Staleness Mitigation:** On 429 (cap exceeded), synchronous Stripe API call to recheck subscription before returning error. Adds 200ms on error path only.

---

### Delivery Integrations (Notification Context)

| Integration | Provider | Method | Purpose |
|------------|----------|--------|---------|
| Telegram | Telegram Bot API | grammy.js | Primary delivery channel |
| Email | Resend | REST API | Secondary delivery channel |

**Telegram Bot Flow:**
```
User sends /start to bot
  → Telegram webhook → /api/v1/webhooks/telegram
  → Create notification_channels row (type=telegram, chat_id)
  → Reply: "Connected! Briefings at 6am."

Daily briefing ready
  → BriefingReady event → Notification context
  → Format briefing JSON → Telegram Markdown
  → Send via grammy.js
  → Record delivery_attempt
  → On success: emit DeliveryConfirmed
  → On failure: retry 3x exponential backoff → emit DeliveryFailed
```

**Email Flow:**
```
User sets email channel via API
  → Create notification_channels row (type=email, email address)
  → Send confirmation email

Daily briefing ready
  → BriefingReady event → Notification context
  → Format briefing JSON → HTML email
  → Send via Resend API
  → Record delivery_attempt
```

---

### LLM Integration (Infrastructure)

| Integration | Provider | Method | Purpose |
|------------|----------|--------|---------|
| Extraction/Triage | Anthropic (Haiku) | via LiteLLM | 80% of LLM calls, cheap |
| Synthesis | Anthropic (Sonnet) | via LiteLLM | 20% of calls, quality-critical |
| Synthesis fallback | OpenAI (GPT-4o-mini) | via LiteLLM | Provider diversity |
| Preference snapshot | Anthropic (Haiku) | via LiteLLM | Weekly background job |

**LiteLLM Config:**
```yaml
model_list:
  - model_name: "extraction"
    litellm_params:
      model: claude-haiku-4
      max_tokens: 500
  - model_name: "synthesis"
    litellm_params:
      model: claude-sonnet-4-6
      max_tokens: 2000
  - model_name: "synthesis-fallback"
    litellm_params:
      model: gpt-4o-mini
      max_tokens: 2000

router_settings:
  fallbacks: [{"synthesis": ["synthesis-fallback"]}]
  allowed_fails: 1
  cooldown_time: 30
```

**Cost Tracking:** LiteLLM emits `usage` metadata per response. Stored in briefing row (`llm_tokens_in`, `llm_tokens_out`, `llm_cost_usd`).

**Hard Caps:** Per-user monthly budget $25 via LiteLLM budget_manager. At 80%: warning in briefing. At 100%: pause generation.

---

### Monitoring Integrations (Operations)

| Integration | Provider | Method | Purpose |
|------------|----------|--------|---------|
| Cron monitoring | Healthchecks.io | HEAD ping | Dead man's switch for BullMQ |
| Structured logs | Grafana Loki | Pino output | Centralized log search |
| Metrics | Prometheus | Fly.io metrics | System metrics |
| Backup | Litestream | Continuous | SQLite -> S3/Tigris |

**Dead Man's Switch:**
```
BullMQ daily job completes
  → fetch(HEARTBEAT_URL, { method: 'HEAD' })
  → Healthchecks.io records ping

If no ping within 45-minute grace period:
  → Healthchecks.io alerts (email/Telegram)
  → Founder investigates
```

---

## Internal Data Flow (End-to-End Briefing Pipeline)

```
[BullMQ Scheduler] triggers at delivery_time per timezone
    │
    ▼
[Workspace Context] — cap check (BEGIN IMMEDIATE)
    │ ok? ──→ [Usage Ledger] increment
    │ exceeded? ──→ 429, emit TaskCapReached
    ▼
[Source Context] — parallel fetch (Promise.allSettled)
    │ Per source: ACL adapter → external API → Signal
    │ Store: briefing_sources row per source
    ▼
[Briefing Context] — extraction (Haiku, parallel per source)
    │ Signal → SourceItem (structured JSON)
    │ Partial success OK: min 1 source needed
    ▼
[Priority Context] — load preference snapshot (~300 tokens)
    │ memory_signals → compact_text for LLM injection
    ▼
[Briefing Context] — synthesis (Sonnet, single call)
    │ Input: structured items + prefs + system prompt (~6K tokens)
    │ Output: BriefingOutput JSON
    │ Validate: Zod schema, retry once on failure
    ▼
[Briefing Context] — store
    │ Insert briefing row (content_json + reliability fields)
    │ Insert briefing_sources rows (lineage)
    ▼
[Notification Context] — deliver
    │ BriefingReady event → format per channel → send
    │ Telegram: grammy.js → delivery_attempt row
    │ Email: Resend → delivery_attempt row
    ▼
[Briefing Context] — finalize
    │ DeliveryConfirmed → status: delivered
    │ Ping heartbeat (dead man's switch)
    ▼
[User] reads briefing
    │ Opens/clicks/dismisses items
    ▼
[Briefing Context] — capture feedback
    │ Insert briefing_feedback rows
    ▼
[Priority Context] — update memory (async, batched)
    │ BriefingEngaged event → UPSERT memory_signals
    │ Weekly: regenerate preference_snapshot via Haiku
```

---

## Integration Risk Matrix

| Integration | Risk | Impact | Mitigation |
|------------|------|--------|------------|
| Google OAuth verification | 4-6 week delay | Blocks public launch | Start day 31, privacy policy ready day 30 |
| Google OAuth token expiry | Token expires every 3600s | Failed Gmail/Calendar fetch | Check expiry before use, auto-refresh |
| Fly.io restart during briefing | Machine restarts mid-job | Missed briefing | BullMQ persistence + idempotency key |
| Stripe webhook delay | 30-60 second staleness | User denied after upgrade | Sync Stripe check on 429 error path |
| Telegram API downtime | Bot API unavailable | Missed delivery | Retry 3x + email fallback |
| Anthropic API outage | Primary LLM unavailable | No synthesis | GPT-4o-mini fallback via LiteLLM |
| Resend free tier limit | 3K emails/month | Email delivery blocked | Monitor usage, upgrade at 2K |

---

## Circuit Breaker Pattern

```typescript
import CircuitBreaker from 'opossum';

// Per-source circuit breakers
const gmailBreaker = new CircuitBreaker(gmailAdapter.fetch, {
  timeout: 10_000,        // 10s timeout per fetch
  errorThresholdPercentage: 50,
  resetTimeout: 60_000,   // Try again after 1 min
});

// Each source failure = degraded briefing, NOT failed briefing
// Minimum viable briefing = any 1 source + calendar
gmailBreaker.on('open', () => {
  domainBus.emit('source:health-degraded', { sourceId: 'gmail', workspaceId });
});
```
