# Frequently Asked Questions

Quick answers to common questions about DLD.

---

## General

### What is DLD?

**DLD (Double-Loop Development)** is an LLM-first architecture methodology. It provides:
- A project structure optimized for AI context windows
- Workflows for spec-first development
- Specialized agents for different tasks (coding, testing, reviewing)
- Rules to prevent common AI coding failures

It's not an IDE or a tool — it's a way of working with AI coding assistants.

### What does "Double-Loop" mean?

The name comes from the two-loop development process:
1. **Outer loop:** Human → Spark (create spec) → Council (review) → Human approves
2. **Inner loop:** Autopilot → Plan → Code → Test → Review → Commit

The outer loop handles *what* to build. The inner loop handles *how* to build it.

### Who is DLD for?

DLD works best for:
- Solo developers or small teams (1-3 people)
- Developers who use AI for most of their coding
- Anyone building new products from scratch
- People frustrated with AI "breaking things" during multi-file changes

DLD may not be the best fit for:
- Large enterprise teams with established processes
- Codebases where humans do 90%+ of coding
- Quick prototypes that won't need maintenance

### How long does it take to learn?

| Level | Time | What you'll learn |
|-------|------|-------------------|
| Basic | 1 hour | Run /bootstrap, /spark, /autopilot |
| Intermediate | 1 day | Understand skills, agents, specs |
| Advanced | 1 week | Customize agents, optimize workflows |

Most developers are productive within a day.

---

## Compatibility

### Does it work with Python/JavaScript/Go/Rust/etc?

**Yes.** DLD is language-agnostic. The template includes Python examples, but the methodology applies to any language:
- The `src/domains/` structure works in any language
- CLAUDE.md format is universal
- Skills and agents don't care about your language

### Does it work with Cursor, VS Code, or other IDEs?

