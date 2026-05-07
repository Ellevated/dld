# Backend: [BACK-0001] Seller LK API — Full MVP

**Status:** queued | **Priority:** P0 | **Date:** 2026-03-02
**Repo:** `dev/awardybot` | **Stack:** FastAPI + SQLAlchemy + Alembic + PostgreSQL
**Prefix:** `/api/seller/v1/`

---

## Why

Фронтенд Seller LK (6 спек FTR-0021..0026) полностью зависит от бэкенд-API. Без этих 15 endpoints ЛК не может работать. Вся бизнес-логика, авторизация, платежи и обработка Excel — на бэкенде.

---

## Scope

**15 endpoints, 10 новых таблиц, 3 внешние интеграции.**

| Группа | Endpoints | Внешняя интеграция |
|--------|-----------|-------------------|
| Auth (§1) | 4: send-otp, verify-otp, refresh, logout | SMSC.ru (SMS) |
| Auth (§1) | 1: me | — |
| Promotions (§2) | 4: list, create, get, cancel | — |
| Batch (§3) | 3: upload, status, confirm | — |
| Balance (§4) | 2: get, topup | YuKassa (платежи) |
| Profile (§5) | 2: get, update | DaData (ИНН → компания) |
| Health (§6) | 1: health | — |
| Webhook (§7) | 1: yukassa callback | YuKassa (webhook) |

**Out of scope:**
- Admin API (существующий, не трогаем)
- Telegram Bot webhook handler (существующий)
- AI-парсер для Excel (v2)
- Recurring payments
- Invoice generation

---

## Pre-conditions (Week 0)

До первого эндпоинта выполнить:

| # | Задача | Оценка |
|---|--------|--------|
| 0.1 | Проверить тип `sellers.id` (UUID vs bigint) — от этого зависят все FK | 30 мин |
| 0.2 | Создать `SELLER_JWT_SECRET` (256-bit): `python -c "import secrets; print(secrets.token_urlsafe(32))"` | 5 мин |
| 0.3 | Получить API ключ SMSC.ru (SMS), сохранить в env | 1ч |
| 0.4 | Зарегистрировать магазин в YuKassa, получить `shop_id` + `secret_key` | 2ч |
| 0.5 | Получить API ключ DaData, сохранить в env | 30 мин |

**ENV vars (новые):**
```bash
SELLER_JWT_SECRET=           # 256-bit, openssl rand -base64 32
SELLER_JWT_ACCESS_TTL=3600   # 1 час
SELLER_JWT_REFRESH_TTL=604800 # 7 дней

SMSC_LOGIN=
SMSC_PASSWORD=
SMSC_SENDER=Dowry            # имя отправителя SMS

YUKASSA_SHOP_ID=
YUKASSA_SECRET_KEY=
YUKASSA_RETURN_URL=https://dowry.pro/lk/balance  # куда редиректить после оплаты

DADATA_API_KEY=
DADATA_SECRET_KEY=

BATCH_JITTER_MAX_HOURS=72    # разброс запуска промоушенов
BATCH_MAX_ITEMS=10           # лимит строк в Excel
```

---

## DB Schema (10 новых таблиц)

Полная схема с SQL — в `ai/blueprint/system-blueprint/data-architecture.md`.

### Миграции (порядок важен — FK зависимости):

```
Sprint 1 — Auth:
  001_create_seller_auth_methods.sql
  002_create_seller_otp_codes.sql
  003_create_seller_sessions.sql

Sprint 2 — Business:
  004_create_seller_companies.sql
  005_create_campaign_results.sql
  006_create_batch_jobs.sql
  007_create_batch_items.sql
  008_create_seller_balances.sql
  009_create_seller_transactions.sql
  010_create_worker_heartbeats.sql
```

**Принцип Expand-Only:** НЕ ALTER TABLE на существующих таблицах (`sellers`, `campaigns`, `slots`). Только новые таблицы.

### Ключевые таблицы (краткое описание):

