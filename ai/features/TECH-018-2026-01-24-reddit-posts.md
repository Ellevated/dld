# TECH: [TECH-018] Draft Reddit Posts

**Status:** done | **Priority:** P3 | **Date:** 2026-01-24

## Problem

Need Reddit posts for launch in relevant communities.
Each subreddit has different culture and rules.

## Solution

Create adapted posts for 3 subreddits.

---

## Scope

**In scope:**
- r/ClaudeAI post
- r/programming post
- r/opensource post

**Out of scope:**
- Other subreddits
- Comment engagement strategy

---

## Allowed Files

**New files allowed:**

| # | File | Reason |
|---|------|--------|
| 1 | `ai/launch/reddit-posts.md` | Draft posts |

**FORBIDDEN:** All other files.

---

## Design

### Post Formats

```markdown
# Reddit Posts Draft

## r/ClaudeAI

**Title:** I built a methodology for deterministic AI coding with Claude Code

**Body:**

After months of using Claude Code, I noticed most of my time went to debugging AI-generated code. So I created DLD (Domain-Level Design).

**What it does:**
- Spec-first: Claude writes detailed specs before coding
- Worktree isolation: Each task in its own branch
- Fresh agents: New context per task, no accumulated confusion

**Key insight:** Give Claude explicit structure, get predictable results.

It's open source: [link]

Happy to answer questions about the methodology.

---

## r/programming

**Title:** DLD: An LLM-first architecture pattern for AI-assisted development

**Body:**

I've been exploring how to make AI coding more predictable. The result is DLD (Domain-Level Design).

**The problem:** AI coding tools generate code faster than we can understand it. Result: 90% debugging, 6% features.

**The approach:**
1. Spec-first development (AI researches and specs before implementing)
2. Domain isolation (clear boundaries, explicit dependencies)
3. Fresh context (new agent per task)

**Why it works:** LLMs respond well to explicit structure. DLD provides that structure.

GitHub: [link]

Curious what patterns others have found effective for AI-assisted development.

---

## r/opensource

**Title:** Releasing DLD - open source methodology for LLM-first development

**Body:**

Releasing DLD (Domain-Level Design), a methodology for making AI coding deterministic.

**What's included:**
- 19 documentation files covering principles, patterns, workflows
- 9 "skills" (reusable prompt templates)
- 11 agent prompts
- Project template ready to clone

**License:** MIT

**Built with:** Claude Code + Claude Opus 4.5

Looking for:
- Feedback on the methodology
- Translations (currently English + Russian)
- Examples from other stacks

GitHub: [link]

---

## Notes:
- Don't crosspost immediately (looks spammy)
- Stagger by 1-2 days
- Engage with comments authentically
```

---

## Implementation Plan

### Task 1: Create Reddit posts

**Files:**
- Create: `ai/launch/reddit-posts.md`

**Steps:**
1. Read product-brief.md
2. Research each subreddit's culture
3. Adapt tone for each community
4. Write authentic, non-promotional content

**Acceptance:**
- [ ] 3 distinct posts
- [ ] Adapted for each community
- [ ] No spam/marketing feel
- [ ] Ready to post

---

## Definition of Done

### Functional
- [ ] All 3 posts written
- [ ] Appropriate for each subreddit
- [ ] Authentic tone

### Technical
- [ ] Valid markdown
- [ ] Easy to copy-paste

---

## Autopilot Log

- **2026-01-25**: Created ai/launch/reddit-posts.md
  - r/ClaudeAI: Personal story + "what works for you?" engagement
  - r/programming: Principles-focused, skeptical audience tone
  - r/opensource: Contribution-focused, MIT license prominent
  - Added posting timing recommendations (stagger 1-2 days)
  - Added subreddit-specific engagement notes
