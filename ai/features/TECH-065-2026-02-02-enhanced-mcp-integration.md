# Feature: [TECH-065] Enhanced MCP Integration

**Status:** done | **Priority:** P1 | **Date:** 2026-02-02

## Why

MCP серверы значительно улучшают `/scout` и `/spark`, но текущая интеграция требует ручной настройки. Пользователи пропускают этот шаг и не получают full value от DLD.

## Context

- MCP работает, но нет guided setup
- Нет health check — проблемы обнаруживаются только при использовании
- Документация не структурирована по уровням (tiers)

---

## Scope

**In scope:**
- `.mcp.json.example` шаблон с комментариями
- Интерактивный `setup-mcp.sh` с health check
- MCP prompt в `create-dld` (с `prompts` библиотекой)
- Tiered documentation (Zero/Recommended/Power)
- Отдельный troubleshooting guide

**Out of scope:**
- Автоматическое обновление MCP серверов
- GUI для настройки
- Кастомные MCP серверы

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- [x] `grep -r "create-dld" .` → 4 files (README, package itself)
- [x] `grep -r "mcp-setup" .` → 1 file (README.md)

### Step 2: DOWN — what depends on?
- [x] `create-dld/index.js` imports: child_process, fs, path (Node built-ins)
- [x] Will add: `prompts` dependency

### Step 3: BY TERM — grep entire project
- [x] `grep -rn "setup-mcp" .` → 0 results (new file)
- [x] `grep -rn "\.mcp\.json" .` → 0 results (new file)

| File | Line | Status | Action |
|------|------|--------|--------|
| README.md | 65-74 | exists | update MCP section |
| docs/20-mcp-setup.md | all | exists | expand with tiers |

### Step 4: CHECKLIST — mandatory folders
- [x] `tests/**` — no tests for create-dld currently
- [x] `docs/**` — 20-mcp-setup.md needs update
- [x] No migrations needed

### Verification
- [x] All found files added to Allowed Files
- [x] No old terms to cleanup

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.mcp.json.example` — new: MCP config template
2. `template/scripts/setup-mcp.sh` — new: interactive setup script
3. `packages/create-dld/index.js` — add MCP prompt
4. `packages/create-dld/package.json` — add prompts dependency
5. `docs/20-mcp-setup.md` — expand with tiered approach
6. `docs/21-mcp-troubleshooting.md` — new: troubleshooting guide
7. `README.md` — update MCP section

**New files allowed:**
- `template/.mcp.json.example`
- `template/scripts/setup-mcp.sh`
- `docs/21-mcp-troubleshooting.md`

**FORBIDDEN:** All other files.

---

## Environment

nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: Layered MCP with Health Monitoring (Selected)

**Source:** [MCP Best Practices 2026](https://mcpcat.io/guides/implementing-connection-health-checks/)

**Summary:** Validate at setup time, degrade gracefully at runtime.

**Pros:**
- User gets immediate feedback during setup
- No "wall of errors" on first /scout
- Works without MCP (progressive enhancement)

**Cons:**
- More complex setup script

### Approach 2: Static Configuration Only

**Summary:** Just provide `.mcp.json.example`, no automation.

**Pros:**
- Simple
- No scripting

**Cons:**
- Users copy-paste without understanding
- No validation until runtime failure

### Selected: Approach 1

**Rationale:** Better first-run experience. DLD is about reducing friction, not adding it.

---

## Design

### User Flow

1. `npx create-dld my-project`
2. Prompt: "Configure MCP servers?"
   - Recommended (Context7 + Exa)
   - Minimal (Context7 only)
   - Power (+ Memory + Sequential Thinking)
   - Skip
3. If selected → run `claude mcp add` commands
4. Test each server → show status
5. If fail → warning + continue option
6. Done → show next steps

### MCP Tiers

| Tier | Servers | Use Case | API Keys |
|------|---------|----------|----------|
| 1 (Zero) | None | Quick try | None |
| 2 (Recommended) | Context7 + Exa | Active dev | None (hosted) |
| 3 (Power) | + Memory + Sequential | Teams | Memory requires key |

### Health Check Logic

```bash
# Pseudo-code for setup-mcp.sh
for server in selected_servers:
    add_server(server)
    if test_server(server):
        print "✓ $server OK"
    else:
        print "✗ $server failed"
        warn_and_continue()