| Таблица | Назначение | Ключевые поля |
|---------|-----------|---------------|
| `seller_auth_methods` | Расширяемая auth (phone, tg) | `method`, `identifier`, `verified_at` |
| `seller_otp_codes` | 6-значный OTP, SHA-256, TTL 5min | `code_hash`, `expires_at`, `attempts` (max 5) |
| `seller_sessions` | Refresh tokens, hashed | `refresh_token` (SHA-256), `expires_at`, `revoked_at` |
| `seller_companies` | ИНН + DaData enrichment | `inn`, `name`, `dadata_raw` JSONB |
| `campaign_results` | Позиции до/после | `position_before`, `position_after`, `position_delta` (generated) |
| `batch_jobs` | Excel-загрузка | `status` (8 состояний), `parse_errors` JSONB |
| `batch_items` | Строки Excel → кампании | `campaign_id` (nullable), `scheduled_at`, `claimed_at` |
| `seller_balances` | Материализованный баланс | `available_kopecks` CHECK >= 0 |
| `seller_transactions` | Append-only ledger | `idempotency_key` UNIQUE, `amount_kopecks` |
| `worker_heartbeats` | Liveness воркеров | `last_seen_at`, `items_processed` |

---

## Глобальные правила

### 1. seller_id ТОЛЬКО из JWT

```python
async def get_current_seller(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Seller:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401)

    payload = jwt.decode(token, SELLER_JWT_SECRET, algorithms=["HS256"])

    if payload.get("role") != "seller":
        raise HTTPException(403)

    seller_id = payload["sub"]  # единственный источник seller_id
    seller = await db.get(Seller, seller_id)
    if not seller or not seller.is_active:
        raise HTTPException(401)

    return seller
```

**Pydantic request models НЕ содержат поле `seller_id`.** Любая попытка передать его в body — игнорируется.

### 2. IDOR Protection

```python
# GET /promotions/{id} — правильный паттерн
promotion = await db.get(Promotion, id)
if not promotion or promotion.seller_id != seller.id:
    raise HTTPException(404)  # НЕ 403 — не раскрываем существование ресурса
```

### 3. Money в kopecks (ADR-001)

Все суммы — `INTEGER`, никаких `FLOAT`. Поля заканчиваются на `_kopecks`.

### 4. Единый error format

```python
class SellerApiError(BaseModel):
    error: ErrorDetail
    request_id: str  # UUID, для корреляции с логами

class ErrorDetail(BaseModel):
    code: str        # машиночитаемый: "INSUFFICIENT_BALANCE"
    message: str     # на русском: "Недостаточно средств"
    action: str | None = None  # что делать
    field: str | None = None   # для validation errors
    details: dict | None = None
```

### 5. Терминология

- **URL:** `/promotions` (НИКОГДА `/campaigns` в seller API)
- **DB:** `campaigns` таблица (существующая)
- **Маппинг:** Pydantic serializer переименовывает: `campaign.id` → `promotion_id`, `campaign.sku` → `article`
- **Запрещено:** "выкуп", "buyout", "slot" в seller API responses

### 6. HttpOnly Cookies

```python
# Set-Cookie при verify-otp
response.set_cookie(
    key="access_token",
    value=access_jwt,
    httponly=True,
    secure=True,          # HTTPS only (в dev = False)
    samesite="strict",
    path="/api/seller",
    max_age=3600,         # 1 час
)
response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,
    secure=True,
    samesite="strict",
    path="/api/seller/v1/auth/refresh",
    max_age=604800,       # 7 дней
)
```

---

## §1. Auth (5 endpoints)

### POST /auth/send-otp

Отправить OTP на телефон.

**Request:**
```json
{ "phone": "+79001234567" }
```

