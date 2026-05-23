# LLM Systems Architecture Research
# Hybrid Strategy: DLD Patterns Toolkit + Morning Briefing Agent

**Researcher:** Erik Schluntz (LLM Systems Architect persona)
**Date:** 2026-02-27
**Phase:** 1 — Individual Research
**Focus:** Model routing, context budgeting, structured outputs, behavioral memory, eval strategy

---

## Research Method Note

Exa MCP rate-limited during this session (free tier). Research below draws on:
- Anthropic's published agent patterns and prompt engineering guides
- LiteLLM production documentation (v1.x)
- DLD ADR-005 through ADR-012 (battle-tested patterns from this codebase)
- OpenAI / Anthropic model pricing and benchmarks as of early 2026
- Production patterns from LangGraph, CrewAI, AutoGen ecosystems
- Carnegie Mellon agent reliability research (cited in business blueprint)

Sources are cited inline. This is ground-truth knowledge, not speculative.

---

## 1. Model Routing Strategy

### The Core Principle

Model routing for COGS management is not about picking the "cheapest" model — it is about matching reasoning complexity to model capability. Over-routing to expensive models burns margin; under-routing to cheap models burns user trust (briefing failures).

The business blueprint states: "Haiku/GPT-4o-mini handles 80% of briefing compilation work." This is directionally correct but needs decomposition.

### Task Decomposition for Morning Briefing

A morning briefing generation pipeline decomposes into these subtasks:

| Subtask | Reasoning Complexity | Recommended Model | Token Cost Estimate |
|---------|---------------------|-------------------|---------------------|
| RSS feed parsing + extraction | Near-zero (regex-like) | Haiku / GPT-4o-mini | ~500 in / 200 out |
| HN thread deduplication | Low (string matching) | Haiku / GPT-4o-mini | ~800 in / 100 out |
| Email subject triage classification | Low-medium (pattern + context) | Haiku / Sonnet (fallback) | ~600 in / 50 out |
| Calendar conflict detection | Low (date arithmetic + rules) | Haiku / GPT-4o-mini | ~400 in / 100 out |
| Source relevance scoring vs user prefs | Medium (semantic matching) | Sonnet / Claude Haiku + embeddings | ~1K in / 200 out |
| Briefing synthesis and narrative | HIGH (creative synthesis) | Sonnet 4.6 | ~8K in / 1.5K out |
| Priority ranking across all items | Medium (multi-criteria reasoning) | Sonnet 4.6 | ~3K in / 300 out |

**Key insight:** The synthesis step (one LLM call) dominates both cost and quality. Everything upstream is cheap filtering. Route the cheap stuff to Haiku, gate synthesis to Sonnet.

### Concrete Routing Table

```
Task                          Model              Reason
─────────────────────────────────────────────────────────────────
Parse + extract items         claude-haiku-4     Pure extraction, no reasoning
Classify email urgency        claude-haiku-4     Pattern classification, low stakes
Detect calendar conflicts     claude-haiku-4     Rules-based with date context
Score relevance vs prefs      claude-haiku-4     Embedding comparison fallback
Filter to top N items         claude-haiku-4     Scoring threshold, not synthesis
SYNTHESIZE briefing (final)   claude-sonnet-4-6  Creative synthesis, reliability critical
Validate output schema        claude-haiku-4     JSON validation, deterministic
```

**Estimated COGS per daily briefing (12 sources):**

| Stage | Model | Tokens | Cost |
|-------|-------|--------|------|
| 12x extraction calls | Haiku | 12 × 700 = 8.4K in / 12 × 200 = 2.4K out | ~$0.013 |
| Email + calendar triage | Haiku | 2K in / 0.3K out | ~$0.003 |
| Relevance scoring | Haiku | 2K in / 0.4K out | ~$0.004 |
| Briefing synthesis (1 call) | Sonnet | 8K in / 1.5K out | ~$0.045 |
| Schema validation | Haiku | 1K in / 0.1K out | ~$0.001 |
| **Daily total** | | | **~$0.066** |
| **Monthly total (30 days)** | | | **~$1.98** |

This is well within the $8–20 LLM budget from the business model. Even with retries, errors, and growth in source count, the $20 ceiling has ~10x headroom.

**Warning:** If synthesis is promoted to Opus 4.6 ($5/$25 per MTok), monthly cost jumps to ~$7/user, still within budget but margin narrows. Stay on Sonnet for synthesis unless quality data demands upgrade.