```

---

## Detailed Implementation Plan

### Research Sources (Verified)
- [MCP Connection Health Checks](https://mcpcat.io/guides/implementing-connection-health-checks/) - health monitoring patterns, keep-alive, timeout handling
- [Build Health Check Endpoints](https://mcpcat.io/guides/building-health-check-endpoint-mcp-server/) - endpoint patterns, dependency validation
- [MCP in Production](https://bytebridge.medium.com/what-it-takes-to-run-mcp-model-context-protocol-in-production-3bbf19413f69) - production considerations
- [Prompts library](https://github.com/terkelg/prompts) - interactive CLI prompts for Node.js

### Drift Check Results
- `packages/create-dld/index.js` exists (82 lines) - no dependencies currently
- `packages/create-dld/package.json` exists (20 lines) - no runtime dependencies
- `docs/20-mcp-setup.md` exists (248 lines) - already has Context7 + Exa documented
- `template/scripts/` directory does NOT exist - needs creation
- `template/.mcp.json.example` does NOT exist - needs creation
- No existing MCP health check logic anywhere

---

### Task 1: Create `.mcp.json.example`

**Files:**
- Create: `template/.mcp.json.example`

**Context:**
Template file showing all three MCP tiers as commented JSON. Users can copy and uncomment their desired tier. JSON5 comments are supported in many editors.

**Implementation:**

```jsonc
// template/.mcp.json.example
// MCP Configuration Template for DLD
// Copy to .claude/settings.json and uncomment desired tier
// Docs: https://github.com/Ellevated/dld/blob/main/docs/20-mcp-setup.md

{
  "mcpServers": {
    // ===========================================
    // TIER 1: Zero (No MCP - skip this section)
    // ===========================================

    // ===========================================
    // TIER 2: Recommended (Context7 + Exa)
    // No API keys needed - uses hosted services
    // ===========================================
    "context7": {
      "command": "npx",
      "args": ["-y", "@context7/mcp-server"]
    },
    "exa": {
      "type": "http",
      "url": "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"
    }

    // ===========================================
    // TIER 3: Power (add to Tier 2)
    // Requires: Memory MCP API key
    // ===========================================
    // "memory": {
    //   "command": "npx",
    //   "args": ["-y", "@anthropic/memory-mcp"],
    //   "env": {
    //     "MEMORY_API_KEY": "your-key-here"
    //   }
    // },
    // "sequential-thinking": {
    //   "command": "npx",
    //   "args": ["-y", "@anthropic/sequential-thinking-mcp"]
    // }
  }
}
```

**Acceptance Criteria:**
- [ ] File exists at `template/.mcp.json.example`
- [ ] Contains all three tiers with clear section headers
- [ ] Tier 2 is uncommented by default (recommended)
- [ ] Tier 3 is commented out
- [ ] Links to documentation in header

---

### Task 2: Expand `docs/20-mcp-setup.md`

**Files:**
- Modify: `docs/20-mcp-setup.md` (lines 1-30)

**Context:**
Restructure the document to lead with tiered approach. Add clear tier comparison table at the top.

**Implementation:**

Add this section after line 1 (after the title):

```markdown
## Choose Your Tier

| Tier | Servers | Setup Time | API Keys | Best For |
|------|---------|------------|----------|----------|
| **Zero** | None | 0 min | None | Quick evaluation |
| **Recommended** | Context7 + Exa | 2 min | None | Active development |
| **Power** | + Memory + Sequential | 5 min | Memory key | Teams, complex projects |

**Recommendation:** Start with **Recommended** tier. All features work, no API keys needed.

---

## Tier 1: Zero (No MCP)

DLD works without MCP servers. Skills like `/scout` and `/spark` will use built-in WebSearch and WebFetch tools instead.

**Limitations:**
- No real-time library documentation (Context7)
- Basic web search instead of Exa deep research
- Research quality is lower but functional

**When to use:** Quick evaluation, offline environments, restricted networks.

---

## Tier 2: Recommended (Context7 + Exa)

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

