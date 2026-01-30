# Feature: [TECH-031] YouTube Tutorial Script

**Status:** queued | **Priority:** P2 | **Date:** 2026-01-26

## Why

Video content reaches different audience than text. YouTube is searchable, shareable, and builds trust. 5-minute tutorial can drive significant traffic.

## Context

No video content exists for DLD. Need script before recording.

---

## Scope

**In scope:**
- Write complete video script
- Define scenes and timing
- Include code examples to show on screen
- Write video description and tags

**Out of scope:**
- Actual recording
- Video editing
- Thumbnail creation

---

## Allowed Files

**New files:**
1. `ai/launch/youtube-script.md` — full video script

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Design

### Script Structure (`ai/launch/youtube-script.md`):

```markdown
# YouTube Tutorial: DLD in 5 Minutes

## Metadata
- **Title:** "I Built an AI Autopilot for Coding (And You Can Too)"
- **Duration:** 5:00
- **Tags:** claude code, ai coding, autonomous development, llm, productivity

## Description
Stop debugging AI-generated code. Start shipping features.

DLD (Double-Loop Development) turns chaotic AI coding sessions into deterministic, reproducible development.

🔗 GitHub: https://github.com/Ellevated/dld
💬 Discord: [link]
📖 Docs: [link]

Timestamps:
0:00 The Problem
0:45 The Solution
1:30 Demo: Bootstrap
2:30 Demo: Spark
3:30 Demo: Autopilot
4:30 Results & Next Steps

---

## Script

### [0:00-0:45] The Problem
**Visual:** Screen recording of chaotic AI coding session

**Narration:**
"You know that feeling. You ask Claude to add a feature.
It writes 200 lines of code. Breaks 3 existing features.
And forgets everything by next session.

I was spending 90% of my time debugging AI-generated code.
Only 6% on actual features.

So I built something to fix this."

---

### [0:45-1:30] The Solution
**Visual:** DLD diagram, README scroll

**Narration:**
"DLD — Double-Loop Development.

The idea is simple: specs before code, fresh agents per task.

Instead of letting AI wander, you write a spec first.
Then an autopilot executes it with isolated subagents.
Each task gets fresh context. No cross-contamination.

Let me show you."

---

### [1:30-2:30] Demo: Bootstrap
**Visual:** Terminal, create project

**Narration:**
"Starting a new project takes one command.
[types] npx create-dld my-project

Now let's extract my idea.
[types] claude
[types] /bootstrap

Bootstrap asks me questions to understand what I'm building.
[answers questions]

It creates a structured idea file. This is my source of truth."

---

### [2:30-3:30] Demo: Spark
**Visual:** Terminal, spark command

**Narration:**
"Now I want to add user authentication.
[types] /spark add user authentication

Spark researches best practices via Exa.
It asks clarifying questions.
Then creates a detailed spec.

Look at this — it lists exactly which files can be modified.
This prevents the AI from touching things it shouldn't."

---

### [3:30-4:30] Demo: Autopilot
**Visual:** Terminal, autopilot running

**Narration:**
"Now the magic.
[types] /autopilot

Autopilot takes the spec and executes it.
Each task runs in isolation.
Fresh coder, fresh tester, fresh reviewer.

[shows commits appearing]

See how it commits after each task?
If something breaks, I just revert that one commit.
No more 'fixing the fix for the fix'."

---

### [4:30-5:00] Results & Next Steps
**Visual:** GitHub repo, star button

**Narration:**
"After 3 months of using DLD:
- 90% less debugging
- 8x faster feature delivery
- Clean, reviewable history

Want to try it?
Link in description.
Star the repo if this was helpful.
Join our Discord for questions.

Thanks for watching."

---

## End Screen
- Subscribe button
- Link to GitHub
- Link to next video (when available)
```

---

## Implementation Plan

### Task 1: Create YouTube script
**Type:** create
**Files:** create `ai/launch/youtube-script.md`
**Acceptance:**
- [ ] Complete script with timing
- [ ] Code examples inline
- [ ] Video description and tags
- [ ] Narration for each scene

---

## Definition of Done

### Functional
- [ ] Script is complete and timed to ~5 minutes
- [ ] All demos are realistic and reproducible

### Manual Follow-up
- [ ] Record video following script
- [ ] Edit and upload to YouTube
- [ ] Add link to README
