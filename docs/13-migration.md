# Migration from Existing Project

If the project already exists with poor structure:

---

## Step 1: Backwards-compatible shims

```python
# OLD: src/services/order_service.py
# NEW: src/domains/orders/service.py

# Shim for compatibility:
# src/services/order_service.py
from domains.orders.service import OrderService  # re-export
__all__ = ["OrderService"]
```

---

## Step 2: Gradual migration

1. Create new `domains/` structure
2. Move files one by one
3. Update imports
4. Remove shims when all imports are updated

---

## Step 3: Import linter from the start

Even during migration — set up linter so new code follows the rules.

```python
# scripts/check_domain_imports.py
# You can add a whitelist for legacy files:

LEGACY_WHITELIST = {
    "src/services/order_service.py",  # TODO: migrate by 2026-02-01
    "src/utils/helpers.py",           # TODO: split into shared/
}
```

---

## Step 4: Remove legacy

After full migration:
- Remove all shims
- Remove legacy folders
- Remove whitelist from linter