## Tier 3: Power (Teams & Complex Projects)

**Setup time:** 5 minutes | **API keys:** Memory MCP key required

Start with Tier 2, then add:

```bash
# Memory MCP (requires API key from Anthropic)
claude mcp add memory -- npx -y @anthropic/memory-mcp

# Sequential Thinking (no key needed)
claude mcp add sequential-thinking -- npx -y @anthropic/sequential-thinking-mcp
```

**What you get (in addition to Tier 2):**
- **Memory** - Cross-session memory, team knowledge sharing
- **Sequential Thinking** - Enhanced reasoning for complex problems

**When to use:** Large codebases, team environments, multi-day projects.

---
```

**Acceptance Criteria:**
- [ ] Tier comparison table at top of document
- [ ] Each tier has: description, setup commands, verify steps
- [ ] One-liner setup for Recommended tier
- [ ] Link to troubleshooting guide

---

### Task 3: Create `docs/21-mcp-troubleshooting.md`

**Files:**
- Create: `docs/21-mcp-troubleshooting.md`

**Context:**
Dedicated troubleshooting guide for MCP issues. Covers common errors, debug steps, and fallback behavior.

**Implementation:**

```markdown
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
```

**Acceptance Criteria:**
- [ ] File exists at `docs/21-mcp-troubleshooting.md`
- [ ] Covers all common errors from spec
- [ ] Has quick health check command
- [ ] Explains fallback behavior
- [ ] Links to issues for help

---

### Task 4: Create `setup-mcp.sh`

**Files:**
- Create: `template/scripts/setup-mcp.sh`

**Context:**
Interactive bash script for MCP setup with health checks. Supports three modes: interactive tier selection, `--check` for health check only, and `--tier N` for non-interactive setup.

**Implementation:**

```bash
#!/usr/bin/env bash
# setup-mcp.sh - Interactive MCP server setup for DLD
# Usage:
#   ./scripts/setup-mcp.sh          # Interactive tier selection
#   ./scripts/setup-mcp.sh --check  # Health check only
#   ./scripts/setup-mcp.sh --tier 2 # Non-interactive setup

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# MCP Server definitions
CONTEXT7_CMD="claude mcp add context7 -- npx -y @context7/mcp-server"
EXA_CMD='claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"'

# Health check function
check_server() {
    local name=$1
    local test_cmd=$2

    printf "  Checking ${BLUE}%s${NC}... " "$name"

    if eval "$test_cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        return 1
    fi
}

# Health check all servers
health_check() {
    echo -e "\n${BLUE}MCP Health Check${NC}"
    echo "================="

    local all_ok=true

    # Check prerequisites
    echo -e "\n${YELLOW}Prerequisites:${NC}"
    check_server "Node.js" "node --version" || all_ok=false
    check_server "npx" "npx --version" || all_ok=false
    check_server "claude CLI" "command -v claude" || all_ok=false

    # Check MCP servers
    echo -e "\n${YELLOW}MCP Servers:${NC}"
    check_server "Context7" "npx -y @context7/mcp-server --help 2>&1 | head -1" || all_ok=false
    check_server "Exa (connectivity)" "curl -s --max-time 5 'https://mcp.exa.ai/mcp' | head -c 1" || all_ok=false

    echo ""
    if $all_ok; then
        echo -e "${GREEN}All checks passed!${NC}"
        return 0
    else
        echo -e "${RED}Some checks failed. See docs/21-mcp-troubleshooting.md${NC}"
        return 1
    fi
}

# Add server with health check
add_server() {
    local name=$1
    local cmd=$2
    local test_cmd=$3

    echo -e "\nAdding ${BLUE}$name${NC}..."

    if eval "$cmd" 2>&1; then
        if check_server "$name" "$test_cmd"; then
            return 0
        fi
    fi

    echo -e "${YELLOW}Warning: $name may not be working correctly${NC}"
    return 1
}

