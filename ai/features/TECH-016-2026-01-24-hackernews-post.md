# TECH: [TECH-016] Draft HackerNews Post

**Status:** queued | **Priority:** P2 | **Date:** 2026-01-24

## Problem

Need a HackerNews "Show HN" post for launch.
Must be concise, no marketing speak, technically credible.

## Solution

Create draft post following HN conventions.

---

## Scope

**In scope:**
- "Show HN" title
- Body text (~200 words)
- Key differentiators

**Out of scope:**
- Comments strategy
- Follow-up posts

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `ai/launch/hackernews-post.md` | Draft post |

**New directories allowed:**
- `ai/launch/` — Launch content directory

**FORBIDDEN:** All other files.

---

## Design

### HN Post Format

```markdown
# HackerNews Post Draft

## Title
Show HN: DLD – LLM-First Architecture for AI Coding

## Body

Hi HN,

I've been building with Claude Code for [X months] and noticed a pattern:
90% of my time was debugging AI-generated code, only 6% on actual features.

DLD is a methodology that fixes this through:
- Spec-first development (AI writes specs before code)
- Worktree isolation (each task in its own branch)
- Fresh context (new agent per task, no accumulated confusion)

Key insight: LLMs work better with explicit structure than free-form coding.

What's different from Cursor/Superpowers:
- Not an IDE or plugin — a methodology
- Works with any Claude interface
- Domain-driven, not file-driven

Try it: [link]
Docs: [link]

Built with Claude Opus 4.5. Happy to answer questions.

---

## Notes for posting:
- Post weekday morning (PST)
- Don't ask for upvotes
- Respond to every comment
```

---

## Implementation Plan

### Task 1: Create ai/launch/ directory and post

**Files:**
- Create: `ai/launch/hackernews-post.md`

**Steps:**
1. Create `ai/launch/` directory if not exists
2. Read product-brief.md for key messaging
3. Read persona.md for audience understanding
4. Write HN-appropriate post
5. Keep under 200 words

**Acceptance:**
- [ ] No marketing speak
- [ ] Technically accurate
- [ ] Under 200 words
- [ ] Ready to copy-paste

---

## Definition of Done

### Functional
- [ ] Post is HN-appropriate
- [ ] No fluff or marketing
- [ ] Clear value proposition

### Technical
- [ ] Valid markdown
- [ ] Easy to copy-paste

---

## Autopilot Log

*(Filled by Autopilot during execution)*
