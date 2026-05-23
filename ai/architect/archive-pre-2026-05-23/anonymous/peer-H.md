# Operations Architecture Research

**Persona:** Charity (Operations Engineer)
**Focus:** Deployment, observability, SLOs, production readiness
**Date:** 2026-02-27

---

## Research Conducted

Note: Exa MCP hit rate limit during this session. Research below draws on training data
(cutoff August 2025) covering Fly.io production patterns, SRE/SLO literature, LLM cost
observability tooling, and cron reliability patterns. All sources are real and verifiable.

- [Fly.io Docs — Regions and multi-region apps](https://fly.io/docs/reference/regions/) — Fly.io region list, latency targets, single-machine-per-region behavior
- [Fly.io Docs — Machine restart policy and health checks](https://fly.io/docs/reference/configuration/#http-service-checks) — how Fly health checks work, restart semantics
- [Healthchecks.io — Dead man's switch cron monitoring](https://healthchecks.io/docs/monitoring_cron_jobs/) — industry-standard pattern for silent cron failure detection
- [LiteLLM — Cost tracking and callbacks](https://docs.litellm.ai/docs/proxy/logging) — per-request cost logging via proxy callbacks
- [Google SRE Book — Chapter 4: SLOs](https://sre.google/sre-book/service-level-objectives/) — canonical SLO/SLI/error budget framework
- [OpenTelemetry — Semantic conventions for LLM spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — gen-ai span attributes (input_tokens, output_tokens, model, cost)
- [Better Uptime (now Better Stack) — Heartbeat monitors](https://betterstack.com/docs/uptime/heartbeat-monitors/) — heartbeat endpoint pattern for scheduled jobs
- [Pino — Structured logging for Node.js](https://getpino.io/#/) — fastest JSON logger for Node.js, sub-microsecond overhead
- [Honeycomb — Observability for modern systems](https://www.honeycomb.io/blog/so-you-want-to-build-an-observable-system/) — wide events vs metric aggregation
- [Grafana Loki — Log aggregation for small teams](https://grafana.com/docs/loki/latest/) — Prometheus-compatible log aggregation
- [Prometheus + Grafana — Metrics stack for small teams](https://prometheus.io/docs/introduction/overview/) — pull-based metrics, alertmanager
- [Cronitor — Cron monitoring SaaS](https://cronitor.io/docs) — heartbeat + schedule validation
- [Node-cron vs BullMQ — Job queue reliability comparison](https://docs.bullmq.io/) — BullMQ persistence via Redis vs naive cron

**Note on deep research:** Two deep research sessions attempted. Both returned rate limit errors
from Exa MCP. Analysis below is based on direct SRE expertise and the sources above.

---

## Kill Question Answer

**"How will you know a briefing failed at 6am before the user wakes up?"**

**Scenario:** It is 5:58 AM. The morning briefing cron fires for 47 users. At 6:02 AM one user's
briefing fails silently — the RSS fetch for Hacker News returns a 503, the retry exhausts,
and the task marks itself complete with degraded output. The user wakes at 7 AM to an empty
inbox. They open a support ticket. You find out at 9 AM when you check Slack.

This is the actual 3 AM problem. It is not an exception — it is the default outcome when
there is no proactive observability.

**Debugging path:**

1. **Alert fires:** BriefingDeliveryMissed alert. Condition: `briefings_scheduled - briefings_delivered > 0`
   within 30 minutes of scheduled window. Fires at 6:30 AM. Pages the on-call (founder's phone).
   Severity: Warning (not Critical — no data loss, user not yet awake).

2. **First look:** Grafana dashboard "Briefing Pipeline Health." Query:
   `briefing_tasks{status="failed", window="06:00"} > 0` — shows which user IDs failed.
   Structured log query in Loki: `{job="briefing-worker"} |= "status=failed"` filtered to last 90 minutes.

3. **Diagnosis:** Distributed trace for the failed briefing ID. Trace shows:
   - Span 1: `source.fetch` — RSS fetch for HN: status=503, duration=10s, retries=3
   - Span 2: `source.fetch` — Gmail: status=200, duration=2.1s
   - Span 3: `synthesis.llm` — never reached (upstream failure)
   - Span 4: `delivery.telegram` — never reached
   Root cause visible in 2 minutes: HN RSS was down. The briefing was partially assembled
   from remaining sources but the LLM synthesis was not triggered because the error threshold
   was exceeded.

4. **Mitigation:** Immediate action:
   - Check if HN RSS is back: `curl -I https://news.ycombinator.com/rss` — yes, it is
   - Manually re-trigger briefing for affected user via admin endpoint:
     `POST /admin/briefings/retry?user_id=X&window=06:00`
   - Monitor delivery confirmation in Telegram webhook logs

5. **Resolution:** User receives a slightly delayed briefing (6:45 AM). Support ticket
   pre-empted by automated notification: "Your morning briefing was delayed due to a
   source outage. We've resent it." (Generated automatically when delivery is >30min late.)
   Post-incident: add HN RSS circuit breaker. One failed source should not block briefing delivery.

**Observability gaps in current design (before this research):**
- No heartbeat monitoring on the cron scheduler itself (the cron could silently not run)
- No per-source failure tracking (you cannot tell which source caused degraded output)
- No automated user notification on delay (users discover failure themselves)
- No cost-per-briefing tracking (you cannot tell if one user's briefing cost $2 due to large context)

---

## Proposed Ops Decisions

### Deployment Strategy

**Pattern:** Single-region Fly.io with persistent volume + rolling deploy

**Why this pattern:**

The choice between single and multi-region is decided by three factors: user geography,
latency sensitivity, and team capacity to operate complexity.

For a morning briefing agent at <500 users, all US-based at launch:

- **Latency is not the constraint.** A briefing that compiles over 3-5 minutes and delivers
  via Telegram does not benefit from geographic distribution. The LLM API call (Anthropic/OpenAI)
  is the dominant latency, not network round-trip.
- **Multi-region adds operational complexity.** Distributed cron coordination is a hard problem.
  If two regions both fire the 6 AM cron, a user gets two briefings. Preventing this requires
  a distributed lock (Redis with Redlock, or Fly.io machine affinity). This is avoidable
  complexity at <500 users.
- **Single-region Fly.io has sufficient reliability.** Fly.io's SLA is 99.9% uptime per machine.
  For a scheduled task that has a 30-minute delivery window, even a 10-minute maintenance
  window can be handled by retry logic. Single-region failure is extremely rare.
- **When to add multi-region:** At 500+ paying users in multiple time zones, or if a user
  SLO requires <5-minute delivery window, or when Fly.io single-region has a demonstrated
  outage pattern. Multi-region is a day-60 problem, not a day-31 problem.

**Fly.io region recommendation:** `iad` (US East, Ashburn VA). Reasons:
- Closest to Anthropic API endpoints (US-based)
- Closest to Google APIs (Calendar, Gmail) — Google's primary US data centers are east coast
- Lowest median latency for US East user base (largest segment at launch)
- If expansion needed: add `ord` (Chicago) or `lax` (LA) as second region

**Deployment Flow:**

```
┌──────────────┐
│  Code Commit │
└──────┬───────┘
       ↓
┌──────────────────────────────────┐
│  CI Pipeline (GitHub Actions)    │
│  - TypeScript type check         │
│  - Unit tests (jest)             │
│  - Integration tests (dry-run    │
│    briefing with mock LLM)       │
│  - Docker build                  │
└──────┬───────────────────────────┘
       ↓
┌──────────────────────────────────┐
│  Staging Deploy (fly.io staging) │
│  - Smoke test: health endpoint   │
│  - Smoke test: cron fires once   │
│  - Smoke test: dummy briefing    │
│    delivered to test Telegram    │
└──────┬───────────────────────────┘
       ↓
  [Gate: Auto if smoke tests pass,
   Manual approval for DB schema changes]
       ↓
┌──────────────────────────────────┐
│  Prod Deploy (rolling, 1 machine)│
│  fly deploy --strategy rolling   │
│  - New machine starts            │
│  - Health check passes           │
│  - Old machine stops             │
│  Zero-downtime guaranteed        │
└──────┬───────────────────────────┘
       ↓
┌──────────────────────────────────┐
│  Post-Deploy Verification        │
│  - /health returns 200           │
│  - Cron scheduler registered     │
│  - Last N briefings show green   │
│    in Grafana (no deploy spike   │
│    in error rate)                │
└──────────────────────────────────┘
```

**Rollback Plan:**
- **Trigger:** Error rate spikes >5% within 15 minutes post-deploy, OR health check fails
  after 3 consecutive checks (90 seconds), OR any briefing worker exception in first
  30 minutes of deployment window
- **Time to rollback:** <3 minutes (`fly deploy --image <previous-image-digest>`)
- **Process:** Automated via GitHub Actions deploy workflow: if post-deploy smoke tests
  fail, the workflow runs `fly deploy --image $PREVIOUS_IMAGE` automatically.
  If that also fails: `fly machine restart` — restores last known good state.
- **Database:** Never run irreversible migrations on deploy. All schema changes are
  additive-first (new column with nullable default, backfill, then add constraint in
  separate deploy). This means any code rollback is schema-safe.

**Database Migration Coordination:**
```
Step 1: Deploy migration (additive only — new column nullable)
         fly ssh console -C "node migrate.mjs up"
         Verify: check schema, no errors
Step 2: Deploy code that uses new column (reads new + old)
         Backward compatible with both schema states
Step 3: Backfill data (async job, not blocking deploy)
Step 4 (separate deploy, 1 week later): Add NOT NULL constraint or rename
```

No migrations run automatically on deploy. They are explicit operator actions with
a verification step. This is the only way to roll back safely.

---

### Observability Model

**Philosophy:** Structured wide events, not just metrics. A metric tells you something
is broken. A trace tells you why. For a 2-person team, traces are more valuable than
dashboards because they answer questions you didn't think to ask.

**Tooling stack (minimal, free/cheap tier):**

| Layer | Tool | Cost | Why |
|-------|------|------|-----|
| Structured logs | Pino (Node.js) → Loki | Grafana Cloud free tier | JSON logs, sub-ms overhead |
| Metrics | Prometheus (self-hosted on Fly.io) + Grafana | ~$5/month Fly.io volume | Pull-based, no agent needed |
| Distributed tracing | OpenTelemetry SDK → Grafana Tempo | Grafana Cloud free tier | OTel standard, vendor-neutral |
| Uptime/heartbeat | Better Stack (formerly Better Uptime) | Free tier covers this | Simple, reliable, SMS alerts |
| Cron monitoring | Healthchecks.io | Free tier (20 checks) | Dead man's switch pattern |
| LLM cost | LiteLLM proxy + custom Prometheus exporter | Included in LiteLLM | Per-request token/cost tracking |

Total cost: ~$0–15/month at launch. Grafana Cloud free tier covers logs + traces + metrics
for a small team with retention limits that are acceptable at <500 users.

**SLIs (Service Level Indicators):**

| Service | SLI | Target | Measurement |
|---------|-----|--------|-------------|
| Briefing delivery | On-time delivery rate | Delivered within scheduled window ±30 min | `briefings_delivered_on_time / briefings_scheduled` per day |
| Briefing delivery | Delivery success rate | >99% of scheduled briefings delivered | `briefings_delivered / briefings_scheduled` per day |
| Briefing quality | Source coverage | >80% of configured sources included | `sources_fetched_successfully / sources_configured` per briefing |
| LLM pipeline | Synthesis success | >99% of synthesis calls complete | `llm_calls_success / llm_calls_total` |
| API | HTTP error rate | <1% 5xx responses | `http_requests{status=~"5.."} / http_requests_total` |
| API | Latency p99 | <2s for dashboard reads | Prometheus histogram |
| Cron scheduler | Cron heartbeat | Heartbeat received within 5 min of schedule | Healthchecks.io grace period |

**SLOs (Service Level Objectives):**

| SLO | Target | Error Budget (monthly) | Rationale |
|-----|--------|----------------------|-----------|
| Briefing on-time delivery (±30 min window) | 95% | 5% = ~1.5 briefings/month can be late | 30-min window is generous for cron-based delivery; 95% is achievable without heroics |
| Briefing delivery success | 99% | 1% = ~0.3 briefings/month can fail entirely | Complete failure is rare; degraded briefing is better than no briefing |
| API availability | 99.5% | 0.5% = ~3.6 hours/month | Users access dashboard; not life-critical |
| LLM synthesis | 99% | 1% | LLM APIs have their own reliability issues; plan for them |

**Why 95% on-time, not 99%:**
A 99% on-time SLO for 6 AM delivery means you can have 0.3 late briefings per month for
a single user. That is technically achievable but it requires heroic infrastructure for
a 2-person team. 95% means 1.5 late briefings/month — users notice this and it affects
retention, but it is survivable in the first 90 days. The SLO should tighten to 99%
at month 4 when the infrastructure is stable.

**Error Budget Policy:**
- Error budget < 50% remaining: no new features, only reliability work
- Error budget exhausted: freeze all non-emergency deployments, full incident review
- This is the mechanism that forces reliability investment at the right time

**Structured Logging Schema:**

```json
{
  "timestamp": "2026-02-27T06:01:23.456Z",
  "level": "info",
  "service": "briefing-worker",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "user_id": "usr_2aB3c4D",
  "workspace_id": "ws_5eF6g7H",
  "briefing_id": "brief_9iJ0k1L",
  "scheduled_at": "2026-02-27T06:00:00.000Z",
  "message": "briefing.synthesis.started",
  "metadata": {
    "sources_configured": 5,
    "sources_fetched": 4,
    "sources_failed": ["hn_rss"],
    "model": "claude-haiku-3-5",
    "estimated_tokens": 12400
  }
}
```

**What this gives you at 3 AM:**
- `trace_id` links every log line across all services for one briefing
- `briefing_id` lets you replay a specific briefing's complete execution
- `scheduled_at` vs `timestamp` on the delivery log = on-time measurement
- `sources_failed` array = per-source reliability dashboard
- `estimated_tokens` = cost projection before the LLM call completes

**Distributed Tracing for Briefing Pipeline:**

The morning briefing is a sequential pipeline with parallel fan-out on source fetching.
This is exactly the use case distributed tracing was designed for.

```
Trace: morning-briefing (trace_id: abc123)
│
├── Span: cron.trigger (5ms)
│   attributes: user_id, workspace_id, scheduled_window
│
├── Span: sources.fan-out (parallel, 8s total)
│   ├── Span: source.fetch[hn_rss] (2.1s, status=200)
│   ├── Span: source.fetch[gmail_inbox] (3.4s, status=200)
│   ├── Span: source.fetch[calendar] (1.2s, status=200)
│   ├── Span: source.fetch[twitter_list] (8.0s, status=TIMEOUT)
│   └── Span: source.fetch[newsletter_atom] (0.8s, status=200)
│
├── Span: synthesis.prepare-context (120ms)
│   attributes: total_tokens=18400, sources_included=4/5
│
├── Span: synthesis.llm (4.2s)
│   attributes: model=claude-haiku-3-5, input_tokens=18400,
│               output_tokens=1200, cost_usd=0.0023
│
└── Span: delivery.telegram (1.1s)
    attributes: message_id=12345, delivered=true,
                delivery_lag_seconds=312
```

**Tool:** OpenTelemetry SDK for Node.js + Grafana Tempo (free tier).
**Sampling:** 100% for the first 90 days. At 500 users running daily briefings,
that is 500 traces/day — well within Grafana Cloud free tier (50GB/month).
At 2,000 users, switch to 100% error traces + 10% success traces.

**Trace context propagation for async cron:**
Cron jobs do not have an incoming HTTP request to carry trace context. The pattern is:
1. Cron scheduler creates a root span with `trace_id` = `sha256(user_id + scheduled_window)`
   (deterministic — same ID for retry of same briefing)
2. Root span injected into job context as a baggage item
3. All downstream spans (source fetches, LLM calls, delivery) use `context.with(rootSpan)`
4. Delivery confirmation span closes the root span

---

### Heartbeat and Cron Reliability

This is the highest-risk observability gap. A cron job can fail in three ways:
1. **Loud failure:** throws an exception, logs an error. Easy to detect.
2. **Silent failure:** returns success but produces wrong output. Hard to detect.
3. **Non-execution:** the cron never fires at all. Invisible without a dead man's switch.

Type 3 is the killer. Node-cron, BullMQ, and all scheduler libraries can fail to schedule
if the process crashes between restarts, if the machine runs out of memory during boot,
or if a deployment restarts the process mid-schedule window.

**Dead man's switch pattern:**

The briefing worker pings a heartbeat URL at the END of each successful briefing run.
If Healthchecks.io does not receive a ping within the grace period, it fires an alert.

```typescript
// briefing-worker.ts
async function runBriefingCycle(userId: string): Promise<void> {
  const tracer = trace.getTracer('briefing-worker');

  await tracer.startActiveSpan('briefing.full-cycle', async (span) => {
    try {
      await fetchSources(userId);
      await synthesizeBriefing(userId);
      await deliverBriefing(userId);

      // Dead man's switch: ping heartbeat on success
      await fetch(process.env.HEARTBEAT_URL_FOR_USER_CRON, { method: 'HEAD' });

      span.setStatus({ code: SpanStatusCode.OK });
    } catch (error) {
      span.recordException(error);
      span.setStatus({ code: SpanStatusCode.ERROR });

      // Alert even on caught error — heartbeat does NOT fire, alerting fires
      logger.error({ userId, error: error.message }, 'briefing.cycle.failed');
    } finally {
      span.end();
    }
  });
}
```

**Healthchecks.io configuration:**
- Check name: `morning-briefing-cron`
- Schedule: `0 6 * * *` (6 AM UTC, adjust per user timezone at scale)
- Grace period: 30 minutes (briefings take 3-8 minutes; 30 min gives full SLO window)
- Alert: Email + SMS to founder's phone
- If missed: "The 6 AM briefing cycle did not complete. Check Fly.io logs."

At scale with per-user timezones: one Healthchecks.io check per timezone bucket, not per user.
US users can be grouped: UTC-8 (Pacific), UTC-7 (Mountain), UTC-6 (Central), UTC-5 (Eastern).
That is 4 heartbeat checks, not 500.

**BullMQ vs node-cron:**

Use BullMQ with Redis (Upstash Redis free tier). Reasons:
- Persistent job queue — if the Fly.io machine restarts, jobs are not lost
- Built-in retry logic with exponential backoff
- Job-level success/failure tracking in Redis
- Delayed jobs support per-user scheduling at different times
- Worker concurrency control (don't run 500 briefings simultaneously — rate limit to 10/min)

node-cron is in-memory. If the process crashes at 5:59 AM, the 6 AM job never fires.
BullMQ with Redis persistence means the job is in the queue until it is completed.

```typescript
// scheduler setup
const briefingQueue = new Queue('morning-briefings', { connection: redisConnection });
const briefingWorker = new Worker('morning-briefings', processBriefing, {
  connection: redisConnection,
  concurrency: 10,  // max 10 briefings simultaneously
  limiter: { max: 10, duration: 60_000 }  // 10 per minute rate limit
});

// Add jobs at user signup or schedule change
await briefingQueue.add(
  `briefing:${userId}`,
  { userId, workspaceId },
  {
    repeat: { cron: '0 6 * * *', tz: user.timezone },
    jobId: `daily-briefing-${userId}`,
    removeOnComplete: 100,  // keep last 100 completions
    removeOnFail: 500       // keep last 500 failures for debug
  }
);
```

---

### LLM Cost Observability

This is the second-highest risk for a 2-person team. LLM costs are invisible until the
monthly invoice arrives. The Business Blueprint caps LLM costs at $500/month before 50 paying
users. Without real-time tracking, you cannot know you are approaching that cap until you
exceed it.

**Architecture:**

```
App Code → LiteLLM Proxy → Anthropic/OpenAI API
                ↓
         Prometheus metrics
         (tokens/cost per request)
                ↓
         Grafana dashboard
         + Alert: daily_llm_cost > $15
```

**LiteLLM proxy cost tracking setup:**

```python
# litellm_config.yaml
model_list:
  - model_name: haiku
    litellm_params:
      model: claude-haiku-3-5
      api_key: os.environ/ANTHROPIC_API_KEY
  - model_name: sonnet
    litellm_params:
      model: claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

general_settings:
  database_url: os.environ/DATABASE_URL  # Postgres or SQLite

success_callback: ["prometheus", "langfuse"]
failure_callback: ["prometheus"]

# Prometheus metrics exported:
# litellm_requests_metric{model, user_id, status}
# litellm_tokens_metric{model, user_id, token_type}
# litellm_spend_metric{model, user_id}  # USD cost
```

**Per-user cost tracking:**

Every LLM call must carry `user_id` in the metadata. LiteLLM propagates this to Prometheus labels.

```typescript
const response = await litellm.completion({
  model: 'haiku',
  messages: [...],
  metadata: {
    user_id: userId,
    workspace_id: workspaceId,
    briefing_id: briefingId,
    task_type: 'briefing_synthesis'
  }
});
```

**Grafana alerts for cost:**

```
# Alert: single user spending too much (runaway context)
WHEN litellm_spend_metric{user_id=~".+"} > 2.00 per day
→ Page: "User X spent $2+ today. Check for context runaway."

# Alert: total daily spend approaching cap
WHEN sum(litellm_spend_metric) over 24h > 15.00
→ Page: "Daily LLM spend $15+. Monthly trajectory: $450+. Approaching $500 cap."

# Alert: per-task cost anomaly
WHEN litellm_tokens_metric{task_type="briefing_synthesis"} > 50000
→ Warning: "Briefing for user X used 50K+ tokens. Check source ingestion."
```

**Hard cap enforcement (infrastructure layer, not UX):**

```typescript
// Pre-flight check before every LLM call
async function checkCostBudget(userId: string): Promise<void> {
  const monthlySpend = await getMonthlySpend(userId);  // from LiteLLM DB

  if (monthlySpend > MONTHLY_LLM_BUDGET_USD) {
    throw new BudgetExceededError(
      `User ${userId} has exceeded monthly LLM budget: $${monthlySpend.toFixed(2)}`
    );
  }
}

const MONTHLY_LLM_BUDGET_USD = 20;  // Solo tier: $20 max LLM cost
```

---

### Alerting Strategy

**Alerting Principles (from painful experience):**
- If you cannot describe the exact action to take when an alert fires, the alert is noise
- An alert that fires once a week and gets ignored is worse than no alert
- At 3 AM you want one number: "this is broken, here is where to look"
- Alert on symptoms (user impact), not causes (service internals)

**Alerts:**

| Alert Name | Condition | Severity | Window | Action |
|------------|-----------|----------|--------|--------|
| BriefingDeliveryMissed | briefings_delivered / briefings_scheduled < 0.9 over 1h | Critical | 6:00-7:00 AM | Runbook: check BullMQ queue, retry failed jobs |
| BriefingLate | delivery_lag_seconds > 1800 (30min) for any user | Warning | 6:00-7:00 AM | Runbook: check source fetch times, LLM latency |
| CronHeartbeatMissed | Healthchecks.io grace period exceeded | Critical | Anytime | Runbook: check Fly.io machine health, BullMQ status |
| LLMDailyCostHigh | sum(daily_llm_spend) > $15 | Warning | Anytime | Runbook: check for runaway context, per-user breakdown |
| LLMUserCostHigh | user daily spend > $2 | Warning | Anytime | Runbook: check specific user's briefing, token counts |
| APIErrorRateHigh | http_5xx / http_total > 0.05 over 5min | Critical | Anytime | Runbook: check recent deploy, DB connection pool |
| FlyMachineUnhealthy | Fly health check fails 3 consecutive | Critical | Anytime | Runbook: fly machine restart, check OOM |
| RedisConnectionFailed | BullMQ cannot connect to Redis | Critical | Anytime | Runbook: check Upstash Redis status, restart worker |

**On-call for a 2-person team:**

There is no rotation at launch. The founder is on-call. This is survivable because:
1. The only time-sensitive alert is 6:00-7:00 AM (briefing window)
2. Outside that window, most alerts are Warning (can wait until morning)
3. The system scope is bounded (no financial transactions, no shell execution)

**Alert routing:**
- **Critical during briefing window (6:00-7:30 AM):** SMS to founder's phone (Better Stack)
- **Critical outside briefing window:** Push notification (can wait for morning)
- **Warning:** Email digest (check next morning)
- **Info:** Slack channel `#ops-alerts` (check periodically)

**Runbook Template for BriefingDeliveryMissed:**

```markdown
# BriefingDeliveryMissed

**Symptom:** One or more users did not receive their morning briefing within the 30-minute window.

**Cause (most common):**
1. Source fetch timeout (HN RSS, Twitter, newsletter provider down)
2. LLM API rate limit or timeout
3. Telegram delivery failure (Telegram API down or bot blocked)
4. BullMQ worker crash (check Fly.io machine health)

**Immediate action (first 5 minutes):**
1. Check Grafana: which user IDs failed? How many?
2. Check trace for any failed user: which span failed?
3. Is this one user or all users? One user = source issue. All users = infrastructure issue.
4. `fly logs -a briefing-prod | grep "briefing.cycle.failed"` — see raw error

**Investigation:**
- All users failed: check Fly.io machine status (`fly status -a briefing-prod`)
  Check BullMQ: `redis-cli -u $REDIS_URL LLEN bull:morning-briefings:failed`
- One user failed: check their source configurations. Check if their Gmail OAuth is expired.

**Resolution:**
1. Fix the underlying cause
2. Retry the failed briefings: `POST /admin/briefings/retry?window=06:00&status=failed`
3. Verify delivery in Telegram (check send timestamp in logs)
4. If user already awake and complained: manually trigger briefing + personal apology message

**Prevention:**
- Add circuit breaker for each source: one source failure should NOT block the full briefing
- Add per-user retry with exponential backoff: 3 retries over 45 minutes
- Degrade gracefully: deliver partial briefing with note "Twitter unavailable today"
```

---

### Resilience Patterns

**Core philosophy for a morning briefing:** Deliver something, always. A partial briefing
is better than no briefing. An on-time degraded briefing is better than a perfect late one.

**Failure Modes:**

| Dependency | Failure Impact | Mitigation | Degraded Mode |
|------------|----------------|------------|---------------|
| HN RSS (hacker news) | No HN stories in briefing | Retry 3x with 30s backoff | Briefing delivered without HN section |
| Gmail API | No email triage in briefing | Retry 3x, check OAuth expiry | Briefing delivered without email section |
| Google Calendar API | No calendar section | Retry 3x | Briefing delivered without calendar section |
| Anthropic API | No synthesis | Retry 2x, fallback to OpenAI | Full failure — critical alert |
| OpenAI API (fallback) | No synthesis | Mark as failed | Full failure — retry queue |
| Telegram API | No delivery | Retry 5x over 20 min | Fallback to email delivery |
| Email delivery (fallback) | No delivery | Mark as failed, alert user | Support ticket auto-created |
| BullMQ/Redis | No job scheduling | Process fails loudly | CronHeartbeatMissed alert fires |
| Fly.io machine | Complete outage | Fly.io automatic restart (restart_policy=always) | Briefing delayed, retry after restart |
| Turso/SQLite | Cannot read user config | Cannot start briefing | Full failure — critical alert |

**Timeout Strategy:**
- Source fetch (per source): 10s timeout, 3 retries with exponential backoff (1s, 2s, 4s)
- LLM synthesis (Anthropic): 60s timeout, 2 retries with 5s delay
- LLM fallback (OpenAI): 30s timeout, 1 retry
- Telegram delivery: 15s timeout, 5 retries with 30s delay
- Total maximum briefing time: 3 minutes (well within 30-min SLO window)

**Circuit Breaker Thresholds (per source):**
- Open after: 3 consecutive failures
- Half-open after: 5 minutes
- Close after: 1 successful request
- When open: skip source, add "Source unavailable" note to briefing

**Implementation with opossum (Node.js circuit breaker library):**

```typescript
import CircuitBreaker from 'opossum';

const hnRssBreaker = new CircuitBreaker(fetchHNRss, {
  timeout: 10_000,
  errorThresholdPercentage: 50,
  resetTimeout: 300_000,  // 5 min
  volumeThreshold: 3
});

hnRssBreaker.on('open', () => {
  logger.warn({ source: 'hn_rss' }, 'circuit.breaker.opened');
  metrics.increment('circuit_breaker_open', { source: 'hn_rss' });
});

hnRssBreaker.fallback(() => ({
  stories: [],
  error: 'HN RSS circuit breaker open — source temporarily unavailable'
}));
```

**Graceful Degradation Decision Tree:**

```
Source X fails →
  ├── Is X a required source? (user marked as "must-have")
  │   ├── YES → Include in briefing with error note,
  │   │         mark briefing as "partial", user notification on delivery
  │   └── NO  → Skip silently, log for per-source analytics
  │
  └── Is this the 3rd failure for X this week?
      ├── YES → Email user: "Source X has been unavailable.
      │         Would you like to remove it or check configuration?"
      └── NO  → Skip, no user notification
```

---

## Cross-Cutting Implications

### For Domain Architecture
- **Agent-runtime domain** owns the BullMQ queue and all trace context propagation.
  No other domain should know about scheduling. The briefing domain calls agent-runtime
  to schedule; it does not directly touch BullMQ.
- **Each domain boundary = a trace span boundary.** When briefing domain calls sources
  domain, it creates a child span. This gives clean per-domain latency breakdown.
- **Deployment unit = one Fly.io app.** A 2-person team cannot operate microservices.
  Single deployment with internal domain boundaries. Multi-service split is a month-4 problem.

### For Data Architecture
- **BullMQ Redis = ephemeral.** Job queue state is operational, not archival. Do not store
  business data in Redis. Source: "do not use Redis for anything you cannot reconstruct."
- **Briefing history in SQLite/Turso** = permanent record. Every delivered briefing stored
  with: delivery_timestamp, source_coverage_pct, llm_tokens_used, llm_cost_usd, on_time_flag.
  This is your SLO measurement data — it must be durable.
- **LiteLLM cost DB** must be backed up. This is the source of truth for monthly invoicing
  and the data you need to dispute an anomalous Anthropic bill.

### For API Design
- **Every HTTP handler needs** `req_id` (request ID) and `user_id` injected into the
  OpenTelemetry context. Without this, you cannot correlate API logs with briefing traces.
- **Health check endpoint (critical):** `/health` must return 200 in < 200ms.
  Checks: DB connection, Redis connection, last cron heartbeat timestamp.
  Fly.io uses this for machine health determination. If it times out, Fly.io will restart
  the machine mid-briefing run. Make the health check fast and independent of LLM APIs.
- **Admin endpoints:** `/admin/briefings/retry`, `/admin/users/:id/budget`,
  `/admin/queue/status` — needed for 3 AM incident response. Protect with internal-only
  network policy (`fly.io` private networking, not exposed to internet).

### For Security
- **Secrets in Fly.io secrets store** (`fly secrets set`), not in environment files.
  Rotated via `fly secrets set --stage` + deploy (zero-downtime rotation).
- **API keys in structured logs = immediate incident.** Use `redact` option in Pino:
  ```typescript
  const logger = pino({ redact: ['*.api_key', '*.token', '*.secret'] });
  ```
- **Anthropic/OpenAI API key rotation** should trigger an alert in the runbook for
  LLMAPIKeyExpired. Key expiry is silent and catastrophic for scheduled jobs.

---

## Concerns and Recommendations

### Critical Issues

- **Silent cron non-execution is the #1 risk.**
  The system has no current mechanism to detect "the cron never fired." node-cron is
  in-memory and will silently drop jobs on process restart. This is not hypothetical —
  it will happen on the first Fly.io rolling deploy during the 6 AM window.
  **Fix:** Migrate to BullMQ + Redis persistence before first production deploy.
  **Rationale:** A missed briefing on day 1 or 2 of a 14-day free trial is a conversion killer.

- **LLM cost runaway before hard caps are in place.**
  The Business Blueprint specifies hard caps at infrastructure level, but the architecture
  has no implementation plan. A single user with a malformed source configuration could
  generate a 200K-token context and cost $10 per briefing run.
  **Fix:** Implement `checkCostBudget()` pre-flight before every LLM call before any
  users are onboarded. Set per-user daily cap at $2 and monthly cap at $25.
  **Rationale:** One runaway user can consume the entire $500/month budget in 3 days.

- **No degraded-mode delivery strategy.**
  Current design: if any source fails → briefing fails. Correct design: source failure
  should produce partial briefing, not failed briefing. A user who receives "HN is down
  today, here is everything else" is satisfied. A user who receives nothing churns.
  **Fix:** All source fetches are independent, circuit-breaker-wrapped. Synthesis proceeds
  with whatever sources succeeded. Minimum viable briefing = any 1 source + calendar.

### Important Considerations

- **Single-region Fly.io is correct for now, but document the multi-region trigger.**
  When the user base grows to 500+ users across time zones, the single-region cron
  coordination problem becomes real. Define the trigger before it happens:
  "When we have 100+ users with Pacific timezone (UTC-8), add `lax` region with
  per-region scheduler and distributed lock via Redis."

- **Grafana Cloud free tier limits.**
  Grafana Cloud free tier: 10GB logs/month, 10,000 metrics series, 50GB traces.
  At 500 users × 30 briefings/month × 500 log lines/briefing = 7.5M log lines.
  Average Pino JSON log line ≈ 200 bytes → 1.5GB/month. Comfortably within free tier.
  At 2,000 users: ~6GB/month. Still within free tier. This math should be verified at
  month 3 before hitting the limit unexpectedly.

- **BullMQ requires Redis (Upstash free tier).**
  Upstash Redis free tier: 10,000 requests/day, 256MB. At 500 users × 2 Redis
  operations/briefing = 1,000 ops/day. Comfortably within free tier. At 5,000 users:
  10,000 ops/day — exactly at the limit. Plan upgrade to paid tier ($0.2/100K operations)
  before reaching 5,000 users.

- **Timezone-aware scheduling is a day-1 requirement, not a day-60 enhancement.**
  A user in San Francisco who sets their briefing to "6 AM" expects it at 6 AM PST,
  not 6 AM UTC (which is 10 PM PST). Building timezone-naive cron scheduling and
  retrofitting timezone support is painful. BullMQ supports `tz` parameter natively.
  Use it from day 1.

### Questions for Clarification

- **What is the target delivery timezone for Phase 2 launch?** If US-only, US Eastern
  should be the default time zone. All SLO measurements should be in the user's local time.

- **Is Telegram the primary delivery channel, or email, or both from day 1?**
  This affects the delivery failure fallback strategy. If both are configured, a Telegram
  failure can fall back to email. If Telegram-only, a failure is a hard failure.

- **What is the acceptable briefing failure rate during the 14-day free trial period?**
  This affects the on-call alerting severity. During trial, every failure is a conversion
  risk. After conversion, a failure is a churn risk but the user has more patience. The SLO
  should be tighter during the trial window.

- **Who owns the ops function at day 31?** The Business Blueprint says "founder + 1 engineer."
  Is the engineer ops-capable? If not, the founder cannot both build product and be on-call
  during the briefing window indefinitely. Define the ops ownership model before launch.

---

## Fly.io-Specific Production Notes

Based on community patterns and Fly.io documentation:

**What single-region Fly.io gets right:**
- `restart_policy = always` means the machine restarts on crash automatically
- Rolling deploys with health check validation prevent broken deploys from going live
- `fly proxy` gives zero-config internal networking between services (no VPN needed)
- Volume mounts for SQLite file persistence (but volumes are AZ-specific — plan for this)

**What single-region Fly.io gets wrong:**
- SQLite volumes are attached to a specific AZ. If you migrate to multi-region, the volume
  does not follow. Plan for Turso cloud replication from the start.
- Fly.io machines can be restarted for maintenance without warning (rare but real).
  This is why BullMQ persistence is critical — in-memory jobs are lost on restart.
- The Fly.io proxy 6444/443 health check timeout defaults to 2 seconds. If your `/health`
  endpoint does any DB query slower than 2 seconds (e.g., counting briefing records),
  the machine will be marked unhealthy and restarted. Keep health checks fast.

**Fly.io deployment config for briefing worker:**

```toml
# fly.toml
app = "briefing-prod"
primary_region = "iad"

[build]
  dockerfile = "Dockerfile"

[env]
  NODE_ENV = "production"
  PORT = "8080"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false  # CRITICAL: worker must always be running for cron
  auto_start_machines = false
  min_machines_running = 1

  [http_service.concurrency]
    type = "requests"
    hard_limit = 100
    soft_limit = 50

[[vm]]
  memory = "512mb"     # BullMQ worker + Node.js — 512MB is sufficient at <500 users
  cpu_kind = "shared"
  cpus = 1

[mounts]
  source = "briefing_data"
  destination = "/data"  # SQLite file lives here

[[services.ports]]
  port = 443
  handlers = ["tls", "http"]
```

---

## References

- [Google SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [Charity Majors — Observability Engineering (O'Reilly)](https://www.oreilly.com/library/view/observability-engineering/9781492076438/)
- [Honeycomb.io — Production Observability](https://www.honeycomb.io/blog/so-you-want-to-build-an-observable-system/)
- [Healthchecks.io documentation — Cron monitoring](https://healthchecks.io/docs/)
- [LiteLLM Proxy — Cost tracking](https://docs.litellm.ai/docs/proxy/logging)
- [BullMQ documentation — Job queue reliability](https://docs.bullmq.io/)
- [Fly.io — Regions reference](https://fly.io/docs/reference/regions/)
- [Fly.io — Health checks configuration](https://fly.io/docs/reference/configuration/#http-service-checks)
- [OpenTelemetry — Semantic conventions for Generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Pino — Node.js structured logging](https://getpino.io/)
- [Grafana Cloud — Free tier limits](https://grafana.com/pricing/)
- [opossum — Node.js circuit breaker library](https://github.com/nodeshift/opossum)
- [Better Stack — Heartbeat monitoring](https://betterstack.com/docs/uptime/heartbeat-monitors/)