# Setup tier
setup_tier() {
    local tier=$1

    case $tier in
        1)
            echo -e "\n${GREEN}Tier 1: Zero${NC}"
            echo "No MCP servers to configure. DLD will use built-in tools."
            ;;
        2)
            echo -e "\n${GREEN}Tier 2: Recommended (Context7 + Exa)${NC}"
            add_server "Context7" "$CONTEXT7_CMD" "npx -y @context7/mcp-server --help 2>&1 | head -1"
            add_server "Exa" "$EXA_CMD" "curl -s --max-time 5 'https://mcp.exa.ai/mcp' | head -c 1"
            ;;
        3)
            echo -e "\n${GREEN}Tier 3: Power${NC}"
            # First add Tier 2
            setup_tier 2

            echo -e "\n${YELLOW}Note: Memory MCP requires an API key.${NC}"
            echo "Get your key from Anthropic and add manually:"
            echo '  claude mcp add memory -- npx -y @anthropic/memory-mcp'
            echo ""
            echo "Sequential Thinking (no key needed):"
            echo '  claude mcp add sequential-thinking -- npx -y @anthropic/sequential-thinking-mcp'
            ;;
        *)
            echo -e "${RED}Invalid tier: $tier${NC}"
            exit 1
            ;;
    esac
}

# Interactive menu
interactive_menu() {
    echo -e "${BLUE}"
    echo "  ____  _     ____    __  __  ____ ____   ____       _"
    echo " |  _ \| |   |  _ \  |  \/  |/ ___|  _ \ / ___|  ___| |_ _   _ _ __"
    echo " | | | | |   | | | | | |\/| | |   | |_) | \___ \/ _ \ __| | | | '_ \\"
    echo " | |_| | |___| |_| | | |  | | |___|  __/  ___) |  __/ |_| |_| | |_) |"
    echo " |____/|_____|____/  |_|  |_|\____|_|    |____/ \___|\__|\__,_| .__/"
    echo "                                                              |_|"
    echo -e "${NC}"

    echo "Select MCP tier:"
    echo ""
    echo "  1) Zero      - No MCP (quick evaluation)"
    echo "  2) Recommended - Context7 + Exa (no API keys)"
    echo "  3) Power     - + Memory + Sequential (requires keys)"
    echo "  4) Skip      - Exit without changes"
    echo ""

    read -rp "Your choice [2]: " choice
    choice=${choice:-2}

    case $choice in
        1|2|3)
            setup_tier "$choice"
            ;;
        4)
            echo "Skipped. Run again when ready."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            exit 1
            ;;
    esac

    echo ""
    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Restart Claude Code to load MCP servers"
    echo "  2. Run: ./scripts/setup-mcp.sh --check"
    echo "  3. Try: /scout 'research topic'"
}

# Main
main() {
    case "${1:-}" in
        --check)
            health_check
            ;;
        --tier)
            if [[ -z "${2:-}" ]]; then
                echo "Usage: $0 --tier <1|2|3>"
                exit 1
            fi
            setup_tier "$2"
            ;;
        --help|-h)
            echo "Usage: $0 [--check | --tier <1|2|3>]"
            echo ""
            echo "Options:"
            echo "  --check       Run health check only"
            echo "  --tier N      Non-interactive setup (1=Zero, 2=Recommended, 3=Power)"
            echo "  (no args)     Interactive menu"
            exit 0
            ;;
        *)
            interactive_menu
            ;;
    esac
}

main "$@"
```

**Acceptance Criteria:**
- [ ] File exists at `template/scripts/setup-mcp.sh`
- [ ] File is executable (`chmod +x`)
- [ ] Interactive menu works with tier selection
- [ ] `--check` flag runs health check only
- [ ] `--tier N` flag for non-interactive setup
- [ ] Colored output for status
- [ ] Graceful handling of failures

---

### Task 5: Update `create-dld` with MCP prompt

**Files:**
- Modify: `packages/create-dld/index.js`
- Modify: `packages/create-dld/package.json`

**Context:**
Add interactive MCP tier selection to the project creation flow. Uses `prompts` library for clean CLI UX.

**Step 1: Update package.json**

Add to `packages/create-dld/package.json`:

```json
{
  "name": "create-dld",
  "version": "1.0.1",
  "description": "Create a new DLD project with Claude Code",
  "author": "DLD Contributors",
  "bin": {
    "create-dld": "./index.js"
  },
  "type": "module",
  "keywords": ["dld", "claude", "ai", "scaffolding"],
  "repository": {
    "type": "git",
    "url": "https://github.com/Ellevated/dld"
  },
  "license": "MIT",
  "engines": {
    "node": ">=18.0.0"
  },
  "dependencies": {
    "prompts": "^2.4.2"
  },
  "files": ["index.js", "README.md"]
}
```

**Step 2: Update index.js**

Replace `packages/create-dld/index.js` with:

```javascript
#!/usr/bin/env node