**Логика:**
1. Валидировать формат E.164 (regex: `^\+7\d{10}$`)
2. Rate check: COUNT OTP за 10 мин с этого номера. Если >= 3 → 429
3. Сгенерировать 6-значный код: `secrets.randbelow(900000) + 100000`
4. Сохранить `SHA-256(code)` в `seller_otp_codes` с `expires_at = NOW() + 5 min`
5. Отправить SMS через SMSC.ru: `"Код: {code}. Dowry"`
6. Ответить `{ "sent": true }` — НЕ подтверждать, зарегистрирован ли номер (phone enumeration protection)

**Auto-registration:** Если номер не в `sellers` — создать запись с `is_active=true`. Продавец узнаёт, зарегистрирован ли он, только после verify-otp.

**SMSC.ru интеграция:**
```python
async def send_sms(phone: str, message: str):
    async with httpx.AsyncClient() as client:
        await client.get("https://smsc.ru/sys/send.php", params={
            "login": SMSC_LOGIN,
            "psw": SMSC_PASSWORD,
            "phones": phone,
            "mes": message,
            "sender": SMSC_SENDER,
        })
```

**Errors:** 400 INVALID_PHONE, 429 OTP_RATE_LIMIT

---

### POST /auth/verify-otp

Проверить OTP, выдать сессию.

**Request:**
```json
{ "phone": "+79001234567", "code": "123456" }
```

**Логика:**
1. Найти последний неиспользованный OTP для этого телефона
2. Если не найден или `expires_at < NOW()` → 400 INVALID_CODE
3. Increment `attempts`. Если `attempts >= 5` → 400 OTP_EXHAUSTED
4. `hmac.compare_digest(SHA-256(code), code_hash)` — timing-safe compare
5. При совпадении: `UPDATE SET used_at = NOW()`
6. Найти/создать seller по телефону
7. Создать JWT (access_token, 1ч) + refresh_token (7 дней, hashed в DB)
8. Set-Cookie обоих токенов (HttpOnly, Secure, SameSite=Strict)

**JWT Payload:**
```json
{
  "sub": "seller-uuid",
  "role": "seller",
  "phone": "1234",
  "iat": 1709000000,
  "exp": 1709003600
}
```

**Response 200:**
```json
{
  "seller_id": "uuid",
  "phone_last4": "1234"
}
```
Токены — ТОЛЬКО через Set-Cookie, не в body.

**Errors:** 400 INVALID_CODE, 400 OTP_EXHAUSTED, 429 OTP_RATE_LIMIT

---

### POST /auth/refresh

Обновить access_token. Refresh token ротируется (single-use).

**Auth:** refresh_token cookie (автоматически).
**Request:** пустое тело.

**Логика:**
1. Прочитать `refresh_token` из cookie
2. `SHA-256(token)` → найти в `seller_sessions` WHERE `revoked_at IS NULL AND expires_at > NOW()`
3. Если не найден → 401
4. **Обнаружение повторного использования:** Если token уже revoked → REVOKE ALL sessions этого seller (compromise detected)
5. Revoke текущий refresh_token (`SET revoked_at = NOW()`)
6. Создать новый refresh_token + новый access_token
7. Set-Cookie обоих

**Response 200:** `{ "ok": true }` (токены в cookie)
**Errors:** 401 REFRESH_TOKEN_INVALID, 401 REFRESH_TOKEN_REUSE

---

### POST /auth/logout

Завершить сессию. Идемпотентен.

**Auth:** access_token cookie.
**Логика:**
1. Revoke refresh_token текущей сессии
2. Clear cookies: `Set-Cookie: access_token=; Max-Age=0`, `Set-Cookie: refresh_token=; Max-Age=0`

**Response 200:** `{ "ok": true }`. Всегда 200, даже если сессия уже не существует.

---

### GET /auth/me

Текущий пользователь. Используется фронтом как проверка "залогинен ли".

**Auth:** access_token cookie.

**Response 200:**
```json
{
  "seller_id": "uuid",
  "phone": "+79001234567",
  "phone_last4": "1234",
  "name": "Иван Иванов",
  "company_name": "ООО Рога и Копыта"
}
```

**Errors:** 401 (redirect to login на фронте)

---

## §2. Promotions (4 endpoints)

