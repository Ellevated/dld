# Naming Rules

## Files: Self-describing names

```
# ❌ BAD: Non-obvious names
src/services/sm.py           # what is sm?
src/utils/helpers.py         # helpers for what?
src/core/manager.py          # manager of what?

# ✅ GOOD: Obvious names
src/domains/orders/slot_assignment.py
src/domains/payments/invoice_generator.py
src/shared/result.py
```

**Rule:** File name should answer "what's inside?" without opening it.

---

## Functions: Verb + Noun

```python
# ❌ BAD
def process(data): ...
def handle(request): ...
def do_stuff(): ...

# ✅ GOOD
def assign_slot_to_buyer(slot_id, buyer_id): ...
def calculate_cashback_amount(order): ...
def validate_phone_number(phone): ...
```

---

## Classes: Noun + Role

```python
# ❌ BAD
class Manager: ...
class Handler: ...
class Helper: ...

# ✅ GOOD
class OrderRepository: ...
class PaymentProcessor: ...
class SlotAssignmentService: ...
```

---

## Constants: UPPER_SNAKE with context

```python
# ❌ BAD
MAX = 10
TIMEOUT = 30
DEFAULT = "ru"

# ✅ GOOD
MAX_SLOTS_PER_CAMPAIGN = 10
API_REQUEST_TIMEOUT_SEC = 30
DEFAULT_LOCALE = "ru"
```

---

## Consistency

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
