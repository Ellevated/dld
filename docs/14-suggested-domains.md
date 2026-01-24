# Suggested Domains for B2B SaaS

## Typical Domains

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

## Dependency Rules

- **auth** — leaf domain, depends on nothing
- **billing** — leaf domain, only depends on infra
- **workflows** — core domain, depends on auth + integrations
- **tasks** — depends on workflows
- **notifications** — depends on workflows + tasks
- **analytics** — depends on tasks + notifications
- **bot** — top-level, depends on everything

---

## Conclusion

LLM-friendly architecture is not rocket science. It's:

1. **Clear structure** — domains instead of types
2. **Compact contexts** — README in each domain (100 lines)
3. **Explicit dependencies** — DAG without cycles
4. **Consistency** — unified naming rules
5. **Enforcement** — import linter + file size gate in CI

Follow these principles from day one — and LLM will be your effective partner.
