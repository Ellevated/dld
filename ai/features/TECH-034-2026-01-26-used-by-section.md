# Feature: [TECH-034] "Used By" Section in README

**Status:** done | **Priority:** P2 | **Date:** 2026-01-26

## Why

Social proof drives adoption. "Used By" section shows real projects using DLD, building trust. Even without big names, showing ANY real usage helps.

## Context

No social proof in README currently. Need template ready for when projects exist.

---

## Scope

**In scope:**
- Add "Used By" section template to README
- Create testimonial collection guide
- Define criteria for inclusion

**Out of scope:**
- Actually collecting testimonials (ongoing manual work)
- Reaching out to users

---

## Allowed Files

**Modify:**
1. `README.md` — add "Used By" section

**New files:**
2. `ai/launch/testimonial-guide.md` — how to collect and format testimonials

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Design

### README "Used By" Section (before Contributing):

```markdown
---

## Used By

> "DLD cut my debugging time from hours to minutes. The spec-first approach changed how I think about AI coding."
> — **@username**, [Project Name](https://github.com/user/project)

### Projects Using DLD

| Project | Description | Stars |
|---------|-------------|-------|
| [Example Project](link) | Brief description | ⭐ 100+ |

*Using DLD? [Add your project](https://github.com/Ellevated/dld/issues/new?template=showcase.md)*

---
```

### Issue Template for Showcase (`ISSUE_TEMPLATE/showcase.md`):

```markdown
---
name: 🎨 Showcase
about: Share your project built with DLD
title: "[Showcase] Project Name"
labels: showcase
assignees: ''
---

## Project Info

**Name:**
**GitHub/URL:**
**Description:**

## How DLD Helped

<!-- What problem did DLD solve for you? -->

## Testimonial (optional)

<!-- A short quote we can use in README -->

## Screenshots (optional)

<!-- Any visuals showing DLD in action -->
```

### Testimonial Collection Guide (`ai/launch/testimonial-guide.md`):

```markdown
# Testimonial Collection Guide

## Why Collect Testimonials

- Social proof increases conversion
- Real stories are more compelling than features
- Shows DLD works for different use cases

## Where to Find Users

1. **Discord** — active users asking questions
2. **GitHub Issues** — people who fixed bugs or contributed
3. **Twitter/X** — mentions of DLD
4. **Reddit** — posts in r/ClaudeAI, r/programming

## How to Ask

### Template Message

```
Hey [Name]!

I noticed you're using DLD for [project/context]. That's awesome!

Would you be open to sharing a quick testimonial? Just 1-2 sentences about your experience.

Examples:
- "DLD reduced my debugging time by X%"
- "The spec-first approach changed how I work with AI"
- "Finally, AI coding that doesn't break everything"

No pressure—just thought I'd ask! 🙏
```

### Follow-up Questions (if they agree)

1. What was your biggest pain point before DLD?
2. What specific improvement did you notice?
3. Would you recommend DLD? Why?
4. Can we use your GitHub handle and project name?

## Testimonial Format

```markdown
> "[Quote - 1-2 sentences, specific benefit]"
> — **@github_handle**, [Project Name](url)
```

### Good Examples

> "DLD turned my 3-hour debugging sessions into 15-minute reviews. The fresh subagent approach is genius."
> — **@developer**, [project-name](url)

> "I was skeptical about another AI methodology. Then I tried spec-first development. Now I can't go back."
> — **@developer**, [project-name](url)

### Bad Examples (too vague)

> "Great tool!" — lacks specificity
> "DLD is amazing" — no concrete benefit
> "I like it" — not quotable

## Criteria for README Inclusion

1. **Real project** — must have GitHub repo or live URL
2. **Verifiable** — we can confirm they use DLD
3. **Specific** — quote mentions concrete benefit
4. **Permission** — explicit OK to use their name

## Storage

Keep approved testimonials in: `ai/launch/testimonials.md`

Format:
```markdown
## Approved Testimonials

### @username - Project Name
- **Date collected:** YYYY-MM-DD
- **Permission:** Yes (Discord DM / Email / GitHub)
- **Quote:** "..."
- **URL:** https://...
```

## Goal

- **Month 1:** 3 testimonials
- **Month 3:** 10 testimonials
- **Month 6:** "Used By" section with recognizable projects
```

---

## Implementation Plan

### Task 1: Add "Used By" section to README
**Type:** edit
**Files:** modify `README.md`
**Acceptance:**
- [ ] Section exists before Contributing
- [ ] Template testimonial format shown
- [ ] Link to showcase issue template
- [ ] Table for projects (empty or with placeholder)

### Task 2: Create showcase issue template
**Type:** create
**Files:** create `.github/ISSUE_TEMPLATE/showcase.md`
**Acceptance:**
- [ ] Template has all required fields
- [ ] Label set to "showcase"

### Task 3: Create testimonial guide
**Type:** create
**Files:** create `ai/launch/testimonial-guide.md`
**Acceptance:**
- [ ] Collection strategy documented
- [ ] Message templates included
- [ ] Good/bad examples shown

### Execution Order
1 → 2 → 3

---

## Definition of Done

### Functional
- [ ] README has "Used By" section
- [ ] Showcase template works
- [ ] Collection guide is actionable

### Manual Follow-up
- [ ] Start collecting testimonials
- [ ] Update README as testimonials come in
