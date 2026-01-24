# Project Dependencies

Карта зависимостей между компонентами проекта.

## Как читать

- `A → B` означает "A использует B"
- `A ← B` означает "A используется в B"

---

## {domain_name}

**Path:** `src/domains/{domain_name}/`

### Использует (→)

| Что | Где | Функция |
|-----|-----|---------|
| {dependency} | {path} | {function}() |

### Используется в (←)

| Кто | Файл:строка | Функция |
|-----|-------------|---------|
| {caller} | {file}:{line} | {function}() |

### При изменении API проверить

- [ ] {dependent_1}
- [ ] {dependent_2}

---

## Пример: billing

**Path:** `src/domains/billing/`

### Использует (→)

| Что | Где | Функция |
|-----|-----|---------|
| users | infra/db | get_user() |
| database | infra/db | transactions table |

### Используется в (←)

| Кто | Файл:строка | Функция |
|-----|-------------|---------|
| campaigns | services.py:45 | get_balance() |
| campaigns | services.py:78 | check_can_spend() |
| seller | actions.py:23 | deduct_balance() |

### При изменении API проверить

- [ ] campaigns
- [ ] seller

---

## Последнее обновление

| Дата | Что | Кто |
|------|-----|-----|
| YYYY-MM-DD | Инициализация карты зависимостей | spark |
