# DLD Installation Guide (LLM-Readable)

This document helps Claude (or other LLMs) understand DLD installation options and make intelligent recommendations based on project context.

---

## LLM Installation Protocol (MANDATORY)

**Claude, when asked to install DLD, you MUST follow this protocol. Never skip steps.**

### Step 1: SCAN current project

```bash
# Check existing Claude setup
ls -la .claude/ 2>/dev/null || echo "No .claude/ folder"
ls -la .claude/skills/ 2>/dev/null || echo "No skills"
ls -la .claude/agents/ 2>/dev/null || echo "No agents"
ls -la .claude/hooks/ 2>/dev/null || echo "No hooks"
ls -la .claude/rules/ 2>/dev/null || echo "No rules"

# Check MCP servers
claude mcp list 2>/dev/null || echo "No MCP configured"

# Check CLAUDE.md
head -50 CLAUDE.md 2>/dev/null || echo "No CLAUDE.md"
```

### Step 2: SHOW DIFF to user

Present a comparison table:

```markdown
## DLD Installation Preview

### Your Current Setup
| Component | Status |
|-----------|--------|
| .claude/ folder | exists / missing |
| Skills | list names or "none" |
| Agents | list names or "none" |
| MCP servers | list names or "none" |
| Hooks | list names or "none" |
| CLAUDE.md | exists / missing |

### What DLD Will Add (Standard Tier)
| Component | Action | Details |
|-----------|--------|---------|
| Skills | +N new | spark, scout, audit, review, ... |
| Agents | +N new | planner, coder, tester, ... |
| MCP | +N new | context7, exa |
| Hooks | +N new | pre-commit validation |
| Rules | +N new | architecture, testing |
| CLAUDE.md | create/update | DLD template |

### Conflicts (files that exist and will be overwritten)
| File | Action |
|------|--------|
| .claude/skills/spark/ | backup → overwrite |
| ... | ... |

If no conflicts: "No conflicts detected."
```

### Step 3: ASK for confirmation

```
Proceed with DLD installation?
- Type 'yes' to install
- Type 'no' to cancel
- Type 'customize' to cherry-pick components
```

### Step 4: INSTALL (only after confirmation)

1. **Backup conflicts** (if any):
   ```bash
   mkdir -p .claude/backup/$(date +%Y%m%d)
   cp -r .claude/skills/spark .claude/backup/$(date +%Y%m%d)/ 2>/dev/null
   ```

2. **Clone DLD template**:
   ```bash
   git clone --depth 1 https://github.com/Ellevated/dld.git /tmp/dld-install
   ```

3. **Copy components by tier** (see Tier Definitions below):
   ```bash
   # Standard tier example:
   cp -r /tmp/dld-install/template/.claude/skills .claude/
   cp -r /tmp/dld-install/template/.claude/agents .claude/
   cp -r /tmp/dld-install/template/.claude/hooks .claude/
   cp -r /tmp/dld-install/template/.claude/rules .claude/
   cp /tmp/dld-install/template/CLAUDE.md ./CLAUDE.md
   mkdir -p ai && cp -r /tmp/dld-install/template/ai/* ai/
   ```

4. **Setup MCP servers**:
   ```bash
   claude mcp add context7 -- npx -y @context7/mcp-server
   claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"
   ```

5. **Cleanup**:
   ```bash
   rm -rf /tmp/dld-install
   ```

6. **Verify**:
   ```bash
   ls -la .claude/skills/
   claude mcp list
   echo "DLD installed successfully!"
   ```

### Step 5: SHOW summary

After installation, show what was done:

```markdown
## Installation Complete

| Component | Status |
|-----------|--------|
| Skills | 8 installed |
| Agents | 6 installed |
| MCP | context7, exa |
| Hooks | 2 installed |
| CLAUDE.md | created |

**Next steps:**
1. Run `/spark` to create your first feature spec
2. Check `ai/backlog.md` for task management
3. Read CLAUDE.md for available commands
```

---

## Project Assessment Checklist

Before recommending a tier, analyze:

1. **Project Size**
   - Small (<50 files): Quick tier likely sufficient
   - Medium (50-500 files): Standard tier recommended
   - Large (>500 files): Power tier beneficial

2. **Tech Stack**
   - Single language: Quick/Standard
   - Polyglot (Python + Node + etc): Standard/Power
   - Complex build systems: Power

3. **Team Size**
   - Solo developer: Quick or Standard
   - Team (2-5): Standard
   - Large team (>5): Power (council, shared memory)

4. **Existing Setup**
   - No `.claude/` folder: Fresh install, any tier
   - Has `.claude/` folder: Check current tier, suggest upgrade if needed

5. **Use Case**
   - Quick prototype/script: Quick
   - Production project: Standard
   - Enterprise/complex: Power

---

## Tier Definitions

### 🏃 Quick Tier (2 minutes)

```yaml
name: Quick
time: 2 minutes
audience: Evaluators, small scripts, quick prototypes
```

**Components:**
- Core CLAUDE.md template
- Basic skills: `/spark`, `/commit`
- No MCP servers
- No hooks

