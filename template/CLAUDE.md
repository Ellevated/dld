# {Project Name}

{One-line description — заполнить после /bootstrap}

**Stack:** {Your stack here — e.g., Python 3.12 + FastAPI + PostgreSQL}
**Not using:** {Optional: list frameworks you're avoiding}

**Commands:**
- `./test fast` — lint + unit tests
- `./test` — full tests

---

## Quick Start

1. Run `/bootstrap` to unpack your idea
2. Fill this file based on `ai/idea/*.md`
3. Create domains structure
4. Run `/spark` for first feature

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

Трёхуровневая система знаний о проекте для предотвращения поломок при рефакторинге.

### Структура

```
.claude/rules/
├── dependencies.md     # Граф зависимостей между компонентами
├── architecture.md     # Паттерны, ADR, анти-паттерны
└── domains/            # Контекст конкретных доменов
    └── {domain}.md

ai/glossary/
├── billing.md          # Термины и правила домена
├── campaigns.md
└── ...
```

### Протоколы (агенты используют автоматически)

| Протокол | Когда | Кто |
|----------|-------|-----|
| `context-loader.md` | ПЕРЕД работой | spark, planner, coder, review, debugger, council |
| `context-updater.md` | ПОСЛЕ работы | spark, coder |

### Impact Tree Algorithm (5 шагов)

При любом изменении:

1. **ВВЕРХ** — кто использует изменяемый код? (`grep -r "from.*{module}" .`)
2. **ВНИЗ** — от чего зависит? (импорты в файле)
3. **ПО ТЕРМИНУ** — grep старого имени по всему проекту
4. **CHECKLIST** — обязательные папки (tests/, migrations/, edge functions/)
5. **DUAL SYSTEM** — если меняем источник данных, кто читает из старого/нового?

**Правило:** После изменений `grep "{old_term}" .` = 0 результатов!

### Module Headers

В начале значимых файлов:
```python
"""
Module: pricing_service
Role: Calculate campaign costs
Uses: campaigns/models, shared/types
Used by: seller/tools, campaigns/activation
Glossary: ai/glossary/billing.md
"""
```

---

## Skills (v3.3)

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

**New in v3.3:**
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
**НИКОГДА не применяй миграции напрямую! CI — единственный источник apply.**

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
├── diary/      # Session learnings (v3.3)
├── features/   # Task specs
├── ARCHITECTURE.md
└── backlog.md
```
