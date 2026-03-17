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

### Step 5: Write durable reflect artifacts (NOT inbox)

**CRITICAL:** Reflect does NOT create TECH specs and does NOT write to inbox.
It writes durable findings to its own reflect artifacts and diary context.
OpenClaw reviews those artifacts later and decides whether to create an inbox item.

**Location:** `ai/reflect/findings-{date}.md` (single file per session, not one per pattern)

**Format:**
```markdown
# Reflect Findings — {date}

## {Pattern Name}
**Frequency:** {N} occurrences. **Evidence:** {task_ids}.
**Type:** {user_preference | failure_pattern | design_decision | tool_workflow}
**Proposed action:** {what should change}

---
```

**Rules:**
- Only patterns with frequency >= 3 are included
- Patterns with frequency 2 are noted in diary but NOT included in findings file
- Max 5 findings per reflect session (prioritize by frequency)
- All findings for a session go into a single file (not one per pattern)
- No `Route: spark` — OpenClaw decides next steps from reflect findings

### Step 5.5: Commit + Push

```bash
git add ai/diary/ ai/reflect/ 2>/dev/null
git diff --cached --quiet || git commit -m "docs: reflect synthesis + findings"
git push origin develop 2>/dev/null || true
```

### Step 5.6: Mark Diary Entries as Done

**CRITICAL:** Update diary index.md — change status from `pending` to `done` for ALL analyzed entries.
This prevents the orchestrator from re-dispatching reflect on every cycle.

```bash
# For each processed TASK_ID:
sed -i "s/| ${TASK_ID} |\\(.*\\)| pending |/| ${TASK_ID} |\\1| done |/" ai/diary/index.md
```

Also maintain dedup log and timestamp:
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
findings_written: M
next_action: "Findings saved to ai/reflect/findings-{date}.md — OpenClaw decides next step"
```

---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Create TECH spec directly | Write to ai/reflect/ -> OpenClaw decides next step |
| Edit CLAUDE.md directly | Write to ai/reflect/ -> OpenClaw -> Spark -> skill-creator |
| Skip marking entries done | MUST mark diary entries `pending → done` in Step 5.6 |
| Write all patterns to ai/reflect/ | Only frequency >= 3, max 5 findings |
| Write findings directly into inbox | Only OpenClaw writes to inbox |

---

## Quality Checklist

Before completing reflect:

- [ ] All pending entries analyzed
- [ ] Exa research performed for patterns with frequency >= 2
- [ ] Patterns counted correctly (frequency threshold)
- [ ] Findings written to ai/reflect/ (not inbox, not direct spec/edits)
- [ ] Commit + push performed
- [ ] Processed entries appended to .processed.log

---

## Notification Output Format

Your final JSON `result_preview` is sent to the user via Telegram. Keep it concise:

```
Записей: {N} обработано
Паттернов: {M} найдено, {K} → ai/reflect/
{If K > 0: one-line top pattern}
```

**BAD:** "entries_analyzed: 5, patterns_found: [...], findings_written: 2, next_action: ..."
**GOOD:** "Записей: 5 обработано. Паттернов: 3 найдено, 2 → ai/reflect/. Топ: мок в интеграционных тестах (×4)"
