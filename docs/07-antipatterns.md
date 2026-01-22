# Антипаттерны

## 1. God Files

```python
# ❌ ПЛОХО: 2000 строк в одном файле
# src/services/main_service.py (2000 LOC)

# ✅ ХОРОШО: Разбить по ответственности
# src/domains/orders/service.py (200 LOC)
# src/domains/orders/validation.py (100 LOC)
# src/domains/orders/notifications.py (150 LOC)
```

**Правило:** Файл > 400 LOC — сигнал к разбиению (600 для тестов).

---

## 2. Utils/Helpers свалка

```python
# ❌ ПЛОХО
src/utils/helpers.py  # 50 несвязанных функций

# ✅ ХОРОШО
src/shared/formatting.py      # форматирование
src/shared/validation.py      # валидация
src/domains/orders/utils.py   # utils специфичные для orders
```

---

## 3. Circular Imports

```python
# ❌ ПЛОХО
# domains/orders/service.py
from domains.users.service import UserService

# domains/users/service.py
from domains.orders.service import OrderService  # CIRCULAR!

# ✅ ХОРОШО: Dependency Injection
# domains/orders/service.py
from shared.interfaces import IUserService

class OrderService:
    def __init__(self, user_service: IUserService):
        self.user_service = user_service
```

---

## 4. Implicit Dependencies

```python
# ❌ ПЛОХО: Глобальный импорт
from config import db  # откуда это?

def get_order(id):
    return db.query(...)  # неявная зависимость

# ✅ ХОРОШО: Явная зависимость
from infra.db import Database

class OrderRepository:
    def __init__(self, db: Database):
        self.db = db
```

---

## 5. Inconsistent Naming

```python
# ❌ ПЛОХО: Разные стили
src/handlers/userHandler.py      # camelCase
src/handlers/order_handler.py    # snake_case
src/handlers/PaymentHandlers.py  # PascalCase

# ✅ ХОРОШО: Единый стиль (snake_case для файлов)
src/domains/users/handlers.py
src/domains/orders/handlers.py
src/domains/payments/handlers.py
```

---

## 6. Deep Nesting

```python
# ❌ ПЛОХО
src/domains/orders/services/internal/core/base/abstract/handler.py

# ✅ ХОРОШО
src/domains/orders/service.py
```

**Правило:** Максимум 3 уровня вложенности.
