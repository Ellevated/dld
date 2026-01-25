# {Project Name}

{One-line description — fill after /bootstrap}

**Stack:** {Your stack here — e.g., Python 3.12 + FastAPI + PostgreSQL}
**Not using:** {Optional: list frameworks you're avoiding}

**Commands:**
- `./test fast` — lint + unit tests
- `./test` — full tests

---

## Quick Start

1. **Configure MCP servers** (recommended):
   ```bash
   claude mcp add context7 -- npx -y @context7/mcp-server
   claude mcp add --transport http exa "https://mcp.exa.ai/mcp?tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,deep_search_exa,crawling_exa,company_research_exa,deep_researcher_start,deep_researcher_check"
   ```
2. Run `/bootstrap` to unpack your idea
3. Fill this file based on `ai/idea/*.md`
4. Create domains structure
5. Run `/spark` for first feature

> MCP enables `/scout` research with Exa (web search, deep research) and Context7 (library docs).

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
| Testing | `.claude/rules/testing.md` | `tests/**`, `*_test.py` |

---

## Project Context System (v3.4)

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

## Skills (v3.4)

**Rule:** If skill applies — MUST use it.

| Skill | When |
|-------|------|
| **bootstrap** | Day 0 — unpack idea from your head |
| **spark** | New feature, bug, architecture decision (auto-handoff to autopilot) |
| **autopilot** | Execute tasks (plan subagent + fresh coder/tester per task + worktree) |
| **council** | Complex/controversial decisions (5 experts) |
| **audit** | Code analysis, consistency check (READ-ONLY) |
| **reflect** | Synthesize diary entries into CLAUDE.md rules |
| **scout** | Isolated research via Exa + Context7 |
| **claude-md-writer** | Optimize CLAUDE.md following Anthropic 2025 best practices |

**Flows:**
```
New project: /bootstrap → Day 1 → /spark first feature
Feature:     /spark → /autopilot (plan is subagent inside autopilot)
Bug:         diagnose (5 Whys) → /spark → /autopilot
Hotfix:      <5 LOC → fix directly with user approval
```

**New in v3.4:**
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

### Atomic Commits
One task = one commit. Tests must pass.

### Git Autonomous Mode
When user says "commit/push" — execute without asking:
1. `git status && git diff`
2. `git add -A && git commit -m "..."` (Conventional Commits)
3. If "push" — `git push`

**Autopilot:** auto-push to `develop` allowed. Never push to `main`.

### Migrations — Git-First ONLY
**NEVER apply migrations directly! CI is the only source of apply.**

### Tool Preferences (API Error Prevention)
Some tools may trigger API content filtering errors. Use fallbacks:
- **File search:** Use `Glob` instead of `Search` for pattern matching
- **Content search:** Use `Grep` tool, not bash `grep`
- **File listing:** Use `Glob` or `ls` via Bash, avoid recursive Search

If a tool returns "content filtering policy" error — retry with alternative tool.

---

## Task Statuses

| Status | Owner | Description |
|--------|-------|-------------|
| `draft` | Spark | Spec incomplete |
| `queued` | Spark | Ready for autopilot |
| `in_progress` | Autopilot | Currently executing |
| `blocked` | Autopilot | Needs human (see ACTION REQUIRED in spec) |
| `resumed` | Human | Problem resolved, continue |
| `done` | Autopilot | Completed |

**Flow:** `draft → queued → in_progress → done`
**Recovery:** `in_progress → blocked → resumed → in_progress`

---

## Backlog Rules

- **Size:** 30-50 active tasks max
- **Prefixes:** BUG, FTR, TECH, ARCH only (4 types)
- **Numbering:** Sequential across all types
- **Archive:** Weekly check, if >50 → archive to 30

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
├── idea/       # From /bootstrap
├── diary/      # Session learnings (v3.4)
├── features/   # Task specs
├── ARCHITECTURE.md
└── backlog.md
```