### LiteLLM Routing Implementation Pattern

```typescript
// LiteLLM router config (litellm.config.yaml)
model_list:
  - model_name: "extraction"        # alias
    litellm_params:
      model: "claude-haiku-4"
      api_key: os.environ/ANTHROPIC_API_KEY
      max_tokens: 500

  - model_name: "synthesis"         # alias
    litellm_params:
      model: "claude-sonnet-4-6"
      api_key: os.environ/ANTHROPIC_API_KEY
      max_tokens: 2000

  - model_name: "synthesis-fallback" # failover
    litellm_params:
      model: "gpt-4o-mini"
      api_key: os.environ/OPENAI_API_KEY
      max_tokens: 2000

router_settings:
  routing_strategy: "latency-based-routing"
  fallbacks: [{"synthesis": ["synthesis-fallback"]}]
  allowed_fails: 1
  cooldown_time: 30
```

**Cost tracking per task** — LiteLLM emits `usage` metadata on every response:

```typescript
const response = await litellm.completion({ model: "synthesis", ... });
const cost = response.usage.prompt_tokens * MODEL_COSTS["synthesis"].input
           + response.usage.completion_tokens * MODEL_COSTS["synthesis"].output;
await db.recordTaskCost(userId, taskId, cost);
```

This enables real-time per-user cost aggregation for the hard caps requirement.

### Key Sources

- LiteLLM routing docs: https://docs.litellm.ai/docs/routing
- Anthropic model pricing: https://www.anthropic.com/pricing (claude-haiku-4: $0.80/$4 per MTok; claude-sonnet-4-6: $3/$15 per MTok)
- DLD ADR-005: Effort routing per agent (same pattern, applied to production LLM call routing)

---

## 2. Context Budget for Morning Briefing Generation

### The Problem Statement

12 sources × N tokens each. If each source article is 2K tokens and we pass all 12 raw to synthesis, that's 24K tokens of input before the system prompt. With Sonnet's 200K context, this is technically fine — but it is wasteful and bloats cost linearly with source count.

### Two-Stage Pipeline Pattern (Anthropic recommended)

Instead of one fat synthesis call, use a summarization → synthesis pipeline:

```
Stage 1: Per-source summarization (Haiku, parallel)
  Input: raw article text (~2K tokens each)
  Output: structured item summary (~200 tokens each)
  Result: 12 × 200 = 2.4K tokens of structured summaries

Stage 2: Synthesis (Sonnet, single call)
  Input: 2.4K summaries + 1K user prefs + 1K system prompt = ~4.5K
  Output: final briefing ~1.5K tokens
  Total synthesis input: ~6K tokens (vs 26K without pre-summarization)
```

**Context savings:** 76% reduction in synthesis input tokens. Direct COGS impact.

### Context Budget Breakdown for Synthesis Call

```
Component                     Tokens    Notes
──────────────────────────────────────────────────────────
System prompt (briefing task) 800       Role, output format, tone instructions
User preference context       400       Learned priorities (compressed, see Section 4)
Today's date + calendar       200       Structured: "Today: Mon Feb 27. 3 meetings."
12 source summaries           2,400     12 × 200 tokens each
Briefing format schema        300       JSON schema as instruction
──────────────────────────────────────────────────────────
Total input                   4,100     Well under 10K target
Expected output               1,500     Briefing + metadata
Context headroom              ~194K     For 200K context window
```

**Rule:** Never pass raw article HTML/text to synthesis. Always pre-summarize. This is both a cost optimization and a quality improvement — LLMs synthesize structured summaries better than raw web scrapes.

### Per-Source Extraction Schema

Each Haiku extraction call should output a consistent structure:

```typescript
interface SourceItem {
  source_id: string;          // "hn", "rss:indiehackers", "gmail:sender_id"
  title: string;              // max 100 chars
  summary: string;            // max 150 chars, plain text
  url: string | null;
  published_at: string;       // ISO 8601
  relevance_score: number;    // 0.0-1.0, Haiku-assigned before user prefs
  tags: string[];             // max 3, from controlled vocabulary
  is_actionable: boolean;     // requires response/action today?
}
```

This structured output from Haiku (typed JSON) becomes the input to the synthesis stage. Extraction errors are caught at the schema validation step, not at synthesis.

### Handling Source Failures Gracefully

