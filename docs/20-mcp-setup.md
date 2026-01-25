# MCP Servers Setup

Model Context Protocol (MCP) servers extend Claude Code's capabilities with external tools.

## Quick Start

**Fastest way to get started:**

```bash
# Context7 — library documentation
claude mcp add context7 -- npx -y @context7/mcp-server

# Exa — web search (hosted, all tools enabled)
claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,linkedin_search_exa,deep_researcher_start,deep_researcher_check"
```

That's it! Restart Claude Code and MCP tools are available.

---

## Overview

DLD uses MCP servers for:
- **Documentation lookup** — Context7 for up-to-date library docs
- **Web research** — Exa for intelligent web search, code examples, company research, deep research

All MCP servers are **optional**. DLD works without them, but skills like `/scout` are significantly more powerful with MCP.

---

## Recommended Servers

### Context7

**Purpose:** Query up-to-date documentation for any library.

**Used by:** `/scout`, `/spark` (research phase)

**Installation:**

```bash
# Add to Claude Code MCP config (~/.claude/settings.json or project's .claude/settings.json)
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@context7/mcp-server"]
    }
  }
}
```

**Available tools:**
- `mcp__plugin_context7_context7__resolve-library-id` — find library ID
- `mcp__plugin_context7_context7__query-docs` — query documentation

**Example usage in agent:**
```yaml
# First resolve library ID
mcp__plugin_context7_context7__resolve-library-id:
  libraryName: "fastapi"
  query: "how to create middleware"

# Then query docs
mcp__plugin_context7_context7__query-docs:
  libraryId: "/tiangolo/fastapi"
  query: "middleware creation example"
```

---

### Exa

**Purpose:** Intelligent web search, code examples, company research, and deep AI-powered research.

**Used by:** `/scout`, `/spark` (research phase)

**Installation (Recommended — Hosted):**

No API key needed! Connect directly to Exa's hosted MCP server:

```bash
# All tools enabled
claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,linkedin_search_exa,deep_researcher_start,deep_researcher_check"
```

**Alternative — Local with API key:**

1. Get API key from [exa.ai](https://exa.ai)

2. Add to MCP config:
```json
{
  "mcpServers": {
    "exa": {
      "command": "npx",
      "args": ["-y", "exa-mcp-server"],
      "env": {
        "EXA_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Available tools:**

| Tool | Description | Default |
|------|-------------|---------|
| `web_search_exa` | Web search with clean content extraction | Yes |
| `get_code_context_exa` | Code snippets from GitHub, StackOverflow | Yes |
| `company_research_exa` | Research companies by crawling websites | Yes |
| `web_search_advanced_exa` | Advanced search with filters | No |
| `deep_search_exa` | Deep search with query expansion | No |
| `crawling_exa` | Extract content from specific URLs | No |
| `linkedin_search_exa` | Search LinkedIn for people/companies | No |
| `deep_researcher_start` | Start AI researcher for complex questions | No |
| `deep_researcher_check` | Check research status and get report | No |

**Enable specific tools:**

```
https://mcp.exa.ai/mcp?tools=web_search_exa,deep_search_exa,crawling_exa
```

**Example usage in agent:**
```yaml
# Basic web search
mcp__exa__web_search_exa:
  query: "FastAPI best practices 2025"
  numResults: 5

# Deep research (async)
mcp__exa__deep_researcher_start:
  query: "Compare React Server Components vs traditional SSR"

# Get content from URL
mcp__exa__crawling_exa:
  url: "https://example.com/article"
```

---

## Configuration Location

MCP servers can be configured at two levels:

### Global (all projects)
```
~/.claude/settings.json
```

### Per-project
```
.claude/settings.json
```

Project settings override global settings.

---

## Full Example Configuration

**Option 1: Hosted Exa (no API key needed)**

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@context7/mcp-server"]
    },
    "exa": {
      "type": "http",
      "url": "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,linkedin_search_exa,deep_researcher_start,deep_researcher_check"
    }
  }
}
```

**Option 2: Local Exa with API key**

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@context7/mcp-server"]
    },
    "exa": {
      "command": "npx",
      "args": ["-y", "exa-mcp-server"],
      "env": {
        "EXA_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

---

## Verification

After configuring, verify MCP servers are working:

1. Start Claude Code
2. Run `/scout` skill with a research query
3. Check that Context7 or Exa tools are being called

If tools are not available, check:
- Node.js is installed (`node --version`)
- MCP config JSON is valid
- API keys are set correctly (for Exa)

---

## Without MCP

If MCP servers are not configured:
- `/scout` will use built-in `WebSearch` and `WebFetch` tools
- Documentation lookups will rely on `WebFetch` instead of Context7
- Research quality may be lower but skills will still work

---

## Security Notes

- API keys should not be committed to git
- Use environment variables or secrets management for production
- MCP servers run locally and communicate with Claude Code via stdio

---

## Troubleshooting

### "MCP server not found"
- Ensure Node.js and npm are installed
- Try running the npx command manually to check for errors

### "Tool not available"
- Restart Claude Code after adding MCP config
- Check that tool names match exactly (case-sensitive)

### "API key invalid" (Exa)
- Verify API key is correct
- Check that env variable is properly set in config
