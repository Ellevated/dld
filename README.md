# DLD: LLM-First Architecture

> Transform AI coding chaos into deterministic development

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Compatible-blue.svg)](https://claude.ai/code)
[![Version](https://img.shields.io/badge/version-3.3-green.svg)](CHANGELOG.md)

---

## The Problem

**90% debugging, 6% features** — the hidden cost of AI coding.

You've experienced it: Claude writes 200 lines, breaks 3 existing features, forgets context from last session, and you spend hours fixing what should have taken minutes.

DLD (Double-Loop Development) is a methodology that turns unpredictable AI sessions into systematic, reproducible development.

---

## Try Before You Dive

Ask any LLM to evaluate this approach:

```
Analyze the DLD methodology from github.com/[your-repo]/dld
Compare with how you currently handle multi-file changes
What problems does this solve?
```

---

## Quick Start (3 Steps)

```bash
# 1. Clone and copy template
git clone https://github.com/[your-repo]/dld
mkdir my-project && cd my-project
cp -r ../dld/template/* .
cp -r ../dld/template/.claude .

# 2. Start Claude Code
claude

# 3. Unpack your idea
> /bootstrap
```

That's it. Bootstrap will guide you through extracting your idea into structured specs.

---

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   /spark    │ ──▶ │  /autopilot │ ──▶ │    Done     │
│  (ideation) │     │ (execution) │     │  (commit)   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       ▼                   ▼
   Feature Spec      Plan + Code + Test + Review
   + Research        (isolated worktree)
```

**Key insight:** Separate *thinking* from *doing*. Spark researches and writes specs. Autopilot executes mechanically.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## License

MIT — See [LICENSE](LICENSE)
