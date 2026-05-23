# Architecture Synthesis

**Synthesizer:** Oracle (Chairman)
**Input:** 8 persona research + 8 cross-critiques
**Output:** 3 architecture alternatives
**Date:** 2026-02-27

---

## Synthesis Summary

### Key Insights from Research

1. **Universal consensus: Drop LangGraph.js.** All 8 personas agree (including LLM Architect) that the morning briefing is a linear pipeline with no branches, no human-in-the-loop, no state graph. LangGraph.js solves a problem Phase 2 does not have. Replace with plain TypeScript async pipeline.

2. **Universal consensus: E2B not needed for Phase 2.** Scope is read-only (RSS, Gmail, Calendar). No user-submitted code, no shell execution. Node.js worker_threads with permission scoping is sufficient. E2B revisited when marketplace opens (month 4+).

3. **Strongest research: Data Architect (Martin).** Ranked best by 5 of 7 personas (Domain, Ops, Security, Evolutionary, LLM). The append-only usage ledger, two-table behavioral memory (raw events + derived signals), and structured JSON briefing content are the most important data decisions.

4. **Signal vs Item is the core value proposition.** Domain persona identified: raw ingested material (Signal) transforms into evaluated briefing content (Item). This transformation is the entire product. LLM persona independently derived the same distinction through cost optimization (Haiku extraction -> Sonnet synthesis).

5. **Behavioral memory: design schema day 1, defer learning algorithm.** Consensus across all personas: the memory schema is the highest-risk irreversible decision. Must be structured (not JSON blob) from day 1. But the learning algorithm can be minimal at launch --- just capture feedback events.

6. **Google OAuth App Verification is a hard external dependency.** 4-6 week review. Must start day 31 of Phase 2. Blocks public launch. Missed by all personas except Security; once identified, unanimously recognized as critical path.

7. **COGS estimate is healthy.** LLM persona: ~$0.066/briefing/day, ~$2/user/month. Against $8-20 budget per user, there is 4-10x headroom. Haiku for extraction/triage, Sonnet for synthesis.

### Major Contradictions Resolved

5 contradictions were identified. Each is resolved below via Evaporating Cloud.

---

## Evaporating Cloud 1: Domain Count (4 vs 7)

**Conflict:** DX/Devil/Evolutionary want 4 modules. Domain wants 7 bounded contexts.

```
                [Ship fast AND maintain clean boundaries]
                              |
                 +------------+------------+
                 |                         |
           [Fast delivery]           [Clean language]
                 |                         |
                 v                         v
          [4 modules]  <---conflict--->  [7 contexts]
```

**Common Goal:** Ship fast AND maintain clean domain boundaries that prevent coupling as the system evolves.

**Need A (DX/Devil/Evolutionary):** Minimize cognitive load for 2-person team. Ship in 30 days. Fewer modules = fewer things to maintain.
**Want A:** 4 modules (briefing, sources, memory, billing).

**Need B (Domain):** Preserve linguistic clarity. "Workspace" means something different from "User." "Channel" is meaningless inside the Briefing context. Unnamed boundaries create invisible coupling.
**Want B:** 7 bounded contexts as separate modules.

**Assumptions underlying conflict:**
1. "Bounded context" = separate module/service with separate overhead
2. "4 modules" means the other 3 concepts (Workspace, Identity, Notification) do not exist

**Challenge assumptions:**
- What if bounded contexts are naming boundaries, not deployment boundaries? (Assumption 1 is FALSE)
- What if we implement 4 deployment modules but name 7 linguistic boundaries within them? (Both needs satisfied)

**Resolution:** 4 code modules implementing 7 named concepts. Auth/Identity is a thin ACL wrapper around Clerk inside `infra/auth/`. Workspace/tier logic lives inside `billing/` module but has its own named types. Notification/delivery is a submodule of `briefing/`. The names exist. The overhead does not.

---

## Evaporating Cloud 2: Scheduler (node-cron vs BullMQ+Redis)

**Conflict:** DX says boring cron. Ops says persistent job queue.

```
                [Reliable 6am briefing delivery]
                              |
                 +------------+------------+
                 |                         |
         [Ship in 30 days]         [No silent failures]
                 |                         |
                 v                         v
         [node-cron]  <---conflict--->  [BullMQ+Redis]
```

**Common Goal:** Reliable 6am briefing delivery within 30-day build timeline.

**Need A (DX):** Zero setup overhead. node-cron is 1 line. BullMQ requires Redis (Upstash), connection config, worker setup. Ship fast.
**Want A:** node-cron (in-memory, simple).

**Need B (Ops):** If Fly.io restarts the machine at 5:59am, in-memory cron silently drops the job. User wakes up to no briefing. During 14-day trial, this is a conversion killer.
**Want B:** BullMQ+Redis (persistent, survives restarts, has retry).

**Assumptions underlying conflict:**
1. "BullMQ adds significant setup time" --- but Upstash Redis free tier + BullMQ is ~30 minutes of setup
2. "node-cron is reliable enough" --- but Fly.io rolling deploys can restart mid-window

**Challenge assumptions:**
- What if BullMQ setup is only 30 minutes, not days? (Assumption 1 is FALSE)
- What if node-cron + idempotency key as a middle ground? (New option emerges)

**Resolution:** BullMQ wins this argument on evidence. The cost is 30 minutes of setup + Upstash free tier. The benefit is job persistence across restarts, built-in retry with backoff, timezone-aware scheduling (`tz` param), and worker concurrency control. DX persona partially conceded in critique phase ("Flag for revisit at 100+ users" softened to "BullMQ if you need retry"). The reliability argument is decisive for a product where a missed briefing during trial = lost conversion.