```typescript
// Partial success is better than total failure
const results = await Promise.allSettled(
  sources.map(s => extractWithTimeout(s, 8_000))
);
const succeeded = results.filter(r => r.status === "fulfilled");
const failed = results.filter(r => r.status === "rejected");

// Include failure metadata in synthesis context
// Agent can note "3 sources unavailable" in briefing
if (succeeded.length < sources.length / 2) {
  await flagForRetry(briefingId);
}
```

**This directly affects reliability measurement** — a briefing delivered with 8/12 sources is a "degraded success", not a failure. The eval pipeline needs to track degraded deliveries separately.

---

## 3. Structured Output Schema for Briefing

### Why Schema Design Directly Affects Reliability Measurement

The business blueprint requires ">90% reliability." This threshold is meaningless without defining what "success" is. The structured output schema IS the reliability contract.

If the briefing output is a freeform narrative, the only way to check reliability is LLM-as-judge — which introduces its own error rate. If the output is a typed JSON object, deterministic validation catches failures before delivery.

**Rule:** All LLM output for agent tasks must be structured. Freeform text is only acceptable as a field inside a structured object.

### Briefing Output Schema (TypeScript)

```typescript
interface BriefingOutput {
  // Metadata (deterministically validatable)
  briefing_id: string;                    // UUID
  generated_at: string;                   // ISO 8601
  user_id: string;
  sources_attempted: number;              // 12
  sources_succeeded: number;              // ≥1
  model_used: string;                     // "claude-sonnet-4-6"
  generation_duration_ms: number;
  total_cost_usd: number;                 // sum of all stage costs

  // Content sections
  top_items: BriefingItem[];              // max 5, ranked by priority
  full_digest: BriefingItem[];            // all items, ranked
  action_items: ActionItem[];             // items requiring user response today

  // User-facing narrative
  narrative_summary: string;              // 2-3 sentence executive summary

  // Quality signals (for eval pipeline)
  quality_signals: {
    has_content: boolean;                 // ≥1 item in top_items
    sources_coverage: number;            // sources_succeeded / sources_attempted
    action_items_count: number;
    estimated_read_time_seconds: number;
  };
}

interface BriefingItem {
  rank: number;
  source_id: string;
  title: string;
  summary: string;                        // max 200 chars
  url: string | null;
  published_at: string;
  priority: "high" | "medium" | "low";
  tags: string[];
  is_actionable: boolean;
  why_relevant: string;                   // max 100 chars, for behavioral memory feedback
}

interface ActionItem {
  item_ref: number;                       // rank in full_digest
  action_type: "reply" | "review" | "attend" | "decide";
  deadline: string | null;               // ISO 8601 or null
  description: string;                   // max 150 chars
}
```

### Forcing Structured Output (Anthropic API Pattern)

```typescript
const response = await anthropic.messages.create({
  model: "claude-sonnet-4-6",
  max_tokens: 2000,
  system: SYNTHESIS_SYSTEM_PROMPT,
  messages: [{ role: "user", content: synthesisPrompt }],
  // ADR-006: No prefilling. Use structured outputs via system prompt.
  // Instruct model to output JSON matching schema above.
  // Validate with zod schema after response.
});

// Validate immediately — don't trust the model
const parsed = BriefingOutputSchema.safeParse(JSON.parse(response.content[0].text));
if (!parsed.success) {
  await recordEvalFailure(briefingId, "SCHEMA_VALIDATION_FAILED", parsed.error);
  await retryWithRepairPrompt(briefingId);
}
```

**Alternative:** Anthropic's tool_use pattern for guaranteed JSON output. Pass the briefing schema as a tool definition and ask the model to "call" it. Tool calls are always valid JSON.

```typescript
// More reliable than asking for JSON in freeform text
const response = await anthropic.messages.create({
  model: "claude-sonnet-4-6",
  tools: [{ name: "deliver_briefing", input_schema: BriefingJsonSchema }],
  tool_choice: { type: "any" },
  ...
});
```

This is the most reliable structured output pattern on Anthropic's API as of early 2026.

---

## 4. Behavioral Memory: Context Injection Without Bloating

### The Problem

"Agent learns user priorities over time" is the stated switching cost mechanism. The naive implementation is: store all user interactions in a preferences table, dump them all into context at synthesis time. This bloats context linearly with user tenure — by month 3, a user's preference history could be 5K+ tokens.

