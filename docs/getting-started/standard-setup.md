# ⭐ Standard Setup (5 minutes)

The recommended setup for active development. Includes MCP servers for enhanced research.

---

## What You Get

- ✅ Full CLAUDE.md template
- ✅ All core skills: `/spark`, `/scout`, `/audit`, `/review`
- ✅ MCP: Context7 (library docs) + Exa (web research)
- ✅ Safety hooks (pre-commit validation)
- ❌ No advanced MCP (Memory, Sequential Thinking)
- ❌ No `/council` or `/autopilot`

---

## Prerequisites

- Node.js 18+
- Git
- Claude Code CLI (`npm install -g @anthropic/claude-code`)

---

## Installation

```bash
# Create project (interactive MCP setup)
npx create-dld my-project --standard
cd my-project

# Or create then set up MCP separately
npx create-dld my-project --quick
cd my-project
./scripts/setup-mcp.sh --tier 2
```

---

## Verify Setup

```bash
# Check MCP servers are working
./scripts/setup-mcp.sh --check

# Expected output:
# ✓ Node.js OK
# ✓ npx OK
# ✓ claude CLI OK
# ✓ Context7 OK
# ✓ Exa (connectivity) OK
```

---

## First Run

```bash
claude

# Try enhanced research
/scout "best practices for TypeScript error handling 2026"

# Generate a feature spec
/spark "add user authentication with JWT"
```

---

## What's Included

### Skills

| Skill | Description |
|-------|-------------|
| `/spark` | Generate feature specifications with research |
| `/scout` | Deep web research with Exa |
| `/audit` | Code quality analysis |
| `/review` | Code review automation |

### MCP Servers

| Server | Function |
|--------|----------|
| Context7 | Real-time library documentation |
| Exa | Intelligent web search, code examples |

---

## What's Next?

- **Need team features?** [Power Setup](power-setup.md)
- **Want to upgrade later?** [Upgrade Paths](upgrade-paths.md)
- **Having issues?** [MCP Troubleshooting](../21-mcp-troubleshooting.md)
