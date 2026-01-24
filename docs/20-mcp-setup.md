# MCP Servers Setup

Model Context Protocol (MCP) servers extend Claude Code's capabilities with external tools.

## Overview

DLD uses MCP servers for:
- **Documentation lookup** — Context7 for up-to-date library docs
- **Web research** — Exa for intelligent web search

All MCP servers are **optional**. DLD works without them, but skills like `/scout` are more powerful with MCP.

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

**Purpose:** Intelligent web search with semantic understanding.

**Used by:** `/scout`, `/spark` (research phase)

**Installation:**

1. Get API key from [exa.ai](https://exa.ai)

2. Add to MCP config:
```bash
{
  "mcpServers": {
    "exa": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-exa"],
      "env": {
        "EXA_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Available tools:**
- `mcp__exa__web_search_exa` — semantic web search
- `mcp__exa__get_code_context_exa` — code-focused search

**Example usage in agent:**
```yaml
mcp__exa__web_search_exa:
  query: "FastAPI best practices 2024"
  numResults: 5
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

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@context7/mcp-server"]
    },
    "exa": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-exa"],
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