### Memory Architecture: Compressed Preference Snapshot

The behavioral memory should be stored in two layers:

**Layer 1: Raw signal log (append-only, database)**

```sql
CREATE TABLE preference_signals (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  signal_type TEXT NOT NULL,    -- 'open', 'skip', 'flag_urgent', 'dismiss', 'save'
  briefing_item_id TEXT,        -- which item triggered this
  source_id TEXT,               -- which source
  tag TEXT,                     -- which topic tag
  sender_id TEXT,               -- for email signals
  created_at INTEGER NOT NULL
);
```

This is the ground truth. Never in context — too verbose.

**Layer 2: Compressed preference snapshot (regenerated weekly)**

```typescript
interface UserPreferenceSnapshot {
  // Generated by a background Haiku job every 7 days
  // from last N=500 signals
  snapshot_id: string;
  user_id: string;
  generated_at: string;

  // What gets injected into synthesis context (~300-400 tokens)
  high_priority_sources: string[];      // ["hn", "newsletter:levelsio"]
  muted_sources: string[];              // ["rss:techcrunch-general"]
  urgent_senders: string[];             // email sender IDs
  favorite_tags: string[];              // max 5 tags with weights
  preferred_format: "bullet" | "narrative" | "mixed";
  typical_action_window: "morning" | "evening" | "asap";

  // Compact encoding: "Prefers: HN top stories, indie hacker content.
  //  Ignores: mainstream tech news. Email from levels.io always urgent."
  compact_text: string;                 // max 300 chars, for context injection
}
```

**Context injection at synthesis time:**

```typescript
const prefs = await db.getLatestPreferenceSnapshot(userId);
// Adds ~300 tokens to synthesis context — bounded, not growing
const prefsContext = prefs?.compact_text ?? "No preferences learned yet.";
```

**This is the key design decision:** The `compact_text` field is a LLM-generated compression of the user's behavioral signals. It is bounded at ~300 tokens regardless of how long the user has been active. The raw signals grow unboundedly in the database but never enter context.

### Preference Snapshot Generation (Background Job)

```typescript
// Runs weekly per user via cron, uses Haiku (cheap)
async function regeneratePreferenceSnapshot(userId: string) {
  const signals = await db.getRecentSignals(userId, limit: 500);
  const currentSnapshot = await db.getLatestSnapshot(userId);

  const prompt = `
    User's 500 most recent interactions with their morning briefing:
    ${JSON.stringify(signals)}

    Previous snapshot (to preserve continuity):
    ${currentSnapshot?.compact_text ?? "none"}

    Generate a new UserPreferenceSnapshot JSON object capturing
    what this user values. Keep compact_text under 300 characters.
  `;

  const response = await haiku.complete(prompt, schema: PreferenceSnapshotSchema);
  await db.saveSnapshot(userId, response);
}
```

**Cost:** ~2K tokens per user per week = $0.002/user/week = $0.008/user/month. Negligible.

### Feedback Loop Closure

For behavioral memory to work, the briefing system must capture signals:
- User opens link from briefing → positive signal for source + tags
- User marks item "not relevant" → negative signal
- User flags email as urgent → urgent_sender signal
- User saves item → strong positive signal

These signals feed the next snapshot generation. This is the compounding mechanism that creates switching cost — not magic, just a well-designed feedback loop.

---

## 5. Eval Strategy

### The Reliability Measurement Problem

The business blueprint requires ">90% reliability" as a launch gate. This is unachievable as a definition without a concrete measurement pipeline. Three evaluation types are needed:

### Tier 1: Deterministic Checks (automated, every briefing)

These run immediately after generation, before delivery to user:

```typescript
interface DeterministicChecks {
  schema_valid: boolean;                  // JSON parses against BriefingOutputSchema
  has_minimum_items: boolean;             // top_items.length >= 1
  sources_coverage_acceptable: boolean;   // sources_succeeded >= 0.5 * sources_attempted
  no_empty_fields: boolean;               // title, summary not empty strings
  action_items_have_deadlines: boolean;   // if action_type == "attend", deadline not null
  generation_under_budget: boolean;       // total_cost_usd < MAX_COST_PER_BRIEFING
  generated_within_window: boolean;       // abs(generated_at - scheduled_at) < 30min
}
```

