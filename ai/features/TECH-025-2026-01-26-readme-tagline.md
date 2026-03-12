# Feature: [TECH-025] README Tagline Optimization

**Status:** done | **Priority:** P2 | **Date:** 2026-01-26

## Why

Current tagline "Transform AI coding chaos into deterministic development" is abstract. For GitHub discoverability need concrete, searchable, action-oriented tagline.

## Context

README.md has:
- Line 1: `# DLD: LLM-First Architecture`
- Line 3: `> Transform AI coding chaos into deterministic development`

Goal: Make it clearer WHAT this is and WHO it's for.

---

## Scope

**In scope:**
- Update tagline in README.md
- Add "What is DLD" one-liner

**Out of scope:**
- Other README changes
- Badges changes

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- N/A — README.md is root documentation

### Step 2: BY TERM — grep entire project
- N/A — tagline is unique to README

### Step 3: CHECKLIST
- [ ] No code affected
- [ ] Only documentation change

### Verification
- [ ] All found files added to Allowed Files ✓

---

## Allowed Files

**ONLY these files may be modified:**
1. `README.md` — update tagline

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Action-Oriented Tagline
Focus on WHAT user gets:
```
> Turn Claude Code into an Autonomous Developer
```

### Approach 2: Problem-Solution Tagline
Focus on pain point:
```
> Stop debugging AI code. Start shipping features.
```

### Approach 3: SEO-Friendly Tagline
Include keywords:
```
> Autonomous AI Development Workflow for Claude Code
```

### Selected: Hybrid (1 + 3)

```markdown
# DLD: Double-Loop Development

> Turn Claude Code into an Autonomous Developer

A methodology for deterministic, spec-driven AI development. Write specs, not code.
```

**Rationale:**
- "Turn X into Y" — clear value prop
- "Autonomous Developer" — matches user intent
- Subtitle adds context without overwhelming
- Keeps "Double-Loop Development" for branding

---

## Design

### Current (lines 1-3):
```markdown
# DLD: LLM-First Architecture

> Transform AI coding chaos into deterministic development
```

### New:
```markdown
# DLD: Double-Loop Development

> Turn Claude Code into an Autonomous Developer

**Write specs, not code.** A methodology for deterministic AI development with fresh subagents, worktree isolation, and automatic rollback.
```

---

## Implementation Plan

### Task 1: Update README header
**Type:** edit
**Files:** modify `README.md`
**Acceptance:**
- [ ] Title updated to "DLD: Double-Loop Development"
- [ ] Tagline updated to action-oriented version
- [ ] Added one-liner explanation

---

## Definition of Done

### Functional
- [ ] README header is more compelling
- [ ] Tagline is action-oriented

### Technical
- [ ] No broken links
- [ ] Renders correctly on GitHub
