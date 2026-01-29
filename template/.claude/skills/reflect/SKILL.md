---
name: reflect
description: Analyze diary entries and create spec with proposed CLAUDE.md improvements
model: opus
---

# Reflect — Synthesize Diary into Rules

Analyzes diary entries and creates spec with proposals for CLAUDE.md.

**Activation:** `/reflect`, "reflection", "let's analyze the diary"

---

## Terminology

| Action | Triggers | What happens |
|--------|----------|--------------|
| **Diary entry** | "write to diary", "save to diary", "remember for diary" | New line in index.md + file |
| **Synthesis (this skill)** | "/reflect", "reflection", "let's analyze the diary" | Analysis -> spec -> skill-writer |

---

## When to Use

- After 5+ pending entries in diary
- Weekly maintenance
- After a series of similar bugs
- Before major work (refresh memory)

---

## Process

### Step 1: Read Diary Index

```bash
cat ai/diary/index.md
```

Find all entries with `pending` status.

### Step 2: Read Pending Entries

For each pending entry — open file and analyze.

### Step 2.5: Research Solutions for Found Patterns

For each pattern found in diary (frequency >= 2), research external solutions:

**If anti-pattern/failure:**
```yaml
mcp__exa__web_search_exa:
  query: "{anti_pattern} solution best practice {tech_stack}"
  numResults: 5
```

**If user preference/design decision:**
```yaml
mcp__exa__web_search_exa:
  query: "{decision} pros cons alternatives {tech_stack} 2024 2025"
  numResults: 3
```

**If tool/workflow pattern:**
```yaml
mcp__exa__get_code_context_exa:
  query: "{tool_pattern} best practices implementation"
  tokensNum: 3000
```

**Rules:**
- Max 6 Exa calls total per reflect session
- Add found solutions to spec's "Proposed Changes" with source URLs
- If Exa confirms our rule → strengthen confidence
- If Exa suggests different approach → note alternative in spec

### Step 3: Analyze Patterns

| Pattern Type | Threshold | Action |
|--------------|-----------|--------|
| User preference | 2+ | Consider adding |
| User preference | 3+ | **MUST** add to CLAUDE.md |
| Failure pattern | 2+ | Add as anti-pattern |
| Design decision | 3+ | Add as guideline |
| Tool/workflow | 2+ | Consider adding |

### Step 4: Check Existing Rules

Compare entries with CLAUDE.md:
- Rule violated? -> Strengthen wording
- Rule helped? -> Keep
- Rule outdated? -> Update or remove

### Step 5: Create Spec (NOT direct edits!)

**CRITICAL:** Never edit CLAUDE.md directly! Create spec.

**Location:** `ai/features/TECH-NNN-YYYY-MM-DD-reflect-synthesis.md`

**Format:**

```markdown
# TECH-NNN: Reflect Diary Synthesis — [Month Year]

**Status:** queued | **Priority:** P2 | **Date:** YYYY-MM-DD

## Context
- Entries analyzed: [list from index.md]
- Period: [date range]

## Findings

### Patterns Found (threshold 2+ = MUST add)
| Pattern | Frequency | Source | Action |

### Anti-Patterns Found
| Anti-Pattern | Frequency | Source | Action |

### User Preferences Found
| Preference | Frequency | Source | Action |

## Proposed Changes

### 1. CLAUDE.md — [Section]
**Pattern:** {what we found in diary}
**Frequency:** {N occurrences}
**Exa Research:** {what external sources say}
**Source:** {URL}
**Add/Update:**
```markdown
[exact content to add]
```

## Allowed Files
| File | Change Type |
|------|-------------|
| `CLAUDE.md` | Update |
| `.claude/rules/*.md` | Update (if needed) |

## Definition of Done
- [ ] `skill-writer` applied changes
- [ ] CLAUDE.md < 200 lines after changes
- [ ] Diary entries marked as done in index.md

## Integration
**Next step:** Run `/skill-writer` with this spec as input.

## After Integration
Update diary entries status in index.md:
```bash
# For each processed entry, change status from pending to done
```
```

### Step 6: Output

```yaml
entries_analyzed: N
patterns_found:
  - "Pattern 1"
  - "Pattern 2"
spec_created: ai/features/TECH-NNN-....md
next_action: "Run /skill-writer to integrate"
```

---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Edit CLAUDE.md directly | Create spec -> skill-writer |
| Edit .claude/rules directly | Create spec -> skill-writer |
| Mark entries done before integration | Mark after skill-writer |

---

## After skill-writer

1. Open `ai/diary/index.md`
2. For each processed entry change status: `pending` -> `done`
3. Update timestamp:

```bash
date +%s > ai/diary/.last_reflect
```

---

## Quality Checklist

Before completing reflect:

- [ ] All pending entries analyzed
- [ ] Exa research performed for patterns with frequency >= 2
- [ ] Patterns counted correctly (frequency threshold)
- [ ] Spec created (not direct edits)
- [ ] Spec contains "Proposed Changes" section with Exa sources
- [ ] Next action = "run skill-writer"
