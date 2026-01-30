# Feature: [TECH-032] Discord Community Setup

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-26

## Why

Community = retention. Discord lets users ask questions, share wins, suggest features. It's also social proof — active Discord = active project.

## Context

No community channels exist. Users have no way to get help or connect.

---

## Scope

**In scope:**
- Create welcome message template
- Create channel structure guide
- Create bot rules template
- Add Discord link placeholder to README
- Add Discord link to CONTRIBUTING.md

**Out of scope:**
- Actually creating Discord server (manual)
- Bot development
- Moderation setup

---

## Allowed Files

**New files:**
1. `ai/launch/discord-setup-guide.md` — complete setup instructions

**Modify:**
2. `README.md` — add community section with Discord link
3. `CONTRIBUTING.md` — add Discord link for questions

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Design

### README addition (after Documentation section):

```markdown
---

## Community

Join our Discord for help, discussions, and feature requests:

[![Discord](https://img.shields.io/discord/XXXXXXXXX?color=7289da&label=Discord&logo=discord&logoColor=white)](https://discord.gg/INVITE_CODE)

---
```

### Discord Setup Guide (`ai/launch/discord-setup-guide.md`):

```markdown
# Discord Server Setup Guide

## Server Creation
1. Go to discord.com, create new server
2. Name: "DLD Community"
3. Icon: Use DLD logo or create simple one

## Channel Structure

### Information
- #welcome (read-only)
  - Server rules
  - Quick start links
  - Role selection

- #announcements (read-only)
  - New versions
  - Major updates
  - Community highlights

### Community
- #general
  - General discussion
  - Introductions

- #help
  - Technical questions
  - Troubleshooting
  - Slow mode: 30 seconds

- #showcase
  - Share projects built with DLD
  - Before/after stories

- #ideas
  - Feature requests
  - Suggestions
  - Voting via reactions

### Development
- #contributors
  - For active contributors
  - PR discussions
  - Architecture decisions

## Welcome Message

\`\`\`
# Welcome to DLD Community! 🎯

DLD (Double-Loop Development) is a methodology for deterministic AI development with Claude Code.

## Quick Links
📚 **GitHub:** https://github.com/Ellevated/dld
📖 **Docs:** https://github.com/Ellevated/dld/tree/main/docs
🚀 **Quick Start:** \`npx create-dld my-project\`

## Getting Started
1. Read the README on GitHub
2. Try the quick start
3. Ask questions in #help
4. Share your projects in #showcase

## Rules
1. Be respectful
2. Search before asking
3. Share context when asking for help
4. No spam or self-promotion

Welcome aboard! 👋
\`\`\`

## Bot Setup (Optional)

### MEE6 or Carl-bot
- Auto-role on join
- Welcome message DM
- Reaction roles for notifications

### Useful Commands
- `/help` — Link to docs
- `/quickstart` — Quick start command
- `/github` — Link to repo

## Moderation Settings
- Slow mode: 30s in #help
- Media in #showcase only
- Auto-mod for spam links
- Verification level: Low

## Invite Link Settings
- Never expires
- Max uses: Unlimited
- Grant temporary membership: No
```

### CONTRIBUTING.md addition:

```markdown
## Questions?

- Open a [Discussion](https://github.com/Ellevated/dld/discussions)
- Join our [Discord](https://discord.gg/INVITE_CODE)
```

---

## Implementation Plan

### Task 1: Create Discord setup guide
**Type:** create
**Files:** create `ai/launch/discord-setup-guide.md`
**Acceptance:**
- [ ] Channel structure defined
- [ ] Welcome message ready to copy
- [ ] Bot recommendations included

### Task 2: Add Community section to README
**Type:** edit
**Files:** modify `README.md`
**Acceptance:**
- [ ] Community section with Discord badge
- [ ] Placeholder invite code (INVITE_CODE)

### Task 3: Update CONTRIBUTING.md
**Type:** edit
**Files:** modify `CONTRIBUTING.md`
**Acceptance:**
- [ ] Discord link added
- [ ] Discussion link added

### Execution Order
1 → 2 → 3

---

## Definition of Done

### Functional
- [ ] README has community section
- [ ] Setup guide is complete

### Manual Follow-up
- [ ] Create actual Discord server
- [ ] Replace INVITE_CODE placeholders
- [ ] Set up channels per guide
