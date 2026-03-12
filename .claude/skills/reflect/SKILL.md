---
name: reflect
description: Analyze diary entries → propose improvements to rules, agents, skills.
model: opus
---

# Reflect — Synthesize Diary + Upstream Signals into Rules

Analyzes diary entries AND upstream signals, creates spec with proposals for CLAUDE.md.

**Activation:** `/reflect`, "reflection", "let's analyze the diary"

---

## Terminology

| Action | Triggers | What happens |
|--------|----------|--------------|
| **Diary entry** | "write to diary", "save to diary", "remember for diary" | New line in index.md + file |
| **Synthesis (this skill)** | "/reflect", "reflection", "let's analyze the diary" | Analysis -> spec -> skill-creator |

---

## When to Use

- After 5+ pending entries in diary
- After 5+ upstream signals in `ai/reflect/upstream-signals.md`
- Weekly maintenance
- After a series of similar bugs
- Before major work (refresh memory)
- After completing a project phase (Board → Architect → Spark cycles)

---

## Process

### Step 1: Read Diary Index

Read `ai/diary/index.md` — find all entries with `pending` status.

**Deduplication:** If `ai/diary/.processed.log` exists, skip entries already listed there.
This prevents re-processing entries from previous reflect sessions.

### Step 1.5: Read Upstream Signals (v2, NEW)

If `ai/reflect/upstream-signals.md` exists, read it.
If `ai/reflect/cross-level-patterns.md` exists, read it.

Upstream signals are feedback from lower levels (Autopilot → Spark → Architect → Board).
Cross-level patterns are recurring issues detected by the reflect-aggregator.

These provide ADDITIONAL input alongside diary entries.

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
- [ ] `skill-creator` applied changes
- [ ] CLAUDE.md < 200 lines after changes
- [ ] Diary entries marked as done in index.md

## Integration

**What `/skill-creator` does with reflect output:**
1. Reads the reflect spec (proposed changes)
2. Applies changes to CLAUDE.md and .claude/rules/
3. Validates CLAUDE.md stays under 200 lines
4. Creates a commit with the integrated changes

**Next step:** Run `/skill-creator` with this spec as input.

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
next_action: "Run /skill-creator — it will apply proposed changes to CLAUDE.md and rules"
```

---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Edit CLAUDE.md directly | Create spec -> skill-creator |
| Edit .claude/rules directly | Create spec -> skill-creator |
| Mark entries done before integration | Mark after skill-creator |

---

## After skill-creator

1. Open `ai/diary/index.md`
2. For each processed entry change status: `pending` -> `done`
3. Append processed entry IDs to dedup log:

```bash
# Append each processed TASK_ID to prevent re-processing
echo "{TASK_ID_1}" >> ai/diary/.processed.log
echo "{TASK_ID_2}" >> ai/diary/.processed.log
```

4. Update timestamp:

```bash
date +%s > ai/diary/.last_reflect
```

5. **Optional:** If `ai/diary/{ID}-state.json` files exist for processed entries,
   read them for rich telemetry (retries, timing, step outcomes) to strengthen pattern analysis.

---

## Quality Checklist

Before completing reflect:

- [ ] All pending entries analyzed
- [ ] Exa research performed for patterns with frequency >= 2
- [ ] Patterns counted correctly (frequency threshold)
- [ ] Spec created (not direct edits)
- [ ] Spec contains "Proposed Changes" section with Exa sources
- [ ] Next action = "run skill-creator"
