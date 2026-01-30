# Living Architecture Documentation

**Problem:** Project grows, specs get archived, knowledge evaporates. After 3 months no one remembers why billing was separated from campaigns.

**Solution:** Three levels of living documentation.

---

## Three Levels

```
ai/
├── ARCHITECTURE.md          # 1. Current state (living map)
├── decisions/               # 2. Why so (ADR)
│   ├── 001-supabase.md
│   └── 002-billing-domain.md
└── changelog/               # 3. How it evolved
    └── ARCHITECTURE-CHANGELOG.md
```

| Level | Question | Updated |
|-------|----------|---------|
| ARCHITECTURE.md | "What exists now?" | After each feature |
| decisions/ | "Why did we decide this?" | On important decisions |
| changelog/ | "How did it change?" | After each feature |

---

## 1. ARCHITECTURE.md — Living Map

### When to Update
- After implementing each feature (documenter agent)
- When adding new domain
- When changing dependencies between domains
- When adding new entry point

### Who Updates
- **Documenter agent** — automatically after autopilot
- **Manually** — if autopilot wasn't used

### Structure

```markdown
# Architecture: {Project Name}

**Last updated:** {date}
**Version:** {semver or just number}

---

## Overview (for humans)

{2-3 paragraphs in plain language: what is this system,
who are the users, what problem does it solve}

---

## System Diagram

{ASCII diagram or link to Mermaid}

```
┌─────────────────────────────────────────────────────────────┐
│                      Entry Points                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ seller_bot  │  │ buyer_bot   │  │ HTTP API            │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼─────────────────────┼────────────┘
          ▼                ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                        Domains                              │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ seller  │  │  buyer  │  │ campaigns│  │   billing    │  │
│  └────┬────┘  └────┬────┘  └────┬─────┘  └──────┬───────┘  │
└───────┼────────────┼────────────┼───────────────┼──────────┘
        └────────────┴─────┬──────┴───────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Infrastructure                          │
│  ┌────────────┐    ┌────────────┐    ┌─────────────────┐   │
│  │  supabase  │    │   openai   │    │  external APIs  │   │
│  └────────────┘    └────────────┘    └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Domains

### `seller` — Sellers
**Responsibility:** LLM agent for sellers, campaign management via chat

**Key components:**
- `agent.py` — main LLM agent
- `tools/` — agent tools (create_campaign, check_balance, etc.)
- `prompts/` — versioned prompts

**Depends on:** campaigns, billing
**Used by:** seller_bot (Telegram)

**Status:** Production
**Last changes:** FTR-213 (autonomous error handling)

---

### `buyer` — Buyers
**Responsibility:** FSM bot for buyers, campaign participation

**Key components:**
- `handlers/` — FSM handlers
- `keyboards/` — inline keyboards
- `locales/` — i18n

**Depends on:** campaigns, billing
**Used by:** buyer_bot (Telegram)

**Status:** Production
**Last changes:** FTR-220 (new onboarding flow)

---

### `campaigns` — Campaigns
...

---

### `billing` — Billing
...

---

## Entry Points

| Entry Point | Technology | Domains | Audience |
|-------------|------------|---------|----------|
| seller_bot | aiogram 3.x | seller | WB/Ozon sellers |
| buyer_bot | aiogram 3.x | buyer | Buyers |
| HTTP API | FastAPI | billing, campaigns | Webhooks, integrations |

---

## Infrastructure

### Database
**Supabase (PostgreSQL)**
- Why: managed, row-level security, realtime
- ADR: [001-supabase](./decisions/001-supabase.md)

### LLM
**OpenAI GPT-4**
- Used by: seller agent
- Why: best reasoning for agent tasks
- ADR: [003-openai-for-agent](./decisions/003-openai-for-agent.md)

### External APIs
| API | Purpose | Domain |
|-----|---------|--------|
| DaData | Bank details validation | billing |
| WB API | Product verification | campaigns |

---

## Key Decisions

| # | Decision | Date | ADR |
|---|----------|------|-----|
| 001 | Supabase instead of raw Postgres | 2025-11-15 | [→](./decisions/001-supabase.md) |
| 002 | Separate billing domain | 2025-11-20 | [→](./decisions/002-billing-domain.md) |
| 003 | LLM agent for seller (not FSM) | 2025-12-01 | [→](./decisions/003-llm-agent.md) |