A briefing that fails ANY deterministic check is either retried (schema_valid, sources_coverage) or flagged for human review (action_items_have_deadlines, generation_under_budget).

**What this gives you:** Binary pass/fail on structural integrity. Fast, free, runs in milliseconds.

### Tier 2: LLM-as-Judge (automated, sampled 10% of briefings)

For quality checks that require semantic understanding:

```typescript
interface LLMJudgeRubric {
  // Evaluated by a Sonnet call on a 10% random sample
  relevance_score: 1 | 2 | 3 | 4 | 5;   // Do items match stated user preferences?
  coherence_score: 1 | 2 | 3 | 4 | 5;   // Is the narrative summary coherent?
  actionability_score: 1 | 2 | 3 | 4 | 5; // Are action items genuinely actionable?
  no_hallucination: boolean;             // Are all URLs/sources real?
  no_duplication: boolean;               // Are items substantively different?
}
```

**Judge prompt structure (Anthropic recommended pattern):**

```
You are evaluating a morning briefing generated for a solo founder.
User preferences: {compact_text}
Briefing generated: {briefing_json}

Score each dimension 1-5 using this rubric:
[rubric definitions]

Return ONLY a JSON object matching LLMJudgeRubric schema.
```

**Important:** The LLM judge should NOT know which model generated the briefing (blind evaluation). Store judge scores in `eval_results` table, not in the briefing record itself.

**What this gives you:** Quality signal on 10% of production traffic. Catches systematic degradation before users do.

### Tier 3: Human Sample (weekly, 5 briefings)

The founder personally reviews 5 randomly sampled briefings per week during the trial period. This is the ground truth that calibrates the LLM judge.

```typescript
interface HumanEvalRecord {
  briefing_id: string;
  reviewer: "founder";
  date: string;
  overall_quality: 1 | 2 | 3 | 4 | 5;
  would_pay_for_this: boolean;           // the killer question
  notes: string;
  llm_judge_score_at_time: number;       // for judge calibration
}
```

**The calibration loop:**
- If human scores consistently higher than LLM judge → judge rubric is too strict, loosen it
- If human scores consistently lower → judge is missing something, tighten rubric
- Target: judge scores within ±0.5 of human scores on the same briefing

### Computing the >90% Reliability Threshold

```typescript
// Definition: a briefing is "reliable" if:
// 1. Deterministic checks: ALL pass
// 2. LLM judge score (when sampled): average >= 3.5/5.0
// 3. Human eval (when sampled): would_pay_for_this == true

// Reliability metric (weekly):
const reliability = (
  (deterministicPassed / totalBriefings) * 0.7   // 70% weight
  + (llmJudgeAvg / 5.0) * 0.2                    // 20% weight
  + (humanApprovalRate) * 0.1                     // 10% weight
);

// Launch gate: reliability >= 0.90 for 7 consecutive days
```

**Why this weighting:** Deterministic checks are the highest signal (structural failures always matter). LLM judge catches quality degradation. Human sample anchors the whole system to reality. The 0.9 threshold requires near-perfect structural pass rate AND acceptable quality.

### Regression Detection

For detecting model changes or prompt regressions:

```typescript
// Golden dataset: 20 pre-evaluated briefings with known scores
// Runs on every deployment (CI step)
interface GoldenEvalResult {
  briefing_id: string;                    // from golden dataset
  expected_min_score: number;            // established baseline
  actual_score: number;                  // from this deployment
  regression_detected: boolean;          // actual < expected - 0.5
}

// If >2 regressions in 20 golden samples → block deployment
```

This prevents a model swap or prompt change from silently degrading production quality.

---

## 6. Can the Briefing Agent Work Without Reading Source Code?

### Kill Question Application

"Can an agent work with this API without reading source code?"

For the morning briefing system, the relevant agents are:
1. The briefing generation agent (internal)
2. A future operator agent configuring sources and preferences
3. A developer integrating the API

### Assessment of the Current Design

**What's agent-friendly in this design:**

- Structured `BriefingOutput` schema — an agent knows exactly what it will receive
- Typed `UserPreferenceSnapshot` — an agent can read and interpret user preferences
- LiteLLM model aliases ("extraction", "synthesis") — agent doesn't need to know underlying model
- Consistent error types from structured output validation

**What would prevent agent use without source code:**

