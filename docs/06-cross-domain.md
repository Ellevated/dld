# Cross-Domain Communication

## Проблема

Домены не должны напрямую импортировать друг друга — это создаёт circular imports и tight coupling.

## Решение: Protocol + Dependency Injection

```python
# shared/interfaces.py
from typing import Protocol
from uuid import UUID

class IUserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> User | None: ...

# domains/orders/service.py
class OrderService:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    async def create_order(self, user_id: UUID):
        user = await self.user_repo.get_by_id(user_id)
        # ...
```

## Правило

Домен НЕ импортирует другой домен напрямую. Используй Protocol + DI.

## Wiring (в Entry Points)

```python
# api/deps.py
from domains.users.repository import UserRepository
from domains.orders.service import OrderService

def get_order_service() -> OrderService:
    return OrderService(user_repo=UserRepository())
```

## Преимущества

1. **Тестируемость** — можно подменить зависимость на mock
2. **Изоляция** — домен не знает о реализации другого домена
3. **Нет циклов** — Protocol определён в shared, не в домене
