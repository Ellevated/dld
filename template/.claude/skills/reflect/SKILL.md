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
| **Synthesis (this skill)** | "/reflect", "reflection", "let's analyze the diary" | Analysis -> spec -> claude-md-writer |

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
- [ ] `claude-md-writer` applied changes
- [ ] CLAUDE.md < 200 lines after changes
- [ ] Diary entries marked as done in index.md

## Integration
**Next step:** Run `/claude-md-writer` with this spec as input.

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
next_action: "Run /claude-md-writer to integrate"
```

---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Edit CLAUDE.md directly | Create spec -> claude-md-writer |
| Edit .claude/rules directly | Create spec -> claude-md-writer |
| Mark entries done before integration | Mark after claude-md-writer |

---

## After claude-md-writer

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
- [ ] Patterns counted correctly (frequency threshold)
- [ ] Spec created (not direct edits)
- [ ] Spec contains "Proposed Changes" section
- [ ] Next action = "run claude-md-writer"
