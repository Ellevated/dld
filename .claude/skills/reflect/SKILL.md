---
name: reflect
description: Analyze diary → propose improvements to rules, agents, and skills
model: opus
---

# Reflect — Diary → System Improvements

Finds patterns in diary entries and proposes changes across the entire system: rules, agent prompts, skill prompts.

**Activation:** `/reflect`, "reflection", "analyze the diary"

---

## Terminology

| Term | Triggers | What happens |
|------|----------|--------------|
| **Diary entry** | "write to diary", "save to diary" | New entry in index.md + file |
| **Reflect (this)** | "/reflect", "reflection" | Analysis → spec → skill-writer |

---

## When to Use

- After 5+ pending entries in diary
- Weekly maintenance
- After series of similar bugs
- Before major work (refresh memory)

---

## Scope

| Target | Path | When to Propose |
|--------|------|----------------|
| Project rules | `CLAUDE.md`, `.claude/rules/*.md` | Pattern found in ≥2 entries |
| Agent prompts | `.claude/agents/*.md` | Agent-specific failure ≥2 times |
| Skill prompts | `.claude/skills/*/SKILL.md` | Skill flow issue found |
| Dispatch logic | `subagent-dispatch.md` | Dispatch condition problem |

---

## Process

### Step 1: Read Diary

Read `ai/diary/index.md`. Open each `pending` entry.

### Step 2: Research Solutions (Exa)

For patterns with frequency ≥ 2:

**Anti-pattern/failure:**
```yaml
mcp__exa__web_search_exa:
  query: "{anti_pattern} solution best practice {tech_stack}"
```

**Tool/workflow pattern:**
```yaml
mcp__exa__get_code_context_exa:
  query: "{pattern} best practices implementation"
```

**Rules:**
- Max 6 Exa calls total per session
- Add source URLs to proposals
- If Exa confirms rule → strengthen confidence
- If Exa suggests alternative → note in spec

### Step 3: Analyze Patterns

| Frequency | Action |
|-----------|--------|
| 2+ | Consider proposing fix |
| 3+ | **MUST** propose fix |

### Step 4: Check Existing Rules

Compare entries with existing targets (`CLAUDE.md`, `.claude/rules/`, agents, skills):

| Finding | Action |
|---------|--------|
| Rule violated | Strengthen wording |
| Rule helped | Keep |
| Rule outdated | Update or remove |
| Agent failed pattern | Fix agent prompt |
| Skill flow issue | Fix skill prompt |

### Step 5: Three-Expert Quality Gate

For each proposed change:

1. **Karpathy:** Redundant? Claude already knows this? If removing doesn't hurt — don't add.
2. **Sutskever:** Constraining instead of guiding? Principles > rigid rules.
3. **Murati:** Adding friction? Could be simpler or faster?

### Step 6: Create Spec

**CRITICAL:** Never edit targets directly.

Create `ai/features/TECH-NNN-YYYY-MM-DD-reflect-synthesis.md`:

```markdown
# TECH-NNN: Reflect Synthesis — [Month Year]

**Status:** queued | **Priority:** P2 | **Date:** YYYY-MM-DD

## Findings

| Pattern | Freq | Source Entries | Target File |
|---------|------|---------------|-------------|

## Proposed Changes

### 1. {target file} — {section}
**Pattern:** {what we found}
**Exa Research:** {external findings + URL}
**Add/Update:**
[exact content]

## Allowed Files
[every file to be modified]

## Definition of Done
- [ ] skill-writer applied changes
- [ ] Diary entries marked done
```

### Step 7: Handoff

Suggest `/skill-writer update` to apply. After integration: mark diary entries `pending` → `done`.

---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Edit targets directly | Create spec → skill-writer |
| Mark entries done before apply | Mark after skill-writer runs |
| Skip Exa research | Research patterns with freq ≥ 2 |

---

## Quality Checklist

Before completing:

- [ ] All pending diary entries analyzed
- [ ] Exa research for patterns with frequency ≥ 2
- [ ] Spec created (not direct edits)
- [ ] Proposed changes have Exa sources
- [ ] Next action = "/skill-writer update"

---

## Rules

- **Spec first** — never edit targets directly
- **Research** — Exa for patterns with frequency ≥ 2
- **Three-Expert gate** — every proposal passes all 3
- **Mark done after apply** — not before skill-writer runs