**Yes, with caveats:**
- DLD is designed for **Claude Code** (Anthropic's CLI)
- You can use any IDE for editing files
- Skills like `/spark` and `/autopilot` require Claude Code
- See [COMPARISON.md](COMPARISON.md) for Cursor-specific guidance

### Can I use it with my existing project?

**Yes.** See the [migration guide](docs/13-migration.md). The basic process:
1. Add `.claude/` folder with skills and agents
2. Create `CLAUDE.md` for your project
3. Gradually move code into `src/domains/` structure
4. Start using specs for new features

You don't have to migrate everything at once.

### Does it work with GPT-4, Gemini, or other models?

**Partially.** DLD is optimized for Claude because:
- Agent prompts use Claude-specific features
- Skills assume Claude Code CLI
- Context management targets Claude's window sizes

You could adapt the methodology for other models, but it would require significant prompt engineering.

### Does it require MCP servers (Exa, Context7)?

**No, but recommended.** The methodology works without external tools, but:
- **Exa** enables web research during spec creation
- **Context7** provides up-to-date library documentation

Without these, Spark and Scout have limited research capabilities.

---

## Workflow

### What's the difference between Skills and Agents?

| Skills | Agents |
|--------|--------|
| User-facing commands | Internal prompts |
| Start with `/` (`/spark`, `/autopilot`) | Called by skills |
| In `.claude/skills/` | In `.claude/agents/` |
| Orchestration logic | Single-task execution |

**Think of it this way:** Skills are recipes, agents are chefs. You ask for "pasta" (skill), the recipe orchestrates multiple chefs (agents) to make it.

### How does Spark differ from Autopilot?

| Spark | Autopilot |
|-------|-----------|
| Creates specs | Implements specs |
| Research phase | Execution phase |
| User dialogue | Autonomous |
| Writes to `ai/features/` | Writes to `src/` |
| Output: Feature spec | Output: Committed code |

**Flow:** Human → Spark (creates spec) → Autopilot (implements spec) → Done

### What if Autopilot gets stuck?

Autopilot has built-in escalation:
1. **Test fails:** Debugger agent analyzes, suggests fix
2. **After 3 attempts:** Creates a `BUG-XXX` spec and escalates
3. **Blocks on decisions:** Sets status to `blocked`, waits for human

If you're stuck:
1. Check the spec file for `blocked` status
2. Look for `ACTION REQUIRED` comments
3. Resolve the blocker, set status to `resumed`
4. Re-run Autopilot

### What are "worktrees" and why do they matter?

Git worktrees are separate working directories for the same repo. Autopilot uses them for isolation:

```bash
# Normal repo
my-project/  (main worktree)

# During Autopilot
my-project/  (main, untouched)
my-project-task-1/  (worktree for current task)
```

**Why it matters:**
- If a task fails, just delete the worktree — main is clean
- No "let me fix the fix for the fix" spirals
- Easy rollback: `git worktree remove my-project-task-1`

### How do I add a new skill or agent?

**New skill:**
1. Create `.claude/skills/my-skill/SKILL.md`
2. Follow the format in existing skills
3. Add entry to CLAUDE.md skills table

**New agent:**
1. Create `.claude/agents/my-agent.md`
2. Define frontmatter (name, model, tools)
3. Reference from a skill using `subagent_type: my-agent`

---

## Comparison

### How is DLD different from Superpowers?

See [COMPARISON.md](COMPARISON.md). The short answer:
- **Superpowers** is a VS Code extension for AI coding
- **DLD** is a methodology that works with Claude Code
- Superpowers focuses on automatic context detection
- DLD focuses on explicit spec-first development

### Why not just use Claude Code directly?

You can! DLD adds structure on top:

| Vanilla Claude Code | Claude Code + DLD |
|---------------------|-------------------|
| Chat-based | Spec-based |
| Single context | Multiple specialized agents |
| Ad-hoc testing | Automatic per-task testing |
| Manual rollback | Worktree isolation |
| No research phase | Mandatory Exa + Context7 |

If your tasks are simple (< 5 files), vanilla Claude Code works fine. For complex features, DLD prevents common failures.

### Is DLD a replacement for Clean Architecture?

**No.** DLD is a variant of domain-driven design, optimized for LLMs. Key differences:
- DLD has strict file size limits (400 LOC)
- DLD requires CLAUDE.md and context files
- DLD focuses on AI comprehension, not just human readability

Many DLD principles align with Clean Architecture (dependency direction, domain isolation). See [COMPARISON.md](COMPARISON.md) for details.

---

## Troubleshooting

### My CLAUDE.md is too long

Keep it under 200 lines. Move details to:
- `.claude/rules/` for architecture rules
- `.claude/contexts/` for domain contexts
- `ai/glossary/` for terminology

CLAUDE.md should be a summary, not the full specification.

### Agent uses wrong model (too expensive)

Check agent frontmatter. Default models:
- `opus` for complex tasks (planner, debugger, council)
- `sonnet` for routine tasks (coder, tester, documenter)
- `haiku` for simple tasks (diary-recorder)

Override with `model:` in frontmatter.

### Autopilot modifies files outside Allowed Files

This shouldn't happen — the `pre_edit.py` hook blocks it. If it does:
1. Check that hooks are installed (`.claude/hooks/`)
2. Verify spec has `## Allowed Files` section
3. Report the bug

### Skills not working after upgrade

After updating DLD:
1. Copy new `.claude/skills/` to your project
2. Update CLAUDE.md with new skill entries
3. Check for breaking changes in release notes

---

## Contributing

### How do I report a bug?

Open an issue on GitHub with:
- What you expected
- What happened
- Steps to reproduce
- Your CLAUDE.md (sanitized)

### How do I suggest a feature?

Open a GitHub discussion in the "Ideas" category. Include:
- Problem you're solving
- Proposed solution
- Alternatives considered

### Can I contribute a new skill/agent?

Yes! See [CONTRIBUTING.md](CONTRIBUTING.md). Requirements:
- Clear use case documentation
- Works with existing workflow
- Tested in a real project

---

## Still have questions?

- Check the [documentation](docs/)
- Open a [GitHub discussion](https://github.com/[your-repo]/dld/discussions)
- Read the [comparison guide](COMPARISON.md)
