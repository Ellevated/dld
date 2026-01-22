# Ключевые принципы

## Принцип #1: Colocation by Domain

Группируй код по бизнес-смыслу, не по техническому типу.

```
# ❌ ПЛОХО: Separation by type
src/
├── handlers/           # ВСЕ handlers вместе
├── services/           # ВСЕ services вместе
├── models/             # ВСЕ models вместе
├── repositories/       # ВСЕ repos вместе
└── utils/              # свалка

# ✅ ХОРОШО: Colocation by domain
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
├── shared/             # базовые типы, exceptions
└── infra/              # db, cache, external APIs
```

**Почему:** Когда LLM работает с заказами, он читает ТОЛЬКО `domains/orders/`. Не нужно искать по всему проекту.

---

## Принцип #2: Три слоя

```
┌─────────────────────────────────────────┐
│              Entry Points               │  ← api/, bots/, cli/
│         (HTTP, Telegram, CLI)           │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│               Domains                   │  ← domains/
│    (бизнес-логика, изолированная)       │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│            Infrastructure               │  ← infra/, shared/
│      (db, llm, external services)       │
└─────────────────────────────────────────┘
```

**Правила зависимостей:**
- Entry Points → Domains → Infrastructure
- Domains НЕ зависят друг от друга напрямую (через shared interfaces)
- Infrastructure НЕ знает о Domains

---

## Принцип #3: Flat > Deep

```
# ❌ ПЛОХО: Глубокая вложенность
src/domains/orders/services/internal/helpers/utils/format.py

# ✅ ХОРОШО: Плоская структура
src/domains/orders/formatting.py
```

**Правило:** Максимум 3 уровня вложенности внутри домена.

---

## Почему это важно

LLM работает с ограниченным контекстом. Чем понятнее структура:

| Проблема | Решение |
|----------|---------|
| LLM путает файлы | Colocation by domain |
| Много Grep/Glob запросов | Self-describing names |
| Непонятно куда класть код | Чёткие слои (api → domains → infra) |
| Долгий онбординг новой сессии | README в каждом домене |
