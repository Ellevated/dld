# {Project Name}

{One-line description — fill after /bootstrap}

**Stack:** {Your stack here — e.g., Python 3.12 + FastAPI + PostgreSQL}
**Not using:** {Optional: list frameworks you're avoiding}

**Commands:**
- `./test fast` — lint + unit tests
- `./test` — full tests

> **Note:** Create `./test` script for your project's stack (e.g., `pytest`, `npm test`, `cargo test`). See examples in `/bootstrap` output.

---

## DLD Tier

**Current:** ⭐ Standard

**What's included:**
- MCP: Context7 + Exa
- Skills: spark, scout, audit, review
- Hooks: Safety validation

**Upgrade:** Run `./scripts/setup-mcp.sh --power` for Power tier (council, autopilot, planner)

---

## Prerequisites

- Node.js 18+ (required for hooks)
- Claude Code CLI

---

## Quick Start

1. **Configure MCP servers** (recommended):
   ```bash
   claude mcp add context7 -- npx -y @context7/mcp-server
   claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"
   ```

   > **Alternative:** Copy `.mcp.json.example` to `~/.claude/.mcp.json` for pre-configured MCP setup.

2. Run `/bootstrap` to unpack your idea
3. Fill this file based on `ai/idea/*.md`
4. Create domains structure
5. Run `/spark` for first feature

> MCP enables `/scout` research with Exa (web search, deep research) and Context7 (library docs).
>
> **Tiers:**
> - **Standard** (default): Context7 + Exa — research and docs lookup
> - **Power**: Adds Sequential Thinking — unlocks `/council` and `/autopilot`
> For Power tier: `./scripts/setup-mcp.sh --tier 3`

---

## Architecture

```
Entry Points:  {your entry points — e.g., API | CLI | Bot}
                    ↓              ↓
Domains:       {domain1} | {domain2} | {domain3}
                    ↓              ↓
Infra:              db | cache | external APIs
```

**Dependencies:** `shared → infra → domains → api`

See `ai/ARCHITECTURE.md` after bootstrap.

---

## Contexts (conditional loading)

| Task | Context | Triggers |
|------|---------|----------|
| {domain1} | `.claude/contexts/{domain1}.md` | `src/domains/{domain1}/**` |
| DB, LLM, infra | `.claude/contexts/shared.md` | `src/infra/**`, `db/**` |

> **Note:** `.claude/contexts/` and `.claude/rules/` domain files are created during `/bootstrap` when you define your project's domains. They don't exist in the template out of the box.

---

## Project Context System (v3.7)

Three-tier knowledge system for preventing breakage during refactoring.

### Structure

```
.claude/rules/
├── dependencies.md     # Dependency graph between components
├── architecture.md     # Patterns, ADR, anti-patterns
└── domains/            # Per-domain context
    └── {domain}.md

ai/glossary/
├── {domain1}.md        # Domain terms and rules
├── {domain2}.md
└── ...
```

### Protocols (agents use automatically)

| Protocol | When | Who |
|----------|------|-----|
| `context-loader.md` | BEFORE work | spark, planner, coder, review, debugger, council |
| `context-updater.md` | AFTER work | spark, coder |

### Impact Tree Algorithm (5 steps)

On any change:

1. **UP** — who uses the changed code? (`grep -r "from.*{module}" .`)
2. **DOWN** — what does it depend on? (imports in file)
3. **BY TERM** — grep old name across entire project
4. **CHECKLIST** — mandatory folders (tests/, migrations/, edge functions/)
5. **DUAL SYSTEM** — if changing data source, who reads from old/new?

**Rule:** After changes `grep "{old_term}" .` = 0 results!

### Module Headers

At the start of significant files:
```python
"""
Module: {module_name}
Role: {brief description}
Uses: {dependencies}
Used by: {dependents}
Glossary: ai/glossary/{domain}.md
"""
```

---

## Skills (v4.0)

**Rule:** If skill applies — MUST use it.

| Skill | When |
|-------|------|
| **bootstrap** | Day 0 — extract idea from founder's head (interviewer, not decider) |
| **board** | Business architecture — revenue, channels, org model (after bootstrap) |
| **architect** | System architecture — domains, data, APIs, cross-cutting (after board) |
| **spark** | Feature spec — multi-agent with 4 scouts + tests mandatory (within blueprint) |
| **autopilot** | Execute tasks (plan + coder/tester per task + reflect upstream) |
| **council** | Complex/controversial decisions (5 experts + cross-critique) |
| **audit** | Code analysis, consistency check (READ-ONLY) |
| **reflect** | Synthesize diary + upstream signals into rules |
| **scout** | Isolated research via Exa + Context7 |
| **release** | Update CHANGELOG, README, docs after changes (fully automatic) |
| **skill-creator** | Create agents/skills or optimize CLAUDE.md, rules, prompts |
| **retrofit** | Brownfield lifecycle — reassess existing projects (audit -> architect -> board -> stabilize) |
| **brandbook** | Brand identity system — anti-convergence, design tokens, coder handoff |
| **diagram** | Generate professional Excalidraw diagrams from description or code analysis |
| **eval** | Agent prompt eval suite — golden datasets + LLM-as-Judge scoring |
| **upgrade** | Upgrade DLD framework from latest GitHub template |
| **qa** | Manual QA tester — tests product behavior like a real user, not code |

### Skill Auto-Selection

Claude auto-selects skills based on user intent. Each skill has semantic triggers in its description.

**How it works:**
- User says "add login feature" → Claude activates `/spark`
- User says "implement TECH-055" → Claude activates `/autopilot`
- User says "how does X work?" → Claude activates `/scout`

**Override:** Always use explicit `/command` to force specific skill.

**Trigger examples:**

| User says | Skill activated |
|-----------|-----------------|
| "new project", "day 0" | bootstrap |
| "business strategy", "revenue model" | board |
| "system design", "architecture" | architect |
| "add feature", "create spec", "bug" | spark |
| "implement", "execute", "build this" | autopilot |
| "should we", "which approach", "debate" | council |
| "research", "find docs", "how does X work" | scout |
| "find all", "analyze code", "check for" | audit |
| "reflect", "what did we learn" | reflect |
| "diagram", "draw", "visualize architecture" | diagram |
| "retrofit", "brownfield", "reassess project" | retrofit |
| "upgrade DLD", "update framework", "обнови DLD" | upgrade |
| "протестируй", "проверь как работает", "QA", "потыкай" | qa |

**Flows:**
```
New project:  /bootstrap → /board → /architect → /spark → /autopilot
Feature:      /spark → /autopilot (within blueprint constraints)
Bug:          diagnose (5 Whys) → /spark → /autopilot
Hotfix:       <5 LOC → fix directly with user approval
Escalation:   Autopilot → Spark → Architect → Board → Founder
Brownfield:   /retrofit → /audit deep → /architect → /board → stabilize → normal
```

**New in v3.7:**
- Spark auto-hands off to autopilot (no manual "plan" step)
- Autopilot always uses worktree (isolation)
- Fresh subagent per task (context stays clean)
- Agent/Skill separation (agents/*.md = prompts, skills/*.md = UX)
- Diary captures learnings → reflect synthesizes rules
- Council decomposition (5 separate expert agents)
- Diary-recorder for automatic problem capture

---

## Key Rules

### Imports Direction
`shared → infra → domains → api` (never reverse)

### File Limits
- Max 400 LOC per file (600 for tests)
- Max 5 exports in `__init__.py`

### Test Safety
- NEVER modify `tests/contracts/` or `tests/regression/`
- Never delete/skip tests without user approval
- Integration tests (`tests/integration/`) use real dependencies — NO mocks (hook enforced)

### Atomic Commits
One task = one commit. Tests must pass.

### Git Autonomous Mode
When user says "commit/push" — execute without asking:
1. `git status && git diff` (review changes first!)
2. `git add <files>` (add specific files, never `.env` or credentials)
3. `git commit -m "..."` (Conventional Commits)
4. If "push" — `git push`

**Autopilot:** auto-push to `develop` allowed. Never push to `main`.

### Migrations — Git-First ONLY
**NEVER apply migrations directly! CI is the only source of apply.**

### Shell Scripts (scripts/vps/)
- Header: `#!/usr/bin/env bash` + `set -euo pipefail`
- SQL: ALWAYS through `python3 db.py <command>`, never shell interpolation
- Variables: quote all `"$var"`, no bare `$var`
- CLI flags: verify flag exists in tool version before using

### Tool Preferences (API Error Prevention)
Some tools may trigger API content filtering errors. Use fallbacks:
- **File search:** Use `Glob` instead of `Search` for pattern matching
- **Content search:** Use `Grep` tool, not bash `grep`
- **File listing:** Use `Glob` or `ls` via Bash, avoid recursive Search

If a tool returns "content filtering policy" error — retry with alternative tool.

---

## AI-First Economic Model

Implementation effort is near-zero for AI agents. **Never deprioritize a task based on implementation effort.**

### Cost Reference

| Scope | Compute cost | Wall-clock |
|-------|-------------|------------|
| Simple change (1-3 files) | ~$1 | 15 min |
| Medium change (5-10 files) | ~$5 | 1-2 hours |
| Large change (20+ files) | ~$15 | 3-4 hours |
| Full domain extraction | ~$50 | 1 day |

**Capacity:** 5 parallel autopilot slots. No "team is busy" — slots are always available.

### Priority = Pure Impact (Cost of Delay)

| Priority | Definition | Cost of Delay |
|----------|-----------|---------------|
| **P0** | Blocks revenue, users, or security RIGHT NOW | Immediate |
| **P1** | High impact on product quality (features, refactoring, testing, tech debt) | This week |
| **P2** | Nice-to-have, doesn't affect metrics this week | Low |

**Key rules:**
- Refactoring and testing are **P1 by default** — they cost $5-10 and maintain the harness
- Maximum 5 P0 tasks in backlog simultaneously (priority inflation gate)
- "Too expensive" means risk, not compute cost

### Risk Classification (R0/R1/R2)

Risk replaces effort as the second axis of decision-making:

| Risk | Definition | Examples |
|------|-----------|----------|
| **R0** | Irreversible | Data loss, schema migration, security exposure, public API break |
| **R1** | High blast radius | 3+ files, cross-domain, external dependency, state machine change |
| **R2** | Contained | 1-2 files, single domain, internal, trivially rollbackable |

### Impact x Risk Routing

| Impact \ Risk | R0 (Irreversible) | R1 (Blast radius) | R2 (Contained) |
|---|---|---|---|
| **P0** | COUNCIL | HUMAN | AUTO |
| **P1** | COUNCIL | AUTO | AUTO |
| **P2** | HUMAN | AUTO | AUTO |

---

## Task Statuses

| Status | Owner | Description |
|--------|-------|-------------|
| `draft` | Manual | Legacy — manual override only, Spark never outputs this |
| `queued` | Spark | Ready for autopilot (Spark always creates specs in this status) |
| `in_progress` | Autopilot | Currently executing |
| `blocked` | Autopilot | Needs human (see ACTION REQUIRED in spec) |
| `resumed` | Human | Problem resolved, continue |
| `done` | Autopilot | Completed |

**Default Flow:** `queued → in_progress → done`
**Manual Override Flow:** `draft → queued → in_progress → done`
**Recovery:** `in_progress → blocked → resumed → in_progress`

**Callback Enforcement (DLD-specific):**
После завершения pueue задачи `callback.py` — единственный writer статусов спек.
Implementation guard проверяет коммиты в Allowed Files. См. dld-orchestrator.md§5

---

## DLD Orchestrator Reference

VPS daemon координирующий multi-project AI execution через pueue + SQLite SoT.
Callback enforces spec/backlog status атомарно (ADR-018). Critical path:
pueue completion → callback.py → verify_status_sync → plumbing commit.

Full docs: `~/.claude/projects/-root/memory/dld-orchestrator.md`
Runbook:   `~/.claude/projects/-root/memory/orchestrator-runbook.md`

---

## Backlog Rules

- **Size:** 30-50 active tasks max
- **Prefixes:** BUG, FTR, TECH, ARCH only (4 types)
- **Numbering:** Sequential across all types
- **Archive:** Weekly check, if >50 → archive to 30
- **Bug Hunt:** Creates a READ-ONLY report (`BUG-XXX-bughunt.md`, not in backlog) + standalone grouped specs (each with own sequential ID and own backlog entry).

---

## Project Structure

```
src/
├── shared/     # Result, exceptions, types
├── infra/      # db, llm, external
├── domains/    # {fill after bootstrap}
└── api/        # entry points

.claude/
├── agents/     # Subagent prompts (planner, coder, tester, etc.)
├── contexts/   # Domain contexts (conditional)
├── rules/      # Testing/operations rules (conditional)
└── skills/     # spark, autopilot, council, etc.

ai/
├── idea/       # From /bootstrap (raw founder input)
├── board/      # From /board (director research, strategies)
├── architect/  # From /architect (persona research, architectures)
├── blueprint/  # Business Blueprint + System Blueprint
│   ├── business-blueprint.md
│   └── system-blueprint/
├── reflect/    # Upstream signals between levels
├── diary/      # Session learnings
├── features/   # Task specs from /spark
└── backlog.md
```
