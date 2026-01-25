# Skills Setup Guide v3.3

How to deploy the LLM skills system in a new project.

---

## Overview

Skills are specialized LLM workflows:

```
spark → autopilot (plan is subagent inside autopilot)
```

**v3.3 Changes:**
- **Council decomposition** — 5 separate expert agents in `agents/council/`
- **Spark agent** — dedicated agent file for idea generation
- **Diary recorder** — auto-captures problems for future reflection
- **Wrapper skills** — tester/coder/planner as standalone skills
- **Research tools** — Exa + Context7 integration in agents
- **Bootstrap skill** — Day 0 discovery, unpack idea from founder
- **Claude-md-writer** — CLAUDE.md optimization with 3-tier system

| Skill | Purpose | Model |
|-------|---------|-------|
| **spark** | Idea → Spec + auto-handoff | opus |
| **autopilot** | Spec → Code (includes plan) | opus (orchestrator) |
| **council** | 5 experts debate | opus |
| **review** | Architecture watchdog (Stage 2) | opus |
| **audit** | READ-ONLY code analysis | opus |
| **reflect** | Diary → CLAUDE.md rules | sonnet |
| **scout** | External research | sonnet |
| **tester** | Run tests (wrapper) | sonnet |
| **coder** | Write code (wrapper) | sonnet |
| **planner** | Create implementation plan (wrapper) | opus |
| **bootstrap** | Day 0 — unpack idea from founder | opus |
| **claude-md-writer** | Optimize CLAUDE.md (3-tier system) | opus |

---

## File Structure (v3.3)

```
.claude/
├── agents/                     ← SOURCE OF TRUTH (pure prompts)
│   ├── spark.md                ← opus (idea generation)
│   ├── planner.md              ← opus (detailed planning)
│   ├── coder.md                ← sonnet (code writing)
│   ├── tester.md               ← sonnet (test running)
│   ├── debugger.md             ← opus (root cause analysis)
│   ├── spec-reviewer.md        ← sonnet (spec matching)
│   ├── review.md               ← opus (code quality)
│   ├── scout.md                ← sonnet (research)
│   ├── documenter.md           ← sonnet (docs update)
│   ├── diary-recorder.md       ← haiku (problem capture)
│   └── council/                ← DECOMPOSED council experts
│       ├── synthesizer.md      ← opus (chairman)
│       ├── architect.md        ← opus (Winston)
│       ├── product.md          ← opus (John)
│       ├── pragmatist.md       ← opus (Amelia)
│       └── security.md         ← opus (Viktor)
│
├── skills/                     ← USER INTERFACE (wrappers + orchestrators)
│   ├── spark/SKILL.md          ← Orchestrator
│   ├── autopilot/SKILL.md      ← Orchestrator
│   ├── council/SKILL.md        ← Orchestrator (dispatches council/*)
│   ├── review/SKILL.md         ← Wrapper → agents/review.md
│   ├── scout/SKILL.md          ← Wrapper → agents/scout.md
│   ├── audit/SKILL.md          ← Standalone (READ-ONLY)
│   ├── reflect/SKILL.md        ← Standalone
│   ├── tester/SKILL.md         ← Wrapper → agents/tester.md
│   ├── coder/SKILL.md          ← Wrapper → agents/coder.md
│   ├── planner/SKILL.md        ← Wrapper → agents/planner.md
│   ├── bootstrap/SKILL.md      ← Standalone (Day 0 discovery)
│   └── claude-md-writer/SKILL.md ← Standalone (CLAUDE.md optimization)
│
├── contexts/
│   ├── shared.md               ← infra, db, llm
│   └── {domain}.md             ← per-domain context
│
└── settings.json               ← Claude Code settings
```

---

## Agent vs Skill