**DB → API маппинг:** `campaigns.id → id`, `campaigns.sku → article`, `campaigns.redemptions_planned → quantity`, DB status (6) → API status (4):
- `draft`, `queued` → `pending`
- `active`, `paused` → `active`
- `completed` → `completed`
- `cancelled` → `cancelled`

### GET /promotions

**Auth:** access_token cookie → `get_current_seller`.
**Query:** `page` (default 1), `per_page` (default 20, max 100), `status?` (pending|active|completed|cancelled)

**Логика:** `SELECT FROM campaigns WHERE seller_id = $seller_id` + статус-фильтр + пагинация. Маппинг полей через Pydantic alias.

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "article": "12345678",
      "marketplace": "WB",
      "keyword": "кроссовки мужские",
      "quantity": 10,
      "quantity_completed": 7,
      "cashback_kopecks": 15000,
      "status": "active",
      "scheduled_at": "2026-03-15T14:30:00Z",
      "started_at": "2026-03-15T15:00:00Z",
      "completed_at": null,
      "created_at": "2026-03-14T10:00:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "per_page": 20,
  "has_next": true
}
```

---

### POST /promotions

Создать одно продвижение.

**Request:**
```json
{
  "article": "12345678",
  "marketplace": "WB",
  "keyword": "кроссовки мужские",
  "quantity": 10,
  "cashback_kopecks": 15000
}
```

**Логика:**
1. Валидация: article max 50, keyword max 100, quantity 1-50
2. Расчёт стоимости (стандартный тариф если cashback не указан)
3. **Атомарное списание** (BEGIN + SELECT FOR UPDATE + UPDATE balance + INSERT transaction + INSERT campaign + COMMIT)
4. Назначить `scheduled_at = NOW() + random(0, BATCH_JITTER_MAX_HOURS)` если из batch, или `NOW()` если одиночный
5. Вернуть созданное промоушен

**Response 201:**
```json
{
  "id": "uuid",
  "status": "pending",
  "scheduled_at": "2026-03-15T14:30:00Z",
  "cost_kopecks": 15000,
  "balance_after_kopecks": 135000
}
```

**Errors:** 400 VALIDATION_ERROR, 402 INSUFFICIENT_BALANCE, 422 INVALID_ARTICLE

---

### GET /promotions/{id}

Детали + история статусов.

**Логика:** SELECT + IDOR check (`seller_id` match). Расширение: `status_history` + `result` (из `campaign_results`).

**Response 200:**
```json
{
  "id": "uuid",
  "article": "12345678",
  "marketplace": "WB",
  "keyword": "кроссовки мужские",
  "quantity": 10,
  "quantity_completed": 7,
  "cashback_kopecks": 15000,
  "status": "active",
  "scheduled_at": "2026-03-15T14:30:00Z",
  "started_at": "2026-03-15T15:00:00Z",
  "completed_at": null,
  "created_at": "2026-03-14T10:00:00Z",
  "status_history": [
    { "status": "created", "changed_at": "2026-03-14T10:00:00Z", "note": null },
    { "status": "active", "changed_at": "2026-03-15T15:00:00Z", "note": null }
  ],
  "result": {
    "position_before": 45,
    "position_after": 12,
    "actual_quantity": 7
  }
}
```

**Errors:** 404 PROMOTION_NOT_FOUND

---

### DELETE /promotions/{id}/cancel

Мягкая отмена. Только для `pending`.

**Логика:**
1. IDOR check
2. Если status != pending → 409 CANNOT_CANCEL
3. UPDATE campaign SET status = 'cancelled'
4. Возврат средств: UPDATE balance + INSERT refund transaction
5. Вернуть сумму возврата

**Response 200:**
```json
{
  "id": "uuid",
  "status": "cancelled",
  "refund_kopecks": 15000,
  "balance_after_kopecks": 150000
}
```

**Errors:** 404 PROMOTION_NOT_FOUND, 409 CANNOT_CANCEL

---

## §3. Batch (3 endpoints)

### POST /batch/upload

Загрузить Excel. Парсинг асинхронный.

**Request:** `multipart/form-data`, поле `file` (.xlsx, max 5MB).

**Валидация (в порядке):**
1. Content-Type = `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
2. Size <= 5 MB
3. Magic bytes: `PK\x03\x04` (ZIP)
4. Extension: `.xlsx`
5. `openpyxl.load_workbook(read_only=True, data_only=True, keep_vba=False)`
6. Max 11 строк (1 header + 10 data)
7. Санитизация: запрет формул (`=`, `+`, `-`, `@` в начале ячейки), control chars

