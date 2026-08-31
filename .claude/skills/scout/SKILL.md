---
name: scout
description: Isolated research agent for external sources — provider cascade with fallback, answers from knowledge when a search isn't warranted.
agent: .claude/agents/scout.md
---

# Scout Skill (Wrapper)

Invokes scout subagent for isolated research across a fallback cascade of providers.

> **Architecture:** This skill is a WRAPPER over `.claude/agents/scout.md`.
> The agent file is the source of truth for the scout prompt.

## When to Use

**During Spark:** Before designing feature, gather external knowledge

**During Development:** When need library docs or patterns

## Invocation

```yaml
Task tool:
  description: "Scout research: {topic}"
  subagent_type: "scout"
  prompt: |
    MODE: quick | deep
    QUERY: {research question}
    TYPE: library | pattern | architecture | error | company | general
    DATE: {current date}
```

## Research Tools

Scout works down a cascade so one provider's rate limit can't end the research:
**Context7** (library questions) → **Exa** (primary semantic search) → **Jina** via WebFetch
(`s.jina.ai` / `r.jina.ai` — no key, no account) → **WebSearch** (built-in, no quota, last rung).

It also decides whether to search at all: training data runs to ~May 2026, so settled
questions get answered directly with `provider_used: knowledge` and an empty `sources` list.
Full rules in the agent file.

**Exa (web research)** — the server serves exactly two tools:
- `mcp__exa__web_search_exa` — find pages. Semantic: describe the ideal page, not keywords
- `mcp__exa__web_fetch_exa` — read pages in full when search highlights are too thin

**Context7 (library docs):**
- `mcp__plugin_context7_context7__resolve-library-id` — find library ID
- `mcp__plugin_context7_context7__query-docs` — official documentation

**Local:**
- Read, Glob, Grep — codebase exploration

## Output

```json
{
  "tldr": "One sentence: the best solution/answer",
  "recommendation": {
    "solution": "Recommended approach",
    "why": "2-3 sentences rationale",
    "confidence": "high | medium | low",
    "caveats": ["Limitation 1"]
  },
  "alternatives": [
    {"name": "Alt", "pros": [], "cons": [], "when_to_use": "..."}
  ],
  "sources": [
    {"title": "...", "url": "...", "type": "docs|blog|official", "relevance": "..."}
  ],
  "triangulation": {
    "verified_claims": ["Claim (confirmed by N sources)"],
    "conflicting_info": ["Topic: source1 vs source2"]
  }
}
```

## Notes

- Scout isolates web search "garbage" from main context
- Use quick mode for simple questions, deep for complex topics
- Always returns structured output with sources
