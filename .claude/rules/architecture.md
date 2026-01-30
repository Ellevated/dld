# Architecture

Architectural decisions and patterns for the project.

## Project Structure

```
src/
├── shared/     # Result, exceptions, types (NO business logic)
├── infra/      # db, llm, external (technical adapters)
├── domains/    # Business logic
└── api/        # Entry points (telegram, http, cli)
```

## Import Direction

```
shared ← infra ← domains ← api
       (NEVER in reverse)
```

**Rule:** Each layer can only import from layers to the left of it.

---

## Patterns (FOLLOW)

| Pattern | Where to apply | Example |
|---------|----------------|---------|
| Result[T, E] | All domain functions | `async def get_user() -> Result[User, UserError]` |
| Async everywhere | All IO operations | `async def`, `await` |
| Cents for money | All money-related | `amount: int` (not float, not Decimal) |
| Explicit errors | Domain boundaries | `UserNotFoundError`, not generic Exception |

---

## Anti-patterns (FORBIDDEN)

| What | Why | Instead |
|------|-----|---------|
| Float for money | Precision loss | int (cents) |
| Bare exceptions | Hides errors | Explicit error types |
| Cross-domain import | Coupling | Through infra or shared |
| File > 400 LOC | LLM-unfriendly | Split into modules |
| Circular imports | Architectural problem | Refactor dependencies |

---

## ADR (Architecture Decision Records)

| ID | Decision | Date | Reason |
|----|----------|------|--------|
| ADR-001 | Money in cents | 2026-01 | Avoid float precision errors |
| ADR-002 | Result instead of exceptions | 2026-01 | Explicit error handling |
| ADR-003 | Async everywhere | 2026-01 | Consistency, performance |

---

## Limits

| What | Limit | Reason |
|------|-------|--------|
| LOC per file | 400 (600 for tests) | LLM context window |
| Exports in __init__.py | 5 | Explicit public API |
| Nesting depth | 3 levels | Readability |
| Function arguments | 5 | Cognitive load |