**Парсинг (синхронный, openpyxl):**
```python
# Ожидаемые заголовки:
HEADERS = ["Артикул", "Маркетплейс", "Ключевое слово", "Количество", "Кешбэк (₽)"]

# Для каждой строки:
# - article: str, required, max 50
# - marketplace: "WB" | "Ozon", required
# - keyword: str, required, max 100
# - quantity: int, 1-50, required
# - cashback: float → *100 → int kopecks, optional
```

**Логика:**
1. Валидировать файл
2. Создать `batch_jobs` запись со статусом `pending`
3. Распарсить Excel (openpyxl)
4. Для каждой строки: валидировать поля, создать `batch_items` записи
5. Собрать ошибки в `parse_errors` JSONB
6. Подсчитать `estimated_cost_kopecks` (sum of row costs)
7. Обновить статус на `preview` (если есть хотя бы 1 valid row) или `failed`

**Response 202:**
```json
{
  "job_id": "uuid",
  "status": "parsing"
}
```

**Errors:** 400 INVALID_FILE_TYPE, 400 FILE_TOO_LARGE, 400 INVALID_FILE_FORMAT, 400 TOO_MANY_ROWS, 400 FORMULA_INJECTION, 400 CORRUPTED_FILE

---

### GET /batch/{job_id}

Статус + preview данные.

**Логика:** SELECT job + items + errors. IDOR check.

**API status mapping:**
- DB `pending`/`parsed` → API `parsing`
- DB `preview` → API `preview_ready`
- DB `failed` → API `error`
- DB `confirmed` → API `queued`
- DB `processing` → API `launching`
- DB `completed` → API `done`

**Response 200:**
```json
{
  "job_id": "uuid",
  "status": "preview_ready",
  "items": [
    {
      "row": 2,
      "article": "12345678",
      "marketplace": "WB",
      "keyword": "кроссовки мужские",
      "quantity": 5,
      "cashback_kopecks": 15000,
      "scheduled_at": null,
      "promotion_id": null
    }
  ],
  "errors": [
    { "row": 4, "field": "quantity", "message": "Количество должно быть числом от 1 до 50" }
  ],
  "summary": {
    "total_rows": 10,
    "valid_rows": 8,
    "error_rows": 2,
    "estimated_cost_kopecks": 120000
  }
}
```

**Errors:** 404 JOB_NOT_FOUND

---

### POST /batch/{job_id}/confirm

Подтвердить и запустить. Только при `status=preview_ready` и `error_rows=0`.

**Логика:**
1. IDOR check
2. Если status != preview → 409 JOB_NOT_READY
3. Если error_rows > 0 → 400 BATCH_HAS_ERRORS
4. Рассчитать total cost
5. **Атомарно:** списать баланс + создать кампании + назначить jitter `scheduled_at` + INSERT transactions
6. Обновить batch_items: `status='scheduled'`, `scheduled_at = NOW() + random(0, jitter_max_hours)`
7. Обновить batch_job: `status='confirmed'`

**Response 200:**
```json
{
  "job_id": "uuid",
  "status": "queued",
  "promotions": [
    { "id": "uuid", "article": "12345678", "scheduled_at": "2026-03-16T02:30:00Z" }
  ],
  "total_cost_kopecks": 120000,
  "balance_after_kopecks": 30000
}
```