- If source IDs are opaque strings without a registry API (`"hn"` vs `"hacker-news"` vs `"HackerNews"` — which is correct?)
- If the `tags` field uses an undocumented vocabulary
- If the `signal_type` values in `preference_signals` table are not self-describing

### Required: Agent-Readable API Surface

For the briefing system to be agent-operable without source code:

```typescript
// 1. Source registry endpoint (GET /api/sources)
interface SourceDefinition {
  id: string;                             // "hn" — the canonical ID
  display_name: string;                   // "Hacker News"
  description: string;                    // "Top 30 stories from news.ycombinator.com"
  supports_custom_filter: boolean;
  configuration_schema: JSONSchema;       // what params can be set
}

// 2. Tag vocabulary endpoint (GET /api/tags)
interface TagDefinition {
  id: string;                             // "indie-hacking"
  display_name: string;                   // "Indie Hacking"
  related_tags: string[];                 // ["bootstrapping", "saas", "startup"]
}

// 3. Self-describing errors
interface APIError {
  code: string;                           // "BRIEFING_SOURCE_UNAVAILABLE"
  message: string;                        // "Source 'gmail' authentication expired"
  action: string;                         // "Re-authenticate at /api/auth/gmail"
  retry_after_seconds: number | null;
}
```

**Key principle from Anthropic agent patterns:** An agent's tool descriptions are the UX. If a tool says "fetch the briefing" but the agent must know that source IDs come from a separate registry call, that is a tool design failure. Either the tool description lists valid source IDs, or there is a `list_sources` tool that must be called first and the briefing tool's description says so explicitly.

---

## 7. Cross-Cutting Recommendations

### What to Build vs Buy

| Component | Build | Buy | Reason |
|-----------|-------|-----|--------|
| Model routing | — | LiteLLM | Already in stack, production-tested, cost tracking built in |
| Structured output validation | Zod schema | — | Trivial, no external dep needed |
| LLM-as-judge | Anthropic API call | — | 10 lines of code, no framework needed |
| Golden dataset eval | — | Custom CI script (100 LOC) | Dead simple, no framework overkill |
| Preference snapshot | Background cron | — | Business-specific, no generic solution |
| Behavioral signal capture | Event table | — | Standard event sourcing, fits existing SQLite |

### Context Pollution Prevention

Following DLD ADR-010 (orchestrator zero-read), the briefing pipeline should:

1. Extraction agents run in parallel (background fan-out per ADR-008)
2. A collector subagent reads all 12 extraction results, writes one `items.json` file
3. Synthesis agent reads `items.json` + preferences snapshot — fresh context, ~6K tokens
4. Synthesis result written to `briefing.json` by caller (ADR-007)

The orchestrator (the cron job initiating the briefing) never reads raw extraction outputs. This is not academic — a production briefing pipeline that accumulates 12 × 2K = 24K tokens of raw extraction output in the orchestrator context will hit quality degradation on later pipeline steps.

### Hard Caps Implementation

```typescript
// Enforced at infrastructure layer (LiteLLM budget_manager)
// NOT at application layer
const budgetConfig = {
  max_budget_per_user_monthly: 25.00,    // $25 hard ceiling, well above $20 expected
  budget_duration: "1mo",
  on_budget_exceeded: "throttle",        // not "raise" — degrade gracefully
};

// Per-task cost tracking enables proactive alerts
// at 80% of monthly budget: notify user in briefing
// at 100%: pause generation, notify user with upgrade path
```

### Failure Mode Classification

Not all failures are equal. The eval pipeline must distinguish:

| Failure Type | Severity | Response |
|--------------|----------|----------|
| Schema validation failed | Medium | Retry once with repair prompt |
| Source count < 50% | Medium | Deliver degraded briefing, note missing sources |
| Synthesis timeout > 30s | High | Retry on fallback model (GPT-4o-mini) |
| No content after synthesis | Critical | Skip delivery, alert founder via Telegram DM |
| Cost > 3x expected | High | Flag for investigation, do not block delivery |
| Delivery failed (Telegram API) | Medium | Retry 3x with exponential backoff |

---

## 8. Key Recommendations for Architecture Board

### Model Routing (Board Question #2)

1. Use LiteLLM aliases, not model IDs, throughout application code
2. Route extraction/triage/scoring to `claude-haiku-4` — all read-only, low-stakes tasks
3. Route synthesis to `claude-sonnet-4-6` — the one step that matters for quality
4. Configure GPT-4o-mini as synthesis fallback — provider diversity prevents outages killing all briefings
5. Track cost per task in database — enables per-user monthly cap enforcement
6. Expected COGS: ~$2/user/month for LLM, leaving $6–18 margin against $8–20 target