**When to recommend:**
- User says "just want to try"
- Project has <20 files
- No build system detected
- Temporary/experimental project

**Installation:**
```bash
npx create-dld my-project --quick
cd my-project
claude
```

---

### ⭐ Standard Tier (5 minutes) — DEFAULT

```yaml
name: Standard
time: 5 minutes
audience: Active developers, production projects
```

**Components:**
- Full CLAUDE.md template
- All core skills: `/spark`, `/commit`, `/scout`, `/audit`, `/review`
- MCP servers: Context7 + Exa (no API keys)
- Safety hooks (pre-commit validation)
- Basic rules

**When to recommend:**
- Default choice when unsure
- Production codebases
- Projects with tests
- CI/CD configured

**Installation:**
```bash
npx create-dld my-project --standard
# or interactive (default):
npx create-dld my-project
cd my-project
claude
```

---

### ⚡ Power Tier (15 minutes)

```yaml
name: Power
time: 15 minutes
audience: Teams, complex projects, power users
```

**Components:**
- Everything from Standard
- Additional MCP: Memory, Sequential Thinking
- Full skill suite: `/council`, `/autopilot`, `/planner`
- Diary system for learning
- Custom hooks template
- Full agent suite

**When to recommend:**
- Team environment
- Multi-day projects
- Complex architectural decisions needed
- User explicitly wants maximum capability
- Large codebase (>500 files)

**Installation:**
```bash
npx create-dld my-project --power
cd my-project
./scripts/setup-mcp.sh --tier 3
claude
```

---

## Component Matrix

| Component | Quick | Standard | Power |
|-----------|-------|----------|-------|
| CLAUDE.md | ✓ | ✓ | ✓ |
| /spark | ✓ | ✓ | ✓ |
| /commit | ✓ | ✓ | ✓ |
| /scout | - | ✓ | ✓ |
| /audit | - | ✓ | ✓ |
| /review | - | ✓ | ✓ |
| /council | - | - | ✓ |
| /autopilot | - | - | ✓ |
| /planner | - | - | ✓ |
| Context7 MCP | - | ✓ | ✓ |
| Exa MCP | - | ✓ | ✓ |
| Memory MCP | - | - | ✓ |
| Sequential Thinking | - | - | ✓ |
| Safety Hooks | - | ✓ | ✓ |
| Diary System | - | - | ✓ |
| Custom Rules | - | - | ✓ |
| Localization | - | Template | Template |

---

## Cherry-Pick Installation

For advanced users or LLM agents, individual components can be added:

### Add MCP Servers

```bash
# Context7 (library docs)
claude mcp add context7 -- npx -y @context7/mcp-server

# Exa (web research)
claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"

# Memory (requires API key)
claude mcp add memory -- npx -y @anthropic/memory-mcp

# Sequential Thinking
claude mcp add sequential-thinking -- npx -y @anthropic/sequential-thinking-mcp
```

### Add Skills

Skills are in `.claude/skills/`. Copy from DLD template:
```bash
# Clone DLD template skills
git clone --depth 1 https://github.com/Ellevated/dld.git /tmp/dld
cp -r /tmp/dld/template/.claude/skills/council .claude/skills/
cp -r /tmp/dld/template/.claude/skills/autopilot .claude/skills/
rm -rf /tmp/dld
```

### Add Hooks

```bash
# Copy hook templates
cp -r /tmp/dld/template/.claude/hooks .claude/
chmod +x .claude/hooks/*.py
```

### Add Localization (Native Language Triggers)

For non-English users who want to invoke skills in their native language:

```bash
# Copy localization template
cp template/.claude/rules/localization.md .claude/rules/

# Edit with your language triggers
# See docs/22-native-language-triggers.md for examples
```

**When to recommend:**
- User's system language is not English
- User communicates in non-English language
- User explicitly asks about native language support

---

## Upgrade Paths

### Quick → Standard

```bash
# Run MCP setup
./scripts/setup-mcp.sh --tier 2

# Update CLAUDE.md tier indicator
# Change: **Tier:** 🏃 Quick
# To: **Tier:** ⭐ Standard
```

### Standard → Power

```bash
# Add Power MCP servers (requires API key for Memory)
./scripts/setup-mcp.sh --tier 3

# Copy additional skills
# Copy diary system
# Update tier indicator
```

---

## LLM Decision Tree

```
START
  |
  v
Has existing .claude/?
  |-- Yes --> Check tier indicator --> Suggest upgrade if beneficial
  |-- No --> Continue
  |
  v
Project size?
  |-- <50 files --> Quick (unless production)
  |-- 50-500 --> Standard
  |-- >500 --> Power
  |
  v
Team size?
  |-- Solo --> Quick/Standard
  |-- Team --> Standard/Power
  |
  v
User stated preference?
  |-- "quick try" --> Quick
  |-- "production" --> Standard
  |-- "maximum" --> Power
  |-- None --> Standard (safe default)
  |
  v
RECOMMEND TIER
```

---

## Verification Commands

After installation, verify setup:

```bash
# Check MCP servers
./scripts/setup-mcp.sh --check

# Check tier
grep "Tier:" CLAUDE.md

# Test Claude
claude "What tier am I running?"
```
