# ⚡ Power Setup (15 minutes)

Maximum capability for teams and complex projects. Includes all MCP servers and advanced skills.

---

## What You Get

- ✅ Everything from Standard tier
- ✅ Additional MCP: Memory (cross-session), Sequential Thinking
- ✅ Full skill suite: `/council`, `/autopilot`, `/planner`
- ✅ Diary system for AI learning
- ✅ Custom hooks template
- ✅ Full agent configuration

---

## Prerequisites

- Node.js 18+
- Git
- Claude Code CLI
- **Memory MCP API key** (from Anthropic) — optional but recommended

---

## Installation

### Option 1: Fresh Install

```bash
npx create-dld my-project --power
cd my-project
```

### Option 2: Upgrade from Standard

```bash
cd my-project
./scripts/setup-mcp.sh --tier 3
```

---

## Configure Memory MCP (Optional)

Memory MCP enables cross-session memory and team knowledge sharing.

1. Get API key from Anthropic
2. Add to Claude settings:

```bash
claude mcp add memory -- npx -y @anthropic/memory-mcp
# When prompted, provide your API key
```

---

## Verify Setup

```bash
./scripts/setup-mcp.sh --check

# Expected:
# ✓ All prerequisites OK
# ✓ Context7 OK
# ✓ Exa OK
# ✓ Memory OK (if configured)
# ✓ Sequential Thinking OK
```

---

## Full Skill Suite

| Skill | Description |
|-------|-------------|
| `/spark` | Feature specification with deep research |
| `/scout` | Comprehensive web research |
| `/audit` | Multi-zone code analysis |
| `/review` | Automated code review |
| `/council` | Multi-agent architectural review (5 experts) |
| `/autopilot` | Autonomous task execution with subagents |
| `/planner` | Detailed implementation planning |

---

## Power Features

### Council Review

Get 5 expert perspectives on architectural decisions:

```bash
/council "Should we use microservices or monolith for this project?"
```

Experts: Product Manager, Architect, Pragmatist, Security Engineer, and Synthesizer.

### Autopilot Mode

Autonomous task execution with planning, coding, testing, and review:

```bash
/autopilot TECH-001
```

### Diary System

AI learns from successes and failures:

```bash
# Recorded automatically during autopilot
# Review learnings:
cat ai/diary.md
```

---

## Team Configuration

For teams, consider:

1. **Shared Memory MCP** — Cross-session knowledge
2. **Custom Rules** — Team coding standards in `.claude/rules/`
3. **Hooks** — Enforce team policies

---

## What's Next?

- **Troubleshooting:** [MCP Troubleshooting](../21-mcp-troubleshooting.md)
- **Customize:** Edit `.claude/rules/` for team standards
- **Learn more:** [DLD Documentation](../../README.md)
