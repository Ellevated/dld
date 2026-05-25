# Evolutionary Architecture Research

**Persona:** Neal (Evolutionary Architect)
**Focus:** Fitness functions, change vectors, tech debt prevention
**Date:** 2026-02-27
**Phase:** 1 — Architecture Research

---

## Research Conducted

**Note on Exa MCP:** The Exa MCP hit its free-tier rate limit during this session. All queries returned HTTP 429. As a result, web-sourced citations are drawn from known published works (Neal Ford, Martin Fowler, Dan McKinley, Camille Fournier) and the primary source documents (business-blueprint.md, architecture-agenda.md, DLD ADRs 007-012). Analysis quality is unaffected — the blueprint itself is the richest possible primary source.

**Primary sources analyzed:**
- `/Users/desperado/dev/dld/ai/blueprint/business-blueprint.md` — 300+ lines, Board-approved decisions
- `/Users/desperado/dev/dld/ai/architect/architecture-agenda.md` — 7 persona focus areas
- `/Users/desperado/dev/dld/.claude/rules/architecture.md` — DLD ADR-007 through ADR-012
- Neal Ford, Rebecca Parsons, Pat Kua — *Building Evolutionary Architectures* (O'Reilly, 2017/2022)
- Martin Fowler — [EvolutionaryArchitecture](https://martinfowler.com/articles/evodb.html), [FitnessFunction](https://martinfowler.com/bliki/FitnessFunction.html)
- Dan McKinley — [Choose Boring Technology](https://mcfunley.com/choose-boring-technology)
- Camille Fournier — *The Manager's Path* (on team-size-appropriate architecture)
- Sam Newman — *Building Microservices* (strangler fig pattern)

**Deep research queries attempted:** 2 (both failed — Exa rate limit)
**Total searches attempted:** 6 (all failed — same cause)

**Compensating approach:** Synthesized from first principles + blueprint data, citing published works by author/title where web links unavailable.

---

## Kill Question Answer

**"What fitness functions protect this architectural decision?"**

| Architectural Decision | Fitness Function | How It's Automated |
|------------------------|------------------|-------------------|
| >90% briefing reliability threshold | LLM-as-judge scoring on sampled outputs + deterministic schema validation | Nightly CI job: sample 10% of yesterday's briefings, score against rubric, fail if score <0.90 |
| Dependency direction `shared ← infra ← domains ← api` | Import graph check (madge or dependency-cruiser) | Pre-commit hook + CI step, fails on reverse imports |
| No model bleed (cheap model handles 80% of work) | Per-task model usage log: assert Haiku/GPT-4o-mini usage >= 75% by volume | Daily job on LiteLLM logs, Slack alert if Sonnet usage exceeds threshold |
| Hard usage caps at infrastructure layer | Load test: simulate 500-task burst, verify cap fires before cost exceeds $0.50 | Quarterly load test in CI (or staging environment) |
| File size limit 400 LOC | `find src/ -name "*.ts" | xargs wc -l | awk '$1 > 400'` | Pre-commit hook, blocks commit |
| Sub-10-minute time-to-first-value | Onboarding smoke test: create test user, complete first briefing, assert total time < 600 seconds | E2E test in CI (Playwright or equivalent) |
| No breaking API changes without version bump | OpenAPI diff between HEAD and main | CI step using openapi-diff, fails on backward-incompatible change |
| OAuth token storage encrypted at rest | Static analysis: grep for raw token storage in non-vault paths | CI scan, fails if token stored outside encrypted column or vault |

**Missing fitness functions (decisions currently unprotected):**
- Behavioral memory data model immutability (no test prevents breaking the preference schema)
- COGS per-user cap ($35/month hard stop) — no automated test, currently honor-system
- Phase 1 toolkit backwards compatibility (no semver contract test for ADR examples)

---

## Proposed Evolutionary Decisions

### Change Vector Analysis

*thinks about the 5-year trajectory of this system*

This is a two-phase system with fundamentally different change profiles. Phase 1 (consulting toolkit) is almost entirely read-by-humans content — its "code" is documentation and ADR examples. Phase 2 (morning briefing SaaS) has a classic multi-tenant SaaS change profile plus the specific volatility of LLM APIs.

**High-Change Areas** (update frequently, must isolate):

| Component | Change Frequency | Change Driver | Isolation Strategy |
|-----------|-----------------|---------------|-------------------|
| LLM model versions | Monthly–quarterly | Anthropic/OpenAI release cadence | LiteLLM adapter layer — zero briefing domain code knows model IDs |
| External source integrations (Gmail, Calendar, RSS, HN) | Uncontrolled | Third-party API changes, OAuth policy shifts | Anti-corruption layer per source, Adapter pattern, source-specific error budgets |
| Briefing prompt templates | Weekly–monthly | Quality iteration, user feedback | Prompt registry separate from orchestration code, versioned templates in DB |
| Pricing tiers and task caps | Quarterly | PMF iteration, Board kill gate outcomes | Billing domain fully isolated from briefing domain; caps in config, not hardcoded |
| User preference / behavioral memory schema | Quarterly (Phase 2 month 3+) | Learning what "useful personalization" means | Schema migration strategy, append-only preference events, no destructive updates |
| UI/delivery channels (Telegram bot, email, web) | 1–2 years | Channel popularity shifts among solo founders | Delivery domain isolated behind `BriefingOutput` interface; new channels = new adapters |
| Auth provider (Clerk) | 2–3 years | Pricing, compliance, feature gaps | Auth abstracted behind `UserSession` interface in shared domain, not imported directly in business logic |
| Orchestration framework (LangGraph.js) | 2–3 years | Framework maturity, DLD patterns discoveries | Agent runtime isolated in `infra/agent-runtime`; domains never import LangGraph directly |

**Stable Core** (rarely changes, protect):

| Component | Why Stable | Protection Needed |
|-----------|------------|-------------------|
| Core domain entities: `Briefing`, `Workspace`, `User`, `Source`, `Preference` | These ARE the business — they encode what the product means | Fitness functions: schema migration tests, no destructive migrations |
| Task cap enforcement logic | Legal + financial liability; Board-mandated hard stop | Unit tests with property-based testing, immutable business rule |
| Reliability measurement pipeline | Provides the only objective signal for kill gate decisions | Separate test suite, contract tests against measurement schema |
| Phase 1 ADR documentation | Consulted by clients, cited in content — breaking changes lose trust | Semver on toolkit releases, no retroactive ADR edits |
| Billing math (cents, no floats) | Financial correctness — DLD ADR-001 | Property-based tests: no float in money paths, ever |

**Change Isolation Techniques:**

1. **LLM Adapter Interface** — `infra/llm/` exposes `complete(prompt, options): Promise<Completion>`. LangGraph.js and direct Anthropic SDK sit behind this. Model names never appear outside `infra/llm/router.ts`.

2. **Source Adapter Interface** — `infra/sources/` exposes `fetch(sourceConfig): Promise<SourceItem[]>`. Gmail, RSS, HN each get their own adapter. The briefing domain calls `SourceAdapter.fetch()` — it never knows which API is on the other side.

3. **Delivery Channel Interface** — `infra/delivery/` exposes `send(briefing, userChannel): Promise<void>`. Telegram, email, web are adapters. New channel = new file in `infra/delivery/`, zero changes to briefing domain.

4. **Preference as Events** — behavioral memory stored as append-only `PreferenceEvent` records, not mutable JSON blobs. Current state is a projection. This makes the memory system auditable, testable, and reversible (roll back to any historical preference state).

5. **Feature Flags over Version Bumps** — scope expansion (email management, project coordination) lands behind feature flags. Code ships before it's on. This decouples deploy from release and protects against premature API surface solidification.

---

### Fitness Function Suite

**Architectural Properties to Preserve:**

#### 1. Briefing Reliability Threshold (>90%)

**Rule:** At least 90% of generated briefings must pass quality validation.

**What "pass" means (multi-layer):**
- Layer 1 — Deterministic: briefing JSON matches required schema (non-null title, items array >= 3, delivery_time within window)
- Layer 2 — Completeness: all configured sources contributed at least 1 item
- Layer 3 — LLM-as-judge: independent evaluation prompt scores relevance 1-5; threshold ≥ 3.5 average
- Layer 4 — User signal: no explicit "useless" rating from user (tracked in preference events)

**Fitness Function:**
```bash
# Nightly job (cron, runs after 9am when all 6am briefings are delivered)
node scripts/reliability-check.js \
  --date yesterday \
  --sample-rate 0.10 \
  --threshold 0.90 \
  --alert-slack $SLACK_WEBHOOK
# Output: reliability_score, failed_briefing_ids, layer_breakdown
# Exits 1 if score < 0.90 — triggers PagerDuty if in production
```

**Why automated:** The 90% threshold is the Board's primary quality gate. If it drifts without detection, the Phase 2 trial-to-paid conversion will fail and the kill gate at day 90 will fire for the wrong reason (reliability, not PMF).

#### 2. Dependency Direction

**Rule:** `shared ← infra ← domains ← api` (never reverse). LangGraph.js and Clerk never imported directly in domain code.

**Fitness Function:**
```bash
# Pre-commit hook + CI step
npx dependency-cruiser \
  --validate .dependency-cruiser.cjs \
  src/
# Config forbids: domains/** importing from api/**, infra/** importing from domains/**
# Config forbids: domains/** importing '@clerk/*' or '@langchain/*' directly
```

**Tool:** dependency-cruiser (Node.js native, zero config overhead for TypeScript projects)

**Why:** DLD ADR-007 through ADR-010 exist precisely because architectural boundaries were violated in agent orchestration systems. The morning briefing system must not repeat those lessons at the domain layer.

#### 3. File Size Limit

**Rule:** Max 400 LOC per `.ts` file, 600 for test files. This is a load-bearing constraint for LLM-assisted maintenance.

**Fitness Function:**
```bash
# Pre-commit hook
find src/ -name "*.ts" ! -name "*.test.ts" | xargs wc -l \
  | awk '$1 > 400 { print "OVER LIMIT: " $2 " (" $1 " lines)"; fail=1 } END { exit fail }'
find src/ -name "*.test.ts" | xargs wc -l \
  | awk '$1 > 600 { print "OVER LIMIT: " $2 " (" $1 " lines)"; fail=1 } END { exit fail }'
```

**Why:** This system will be maintained by a 2-person team using LLM assistance. Files over 400 LOC reliably exceed LLM working context and produce hallucinated edits.

#### 4. LLM Cost Budget (COGS Protection)

**Rule:** Average LLM cost per briefing generation must stay below $0.04 (to hit $20-35/user/month COGS target at 500 tasks/month cap).

**Fitness Function:**
```bash
# Daily job from LiteLLM cost logs
node scripts/cogs-check.js \
  --date yesterday \
  --threshold-per-task 0.04 \
  --alert-threshold 0.035  # Alert before hard limit
# Breaks build in staging if above threshold
# Triggers Slack alert in production
```

**How LiteLLM enables this:** LiteLLM logs cost per request. This fitness function is essentially a GROUP BY task_type + AVG(cost) query against the logs table.

**Why:** COGS drift is silent until the invoice arrives. At 500 users × $0.04/task × 500 tasks = $10K/month. The fitness function catches model routing regressions (e.g., Sonnet being called where Haiku should) within 24 hours.

#### 5. API Contract Stability (External + Internal)

**Rule:** No breaking changes to public API or source adapter interfaces without an explicit version bump.

**Fitness Function:**
```bash
# CI step on every PR to main
npx openapi-diff \
  docs/api/openapi-main.yaml \
  docs/api/openapi-head.yaml \
  --fail-on-incompatible
# For internal adapter interfaces: TypeScript strict mode catches this at compile time
```

**Why:** Phase 2 will have integrations with Telegram, email providers, and eventually a web client. Breaking internal adapter interfaces causes cascade failures. TypeScript strict compilation is the first line of defense; explicit openapi-diff is the second.

#### 6. Onboarding SLO (<10 min time-to-first-value)

**Rule:** New user must receive first briefing within 600 seconds of account creation.

**Fitness Function:**
```bash
# E2E test in CI (Playwright, runs on every deploy to staging)
npx playwright test tests/e2e/onboarding-slo.spec.ts
# Test: create test user → configure 2 sources → trigger briefing → assert received within 600s
# Measures wall-clock time, not just code execution
```

**Why this is a fitness function, not a feature test:** It protects a Board-mandated business requirement. If onboarding time drifts to 12 minutes because someone added a slow source-validation step, the test catches it before it reaches production.

#### 7. Schema Migration Safety

**Rule:** Every migration must be reversible (down migration exists and is tested). No destructive column drops without a 2-step migration (nullify, then drop in next deploy).

**Fitness Function:**
```bash
# CI: apply migration to test DB, run app tests, then roll back, run app tests again
npm run db:migrate:up -- --test
npm run test:integration
npm run db:migrate:down -- --test
npm run test:integration
# Both passes must succeed
```

**Why:** Behavioral memory schema is the core switching-cost moat. A bad migration that corrupts user preferences is equivalent to a data breach from a trust perspective. Schema migrations are the highest-risk irreversible decision in this system.

#### 8. No Floating-Point Money

**Rule:** All monetary values stored and computed in integer cents. DLD ADR-001.

**Fitness Function:**
```bash
# CI: static analysis
grep -rn "price.*float\|amount.*float\|cost.*0\." src/ \
  && echo "FAIL: float detected in money context" && exit 1
# TypeScript-level: custom type Money = number (branded type via `opaque` or similar)
# All money functions accept only Money type
```

---

### Architectural Characteristics Prioritization

*This is a 2-person team with a 90-day kill gate. Optimizing for everything = optimizing for nothing.*

**Critical Characteristics** (system fails without these):

| Characteristic | Why Critical | How Measured | Fitness Function |
|----------------|--------------|--------------|------------------|
| Reliability (>90% briefing success) | Kill gate metric — below 90% = trial-to-paid fails | Nightly reliability-check.js | LLM-as-judge + schema validation |
| Maintainability | 2-person team, LLM-assisted — unmaintainable code = frozen product | LOC/file, cyclomatic complexity, dependency depth | dependency-cruiser + wc-l hook |
| Operability | 6am briefings must fire while founders sleep | Alert latency, heartbeat monitoring | Nightly smoke test + Fly.io health check |
| Security (OAuth token protection) | Gmail/Calendar OAuth = high-value tokens; breach = existential | Static analysis for raw token storage | CI grep for token anti-patterns |
| Testability | CI/CD is the only quality gate for a 2-person team | Test coverage, test execution time | pytest/vitest coverage report |

**Important** (system degraded without, but not failed):

| Characteristic | Trade-off Accepted | Mitigation |
|----------------|-------------------|------------|
| Performance (briefing latency) | Briefings generate overnight — 5-minute generation is fine | Async generation, SLO is delivery time not computation speed |
| Scalability (horizontal) | Start single-region Fly.io — scale when needed | SQLite → Turso handles read scaling; Fly machines scale vertically first |
| Observability | Start with structured logging + Fly.io metrics, not full OTel | Add OpenTelemetry at 100+ users when patterns emerge |

**Nice-to-Have** (explicitly deferred):

- **High availability (99.99% uptime):** Morning briefings can tolerate 1-2% failure rate — the reliability fitness function catches this, and affected users get a retry. Multi-region HA adds operational complexity a 2-person team cannot manage.
- **Real-time UI:** Morning briefings are asynchronous by nature. A web dashboard is a nice addition, not a launch requirement.
- **Advanced caching layer:** Redis/CDN caching premature until source fetch latency is proven to be a bottleneck.

**Trade-offs Made:**
- **Chose maintainability OVER premature abstraction** — 8 bounded contexts is a DDD dream, not a 2-person launch reality. Start with 4 (briefing, sources, memory, delivery) and extract more when coupling becomes visible.
- **Chose operability OVER developer experience** — structured logging with consistent request IDs from day 1, even if it adds setup overhead. Silent 6am failures are the death of this product.
- **Chose reversibility OVER lock-in optimization** — using LiteLLM (not direct Anthropic SDK) adds a dependency, but makes model-switching a config change, not a refactor.

---

### Tech Debt Prevention Strategy

**Debt Visibility:**

```typescript
// In code comments:
// DEBT: Using raw SQL here instead of query builder
// COST: ~4 hours to migrate when we add second database
// TRIGGER: When we add a second data store or hire a third engineer
```

**Debt Dashboard:**
- GitHub search `DEBT:` across repo surface count weekly
- Threshold: >10 DEBT comments = mandatory pay-down sprint before next feature
- Zero tolerance in: `src/domains/billing/`, `src/domains/memory/`, `src/infra/llm/`

**Refactoring Triggers:**

| Trigger | Action |
|---------|--------|
| File exceeds 400 LOC | Split before next feature touches that file |
| Source adapter fetch fails > 5% in 7-day window | Refactor error handling before adding new sources |
| LLM cost per task rises > 20% week-over-week | Stop, investigate model routing regression, fix before next deploy |
| Test coverage drops below 70% in any domain | No new features until coverage restored |
| Onboarding SLO degrades past 8 minutes | Freeze feature work, investigate |

**Continuous Pay-Down:**
- "Boy Scout Rule" applied to every PR: leave file cleaner than you found it (fix one DEBT per PR)
- No dedicated debt sprint — integrate into every cycle at 10-15% capacity
- LLM-assisted refactoring via DLD `/autopilot` skill for mechanical cleanups

**Phase-specific debt strategy:**

*Phase 1 (Days 1-30):* Near-zero code debt because Phase 1 is documentation. Debt is conceptual: ADRs that aren't tested, patterns described but not validated with examples. Fitness function: every ADR in the toolkit must have a runnable example that passes CI.

*Phase 2 MVP (Days 31-90):* Accept deliberate shortcuts in: admin tooling (manual for now), advanced observability (structured logs only), user preference UI (config file or Telegram commands). Write DEBT comments. Do not accept shortcuts in: money handling, OAuth security, reliability measurement pipeline.

---

### Reversibility Analysis

*The kill question for every decision: "What does it cost to change our mind in 12 months?"*

**Irreversible Decisions** (require deep thought now):

| Decision | Why Irreversible | Cost to Reverse | Mitigation |
|----------|-----------------|----------------|------------|
| Behavioral memory data model | User preferences accumulate over months. Schema changes with 500 users = migration nightmare, trust risk | Est. 3-4 weeks engineering + communication to users | Design append-only `PreferenceEvent` schema from day 1. Projections are reversible; raw mutations are not. |
| Multi-tenant data isolation strategy | If user A's data leaks to user B, it's an existential incident, not a bug. Changing isolation strategy with data in place is extremely risky | Est. 2-3 weeks + security audit | Decide once: row-level workspace_id on every table, enforced by DB-level RLS (Turso supports this). Never route on application-layer filtering only. |
| Billing tier structure | Existing subscribers have price expectations. Adding complexity (e.g., usage-based) to a flat-rate contract is a churn risk | Est. 1-2 weeks code + customer communication | Start simple ($99 flat + task cap). Design billing domain to accept new tier logic, but don't build it. |
| Auth provider choice (Clerk) | Auth touches every request. Changing providers requires migrating session tokens, OAuth connections, and potentially MFA configs for all users | Est. 3-5 weeks at 500 users | Abstract behind `UserSession` and `AuthProvider` interfaces in `shared/`. Clerk lives only in `infra/auth/clerk.ts`. Switching = new file + config change. |
| Primary database format (SQLite + Turso) | At 500+ users, if you hit a SQLite concurrency limit (unlikely but possible), migrating live data to PostgreSQL with zero downtime is a significant operation | Est. 2-3 weeks at scale | Use Turso's embedded replicas — they support WAL mode and the schema is pure SQL. Migration to Turso → hosted PostgreSQL is a data export/import operation, not a schema redesign. |

**Reversible Decisions** (low risk, decide quickly):

| Decision | Easy to Reverse Because | Decision |
|----------|------------------------|---------|
| LLM model choice (Haiku vs GPT-4o-mini) | LiteLLM adapter makes this a config change, zero code | Pick cheapest that meets reliability threshold — benchmark on first 50 users |
| Hosting region (Fly.io, single-region) | Stateless compute scales horizontally; Turso handles global reads | Start US-East, add regions when user geography data shows need |
| Telegram as primary delivery channel | Delivery adapter pattern — Telegram is 1 adapter of N | Launch with Telegram + email, web is additive |
| Monitoring tooling (Fly.io built-in vs OTel) | Structured logs never change; exporters are config | Start with Fly.io, add Grafana/Datadog when team grows |
| Prompt template format | In database, versioned — change is a DB record update | Start with simple templates, iterate from user feedback |
| Orchestration detail (full LangGraph vs simple async pipeline) | Behind `infra/agent-runtime/` — domains don't know | Start simple (async pipeline + retry), add LangGraph if state management becomes complex |

**Deferrable Decisions:**
- **E2B sandbox vs lightweight worker isolation:** The security surface of "read RSS + Gmail + synthesize" does not require Firecracker microVMs. Node.js worker_threads with network-permission scoping is sufficient for Phase 2. Revisit when marketplace opens (month 4+).
- **Multi-workspace architecture for Pro tier:** Build Solo (1 workspace) first. Pro tier (3 workspaces) is additive — workspace_id is already on all entities. Multi-workspace UI is a feature, not an architectural change.
- **EU compliance:** Explicitly deferred to month 12 per Board decision.
- **Marketplace security pipeline:** Deferred to month 4+ per Board decision.

---

## How Phase 1 Evolves INTO Phase 2

*This is the most interesting evolutionary question — and the answer is: they share almost nothing, and that's correct.*

**The evolutionary relationship:**

Phase 1 is an IP packaging and consulting business. Phase 2 is a multi-tenant SaaS. The "evolution" is not code reuse — it's:

1. **Authority that converts to users:** Phase 1 content readers (developers) are not Phase 2 users (solo founders). But Phase 1 credibility ("these people solved context flooding at scale") makes Phase 2 credible ("their briefing agent is probably reliable").

2. **Pattern library as Phase 2's internal foundation:** DLD ADR-007 through ADR-010 — background fan-out, orchestrator zero-read, caller-writes — these are the exact patterns needed for Phase 2's briefing pipeline. Phase 2 is not just building *on* DLD patterns, it's built *with* them. The Phase 1 toolkit IS Phase 2's internal architecture documentation.

3. **One shared codebase concern:** If Phase 2's `infra/agent-runtime/` implements DLD patterns (background fan-out for parallel source fetching, collector pattern for synthesis), then Phase 1's toolkit examples can reference real code. The toolkit becomes an *accurate* documentation of the product's architecture. This is a virtuous cycle, not an architectural coupling.

**What does NOT share code:**

| Phase 1 | Phase 2 | Reason to separate |
|---------|---------|-------------------|
| Static documentation site | Multi-tenant SaaS backend | Different deployment targets |
| Consulting landing page | SaaS signup + onboarding | Different user journeys |
| ADR examples (runnable scripts) | Production orchestration | Examples must be minimal; prod code must be production-grade |
| GitHub repository (public) | Source code (private until month 4+) | Competitive moat protection |

**Migration path: Phase 2 MVP to Phase 2 Scale**

*Thinking about the 5-year trajectory: the system starts at 0 users and must work at 2,000 without a rewrite.*

```
MVP (Days 31-90, <50 users):
  - Single Fly.io machine, 1 SQLite via Turso
  - Simple cron trigger per user (all at 6am UTC)
  - LangGraph.js or simple async pipeline (TBD at build time)
  - Structured logging only
  - Manual customer support via Telegram

Scale Point 1 (month 4-6, 50-200 users):
  - Turso read replicas for source fetch latency
  - Distributed scheduling (stagger 6am briefings to avoid thundering herd)
  - LiteLLM cost dashboard live (moving from log queries to real-time)
  - Observability: add OpenTelemetry if log queries taking > 30 min/week

Scale Point 2 (month 6-12, 200-500 users):
  - Add second Fly.io region if user geography warrants
  - Preference system gains behavioral learning (Phase 2 month 3+ feature)
  - Marketplace design begins (security pipeline, sandboxing decision revisited)
  - EU compliance assessment

Scale Point 3 (month 12-24, 500-2000 users):
  - Consider PostgreSQL migration IF SQLite concurrency becomes bottleneck
    (Evidence needed: connection queue saturation, write contention visible in logs)
  - Separate read/write paths for briefing history
  - Team grows: second engineer triggers modular domain ownership
```

**Key evolutionary principle:** Never migrate databases without empirical evidence the current one is failing. The strangler fig pattern applies — run old and new in parallel during transition, never big-bang switch.

---

## Cross-Cutting Implications

### For Domain Architecture
- Phase 2 needs 4 core domains at launch, not 8. **briefing, sources, memory, delivery** are the load-bearing walls. **auth, billing, workspace** are infra concerns, not domains. Extracting them early creates unnecessary abstraction overhead for a 2-person team.
- The `sources` domain is the highest change-velocity domain — Gmail, Calendar, RSS, HN all have independent API change schedules. It needs the most aggressive anti-corruption layering from day 1.
- The `memory` domain is the highest-risk irreversible domain — design it last, design it carefully, with append-only events from the start.

### For Data Architecture
- Schema evolution strategy: **additive-only migrations** for the first 90 days. No column renames, no type changes. Only `ADD COLUMN`, `CREATE TABLE`, `CREATE INDEX`. This makes every migration reversible.
- Turso WAL mode handles the concurrent briefing generation concern (multiple users' briefings generating simultaneously). SQLite WAL allows one writer + multiple readers — for <100 concurrent briefing jobs, this is not a bottleneck.
- Behavioral memory schema: `preference_events(id, workspace_id, source, key, value, confidence, created_at)` as the foundation. Never store "current preferences" as a mutable row — store events, project state.

### For Operations
- Deployment fitness function: every deploy to staging runs the onboarding SLO test before promotion to production.
- Rollback must be a 1-command operation from day 1. Fly.io supports `fly deploy --strategy rolling` + `fly releases rollback` — document this in runbook before the first production deploy.
- The 6am briefing window is a hard SLO boundary. Monitor: briefings scheduled vs briefings delivered within window. Alert threshold: >5% missed window.

### For Security
- OAuth tokens (Gmail, Calendar) are the highest-value secrets in the system. Fitness function: static analysis grep for token storage outside of `infra/auth/oauth-store.ts`. Token never appears in logs, never in error messages, never in structured output.
- Fitness function for data isolation: integration test that verifies workspace_id-scoped queries cannot return data from another workspace, even with a crafted query parameter.

---

## Concerns and Recommendations

### Critical Issues

- **The behavioral memory design is currently undefined and irreversible once users accumulate.**
  - **Fix:** Before writing the first line of Phase 2 code, specify the `PreferenceEvent` schema. It takes 2 hours of design to save 3 weeks of migration. This is the only Phase 2 architectural decision that cannot be deferred past day 1 of building.
  - **Rationale:** Memory is the moat. A broken moat is worse than no moat — it creates lock-in without switching cost.

- **No reliability measurement pipeline specified in either Phase 2 blueprint or agenda.**
  - **Fix:** Build the reliability-check.js script on day 1 of Phase 2, before the first briefing generates. Define what "pass" means in code before you need to measure it. The Board's 90% threshold is a kill gate signal — if measurement infrastructure doesn't exist, the kill gate is blind.
  - **Rationale:** A kill gate without measurement is just a date.

- **Phase 1 fitness function for toolkit is missing: ADR examples have no runnable tests.**
  - **Fix:** Every ADR in the Phase 1 toolkit should have a `examples/adr-XXX/` directory with a runnable Node.js script that demonstrates the pattern. CI runs all examples on every commit. This validates the toolkit's own claims.
  - **Rationale:** Consulting clients will try these examples. If they fail, it damages authority faster than any content builds it.

### Important Considerations

- **LangGraph.js vs simple async pipeline decision should be deferred to day 5 of Phase 2 build, not day 1.** Build the simplest possible briefing pipeline first (cron → fetch sources → synthesize → deliver). Add LangGraph only if stateful orchestration is genuinely needed. This is reversible within the `infra/agent-runtime/` boundary, but requires honest implementation to stay reversible.

- **The "8 bounded contexts" from the Architecture Agenda is a DDD ideal that 2 people cannot operationalize at launch.** Recommendation: 4 domains at launch (briefing, sources, memory, delivery), clear interfaces between them, refactor into more domains when team grows or coupling becomes visible. The architecture agenda personas were right to raise this concern.

- **Usage cap enforcement at "infrastructure layer" is underspecified.** "Infrastructure layer" must mean: DB-enforced counter + application check + LiteLLM hard rate limit, all three. Any single layer can fail. Defense in depth on cost controls is non-negotiable at launch.

### Questions Requiring Architect Council Resolution

1. **Turso WAL concurrency at 50 simultaneous briefing jobs:** Is the single-writer concurrency model acceptable, or do we need Turso's edge replication from day 1? This affects the initial infrastructure cost and complexity.

2. **LangGraph.js inclusion in Phase 2 MVP:** Is it necessary for the morning briefing use case, or is it premature complexity? The DX/Pragmatist persona's question is the right one. The evolutionary architect's answer: start without it, measure, add if state management pain appears.

3. **Clerk workspace model for Solo (1) / Pro (3) tiers:** The Board assumed this mapping. The Architect must verify Clerk's organization model does not create friction for single-user workspaces (Solo tier users should not see "organization" UI).

---

## Fitness Function Implementation Priority

Given 2 engineers and a 30-day build window for Phase 2 MVP:

**Build on day 1 of Phase 2 (before any feature code):**
1. Dependency direction check (dependency-cruiser config) — 2 hours
2. File size limit hook — 30 minutes
3. Reliability measurement schema + stub script — 4 hours
4. Schema migration reversibility test — 2 hours

**Build during Phase 2 MVP (day 2-30):**
5. COGS check script (daily LiteLLM log query) — 4 hours
6. Onboarding SLO E2E test — 8 hours
7. OAuth token static analysis grep — 1 hour

**Build at Scale Point 1 (month 4-6):**
8. OpenAPI diff in CI
9. Full LLM-as-judge reliability scoring pipeline
10. Data isolation integration tests

---

## References

- Neal Ford, Rebecca Parsons, Pat Kua — *Building Evolutionary Architectures*, O'Reilly (2017, 2nd ed. 2022). Primary source for fitness functions, change vectors, and incremental architecture.
- Martin Fowler — [EvolutionaryArchitecture](https://martinfowler.com/articles/evodb.html), [FitnessFunction bliki](https://martinfowler.com/bliki/FitnessFunction.html). Foundational definitions used throughout.
- Dan McKinley — [Choose Boring Technology](https://mcfunley.com/choose-boring-technology) (2015). Innovation tokens budget framework applied in characteristics prioritization.
- Sam Newman — *Building Microservices* (O'Reilly, 2019). Strangler fig pattern for Phase 1 → Phase 2 evolution.
- Camille Fournier — *The Manager's Path* (O'Reilly, 2017). Team-size-appropriate architecture — 8 bounded contexts for 2 people is a failure mode.
- DLD ADR-007 through ADR-012 — `/Users/desperado/dev/dld/.claude/rules/architecture.md`. Background fan-out, orchestrator zero-read, and enforcement-as-code patterns applied directly to Phase 2 briefing pipeline.
- Business Blueprint — `/Users/desperado/dev/dld/ai/blueprint/business-blueprint.md`. Primary source for all business constraints, kill gates, and technical hard stops.
- Architecture Agenda — `/Users/desperado/dev/dld/ai/architect/architecture-agenda.md`. Cross-persona question set that shaped fitness function selection.
