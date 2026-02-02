---
name: scout
description: |
  Isolated research agent for external sources (Exa + Context7).

  AUTO-ACTIVATE when user says:
  - "research", "find out", "look up"
  - "how does X work", "what's the best way to"
  - "find docs", "find examples"
  - "compare options", "what are alternatives"

  Also activate when:
  - User asks about library/framework usage
  - User needs current best practices (2024-2026)
  - Error message needs external context

  DO NOT USE when:
  - User wants full feature spec → use spark
  - User ready to implement → use autopilot
  - Analysis of own codebase → use audit
agent: .claude/agents/scout.md
---

# Scout Skill (Wrapper)

Invokes scout subagent for isolated research via Exa + Context7.

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
  max_turns: 8                    # quick: 8, deep: 15
  prompt: |
    MODE: quick | deep
    QUERY: {research question}
    TYPE: library | pattern | architecture | error | general
    DATE: {current date}
```

## Research Tools

Scout has access to:
- `mcp__exa__web_search_exa` — quick web search
- `mcp__exa__web_search_advanced_exa` — filtered search (dates, domains, categories)
- `mcp__exa__deep_search_exa` — multi-angle search with query expansion
- `mcp__exa__crawling_exa` — full page content extraction
- `mcp__exa__get_code_context_exa` — code examples and docs
- `mcp__plugin_context7_context7__resolve-library-id` — find library ID
- `mcp__plugin_context7_context7__query-docs` — official docs
- Read, Glob, Grep — codebase exploration

## Output

```json
{
  "solution": "Recommended approach",
  "why": "2-3 sentences rationale",
  "alternatives": [
    {"name": "Alt", "pros": [], "cons": [], "when_to_use": "..."}
  ],
  "sources": [
    {"title": "...", "url": "...", "relevance": "..."}
  ]
}
```

## Notes

- Scout isolates web search "garbage" from main context
- Use quick mode for simple questions, deep for complex topics
- max_turns prevents hanging: quick=8, deep=15
- Reliability rules: max 6 tool calls (quick) / 12 (deep), no retry loops