import { execSync, exec } from 'child_process';
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import prompts from 'prompts';

const REPO_URL = 'https://github.com/Ellevated/dld.git';
const TEMPLATE_DIR = 'template';

// MCP server commands
const MCP_SERVERS = {
  context7: {
    name: 'Context7',
    cmd: 'claude mcp add context7 -- npx -y @context7/mcp-server',
    test: 'npx -y @context7/mcp-server --help'
  },
  exa: {
    name: 'Exa',
    cmd: 'claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"',
    test: 'curl -s --max-time 5 "https://mcp.exa.ai/mcp" | head -c 1'
  }
};

// Check Node version
const [major] = process.versions.node.split('.');
if (parseInt(major) < 18) {
  console.error('Error: Node.js 18+ required (current: ' + process.versions.node + ')');
  process.exit(1);
}

// Check git availability
try {
  execSync('git --version', { stdio: 'pipe' });
} catch {
  console.error('Error: git is not installed. Please install git first.');
  process.exit(1);
}

async function addMcpServer(server) {
  return new Promise((resolve) => {
    console.log(`  Adding ${server.name}...`);
    exec(server.cmd, { timeout: 30000 }, (error) => {
      if (error) {
        console.log(`  Warning: ${server.name} setup may have issues`);
        resolve(false);
      } else {
        console.log(`  ${server.name} added`);
        resolve(true);
      }
    });
  });
}

async function setupMcp(tier) {
  if (tier === 0) {
    console.log('\nSkipping MCP setup. You can run ./scripts/setup-mcp.sh later.');
    return;
  }

  console.log('\nConfiguring MCP servers...');

  if (tier >= 1) {
    await addMcpServer(MCP_SERVERS.context7);
    await addMcpServer(MCP_SERVERS.exa);
  }

  if (tier >= 2) {
    console.log('\nTier 3 servers require API keys.');
    console.log('Run ./scripts/setup-mcp.sh --tier 3 to complete setup.');
  }

  console.log('\nMCP setup complete. Restart Claude Code to activate.');
}

async function main() {
  const projectName = process.argv[2];

  if (!projectName) {
    console.log('Usage: npx create-dld <project-name>');
    process.exit(1);
  }

  if (existsSync(projectName)) {
    console.error(`Error: Directory '${projectName}' already exists`);
    process.exit(1);
  }

  console.log(`Creating DLD project: ${projectName}`);

  // Clone template (sparse checkout)
  const tempDir = `.dld-temp-${Date.now()}`;

  try {
    execSync(`git clone --depth 1 --filter=blob:none --sparse ${REPO_URL} ${tempDir}`, { stdio: 'pipe' });
    execSync(`git -C ${tempDir} sparse-checkout set ${TEMPLATE_DIR}`, { stdio: 'pipe' });

    // Move template to project
    mkdirSync(projectName);
    execSync(`cp -r ${tempDir}/${TEMPLATE_DIR}/. ${projectName}/`, { stdio: 'pipe' });

    // Initialize git
    execSync(`git -C ${projectName} init`, { stdio: 'pipe' });

    // Cleanup
    execSync(`rm -rf ${tempDir}`, { stdio: 'pipe' });

    console.log(`\nProject created: ${projectName}`);

    // MCP setup prompt
    const response = await prompts({
      type: 'select',
      name: 'mcpTier',
      message: 'Configure MCP servers?',
      choices: [
        { title: 'Recommended (Context7 + Exa)', description: 'No API keys needed', value: 1 },
        { title: 'Skip for now', description: 'Run ./scripts/setup-mcp.sh later', value: 0 },
        { title: 'Power tier', description: 'Requires API keys (advanced)', value: 2 }
      ],
      initial: 0
    });

    // Handle Ctrl+C
    if (response.mcpTier === undefined) {
      console.log('\nSetup cancelled. Project created without MCP.');
    } else {
      await setupMcp(response.mcpTier);
    }

    console.log(`
Next steps:
  cd ${projectName}
  claude
  /bootstrap
    `);
  } catch (error) {
    const msg = error.message || '';
    if (msg.includes('ENOTFOUND') || msg.includes('getaddrinfo')) {
      console.error('Error: Network unavailable. Check your internet connection.');
    } else if (msg.includes('Repository not found') || msg.includes('not found')) {
      console.error('Error: Could not access DLD repository. Please try again later.');
    } else {
      console.error('Error:', msg);
    }
    try {
      execSync(`rm -rf ${tempDir} ${projectName} 2>/dev/null`, { stdio: 'pipe' });
    } catch {}
    process.exit(1);
  }
}

