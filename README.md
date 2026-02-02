# DLD: Double-Loop Development

> Turn Claude Code into an Autonomous Developer

**Write specs, not code.** A methodology for deterministic AI development with fresh subagents, worktree isolation, and automatic rollback.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Compatible-blue.svg)](https://claude.ai/code)
[![Version](https://img.shields.io/badge/version-3.4-green.svg)](CHANGELOG.md)

---

## See It In Action

![DLD Workflow Demo](assets/demo/workflow.gif)

*From idea to shipped code in 3 commands: `/bootstrap` → `/spark` → `/autopilot`*

---

## The Problem

**90% debugging, 6% features** — the hidden cost of AI coding.

You've experienced it: Claude writes 200 lines, breaks 3 existing features, forgets context from last session, and you spend hours fixing what should have taken minutes.

DLD (Double-Loop Development) is a methodology that turns unpredictable AI sessions into systematic, reproducible development.

---

## Try Before You Dive

Ask any LLM to evaluate this approach:

```
Analyze the DLD methodology from github.com/Ellevated/dld
Compare with how you currently handle multi-file changes
What problems does this solve?
```

---

## Quick Start

### Option 1: NPX (Recommended)

```bash
npx create-dld my-project
cd my-project
claude
/bootstrap
```

### Option 2: Manual

```bash
git clone https://github.com/Ellevated/dld
mkdir my-project && cd my-project
cp -r ../dld/template/* .
cp -r ../dld/template/.claude .
claude
/bootstrap
```

### Optional: Configure MCP Servers

**Recommended** (no API keys needed):
```bash
claude mcp add context7 -- npx -y @context7/mcp-server
claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"
```

Or run the interactive setup:
```bash
./scripts/setup-mcp.sh
```

MCP enhances `/scout` and `/spark` with real-time docs and web research. See [MCP Setup Guide](docs/20-mcp-setup.md) for all tiers.

That's it. Bootstrap will guide you through extracting your idea into structured specs.

---

## How It Works

```mermaid
flowchart LR
    A[Idea] --> B[/spark]
    B --> C{Spec Ready?}
    C -->|Yes| D[/autopilot]
    C -->|No| B
    D --> E[Plan Subagent]
    E --> F[Coder]
    F --> G[Tester]
    G --> H{Tests Pass?}
    H -->|Yes| I[Reviewer]
    H -->|No| F
    I --> J{Approved?}
    J -->|Yes| K[Commit]
    J -->|No| F
    K --> L{More Tasks?}
    L -->|Yes| F
    L -->|No| M[Done]
```

### Workflow Steps

1. **Idea** — You describe what you want to build
2. **/spark** — AI researches and creates a detailed spec
3. **Spec Ready?** — Human reviews and approves the spec
4. **/autopilot** — Autonomous execution begins in isolated worktree
5. **Plan → Code → Test → Review** — Each task is executed by fresh subagents
6. **Done** — All tasks completed, merged to develop

### Fresh Subagents Per Task

```mermaid
flowchart TD
    subgraph Autopilot
        P[Planner] --> C1[Task 1]
        C1 --> |Fresh Agent| CO1[Coder]
        CO1 --> TE1[Tester]
        TE1 --> RE1[Reviewer]
        RE1 --> CM1[Commit]
        CM1 --> C2[Task 2]
        C2 --> |Fresh Agent| CO2[Coder]
        CO2 --> TE2[Tester]
        TE2 --> RE2[Reviewer]
        RE2 --> CM2[Commit]
    end
```

**Key insight:** Each task gets fresh context. No cross-contamination between tasks. If Task 1 fails, Task 2 isn't affected.

---

## Key Concepts

### Skills vs Agents

| Skills | Agents |
|--------|--------|
| User-facing commands (`/spark`, `/autopilot`) | Internal prompts (planner, coder, tester) |
| Orchestration logic | Single-task execution |
| In `skills/*.md` | In `agents/*.md` |

### Worktree Isolation

Every Autopilot task runs in a fresh git worktree. If something breaks — `git worktree remove` and start clean. No more "let me fix the fix for the fix."

### Spec-First Development

Before any code is written:
1. Research via Exa + Context7
2. Write detailed spec with allowed files
3. Break into atomic tasks
4. Execute mechanically

---

## Project Structure

```
my-project/
├── .claude/
│   ├── skills/          # 8 skills (bootstrap, spark, autopilot, ...)
│   ├── agents/          # 10 agent prompts (planner, coder, ...)
│   ├── rules/           # Architecture constraints
│   └── contexts/        # Domain-specific context
├── ai/
│   ├── idea/            # From /bootstrap
│   ├── features/        # Task specs
│   ├── diary/           # Session learnings
│   └── backlog.md       # Task queue
├── src/
│   ├── shared/          # Common types, Result pattern
│   ├── infra/           # DB, LLM, external APIs
│   ├── domains/         # Business logic (DDD)
│   └── api/             # Entry points
└── CLAUDE.md            # Main context file
```

---

## Skills

| Skill | When to Use |
|-------|-------------|
| `/bootstrap` | Day 0 — extract idea from your head |
| `/spark` | New feature, bug, architecture decision |
| `/autopilot` | Autonomous execution with fresh subagents |
| `/council` | Complex decisions (5 AI experts debate) |
| `/audit` | READ-ONLY code analysis |
| `/reflect` | Synthesize diary into CLAUDE.md rules |
| `/scout` | Isolated research (Exa + Context7) |

---

## Documentation

### Foundation
- [Why DLD?](docs/foundation/00-why.md) — The entrepreneur's pain
- [Double-Loop Concept](docs/foundation/01-double-loop.md) — Core methodology
- [Agent Roles](docs/foundation/02-agent-roles.md) — Who does what

### Architecture
- [Principles](docs/01-principles.md) — Core rules
- [Project Structure](docs/03-project-structure.md) — How to organize
- [CLAUDE.md Template](docs/04-claude-md-template.md) — Context file guide
- [Anti-patterns](docs/07-antipatterns.md) — What to avoid

### Workflows
- [Skills Setup](docs/15-skills-setup.md) — How to configure skills
- [Spec Template](docs/18-spec-template.md) — Writing good specs
- [MCP Setup](docs/20-mcp-setup.md) — Context7 + Exa configuration

---

## Comparison

| Feature | DLD | Plain Claude Code | Cursor |
|---------|-----|-------------------|--------|
| Context persistence | Spec files | Session memory | Chat history |
| Multi-file changes | Atomic worktrees | Same context | Same context |
| Research before code | Mandatory (Exa) | Optional | Optional |
| Rollback strategy | `git worktree remove` | Manual revert | Manual revert |
| Test isolation | Per-task scope | Global | Global |
| Review process | Spec → Code → Review | Ad-hoc | Ad-hoc |

---

## TL;DR

```
1. Colocation > Separation by type
2. One domain = one context (~100 lines)
3. Self-describing names (no abbreviations)
4. Dependency graph = DAG (no cycles)
5. Max 400 LOC per file (600 for tests)
6. Max 5 exports in __init__.py
7. Skills workflow: spark → autopilot
```

**Success metric:** If a new developer understands the project in 30 minutes — LLM understands it in 30 seconds.

---

## Community

Join our Discord for help, discussions, and feature requests:

[![Discord](https://img.shields.io/discord/XXXXXXXXX?color=7289da&label=Discord&logo=discord&logoColor=white)](https://discord.gg/INVITE_CODE)

---

## Used By

This is a new project. Be among the first to try it!

If you're using DLD, we'd love to hear about it:
- [Share your experience](https://github.com/Ellevated/dld/issues/new?labels=testimonial&title=My+DLD+Experience)
- [Submit a showcase](https://github.com/Ellevated/dld/issues/new?template=showcase.md)

Early adopters will be featured here.

---

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=.claude/hooks --cov-report=term-missing

# Run specific test file
pytest tests/test_pre_edit.py -v
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## License

MIT — See [LICENSE](LICENSE)
