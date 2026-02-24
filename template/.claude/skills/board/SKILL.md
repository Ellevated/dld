---
name: board
description: Board of Directors — business architecture before system design. Multi-agent with cross-critique.
model: opus
---

# Board — Совет Директоров

Business architecture: revenue model, channels, org structure, risks — BEFORE system design.

**Activation:** `/board`, "совет директоров", "бизнес-стратегия"
**Input (Greenfield):** `ai/idea/*` from Bootstrap
**Input (Retrofit):** `ai/audit/deep-audit-report.md` + `ai/blueprint/system-blueprint/` + `ai/architect/migration-path.md`
**Output:** `ai/blueprint/business-blueprint.md`

## When to Use

- After `/bootstrap` (Greenfield — Board is mandatory for every project)
- From `/retrofit` (business reassessment after architecture recovery)
- When business strategy needs revision (pivot, new market, pricing change)
- When Architect escalates a business question upstream

**Not for:** Technical decisions (use `/architect`), feature specs (use `/spark`).

---

## Composition

| Director | Worldview | Lens | Kill Question |
|----------|-----------|------|---------------|
| **CPO** | Jeanne Bliss (CCO) | CX = growth engine | "What does user lose if we disappear tomorrow?" |
| **CFO** | Unit Economics | Numbers must converge | "CAC payback < 12 months? If not — business doesn't live" |
| **CMO** | Tim Miller (CRO) | Revenue ops = science | "Which ONE repeatable channel works right now?" |
| **COO** | Keith Rabois (COO Square) | Triage. Barrels vs ammo | "What breaks at ×10? What's agent, what's human?" |
| **CTO** | Piyush Gupta (DBS Bank) | Think like a startup | "If building from scratch — same stack?" |
| **Devil** | Peter Thiel | Contrarian | "What do you know that nobody agrees with?" |
| **Facilitator** | Chief of Staff | Process, NO vote | Agenda + artifacts + gates |

---

### Cost Estimate

Before launching, inform user (non-blocking):

```
Greenfield: "Board: {project} — 14 agents (6 sonnet directors × 2 phases + 1 opus synthesizer + validation), est. ~$8-20. Running..."
Retrofit:   "Board retrofit: {project} — 14 agents + audit/architecture input, est. ~$8-20. Running..."
```

---

## Mode Detection

Board operates in two modes:

| Trigger | Mode | Read Next |
|---------|------|-----------|
| After /bootstrap, "business strategy", "revenue model" | **Greenfield** | `greenfield-mode.md` |
| From /retrofit, "retrofit", "strategy revision", explicit MODE: retrofit | **Retrofit** | `retrofit-mode.md` |

**Default:** Greenfield (if unclear, ask user)

## Modules

| Module | When | Content |
|--------|------|---------|
| `greenfield-mode.md` | Mode = Greenfield | 8-phase process for new projects |
| `retrofit-mode.md` | Mode = Retrofit | KEEP/CHANGE/DROP lens, audit+architect input |

**Flow:**
```
Greenfield: SKILL.md → greenfield-mode.md
Retrofit:   SKILL.md → retrofit-mode.md
```

---

## Business Blueprint Template

```markdown
# Business Blueprint: {Project Name}

**Date:** {today}
**Board Round:** {N}
**Founder Approved:** {date}

---

## Executive Summary
{2-3 paragraphs}

## Target Customer
{Persona with concrete data from CPO research}

## Revenue Model
{Concrete model with numbers from CFO research}

## Go-to-Market
{Channels with CAC estimates from CMO research}

## Operating Model
{Agent/human/hybrid for each process from COO research}

## Technical Constraints
{High-level tech considerations from CTO — NOT architecture}

## Risks & Mitigations
{From Devil's Advocate + all directors}

## Unit Economics
| Metric | Value | Source |
|--------|-------|--------|
| TAM | ... | CFO |
| CAC | ... | CMO |
| LTV | ... | CFO |
| Payback | ... | CFO |

## Decisions Made
| # | Decision | Rationale | Director |
|---|----------|-----------|----------|
| 1 | {decision} | {why} | {who advocated} |

## Open for Architect
{What technical questions Board leaves for Architect to decide}
```

### Retrofit Extension

In retrofit mode, Business Blueprint includes additional sections:

```markdown
## KEEP Decisions
| # | Feature/Line | Rationale | Director |
|---|-------------|-----------|----------|
| 1 | {what to keep} | {why} | {who advocated} |

## CHANGE Decisions
| # | What | From → To | Rationale |
|---|------|-----------|-----------|
| 1 | {what to change} | {current → target} | {why} |

## DROP Decisions
| # | Feature/Line | Rationale | Impact |
|---|-------------|-----------|--------|
| 1 | {what to drop} | {why} | {user impact} |

## Migration Priority
{Which waves from migration-path.md are business-critical}
{Investment split: stabilization % vs features %}
```

---

## Rules

- Board is READ-ONLY for code — never modifies source files
- Board creates files ONLY in `ai/board/` and `ai/blueprint/`
- Each director must cite sources in research
- Founder sees full strategies with trade-offs, not binary approve/reject
- Minimum 2 rounds (even if founder approves R1 — devil must challenge)
- Maximum 4 rounds (diminishing returns)
- In retrofit: NO AUTO-DECIDE. Human ALWAYS chooses.

---

## After Board

```
ai/blueprint/business-blueprint.md  ✓

Greenfield → Next: /architect (designs system architecture within business constraints)
Retrofit   → Next: Stabilization phase (Spark works from migration-path.md)
```
