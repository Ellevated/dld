# Project Dependencies

Dependency map between project components.

## How to Read

- `A → B` means "A uses B"
- `A ← B` means "A is used by B"

---

## {domain_name}

**Path:** `src/domains/{domain_name}/`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| {dependency} | {path} | {function}() |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| {caller} | {file}:{line} | {function}() |

### When changing API, check

- [ ] {dependent_1}
- [ ] {dependent_2}

---

## Example: billing

**Path:** `src/domains/billing/`

### Uses (→)

| What | Where | Function |
|------|-------|----------|
| users | infra/db | get_user() |
| database | infra/db | transactions table |

### Used by (←)

| Who | File:line | Function |
|-----|-----------|----------|
| campaigns | services.py:45 | get_balance() |
| campaigns | services.py:78 | check_can_spend() |
| seller | actions.py:23 | deduct_balance() |

### When changing API, check

- [ ] campaigns
- [ ] seller

---

## Last Update

| Date | What | Who |
|------|------|-----|
| YYYY-MM-DD | Initialize dependency map | spark |
