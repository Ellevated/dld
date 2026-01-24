# Antipatterns

## 1. God Files

```python
# ❌ BAD: 2000 lines in one file
# src/services/main_service.py (2000 LOC)

# ✅ GOOD: Split by responsibility
# src/domains/orders/service.py (200 LOC)
# src/domains/orders/validation.py (100 LOC)
# src/domains/orders/notifications.py (150 LOC)
```

**Rule:** File > 400 LOC — signal to split (600 for tests).

---

## 2. Utils/Helpers Junk Drawer

```python
# ❌ BAD
src/utils/helpers.py  # 50 unrelated functions

# ✅ GOOD
src/shared/formatting.py      # formatting
src/shared/validation.py      # validation
src/domains/orders/utils.py   # utils specific to orders
```

---

## 3. Circular Imports

```python
# ❌ BAD
# domains/orders/service.py
from domains.users.service import UserService

# domains/users/service.py
from domains.orders.service import OrderService  # CIRCULAR!

# ✅ GOOD: Dependency Injection
# domains/orders/service.py
from shared.interfaces import IUserService

class OrderService:
    def __init__(self, user_service: IUserService):
        self.user_service = user_service
```

---

## 4. Implicit Dependencies

```python
# ❌ BAD: Global import
from config import db  # where is this from?

def get_order(id):
    return db.query(...)  # implicit dependency

# ✅ GOOD: Explicit dependency
from infra.db import Database

class OrderRepository:
    def __init__(self, db: Database):
        self.db = db
```

---

## 5. Inconsistent Naming

```python
# ❌ BAD: Different styles
src/handlers/userHandler.py      # camelCase
src/handlers/order_handler.py    # snake_case
src/handlers/PaymentHandlers.py  # PascalCase

# ✅ GOOD: Single style (snake_case for files)
src/domains/users/handlers.py
src/domains/orders/handlers.py
src/domains/payments/handlers.py
```

---

## 6. Deep Nesting

```python
# ❌ BAD
src/domains/orders/services/internal/core/base/abstract/handler.py

# ✅ GOOD
src/domains/orders/service.py
```

**Rule:** Maximum 3 levels of nesting.