**Decision:** BullMQ+Redis (Upstash free tier) from day 1.

---

## Evaporating Cloud 3: Storage (Plain SQLite vs Turso)

**Conflict:** DX/Devil say local SQLite file. Data/Agenda designed around Turso.

```
                [Reliable data storage for <500 users]
                              |
                 +------------+------------+
                 |                         |
         [Zero dependencies]         [Cloud durability]
                 |                         |
                 v                         v
     [SQLite on Fly volume]  <-conflict->  [Turso cloud]
```

**Common Goal:** Reliable data storage that handles <500 users without operational pain.

**Need A (DX/Devil):** No third-party dependency. No network hop. No billing relationship. SQLite WAL on Fly.io volume is local disk I/O --- microsecond reads, zero cost, trivially backed up.
**Want A:** Plain SQLite file on Fly.io persistent volume.

**Need B (Data/CTO):** Cloud backup, potential multi-region reads, managed replication.
**Want B:** Turso from day 1.

**Assumptions underlying conflict:**
1. "Turso is needed for durability" --- but Litestream provides continuous SQLite backup to S3 at ~$5/month
2. "SQLite file cannot be backed up reliably" --- FALSE, Litestream does exactly this

**Challenge assumptions:**
- What if Litestream gives cloud durability without Turso? (Assumption 1 is FALSE)
- What if Turso is a month-6 upgrade, not a day-1 requirement? (Both needs satisfied sequentially)

**Resolution:** SQLite WAL on Fly.io volume + Litestream backup to S3/Tigris. Turso deferred to 500+ users or multi-region need. The schema uses `workspace_id` on every table, making migration to Turso per-tenant sharding a mechanical operation (no data model changes). The upgrade trigger: "When write contention is visible in logs (>10ms write queue) OR multi-region is needed."

**Decision:** Plain SQLite WAL + Litestream at launch. Turso at 500+ users.

---

## Evaporating Cloud 4: OAuth Token Ownership

**Conflict:** Domain says Identity context. Security says auth domain. Data puts it in a separate table under sources.

```
                [Secure, maintainable token storage]
                              |
                 +------------+------------+
                 |                         |
         [Domain clarity]            [Security isolation]
                 |                         |
                 v                         v
     [Identity context owns]  <-conflict->  [Separate table, infra concern]
```

**Resolution:** No real conflict once clarified. All three personas agree on the physical design:
- Separate `oauth_tokens` table (not embedded in source_configs)
- AES-256-GCM encrypted at rest
- Decrypted token injected into Source context per-task, never stored decrypted
- The table lives in `infra/auth/` module (Identity/Auth concern)
- Source context receives a fresh access token as a function parameter

The "conflict" was about naming, not implementation. The implementation is unanimous.

---

## Evaporating Cloud 5: Forced Tool Calls vs No Tool Calls

**Conflict:** LLM recommends `tool_choice: { type: "any" }` for reliable structured JSON. Security says no tool calls to prevent prompt injection exfiltration.

```
                [Reliable structured output that is safe]
                              |
                 +------------+------------+
                 |                         |
      [Reliable JSON output]         [No exfiltration vector]
                 |                         |
                 v                         v
      [Forced tool_choice]  <-conflict->  [No tools on synthesis]
```

**Common Goal:** Reliable structured briefing output that cannot be exploited via prompt injection.

**Need A (LLM):** LLM must output valid JSON matching BriefingOutput schema. Freeform text output fails ~5-10% of the time. Tool calls are always valid JSON.
**Want A:** `tool_choice: { type: "any" }` on synthesis call.

**Need B (Security):** A poisoned RSS feed could instruct the LLM to call an exfiltration tool. If the synthesis call has tool access, prompt injection can trigger unintended tool calls.
**Want B:** No tool calls on synthesis --- output-only response.

**Assumptions underlying conflict:**
1. "Tool calls are the only way to get reliable JSON" --- FALSE, Anthropic structured outputs and Zod validation + retry achieve similar reliability
2. "Any tool access = exfiltration risk" --- TRUE for arbitrary tools, but a single forced `deliver_briefing` tool with no side effects is safe

**Challenge assumptions:**
- What if we use a single tool definition with no side effects? The tool IS the output schema, not a callable action.
- What if we use structured outputs (system prompt + Zod validation + 1 retry) instead of tool_choice?

**Resolution: Two viable approaches:**

**Approach A (Preferred):** No tool calls. System prompt instructs JSON output. Zod validation on response. On validation failure, retry once with a repair prompt that includes the Zod error. This is ~97% reliable with one retry. No exfiltration vector.

**Approach B (Acceptable):** Single `deliver_briefing` tool definition that IS the output schema. `tool_choice: { type: "tool", name: "deliver_briefing" }`. The tool has no implementation (it is a structured output trick, not a real tool call). Since only one tool exists and it is forced, the LLM cannot be tricked into calling a different tool.

**Decision:** Approach A for Phase 2 MVP (simpler, no tools). Approach B available as upgrade if validation failure rate exceeds 3%.

---

## Board Open Questions --- Answers

### Q1: E2B sandbox vs lighter isolation
**Answer:** Node.js worker_threads. E2B not needed. Phase 2 scope is read-only HTTP calls to pre-approved APIs. No code execution, no shell access. Security persona confirmed with STRIDE analysis. Revisit when marketplace opens (month 4+).

