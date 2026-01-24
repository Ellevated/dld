---
name: scout
description: Isolated research agent for external sources
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
    TYPE: library | pattern | architecture | general
    DATE: {current date}
```

## Research Tools

Scout has access to:
- `mcp__exa__web_search_exa` — web search
- `mcp__exa__get_code_context_exa` — code examples
- `mcp__plugin_context7_context7__resolve-library-id` — find library ID
- `mcp__plugin_context7_context7__query-docs` — official docs
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
