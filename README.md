# LLM-Friendly Architecture Principles

**Version:** 3.3 | **Date:** 2026-01-22

Руководство по созданию проектов, понятных для LLM-агентов.

---

## Quick Start

```bash
# 1. Клонируй/скопируй этот репо
git clone github.com/you/principles

# 2. Скопируй template в новый проект
mkdir my-project && cd my-project
cp -r /path/to/principles/template/* .
cp -r /path/to/principles/template/.claude .

# 3. Запусти Claude Code
claude

# 4. Распакуй идею
> /bootstrap
```

---

## Структура

```
principles/
├── README.md           # ← Ты здесь
├── docs/               # Документация для чтения
│   ├── 00-bootstrap.md
│   ├── 01-principles.md
│   └── ...
└── template/           # Готовый проект для копирования
    ├── .claude/
    │   ├── skills/     # 7 готовых skills
    │   └── agents/     # 8 agent prompts (flat structure)
    ├── ai/
    │   ├── backlog.md
    │   ├── diary/
    │   └── features/
    ├── CLAUDE.md
    └── README.md
```

---

## Workflow v3.1

```
New project: /bootstrap → Day 1 → /spark first feature
Feature:     /spark → /autopilot (auto-handoff)
Bug:         diagnose (5 Whys) → /spark → /autopilot
Complex:     /spark → /council → /autopilot
Hotfix:      <5 LOC → fix directly
```

**v3.1 Key changes:**
- Agent/Skill separation (agents/*.md = prompts, skills/*.md = UX)
- Flat agents directory (no nested folders)
- Diary captures learnings → reflect synthesizes rules

---

## Skills (в template/.claude/skills/)

| Skill | Когда использовать |
|-------|-------------------|
| **bootstrap** | Day 0 — распаковка идеи из головы |
| **spark** | Новая фича, баг, архитектурное решение |
| **autopilot** | Автономное выполнение (worktree + fresh subagents) |
| **council** | Сложные/спорные решения (5 экспертов) |
| **review** | Architecture watchdog |
| **reflect** | Синтез дневника в правила CLAUDE.md |
| **audit** | READ-ONLY анализ кода |
| **scout** | Изолированный research (Exa + Context7) |

## Agents (в template/.claude/agents/)

| Agent | Model | Роль |
|-------|-------|------|
| planner | opus | Детальный план имплементации |
| coder | sonnet | Написание кода |
| tester | sonnet | Smart Testing + Scope Protection |
| debugger | opus | Root cause analysis |
| spec-reviewer | sonnet | Соответствие спеке |
| review | opus | Качество кода, архитектура |
| scout | sonnet | Внешний research |
| documenter | sonnet | Обновление документации |

---

## Документация (в docs/)

### Foundation (философия)
| # | Документ | Описание |
|---|----------|----------|
| 0 | [00-why.md](docs/foundation/00-why.md) | Боль предпринимателя, зачем DLD |
| 1 | [01-double-loop.md](docs/foundation/01-double-loop.md) | Концепция двух петель |
| 2 | [02-agent-roles.md](docs/foundation/02-agent-roles.md) | Роли агентов (Planner/Developer/Tester/Supervisor) |

### Начало
| # | Документ | Описание |
|---|----------|----------|
| 0 | [00-bootstrap.md](docs/00-bootstrap.md) | Философия + порядок запуска |

### Архитектура (01-08)
| # | Документ | Описание |
|---|----------|----------|
| 1 | [01-principles.md](docs/01-principles.md) | Ключевые принципы |
| 2 | [02-naming.md](docs/02-naming.md) | Правила именования |
| 3 | [03-project-structure.md](docs/03-project-structure.md) | Структура проекта |
| 4 | [04-claude-md-template.md](docs/04-claude-md-template.md) | Шаблон CLAUDE.md |
| 5 | [05-domain-template.md](docs/05-domain-template.md) | Шаблон домена |
| 6 | [06-cross-domain.md](docs/06-cross-domain.md) | Cross-Domain Communication |
| 7 | [07-antipatterns.md](docs/07-antipatterns.md) | Антипаттерны |
| 8 | [08-metrics.md](docs/08-metrics.md) | Метрики качества |

### Процессы (09-14)
| # | Документ | Описание |
|---|----------|----------|
| 9 | [09-onboarding.md](docs/09-onboarding.md) | Day-by-Day Onboarding |
| 10 | [10-testing.md](docs/10-testing.md) | Testing Strategy |
| 11 | [11-ci-cd.md](docs/11-ci-cd.md) | CI/CD + Import Linter |
| 12 | [12-docker.md](docs/12-docker.md) | Docker Configuration |
| 13 | [13-migration.md](docs/13-migration.md) | Migration from Existing |
| 14 | [14-suggested-domains.md](docs/14-suggested-domains.md) | Suggested Domains B2B SaaS |

### LLM Workflows (15-20)
| # | Документ | Описание |
|---|----------|----------|
| 15 | [15-skills-setup.md](docs/15-skills-setup.md) | Skills System Setup |
| 16 | [16-forbidden.md](docs/16-forbidden.md) | Forbidden Rules & Guardrails |
| 17 | [17-backlog-management.md](docs/17-backlog-management.md) | Backlog & ID Protocol |
| 18 | [18-spec-template.md](docs/18-spec-template.md) | Feature Spec Template |
| 19 | [19-living-architecture.md](docs/19-living-architecture.md) | Living Architecture Docs |
| 20 | [20-mcp-setup.md](docs/20-mcp-setup.md) | MCP Servers Setup (Context7, Exa) |

---

## TL;DR

```
1. Colocation > Separation by type
2. Один домен = один контекст (~100 строк)
3. Self-describing names (без аббревиатур)
4. Dependency graph = DAG (без циклов)
5. Max 400 LOC per file (600 for tests)
6. Max 5 exports in __init__.py
7. Immutable tests: contracts/ + regression/
8. Skills workflow: spark → autopilot
```

**Метрика успеха:** Если новый разработчик понимает проект за 30 минут — LLM поймёт за 30 секунд.
