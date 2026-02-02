# Frequently Asked Questions

Common questions about DLD methodology.

---

## General

### What is DLD?

DLD (Double-Loop Development) is a methodology that turns unpredictable AI sessions into systematic, reproducible development. It provides structure for AI-assisted development: spec-first workflow, domain isolation, and multi-agent pipelines.

### Who is DLD for?

DLD is designed for:
- Solo developers and small teams (1-5 people)
- Anyone who uses AI coding assistants daily
- Developers building production systems, not just prototypes
- Those frustrated with unpredictable AI coding results

### How long does it take to learn?

- **Basic workflow:** 1 hour (run /spark, review spec, run /autopilot)
- **Full methodology:** 1-2 days (understand principles, customize agents)
- **Mastery:** 1-2 weeks (optimize for your specific use case)

### Is DLD a framework or library?

Neither. DLD is a **methodology** — a set of principles, conventions, and workflows. It doesn't add runtime dependencies to your project. The template provides configuration files for Claude Code.

---

## Compatibility

### Does it work with Python/JavaScript/Go/Rust/etc?

Yes. DLD is **language-agnostic**. The architecture principles (domain isolation, file size limits, dependency direction) apply to any language. The template includes examples for common stacks.

### Does it work with Cursor?

Yes, but with limitations. DLD is designed for **Claude Code CLI**. Cursor users can adopt DLD principles (CLAUDE.md, spec-first development, domain structure) but won't have access to the full skill/agent pipeline.

See [COMPARISON.md](COMPARISON.md#dld-vs-cursor) for details.

### Can I use it with my existing project?

Yes. See [Migration Guide](docs/13-migration.md) for step-by-step instructions. The basic approach:
1. Add `.claude/` directory structure
2. Create CLAUDE.md
3. Organize existing code into domains (gradually)

### Does it require specific AI models?

DLD is optimized for **Claude** (Anthropic) via Claude Code CLI. The methodology could work with other LLMs, but the agents and skills assume Claude's capabilities.

---

## Workflow

### What's the difference between Skills and Agents?

| Aspect | Skills | Agents |
|--------|--------|--------|
| Interface | User-facing (`/spark`, `/autopilot`) | Internal (called by skills) |
| Purpose | Entry points for workflows | Specialized execution |
| Examples | `/council`, `/audit`, `/tester` | coder, reviewer, planner |

Skills orchestrate agents. You invoke skills; skills invoke agents.

### How does Spark differ from Autopilot?

| Spark | Autopilot |
|-------|-----------|
| **Creates** feature specs | **Implements** feature specs |
| Research + design | Code + test + review |
| Outputs: spec file | Outputs: working code |
| Interactive (dialogue) | Autonomous (runs to completion) |

Typical flow: `/spark` → review spec → `/autopilot` → review PR

### What if Autopilot gets stuck?

1. Check the spec — unclear specs cause most issues
2. Look at the Autopilot Log in the spec file
3. Run `/audit` to analyze the current state
4. Update spec with clarifications and run `/autopilot` again

### What is the Council?

The Council (`/council`) is a multi-perspective review system. Five specialized agents (Architect, Pragmatist, Security, Product, Synthesizer) analyze your spec or code from different angles. Use it for:
- Complex architectural decisions
- High-risk changes
- When you want diverse expert opinions

---

## Comparison

### How is DLD different from Cursor/Superpowers?

DLD is a **methodology**, not an IDE or extension. It provides structure for *how* you work with AI, regardless of which tool you use.

See [COMPARISON.md](COMPARISON.md) for detailed comparisons with:
- Cursor
- Claude Code (vanilla)
- Superpowers
- Clean Architecture

### Why not just use Claude Code directly?

You can. Claude Code works fine without DLD. But DLD adds:
- **Context persistence** — CLAUDE.md and specs survive session resets
- **Predictable results** — spec-first workflow reduces variance
- **Safe experimentation** — worktree isolation prevents damage
- **Specialized agents** — optimized prompts for specific tasks
- **Quality gates** — two-stage review (spec + code)

### Is DLD compatible with Clean Architecture?

Yes, with adaptations. DLD shares principles with Clean Architecture (dependency direction, domain isolation) but optimizes for LLM constraints:
- Smaller files (max 400 LOC)
- Context-sized domains (~100 lines of business rules)
- Mandatory documentation (CLAUDE.md, per-domain rules)

See [COMPARISON.md](COMPARISON.md#dld-vs-clean-architecture) for details.

---

## Getting Started

### Where do I start?

1. Copy the [template](template/) to your project
2. Run `/bootstrap` to initialize
3. Run `/spark` for your first feature
4. Review the generated spec
5. Run `/autopilot` to implement

### What's the minimum setup?

At minimum, you need:
- Claude Code CLI installed
- `CLAUDE.md` in your project root
- `.claude/` directory with settings

Full template is recommended but not required.

### Where can I get help?

- [GitHub Discussions](https://github.com/Ellevated/dld/discussions) — ask questions, share ideas
- [Documentation](docs/) — full methodology reference
- [GitHub Issues](https://github.com/Ellevated/dld/issues) — bug reports
- This FAQ — common questions

---

## Technical

### What are the file size limits?

- **Max 400 lines** per file (LLM context optimization)
- **~100 lines** of business rules per domain
- Split larger files into modules

### How do domains relate to folders?

```
src/domains/
├── users/          # Domain folder
│   ├── index.ts    # Public API
│   ├── service.ts  # Business logic
│   ├── types.ts    # Domain types
│   └── rules.md    # Domain context for LLM
└── orders/
    └── ...
```

Each domain has one folder. Dependencies flow in one direction (DAG, no cycles).

### What goes in CLAUDE.md?

- Project tech stack
- Architecture overview
- Key commands (build, test, lint)
- Domain map with dependencies
- Project-specific conventions

See [CLAUDE.md Template](docs/04-claude-md-template.md).
