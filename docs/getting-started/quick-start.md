# 🏃 Quick Start (2 minutes)

Get DLD running in under 2 minutes. Perfect for trying it out or small scripts.

---

## What You Get

- ✅ Core CLAUDE.md template
- ✅ `/spark` for idea generation
- ❌ No MCP servers (uses built-in web search)
- ❌ No hooks (no validation)

---

## Installation

```bash
npx create-dld my-project --quick
cd my-project
```

---

## First Run

```bash
# Start Claude Code
claude

# Try the spark skill
/spark "build a CLI tool that converts markdown to HTML"
```

That's it! You're running DLD.

---

## What's Next?

When you're ready for more:
- **Add MCP servers** for better research: [Standard Setup](standard-setup.md)
- **Enable all features**: [Power Setup](power-setup.md)
- **Understand upgrade options**: [Upgrade Paths](upgrade-paths.md)

---

## Limitations

Without MCP servers:
- `/scout` uses basic web search instead of Exa deep research
- No real-time library documentation from Context7
- Research quality is functional but limited

These work fine for quick prototypes but may slow you down on larger projects.
