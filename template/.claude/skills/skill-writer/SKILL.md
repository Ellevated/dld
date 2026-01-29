---
name: skill-writer
description: Write and optimize CLAUDE.md, rules, agent prompts, and skill prompts
model: opus
---

# Skill Writer — CREATE & UPDATE System Documentation

Unified tool for creating new agents/skills and optimizing existing system docs.

**Activation:**
- `skill-writer create {type} {name}` — new agent/skill/wrapper
- `skill-writer update {target}` — optimize existing (from /reflect or direct)
- `/skill-writer` — interactive mode

---

## Scope

| Target | Path | CREATE | UPDATE | Limits |
|--------|------|--------|--------|--------|
| Foundation | `CLAUDE.md` | - | Yes | < 200 lines |
| Rules | `.claude/rules/*.md` | - | Yes | < 500 lines |
| Agents | `.claude/agents/*.md` | Yes | Yes | Concise |
| Skills | `.claude/skills/*/SKILL.md` | Yes | Yes | < 500 lines |

---

## Six-Phase Process

```
1. REQUIREMENTS → what, who, tools, model, constraints
2. RESEARCH → Exa for patterns, alternatives (max 3 calls)
3. DRAFT → generate structure and content
4. THREE-EXPERT GATE → compress, quality check
5. VALIDATE → limits, structure, no duplication
6. WRITE → create/update file, report changes
```

---

## Phase 1: Requirements

### CREATE Mode

Gather (ask if not explicit):
- **What:** One sentence — what does it do?
- **Who calls:** User / autopilot / both?
- **Tools:** Read, Edit, Bash, MCP tools, etc.
- **Model:** opus (complex) / sonnet (routine) / haiku (simple)

### UPDATE Mode

Gather:
- **Target file:** Which file to optimize?
- **What to change:** Specific section or full optimization?
- **Source:** From /reflect spec or direct request?

---

## Phase 2: Research (Exa)

Skip for trivial changes. Max 3 calls.

```yaml
# Similar skills/patterns
mcp__exa__web_search_exa:
  query: "{type} agent pattern best practice LLM 2025"

# Implementation examples
mcp__exa__get_code_context_exa:
  query: "{skill_type} implementation examples"
```

---

## Phase 3: Draft

### CREATE — Determine Type

```
Need reusable prompt for Autopilot?
  YES → Wrapper (agent + skill)
  NO  → Multi-agent orchestration?
        YES → Orchestrator (no agent file)
        NO  → Standalone skill
```

| Type | Description | Has Agent File? |
|------|-------------|-----------------|
| **Wrapper** | Thin layer over single agent | Yes (agents/*.md) |
| **Orchestrator** | Dispatches multiple agents | No |
| **Standalone** | Self-contained logic | No |

### UPDATE — Identify Changes

1. Read current file
2. Compare with spec (if from /reflect)
3. Identify sections to add/update/remove

---

## Phase 4: Three-Expert Gate

Apply to ALL output (CREATE and UPDATE):

### Karpathy (Remove redundancy)
- Does Claude already know this? Remove.
- "If I remove this line, will output worsen?" No → remove.
- Telling HOW to think vs WHAT to achieve? Prefer WHAT.

### Sutskever (Unlock capability)
- Constraining instead of guiding? Principles > rigid procedures.
- Fighting model's strengths? (rigid templates vs free-form)
- Examples beat descriptions.

### Murati (Simplify UX)
- Can steps be eliminated or parallelized?
- Is input/output format minimal?
- Unnecessary waiting?

**Deletion test:** Every line must pass "removal worsens output?" check.

---

## Phase 5: Validate

### Structure (CREATE)

**Agent template:**
```markdown
---
name: {name}
description: {One-line}
model: {opus|sonnet|haiku}
tools: {Read, Glob, Grep, Edit, Write, Bash, ...}
---

# {Name} Agent

{Mission.}

## Input
{input spec}

## Process
1. {Step}

## Output
{output spec}

## Rules
- {Rule}
```

**Wrapper skill template:**
```markdown
---
name: {name}
description: {One-line}
---

# {Name} Skill

{What user gets.}

**Activation:** `{trigger}`

## Process
1. Parse arguments
2. Validate preconditions
3. Dispatch agent via Task tool
4. Report result

## User Experience
{Progress, errors, success handling}
```

**Orchestrator skill template:**
```markdown
---
name: {name}
description: {One-line}
model: opus
---

# {Name} Skill

{Mission.}

**Activation:** `{trigger}`

## Architecture
{Phase diagram}

## Process
{Phase details with agent dispatch}
```

### Limits (all modes)

| Check | Requirement |
|-------|-------------|
| CLAUDE.md | < 200 lines |
| Rules files | < 500 lines, `paths:` frontmatter |
| Skills | < 500 lines |
| Naming | lowercase, hyphenated |
| No duplication | Single source of truth |
| Critical first | Top 20 lines = most important |

**Verify with:**
```bash
wc -l {file}
```

---

## Phase 6: Write

### CREATE

1. Create directory: `.claude/skills/{name}/`
2. Write `SKILL.md`
3. If wrapper → also write `.claude/agents/{name}.md`
4. Register in CLAUDE.md Skills table (if user-invocable)

### UPDATE

1. Apply changes to target file
2. Verify limits after edit
3. Report what changed

---

## Documentation Hierarchy

```
1. CLAUDE.md          — always loaded, universal rules only
2. .claude/rules/     — conditional (paths: frontmatter)
3. .claude/agents/    — loaded per Task tool dispatch
4. .claude/skills/    — loaded per Skill tool invocation
5. Co-located (src/)  — loaded when reading nearby code
```

### What Belongs Where

| Content | Location |
|---------|----------|
| Universal rules, commands | `CLAUDE.md` |
| Domain-specific logic | `.claude/rules/{domain}.md` |
| Agent execution behavior | `.claude/agents/{name}.md` |
| User-facing skill flow | `.claude/skills/{name}/SKILL.md` |
| Code style | Linter config (NOT docs) |

---

## Prompt Quality Principles

- **Front-load** — critical context first (LLM attention front-weighted)
- **Principles > procedures** — "Be concise" beats 10 length rules
- **Show > tell** — one example beats a paragraph
- **Negative space** — "don't do X" only when counterintuitive
- **Trust the model** — don't explain what it knows
- **Verify counts** — `wc -l`, `grep -c`, never manual

---

## Anti-Patterns

| Don't | Do |
|-------|-----|
| Duplicate across files | Single source of truth |
| Code style in docs | Linter config |
| Overspecify agent steps | Principles + examples |
| Count manually | `wc -l`, `grep -c` |
| > 200 lines CLAUDE.md | Split to rules/ |

---

## Model Selection

| Use Case | Model |
|----------|-------|
| Complex analysis, architecture | opus |
| Routine tasks (90% capability, 2x speed) | sonnet |
| Simple/fast tasks, logging | haiku |

---

## Output

```yaml
status: complete
mode: create|update
target: {file path}
action: created|updated
summary: {what was done}
lines: {count}
```
