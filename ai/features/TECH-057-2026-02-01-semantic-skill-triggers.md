# Tech: [TECH-057] Semantic Skill Auto-Selection

**Status:** done | **Priority:** P2 | **Date:** 2026-02-01

## Why

Users must explicitly invoke `/spark`, `/autopilot`. Industry best practice: Claude auto-selects skill based on user intent and file context. Reduces friction, improves UX.

## Context

Current: User says "add login feature" → must type `/spark`

Industry 2026: User says "add login feature" → Claude recognizes intent → auto-invokes spark

This is achieved via semantic triggers in skill descriptions.

---

## Scope

**In scope:**
- Add trigger keywords/patterns to all skill SKILL.md frontmatter
- Document auto-selection behavior in CLAUDE.md
- Test with common user phrases

**Out of scope:**
- Changing skill behavior
- Adding new skills
- ML-based intent classification

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `template/.claude/skills/spark/SKILL.md` | modify | Add triggers |
| 2 | `template/.claude/skills/autopilot/SKILL.md` | modify | Add triggers |
| 3 | `template/.claude/skills/council/SKILL.md` | modify | Add triggers |
| 4 | `template/.claude/skills/audit/SKILL.md` | modify | Add triggers |
| 5 | `template/.claude/skills/reflect/SKILL.md` | modify | Add triggers |
| 6 | `template/.claude/skills/scout/SKILL.md` | modify | Add triggers |
| 7 | `template/.claude/skills/bootstrap/SKILL.md` | modify | Add triggers |
| 8 | `template/CLAUDE.md` | modify | Document behavior |
| 9 | `.claude/skills/spark/SKILL.md` | modify | Add triggers (current project) |
| 10 | `.claude/skills/autopilot/SKILL.md` | modify | Add triggers (current project) |
| 11 | `.claude/skills/council/SKILL.md` | modify | Add triggers (current project) |
| 12 | `.claude/skills/audit/SKILL.md` | modify | Add triggers (current project) |
| 13 | `.claude/skills/reflect/SKILL.md` | modify | Add triggers (current project) |
| 14 | `.claude/skills/scout/SKILL.md` | modify | Add triggers (current project) |
| 15 | `.claude/skills/bootstrap/SKILL.md` | modify | Add triggers (current project) |

---

## Approaches

### Approach 1: Keyword List in Frontmatter

**Source:** affaan-m/everything-claude-code

**Summary:** Add `triggers:` field with keywords and file patterns

**Pros:**
- Simple to implement
- Easy to maintain
- Claude Code supports this natively

**Cons:**
- May have false positives

### Approach 2: Full Description Block

**Source:** Claude Code docs

**Summary:** Rich description with "Use when..." patterns

**Pros:**
- More nuanced matching
- Can express complex conditions

**Cons:**
- More verbose

### Selected: Approach 2

**Rationale:** Richer descriptions allow Claude to make better decisions. Follows Claude Code best practices.

---

## Design

### Trigger Format

```yaml
---
name: spark
description: |
  Feature specification and research agent.

  Use when:
  - User mentions: "add feature", "new functionality", "implement X"
  - User mentions: "create spec", "write specification"
  - User asks about a bug without clear solution
  - Files match: ai/features/*.md (viewing/editing specs)

  Do NOT use when:
  - User has existing spec and wants implementation (use autopilot)
  - User wants quick research only (use scout)
---
```

### Skill Trigger Matrix

| Skill | Trigger Phrases | File Patterns |
|-------|-----------------|---------------|
| spark | "add feature", "new X", "create spec", "bug analysis" | `ai/features/*.md` |
| autopilot | "implement", "execute spec", "run tasks" | spec with `status: queued` |
| council | "should we", "which approach", "debate", "decide" | architectural files |
| audit | "analyze", "check code", "review quality" | `src/**/*.py` |
| reflect | "what did we learn", "update rules" | `ai/diary/**` |
| scout | "research", "find docs", "how does X work" | — |
| bootstrap | "new project", "start fresh", "day 0" | empty `ai/idea/` |

---

## Implementation Plan

### Task 1: Update spark triggers ✅

**Files:**
- Modify: `template/.claude/skills/spark/SKILL.md`
- Modify: `.claude/skills/spark/SKILL.md`

**Steps:**
1. Add description block with "Use when" patterns
2. Add "Do NOT use when" exclusions
3. Test common phrases

**Acceptance:**
- [x] Triggers documented in skill

### Task 2: Update autopilot triggers ✅

**Files:**
- Modify: `template/.claude/skills/autopilot/SKILL.md`
- Modify: `.claude/skills/autopilot/SKILL.md`

**Steps:**
1. Add description block
2. Differentiate from spark clearly

**Acceptance:**
- [x] Clear separation from spark

### Task 3: Update remaining skills ✅

**Files:**
- Modify: council, audit, reflect, scout, bootstrap SKILL.md (both template/ and .claude/)

**Steps:**
1. Add triggers to each skill
2. Ensure no overlap conflicts

**Acceptance:**
- [x] All skills have triggers

### Task 4: Document in CLAUDE.md ✅

**Files:**
- Modify: `template/CLAUDE.md`

**Steps:**
1. Add section explaining auto-selection
2. Show how to override with explicit /command

**Acceptance:**
- [x] User understands auto-selection

### Execution Order

Task 1 → Task 2 → Task 3 → Task 4

---

## Definition of Done

### Functional
- [x] All skills have trigger descriptions
- [x] No conflicting triggers between skills
- [x] Override with explicit /command works

### Technical
- [x] Follows Claude Code description format

### Documentation
- [x] Auto-selection documented in CLAUDE.md

---

## Autopilot Log

**2026-02-02 (manual execution):**
- Tasks 1-3 completed: Added semantic triggers to all 7 skills
- Format: AUTO-ACTIVATE when / Also activate when / DO NOT USE when
- Both template/ and .claude/ updated for sync
- Research: Scout found 20% native activation rate, 84% with commitment hooks
- Decision: Start with descriptions only, add hooks later if needed
