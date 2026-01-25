# TECH: [TECH-020] Example: AI Autonomous Company

**Status:** done | **Priority:** P3 | **Date:** 2026-01-24

## Problem

No examples showing DLD for AI-heavy autonomous systems.
This is a key use case that differentiates DLD.

## Solution

Create example documentation for an AI autonomous company project.

---

## Scope

**In scope:**
- README describing the project
- How AI agents work together
- DLD principles applied
- Architecture decisions

**Out of scope:**
- Actual source code (if private)
- Sensitive business logic

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `examples/ai-autonomous-company/README.md` | Example documentation |

**New directories allowed:**
- `examples/ai-autonomous-company/` — This example

**FORBIDDEN:** All other files.

---

## Design

### Example Structure

```markdown
# AI Autonomous Company

> Multi-agent system for autonomous business operations

## The Problem

Running a company requires coordination between:
- Strategy
- Operations
- Finance
- Customer service

Traditional automation: brittle, requires constant updates
LLM-based: unpredictable, context collapse

## The Solution

DLD-based multi-agent architecture:
- Each business function = domain
- Agents with clear roles and boundaries
- Structured handoffs between agents

## DLD Principles Applied

### 1. Agent Isolation
Each agent has:
- Clear role definition
- Limited scope
- Explicit inputs/outputs

### 2. Structured Handoffs
Agents don't freestyle—they follow protocols:
- spark → defines task
- domain-agent → executes
- review → validates

### 3. Context Management
- Fresh context per task
- No accumulated confusion
- Clear memory boundaries

## Architecture

```
src/
├── domains/
│   ├── strategy/     # Business planning
│   ├── operations/   # Daily operations
│   ├── finance/      # Financial management
│   └── customer/     # Customer interactions
├── agents/
│   ├── strategist/   # Long-term planning
│   ├── operator/     # Task execution
│   ├── accountant/   # Financial decisions
│   └── support/      # Customer handling
└── orchestration/
    └── coordinator/  # Agent coordination
```

## Key Decisions (ADRs)

### ADR-001: Separate Agents per Domain
Why: Prevents context contamination
Trade-off: More complexity, cleaner boundaries

### ADR-002: Structured Handoffs
Why: Predictable agent interactions
Trade-off: Less flexible, more reliable

## Results

- Decision quality: improved
- Error recovery: faster
- Scalability: agents can be added without breaking existing ones

## Lessons Learned

1. ...
2. ...
```

---

## Implementation Plan

### Task 1: Create example README

**Files:**
- Create: `examples/ai-autonomous-company/README.md`

**Steps:**
1. Create directory if not exists
2. Write README based on real project experience
3. Include architecture diagram
4. Add ADRs and lessons learned

**Acceptance:**
- [ ] Shows multi-agent DLD usage
- [ ] Architecture clear
- [ ] Lessons valuable

---

## Definition of Done

### Functional
- [ ] Example complete
- [ ] Shows AI agent orchestration
- [ ] Useful for autonomous systems

### Technical
- [ ] Valid markdown
- [ ] Diagrams render

---

## Autopilot Log

- **2026-01-25**: Created examples/ai-autonomous-company/README.md
  - Multi-agent architecture with CEO/COO/CFO/CSO agents
  - Domain structure: strategy, operations, finance, customer
  - DLD principles: agent isolation, structured handoffs, fresh context
  - 3 ADRs explaining key decisions
  - 4 lessons learned from experimental projects
  - ASCII architecture diagrams
  - "When to use" guidance
