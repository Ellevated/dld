# DLD

The framework itself — the skills, agents and prompts that other projects consume, plus the
VPS orchestrator that runs them. **This repo is not a project bootstrapped from DLD; it is
DLD.** Instructions written for a downstream project do not apply here.

**Stack:** Python 3.12 (`scripts/vps/` — orchestrator, callback, lifecycle, pueue + SQLite)
· Node 20 (`.claude/scripts/`, `.claude/hooks/`) · Markdown prompt tree
**No `src/`, no `src/domains/`** — this repo's product is the prompt tree, not an application.

**Commands** (there is no `./test` here — see below):
```bash
ruff check . && ruff format --check .              # lint
pytest tests/ -v                                   # unit + integration + regression
pytest scripts/vps/tests/ -v                       # orchestrator
for f in test/scripts/*.test.mjs; do node "$f"; done   # skill harness
node .claude/scripts/check-prompt-integrity.mjs --tree .claude
```

> **`./test` does not exist in this repo, by decision.** It is a per-project artifact
> (`rules/template-sync.md`, "Files Only in Template"). Prompts still name it because
> downstream projects have one. `test-wrapper.mjs` reports its absence as
> `TEST_COMMAND_UNAVAILABLE` + **exit 2** — that is "nothing ran", not a failing suite.
> Until 2026-08-02 it reported `FAIL: 0 failure(s)` instead, and a test asserted that
> was fine.

---

## Two trees

```
.claude/     ← what DLD itself runs
template/    ← what downstream projects receive
```

Editing one without the other is the most common defect class here. `rules/template-sync.md`
is the contract: it names what must stay identical, what deliberately differs, and why.

---

## Research providers

Agents degrade *silently* when a provider is missing — they just search worse. Check it
directly rather than trusting that setup once succeeded:

```bash
python scripts/check-research-stack.py
```

Run it after any MCP/plugin change, and when research quality feels off.

---

## Contexts (conditional loading)

`.claude/contexts/` does not exist in this repo — it is created by `/bootstrap` in a
downstream project, keyed to that project's domains. Nothing here loads from it.

### Rules loading — `paths:` is mandatory

A `.claude/rules/*.md` file **with** a YAML `paths:` header loads only when the session touches
files matching those globs. **Without** the header it loads into **every** session, forever.

```yaml
---
paths:
  - "src/**"
  - "tests/**"
---
```

| Rule | Loads when |
|------|-----------|
| `architecture.md` | `packages/**`, `scripts/**`, `tests/**`, `test/**` |
| `dependencies.md` | `scripts/**`, `packages/**`, `tests/**` |
| `model-capabilities.md` | `.claude/{agents,skills}/**`, `template/.claude/{agents,skills}/**`, `scripts/vps/claude-runner.py`, `run-agent.sh` |
| `template-sync.md` | `.claude/**`, `template/**` |
| `localization.md` | **always** — skill triggers must be reachable in any session |

**Writing a new rule:** give it `paths:`. If it is triggered by *intent* rather than by editing a
file ("разбери выплаты", "сделай страницу"), the answer is still `paths:` — plus a short pointer in
CLAUDE.md that tells the session to open the file. A permanently loaded rule buys discoverability
at the price of every unrelated session; measured 2026-07-26 in AwardyBot, four unmarked files cost
**37k tokens per session** for 25 days.

A file that genuinely must always load declares `always_on: true` instead, so the intent lives in
the file rather than in someone's memory. `localization.md` is the only one.

**Check it, don't assume it** — this cost nine projects ~87k tokens/session and was found by
accident, not by looking:

```bash
python scripts/check-rules-loading.py .
```

Exits non-zero on any rule that is neither scoped nor declared. Run it after adding a rule, and
in any repo bootstrapped from this template before trusting its context budget.

---

## Project Context System

Knowledge that prevents breakage during refactoring. In **this** repo it is two files:

| File | Holds |
|---|---|
| `.claude/rules/dependencies.md` | Dependency map for `scripts/vps/*`, `.claude/scripts/*`, and the prompts that call them |
| `.claude/rules/architecture.md` | Patterns, ADR table, anti-patterns |

`ai/glossary/` and `.claude/rules/domains/{domain}.md` are downstream artifacts — created by
`/bootstrap` per project. Prompts reference them with an "if exists" guard; here they do not.

### Impact Tree Algorithm (5 steps)

On any change:

1. **UP** — who uses the changed code? (`grep -r "from.*{module}" .`)
2. **DOWN** — what does it depend on? (imports in file)
3. **BY TERM** — grep old name across entire project
4. **CHECKLIST** — mandatory folders (tests/, migrations/, edge functions/)
5. **DUAL SYSTEM** — if changing data source, who reads from old/new?

**Rule:** After changes `grep "{old_term}" .` = 0 results!

**In this repo, step 4 always includes `template/`.** A rename finished in one tree and not
the other is the defect this framework produces most often.

---

## Skills (v4.0)

**Rule:** If skill applies — MUST use it.

The roster (name + when to use) is already in the session's skill list, and Russian triggers live in
`.claude/rules/localization.md` — neither is repeated here. What is NOT derivable from a description
is the **order** skills run in, so that is all this section keeps.

Auto-selection happens on intent ("add login feature" → `/spark`); an explicit `/command` always
overrides it.

