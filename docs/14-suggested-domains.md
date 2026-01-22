# Suggested Domains for B2B SaaS

## Типичные домены

| Domain | Responsibility |
|--------|---------------|
| `auth` | Users, organizations, permissions |
| `workflows` | Workflow definitions, triggers, actions |
| `tasks` | Task instances, execution, history |
| `notifications` | Email, Telegram, webhook notifications |
| `integrations` | External service connections |
| `analytics` | Metrics, dashboards, reports |
| `billing` | Subscriptions, usage, invoices |
| `bot` | Telegram bot handlers, keyboards |

---

## Domain Dependency Graph (DAG)

```
                      shared
                         │
                         ▼
                       infra
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
       auth         integrations     billing
         │               │               │
         └───────┬───────┘               │
                 ▼                       │
             workflows ◄─────────────────┘
                 │
         ┌───────┴───────┐
         ▼               ▼
       tasks       notifications
         │               │
         └───────┬───────┘
                 ▼
             analytics
                 │
                 ▼
                bot
```

---

## Правила зависимостей

- **auth** — leaf domain, ни от кого не зависит
- **billing** — leaf domain, только от infra
- **workflows** — core domain, зависит от auth + integrations
- **tasks** — зависит от workflows
- **notifications** — зависит от workflows + tasks
- **analytics** — зависит от tasks + notifications
- **bot** — top-level, зависит от всех

---

## Заключение

LLM-friendly архитектура — это не rocket science. Это:

1. **Понятная структура** — домены вместо типов
2. **Компактные контексты** — README в каждом домене (100 строк)
3. **Явные зависимости** — DAG без циклов
4. **Консистентность** — единые правила именования
5. **Enforcement** — import linter + file size gate в CI

Следуй этим принципам с первого дня — и LLM будет твоим эффективным напарником.
