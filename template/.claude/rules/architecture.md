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

**Exception:** Bare `except Exception:` is ALLOWED in `.claude/hooks/` for fail-safe behavior.
Hooks must never crash — a crashing hook breaks Claude Code. See ADR-004.

---

## ADR (Architecture Decision Records)

| ID | Decision | Date | Reason |
|----|----------|------|--------|
| ADR-001 | Money in cents | 2026-01 | Avoid float precision errors |
| ADR-002 | Result instead of exceptions | 2026-01 | Explicit error handling |
| ADR-003 | Async everywhere | 2026-01 | Consistency, performance |
| ADR-004 | Bare exceptions in hooks | 2026-02 | Hooks are fail-safe infrastructure — must never crash |
| ADR-005 | Effort routing per agent | 2026-02 | Opus 4.6 effort parameter: max for planning/council, high for coding/review, medium for testing, low for logging |
| ADR-006 | No assistant prefilling | 2026-02 | Opus 4.6 removed prefilling support — use structured outputs or system prompts |
| ADR-007 | Caller-writes for subagent output | 2026-02 | Subagents can't reliably write files (0/36, GitHub #7032). Caller writes from response. |
| ADR-008 | Background fan-out for parallel agents | 2026-02 | `run_in_background: true` prevents context flooding. Responses go to temp files, not parent context. |
| ADR-009 | Background ALL pipeline steps | 2026-02 | Sequential foreground agents accumulate in orchestrator context. ALL steps use `run_in_background: true`. |
| ADR-010 | Orchestrator zero-read | 2026-02 | Orchestrator NEVER reads agent outputs directly (TaskOutput floods context, ~70K+). Collector subagent reads + summarizes. |
| ADR-011 | Enforcement as Code | 2026-02 | Process enforcement via JSON state + hooks + hard gates, not LLM memory. State files are SSOT for phase/task progress. |
| ADR-012 | Eval Criteria over freeform Tests | 2026-02 | Structured eval criteria (deterministic + integration + llm-judge) provide measurable, repeatable quality gates. Backward compat with legacy ## Tests. |

---

## Limits

| What | Limit | Reason |
|------|-------|--------|
| LOC per file | 400 (600 for tests) | LLM context window |
| Exports in __init__.py | 5 | Explicit public API |
| Nesting depth | 3 levels | Readability |
| Function arguments | 5 | Cognitive load |