**Errors:** 404 JOB_NOT_FOUND, 409 JOB_NOT_READY, 402 INSUFFICIENT_BALANCE, 400 BATCH_HAS_ERRORS

---

## §4. Balance (2 endpoints)

### GET /balance

Баланс + история транзакций.

**Query:** `page` (default 1), `per_page` (default 20, max 100).

**Response 200:**
```json
{
  "balance_kopecks": 150000,
  "transactions": [
    {
      "id": "uuid",
      "type": "topup",
      "amount_kopecks": 500000,
      "balance_after_kopecks": 500000,
      "description": "Пополнение",
      "created_at": "2026-03-14T14:30:00Z",
      "idempotency_key": "webhook:pay_xxx"
    }
  ],
  "total": 5,
  "page": 1,
  "per_page": 20,
  "has_next": false
}
```

---

### POST /balance/topup

Создать платёж через YuKassa. Возвращает URL для редиректа.

**Request:**
```json
{ "amount_kopecks": 500000 }
```

**Валидация:** min 10000 (100₽), max 1000000000 (10M₽).

**YuKassa интеграция:**
```python
import yookassa
from yookassa import Payment

yookassa.Configuration.account_id = YUKASSA_SHOP_ID
yookassa.Configuration.secret_key = YUKASSA_SECRET_KEY

payment = Payment.create({
    "amount": {
        "value": str(amount_kopecks / 100),  # YuKassa принимает рубли
        "currency": "RUB"
    },
    "confirmation": {
        "type": "redirect",
        "return_url": f"{YUKASSA_RETURN_URL}?payment_id={payment_id}"
    },
    "capture": True,
    "description": f"Пополнение баланса Dowry (seller: {seller_id})",
    "metadata": {
        "seller_id": str(seller_id)
    }
})
```

**Response 200:**
```json
{
  "payment_id": "pay_xxx",
  "confirmation_url": "https://yoomoney.ru/checkout/...",
  "expires_at": "2026-03-14T15:30:00Z"
}
```

**Errors:** 400 AMOUNT_TOO_SMALL, 400 AMOUNT_TOO_LARGE, 503 PAYMENT_PROVIDER_UNAVAILABLE

---

## §5. Profile (2 endpoints)

### GET /profile

**Response 200:**
```json
{
  "seller_id": "uuid",
  "phone": "+79001234567",
  "name": "Иван Иванов",
  "company": {
    "inn": "7707083893",
    "name": "ООО \"Рога и Копыта\"",
    "legal_form": "ООО",
    "enriched_at": "2026-03-14T10:00:00Z"
  },
  "created_at": "2026-03-01T00:00:00Z",
  "marketplace_accounts": [
    { "marketplace": "WB", "seller_name": "Магазин Nike", "added_at": "2026-02-14T00:00:00Z" }
  ]
}
```

`company` = null если ИНН не указан. `enriched_at` = null если DaData ещё не ответил.

---

### PUT /profile

**Request:**
```json
{ "name": "Иван Иванов", "inn": "7707083893" }
```

**Логика:**
1. Валидация: name max 100, inn regex `^\d{10}(\d{2})?$`
2. Если INN изменился:
   - Проверить INN checksum (стандартный алгоритм)
   - Проверить уникальность (другой seller с таким INN → 422 INN_ALREADY_USED)
   - **Асинхронно** запросить DaData (не блокировать response):
     ```python
     # Background task (FastAPI BackgroundTasks)
     async def enrich_company(seller_id: str, inn: str):
         async with httpx.AsyncClient() as client:
             resp = await client.post(
                 "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
                 json={"query": inn},
                 headers={"Authorization": f"Token {DADATA_API_KEY}"},
             )
             data = resp.json()
             # UPDATE seller_companies SET name=..., legal_form=..., enriched_at=NOW()
     ```
3. UPDATE seller + company
4. Вернуть обновлённый профиль

**Response 200:** `SellerProfileResponse` (полный профиль после обновления)

**Errors:** 400 VALIDATION_ERROR, 400 INVALID_INN (checksum), 422 INN_ALREADY_USED

