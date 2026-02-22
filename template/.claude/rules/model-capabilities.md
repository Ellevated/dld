# Model Capabilities (Claude Opus 4.6)

Reference for agents about current model capabilities.
Last updated: 2026-02-08

---

## Active Model: Claude Opus 4.6

**Released:** February 5, 2026
**Model ID:** `claude-opus-4-6`
**Pricing:** $5/$25 per million tokens (input/output)

---

## Key Capabilities

| Feature | Value | Notes |
|---------|-------|-------|
| Context window | 200K standard, 1M beta | Beta: $10/$37.50 for >200K |
| Max output tokens | 128K | Doubled from 64K in Opus 4.5 |
| Adaptive thinking | Default | Model decides when/how much to think |
| Effort levels | low / medium / high / max | Controls thinking depth |
| Fast mode | 2.5x faster output | Research preview, `/fast` toggle |

---

## Effort Routing Strategy

Agents should operate at different effort levels based on task complexity:

| Agent Role | Recommended Effort | Rationale |
|------------|-------------------|-----------|
| planner | max | Deep analysis, drift detection, solution design |
| council experts | max | Expert-level architectural decisions |
| debugger | max | Root cause analysis requires deep thinking |
| coder | high | Standard implementation work |
| review | high | Quality review needs careful analysis |
| scout | high | Research quality matters |
| tester | medium | Execution-focused, less reasoning needed |
| spec-reviewer | medium | Checklist verification, not creative work |
| documenter | medium | Structured output, clear patterns |
| diary-recorder | low | Simple capture, minimal reasoning |
| eval-judge | high | Rubric-based LLM output evaluation (sonnet) |
| bughunt scope-decomposer | medium | File listing and grouping (sonnet) |
| bughunt personas (6) | high | Deep analysis from specialized perspectives (sonnet) |
| bughunt findings-collector | medium | Normalization, no reasoning (sonnet) |
| bughunt spec-assembler | high | Structured assembly with ID protocol (sonnet) |
| bughunt validator | high | Triage requires good judgment (opus) |
| bughunt report-updater | medium | Structured update, clear patterns (sonnet) |
| bughunt solution-architect | high | Fix design needs careful analysis (opus) |
| triz data-collector | medium | Pure data extraction, no reasoning (sonnet) |
| triz toc-analyst | max | System-level constraint analysis (opus) |
| triz triz-analyst | max | System-level contradiction resolution (opus) |
| triz synthesizer | high | Merge and prioritize recommendations (opus) |

---

## Breaking Changes from Opus 4.5

| What | Impact | Action |
|------|--------|--------|
| Prefilling removed | `400` error on assistant prefills | Use structured outputs or system prompts |
| `output_format` deprecated | Will stop working | Use `output_config.format` instead |
| `interleaved-thinking` header | No longer needed | Remove beta header |

---

## What Agents Should Know

1. **Adaptive thinking is automatic** — no need to request "think harder"
2. **128K output** — can generate comprehensive plans in single pass
3. **1M context (beta)** — large codebases can fit entirely in context
4. **Context compaction** — server-side, enables infinite conversations
5. **Agent Teams** — research preview, direct agent-to-agent messaging

---

## Model Routing (SSOT in agent frontmatter)

| Model | Use For | Cost |
|-------|---------|------|
| opus | Complex reasoning, planning, review, council | $5/$25 |
| sonnet | Standard implementation, research, testing | $3/$15 |
| haiku | Simple capture, logging, quick checks | $1/$5 |

**Rule:** Model is defined ONCE in agent frontmatter `model:` field.
Never hardcode model in skill dispatch — use `subagent_type` only.

---

## MCP Tools: Deferred Loading

**CRITICAL:** Most MCP tools are **deferred** — they are NOT in your tool list until explicitly loaded via `ToolSearch`.

### The Problem

MCP servers (fal-ai, Notion, etc.) register tools as "deferred". If you check your available tools directly, deferred tools appear absent. This leads to false conclusions like "MCP not connected" or "tools unavailable".

### The Rule

**NEVER assume an MCP tool is unavailable. NEVER silently fall back to degraded mode.**

```
Step 1: ToolSearch(query: "{mcp-server-name}")     → loads matching tools
Step 2: Tools returned?  → available, proceed
Step 3: Nothing returned? → try alternative queries (tool name, alias)
Step 4: Still nothing?   → ASK THE USER with AskUserQuestion
                           Do NOT silently fall back!
```

**Why ask?** MCP servers can be configured but need session restart, or user may want to add one now. Silent fallback = user gets degraded output without knowing why.

### Common MCP Servers and Search Queries

| Server | Primary Query | Fallback Queries |
|--------|--------------|-----------------|
| fal-ai | `"fal-ai"` | `"generate_image"`, `"fal"` |
| Notion | `"notion"` | `"notion-search"` |
| Exa | `"exa"` | `"web_search_exa"` |
| Context7 | `"context7"` | `"resolve-library"` |
| Sequential Thinking | `"sequential"` | `"sequentialthinking"` |

### For Skill Authors

When writing skills that depend on MCP tools:
1. In Pre-flight section, use `ToolSearch` — not "check available tools"
2. Provide primary + fallback query strings
3. If all queries fail → use `AskUserQuestion` to confirm with user
4. **Never silently degrade** — user must know and approve fallback mode
