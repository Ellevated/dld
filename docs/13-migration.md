# Migration from Existing Project

Если проект уже существует с плохой структурой:

---

## Шаг 1: Backwards-compatible shims

```python
# OLD: src/services/order_service.py
# NEW: src/domains/orders/service.py

# Shim для совместимости:
# src/services/order_service.py
from domains.orders.service import OrderService  # re-export
__all__ = ["OrderService"]
```

---

## Шаг 2: Постепенная миграция

1. Создай новую структуру `domains/`
2. Переноси файлы по одному
3. Обновляй импорты
4. Удаляй shims когда все импорты обновлены

---

## Шаг 3: Import linter с начала

Даже во время миграции — настрой linter чтобы новый код следовал правилам.

```python
# scripts/check_domain_imports.py
# Можно добавить whitelist для legacy файлов:

LEGACY_WHITELIST = {
    "src/services/order_service.py",  # TODO: migrate by 2026-02-01
    "src/utils/helpers.py",           # TODO: split into shared/
}
```

---

## Шаг 4: Удаление legacy

После полной миграции:
- Удали все shims
- Удали legacy папки
- Удали whitelist из linter
