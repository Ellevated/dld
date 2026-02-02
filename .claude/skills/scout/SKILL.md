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
  prompt: |
    MODE: quick | deep
    QUERY: {research question}
    TYPE: library | pattern | architecture | error | company | general
    DATE: {current date}
```

## Research Tools

Scout has access to:

**Exa (web research):**
- `mcp__exa__web_search_exa` — web search with clean content
- `mcp__exa__web_search_advanced_exa` — filtered search (date, domain)
- `mcp__exa__get_code_context_exa` — code from GitHub, StackOverflow
- `mcp__exa__deep_search_exa` — deep search with query expansion
- `mcp__exa__crawling_exa` — extract content from specific URL
- `mcp__exa__company_research_exa` — company information
- `mcp__exa__deep_researcher_start` — start AI researcher (complex topics)
- `mcp__exa__deep_researcher_check` — get deep research results

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
