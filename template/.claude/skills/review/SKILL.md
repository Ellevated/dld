---
name: review
description: Code Quality Reviewer (Stage 2) - prevents tech debt and duplication
agent: .claude/agents/review.md
---

# Review — Code Quality Reviewer (Stage 2)

Prevent tech debt BEFORE it accumulates.

**Stage 2 of Two-Stage Review** — runs AFTER Spec Reviewer (Stage 1) approved.

**Activation:** Automatic in autopilot (after Spec Reviewer approved, before commit)

## Mission

**Don't let project become a pile of scripts and duplicate code.**

## When

1. **Automatic** — In autopilot cycle after documenter, BEFORE commit
2. **On request** — "review" before big changes

## What It Checks

### 1. Deduplication (MAIN!)
- Similar functionality already exists?
- Creating new script — isn't there one already?
- Can use existing code?

### 2. Architecture Integrity
- Code in right layer?
- Respects agents → services → db?
- Business logic in scripts/ — red flag!

### 3. Integration
- Uses existing helpers?
- Reinventing wheels?

### 4. Simplicity
- Can solve simpler?
- Over-engineered?

## What It Doesn't Check
- Code works (Tester's job)
- Syntax/lint (CI's job)
- Matches spec (Autopilot checklist)

## Output

```yaml
status: approved | needs_refactor | needs_discussion

duplicates_found:
  - new: scripts/new_script.py
    existing: scripts/similar_script.py
    action: "Merge into one"

architecture_issues:
  - file: src/domains/seller/agent.py
    issue: "Business logic in agent"
    action: "Move to domain services/"

recommended_action: approve | refactor_then_commit | discuss_with_human
```

## After Review

| Result | Next |
|--------|------|
| approved | Commit |
| needs_refactor | Coder fixes → re-review |
| needs_discussion | Human decides |

**Limit:** max 2 refactor iterations, then → Council
