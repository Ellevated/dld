# Day-by-Day Onboarding

## День 1: Структура

- [ ] Создать базовую структуру:
  ```
  backend/src/
  ├── domains/
  ├── shared/
  ├── infra/
  └── api/
  ```
- [ ] Создать `CLAUDE.md` с описанием проекта (50 строк)
- [ ] Создать `.claude/contexts/shared.md`
- [ ] Настроить import linter
- [ ] Создать `ai/backlog.md`

---

## День 2: Shared Layer

- [ ] `shared/types.py` — базовые типы (UUID wrappers, etc.)
- [ ] `shared/result.py` — Result pattern для ошибок
- [ ] `shared/exceptions.py` — базовые исключения
- [ ] `shared/interfaces.py` — Protocol классы для DI

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

## День 3: Infrastructure

- [ ] `infra/db/client.py` — подключение к Supabase
- [ ] `infra/db/base_repository.py` — базовый репозиторий
- [ ] `infra/llm/client.py` — LLM клиент (если нужен)

---

## День 4+: Domains

Для каждого домена:
- [ ] Создать папку `domains/{name}/`
- [ ] Создать `README.md` с контекстом
- [ ] Создать `models.py` — Pydantic модели
- [ ] Создать `repository.py` — работа с БД
- [ ] Создать `service.py` — бизнес-логика
- [ ] Создать `__init__.py` с публичным API (max 5 exports)
- [ ] Создать `tests/` с unit-тестами

---

## Чеклист готовности

- [ ] CLAUDE.md < 100 строк
- [ ] Import linter проходит
- [ ] Нет файлов > 400 LOC (600 для тестов)
- [ ] Каждый домен имеет README.md
- [ ] Все exports в __init__.py ≤ 5