| Type | Location | Purpose | Has Agent? |
|------|----------|---------|------------|
| **Orchestrator** | skills/ | Multi-agent workflow | No (dispatches agents/) |
| **Wrapper** | skills/ | UX layer over agent | Yes (agents/*.md) |
| **Standalone** | skills/ | Self-contained logic | No |
| **Agent** | agents/ | Pure execution prompt | - |

---

## Step 1: Create Agents

Each agent has frontmatter with model and tools:

```markdown
---
name: coder
description: Write/modify code for autopilot tasks
model: sonnet
tools: Read, Glob, Grep, Edit, Write, Bash, mcp__exa__*, mcp__plugin_context7_*
---

# Coder Agent

[Execution prompt...]
```

**Agent Files:**
- `agents/spark.md` — opus (idea generation + research)
- `agents/planner.md` — opus (detailed planning)
- `agents/coder.md` — sonnet (code writing)
- `agents/tester.md` — sonnet (test running)
- `agents/debugger.md` — opus (root cause)
- `agents/spec-reviewer.md` — sonnet (spec matching)
- `agents/review.md` — opus (code quality)
- `agents/scout.md` — sonnet (research)
- `agents/documenter.md` — sonnet (docs)
- `agents/diary-recorder.md` — haiku (problem capture)

**Council Experts (in agents/council/):**
- `council/synthesizer.md` — opus (chairman Oracle)
- `council/architect.md` — opus (Winston)
- `council/product.md` — opus (John)
- `council/pragmatist.md` — opus (Amelia)
- `council/security.md` — opus (Viktor)

---

## Step 2: Create Skills

### Orchestrator Skill (spark, autopilot, council)

```markdown
---
name: autopilot
description: Autonomous task execution
model: opus
---

# Autopilot

[Orchestration logic that dispatches agents via Task tool]
```

### Wrapper Skill (scout, review, tester, coder, planner)

```markdown
---
name: tester
description: Run tests with Smart Testing
agent: .claude/agents/tester.md
---

# Tester Skill

[Validation, UX, then dispatch to agent]
```

---

## Step 3: Create settings.json

```json
{
  "skills": [
    { "name": "spark", "path": ".claude/skills/spark/SKILL.md" },
    { "name": "autopilot", "path": ".claude/skills/autopilot/SKILL.md" },
    { "name": "council", "path": ".claude/skills/council/SKILL.md" },
    { "name": "review", "path": ".claude/skills/review/SKILL.md" },
    { "name": "audit", "path": ".claude/skills/audit/SKILL.md" },
    { "name": "scout", "path": ".claude/skills/scout/SKILL.md" },
    { "name": "reflect", "path": ".claude/skills/reflect/SKILL.md" },
    { "name": "tester", "path": ".claude/skills/tester/SKILL.md" },
    { "name": "coder", "path": ".claude/skills/coder/SKILL.md" },
    { "name": "planner", "path": ".claude/skills/planner/SKILL.md" },
    { "name": "bootstrap", "path": ".claude/skills/bootstrap/SKILL.md" },
    { "name": "claude-md-writer", "path": ".claude/skills/claude-md-writer/SKILL.md" }
  ]
}
```

---

## Step 4: Model Routing

| Agent | Model | Why |
|-------|-------|-----|
| spark | opus | Deep research + dialogue |
| planner | opus | Architecture analysis |
| debugger | opus | Root cause needs depth |
| review | opus | Architecture review |
| council/* | opus | Complex decisions |
| coder | **sonnet** | 90% capability, 2x speed |
| tester | **sonnet** | Running tests, parsing |
| spec-reviewer | **sonnet** | Spec matching |
| scout | **sonnet** | Research aggregation |
| documenter | **sonnet** | Routine updates |
| diary-recorder | **haiku** | Simple logging |

**Dispatch via Task tool:**
```yaml
Task tool:
  subagent_type: "coder"  # Model from agent frontmatter
  prompt: |
    task: "Task 1/3 — Add validation"
    files:
      modify: [src/service.py]
```

---

## Skill Workflow

### Feature Flow

```
1. User: "Add feature X"
2. /spark
   - Research (Exa, Context7)
   - Socratic Dialogue
   - Create spec → Status = queued
3. "Spec ready. Starting autopilot?"
4. /autopilot (auto-handoff)
   - PHASE 0: Worktree + CI check
   - PHASE 1: [planner] → tasks
   - PHASE 2: [coder] → [tester] → [review] → commit (per task)
   - PHASE 3: Merge → develop
5. Status = done
```

### Bug Flow

```
1. User: "Bug in X"
2. Diagnose (5 Whys)
3. /spark (bug mode) → BUG-XXX spec
4. Continue as Feature Flow
```

---

## Council Workflow

```
1. /council invoked
2. Parallel: architect, product, pragmatist, security analyze
3. Cross-critique phase (peer review)
4. Synthesizer (Oracle) produces final decision
5. Return: approved | needs_changes | rejected
```

---

## Worktree Setup

**ALWAYS by default** (skip only for hotfixes <5 LOC).

```
Step 0: CI Health Check
  → ./scripts/ci-status.sh

Step 1: Branch by type
  → FTR → feature/FTR-XXX
  → BUG → fix/BUG-XXX

Step 2: Create worktree
  → git worktree add ".worktrees/{ID}" -b "{type}/{ID}"

Step 3: Setup + baseline
  → pip install && ./test fast
```

---

## Escalation

```
3 debug retries failed
        ↓
    Code bug? → Spark (BUG spec)
    Architecture? → Council
    Unclear? → STOP + ask human
```

---

## Testing

```bash
/spark quick      # Research + questions
/autopilot        # Worktree + subagents
/audit            # READ-ONLY analysis
/council          # 5 experts
/scout            # External research
/reflect          # Diary → rules
```

---

## Common Issues

### Skill not recognized
Check `settings.json` path.

### Wrong model
Add `model:` to agent frontmatter.

### Agent not found
Ensure `agent:` path in skill wrapper is correct.

### CI blocks work
Fix CI first — worktree setup checks status.

### Council not reaching consensus
Synthesizer has final say. If needs_human → STOP.
