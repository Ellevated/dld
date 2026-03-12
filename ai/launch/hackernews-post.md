# HackerNews Post Draft

## Title

Show HN: DLD – An LLM-First Architecture Methodology for AI Coding

## Body

Hi HN,

After a year of coding with Claude and GPT, I tracked where my time went: 90% debugging AI-generated code, 6% on actual features.

The issue wasn't the LLMs — it was architecture designed for humans, not language models.

DLD is a methodology that fixes this:

- **Spec-first development** — AI writes a spec with allowed files before touching code
- **Worktree isolation** — each task gets its own git worktree, so mistakes don't accumulate
- **Fresh context per task** — new agent instance, no hallucinations from previous context
- **Domain-driven structure** — max 400 LOC files, explicit dependency graph

Key insight: LLMs work better with explicit constraints than free-form coding.

This isn't an IDE or plugin — it's a methodology that works with Claude Code CLI. The template provides CLAUDE.md, agent prompts, and workflow skills (/spark, /autopilot).

What makes it different from Cursor/Superpowers: it's architecture-first, not tool-first.

Repo: [link]

Built over 6 months of production use. Happy to answer questions about the methodology.

---

## Notes for Posting

- Post Tuesday-Thursday, 9-11am PT (peak HN traffic)
- Title alternatives:
  - "Show HN: DLD – Architecture patterns for predictable AI coding"
  - "Show HN: DLD – From 90% debugging to 90% building with AI"
- Don't ask for upvotes
- Respond to every comment thoughtfully
- Be ready to explain: Why not just use .cursorrules? What's different about "LLM-first"?
- Key talking points:
  - Context window limits require smaller files
  - Agents need explicit boundaries (allowed files list)
  - Spec-first prevents scope creep
  - Fresh context per task prevents hallucination accumulation
