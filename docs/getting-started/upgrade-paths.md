# Upgrade Paths

How to move between DLD tiers as your needs grow.

---

## Quick → Standard

**Time:** 3 minutes

### What You're Adding
- MCP servers (Context7 + Exa)
- Enhanced research capabilities
- Safety hooks

### Steps

```bash
# 1. Run MCP setup
./scripts/setup-mcp.sh --tier 2

# 2. Verify
./scripts/setup-mcp.sh --check

# 3. Update tier indicator in CLAUDE.md
# Change: **Tier:** 🏃 Quick
# To: **Tier:** ⭐ Standard
```

### Verification

```bash
claude
/scout "test query"
# Should use Exa for research
```

---

## Standard → Power

**Time:** 10 minutes

### What You're Adding
- Memory MCP (optional, requires API key)
- Sequential Thinking MCP
- `/council`, `/autopilot`, `/planner` skills
- Diary system

### Steps

```bash
# 1. Add Power MCP servers
./scripts/setup-mcp.sh --tier 3

# 2. If you have Memory API key:
claude mcp add memory -- npx -y @anthropic/memory-mcp

# 3. Verify
./scripts/setup-mcp.sh --check

# 4. Update tier indicator in CLAUDE.md
# Change: **Tier:** ⭐ Standard
# To: **Tier:** ⚡ Power
```

### Verification

```bash
claude
/council "architectural question"
# Should spawn 5 expert agents
```

---

## Quick → Power (Direct)

**Time:** 15 minutes

### Steps

```bash
# 1. Full MCP setup
./scripts/setup-mcp.sh --tier 3

# 2. Update CLAUDE.md tier indicator to ⚡ Power

# 3. Verify
./scripts/setup-mcp.sh --check
```

---

## Downgrade Paths

### Power → Standard

Remove advanced MCP servers:

```bash
# Remove from Claude settings
claude mcp remove memory
claude mcp remove sequential-thinking

# Update CLAUDE.md tier indicator
```

### Standard → Quick

Remove all MCP servers:

```bash
claude mcp remove context7
claude mcp remove exa

# Update CLAUDE.md tier indicator
```

---

## When to Upgrade

| Signal | Recommended Action |
|--------|-------------------|
| Research feels limited | Quick → Standard |
| Need team collaboration | Standard → Power |
| Complex architectural decisions | Standard → Power |
| Want autonomous execution | Standard → Power |
| Project growing >500 files | Standard → Power |

---

## Tier Comparison

| Feature | 🏃 Quick | ⭐ Standard | ⚡ Power |
|---------|----------|------------|---------|
| Setup time | 2 min | 5 min | 15 min |
| MCP servers | 0 | 2 | 4 |
| Research quality | Basic | Good | Excellent |
| Skills | 2 | 5 | 8 |
| Team features | ❌ | ❌ | ✅ |
| API keys needed | 0 | 0 | 1 (optional) |
