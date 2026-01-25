# TECH: [TECH-023] Comparison Table Image

**Status:** in_progress | **Priority:** P3 | **Date:** 2026-01-24

## Problem

Need a clean comparison table image for Twitter/social media.
Markdown tables don't look good in tweets.

## Solution

Create comparison table as Mermaid or describe format for image creation.

---

## Scope

**In scope:**
- Comparison table content
- Mermaid version (if possible)
- Specifications for image creation

**Out of scope:**
- Actual PNG generation (manual or external tool)
- Design work

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `assets/comparison-table.md` | Table content and specs |

**FORBIDDEN:** All other files.

---

## Design

### Comparison Table Content

| Feature | DLD | Cursor | Claude Code | Superpowers |
|---------|:---:|:------:|:-----------:|:-----------:|
| Spec-First | ✓ | - | - | - |
| Worktree Isolation | ✓ | - | - | ~ |
| Fresh Context/Task | ✓ | - | - | ~ |
| Domain-Driven | ✓ | - | - | - |
| Auto-Commit | ✓ | - | - | ✓ |
| Quality Gates | ✓ | - | - | ~ |
| IDE Integration | - | ✓ | - | ✓ |
| Works Standalone | ✓ | - | ✓ | - |

### Image Specifications

```
Size: 1200x630 (Twitter card)
Background: Dark (#1a1a2e)
Text: White (#ffffff)
Accent: Blue (#4a9eff)
Font: Inter or system sans-serif
Checkmarks: Green (#22c55e)
X marks: Red (#ef4444)
Partial: Yellow (#eab308)
```

---

## Implementation Plan

### Task 1: Create comparison table spec

**Files:**
- Create: `assets/comparison-table.md`

**Steps:**
1. Create assets directory if not exists
2. Write table content
3. Add image specifications
4. Include alt text for accessibility

**Acceptance:**
- [ ] Table content complete
- [ ] Specs clear for image creation
- [ ] Alt text included

---

## Definition of Done

### Functional
- [ ] Table content accurate
- [ ] Ready for image creation
- [ ] Specs complete

### Technical
- [ ] Valid markdown
- [ ] Clear formatting

---

## Notes

This spec creates the content. Actual image creation may require:
- Figma/Canva
- Screenshot of HTML table
- External design tool

---

## Autopilot Log

*(Filled by Autopilot during execution)*
