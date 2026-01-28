# TECH-036: Research-Enhanced /reflect with Exa

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-29

## Why

Current `/reflect` reads diary entries in a vacuum — analyzes patterns only from internal data. With Exa research, it can:
- Find external solutions for recurring problems
- Verify proposed CLAUDE.md rules against industry best practices
- Search for fix patterns when anti-patterns are detected

This closes the Reflexion loop: diary captures problems → reflect finds solutions → rules get updated → agents read updated rules → fewer problems.

## Context

Research sources (Jan 2026):
- Reflexion pattern (NeurIPS 2025): multi-trial learning with persistent memory
- A-Mem framework: Zettelkasten-style structured memory for agents
- ReMe framework: learns from success patterns + failure triggers

Current reflect: `Read diary → Analyze patterns → Create spec for CLAUDE.md`
Target: `Read diary → **Exa research solutions** → Analyze patterns → Create spec`

---

## Scope

**In scope:**
- Add Exa tools to reflect skill
- Add research phase after reading diary, before analysis
- Search for solutions to found patterns
- Verify proposed rules against best practices

**Out of scope:**
- Changing diary format (separate TECH-038)
- Auto-applying CLAUDE.md changes (stays manual via claude-md-writer)
- Changing reflect trigger conditions

## Impact Tree Analysis

### Step 1: UP — who uses?
- `/reflect` is invoked by user directly

### Step 2: DOWN — what depends on?
- Reflect reads: `ai/diary/index.md`, `ai/diary/*.md`
- Reflect writes: `ai/features/TECH-NNN-*.md` (spec)

### Step 3: BY TERM
- `reflect` referenced in diary-recorder.md (mentions /reflect)
- No other consumers

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/skills/reflect/SKILL.md` — add Exa research phase and tools

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### Research Phase (new Step 2.5 in reflect)

Between "Read Pending Entries" (Step 2) and "Analyze Patterns" (Step 3):

```markdown
### Step 2.5: Research Solutions for Found Patterns

For each pattern found (frequency ≥ 2):

**If anti-pattern/failure:**
mcp__exa__web_search_exa:
  query: "{anti_pattern} solution best practice {tech_stack}"
  numResults: 5

**If user preference/design decision:**
mcp__exa__web_search_exa:
  query: "{decision} pros cons alternatives {tech_stack} 2024 2025"
  numResults: 3

**If tool/workflow pattern:**
mcp__exa__get_code_context_exa:
  query: "{tool_pattern} best practices implementation"
  tokensNum: 3000

Rules:
- Max 6 Exa calls total per reflect session
- Add found solutions to spec's "Proposed Changes" with source URLs
- If Exa confirms our rule → strengthen confidence
- If Exa suggests different approach → note alternative in spec
```

### Updated Spec Format

```markdown
## Proposed Changes

### 1. CLAUDE.md — [Section]
**Pattern:** {what we found in diary}
**Frequency:** {N occurrences}
**Exa Research:** {what external sources say}
**Source:** {URL}
**Add/Update:**
[exact content to add]
```

## Implementation Plan

### Task 1: Add Exa Research Phase to reflect SKILL.md

**Type:** code
**Files:**
- Modify: `.claude/skills/reflect/SKILL.md`

**What to do:**
1. Add Exa tools to frontmatter model section (reflect is a skill, not agent — it runs in main context, so just document which tools to use)
2. Add Step 2.5: "Research Solutions for Found Patterns" between Step 2 and Step 3
3. Update Step 5 (Create Spec) format to include Exa research results and source URLs
4. Add max 6 Exa calls rule
5. Update Quality Checklist to include "Exa research performed for patterns with frequency ≥ 2"

**Acceptance:**
- SKILL.md has Step 2.5 with Exa search templates
- Spec format includes research results and sources
- Quality checklist mentions Exa research

### Execution Order

Task 1 (single task)

---

## Definition of Done

### Functional
- [ ] Reflect SKILL.md has research phase (Step 2.5)
- [ ] Exa search templates for anti-patterns, preferences, and tool patterns
- [ ] Max 6 calls limit specified
- [ ] Spec format includes research results with source URLs

### Technical
- [ ] No regressions in reflect flow

## Autopilot Log
