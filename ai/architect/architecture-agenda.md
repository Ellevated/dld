# Architecture Agenda: Hybrid Strategy (DLD Patterns → Morning Briefing Agent)

**Date:** 2026-02-27
**Input:** `ai/blueprint/business-blueprint.md` (Board-approved Hybrid Strategy)
**Constraint:** Business Blueprint is non-negotiable — Architect designs WITHIN it

---

## Business Context (from Board)

**Two-phase product:**
- Phase 1 (Days 1-30): DLD orchestration patterns as standalone toolkit + consulting ($5K-25K/engagement)
- Phase 2 (Days 31-90): Morning briefing agent for solo founders ($99/mo SaaS, Telegram + email + web)

**Hard constraints:**
- Team: 2 people (founder + 1 engineer)
- No marketplace before security pipeline
- No EU before compliance
- Sub-10-minute time-to-first-value
- >90% reliability on narrow tasks only
- Hard usage caps at infrastructure level
- No $29 tier, minimum $99/mo
- Kill gate: trial-to-paid > 7% at day 90

**Stack assumptions from Board (CTO director):**
- Node.js 22 + TypeScript 5.x
- LangGraph.js for agent orchestration
- SQLite (WAL) local + Turso cloud
- E2B for sandboxing (TBD — may be overkill for Phase 2)
- Clerk for auth
- LiteLLM for model routing
- Fly.io for hosting

---

## Open Questions from Board (MUST resolve)

1. **E2B sandbox vs lighter isolation** for Phase 2's bounded scope
2. **LLM routing layer** design for COGS management ($20-35/user/month target)
3. **Behavioral memory data model** — the switching cost mechanism
4. **Auth/multi-workspace** with Clerk — does it map to Solo (1) / Pro (3) tiers?
5. **Phase 1 toolkit packaging format** — Git repo? npm? Docker?
6. **Reliability measurement pipeline** — how to measure >90% task success

---

## Domains Implied by Business

```
Phase 1:
  - toolkit (DLD patterns packaging + docs)
  - consulting (landing, CRM, scheduling)

Phase 2:
  - briefing (source ingestion, synthesis, delivery)
  - sources (RSS, HN, Twitter, Gmail, Calendar integrations)
  - memory (user preferences, learned priorities, behavioral model)
  - delivery (Telegram bot, email, web dashboard)
  - billing (Stripe, usage caps, tier enforcement)
  - auth (Clerk, workspaces, user management)
  - agent-runtime (LLM routing, task execution, heartbeat)
```

---

## Focus Areas by Persona

### Domain Architect (Eric Evans lens)
- What are the bounded contexts for Phase 2?
- Where are the context boundaries between briefing, sources, memory, delivery?
- What's the ubiquitous language? (task, briefing, source, preference, workspace)
- How do Phase 1 toolkit and Phase 2 product share code (if at all)?
- What's the anti-corruption layer between external APIs (Gmail, Calendar, HN) and the briefing domain?

### Data Architect (Martin Kleppmann lens)
- What's the system of record for each entity? (user preferences, briefing history, source configs, usage metrics)
- SQLite + Turso — how does WAL mode work for concurrent briefing generation?
- Behavioral memory schema: how to store learned preferences that compound over time?
- Usage tracking schema for hard caps (tasks/month per workspace)
- Data model for briefing output (structured enough for reliability measurement)

### Ops/Observability (Charity Majors lens)
- How will you know a briefing failed at 6am before the user wakes up?
- Deployment model: Fly.io single region or multi-region?
- Heartbeat monitoring — if the agent cron fails, who gets alerted?
- Cost observability: real-time LLM spend per user, per task
- SLO: what's the acceptable briefing delivery window? 6am ± 30 min?

### Security Architect (Threat model lens)
- Phase 2 attack surface: Gmail OAuth tokens, Calendar API, user preference data
- Do we need E2B sandbox for "read RSS + Gmail + synthesize" scope?
- OAuth token storage — where and how?
- Skill execution boundary — what can a briefing skill access?
- GDPR-adjacent: user data deletion, export, retention policy (even US-only)

### Evolutionary Architect (Neal Ford lens)
- What fitness functions protect the >90% reliability threshold?
- How does Phase 1 toolkit evolve INTO Phase 2 product (or stay separate)?
- What technical decisions are easy to reverse (model choice, hosting) vs hard (data model, auth)?
- How to design for scope expansion (email management, project coordination) without building for it now?
- What's the migration path from Phase 2 MVP to Phase 2 scale?

### DX / Pragmatist (Dan McKinley lens)
- Innovation tokens budget: what's novel vs boring tech?
- LangGraph.js — necessary or over-engineering for a morning briefing?
- Is Clerk justified for 2 people and <100 users at launch?
- Could Phase 2 be a simple cron + LLM call + Telegram message? How simple can this be?
- What's the minimum viable stack that ships in 30 days?

### LLM Architect (Erik Schluntz lens)
- Model routing strategy: which tasks get Haiku vs Sonnet vs GPT-4o-mini?
- Context budget for morning briefing generation (12 sources × N tokens)
- Structured output schema for briefing (reliability measurement depends on this)
- How does behavioral memory get injected into context without bloating?
- Eval strategy: deterministic checks + LLM-as-judge + human sample?
- Can the briefing agent work with the API without reading source code?

### Devil's Advocate (Fred Brooks lens)
- Is LangGraph.js over-engineering for "cron that calls an LLM"?
- Turso adds a dependency — SQLite file on Fly.io volume is simpler. When does Turso become necessary?
- Clerk adds billing dependency — is a JWT + Stripe sufficient?
- The "behavioral memory" is the supposed moat — but is it just a JSON file of preferences?
- 8 bounded contexts for a 2-person team building a morning briefing app?
- Conceptual integrity: who owns the system vision when the team is 2 people?
