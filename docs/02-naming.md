# Правила именования

## Файлы: Self-describing names

```
# ❌ ПЛОХО: Неочевидные имена
src/services/sm.py           # что такое sm?
src/utils/helpers.py         # helpers чего?
src/core/manager.py          # manager чего?

# ✅ ХОРОШО: Очевидные имена
src/domains/orders/slot_assignment.py
src/domains/payments/invoice_generator.py
src/shared/result.py
```

**Правило:** Имя файла должно отвечать на вопрос "что внутри?" без открытия.

---

## Функции: Verb + Noun

```python
# ❌ ПЛОХО
def process(data): ...
def handle(request): ...
def do_stuff(): ...

# ✅ ХОРОШО
def assign_slot_to_buyer(slot_id, buyer_id): ...
def calculate_cashback_amount(order): ...
def validate_phone_number(phone): ...
```

---

## Классы: Noun + Role

```python
# ❌ ПЛОХО
class Manager: ...
class Handler: ...
class Helper: ...

# ✅ ХОРОШО
class OrderRepository: ...
class PaymentProcessor: ...
class SlotAssignmentService: ...
```

---

## Константы: UPPER_SNAKE с контекстом

```python
# ❌ ПЛОХО
MAX = 10
TIMEOUT = 30
DEFAULT = "ru"

# ✅ ХОРОШО
MAX_SLOTS_PER_CAMPAIGN = 10
API_REQUEST_TIMEOUT_SEC = 30
DEFAULT_LOCALE = "ru"
```

---

## Единообразие

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
