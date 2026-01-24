---
name: scaffold
description: Generate new skills or agents following DLD architecture
model: sonnet
---

# Scaffold — Create New Skills & Agents

Generate new skills or agents that integrate consistently with DLD ecosystem.

**Activation:**
- `scaffold skill {name}` — create new skill
- `scaffold agent {name}` — create new agent
- `scaffold wrapper {name}` — create skill + agent pair

---

## Architecture Overview

```
.claude/
├── agents/                    ← SOURCE OF TRUTH (pure prompts)
│   └── {name}.md              ← Reusable by Autopilot & user
│
└── skills/                    ← USER INTERFACE (wrappers + orchestrators)
    └── {name}/SKILL.md        ← UX, validation, dispatch
```

**Key Principle:**
- **agents/*.md** = pure execution prompts (stateless, reusable)
- **skills/*/SKILL.md** = user-facing interface (UX, validation)

---

## Skill Types

| Type | Description | Has Agent File? | Examples |
|------|-------------|-----------------|----------|
| **Orchestrator** | Dispatches multiple agents, manages flow | No | autopilot, spark |
| **Wrapper** | Thin layer over single agent | Yes (agents/*.md) | plan, scout, review |
| **Standalone** | Self-contained logic, no reusable agent | No | council, reflect |

**Decision tree:**
```
Need reusable prompt for Autopilot?
  YES → Create agent + wrapper skill
  NO  → Is it multi-agent orchestration?
        YES → Orchestrator skill (no agent file)
        NO  → Standalone skill
```

---

## Process

### 1. Gather Requirements

Ask user:
- What does this skill/agent do? (one sentence)
- Who calls it? (user directly / autopilot / both)
- What tools does it need? (Read, Edit, Bash, MCP tools, etc.)
- What model? (opus for complex analysis, sonnet for routine, haiku for simple)

### 2. Determine Type

Based on answers:
- Called by both user AND autopilot → **Wrapper** (agent + skill)
- Only user, multi-step orchestration → **Orchestrator**
- Only user, self-contained → **Standalone**
- Only autopilot → **Agent only** (no skill needed)

### 3. Generate Files

Use templates below. Validate against rules.

### 4. Register (if needed)

- Add to `CLAUDE.md` Skills table (if user-invocable)
- Add to `docs/foundation/02-agent-roles.md` (if significant)

---

## Templates

### Agent Template

```markdown
---
name: {name}
description: {One-line description}
model: {opus|sonnet|haiku}
tools: {Read, Glob, Grep, Edit, Write, Bash, ...}
---

# {Name} Agent

{One sentence mission.}

## Input

```yaml
{input_field}: {type}  # {description}
```

## Process

1. {Step 1}
2. {Step 2}
3. {Step 3}

## Output

```yaml
status: {success|blocked|...}
result: ...
```

## Rules

- {Rule 1}
- {Rule 2}
```

**Agent naming:** `{name}.md` in `.claude/agents/`

### Wrapper Skill Template

```markdown
---
name: {name}
description: {One-line description}
model: {from agent frontmatter}
---

# {Name} Skill

{One sentence — what user gets.}

**Activation:** `{trigger phrase}`

## Process

1. Parse arguments
2. Validate preconditions
3. **Dispatch agent:**
   ```yaml
   Task tool:
     subagent_type: "{name}"
     prompt: |
       {INPUT YAML from user}
   ```
4. Report result
5. Suggest next step

## User Experience

- Progress: {what to show}
- Errors: {how to handle}
- Success: {what to return}
```

**Skill naming:** `.claude/skills/{name}/SKILL.md`

### Orchestrator Skill Template

```markdown
---
name: {name}
description: {One-line description}
model: opus
---

# {Name} Skill

{Mission statement.}

**Activation:** `{trigger}`

## Architecture

```
PHASE 1: ...
  └─ [Agent A] → output
PHASE 2: ...
  └─ [Agent B] → output
PHASE 3: ...
  └─ Result
```

## Process

### Phase 1: {Name}
{Details + agent dispatch}

### Phase 2: {Name}
{Details + agent dispatch}

## Subagent Dispatch

```yaml
# Agent A
Task tool:
  subagent_type: "{agent_a}"
  prompt: |
    ...

# Agent B
Task tool:
  subagent_type: "{agent_b}"
  prompt: |
    ...
```
```

---

## Validation Rules

Before generating, verify:

### Naming
- [ ] Agent: lowercase, single word or hyphenated (`coder`, `spec-reviewer`)
- [ ] Skill: same as agent name
- [ ] No conflicts with existing names

### Structure
- [ ] Agent has: frontmatter, Input, Process, Output, Rules
- [ ] Skill has: frontmatter, Activation, Process
- [ ] Frontmatter has: name, description, model, tools (agent only)

### Model Selection
- [ ] Opus: complex analysis, architecture, debugging
- [ ] Sonnet: routine tasks, 90% capability, 2x speed
- [ ] Haiku: simple/fast tasks, logging

### Tools Selection
- [ ] Read, Glob, Grep: for analysis agents
- [ ] Edit, Write: for modification agents
- [ ] Bash: only if truly needed (prefer dedicated tools)
- [ ] MCP tools: if external research needed

### Integration
- [ ] If wrapper: agent file exists in `.claude/agents/`
- [ ] If orchestrator: all dispatched agents exist
- [ ] Dispatch uses correct `subagent_type` matching agent filename

---

## Examples

### Example 1: Create wrapper skill

```
User: scaffold wrapper linter
```

Creates:
- `.claude/agents/linter.md` — lint logic
- `.claude/skills/linter/SKILL.md` — user interface

### Example 2: Create standalone skill

```
User: scaffold skill quickfix
```

Creates:
- `.claude/skills/quickfix/SKILL.md` — self-contained

### Example 3: Create agent only

```
User: scaffold agent summarizer
```

Creates:
- `.claude/agents/summarizer.md` — for autopilot use

---

## Reference

**Architecture docs:** `docs/foundation/02-agent-roles.md`
**Existing agents:** `.claude/agents/*.md`
**Existing skills:** `.claude/skills/*/SKILL.md`