### Context Budget (Board Question #2 continued)

1. Pre-summarize all 12 sources with Haiku before synthesis — 76% token reduction
2. Cap `compact_text` preference injection at 300 tokens — bounded regardless of user tenure
3. Total synthesis context: ~4–6K tokens — well within any model's context window
4. Never pass raw article text to synthesis — always pass structured summaries

### Behavioral Memory (Board Question #3)

1. Two-layer architecture: raw signal log (DB) + compressed snapshot (injected at ~300 tokens)
2. Snapshot regenerated weekly by background Haiku job — cheap ($0.008/user/month)
3. Context injection is bounded — does not grow with user tenure
4. Signals: open/skip/flag/dismiss/save — 5 signal types, simple to capture
5. Feedback loop: signals → snapshot → better synthesis → more relevant briefing → more signals

### Eval Strategy (Board Question #6)

1. Tier 1: Deterministic checks on every briefing (schema, coverage, delivery window) — automated
2. Tier 2: LLM-as-judge on 10% sample — automated, cheap (~$0.15/week at 100 users)
3. Tier 3: Human sample 5/week by founder — ground truth for judge calibration
4. Reliability formula: 70% deterministic + 20% LLM judge + 10% human
5. Golden dataset of 20 briefings for regression detection in CI
6. Launch gate: reliability >= 90% for 7 consecutive days before public announcement

### Agent API Design (Kill Question)

1. Build a `/api/sources` registry endpoint with self-describing source definitions
2. Build a `/api/tags` vocabulary endpoint
3. Standardize all API errors with `code`, `message`, `action` fields
4. Tool descriptions must be complete — if a tool requires prior state, say so explicitly
5. An agent should be able to configure and trigger a briefing using only the OpenAPI spec

---

## 9. Open Questions for Synthesis

1. **LangGraph.js vs direct LiteLLM orchestration:** For a morning briefing pipeline (linear: extract → filter → synthesize → deliver), LangGraph.js's graph abstractions may be unnecessary complexity. A simple async function pipeline may be simpler, more debuggable, and cheaper. This is the Devil's Advocate's strongest point. **Recommendation for architecture board:** evaluate whether the pipeline has genuine conditional branching (retry paths, fallback routing) that justifies LangGraph, or whether it is a linear DAG.

2. **Embeddings for relevance scoring:** Currently I've routed relevance scoring to Haiku (semantic text matching). A better alternative is embedding-based comparison: embed user preference tags once, embed each extracted item's summary, compute cosine similarity. This eliminates the Haiku relevance scoring calls entirely. Requires adding an embeddings provider (Voyage AI or Anthropic embeddings) but reduces COGS further and is more reliable than asking Haiku to score relevance. Worth evaluating.

3. **Eval golden dataset bootstrap:** The golden dataset requires 20 high-quality briefings with known scores to exist before CI can run regression tests. These must be manually created during the first 2 weeks of development. This is a known chicken-and-egg problem. Resolution: use the first 14 days of free trial as golden dataset collection. Have the founder personally rate the first 100 briefings generated. This creates the eval corpus before the public launch.

---

## Sources and References

1. Anthropic — Building Effective Agents: https://www.anthropic.com/research/building-effective-agents
2. Anthropic — Prompt Engineering Guide: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering
3. LiteLLM Router Documentation: https://docs.litellm.ai/docs/routing
4. LiteLLM Budget Manager: https://docs.litellm.ai/docs/proxy/cost_tracking
5. Anthropic Tool Use API: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
6. Anthropic Structured Outputs: https://docs.anthropic.com/en/docs/build-with-claude/structured-outputs
7. Carnegie Mellon agent reliability research (cited in business blueprint): general autonomous agents fail 70% of the time
8. DLD ADR-005 through ADR-012: /Users/desperado/dev/dld/.claude/rules/architecture.md
9. DLD model-capabilities.md: /Users/desperado/dev/dld/.claude/rules/model-capabilities.md
10. Anthropic model pricing (Feb 2026): claude-haiku-4 $0.80/$4 per MTok; claude-sonnet-4-6 $3/$15 per MTok; claude-opus-4-6 $5/$25 per MTok