### Q2: LLM routing for COGS management
**Answer:** Haiku for extraction/triage/scoring (80% of calls), Sonnet for synthesis (20% of calls, 70% of cost). GPT-4o-mini as synthesis fallback. LiteLLM for routing + cost tracking. Expected COGS: ~$2/user/month against $8-20 budget. Two-stage pipeline: per-source Haiku summarization -> Sonnet synthesis (76% token reduction).

### Q3: Behavioral memory data model
**Answer:** Three-layer design:
1. `briefing_feedback` --- raw event log (append-only, ground truth)
2. `memory_signals` --- derived state (running weighted average, system-owned)
3. `preference_snapshot` --- compressed 300-token text for LLM context injection (weekly Haiku job)

Schema designed day 1. Learning algorithm minimal at launch (capture events, basic running average). Full learning deferred to post-kill-gate data.

### Q4: Auth/multi-workspace with Clerk
**Answer:** Clerk free tier (10K MAU). Organizations map to workspaces. Solo = 1 org, Pro = 3 orgs. Clerk wrapped in ACL at `infra/auth/clerk.ts` --- never imported directly in domain code. When Clerk stops being free or needs EU residency, swap adapter.

### Q5: Phase 1 toolkit packaging format
**Answer:** Separate Git repository. Documented ADRs + runnable examples. No shared code dependency with Phase 2. "Separate Ways" pattern (DDD). Phase 1 documents patterns; Phase 2 applies them. Intellectual relationship, not code coupling.

### Q6: Reliability measurement pipeline
**Answer:** Three-tier eval:
- **Tier 1 (every briefing):** Deterministic checks --- schema valid, sections present, sources covered, delivery within window. Free, milliseconds.
- **Tier 2 (10% sample):** LLM-as-judge --- Sonnet scores relevance, coherence, actionability on 1-5 rubric. ~$0.15/week at 100 users.
- **Tier 3 (5/week):** Founder manually reviews, scores "would you pay for this?" Calibrates the LLM judge.
- **Formula:** `reliability = 0.7 * deterministic_pass_rate + 0.2 * (llm_judge_avg / 5.0) + 0.1 * human_approval_rate`
- **Launch gate:** reliability >= 0.90 for 7 consecutive days.

---

## Alternative A: Lean Machine

**Philosophy:** Ship the simplest thing that works. Every dependency must justify its existence with a named business problem. Boring technology, maximum velocity.

**Best for:** Maximum speed to market. Kill gate validation. Team of 2 with 30-day deadline. High uncertainty about PMF.

---

### A1. Domain Map

**Modules:** 4 code modules, 7 named concepts

| Module | Concepts Inside | Responsibility | Core Entities |
|--------|----------------|----------------|---------------|
| `briefing/` | Briefing + Notification | Compilation, synthesis, delivery | Briefing, Section, Item, Channel, DeliveryAttempt |
| `sources/` | Source | Ingestion, ACL for external APIs | Source, Signal, SourceHealth |
| `memory/` | Priority | User preferences + behavioral signals | PriorityProfile, DeclaredPriority, LearnedSignal, Engagement |
| `billing/` | Workspace + Billing | Tier enforcement, usage caps, Stripe | Workspace, UsageLedger, Subscription |

**Auth (Identity):** Thin ACL wrapper at `infra/auth/clerk.ts`. Not a domain module.

**Context Relationships:**

```
External APIs ──[ACL]──> sources/
Clerk ──[ACL]──> infra/auth/
Stripe ──[ACL]──> billing/

billing/ ──[function call]──> briefing/  (canConsumeTask check)
sources/ ──[function call]──> briefing/  (provide extracted signals)
memory/  ──[function call]──> briefing/  (provide preference snapshot)
briefing/ ──[event: BriefingEngaged]──> memory/  (feedback loop)
billing/ ──[Stripe webhook]──> billing/  (tier changes)
```

**Domain Events (in-process EventEmitter, not message broker):**

| Event | Source | Consumed By | Implementation |
|-------|--------|-------------|----------------|
| BriefingReady | briefing/ | briefing/ (delivery submodule) | Function call |
| BriefingEngaged | briefing/ | memory/ | Async function call |
| BriefingFailed | briefing/ | billing/ (reverse task), ops (alert) | Function call + log |
| SourceHealthDegraded | sources/ | briefing/ (degrade gracefully) | Function call |
| SubscriptionChanged | billing/ | billing/ (update tier/caps) | Stripe webhook handler |
| TaskCapReached | billing/ | briefing/ (block compilation) | Function call |

---

### A2. Data Model

**Schema Approach:** Single SQLite WAL file on Fly.io volume. Litestream backup to S3.

**System of Record:**

| Entity | SoR | Consistency | Notes |
|--------|-----|-------------|-------|
| User identity | Clerk | External | Our DB stores only `clerk_user_id` |
| Workspace | Our SQLite | Strong | Owns tier, caps, settings |
| Preferences (explicit) | Our SQLite | Strong | User-authored, user-editable |
| Memory signals (learned) | Our SQLite | Eventual | System-derived from feedback events |
| Source configs | Our SQLite | Strong | Versioned rows, soft-delete |
| OAuth tokens | Our SQLite | Strong | AES-256-GCM encrypted at rest |
| Briefings | Our SQLite | Strong | Immutable once delivered |
| Usage ledger | Our SQLite | Strong | Append-only, idempotency key |
| Billing state | Stripe | External | Local `billing_cache` updated via webhook |

