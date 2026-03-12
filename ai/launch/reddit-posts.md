# Reddit Posts Draft

Adapted posts for different subreddit communities.

---

## r/ClaudeAI

**Title:** I built a methodology for deterministic AI coding with Claude Code - sharing what worked

**Body:**

After 6 months of using Claude Code daily, I tracked where my time went: 90% debugging AI-generated code, 6% on actual features. The problem wasn't Claude — it was my approach.

So I built DLD (Domain-Level Design), a methodology that makes Claude Code predictable.

**What changed:**

1. **Spec-first** — Claude writes detailed specs before touching code. I approve the spec, then it implements.

2. **Worktree isolation** — Each task runs in its own git worktree. If something breaks, I just delete the worktree instead of debugging.

3. **Fresh agents** — New agent instance per task. No accumulated context confusion.

4. **LLM-optimized structure** — Max 400 LOC per file, explicit domain boundaries. Claude stays oriented.

**The result:** Features ship. Debugging dropped dramatically. Specs become documentation.

It's open source (MIT): [GitHub link]

**Key insight:** Give Claude explicit constraints, get consistent results. Free-form prompting is the enemy.

Happy to answer questions. What patterns have you found work well with Claude Code?

---

## r/programming

**Title:** DLD: An architecture pattern for predictable AI-assisted development

**Body:**

I've been exploring what makes AI coding predictable vs chaotic. After 6 months of iteration, I'm releasing DLD (Domain-Level Design).

**The problem:**

AI coding tools generate code faster than we can review it. Without structure, this leads to:
- Accumulated technical debt
- Context drift (AI "forgets" project conventions)
- Cyclic dependencies
- The 90/6 problem: 90% debugging, 6% features

**The approach:**

DLD is architecture patterns + workflows designed specifically for LLM capabilities and limitations:

1. **Spec-first development** — AI researches (via tools like Exa) and writes specs before implementing. You review specs, not code.

2. **Domain isolation** — Explicit dependency graph. No cycles. Each domain fits in a context window.

3. **Fresh context per task** — New agent instance, no hallucinations from previous tasks.

4. **File size limits** — Max 400 LOC. LLMs work better with focused files.

**Why it works:**

LLMs respond predictably to explicit structure. They struggle with ambiguity. DLD removes the ambiguity.

This isn't about specific tools — it's about principles that should apply to any LLM-assisted development.

GitHub: [link]
Docs: [link]

Curious what architectural patterns others have found effective for AI-assisted development. What's worked for you?

---

## r/opensource

**Title:** Releasing DLD — open source methodology for LLM-first development (MIT)

**Body:**

Releasing DLD (Domain-Level Design), a methodology for making AI-assisted coding deterministic rather than chaotic.

**What's included:**

- **19 documentation files** — principles, architecture patterns, workflows
- **9 skills** — reusable workflow templates (/spark, /autopilot, /council, etc.)
- **11 agent prompts** — specialized agents for coding, testing, reviewing
- **Project template** — ready to clone and adapt

**The idea:**

Most architecture patterns were designed for human developers. LLMs have different constraints — context windows, attention patterns, tendency to drift.

DLD adapts domain-driven design for LLM-first development:
- Smaller files (max 400 LOC)
- Explicit dependency graphs
- Persistent context (CLAUDE.md)
- Spec-first workflow

**Tech stack:**

- Works with Claude Code CLI
- Language-agnostic (docs use TypeScript examples)
- Built with Claude Opus 4.5

**License:** MIT

**Looking for:**

- Feedback on the methodology itself
- Contributions: additional skills, agents, or examples
- Translations (currently EN + RU)
- Examples from other tech stacks

GitHub: [link]

---

## Posting Notes

### Timing
- r/ClaudeAI: Post first (most relevant audience)
- r/programming: Wait 1-2 days (avoid crosspost spam perception)
- r/opensource: Wait 2-3 days

### Subreddit-specific notes

**r/ClaudeAI:**
- Audience knows Claude Code, speak to their experience
- Personal story resonates
- "What works for you?" question invites engagement

**r/programming:**
- More skeptical audience, focus on principles over tools
- Emphasize this isn't hype — it's architectural patterns
- Avoid marketing language entirely
- "What's worked for you?" question positions you as learner, not promoter

**r/opensource:**
- Focus on contribution opportunities
- List concrete assets (19 docs, 9 skills, etc.)
- MIT license prominent
- Ask for help with translations/examples

### Engagement rules
- Reply to every comment
- Acknowledge criticism constructively
- Don't defend — explain and learn
- Thank people who test/try it
