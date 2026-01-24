# DLD Comparison

A fair, factual comparison of DLD with other approaches to AI-assisted development.

---

## TL;DR

| Aspect | DLD | Cursor | Superpowers | Clean Architecture |
|--------|-----|--------|-------------|-------------------|
| **Type** | Methodology | IDE | IDE Extension | Design Pattern |
| **Focus** | LLM context management | AI code completion | AI coding assistant | Code organization |
| **Learning curve** | Medium | Low | Low | High |
| **Best for** | Production systems | Quick edits | Enhancements | Enterprise apps |

---

## DLD vs Cursor

### What they are

**Cursor** is an AI-powered IDE built on VS Code. It provides inline AI suggestions, chat-based code generation, and multi-file editing capabilities.

**DLD** is a development methodology. It doesn't replace your IDE — it provides structure for how you work with AI agents.

### Comparison

| Aspect | Cursor | DLD |
|--------|--------|-----|
| Installation | Download IDE | Copy template to project |
| AI model | Built-in Claude/GPT | Works with any Claude interface |
| Project structure | Your choice | Prescribed (domains, specs, etc.) |
| Context management | Chat history + .cursorrules | CLAUDE.md + feature specs |
| Multi-file changes | Composer mode | Worktree isolation |
| Rollback | Manual git revert | `git worktree remove` |
| Research phase | Optional | Mandatory (Exa, Context7) |
| Review process | None built-in | Spec reviewer + Code reviewer |

### When to use

**Use Cursor when:**
- Quick prototyping and exploration
- Single-file edits
- You prefer an integrated IDE experience
- Learning AI coding

**Use DLD when:**
- Building production systems
- Working on multi-file features
- You need reproducible results
- Team collaboration required
- Context persistence matters

**Combine them:** Many DLD users use Cursor as their IDE with DLD methodology on top.

---

## DLD vs Claude Code (Vanilla)

### What they are

**Claude Code** is Anthropic's official CLI for Claude. It provides terminal-based access to Claude with file read/write capabilities.

**DLD** is a methodology that runs ON TOP of Claude Code. It adds structure, workflows, and agent specialization.

### Comparison

| Aspect | Claude Code (Vanilla) | Claude Code + DLD |
|--------|----------------------|-------------------|
| Context | Conversation only | CLAUDE.md + specs + rules |
| Workflow | Ad-hoc requests | Spark → Autopilot pipeline |
| Multi-file | Same conversation | Fresh subagent per task |
| Research | Manual web search | Integrated Exa + Context7 |
| Specs | None | Feature specs with allowed files |
| Testing | Run when you remember | Automatic per task |
| Review | None | Two-stage (spec + code) |
| Rollback | Manual | Worktree isolation |

### When to use

**Use Vanilla Claude Code when:**
- Simple one-off tasks
- Exploring a codebase
- Quick fixes (< 5 lines)
- Learning Claude Code

**Use DLD when:**
- Feature development
- Bug fixes that touch multiple files
- You want context to persist between sessions
- You need predictable results

---

## DLD vs Superpowers

### What they are

**Superpowers** is a VS Code extension that adds AI coding capabilities with context awareness and multi-file editing.

**DLD** is a methodology for structuring AI development, independent of IDE choice.

### Comparison

| Aspect | Superpowers | DLD |
|--------|-------------|-----|
| Type | VS Code extension | Methodology |
| Context | Automatic codebase indexing | Manual context files |
| Workflow | Request → Generate | Spec → Plan → Execute → Review |
| Spec files | None | Required for every feature |
| Agent specialization | Single agent | Multiple specialized agents |
| Research | Limited | Mandatory (Exa, Context7) |
| Cost control | Per-request | Task-scoped budgets |

### When to use

**Use Superpowers when:**
- You prefer staying in VS Code
- Quick code generation tasks
- Working with existing codebases
- You want automatic context detection

**Use DLD when:**
- Building new systems from scratch
- You need explicit context control
- Complex features with dependencies
- You want task isolation

---

## DLD vs Clean Architecture

### What they are

**Clean Architecture** is a software design philosophy by Robert Martin emphasizing separation of concerns, dependency inversion, and testability.

**DLD** is an LLM-optimized variant of domain-driven design, specifically structured for AI agent comprehension.

### Comparison

| Principle | Clean Architecture | DLD |
|-----------|-------------------|-----|
| Core idea | Dependency inversion | LLM context windows |
| Layers | Entities → Use Cases → Interface | shared → infra → domains → api |
| File size | No limit | Max 400 LOC (LLM-friendly) |
| Dependencies | Inward only | DAG, no cycles |
| Domain definition | Business logic isolation | Context-sized chunks (~100 lines) |
| Testing | Unit + Integration | Collocated + Immutable contracts |
| Documentation | Optional | CLAUDE.md + per-domain context |

### Key differences

**Clean Architecture** optimizes for:
- Human developers reading code
- Long-term maintainability
- Theoretical purity

**DLD** optimizes for:
- LLM context window limits
- AI agent comprehension
- Fast iteration with AI

### When to use

**Use Clean Architecture when:**
- Large team of human developers
- Long-term enterprise project
- You have architects reviewing PRs
- Theoretical correctness matters

**Use DLD when:**
- Solo developer or small team
- AI does most of the coding
- Rapid iteration needed
- Context management is the bottleneck

**Note:** DLD incorporates many Clean Architecture ideas (dependency direction, domain isolation) but adapts them for LLM constraints.

---

## Feature Matrix

| Feature | DLD | Cursor | Superpowers | Clean Arch |
|---------|:---:|:------:|:-----------:|:----------:|
| Spec-first development | ✓ | - | - | - |
| Worktree isolation | ✓ | - | - | - |
| Mandatory research phase | ✓ | - | - | - |
| Multi-agent pipeline | ✓ | - | - | - |
| Two-stage review | ✓ | - | - | - |
| File size limits | ✓ | - | - | - |
| Context persistence | ✓ | Partial | Partial | N/A |
| IDE integration | Any | Native | VS Code | Any |
| Learning resources | Docs | Videos | Docs | Books |
| Community | GitHub | Discord | GitHub | Large |

---

## Summary: When to Use What

### Use DLD when:
- You're building a new product from scratch
- AI agents do most of your coding
- You need reproducible, predictable results
- Context management is your bottleneck
- You work solo or in a small team

### Use Cursor when:
- You want an integrated IDE experience
- Quick prototyping and exploration
- You prefer visual interfaces
- Learning AI-assisted coding

### Use Superpowers when:
- You're committed to VS Code
- Enhancing an existing codebase
- You want automatic context detection

### Use Clean Architecture when:
- Large team of human developers
- Enterprise environment with architects
- Theoretical correctness matters most
- Long-term project (5+ years)

### Combine approaches:
- **Cursor + DLD:** Use Cursor as IDE, DLD as methodology
- **Superpowers + DLD:** Use Superpowers for quick edits, DLD for features
- **Clean Architecture + DLD:** Apply DLD's file size limits and context rules to Clean Architecture structure

---

## Not Covered

This comparison focuses on development methodology. It does not compare:
- Pricing (changes frequently)
- Model quality (depends on provider)
- Specific features (change with updates)

For the most current information, check each tool's official documentation.
