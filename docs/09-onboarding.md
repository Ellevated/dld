# Day-by-Day Onboarding

## Day 1: Structure

- [ ] Create basic structure:
  ```
  backend/src/
  ├── domains/
  ├── shared/
  ├── infra/
  └── api/
  ```
- [ ] Create `CLAUDE.md` with project description (50 lines)
- [ ] Create `.claude/contexts/shared.md`
- [ ] Set up import linter
- [ ] Create `ai/backlog.md`

---

## Day 2: Shared Layer

- [ ] `shared/types.py` — base types (UUID wrappers, etc.)
- [ ] `shared/result.py` — Result pattern for errors
- [ ] `shared/exceptions.py` — base exceptions
- [ ] `shared/interfaces.py` — Protocol classes for DI

```python
# shared/result.py
from dataclasses import dataclass
from typing import TypeVar, Generic

T = TypeVar("T")
E = TypeVar("E")

@dataclass
class Ok(Generic[T]):
    value: T

@dataclass
class Err(Generic[E]):
    error: E

Result = Ok[T] | Err[E]
```

---

## Day 3: Infrastructure

- [ ] `infra/db/client.py` — Supabase connection
- [ ] `infra/db/base_repository.py` — base repository
- [ ] `infra/llm/client.py` — LLM client (if needed)

---

## Day 4+: Domains

For each domain:
- [ ] Create folder `domains/{name}/`
- [ ] Create `README.md` with context
- [ ] Create `models.py` — Pydantic models
- [ ] Create `repository.py` — DB operations
- [ ] Create `service.py` — business logic
- [ ] Create `__init__.py` with public API (max 5 exports)
- [ ] Create `tests/` with unit tests

---

## Readiness Checklist

- [ ] CLAUDE.md < 100 lines
- [ ] Import linter passes
- [ ] No files > 400 LOC (600 for tests)
- [ ] Each domain has README.md
- [ ] All exports in __init__.py ≤ 5