---

## Evolution Timeline

| Date | What changed | Feature/Reason |
|------|--------------|----------------|
| 2025-11-15 | Initial architecture | — |
| 2025-12-01 | Added seller agent | FTR-100 |
| 2025-12-15 | Separated billing | FTR-150 |
| 2026-01-05 | Autonomous error handling | FTR-213 |

[Full changelog →](./changelog/ARCHITECTURE-CHANGELOG.md)

---

## Current Metrics

| Metric | Value | Threshold |
|--------|-------|-----------|
| Domains | 4 | — |
| Max LOC in file | 380 | 400 |
| Test coverage | 41% | 40% |
| Avg exports per __init__ | 3.2 | 5 |
```

---

## 2. ADR (Architecture Decision Records)

### When to Create
- Technology choice (DB, framework, API)
- Structural decision (new domain, splitting existing)
- Rejection of something (why we did NOT choose X)
- Trade-off decisions

### ADR Template

```markdown
# ADR-{NNN}: {Title}

**Status:** Accepted | Superseded by ADR-XXX | Deprecated
**Date:** {YYYY-MM-DD}
**Deciders:** {who}

---

## Context

{What was the situation? What problem were we solving?}

## Decision

{What did we decide? One sentence.}

## Rationale

{Why exactly this way?}

### Alternatives Considered

| Option | Pros | Cons | Why rejected |
|--------|------|------|--------------|
| {alt1} | ... | ... | ... |
| {alt2} | ... | ... | ... |

## Consequences

### Positive
- {what became better}

### Negative
- {what trade-offs we accepted}

### Risks
- {what could go wrong}

---

## Related
- Feature: {FTR-XXX}
- Other ADRs: {links}
```

---

## 3. Architecture Changelog

### Format

```markdown
# Architecture Changelog

All significant changes to project architecture.

---

## [2026-01-06]

### Added
- Domain `outreach` for lead generation (FTR-225)

### Changed
- `campaigns` now depends on `outreach` (was independent)

### Decisions
- ADR-015: Separate domain for outreach vs extending campaigns

---

## [2026-01-03]

### Changed
- `seller` agent: autonomous error handling without auto-escalation (FTR-213)

### Architecture Impact
- New pattern: agent decides when to escalate

---

## [2025-12-15]

### Added
- Domain `billing` extracted from `campaigns` (FTR-150)

### Decisions
- ADR-002: Why separate billing

### Migration
- transactions table moved
- Old imports deprecated
```

---

## Update Process

### After Each Feature (Documenter Agent)

```
1. Feature implemented
2. Documenter checks:
   - Did domains change?
   - New dependencies?
   - New entry points?
   - Was there an architectural decision?
3. If yes → updates:
   - ARCHITECTURE.md (corresponding sections)
   - changelog/ARCHITECTURE-CHANGELOG.md
   - Creates ADR if needed
```

### When Archiving Spec

```
1. Spec goes to archive/
2. Documenter extracts:
   - Architectural changes → ARCHITECTURE.md
   - Decisions → ADR (if any)
   - Timeline entry → changelog
3. Knowledge "settles" in living documentation
```

---

## Integration with Documenter

Add to documenter agent prompt:

```
After updating regular documentation, check:

1. ARCHITECTURE.md
   - Are domains up to date?
   - Are dependencies up to date?
   - Add to Evolution Timeline?

2. ADR needed?
   - Was there an important architectural decision?
   - Was there a choice between alternatives?

3. Changelog
   - Add entry about what changed
```

---

## Review Checklist

During code review verify:

- [ ] If new domain → added to ARCHITECTURE.md
- [ ] If new dependency → diagram updated
- [ ] If architectural decision → ADR exists
- [ ] Changelog updated

---

## 4. Project Context System (ARCH-001)

**Problem:** LLM agent starts refactoring, finds some files via grep, edits them — but forgets about dependent components. Result: broken code in other parts of the system.

**Solution:** Three-level project knowledge system.

### Structure

```
.claude/rules/                          # KNOWLEDGE (what we know about project)
├── dependencies.md                     # Dependency graph between components
├── architecture.md                     # Patterns, ADR, anti-patterns
└── domains/
    └── {domain}.md                     # Context for specific domain

