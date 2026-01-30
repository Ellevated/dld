# Feature: [TECH-029] Dev.to Article Draft

**Status:** done | **Priority:** P2 | **Date:** 2026-01-26

## Why

No content marketing = no discoverability. Dev.to is free, indexed by Google, and has AI/developer audience. Article drives traffic to GitHub.

## Context

Target audience: Developers frustrated with AI coding tools
Goal: Drive traffic to GitHub repo
Platform: Dev.to (free, good SEO, developer audience)

---

## Scope

**In scope:**
- Write article draft in `ai/launch/devto-article.md`
- Include code examples from DLD workflow
- Add call-to-action to GitHub

**Out of scope:**
- Publishing (manual step)
- Images/GIFs (separate task)
- Cross-posting to Medium, Habr

---

## Allowed Files

**New files allowed:**
1. `ai/launch/devto-article.md` — article draft

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Design

### Article Structure:

```markdown
---
title: "I Built an AI Autopilot That Actually Ships Code (Here's How)"
published: false
description: "Stop debugging AI-generated code. Start shipping features. A methodology for deterministic AI development."
tags: ai, productivity, claudecode, opensource
cover_image: [URL to workflow diagram]
---

## The Problem Nobody Talks About

[Hook: "90% debugging, 6% features" stat]
[Personal story of AI coding frustration]
[The real cost: context loss, regression bugs, wasted time]

## What If AI Could Actually Finish What It Started?

[Introduce DLD concept]
[Key insight: specs before code, fresh agents per task]
[Diagram: spark → autopilot → done]

## The Double-Loop

[Explain outer loop (spec) vs inner loop (implementation)]
[Why specs matter: deterministic, reproducible, auditable]
[Code example: spec file]

## Fresh Agents = No Cross-Contamination

[Explain problem: context pollution]
[Solution: fresh subagent per task]
[Diagram: worktree isolation]

## Real Results

[Before/after comparison]
[Metrics from examples]
[Quote or testimonial if available]

## Try It Yourself

\`\`\`bash
npx create-dld my-project
cd my-project
claude
/bootstrap
\`\`\`

[Link to GitHub]
[Link to docs]

## The Catch

[Be honest: requires Claude Code subscription]
[Learning curve for specs]
[Not magic — requires discipline]

## Conclusion

[Call to action: star on GitHub]
[Invite to contribute]
```

---

## Implementation Plan

### Task 1: Write article draft
**Type:** create
**Files:** create `ai/launch/devto-article.md`
**Acceptance:**
- [ ] Full article with all sections
- [ ] Code examples included
- [ ] Links to GitHub repo
- [ ] Honest about limitations

---

## Definition of Done

### Functional
- [ ] Article draft ready for review
- [ ] Code examples are accurate
- [ ] Links work

### Publishing (Manual)
- [ ] Copy to Dev.to
- [ ] Add cover image
- [ ] Set tags
- [ ] Publish