---

## §6. Health

### GET /health

Без auth. Для мониторинга и smoke tests.

**Response 200:**
```json
{
  "status": "ok",
  "db": "ok",
  "overdue_items": 0,
  "scheduled_items": 15,
  "worker_last_heartbeat": "2026-03-14T14:29:00Z"
}
```

**Response 503:** если `db: "error"`.

---

## §7. YuKassa Webhook

### POST /webhooks/yukassa

Отдельный endpoint (НЕ в `/api/seller/v1/`). Без seller auth — проверяется HMAC-SHA256 подпись.

**Логика:**
1. Проверить `X-YuKassa-Signature` header (HMAC-SHA256 с `YUKASSA_SECRET_KEY`)
2. Если подпись невалидна → 403
3. Достать `payment_id`, `status`, `amount`, `metadata.seller_id`
4. Если status == "succeeded":
   - `amount_kopecks = int(float(amount.value) * 100)`
   - **Идемпотентно:** INSERT transaction с `idempotency_key = "webhook:{payment_id}"` + `ON CONFLICT DO NOTHING`
   - UPDATE `seller_balances` SET `available_kopecks += amount_kopecks`
5. Ответить 200 (YuKassa at-least-once delivery — всегда 200 при обработке)

---

## §8. Batch Worker (Background)

Отдельный процесс (или FastAPI BackgroundTask), не endpoint. Запускает кампании из confirmed batch.

**Логика:**
```python
# Каждые 30 секунд:

# 1. Heartbeat
UPDATE worker_heartbeats SET last_seen_at = NOW(), items_processed += N
WHERE worker_id = $worker_id;

# 2. Захватить готовые items (crash-safe)
SELECT id, sku, keyword, ... FROM batch_items
WHERE status = 'scheduled' AND scheduled_at <= NOW()
ORDER BY scheduled_at
LIMIT 5
FOR UPDATE SKIP LOCKED;

# 3. Обработать каждый item
UPDATE batch_items SET status = 'claimed', claimed_at = NOW() WHERE id = $id;
# → Создать campaign (существующая логика AwardyBot)
UPDATE batch_items SET status = 'launched', campaign_id = $campaign_id WHERE id = $id;

# 4. Watchdog: reset застрявших items (claimed > 10 мин назад)
UPDATE batch_items SET status = 'scheduled', claimed_at = NULL
WHERE status = 'claimed' AND claimed_at < NOW() - INTERVAL '10 minutes';

# 5. Проверить batch completion
UPDATE batch_jobs SET status = 'completed', completed_at = NOW()
WHERE id = $batch_job_id
AND NOT EXISTS (SELECT 1 FROM batch_items WHERE batch_job_id = $id AND status IN ('pending','scheduled','claimed'));
```

---

## Rate Limiting (Nginx)

```nginx
# В http {} блоке nginx.conf
limit_req_zone $binary_remote_addr zone=otp_request:10m rate=2r/m;
limit_req_zone $binary_remote_addr zone=otp_verify:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=api_general:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=upload:10m rate=5r/m;

# В server {} блоке
location /api/seller/v1/auth/send-otp {
    limit_req zone=otp_request burst=3 nodelay;
    proxy_pass http://127.0.0.1:8000;
}

location /api/seller/v1/auth/verify-otp {
    limit_req zone=otp_verify burst=5 nodelay;
    proxy_pass http://127.0.0.1:8000;
}

location /api/seller/v1/batch/upload {
    limit_req zone=upload burst=2 nodelay;
    client_max_body_size 5m;
    proxy_pass http://127.0.0.1:8000;
}

location /api/seller/ {
    limit_req zone=api_general burst=20 nodelay;
    proxy_pass http://127.0.0.1:8000;
}
```

---

## Карта endpoints (summary)