.claude/agents/_shared/                 # PROTOCOLS (how to work)
├── context-loader.md                   # Load context BEFORE work
└── context-updater.md                  # Update context AFTER work

ai/glossary/                            # TERMS (self-contained per domain)
├── billing.md                          # Billing terms and rules
├── campaigns.md
└── ...
```

### Knowledge Levels

```
┌──────────────────────────────────────────────────────────────┐
│ Layer 1: dependencies.md + architecture.md                    │
│ Connection graph + patterns. Loaded by ALL agents            │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 2: domains/{name}.md + glossary/{domain}.md            │
│ Domain context. Loaded IF working with domain                │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 3: Feature spec (ai/features/XXX.md)                   │
│ Task context. Loaded by executor                             │
└──────────────────────────────────────────────────────────────┘
```

### Impact Tree Algorithm (5 Steps)

For any code change execute:

#### Step 1: UP — who uses?

```bash
# Find all module importers
grep -r "from.*{module}" . --include="*.py" --include="*.ts" --include="*.sql"
```

**CRITICALLY IMPORTANT:** Dot `.` — entire project, NOT specific folder!

#### Step 2: DOWN — what depends on?

```bash
# In file being changed — what imports?
grep "^from\|^import" {file}
```

#### Step 3: BY TERM — grep entire project

```bash
# CRITICALLY IMPORTANT: grep entire project
grep -rn "{old_term}" . --include="*.py" --include="*.ts" --include="*.sql" --include="*.md"
```

**RULE:** After all changes `grep "{old_term}" .` = 0 results!

#### Step 4: CHECKLIST — mandatory folders

| Change type | MUST check |
|-------------|------------|
| DB schema / columns | `tests/**`, `supabase/migrations/**`, `supabase/functions/**` |
| Money/amounts | `tests/**`, `*.sql`, `ai/glossary/**` |
| API signature | `tests/**`, all calling modules |
| Naming convention | **EVERYTHING** — grep entire project |

#### Step 5: Dual System Check

If changing data source:
1. Who READS from old source?
2. Who READS from new source?
3. Is there a transition period?

### Integration with Agents

| Agent | When to load | When to update |
|-------|--------------|----------------|
| spark | Phase 0 (before Impact Tree) | Phase 7.5 (after spec) |
| planner | Phase 0 (before plan) | — |
| coder | Step 0 (before code) | Step 7 (after code) |
| review | Check 0 (verify update) | — |
| debugger | Step 1.5 (check dependencies) | — |
| council | Phase 0 (before experts) | — |

### Module Headers

At the beginning of significant files add:

```python
"""
Module: pricing_service
Role: Calculate campaign costs (preview before creation)
Source of Truth: SQL RPC calculate_campaign_cost()

Uses:
  - campaigns/models.py: Campaign, UgcType, SlotStatus
  - shared/types.py: UUID, Decimal

Used by:
  - seller/tools/campaigns: cost preview for agent
  - campaigns/activation: launch validation

Glossary: ai/glossary/billing.md (money rules)
"""
```

### Per-Domain Glossary (Self-Contained)

Each glossary file contains EVERYTHING needed for working with domain:

```markdown
# Billing Glossary

## Money Rules (CRITICAL)
All amounts in kopecks. 1 ruble = 100 kopecks.
Naming: `amount_kopecks`, never bare `amount`.
Why: Integer arithmetic prevents floating-point errors.

## term_name
**What:** Definition
**Why:** History, reason
**Naming:** Code convention
**Related:** Related terms
```

**Duplicating Money Rules in each domain file — ok.** LLM reads one file and has all context.

### Enforcement Mechanisms

| Mechanism | What it does |
|-----------|--------------|
| `validate-spec-complete.sh` | Blocks commit if Impact Tree checkboxes empty |
| Spark Phase 0 | Mandatory context load before spec |
| Coder Step 0 / Step 7 | Load + update context |
| Review Check 0 | Verify context was updated |

### Success Metrics (example metrics)

| Metric | Before | After |
|--------|--------|-------|
| Tasks for refactoring | 23 | ≤5 |
| Forgotten files | Multiple | 0 |
| Production issues from refactor | Yes | No |
