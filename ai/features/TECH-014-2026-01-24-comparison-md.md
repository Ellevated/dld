# TECH: [TECH-014] Create COMPARISON.md

**Status:** queued | **Priority:** P2 | **Date:** 2026-01-24

## Problem

No comparison document exists. Users want to understand how DLD differs from:
- Cursor
- Claude Code (vanilla)
- Superpowers
- Clean Architecture

## Solution

Create COMPARISON.md with fair, factual comparisons.

---

## Scope

**In scope:**
- Compare DLD with 3-4 alternatives
- Feature comparison table
- "When to use what" guidance

**Out of scope:**
- Marketing language
- Unfair criticism of alternatives

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `COMPARISON.md` | Main comparison document |

**FORBIDDEN:** All other files.

---

## Design

### Comparison Structure

```markdown
# DLD Comparison

## DLD vs Cursor

**What Cursor is:** IDE with AI features
**What DLD is:** Methodology for AI-first development

| Aspect | Cursor | DLD |
|--------|--------|-----|
| Type | IDE | Methodology |
| AI Integration | Built-in | Works with any Claude interface |
| Structure | Free-form | Spec-first, domain-driven |
| Learning curve | Low | Medium |

**When to use:**
- Cursor: Quick edits, exploration
- DLD: Production projects, team collaboration

## DLD vs Superpowers

**What Superpowers is:** AI coding assistant extension
**What DLD is:** Complete development methodology

[Similar table and guidance]

## DLD vs Clean Architecture

**What Clean Architecture is:** Software design pattern
**What DLD is:** LLM-optimized architecture pattern

[Comparison of principles]

## Feature Matrix

| Feature | DLD | Cursor | Superpowers | Clean Arch |
|---------|-----|--------|-------------|------------|
| Spec-first | ✓ | - | - | - |
| ...       | ... | ...    | ...         | ...        |

## Summary: When to Use What

- Use DLD when: ...
- Use Cursor when: ...
- Combine: ...
```

---

## Implementation Plan

### Task 1: Create COMPARISON.md

**Files:**
- Create: `COMPARISON.md`

**Steps:**
1. Research each alternative (Cursor, Superpowers, Clean Arch)
2. Write fair comparison for each
3. Create feature matrix
4. Add "when to use" recommendations

**Acceptance:**
- [ ] All comparisons factual
- [ ] No marketing language
- [ ] Helpful for decision-making

---

## Definition of Done

### Functional
- [ ] All alternatives compared
- [ ] Feature matrix complete
- [ ] Recommendations clear

### Technical
- [ ] Valid markdown
- [ ] Tables render correctly

---

## Autopilot Log

- **2026-01-25**: COMPARISON.md already exists with full content
  - DLD vs Cursor comparison complete
  - DLD vs Claude Code (Vanilla) comparison complete
  - DLD vs Superpowers comparison complete
  - DLD vs Clean Architecture comparison complete
  - Feature matrix included
  - "When to use what" guidance present
- No changes needed - already complete
