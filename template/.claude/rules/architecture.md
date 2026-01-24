# Architecture

Архитектурные решения и паттерны проекта.

## Структура проекта

```
src/
├── shared/     # Result, exceptions, types (NO business logic)
├── infra/      # db, llm, external (technical adapters)
├── domains/    # Business logic
└── api/        # Entry points (telegram, http, cli)
```

## Направление импортов

```
shared ← infra ← domains ← api
       (НИКОГДА в обратную сторону)
```

**Правило:** Каждый слой может импортировать только из слоёв левее себя.

---

## Паттерны (СЛЕДОВАТЬ)

| Паттерн | Где применять | Пример |
|---------|---------------|--------|
| Result[T, E] | Все domain функции | `async def get_user() -> Result[User, UserError]` |
| Async everywhere | Все IO операции | `async def`, `await` |
| Копейки для денег | Все money-related | `amount: int` (не float, не Decimal) |
| Explicit errors | Domain boundaries | `UserNotFoundError`, не generic Exception |

---

## Анти-паттерны (ЗАПРЕЩЕНО)

| Что | Почему | Вместо этого |
|-----|--------|--------------|
| Float для денег | Precision loss | int (копейки) |
| Bare exceptions | Скрывает ошибки | Explicit error types |
| Cross-domain import | Coupling | Через infra или shared |
| Файл > 400 LOC | LLM-unfriendly | Split на модули |
| Circular imports | Архитектурная проблема | Рефакторинг зависимостей |

---

## ADR (Architecture Decision Records)

| ID | Решение | Дата | Причина |
|----|---------|------|---------|
| ADR-001 | Деньги в копейках | YYYY-MM | Избежать float precision errors |
| ADR-002 | Result вместо exceptions | YYYY-MM | Explicit error handling |
| ADR-003 | Async everywhere | YYYY-MM | Consistency, performance |

---

## Лимиты

| Что | Лимит | Причина |
|-----|-------|---------|
| LOC per file | 400 (600 for tests) | LLM context window |
| Exports in __init__.py | 5 | Explicit public API |
| Nesting depth | 3 levels | Readability |
| Function arguments | 5 | Cognitive load |
