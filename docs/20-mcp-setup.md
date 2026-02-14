# MCP Servers Setup

Model Context Protocol (MCP) servers extend Claude Code's capabilities with external tools.

## Choose Your Tier

| Tier | Servers | Setup Time | API Keys | Best For |
|------|---------|------------|----------|----------|
| **Quick** | None | 0 min | None | Quick evaluation |
| **Standard** | Context7 + Exa | 2 min | None | Active development |
| **Power** | + Memory + Sequential | 5 min | Memory key | Teams, complex projects |

**Recommendation:** Start with **Standard** tier. All features work, no API keys needed.

---

## Quick Tier (No MCP)

DLD works without MCP servers. Skills like `/scout` and `/spark` will use built-in WebSearch and WebFetch tools instead.

**Limitations:**
- No real-time library documentation (Context7)
- Basic web search instead of Exa deep research
- Research quality is lower but functional

**When to use:** Quick evaluation, offline environments, restricted networks.

---

## Standard Tier (Context7 + Exa)

**Setup time:** 2 minutes | **API keys:** None needed

```bash
# One-liner setup
claude mcp add context7 -- npx -y @context7/mcp-server && \
claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"
```

**What you get:**
- **Context7** - Real-time library documentation lookup
- **Exa** - Intelligent web search, code examples, deep research

**Verify installation:**
```bash
./scripts/setup-mcp.sh --check
```

---

## Power Tier (Teams & Complex Projects)

**Setup time:** 5 minutes | **API keys:** Memory MCP key required

Start with Standard tier, then add:

```bash
# Memory MCP (requires API key from Anthropic)
claude mcp add memory -- npx -y @anthropic/memory-mcp

# Sequential Thinking (no key needed)
claude mcp add sequential-thinking -- npx -y @anthropic/sequential-thinking-mcp
```

**What you get (in addition to Standard):**
- **Memory** - Cross-session memory, team knowledge sharing
- **Sequential Thinking** - Enhanced reasoning for complex problems

**When to use:** Large codebases, team environments, multi-day projects.

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

See [MCP Troubleshooting Guide](21-mcp-troubleshooting.md) for common issues and solutions.
