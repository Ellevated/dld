# Feature: [TECH-033] Product Hunt Launch Assets

**Status:** queued | **Priority:** P2 | **Date:** 2026-01-26

## Why

Product Hunt can drive 1000+ visitors in one day. But success requires preparation: assets, description, timing, response strategy. This spec prepares everything needed.

## Context

Product Hunt launch requirements:
- Logo (240x240)
- Gallery images (4-6)
- Tagline (60 chars)
- Description (260 chars)
- Maker comment template

---

## Scope

**In scope:**
- Create launch preparation guide
- Write all copy (tagline, description, first comment)
- Define gallery image requirements
- Create launch day checklist

**Out of scope:**
- Actual asset creation (Figma/design work)
- Scheduling the launch
- Social media posts (separate spec TECH-017, TECH-018)

---

## Allowed Files

**New files:**
1. `ai/launch/producthunt-launch-kit.md` — complete launch preparation

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Design

### Product Hunt Launch Kit (`ai/launch/producthunt-launch-kit.md`):

```markdown
# Product Hunt Launch Kit

## Product Info

**Name:** DLD
**Tagline (60 chars max):**
> Turn Claude Code into an Autonomous Developer

**Description (260 chars max):**
> DLD is a methodology that transforms chaotic AI coding into deterministic development. Write specs, not code. Fresh subagents per task. Automatic rollback. Stop debugging AI mistakes—start shipping features.

**Topics:**
- Developer Tools
- Artificial Intelligence
- Productivity
- Open Source

**Pricing:** Free

**Links:**
- Website: https://github.com/Ellevated/dld
- GitHub: https://github.com/Ellevated/dld

---

## Assets Checklist

### Logo (Required)
- [ ] Size: 240x240 px
- [ ] Format: PNG, transparent background
- [ ] Style: Simple, recognizable at small size
- [ ] Concept: "DLD" letters or double-loop symbol

### Gallery Images (4-6 recommended)
1. [ ] **Hero image** — Workflow diagram (spark → autopilot → done)
2. [ ] **Problem/Solution** — Before/after comparison
3. [ ] **Demo GIF** — Quick workflow demonstration
4. [ ] **Architecture** — Project structure visualization
5. [ ] **Terminal screenshot** — Actual commands in action
6. [ ] **Results** — Metrics or testimonial

**Specifications:**
- Size: 1270x760 px (recommended)
- Format: PNG, JPG, or GIF
- First image is thumbnail — make it compelling

---

## Maker Comment (Post immediately after launch)

```
Hey Product Hunt! 👋

I'm [Name], creator of DLD.

**The problem:** I was spending 90% of my time debugging AI-generated code. Claude would write features, break existing ones, and forget everything by next session.

**The solution:** DLD (Double-Loop Development) — a methodology that makes AI coding deterministic:

1. Write specs before code (not after)
2. Fresh subagent for each task (no context pollution)
3. Automatic rollback if something breaks

**Quick start:**
\`\`\`
npx create-dld my-project
cd my-project
claude
/bootstrap
\`\`\`

**What I'd love feedback on:**
- Is the documentation clear enough?
- What features would make this more useful?
- Any pain points I haven't addressed?

Happy to answer any questions! 🙏
```

---

## Launch Timing

**Best days:** Tuesday, Wednesday, Thursday
**Best time:** 00:01 AM PT (to maximize 24-hour window)
**Avoid:** Weekends, holidays, major tech announcements

### Countdown Checklist

**1 Week Before:**
- [ ] All assets ready and uploaded
- [ ] Description finalized
- [ ] Maker comment drafted
- [ ] Social posts scheduled (Twitter, Reddit, LinkedIn)
- [ ] Discord announcement prepared
- [ ] Email to supporters drafted

**1 Day Before:**
- [ ] Preview link shared with close supporters
- [ ] Browser tabs ready (PH, GitHub, Discord, Twitter)
- [ ] Response templates prepared
- [ ] Sleep early!

**Launch Day:**
- [ ] Post maker comment immediately (within 5 min)
- [ ] Share on Twitter, LinkedIn
- [ ] Post in relevant communities (don't spam)
- [ ] Respond to EVERY comment within 1 hour
- [ ] Thank every upvoter (if possible)
- [ ] Post updates throughout the day

**Day After:**
- [ ] Thank you post on social media
- [ ] Summary of feedback
- [ ] Create issues for suggested features

---

## Response Templates

### Positive Feedback
> Thanks so much! Really appreciate the support. Let me know if you try it out—would love to hear how it goes! 🙏

### Technical Question
> Great question! [Answer]. If you want to dig deeper, check out [doc link] or join our Discord for real-time help.

### Feature Request
> Love this idea! I've added it to our backlog: [GitHub issue link]. Would you mind adding any additional context there?

### Criticism
> Thanks for the honest feedback. You raise a valid point about [X]. We're working on [Y] to address this. Any specific suggestions?

---

## Success Metrics

**Goals:**
- Top 5 of the day
- 200+ upvotes
- 50+ comments
- 500+ GitHub visitors

**Tracking:**
- Product Hunt analytics
- GitHub traffic (Settings → Insights → Traffic)
- Discord joins
- npm downloads
```

---

## Implementation Plan

### Task 1: Create Product Hunt launch kit
**Type:** create
**Files:** create `ai/launch/producthunt-launch-kit.md`
**Acceptance:**
- [ ] All copy written (tagline, description, comment)
- [ ] Asset specifications defined
- [ ] Launch day checklist complete
- [ ] Response templates included

---

## Definition of Done

### Functional
- [ ] Launch kit is complete and actionable

### Manual Follow-up
- [ ] Create actual assets in Figma/Canva
- [ ] Upload to Product Hunt
- [ ] Schedule launch
- [ ] Execute launch day plan