```
/api/seller/v1/
  auth/
    POST send-otp          # без auth, rate: otp_request
    POST verify-otp        # без auth, rate: otp_verify
    POST refresh           # refresh_token cookie
    POST logout            # access_token cookie
    GET  me                # access_token cookie
  promotions/
    GET  /                 # список, пагинация, фильтр
    POST /                 # создать (атомарное списание)
    GET  /{id}             # детали + history + result
    DELETE /{id}/cancel    # мягкая отмена (только pending)
  batch/
    POST upload            # multipart .xlsx, rate: upload
    GET  /{job_id}         # статус + preview
    POST /{job_id}/confirm # подтвердить (атомарное списание)
  balance/
    GET  /                 # баланс + транзакции
    POST topup             # → YuKassa redirect URL
  profile/
    GET  /                 # профиль + компания
    PUT  /                 # обновить (DaData async)
  health                   # без auth

/webhooks/
  POST yukassa             # HMAC-SHA256, не в /api/seller/
```

---

## Порядок реализации

| Sprint | Что | Endpoints | Таблицы | Зависимость |
|--------|-----|-----------|---------|-------------|
| **0** | Pre-conditions | — | verify sellers.id | — |
| **1** | Auth | 5: send-otp, verify-otp, refresh, logout, me | 3: auth_methods, otp_codes, sessions | SMSC.ru key |
| **2** | Balance + Topup | 2: get, topup + webhook | 2: balances, transactions | YuKassa credentials |
| **3** | Promotions | 4: list, create, get, cancel | 1: campaign_results | Sprint 2 (balance check) |
| **4** | Batch | 3: upload, status, confirm + worker | 2: batch_jobs, batch_items | Sprint 3 (create promotion) |
| **5** | Profile | 2: get, update | 1: companies | DaData key |
| **6** | Health + Nginx | 1: health + rate limits | 1: worker_heartbeats | Sprint 4 (worker) |

**Параллелизм:** Sprint 1 (auth) блокирует всё. После Sprint 1 можно делать Sprint 2+5 параллельно.

---

## Tests (рекомендуемые)

| # | Что тестировать | Тип | Приоритет |
|---|----------------|-----|-----------|
| 1 | OTP rate limit (3/10min) | unit | P0 |
| 2 | OTP timing-safe compare | unit | P0 |
| 3 | IDOR: seller A не видит promotion seller B | integration | P0 |
| 4 | Атомарное списание баланса (concurrent) | integration | P0 |
| 5 | Balance не уходит в минус (CHECK constraint) | unit | P0 |
| 6 | YuKassa webhook idempotency (duplicate) | integration | P0 |
| 7 | Batch Excel: formula injection blocked | unit | P0 |
| 8 | Batch Excel: >10 rows rejected | unit | P1 |
| 9 | Refresh token rotation + reuse detection | integration | P1 |
| 10 | DaData enrichment async (не блокирует PUT) | integration | P1 |
| 11 | Worker crash recovery (claimed_at watchdog) | integration | P1 |
| 12 | Cookie params (HttpOnly, Secure, SameSite) | integration | P1 |

---

## Зависимости (pip)

```
# Новые (добавить в requirements.txt):
PyJWT>=2.8            # JWT encode/decode
openpyxl>=3.1         # Excel parsing (read_only mode)
yookassa>=3.0         # YuKassa SDK
httpx>=0.27           # Async HTTP (SMSC, DaData)

# Существующие (уже в awardybot):
fastapi
sqlalchemy[asyncio]
alembic
pydantic>=2
```

---

## Ссылки

- **API контракты (полные):** `ai/blueprint/system-blueprint/api-contracts.md`
- **DB схема (полный SQL):** `ai/blueprint/system-blueprint/data-architecture.md`
- **Cross-cutting правила:** `ai/blueprint/system-blueprint/cross-cutting.md`
- **Domain map:** `ai/blueprint/system-blueprint/domain-map.md`
- **Frontend спеки:** FTR-0021 (auth), FTR-0022 (layout), FTR-0023 (promotions), FTR-0024 (balance), FTR-0025 (batch), FTR-0026 (profile)
