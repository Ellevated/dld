# Шаблон CLAUDE.md

```markdown
# {Project Name}

{One-line description}

**Stack:** Python 3.12 + FastAPI + Supabase + Next.js + aiogram 3.x

**Commands:**
- `./test fast` — lint + unit tests
- `./test` — full (+ integration)
- `docker compose up` — run locally

---

## Architecture

### Layers

┌─────────────────────────────────────────────────────────────┐
│                      Entry Points                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  REST API   │  │ Telegram Bot│  │    Next.js Web      │  │
│  │  (FastAPI)  │  │  (aiogram)  │  │    (React SSR)      │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼─────────────────────┼────────────┘
          │                │                     │
          ▼                ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                        Domains                              │
│  ┌─────────┐  ┌───────────┐  ┌───────┐  ┌───────────────┐  │
│  │  auth   │  │ workflows │  │ tasks │  │ notifications │  │
│  └────┬────┘  └─────┬─────┘  └───┬───┘  └───────┬───────┘  │
└───────┼─────────────┼────────────┼──────────────┼──────────┘
        └─────────────┴──────┬─────┴──────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Infrastructure                          │
│  ┌────────────┐    ┌────────────┐    ┌─────────────────┐   │
│  │     db     │    │    llm     │    │    external     │   │
│  │  supabase  │    │   openai   │    │   (webhooks)    │   │
│  └────────────┘    └────────────┘    └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘

### Domain Dependencies

         shared (Result, exceptions)
              │
              ▼
         infra (db, llm, external)
              │
    ┌─────────┴─────────┐
    ▼                   ▼
  auth ◄───────── workflows
              ┌─────────┴─────────┐
              ▼                   ▼
           tasks          notifications
              │                   │
              └─────────┬─────────┘
                        ▼
                       bot

**Rule:** Arrows = "depends on". No reverse dependencies.

---

## Contexts

**Load before working:**

| Task | Context |
|------|---------|
| Workflows logic | `.claude/contexts/workflows.md` |
| Bot handlers | `.claude/contexts/bot.md` |
| DB, LLM, infra | `.claude/contexts/shared.md` |
| Frontend | `.claude/contexts/web.md` |

---

## Skills

| Skill | When |
|-------|------|
| **spark** | New feature, architecture decision |
| **plan** | After spark — detailed tasks |
| **autopilot** | Execute tasks (coder→tester→documenter→reviewer) |
| **council** | Complex decisions (5 experts) |
| **debug** | Root cause analysis |

**Flow:** `spark → plan → autopilot`

---

## Key Rules

### Imports
Direction: `domains → infra → shared` (never reverse)

### Test Safety
NEVER modify tests in `contracts/` or `regression/`

### File Size
Max 400 LOC per file (600 for tests). CI blocks larger files.

### Atomic Commits
One task = one commit. Tests must pass.

---

## Project Structure

```
backend/src/
├── shared/     # Result, exceptions, types
├── infra/      # db, llm, external
├── domains/    # auth, workflows, tasks, notifications, bot
├── api/        # http (FastAPI), telegram (aiogram)
└── config/     # settings

frontend/src/
├── app/        # Next.js app router
├── components/ # UI components
└── lib/        # utilities
```
```