main();
```

**Acceptance Criteria:**
- [ ] `prompts` added to dependencies
- [ ] Version bumped to 1.0.1
- [ ] Interactive MCP tier selection after project creation
- [ ] Graceful handling of Ctrl+C
- [ ] "Skip" option works
- [ ] MCP commands execute without blocking

---

### Task 6: Update README MCP section

**Files:**
- Modify: `README.md` (lines 65-75)

**Context:**
Update the MCP section to mention tiers and link to documentation.

**Implementation:**

Replace lines 65-75 in `README.md`:

```markdown
### Optional: Configure MCP Servers

**Recommended** (no API keys needed):
```bash
claude mcp add context7 -- npx -y @context7/mcp-server
claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"
```

Or run the interactive setup:
```bash
./scripts/setup-mcp.sh
```

MCP enhances `/scout` and `/spark` with real-time docs and web research. See [MCP Setup Guide](docs/20-mcp-setup.md) for all tiers.
```

**Acceptance Criteria:**
- [ ] Mentions "Recommended" tier explicitly
- [ ] Shows quick setup commands
- [ ] Links to `./scripts/setup-mcp.sh`
- [ ] Links to full documentation

---

### Execution Order

```
Task 1 (.mcp.json.example)
    |
    v
Task 2 (docs/20-mcp-setup.md) --> Task 3 (troubleshooting.md)
    |
    v
Task 4 (setup-mcp.sh) -- depends on troubleshooting guide reference
    |
    v
Task 5 (create-dld) -- can run in parallel with Task 4
    |
    v
Task 6 (README) -- depends on setup-mcp.sh existing
```

**Parallel opportunities:**
- Tasks 2 and 3 can be done in parallel
- Task 5 can start after Task 1

### Dependencies

- Task 2 references troubleshooting guide (Task 3) - soft dependency
- Task 4 references troubleshooting guide (Task 3) - soft dependency
- Task 6 references setup-mcp.sh (Task 4) - hard dependency

---

## Flow Coverage Matrix

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User runs `npx create-dld` | Task 5 | ✓ |
| 2 | Sees MCP tier options | Task 5 | ✓ |
| 3 | Selects tier | Task 5 | ✓ |
| 4 | Servers are added | Task 5 | ✓ |
| 5 | Health check runs | Task 4, 5 | ✓ |
| 6 | User sees result | Task 5 | ✓ |
| 7 | User wants to reconfigure | Task 4 | ✓ |
| 8 | User needs help | Task 2, 3 | ✓ |

---

## Definition of Done

### Functional
- [ ] `npx create-dld` shows MCP tier prompt
- [ ] All three tiers work correctly
- [ ] Health check validates servers
- [ ] Graceful degradation on failure
- [ ] `./scripts/setup-mcp.sh` works standalone
- [ ] `./scripts/setup-mcp.sh --check` shows status

### Documentation
- [ ] `docs/20-mcp-setup.md` covers all tiers
- [ ] `docs/21-mcp-troubleshooting.md` exists
- [ ] README updated

### Technical
- [ ] `prompts` added to create-dld dependencies
- [ ] Scripts are executable
- [ ] No hardcoded paths

---

## Autopilot Log

<!-- Autopilot will fill this section -->