**Flows:**
```
New project:  /bootstrap → /board → /architect → /spark → /autopilot
Feature:      /spark → /autopilot (within blueprint constraints)
Bug:          diagnose (5 Whys) → /spark → /autopilot
Hotfix:       <5 LOC → fix directly with user approval
Escalation:   Autopilot → Spark → Architect → Board → Founder
Brownfield:   /retrofit → /audit deep → /architect → /board → stabilize → normal
```

**Interactive `/spark` workflow:** Run `/spark` interactive sessions from ONE machine at a time (laptop preferred). VPS spark runs only via orchestrator dispatch (headless). The spec-first ID CAS (ARCH-196) handles concurrent claims structurally, but this convention prevents push contention races.

---

## Key Rules

### Imports Direction
`shared → infra → domains → api` (never reverse). Enforced by
`scripts/check_domain_imports.py`, which **exits 0 here** — this repo has no `src/`, so the
rule is one DLD ships downstream rather than one it obeys.

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

### Tool Preferences
Prefer `Glob` for path patterns and `Grep` for content over shell `find`/`grep` — they
return structured results and integrate with the permission UI. (This section used to
name a `Search` tool to avoid; no such tool exists.)

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

> **Scope:** R0/R1/R2 are inputs for **Spark Phase 4 only**. Coder, tester, and autopilot agents do NOT route on this classification.

| Risk | Definition | Examples |
|------|-----------|----------|
| **R0** | Irreversible | Data loss, schema migration, security exposure, public API break |
| **R1** | High blast radius | 3+ files, cross-domain, external dependency, state machine change |
| **R2** | Contained | 1-2 files, single domain, internal, trivially rollbackable |

For Impact × Risk routing matrix, see `.claude/skills/spark/feature-mode.md` Phase 4 DECIDE — matrix applies ONLY during spec design, not during autopilot execution.

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
Статус живёт в `ai/lifecycle/*.yaml` (git HEAD = SoT), пишется атомарным CAS-plumbing.
Implementation guard проверяет коммиты в Allowed Files. См. `docs/orchestrator/status-model.md`

---

## DLD Orchestrator Reference

VPS daemon координирующий multi-project AI execution через pueue + SQLite (рантайм) + git
per-spec YAML (статус SoT, ADR-023). Critical path:
pueue completion → callback.py → guard → lifecycle.write_lifecycle (CAS) → push.

**Канонические доки (in-repo, версионируются с кодом):** `docs/orchestrator/`
- `README.md` — что/зачем, архитектура, поток задачи, два контракта, ADR-индекс
- `status-model.md` — lifecycle-SoT, запись статуса, write-once-done, guard, инварианты
- `components.md` — покомпонентный справочник + инварианты диспатча
- `runbook.md` — операционка, инцидент-восстановление, drift-инструменты
- `verification.md` — протокол ручной верификации спеки

---

## Backlog Rules

- **Size:** 30-50 active tasks max
- **Prefixes:** BUG, FTR, TECH, ARCH only (4 types)
- **Numbering:** Sequential across all types
- **Archive:** Weekly check, if >50 → archive to 30
- **Bug Hunt:** Saves a read-only report to `ai/bughunt/{YYYY-MM-DD}-report.md`. It creates **no** specs, **no** inbox items and **no** backlog rows — Hermes reviews the report and decides what becomes work (ADR-021/022). This line used to promise "standalone grouped specs, each with own sequential ID and own backlog entry", which stopped being true when intake moved behind the Hermes gate; `skills/bughunt/completion.md` is the contract.

---

## Project Structure

```
.claude/            # what DLD itself runs
├── agents/         # Subagent prompts (planner, coder, tester, review, personas)
├── rules/          # Conditional context — see "Rules loading" above
├── scripts/        # Node gates called from prompts (validate-*, check-prompt-integrity)
├── hooks/          # PreToolUse / PostToolUse / Stop validation
└── skills/         # spark, autopilot, council, audit, …

template/           # what downstream projects receive (mirror of the above + scaffold)

scripts/
├── vps/            # Orchestrator: orchestrator.py, callback.py, lifecycle.py, db.py, gate_logic.py
└── check_*.py      # Quality gates agents invoke (domain imports, docs sync)

tests/              # pytest — unit, integration, regression, contracts
test/
├── agents/         # Golden datasets for /eval (planner, coder, review, devil)
├── agents-harvested/  # Mined from real subagent traces; curate before use
└── scripts/        # Node harness suites

docs/orchestrator/  # Canonical orchestrator docs, versioned with the code

ai/
├── features/       # Specs from /spark
├── lifecycle/      # {SPEC-ID}.yaml — status SoT (ADR-023), callback is the only writer
├── backlog.md      # Rendered view, not the source of truth
├── lessons/        # Lessons bank (Historical Risks) — index.jsonl + per-domain files
├── diary/          # Session learnings → /reflect
├── inbox/          # Hermes intake gate (ADR-021/022)
└── bughunt/        # Read-only reports from /bughunt
```

`src/`, `ai/glossary/`, `.claude/contexts/`, `ai/ARCHITECTURE.md` and `.mcp.json.example`
belong to a **downstream** project's layout. They do not exist here; prompts that name them
guard with "if exists".
