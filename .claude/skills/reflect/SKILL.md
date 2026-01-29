---
name: reflect
description: Analyze diary → propose improvements to rules, agents, and skills
model: opus
---

# Reflect — Diary → System Improvements

Finds patterns in diary entries and proposes changes across the entire system: rules, agent prompts, skill prompts.

**Activation:** `/reflect`

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

- `mcp__exa__web_search_exa` → "{problem} solution best practice {tech_stack}"
- `mcp__exa__get_code_context_exa` → "{pattern} implementation examples"

Max 6 Exa calls. Include source URLs in proposals.

### Step 3: Analyze Patterns

| Frequency | Action |
|-----------|--------|
| 2+ | Consider proposing fix |
| 3+ | **MUST** propose fix |

Compare with existing rules — strengthen, update, or remove outdated.

### Step 4: Three-Expert Quality Gate

For each proposed change:

1. **Karpathy:** Redundant? Claude already knows this? If removing doesn't hurt — don't add.
2. **Sutskever:** Constraining instead of guiding? Principles > rigid rules.
3. **Murati:** Adding friction? Could be simpler or faster?

### Step 5: Create Spec

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

### Step 6: Handoff

Suggest `/skill-writer update` to apply. After integration: mark diary entries `pending` → `done`.

---

## Rules

- **Spec first** — never edit targets directly
- **Research** — Exa for patterns with frequency ≥ 2
- **Three-Expert gate** — every proposal passes all 3
- **Mark done after apply** — not before skill-writer runs
