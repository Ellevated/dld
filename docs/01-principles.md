# Key Principles

## Principle #1: Colocation by Domain

Group code by business meaning, not by technical type.

```
# ❌ BAD: Separation by type
src/
├── handlers/           # ALL handlers together
├── services/           # ALL services together
├── models/             # ALL models together
├── repositories/       # ALL repos together
└── utils/              # junk drawer

# ✅ GOOD: Colocation by domain
src/
├── domains/
│   ├── orders/
│   │   ├── handlers.py
│   │   ├── service.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   └── README.md
│   └── payments/
│       └── ...
├── shared/             # base types, exceptions
└── infra/              # db, cache, external APIs
```

**Why:** When LLM works with orders, it reads ONLY `domains/orders/`. No need to search the entire project.

---

## Principle #2: Three Layers

```
┌─────────────────────────────────────────┐
│              Entry Points               │  ← api/, bots/, cli/
│         (HTTP, Telegram, CLI)           │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│               Domains                   │  ← domains/
│    (business logic, isolated)           │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│            Infrastructure               │  ← infra/, shared/
│      (db, llm, external services)       │
└─────────────────────────────────────────┘
```

**Dependency rules:**
- Entry Points → Domains → Infrastructure
- Domains do NOT depend on each other directly (through shared interfaces)
- Infrastructure does NOT know about Domains

---

## Principle #3: Flat > Deep

```
# ❌ BAD: Deep nesting
src/domains/orders/services/internal/helpers/utils/format.py

# ✅ GOOD: Flat structure
src/domains/orders/formatting.py
```

**Rule:** Maximum 3 levels of nesting within a domain.

---

## Why This Matters

LLM works with limited context. The clearer the structure:

| Problem | Solution |
|---------|----------|
| LLM confuses files | Colocation by domain |
| Many Grep/Glob queries | Self-describing names |
| Unclear where to put code | Clear layers (api → domains → infra) |
| Long onboarding for new session | README in each domain |