**Key Tables** (from Martin's research --- full SQL in research-data.md):

- `workspaces` --- tier, task_cap_monthly, clerk_user_id
- `billing_cache` --- Stripe read-through cache
- `source_configs` --- versioned with soft-delete, config_json
- `oauth_tokens` --- AES-256-GCM encrypted refresh + access tokens
- `preferences` --- explicit user prefs (pref_key/pref_value)
- `memory_signals` --- learned behavioral signals (signal_type, signal_value, confidence)
- `briefing_feedback` --- raw event log (opened, clicked, dismissed, skipped)
- `briefings` --- state machine (scheduled -> fetching -> synthesizing -> delivering -> delivered/failed/degraded)
- `briefing_sources` --- per-source lineage (items_fetched, items_used, fetch_status)
- `usage_ledger` --- append-only (task_consumed, task_reversed, cap_reset)
- `usage_summary` --- materialized view for fast cap checks

**Schema Evolution:** Additive-only for first 90 days. No column renames, no type changes. Only ADD COLUMN, CREATE TABLE, CREATE INDEX. drizzle-kit for migration generation. CI/CD only applies migrations.

**Critical Invariants:**
1. Usage cap: `SUM(usage_ledger.amount) <= workspaces.task_cap_monthly` --- enforced by BEGIN IMMEDIATE
2. Briefing immutability: delivered briefing's content_json never modified
3. OAuth isolation: token accessible only via workspace_id ownership verification
4. Source lineage: every item in content_json has a source_config_id in briefing_sources

---

### A3. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Language** | TypeScript 5.x + Node.js 22 | Boring. 10M+ devs. Hireable tomorrow. |
| **Framework** | Express or Fastify (minimal) | Boring. Routes + middleware. No magic. |
| **Database** | SQLite WAL on Fly.io volume | Zero server. Microsecond reads. Litestream backup. |
| **Scheduler** | BullMQ + Upstash Redis (free tier) | Persistent jobs. Survives restarts. Timezone-aware. Retry built-in. |
| **LLM routing** | LiteLLM | 1 innovation token. Real COGS problem. Model switching as config. |
| **LLM calls** | Anthropic SDK + OpenAI SDK (via LiteLLM) | Direct SDKs. Debuggable in 30 seconds. |
| **Auth** | Clerk (free tier to 10K MAU) | 2-hour setup. OAuth + Organizations built-in. Free at launch. |
| **Payments** | Stripe Checkout + webhooks | Industry standard. No alternative needed. |
| **Telegram** | grammy.js | Best-documented TS Telegram lib. Active community. |
| **Email** | Resend (free tier: 3K/mo) | Simple API. Free at launch scale. |
| **Hosting** | Fly.io single region (iad) | SQLite-friendly. Rolling deploys. $5-15/month. |
| **Logging** | Pino (structured JSON) | Fastest Node.js logger. Sub-ms overhead. |
| **Testing** | vitest | Fast. TS-native. Drop-in jest replacement. |

**Innovation tokens:** 1 spent (LiteLLM). 2 reserved.

**NOT in stack:** LangGraph.js, Turso, E2B, BullMQ dashboard, OpenTelemetry full stack.

**Developer-hours to first production briefing:** 8-10 hours.

---

### A4. Cross-Cutting Rules (as CODE)

#### Error Handling Pattern

```typescript
// All domain functions return Result<T, E>
type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

// Usage in domain code
async function compileBriefing(
  workspaceId: string
): Promise<Result<Briefing, BriefingError>> {
  const capCheck = await billing.canConsumeTask(workspaceId);
  if (!capCheck.ok) return err({ code: 'TASK_CAP_EXCEEDED', ...capCheck.error });

  const sources = await fetchAllSources(workspaceId);
  if (sources.succeeded.length === 0) return err({ code: 'NO_SOURCES_AVAILABLE' });

  // ... compilation logic
  return ok(briefing);
}
```

#### API Design Pattern

```yaml
# All endpoints follow this pattern
paths:
  /api/v1/workspaces/{workspaceId}/briefings:
    get:
      parameters:
        - name: workspaceId
          in: path
          required: true
          schema: { type: string, format: uuid }
      responses:
        200:
          content:
            application/json:
              schema: { $ref: '#/components/schemas/BriefingList' }
        403:
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Error' }
        429:
          content:
            application/json:
              schema: { $ref: '#/components/schemas/Error' }

components:
  schemas:
    Error:
      type: object
      required: [code, message, action]
      properties:
        code: { type: string }
        message: { type: string }
        action: { type: string }  # What user/agent should do next
```

#### Logging Schema

```json
{
  "timestamp": "2026-02-28T06:01:23.456Z",
  "level": "info",
  "service": "briefing-worker",
  "trace_id": "sha256(user_id+scheduled_window)",
  "user_id": "usr_2aB3c4D",
  "workspace_id": "ws_5eF6g7H",
  "briefing_id": "brief_9iJ0k1L",
  "message": "briefing.synthesis.completed",
  "metadata": {
    "sources_configured": 5,
    "sources_succeeded": 4,
    "model": "claude-sonnet-4-6",
    "tokens_in": 4100,
    "tokens_out": 1500,
    "cost_usd": 0.045,
    "duration_ms": 4200
  }
}
```

#### Fitness Functions (Pre-commit + CI)

```bash
#!/bin/bash
# scripts/check-architecture.sh --- runs pre-commit + CI

# 1. Dependency direction
npx dependency-cruiser --validate .dependency-cruiser.cjs src/ || exit 1

# 2. File size limit
find src/ -name "*.ts" ! -name "*.test.ts" -exec wc -l {} + \
  | awk '$1 > 400 { print "OVER LIMIT: " $2 " (" $1 " lines)"; fail=1 } END { exit fail }' || exit 1

# 3. No float in money paths
grep -rn "price.*float\|amount.*float\|cost.*0\." src/ \
  && echo "FAIL: float in money context" && exit 1

# 4. No Clerk imports outside infra/auth/
grep -rn "from.*@clerk" src/domains/ src/api/ \
  && echo "FAIL: Clerk imported outside infra/auth/" && exit 1

# 5. No raw token in logs
grep -rn "refresh_token\|access_token" src/ --include="*.ts" \
  | grep -v "oauth_tokens\|_enc\|encrypt\|decrypt\|\.test\." \
  && echo "FAIL: potential raw token exposure" && exit 1

echo "All architecture checks passed"
```

---

### A5. LLM Architecture

**Pipeline (40-line TypeScript function):**

```typescript
export async function generateBriefing(workspaceId: string): Promise<BriefingResult> {
  // 1. Check cap (billing/ domain)
  const cap = await billing.canConsumeTask(workspaceId);
  if (!cap.ok) return { status: 'cap_exceeded' };

  // 2. Record task consumption (append-only ledger)
  await billing.consumeTask(workspaceId, briefingId);

  // 3. Fetch sources in parallel (sources/ domain, ACL per source)
  const sourceResults = await Promise.allSettled(
    activeSources.map(s => sources.fetchWithTimeout(s, 10_000))
  );

  // 4. Extract structured items via Haiku (parallel, per-source)
  const items = await Promise.all(
    succeeded.map(s => llm.extract(s, { model: 'extraction' }))
  );

  // 5. Load preference snapshot (memory/ domain, ~300 tokens)
  const prefs = await memory.getPreferenceSnapshot(workspaceId);

  // 6. Synthesize via Sonnet (single call, ~6K tokens input)
  const briefing = await llm.synthesize(items, prefs, { model: 'synthesis' });

  // 7. Validate output (Zod schema, retry once on failure)
  const validated = BriefingOutputSchema.safeParse(briefing);
  if (!validated.success) {
    briefing = await llm.repairAndRetry(briefing, validated.error);
  }

  // 8. Store briefing + lineage
  await db.briefings.insert({ workspaceId, content: validated.data });
  await db.briefingSources.insertMany(sourceLineage);

  // 9. Deliver via configured channels
  await delivery.send(workspaceId, validated.data);

  // 10. Ping heartbeat (dead man's switch)
  await fetch(HEARTBEAT_URL, { method: 'HEAD' });

  return { status: 'delivered', cost: totalCost };
}
```

**Model Routing:**

| Task | Model | Tokens (est.) | Cost (est.) |
|------|-------|---------------|-------------|
| 12x source extraction | claude-haiku-4 | 8.4K in / 2.4K out | $0.013 |
| Email + calendar triage | claude-haiku-4 | 2K in / 0.3K out | $0.003 |
| Relevance scoring | claude-haiku-4 | 2K in / 0.4K out | $0.004 |
| Briefing synthesis | claude-sonnet-4-6 | 8K in / 1.5K out | $0.045 |
| Schema validation | claude-haiku-4 | 1K in / 0.1K out | $0.001 |
| **Daily total** | | | **~$0.066** |
| **Monthly per user** | | | **~$1.98** |

**Fallback:** GPT-4o-mini as synthesis fallback via LiteLLM routing config. Provider diversity prevents single-provider outage from killing all briefings.

---

### A6. Ops Model

**Deployment:** Single-region Fly.io (`iad`), rolling deploy, persistent volume for SQLite.

```toml
# fly.toml
app = "briefing-prod"
primary_region = "iad"

[http_service]
  auto_stop_machines = false  # Worker must always run for BullMQ
  min_machines_running = 1

[[vm]]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1

[mounts]
  source = "briefing_data"
  destination = "/data"
```

**SLOs:**

| SLO | Target | Error Budget |
|-----|--------|-------------|
| Briefing on-time (+-30 min) | 95% | ~1.5 late/month/user |
| Briefing delivery success | 99% | ~0.3 failures/month/user |
| API availability | 99.5% | ~3.6 hours/month |

**Observability (free/cheap tier):**

| Layer | Tool | Cost |
|-------|------|------|
| Structured logs | Pino -> Grafana Loki | Free tier |
| Metrics | Prometheus on Fly.io | ~$5/month |
| Cron monitoring | Healthchecks.io | Free tier |
| LLM cost | LiteLLM callbacks | Included |

**Alerting:**

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| BriefingDeliveryMissed | <90% delivered in 1h window | Critical | Check BullMQ, retry failed |
| CronHeartbeatMissed | No ping within grace period | Critical | Check Fly.io machine |
| LLMDailyCostHigh | >$15/day total | Warning | Check for runaway context |
| APIErrorRateHigh | >5% 5xx in 5 min | Critical | Check recent deploy |

**Rollback:** `fly deploy --image <previous-digest>`. <3 minutes. Automated via CI if post-deploy smoke tests fail.

**Resilience:** Circuit breakers per source (opossum). Each source failure = degraded briefing, not failed briefing. Minimum viable briefing = any 1 source + calendar.

---

### A7. Security Model

**Key Decisions:**

| Concern | Decision |
|---------|----------|
| OAuth tokens | AES-256-GCM encrypted at rest. DEK in Fly.io secrets. Refresh-only strategy (access tokens ephemeral). |
| OAuth CSRF | Cryptographically random state param, server-side validation, 10-min expiry, one-time use |
| Workspace isolation | UUID v7 IDs. Every query: `JOIN workspaces ON workspace_id AND user_id`. Integration test for IDOR. |
| Prompt injection | Input sanitization on RSS content. Structural XML tag separation in prompt. No tool calls on synthesis. |
| Gmail content | Never stored at rest. Ephemeral in-memory only. |
| Google App Verification | Start day 31 of Phase 2. 4-6 week external dependency. Blocks public launch. |
| Scope minimization | `gmail.readonly` + `calendar.readonly` only |

---

### A8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Google OAuth verification delayed >6 weeks | Medium | Critical | Start day 31. Privacy policy ready day 30. |
| Fly.io restart during briefing window | Medium | High | BullMQ persistence + idempotency key |
| LLM cost runaway (malformed source) | Low | High | Per-user daily cap $2, monthly $25 via LiteLLM budget |
| Behavioral memory schema needs rework | Low | Critical | Append-only events + derived state. Reproject if algorithm changes. |
| Clerk pricing change or API break | Low | Medium | ACL wrapper. Swap to BetterAuth if needed. |

**Biggest Risk:** Google OAuth verification blocks public launch. External dependency, non-negotiable lead time.

**Irreversible Decisions:** Behavioral memory schema, multi-tenant isolation (workspace_id), OAuth encryption, billing tier structure.

**Reversible Decisions:** LLM model choice, hosting region, delivery channels, monitoring tooling, Clerk vs alternative auth.

---

### A9. 30-Day Timeline Check

| Week | Deliverable | Hours |
|------|-------------|-------|
| 1 (Days 31-37) | Fly.io + SQLite + BullMQ + Clerk setup. Google OAuth verification started. Schema migration framework. | 40h |
| 2 (Days 38-44) | Source adapters (RSS, HN). LiteLLM routing. Haiku extraction pipeline. Briefing state machine. | 40h |
| 3 (Days 45-51) | Sonnet synthesis. Structured output + Zod validation. Telegram delivery. Email delivery. Usage cap enforcement. | 40h |
| 4 (Days 52-58) | Reliability measurement (Tier 1 deterministic). Preference capture (feedback events). Onboarding flow. | 40h |
| Buffer (Days 59-60) | Bug fixes, polish, first 5 manual briefings for golden dataset. | 16h |

**Total:** ~176 engineer-hours (1 person full-time + 1 part-time).

---

### A. Trade-Offs

**Optimizes for:** Speed to market. Kill gate validation. Minimum viable infrastructure.

**At the cost of:** Sophisticated behavioral learning (deferred). Multi-region (deferred). Full observability (deferred). Domain purity (4 modules, not 7 services).

**Why this makes sense:** The kill gate at day 90 measures trial-to-paid conversion, not architectural elegance. If conversion fails, all infrastructure is dead code. Ship the minimum that lets you measure.

---

## Alternative B: Domain-Pure Architecture

**Philosophy:** Name every concept correctly from day 1. Linguistic clarity prevents coupling. The cost of naming is small; the cost of renaming is enormous.

**Best for:** Team that plans to grow to 5+ engineers within 12 months. System expected to survive past Phase 2 kill gate. Strong belief in behavioral memory moat.

---

### B1. Domain Map

**Modules:** 7 bounded contexts as separate code modules within a monolith

| Context | Module Path | Responsibility | Core Entities |
|---------|-------------|----------------|---------------|
| Briefing | `src/domains/briefing/` | Compilation, synthesis, quality | Briefing, Section, Item, RelevanceScore |
| Source | `src/domains/source/` | Ingestion, ACL, health tracking | Source, Signal, SourceHealth |
| Priority | `src/domains/priority/` | Declared + learned preferences | PriorityProfile, DeclaredPriority, LearnedSignal |
| Workspace | `src/domains/workspace/` | Tier enforcement, usage caps | Workspace, UsageLedger, TaskCap |
| Notification | `src/domains/notification/` | Channel management, delivery | Channel, DeliveryAttempt, DeliveryFormat |
| Identity | `src/domains/identity/` | Clerk ACL, user lifecycle | User (thin wrapper around Clerk) |
| Billing | `src/domains/billing/` | Stripe ACL, subscriptions | Subscription, BillingCache |

**Context Map:**

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

**Ubiquitous Language (enforced in code):**

| Term | Context | NOT called |
|------|---------|-----------|
| Briefing | Briefing | report, digest, summary |
| Compile | Briefing | generate, run, execute |
| Signal | Source | data, event, item |
| Item | Briefing | result, finding, entry |
| Ingest | Source | sync, pull, fetch |
| Priority | Priority | preference, setting, config |
| Channel | Notification | integration, destination |
| Workspace | Workspace | account, project, team |
| Tier | Workspace | plan, pricing, subscription |

---

### B2. Data Model

Same schema as Alternative A (Martin's research is consensus). Key difference: table naming convention enforces context boundaries.

**Naming Convention:**
- `briefing_*` tables owned by Briefing context
- `source_*` tables owned by Source context
- `priority_*` tables owned by Priority context
- `workspace_*` tables (workspaces, usage_ledger, usage_summary)
- `notification_*` tables (channels, delivery_attempts)
- `identity_*` minimal (clerk_user_id mapping)
- `billing_*` (billing_cache, stripe refs)

**Cross-context rule:** No direct SQL JOINs across context prefixes. Contexts communicate via domain events (in-process function calls at monolith scale).

**Additional table for B:**

```sql
-- Preference snapshots (Priority context)
CREATE TABLE priority_snapshots (
    id              TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id),
    high_priority_sources TEXT NOT NULL,  -- JSON array
    muted_sources   TEXT NOT NULL,         -- JSON array
    urgent_senders  TEXT NOT NULL,          -- JSON array
    favorite_tags   TEXT NOT NULL,          -- JSON array
    compact_text    TEXT NOT NULL,          -- max 300 chars, for LLM injection
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

### B3. Tech Stack

Same as Alternative A, with one addition:

| Addition | Choice | Why |
|----------|--------|-----|
| Domain event bus | EventEmitter3 (typed) | In-process pub/sub for domain events. Zero infrastructure. Makes context boundaries observable. |

All other choices identical to A. The domain purity is in code structure, not technology.

---

### B4. Cross-Cutting Rules (as CODE)

Same as Alternative A, plus:

```bash
# Additional fitness function: context boundary enforcement
# No domain imports across context boundaries
grep -rn "from.*domains/briefing" src/domains/source/ \
  && echo "FAIL: Source context imports from Briefing" && exit 1
grep -rn "from.*domains/source" src/domains/briefing/ \
  && echo "FAIL: Briefing context imports from Source" && exit 1
# ... repeat for all context pairs

# Domain events must be the ONLY cross-context communication
```

---

### B5-B6. LLM Architecture and Ops Model

Identical to Alternative A. The domain purity does not change the LLM pipeline or ops model.

---

### B7. Risks and Mitigations

All risks from Alternative A, plus:

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| 7 contexts slow down 2-person team | Medium | Medium | Monolith deploy. Contexts are folders, not services. |
| Over-abstraction delays shipping | Medium | High | Strict 30-day deadline. If behind, collapse Notification into Briefing. |
| New engineer confused by context boundaries | Low | Low | Each context has README with 10-line description. |

**Biggest Additional Risk:** Spending 3-5 extra days on context boundary setup instead of briefing quality iteration.

---

### B. Trade-Offs

**Optimizes for:** Long-term maintainability. Clean seams for future extraction. Linguistic clarity.

**At the cost of:** 3-5 extra days of setup. Higher cognitive load for 2-person team. Risk of over-engineering for a product that might not survive kill gate.

**Why this makes sense:** If the team believes they will grow past 2 people within 12 months and the product will survive the kill gate, clean boundaries pay off. The cost of renaming and restructuring at 5 engineers is 2-3 weeks. The cost of naming correctly now is 3-5 days.

---

## Alternative C: Validated Prototype

**Philosophy:** Build the cheapest possible thing that answers the kill gate question. If the answer is "yes, users pay," then rebuild properly. If "no," minimize waste.

**Best for:** Maximum uncertainty about PMF. Founder who wants to validate before building. "Would you pay $99/month for this?" answered in 2 weeks, not 90 days.

---

### C1. Domain Map

**Modules:** 2. Just 2.

| Module | Responsibility |
|--------|----------------|
| `app/` | Everything --- briefing generation, source fetching, delivery, user management |
| `scripts/` | Cron trigger, admin tools, manual operations |

No domain boundaries. No bounded contexts. No events. One folder. Ship.

---

### C2. Data Model

**3 tables:**

```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    clerk_user_id   TEXT,
    stripe_customer_id TEXT,
    tier            TEXT NOT NULL DEFAULT 'trial',
    task_cap        INTEGER NOT NULL DEFAULT 50,
    tasks_used      INTEGER NOT NULL DEFAULT 0,
    preferences     TEXT NOT NULL DEFAULT '{}',  -- JSON blob
    timezone        TEXT NOT NULL DEFAULT 'America/New_York',
    delivery_time   TEXT NOT NULL DEFAULT '06:00',
    telegram_chat_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_configs (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    type            TEXT NOT NULL,
    config          TEXT NOT NULL,  -- JSON
    enabled         INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE briefings (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    date            TEXT NOT NULL,
    content         TEXT,  -- JSON or markdown
    status          TEXT NOT NULL DEFAULT 'pending',
    cost_usd        REAL,
    delivered_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);
```

**No usage ledger.** `tasks_used` is a mutable counter (yes, race condition risk --- acceptable at <50 users).
**No behavioral memory tables.** Preferences is a JSON blob. Learning deferred entirely.
**No briefing_sources lineage.** Debug by reading logs.

---

### C3. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | TypeScript + Node.js 22 | Boring |
| Database | SQLite file on Fly.io | Zero ops |
| Scheduler | node-cron | 1 line. If it fails, fix tomorrow. |
| LLM | Direct Anthropic SDK (Sonnet only) | No LiteLLM. No routing. Just call the API. |
| Auth | Clerk free tier | 2 hours. Done. |
| Telegram | grammy.js | Send message. Done. |
| Hosting | Fly.io | Done. |

**Innovation tokens spent:** 0.

**NOT in stack:** LiteLLM, BullMQ, Redis, Litestream, any monitoring beyond `fly logs`.

**Developer-hours to first production briefing:** 4-6 hours.

---

### C4. Cross-Cutting Rules

```typescript
// One rule: if it breaks, fix it tomorrow.
// No fitness functions. No pre-commit hooks. No dependency checks.
// Ship. Measure. Decide.
```

---

### C5. LLM Architecture

```typescript
// The entire LLM architecture
async function generateBriefing(userId: string) {
  const user = await db.get('SELECT * FROM users WHERE id = ?', userId);
  const sources = await db.all('SELECT * FROM source_configs WHERE user_id = ? AND enabled = 1', userId);

  const content = await Promise.allSettled(
    sources.map(s => fetchSource(s))
  );

  const response = await anthropic.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 2000,
    messages: [{ role: 'user', content: buildPrompt(content, user.preferences) }]
  });

  await db.run('INSERT INTO briefings (id, user_id, date, content, status) VALUES (?, ?, ?, ?, ?)',
    [uuid(), userId, today(), response.content[0].text, 'delivered']);

  await telegram.sendMessage(user.telegram_chat_id, formatBriefing(response));
}
```

One file. One function. No routing. No extraction stage. No eval pipeline.

---

### C6. Ops Model

```
Monitoring: `fly logs`
Alerting: Look at Telegram. Did you get a briefing this morning?
Rollback: `fly deploy --image <previous>`
SLO: "Does it work today? Yes/No."
```

---

### C7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Mutable task counter race condition | Low (at <50 users) | Low | Fix when it happens |
| No behavioral memory schema | High | Medium (at kill gate) | Manually review what users want, iterate prompt |
| No usage cap enforcement | Medium | Medium | Stripe hard-codes tier limits |
| OAuth tokens unencrypted | High | Critical | Encrypt before first Gmail user. Non-negotiable even here. |
| No backup | Medium | Critical | Add Litestream. 30 minutes. |

**Biggest Risk:** Building so little that you cannot distinguish "product is bad" from "implementation is unreliable." If briefings fail randomly, you cannot tell whether users churn because of quality or infrastructure.

---

### C. Trade-Offs

**Optimizes for:** Speed to first user. Minimum waste if kill gate fails. Answer "would you pay?" in 2 weeks.

**At the cost of:** Everything. No reliability measurement. No behavioral memory. No proper security (except OAuth encryption --- non-negotiable). No graceful degradation. No cost control. Technical debt from day 1.

**Why this makes sense:** If you genuinely do not know whether anyone will pay $99/month for a morning briefing, spending 30 days building infrastructure is 30 days of delayed learning. Build the cheapest thing that delivers one good briefing, show it to 10 people, ask if they would pay.

**Why this might NOT make sense:** The Board already committed to 90 days and the business blueprint has hard constraints (usage caps, security, reliability). Alternative C violates most of those constraints. It is appropriate only if the founder decides the Board constraints are negotiable.

---

## Comparison Matrix

| Aspect | A: Lean Machine | B: Domain-Pure | C: Validated Prototype |
|--------|-----------------|----------------|----------------------|
| **Complexity** | Medium | Medium-High | Low |
| **Time to first briefing** | 8-10 hours | 12-15 hours | 4-6 hours |
| **Time to MVP** | 30 days | 33-35 days | 7-10 days |
| **Scalability ceiling** | ~2,000 users | ~2,000 users | ~50 users |
| **Team size needed** | 2 | 2-3 | 1 |
| **Innovation tokens** | 1 (LiteLLM) | 1 (LiteLLM) | 0 |
| **Domain boundaries** | 4 modules, 7 named | 7 contexts, strict | None |
| **Behavioral memory** | Schema day 1, learning deferred | Schema day 1, learning deferred | JSON blob, deferred entirely |
| **Reliability measurement** | 3-tier eval pipeline | 3-tier eval pipeline | Manual review |
| **Security posture** | Full (OAuth enc, CSRF, IDOR tests) | Full | Minimal (OAuth enc only) |
| **Bus factor (new dev onboard)** | 4-8 hours | 1-2 days | 2 hours |
| **Biggest risk** | Google OAuth verification delay | Over-engineering delays ship | Cannot distinguish quality from reliability |
| **Kill gate readiness** | Strong | Strong | Weak (no measurement) |
| **Post-kill-gate evolution** | Clean upgrade path | Already structured | Requires rebuild |

---

## Recommendation for Human

**If your priority is shipping in 30 days with full Board constraints:** Choose **Alternative A (Lean Machine)**.
- 4 modules give you speed. 7 named concepts give you language clarity.
- BullMQ gives you reliable 6am delivery.
- All Board constraints met (caps, security, reliability measurement, COGS).
- Clean upgrade path to B if you survive the kill gate.

**If your priority is long-term maintainability and you are confident the product survives:** Choose **Alternative B (Domain-Pure)**.
- 7 contexts give you clean seams for team growth.
- Same tech stack as A --- the difference is code organization, not infrastructure.
- 3-5 extra days is the only cost. Worth it if you expect 5+ engineers within 12 months.

**If your priority is validating demand before committing to infrastructure:** Choose **Alternative C (Validated Prototype)**.
- Ship a working briefing in 1 week.
- Show to 10 people. Ask "would you pay $99/month?"
- If yes, rebuild with A or B. If no, you saved 20 days.
- WARNING: Violates most Board constraints. Only valid if Board constraints are negotiable.

**My observation (not a recommendation):** A and B are closer to each other than either is to C. The real decision is between A/B (build properly) and C (validate first). If you choose A, upgrading to B later is a 1-week refactoring exercise. If you choose C, upgrading to A is a rebuild.

**No clear winner** --- depends on your confidence in PMF and your tolerance for technical debt.

---

## What Happens Next

Human chooses ONE alternative.

Then the Write Chain produces:
1. `architecture-overview.md` --- the chosen alternative, expanded
2. `domain-map.md` --- bounded contexts, events, aggregates
3. `data-model.md` --- full SQL schemas, migrations, consistency rules
4. `cross-cutting-rules.md` --- error handling, logging, fitness functions as CODE
5. `agent-architecture.md` --- LLM pipeline, model routing, eval strategy

**Output location:** `ai/blueprint/system-blueprint/`
