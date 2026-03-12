# TECH: [TECH-004] Add MCP Setup Instructions

**Status:** done | **Priority:** P2 | **Date:** 2026-01-24

## Problem

MCP servers (Context7, Exa) are mentioned in DLD but there are no setup instructions.
New users cannot configure MCP from current docs.

## Solution

Create documentation explaining what MCP servers DLD uses and how to configure them.

---

## Scope

**In scope:**
- Document what MCP servers DLD recommends
- Provide configuration instructions
- Mark which are optional vs recommended

**Out of scope:**
- MCP server development
- Troubleshooting guides for MCP issues

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `docs/20-mcp-setup.md` | create | Main documentation |
| 2 | `README.md` | modify | Add link to MCP docs |

**New files allowed:**
- `docs/20-mcp-setup.md` — MCP configuration guide

**FORBIDDEN:** All other files.

---

## Implementation Plan

### Task 1: Create MCP Setup Documentation

**Files:**
- Create: `docs/20-mcp-setup.md`

**Steps:**
1. Research current MCP usage in DLD skills (Context7 in scout, Exa in spark)
2. Document each MCP server:
   - Name and purpose
   - Installation command
   - Configuration in `.claude/settings.json` or equivalent
   - Required vs optional status
3. Add troubleshooting tips

**Content structure:**
```markdown
# MCP Servers Setup

## Overview
What MCP is and why DLD uses it.

## Required Servers
- None (all optional)

## Recommended Servers

### Context7
- Purpose: Documentation lookup
- Install: ...
- Config: ...

### Exa
- Purpose: Web research
- Install: ...
- Config: ...

## Configuration
How to add to Claude Code settings.

## Verification
How to test MCP is working.
```

**Acceptance:**
- [ ] All used MCP servers documented
- [ ] Clear install instructions
- [ ] Config examples provided

### Task 2: Add Link to README

**Files:**
- Modify: `README.md`

**Steps:**
1. Add link to MCP docs in documentation section

**Acceptance:**
- [ ] Link added and works

---

## Definition of Done

### Functional
- [ ] New user can setup MCP from docs
- [ ] All MCP servers documented
- [ ] Optional vs required clearly marked

### Technical
- [ ] Valid markdown
- [ ] Links work

---

## Autopilot Log

*(Filled by Autopilot during execution)*
