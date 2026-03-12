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

### Step 5: Write to Inbox (NOT direct spec creation!)

**CRITICAL:** Reflect does NOT create TECH specs directly. It writes findings to inbox.
Spark will create specs from reflect findings.

For each pattern found (frequency >= 3):

**Location:** `ai/inbox/{timestamp}-reflect-{N}.md`

**Format:**
```markdown
# Idea: {timestamp}
**Source:** reflect
**Route:** spark
**Status:** new
**Context:** ai/diary/index.md
---
Reflect finding: {description of pattern and recommendation}
Frequency: {N} occurrences. Evidence: {task_ids}.
Pattern type: {user_preference | failure_pattern | design_decision | tool_workflow}
Proposed action: {what should change}
```

**Rules:**
- Only patterns with frequency >= 3 get inbox files
- Patterns with frequency 2 are noted in diary but NOT sent to inbox
- Max 5 inbox files per reflect session (prioritize by frequency)
- One inbox file per pattern (not per diary entry)
- Context links to diary index for full evidence

### Step 5.5: Commit + Push

```bash
git add ai/diary/ ai/inbox/ ai/reflect/ 2>/dev/null
git diff --cached --quiet || git commit -m "docs: reflect synthesis + inbox findings"
git push origin develop 2>/dev/null || true
```

### Step 5.6: Mark Processed

1. Append processed entry IDs to dedup log:
```bash
echo "{TASK_ID}" >> ai/diary/.processed.log
```
2. Update timestamp:
```bash
date +%s > ai/diary/.last_reflect
```

### Step 6: Output

```yaml
entries_analyzed: N
patterns_found:
  - "Pattern 1 (frequency: N)"
  - "Pattern 2 (frequency: N)"
inbox_files_created: M
next_action: "Orchestrator will dispatch Spark for each finding"
```

---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Create TECH spec directly | Write to inbox -> Spark creates spec |
| Edit CLAUDE.md directly | Write to inbox -> Spark -> skill-creator |
| Mark entries done immediately | Mark after Spark processes findings |
| Write all patterns to inbox | Only frequency >= 3, max 5 files |

---

## Quality Checklist

Before completing reflect:

- [ ] All pending entries analyzed
- [ ] Exa research performed for patterns with frequency >= 2
- [ ] Patterns counted correctly (frequency threshold)
- [ ] Findings written to inbox (not direct spec/edits)
- [ ] Commit + push performed
- [ ] Processed entries appended to .processed.log
