# TECH-035: Post-Execution Verifier with Exa Research

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-29

## Why

After autopilot completes all tasks, finishing.md only runs `./test fast` and a mechanical checklist. Tests verify code **works**, but don't verify it's **correct** — no check against known pitfalls, security issues, or anti-patterns. A post-execution research step catches problems that tests miss.

## Context

Research sources (Jan 2026):
- VIGIL framework (Dec 2025): out-of-band verification during/after execution
- GVR pattern: Generate → Verify with external knowledge → Reflect
- Autonomy Loops: Reflection → Evaluation → Correction → Execution

Current finishing flow: `Final test → Pre-Done Checklist → Done`
Target: `Final test → **Exa Verification** → Pre-Done Checklist → Done`

---

## Scope

**In scope:**
- Add Exa verification step to finishing.md (between final test and pre-done checklist)
- Inline execution by autopilot (NOT a subagent — runs in main autopilot context)
- Search for pitfalls of the pattern/library used
- Flag findings as warnings (don't auto-block)

**Out of scope:**
- Separate verifier subagent (overkill — keep inline)
- Auto-fixing found issues (just flag)
- Security scanning tools integration

## Impact Tree Analysis

### Step 1: UP — who uses?
- `finishing.md` is used by autopilot SKILL.md main loop (Phase 3)

### Step 2: DOWN — what depends on?
- finishing.md depends on: spec file (reads DoD), backlog (updates status)

### Step 3: BY TERM — grep
- `finishing.md` referenced in autopilot/SKILL.md
- No other consumers

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/skills/autopilot/finishing.md` — add Exa verification step
2. `.claude/skills/autopilot/SKILL.md` — update Phase 3 Quick Reference to mention verification

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### Verification Step (inline in finishing.md)

After `./test fast` passes, before pre-done checklist:

```markdown
## Exa Verification (after final test)

Search for known issues with the approach used:

**Step 1:** Extract key patterns from spec
- Read spec's `## Design` and `## Approaches` sections
- Identify: libraries used, patterns chosen, architecture decisions

**Step 2:** Search for pitfalls
mcp__exa__web_search_exa:
  query: "{pattern_used} {library} common pitfalls production issues"
  numResults: 5

**Step 3:** Search for security concerns
mcp__exa__web_search_exa:
  query: "{library} security vulnerabilities 2024 2025"
  numResults: 3

**Step 4:** Evaluate findings
- If critical issue found → add WARNING to Autopilot Log, flag for human review
- If minor concern → note in Autopilot Log
- If nothing found → proceed

Max 3 Exa calls. Don't block on this — warnings only.
```

**Key design decision:** Inline, not subagent. Autopilot already has main context, can read the spec, and just needs 2-3 Exa calls. No need for isolated subagent overhead.

## Implementation Plan

### Task 1: Add Exa Verification Step to finishing.md

**Type:** code
**Files:**
- Modify: `.claude/skills/autopilot/finishing.md`

**What to do:**
Add new section `## Exa Verification` between the "Final test" step and "Pre-Done Checklist" in the Flow section. Include:
- Step 1: Extract patterns from spec (Read spec Design/Approaches sections)
- Step 2: Search for pitfalls (`mcp__exa__web_search_exa`)
- Step 3: Search for security concerns (`mcp__exa__web_search_exa`)
- Step 4: Evaluate and log findings
- Max 3 tool calls, warnings only (never block)
- Add to Autopilot Log format: `- Exa Verify: no issues | WARNING: {description}`

**Acceptance:**
- finishing.md Flow shows verification between test and checklist
- Autopilot Log format includes Exa Verify entry

### Task 2: Update Quick Reference in SKILL.md

**Type:** code
**Files:**
- Modify: `.claude/skills/autopilot/SKILL.md`

**What to do:**
Update Phase 3 in Quick Reference to mention Exa verification:
```
PHASE 3: Finish → finishing.md
  └─ Final test → Exa verification → status done → merge develop → cleanup
```

**Acceptance:**
- Quick Reference shows Exa verification step

### Execution Order

Task 1 → Task 2

---

## Definition of Done

### Functional
- [ ] finishing.md has Exa verification step
- [ ] Verification is between final test and pre-done checklist
- [ ] Max 3 Exa calls specified
- [ ] Warnings-only approach (no blocking)
- [ ] Autopilot Log format includes verification entry

### Technical
- [ ] No regressions in finishing flow
- [ ] SKILL.md Quick Reference updated

## Autopilot Log
