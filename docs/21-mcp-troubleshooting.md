# MCP Troubleshooting Guide

Common issues and solutions for MCP server configuration.

---

## Quick Health Check

```bash
# Check all configured MCP servers
./scripts/setup-mcp.sh --check
```

---

## Common Errors

### "MCP server not found"

**Symptom:** Claude Code doesn't show MCP tools in suggestions.

**Causes:**
1. Node.js not installed or not in PATH
2. npx command failing silently
3. Config file syntax error

**Solutions:**

```bash
# 1. Verify Node.js
node --version  # Should be 18+
npx --version   # Should work

# 2. Test npx manually
npx -y @context7/mcp-server --help

# 3. Validate config JSON
cat ~/.claude/settings.json | python3 -m json.tool
```

---

### "Tool not available" in Claude Code

**Symptom:** MCP is configured but tools like `mcp__exa__web_search_exa` don't appear.

**Solutions:**
1. **Restart Claude Code** - MCP servers load on startup
2. **Check tool names** - Names are case-sensitive
3. **Verify server is running:**

```bash
# Test Context7
npx -y @context7/mcp-server --help

# Test Exa connectivity
curl -s "https://mcp.exa.ai/mcp" | head -c 100
```

---

### "Connection closed unexpectedly"

**Symptom:** MCP works initially then stops responding.

**Cause:** Idle timeout from proxies or long-running operations.

**Solutions:**
1. Restart Claude Code session
2. Check for network proxy settings
3. For Exa HTTP transport, connection should auto-reconnect

---

### "Request timed out" (Exa)

**Symptom:** Web search or deep research takes too long.

**Cause:** Complex queries, network latency, or Exa service load.

**Solutions:**
1. Simplify query
2. Use `web_search_exa` instead of `deep_search_exa` for faster results
3. Check Exa status: https://status.exa.ai/

---

### "Memory MCP authentication failed"

**Symptom:** Memory server fails to start.

**Cause:** Missing or invalid API key.

**Solutions:**
```bash
# 1. Verify key is set in config
grep -A5 "memory" ~/.claude/settings.json

# 2. Test key manually
MEMORY_API_KEY=your-key npx -y @anthropic/memory-mcp --test
```

---

## Debug Mode

Enable verbose logging to diagnose issues:

```bash
# Set debug environment
export MCP_DEBUG=1

# Restart Claude Code
claude
```

Check logs in:
- macOS: `~/Library/Logs/Claude/`
- Linux: `~/.local/share/claude/logs/`

---

## Fallback Behavior

When MCP servers are unavailable, DLD gracefully degrades:

| Feature | With MCP | Without MCP |
|---------|----------|-------------|
| `/scout` research | Exa deep search | WebSearch tool |
| Library docs | Context7 real-time | WebFetch from docs sites |
| Code examples | Exa code context | WebSearch + WebFetch |

**Key point:** DLD always works. MCP enhances but doesn't block.

---

## Getting Help

1. Check this guide
2. Run `./scripts/setup-mcp.sh --check` for diagnostics
3. Open an issue: https://github.com/Ellevated/dld/issues

Include in your issue:
- Output of `./scripts/setup-mcp.sh --check`
- Node.js version (`node --version`)
- OS and version
