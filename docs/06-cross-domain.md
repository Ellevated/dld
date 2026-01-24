# Cross-Domain Communication

## Problem

Domains should not directly import each other — this creates circular imports and tight coupling.

## Solution: Protocol + Dependency Injection

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

## Rule

A domain does NOT import another domain directly. Use Protocol + DI.

## Wiring (in Entry Points)

```python
# api/deps.py
from domains.users.repository import UserRepository
from domains.orders.service import OrderService

def get_order_service() -> OrderService:
    return OrderService(user_repo=UserRepository())
```

## Benefits

1. **Testability** — can replace dependency with mock
2. **Isolation** — domain doesn't know about another domain's implementation
3. **No cycles** — Protocol is defined in shared, not in domain
