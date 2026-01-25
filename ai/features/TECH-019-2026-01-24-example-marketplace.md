# TECH: [TECH-019] Example: Marketplace Launch

**Status:** done | **Priority:** P3 | **Date:** 2026-01-24

## Problem

No real-world examples showing DLD in action.
Users need to see how DLD works on actual projects.

## Solution

Create example documentation for a marketplace launch automation project.

---

## Scope

**In scope:**
- README describing the project
- Problem it solved
- DLD principles applied
- Results (anonymized if needed)
- Structure diagram

**Out of scope:**
- Actual source code (if private)
- Sensitive business data

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `examples/marketplace-launch/README.md` | Example documentation |

**New directories allowed:**
- `examples/` — Examples directory
- `examples/marketplace-launch/` — This example

**FORBIDDEN:** All other files.

---

## Design

### Example Structure

```markdown
# Marketplace Launch Automation

> SKU launch automation for major marketplaces

## The Problem

Launching products on marketplaces (Ozon, Wildberries, etc.) requires:
- Content preparation
- Price calculations
- Compliance checks
- Multi-platform publishing

Manual process: X hours per SKU
Error rate: Y%

## The Solution

Automated pipeline using DLD principles:
- Domain: catalog, pricing, compliance, publishing
- Agents: content-writer, price-calculator, compliance-checker
- Workflow: spark → autopilot → done

## DLD Principles Applied

### 1. Domain Isolation
Each marketplace = separate domain with clear boundaries.

### 2. Spec-First
Every SKU launch starts with a spec:
- Target marketplaces
- Content requirements
- Price rules

### 3. Fresh Context
Each SKU processed by fresh agent—no cross-contamination.

## Architecture

```
src/
├── domains/
│   ├── catalog/      # Product data management
│   ├── pricing/      # Price calculation
│   ├── compliance/   # Marketplace rules
│   └── publishing/   # Multi-platform publishing
└── api/
    └── launcher/     # SKU launch orchestration
```

## Results

- Launch time: X hours → Y minutes
- Error rate: X% → Y%
- Throughput: X SKUs/day → Y SKUs/day

## Lessons Learned

1. ...
2. ...
3. ...
```

---

## Implementation Plan

### Task 1: Create example directory and README

**Files:**
- Create: `examples/marketplace-launch/README.md`

**Steps:**
1. Create `examples/` directory if not exists
2. Create `examples/marketplace-launch/` directory
3. Write README based on real project experience
4. Include structure diagram
5. Add results (anonymized if needed)

**Acceptance:**
- [ ] Compelling story
- [ ] Shows DLD value
- [ ] Structure clear
- [ ] Results included

---

## Definition of Done

### Functional
- [ ] Example complete
- [ ] Shows real DLD usage
- [ ] Useful for new users

### Technical
- [ ] Valid markdown
- [ ] Diagrams render

---

## Autopilot Log

- **2026-01-25**: Created examples/marketplace-launch/README.md
  - Created examples/ directory structure
  - Comprehensive README with problem/solution story
  - DLD principles applied: domain isolation, spec-first, fresh context, file limits
  - Architecture diagram (ASCII)
  - Results table with before/after metrics
  - 4 lessons learned from real experience
  - Tech stack and migration guidance
