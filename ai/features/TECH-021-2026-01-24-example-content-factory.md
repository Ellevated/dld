# TECH: [TECH-021] Example: Content Factory

**Status:** in_progress | **Priority:** P3 | **Date:** 2026-01-24

## Problem

No example showing DLD for content generation pipelines.
Content automation is a common AI use case.

## Solution

Create example documentation for a content factory project.

---

## Scope

**In scope:**
- README describing the project
- Content pipeline architecture
- DLD principles applied
- Quality control approach

**Out of scope:**
- Actual source code
- Proprietary content strategies

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `examples/content-factory/README.md` | Example documentation |

**New directories allowed:**
- `examples/content-factory/` — This example

**FORBIDDEN:** All other files.

---

## Design

### Example Structure

```markdown
# Content Factory

> Automated content generation pipeline with quality control

## The Problem

Content creation at scale requires:
- Research
- Writing
- Editing
- Publishing

LLM content risks:
- Hallucinations
- Inconsistent tone
- Quality variance

## The Solution

DLD-based content pipeline:
- Staged generation (research → outline → draft → edit)
- Quality gates between stages
- Domain-specific knowledge injection

## DLD Principles Applied

### 1. Staged Processing
Each stage is isolated:
1. Research agent → facts only
2. Outline agent → structure only
3. Writer agent → first draft
4. Editor agent → polish

### 2. Quality Gates
Between each stage:
- Fact-checking
- Style consistency
- Brand alignment

### 3. Domain Knowledge
Each content type has:
- Glossary (terms, definitions)
- Style guide (tone, format)
- Examples (good content samples)

## Architecture

```
src/
├── domains/
│   ├── research/     # Fact gathering
│   ├── writing/      # Content creation
│   ├── editing/      # Quality improvement
│   └── publishing/   # Distribution
├── agents/
│   ├── researcher/   # Gathers facts
│   ├── outliner/     # Creates structure
│   ├── writer/       # Drafts content
│   └── editor/       # Polishes content
└── quality/
    ├── fact-checker/ # Verifies claims
    └── style-checker/# Ensures consistency
```

## Workflow

```
/spark "Create blog post about X"
    ↓
Research Agent → Facts + Sources
    ↓ [fact-check gate]
Outline Agent → Structure
    ↓ [structure review]
Writer Agent → Draft
    ↓ [style check]
Editor Agent → Final
    ↓
Publishing Domain → Distribute
```

## Results

- Content velocity: X → Y articles/day
- Quality score: X% → Y%
- Revision rounds: X → Y

## Lessons Learned

1. Research quality determines final quality
2. Style guides prevent drift
3. Human review still needed for sensitive topics
```

---

## Implementation Plan

### Task 1: Create example README

**Files:**
- Create: `examples/content-factory/README.md`

**Steps:**
1. Create directory if not exists
2. Write README based on real content pipeline experience
3. Include workflow diagram
4. Add quality control details

**Acceptance:**
- [ ] Shows content pipeline with DLD
- [ ] Quality gates explained
- [ ] Workflow clear

---

## Definition of Done

### Functional
- [ ] Example complete
- [ ] Shows content automation
- [ ] Quality approach clear

### Technical
- [ ] Valid markdown
- [ ] Diagrams render

---

## Autopilot Log

*(Filled by Autopilot during execution)*
