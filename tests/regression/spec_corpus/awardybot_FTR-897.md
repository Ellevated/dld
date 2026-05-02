# FTR-897 — External Traffic Onboarding MVP

**Status:** done (Task 11 catch-up завершён 2026-05-02 — v2 endpoints /onboarding/consent, /onboarding/event, /admin/onboarding/attribution реализованы per ADR-016)

> **2026-05-01 unblocked:** baseline ruff зелёный (commit `2d652cff`, 13 errors fixed: 11 auto + 2 manual — F841 unused var, SIM117 nested with). Готов к autopilot.
**Priority:** P1
**Date:** 2026-05-01
**Effort:** ~$8-10, 4-6 дней (probation удалён по решению founder 2026-05-01 — см. `memory/feedback_no_probation_state.md`)
**Decision mode:** council (synthesis: `ai/.council/20260501-external-traffic-onboarding/synthesis.md`) + founder review delta 2026-05-01
**Blueprint reference:** `ai/blueprint/system-blueprint/` + buyer domain rules (`.claude/rules/domains/buyer.md`)
**Related future work:** `ai/inbox/creator-onboarding-flow.md` (creator branch — schema должна быть extensible, см. Architectural Compliance)

---

## Problem

Awardy планирует платный трафик внешних байеров через таргетированные посевы. Сейчас `/start` не отличает органических пользователей от service-трафика — нет ни выделенного welcome-флоу, ни атрибуции источника, ни базовой anti-fraud защиты.

Разрывы:
- Нет `phone_hash UNIQUE` → один человек × N TG-аккаунтов = N байер-строк, легально обходит phone-deduplication
- Нет явного 152-ФЗ consent → обработка PII без согласия = штраф РКН 60-100K (ст. 9)
- Нет `acquisition_source` → непонятно, какие каналы (TG Ads / Яндекс / блогер) приносят завершённых байеров
- Нет audit log → botnet-атака невидима до понедельника, нет repudiation defense, нет funnel-аналитики
- Нет welcome-копирайта под Personas из платного трафика → высокий drop-off на screen 1

**Kill question:** без этой фичи первый же рекламный посев с 100+ регистрациями = слепое сжигание CAC + юр. риск по 152-ФЗ.

**Note (founder decision 2026-05-01):** probation state (24h cooling period перед accept_slot) — НЕ берём, founder reject. Конверсия > anti-fraud floor для запуска. Re-evaluate после первого fraud-инцидента (см. `memory/feedback_no_probation_state.md`).

---

## Scope

**Включено (Phase 1 — bot-only):**
- Service deep-link ветка в `parse_deep_link()` + `cmd_start` if-branch
- Screen 1+2+3 copy в `src/domains/buyer/locales/ru.yaml` (founder-provided 2026-05-01 — см. секцию Localization)
- Миграции: `buyers.phone_hash`, `buyers.acquisition_source`
- `onboarding_events` lightweight audit log + index `(ref_source, ts)`
- `consents` table (новая) + 152-ФЗ explicit non-pre-checked consent на screen 3
- Phone hash collision UX: deeplink на `cmd_start` без service-ветки
- Empty-state CTA к FTR-872 morning digest
- Сохранение `acquisition_source` в `get_or_create_buyer()`
- **API v2 endpoints с первого дня** для всех новых данных (consent, onboarding_event, acquisition_source) — см. Task 11

**Исключено (строго out of scope):**
- **Probation state** (founder reject 2026-05-01 — конверсия > anti-fraud floor; re-evaluate после первого fraud-инцидента)
- Approach 2/3, MiniApp landing/видео
- HMAC signed ref-source tokens
- Автоматический velocity checker (только manual SQL для первых 100 регистраций)
- Behavioral fraud detection / TG account age heuristics
- Категории интересов / segments
- 5-экранный FSM (сжато до 3)
- Live DB aggregates trust-block (статичные числа в ru.yaml, обновляются вручную ~раз в месяц)
- Retention policy / GDPR delete endpoint для `onboarding_events` / `consents`
- Attribution Analytics Baseline (Спека 2 — после 50 регистраций, отдельный FTR)
- **Creator-onboarding** branch (см. `ai/inbox/creator-onboarding-flow.md` — отдельная архитектурная дискуссия)

---

## Approaches

### Approach 1 (SELECTED by Council — unanimous)

**Bot-only `/start service` как Phase 1.**

- Расширить `parse_deep_link()` существующей веткой `src_<channel>` + добавить branch `service` (или `src_service`)
- if-branch в `cmd_start`: `is_new AND source IS NOT NULL AND no offer_id` → service onboarding flow (screen 1→2→3)
- Existing users через service deep-link → обычный menu (не повторный онбординг)
- НЕ создавать новый парсер / новый сервис / новые файлы (если `onboarding.py` ≤ 400 LOC)

**Rationale:**
1. Не блокируется на FTR-887/889 (queued, не раскатаны)
2. R2 (contained) — минимальный blast radius
3. Identity infrastructure уже на месте (FTR-846 + FTR-886)
4. Валидация экономики за 5-7 дней vs 3-4 недели

### Approach 2 (DEFERRED)

MiniApp landing + video demo. После 100 регистраций И раскатки FTR-889. Отдельная спека.

### Approach 3 (DEFERRED)

Двухступенчатый bot→miniapp с HMAC ref-tokens. После первого fraud-инцидента или 500 регистраций.

---

## Implementation Plan

> **Plan validated:** 2026-05-01 (Plan agent). Confirmed paths/anchors against current codebase. See `## Plan Validation Notes` at the end of this section for the full diff.

### Task 1 — Миграция `phone_hash` + `acquisition_source`

**File:** `supabase/migrations/20260501120001_ftr897_buyer_onboarding_columns.sql`

> Корректный путь миграций — `supabase/migrations/` (не `db/migrations/` — такой папки в репо нет). Последняя миграция в репо — `20260430150000_887_buyer_sessions_cleanup.sql`, поэтому используем префикс `20260501`.

```sql
-- phone_hash: SHA-256 хэш телефона, UNIQUE WHERE NOT NULL
ALTER TABLE buyers ADD COLUMN IF NOT EXISTS phone_hash TEXT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_buyers_phone_hash
    ON buyers (phone_hash)
    WHERE phone_hash IS NOT NULL;

-- acquisition_source: канал привлечения
ALTER TABLE buyers ADD COLUMN IF NOT EXISTS acquisition_source TEXT NULL;
```

**ADR-018 note:** `CREATE INDEX ... WHERE` в partial index — вне транзакции если нужен CONCURRENTLY. `phone_hash IS NOT NULL` использует только IMMUTABLE операторы — safe.

**Removed (founder decision 2026-05-01):** `probation_until_at TIMESTAMPTZ NULL` исключён из миграции. Re-evaluate после первого fraud-инцидента.

### Task 2 — Миграция `onboarding_events` audit log

**File:** `supabase/migrations/20260501120002_ftr897_onboarding_events.sql`

```sql
CREATE TABLE IF NOT EXISTS onboarding_events (
    id BIGSERIAL PRIMARY KEY,
    buyer_id UUID NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    ref_source TEXT,
    ip_hash TEXT,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_onboarding_events_ref_source_ts
    ON onboarding_events (ref_source, ts);
```

Один INSERT per шаг онбординга. Без retention policy. Velocity check: `SELECT COUNT(*) WHERE ref_source=X AND ts > NOW()-INTERVAL '1 hour' > 50` → alert в MC group (`notify_ops`).

### Task 3 — 152-ФЗ consent table

**Validation result (2026-05-01):** `rules_acceptance_logs` НЕ существует ни в `supabase/migrations/`, ни в `src/`. Создаём `consents` с нуля.

```sql
CREATE TABLE IF NOT EXISTS consents (
    id BIGSERIAL PRIMARY KEY,
    buyer_id UUID NOT NULL REFERENCES buyers(id) ON DELETE CASCADE,
    version TEXT NOT NULL,          -- версия оферты, напр. "2026-05-01"
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip_hash TEXT,                   -- SHA-256 IP для аудита
    ua_hash TEXT,                   -- SHA-256 user-agent (если доступен)
    consent_type TEXT NOT NULL DEFAULT 'personal_data'
);
CREATE INDEX IF NOT EXISTS idx_consents_buyer ON consents (buyer_id);
```

**File:** `supabase/migrations/20260501120003_ftr897_consents.sql`

### Task 4 — `Buyer` model + `BuyerUpdate` (models.py)

**File:** `src/domains/buyer/models.py`

Подтверждено (2026-05-01): класс `Buyer` начинается на строке 22, `BuyerUpdate` — на строке 80. Добавить блок после `is_test: bool = False` в `Buyer` (после строки 67) и аналогично в конце `BuyerUpdate` (после строки 102).

Добавить в `Buyer` (после `is_test`):
```python
# External traffic onboarding (FTR-897)
phone_hash: str | None = None
acquisition_source: str | None = None
```

Добавить в `BuyerUpdate` (после `is_test`):
```python
phone_hash: str | None = None
acquisition_source: str | None = None
```

**Note:** `probation_until_at` НЕ добавляется (founder decision 2026-05-01).

### Task 5 — `buyers_repo` расширения

**File:** `src/domains/buyer/repositories/buyers.py` (текущий LOC = 360, headroom есть)

a) `get_or_create_buyer()` (handler в `onboarding.py:40-61`) — принимает новый kwarg `acquisition_source: str | None = None`, передаёт в `buyers_repo.create()` ТОЛЬКО когда `is_new=True`. Существующие байеры не перезаписываются.

b) `buyers_repo.create()` (текущая сигнатура `buyers.py:70-115`) — расширить kwargs `acquisition_source: str | None = None`. В блоке `data = {...}` (строки 96-106) добавить ключ `"acquisition_source": acquisition_source`.

c) Новый метод `get_by_phone_hash(phone_hash: str) -> Buyer | None` — добавить рядом с `get_by_tg_id()` (после строки 68). Запрос `.eq("phone_hash", phone_hash).is_("archived_at", "null")`.

d) `finalize_onboarding()` (текущая сигнатура `buyers.py:188-226`) — **без изменений**. Probation logic удалён по решению founder 2026-05-01. Сервисные байеры завершают онбординг в `status='active'` без cooling period. Atribution и phone_hash сохраняются через `BuyerUpdate` в Tasks 5b/7.

### Task 6 — `parse_deep_link()` + `cmd_start` service-branch + новый `onboarding_service.py`

**Files:**
- `src/domains/buyer/handlers/onboarding.py` (текущий LOC = 439, УЖЕ выше лимита 400)
- `src/domains/buyer/handlers/onboarding_service.py` (НОВЫЙ — service-flow handlers)

**Validation result (2026-05-01):** `onboarding.py` сейчас 439 строк, превышает 400-LOC лимит ДО любых изменений. Поэтому новые service-handlers создаём СРАЗУ в отдельном файле `onboarding_service.py` (по образцу `onboarding_blogger.py` per TECH-791) — не ждём LOC-триггера.

`parse_deep_link()` (текущая реализация — `onboarding.py:64-81`) уже корректно обрабатывает `src_<value>` → `result["source"] = value`. Минимальное изменение — оставить функцию как есть и читать `deep_link["source"]` в `cmd_start`.

В `cmd_start` (`onboarding.py:187-250`), в ветке `if is_new or buyer.status.value in ("onboarding", "pending"):` (строки 220-230) добавить branching:

```python
if is_new or buyer.status.value in ("onboarding", "pending"):
    is_service = bool(deep_link.get("source"))

    if is_service:
        # FTR-897: External traffic — delegate to service onboarding module
        from src.domains.buyer.handlers.onboarding_service import (
            start_service_onboarding,
        )
        # buyer уже создан выше в get_or_create_buyer; передаём acquisition_source
        await start_service_onboarding(message, state, buyer, deep_link)
        return

    # Existing organic flow (без изменений)
    await state.set_state(BuyerStates.onboarding_phone)
    await state.update_data(deep_link=deep_link)
    sent = await _send_onboarding_photo(...)
    await state.update_data(onboarding_msg_ids=[sent.message_id])
```

**Доп. правило:** `get_or_create_buyer()` в `onboarding.py:40-61` принимает kwarg `acquisition_source` и передаёт в `buyers_repo.create()` ТОЛЬКО для `is_new=True` (см. Task 5).

`onboarding_service.py` владеет:
- `service_router = Router(name="onboarding_service")`
- `start_service_onboarding(message, state, buyer, deep_link)` — entrypoint screen 1
- handlers screen 1 → 2 → consent → phone (merge в существующий `BuyerStates.onboarding_phone`)
- helper `_insert_onboarding_event(buyer_id, step, ref_source)` — fire-and-forget INSERT

```python
async def _insert_onboarding_event(
    buyer_id: UUID, step: str, ref_source: str | None
) -> None:
    """Fire-and-forget INSERT into onboarding_events. Never raise."""
```

**Router wiring:** `src/domains/buyer/handlers/__init__.py` — `get_buyer_router()` инклюдит все sub-роутеры (см. `buyer.md` "18 handler routers"). Добавить `service_router` в порядке `onboarding_router → onboarding_service_router → ...`. `src/api/telegram/buyer_bot.py:274` уже использует `get_buyer_router()`, отдельных правок не требуется.

**Запрет:** НЕ импортировать `seller.conversations_repo` в `onboarding_service.py` (избегаем legacy upstream-смелл из `onboarding.py:28`). Если нужен лог диалога — только `buyer.conversation_logs_repo`.

**Локали:** `t()` импортируется из `src.domains.buyer.locales` (подтверждено: `onboarding.py:25`). YAML-файл — `src/domains/buyer/locales/ru.yaml` (parent ключ `onboarding:` на строке 25). Все новые ключи добавляются в `onboarding.service.*` (см. секцию Localization ниже).

### Task 7 — Phone hash + collision UX

**File:** `src/domains/buyer/handlers/onboarding.py` (в `_process_phone()` — текущий блок `onboarding.py:434-468`)

Точка вставки: ДО существующего `await buyers_repo.update(buyer.id, BuyerUpdate(sbp_phone=phone))` (строка 449). Логика применяется ко ВСЕМ phone-flow путям (organic + service), потому что `_process_phone` — общий handler.

```python
import hashlib

phone_hash = hashlib.sha256(phone.encode()).hexdigest()

# FTR-897: Check phone uniqueness across all buyers
existing = await buyers_repo.get_by_phone_hash(phone_hash)
if existing and existing.id != buyer.id:
    # Collision: same phone, different buyer → ask user to use existing account
    await message.answer(t("onboarding.service.phone_collision"))
    return  # do NOT advance FSM, do NOT save phone

# Save phone + hash atomically (single update call)
await buyers_repo.update(
    buyer.id,
    BuyerUpdate(sbp_phone=phone, phone_hash=phone_hash),
)
```

`t("onboarding.service.phone_collision")` — текст founder copy (placeholder "Номер уже зарегистрирован — войти?" до утверждения).

> **Note:** `BuyerUpdate.phone_hash` будет добавлено в Task 4. До этого тест EC-3/EC-4 не проходит — Task 4 идёт ДО Task 7 в TDD order.

### Task 8 — 152-ФЗ consent screen (Screen 3)

Screen 3 — перед phone share для service flow. Explicit checkbox (НЕ pre-checked).

- FSM state: `BuyerStates.onboarding_service_consent`
- Keyboard: кнопка "Согласен с обработкой персональных данных [ссылка]" (callback `service:consent_accept`)
- БЕЗ pre-checked состояния — callback НЕ отправляется автоматически
- Handler `cb_service_consent_accept`:
  1. INSERT в `consents` (buyer_id, version="2026-05-01", ip_hash=sha256(message.from_user.id))
  2. INSERT в `onboarding_events` step="consent_given"
  3. Advance FSM → `BuyerStates.onboarding_phone`

**Нарушение 152-ФЗ если:** checkbox pre-checked, consent не записан до обработки PII.

### Task 9 — REMOVED (founder decision 2026-05-01)

Probation reject в `confirm_ugc_choice()` удалён из scope. Сервисные байеры могут принимать слоты без cooling period. Re-evaluate после первого fraud-инцидента или 500 регистраций.

### Task 10 — Empty-state CTA к FTR-872

Когда pool пуст после service онбординга → показывать CTA "Подписаться на новые слоты" — тогл к `FTR-872` morning digest. Новый механизм не создавать — использовать существующий `PATCH /api/v2/buyer/profile` или toggle-метод из FTR-872.

### Task 11 — API v2 endpoints для нового onboarding-data (drift prevention)

**Founder requirement (2026-05-01):** все новые поля/таблицы доступны через v2 с первого дня — чтобы miniapp/web-клиенты не дрифтили относительно bot-flow.

**Files:** `src/api/v2/buyer/onboarding.py` (новый, ~150 LOC) + регистрация в `src/api/v2/buyer/__init__.py`

#### 11a. `submit_consent_impl(actor, request) -> Result[ConsentResponse, OnboardingError]`

Pure-function в `src/api/v2/buyer/onboarding.py`. Принимает `ConsentSubmitRequest(version, ip_hash, ua_hash)`. Записывает в `consents` table. Возвращает `ConsentResponse(consent_id, accepted_at)`.

Bot-handler (Task 8) — тонкий адаптер: вызывает `submit_consent_impl(actor, req).model_dump(mode='json')` (per ADR-016).

#### 11b. `record_onboarding_event_impl(actor, request) -> Result[OnboardingEventResponse, OnboardingError]`

Принимает `OnboardingEventCreate(step, ref_source, ip_hash)`. Fire-and-forget INSERT в `onboarding_events`. Возвращает `OnboardingEventResponse(event_id, ts)`.

Bot-handler (`_insert_onboarding_event` helper из Task 6) — вызывает этот impl. Не raise при ошибке — log + continue (audit log не должен ронять онбординг).

#### 11c. `get_acquisition_attribution_impl(actor) -> Result[AcquisitionResponse, OnboardingError]`

Read-only endpoint для admin/MC. Возвращает `acquisition_source × finalize_rate` aggregate. Используется в Спеке 2 (Attribution Analytics Baseline) — но pure-function `*_impl` уже есть с первого дня, чтобы не делать вторую миграцию для admin UI.

#### 11d. Pydantic типы

Новые модели в `src/api/v2/buyer/onboarding.py`:
- `ConsentSubmitRequest`, `ConsentResponse`
- `OnboardingEventCreate`, `OnboardingEventResponse`
- `AcquisitionResponse(items: list[AcquisitionRow], total_buyers: int)`
- `OnboardingError` enum: `INVALID_VERSION`, `BUYER_NOT_FOUND`, `INTERNAL`

#### 11e. Routes (FastAPI)

```
POST /api/v2/buyer/onboarding/consent          → submit_consent_impl
POST /api/v2/buyer/onboarding/event            → record_onboarding_event_impl
GET  /api/v2/admin/onboarding/attribution      → get_acquisition_attribution_impl  (admin auth)
```

JWT auth для buyer-endpoints (per ADR-017 — human actors). X-Admin-Key для admin-endpoint.

**Why this matters:** когда miniapp/web подключатся через FTR-889 — не нужно будет писать вторую реализацию consent/audit-log. Эти endpoints живут с первого коммита.

---

## Plan Validation Notes (2026-05-01)

Plan agent re-read all Allowed Files и сверил с текущим кодом. Diff vs. оригинальная спека:

| # | Path / anchor in spec | Корректировка | Reason |
|---|-----------------------|----------------|--------|
| 1 | `db/migrations/` | → `supabase/migrations/` | Папки `db/migrations/` нет в репо. Все миграции живут в `supabase/migrations/`. |
| 2 | `YYYYMMDDHHMMSS_*.sql` префикс | → `20260501120001..03_ftr897_*.sql` | Последняя миграция в репо — `20260430150000_887_buyer_sessions_cleanup.sql`. Берём `20260501` + слоты `120001/120002/120003`. |
| 3 | Task 3 — `rules_acceptance_logs` | "Не существует, создаём `consents` с нуля" | `grep` в `supabase/migrations/` и `src/` — 0 совпадений (упоминания только в docs/синтезе). |
| 4 | Task 4 — anchor lines | `Buyer` class @ line 22, `BuyerUpdate` @ line 80 | Файл `src/domains/buyer/models.py` содержит ровно эти поля + `is_test`, `datetime` уже импортирован. |
| 5 | Task 5 — `buyers_repo` LOC | 360 LOC, headroom есть | Файл уверенно ≤ 400, расширение безопасно. |
| 6 | Task 5 — `create()` signature | `create(tg_id, tg_username=None, first_name=None, last_name=None)` (строки 70-76) | Текущая сигнатура без `acquisition_source` — расширяем kwarg. |
| 7 | Task 5 — `finalize_onboarding()` signature | `finalize_onboarding(self, tg_id: int) -> Buyer` (строки 188-226) | Текущая сигнатура без `is_service_source` — расширяем `keyword-only`. |
| 8 | Task 6 — `onboarding.py` LOC | **439 LOC** (УЖЕ > 400 лимит) | Spec говорил "если превысит 400 → вынести в `onboarding_service.py`". Превысил ДО изменений → создаём `onboarding_service.py` upfront. |
| 9 | Task 6 — anchor lines | `parse_deep_link` @ 64-81, `cmd_start` @ 187-250, `_process_phone` @ 434-468, `_send_onboarding_photo` @ 163-181 | Все четыре функции присутствуют, сигнатуры совпадают со спекой. |
| 10 | Task 6 — router wiring | `get_buyer_router()` в `src/domains/buyer/handlers/__init__.py`; `buyer_bot.py:274` уже инклюдит | Добавляем `service_router` в `__init__.py`, `buyer_bot.py` менять не нужно. |
| 11 | Task 7 — `_process_phone` insertion point | Перед `buyers_repo.update(...)` на строке 449 | Подтверждённое место. |
| 12 | Task 9 — `confirm_ugc_choice` insertion point | Между trust check (стр. 70-79) и `client.rpc("claim_slot", ...)` (стр. 84) | `buyer` уже получен на строке 52 — повторный fetch не нужен. |
| 13 | Task 9 — `from src.shared.time_utils import utc_now` | Подтверждено: `src/shared/time_utils.py:39` | Импорт корректен. |
| 14 | Task 8 — `BuyerStates` location | `src/domains/buyer/states.py:11` (`StatesGroup`) | Существующие onboarding states (lines 25-28). Новые 3 (`onboarding_service_screen1/screen2/consent`) добавляем в группу `=== Onboarding Flow ===`. |
| 15 | ru.yaml path | `src/locales/ru.yaml` → **`src/domains/buyer/locales/ru.yaml`** | Каноничный путь под buyer-доменом, parent `onboarding:` на строке 25. `t()` уже импортирован из `src.domains.buyer.locales` в `onboarding.py:25`. |
| 16 | MCP `*_impl` pattern | Не нужен | Спека не экспозит ни одного MCP/HTTP endpoint — flow целиком aiogram FSM. ADR-016 не применим. |

### Surprises / Risks

- **`onboarding.py` уже превысил 400 LOC до FTR-897** — это надо признать в DoD: после задачи `onboarding.py` НЕ обязан быть ≤ 400, новый код идёт в `onboarding_service.py`. Боюскаут-ребюджирование existing 439 LOC — выходит за scope FTR-897 (см. Upstream Signals: legacy seller import + общий рефактор).
- **Top-level `from src.domains.seller.repositories.conversations import conversations_repo`** в `onboarding.py:28` — продолжает нарушать "lazy imports only" (`buyer.md`). FTR-897 не трогает этот импорт; legacy остаётся для дальнейшего Boy Scout. `onboarding_service.py` создаётся БЕЗ этого импорта.
- **FSM merge на `onboarding_phone`** после consent — означает, что `_process_phone` теперь входная точка для двух разных flow (organic + service). EC-10 проверяет non-regression organic; EC-3/EC-4 проверяют общий phone_hash check. Логика не разветвляется в `_process_phone` — флаг `is_service_source` переходит из FSM data в `finalize_onboarding(is_service_source=True)` через `state.update_data` в `start_service_onboarding`.
- **No drift, no blockers.** Allowed Files и DoD не менял.

---

## FSM States (новые)

| State | Description |
|-------|-------------|
| `BuyerStates.onboarding_service_screen1` | Screen 1 (hero + trust block) |
| `BuyerStates.onboarding_service_screen2` | Screen 2 (mechanics + Persona C filter) |
| `BuyerStates.onboarding_service_consent` | Screen 3 — 152-ФЗ consent checkbox |

После consent → merge в существующий `BuyerStates.onboarding_phone` (единый phone collection flow).

---

## Localization (`src/domains/buyer/locales/ru.yaml`)

**Founder-approved copy (2026-05-01).** Цифры в trust-block — статичные, обновляются founder'ом вручную (~раз в месяц через PR в этот yaml).

Источник цифр: https://awardy.ru (live data на 2026-05-01: 14 853 329 ₽ выплачено, 5 319 покупателей).

Секция `onboarding.service`:

```yaml
onboarding:
  service:
    screen1_hero: |
      🎯 Awardy — выплаты за выкуп товаров на Wildberries

      Как это работает:
      • Берёшь слот → выкупаешь товар на свои
      • Получаешь товар + оставляешь честный отзыв
      • Через 15 дней возвращаем кэшбек на СБП

    screen1_trust_block: |
      ✓ 14 853 329 ₽ уже выплачено покупателям
      ✓ 5 319 человек получают кэшбек через нас
      ✓ Деньги селлера в холде до выплаты тебе

    screen1_cta_details: "Как это работает подробнее"
    screen1_cta_start: "Я готов попробовать →"

    screen2_mechanics: |
      Чтобы не было неожиданностей:

      💸 Нужны свои деньги на выкуп
         От 100 ₽ до 4000 ₽ за товар — оплачиваешь сам, потом возвращаем

      ⏳ Ждать ровно 15 дней
         Кэшбек придёт ПОСЛЕ того, как WB закроет заказ + ты оставишь отзыв.
         Раньше — никак, это правила маркетплейса.

      🤝 Это сотрудничество, не благотворительность
         Кэшбек — это вознаграждение за выполненную работу: выкуп + отзыв + соблюдение условий.
         Деньги не дарим. Платим тем, кто реально помогает селлерам.

    screen2_cta_continue: "Понятно, поехали →"
    screen2_cta_decline: "Это не для меня"

    screen3_consent: |
      Последний шаг — номер телефона

      Зачем: чтобы выплачивать кэшбек на СБП.
      Звонить НЕ будем. Спам не присылаем.

    consent_button: "Согласен с обработкой персональных данных"
    consent_share_phone_button: "📱 Поделиться номером"

    phone_collision: "Этот номер уже зарегистрирован. Войти в существующий аккаунт?"

    empty_state: |
      Сейчас слотов под твой профиль нет 😔

      Они появляются по 3-10 штук в день.
      Включи уведомление — пришлём в первую минуту, как появится.

    empty_state_cta_subscribe: "🔔 Уведомить о новом слоте"
    empty_state_cta_explain: "Что вообще за слоты?"
```

**Note:** Probation UX-сообщение удалено (founder reject 2026-05-01).

---

## Allowed Files

| File | Change |
|------|--------|
| `src/domains/buyer/handlers/onboarding.py` | parse_deep_link уже OK + cmd_start if-branch + _process_phone phone_hash check |
| `src/domains/buyer/handlers/onboarding_service.py` | **NEW** — service-flow handlers (screen 1→2→consent→phone), `_insert_onboarding_event` helper |
| `src/domains/buyer/handlers/__init__.py` | wire new `service_router` в `get_buyer_router()` |
| `src/domains/buyer/models.py` | `phone_hash`, `acquisition_source` поля в Buyer + BuyerUpdate |
| `src/domains/buyer/repositories/buyers.py` | `get_by_phone_hash()`, расширить `create()` (acquisition_source kwarg) |
| `src/domains/buyer/locales/ru.yaml` | секция `onboarding.service.*` (см. Localization) |
| `src/api/v2/buyer/onboarding.py` | **NEW** — `submit_consent_impl`, `record_onboarding_event_impl`, `get_acquisition_attribution_impl` + Pydantic типы |
| `src/api/v2/buyer/__init__.py` | регистрация новых routes |
| `src/api/telegram/buyer_bot.py` | router wiring (если требуется) |
| `supabase/migrations/20260501120001_ftr897_buyer_onboarding_columns.sql` | **NEW** — phone_hash, acquisition_source |
| `supabase/migrations/20260501120002_ftr897_onboarding_events.sql` | **NEW** — audit log table |
| `supabase/migrations/20260501120003_ftr897_consents.sql` | **NEW** — 152-ФЗ consent table |
| `src/locales/ru.yaml` | секция `onboarding.service` |
| `tests/` | новые тесты (см. Eval Criteria) |

**Новые файлы только если `onboarding.py` > 400 LOC после всех изменений.** Тогда → `onboarding_service.py` для service-flow handlers.

---

## Eval Criteria

### EC-1, EC-2 — REMOVED (probation удалён из scope per founder decision 2026-05-01)

### EC-3 (deterministic) — Phone hash collision returns deeplink
`_process_phone()` с телефоном, чей SHA-256 уже есть в `buyers.phone_hash` (другой buyer_id) → возвращает сообщение с `phone_collision` текстом, НЕ сохраняет телефон, НЕ продвигает FSM.
Source: council synthesis P0 #2.

### EC-4 (deterministic) — Phone hash saved on success
`_process_phone()` с уникальным телефоном → `buyers.phone_hash = sha256(phone)` записан в DB вместе с `sbp_phone`.
Source: council synthesis P0 #2.

### EC-5 (deterministic) — Consent checkbox required (not pre-checked)
Service-flow достигает screen 3 → `onboarding_service_consent` FSM state. Продвижение возможно ТОЛЬКО через callback `service:consent_accept`. Нет автоматического перехода без явного клика.
Source: council synthesis P0 #3.

### EC-6 (deterministic) — Consent INSERT before phone collection
После `cb_service_consent_accept` → INSERT в `consents` (или расширенную `rules_acceptance_logs`) с `buyer_id`, `version`, `accepted_at` ДО перехода в `onboarding_phone`.
Source: council synthesis P0 #3, 152-ФЗ ст. 9.

### EC-7 (integration) — onboarding_events INSERT per step
Прохождение service flow (screen1 → screen2 → consent → phone) → 4 строки в `onboarding_events` с `step` соответственно, `ref_source = acquisition_source`, `buyer_id` совпадает.
Source: council synthesis P0 #4.

### EC-8 (deterministic) — Service deep_link routing
`parse_deep_link("src_blogger123")` → `{"offer_id": None, "source": "blogger123", "resume_slot_id": None}`. `parse_deep_link("offer_UUID_src_blogger")` → `{"offer_id": "UUID", "source": "blogger", ...}`. `parse_deep_link("src_service")` → `{"source": "service", ...}`.
Source: codebase analysis, `parse_deep_link()` existing logic.

### EC-9 (integration) — acquisition_source persistence
`get_or_create_buyer(tg_id, ..., acquisition_source="blog_1234")` для нового байера → `buyers.acquisition_source = "blog_1234"` в DB. Для существующего байера — `acquisition_source` не перезаписывается.
Source: council synthesis P1 Architect recommendation.

### EC-10 (deterministic) — Organic /start unaffected
`cmd_start` без параметров (`command.args = None`) → существующий органический flow (state = `onboarding_phone`), service-branch НЕ активируется.
Source: non-regression requirement.

### EC-11 (deterministic) — Existing user via service deeplink → menu
Существующий активный байер приходит через `src_blogger` → показывается menu (`BuyerStates.menu`), НЕ повторный онбординг, НЕ probation.
Source: council synthesis (existing users bypass service flow).

### EC-12 — REMOVED (probation удалён из scope per founder decision 2026-05-01)

---

**TDD Order:**
1. EC-8 (parse_deep_link unit test — нет side effects)
2. EC-3, EC-4 (phone_hash unit tests)
3. EC-5, EC-6 (consent FSM tests)
4. EC-10, EC-11 (non-regression unit tests)
5. EC-7, EC-9 (integration tests против dev DB)

Coverage: 9 active eval criteria (EC-3..EC-11), 6 deterministic + 2 integration. EC-1, EC-2, EC-12 — REMOVED (probation per founder decision).

---

## Top Risks

### Risk 1 — Botnet farms (CRITICAL)
**Likelihood:** medium-high
**Impact:** прямой cashback theft через фермы аккаунтов
**Mitigation:** `phone_hash UNIQUE` (один телефон = один аккаунт) + `onboarding_events` с COUNT-порогом: `SELECT COUNT(*) WHERE ref_source=X AND ts > NOW()-INTERVAL '1 hour' > 50` → `notify_ops()` alert + manual velocity review оператором.
**Note (founder decision 2026-05-01):** `probation_until_at` (24h delay) был частью defense-in-depth по council synthesis, но removed по founder decision (конверсия > anti-fraud floor). Re-evaluate после первого fraud-инцидента — это P2 trigger для возврата probation.

### Risk 2 — 152-ФЗ violation (LEGISLATIVE)
**Likelihood:** 100% без consent
**Impact:** штраф РКН 60-100K руб
**Mitigation:** Explicit НЕ pre-checked checkbox на screen 3 + INSERT в `consents` ДО обработки phone. Нарушение — если форма отправляется без явного клика, или consent не записан в DB.

### Risk 3 — Founder scope creep (PROCESS)
**Likelihood:** high
**Impact:** 4-6 недель вместо 5-7 дней
**Mitigation:** Этот spec — максимум для Phase 1. Approach 2/3 строго заблокированы здесь. Новые файлы только по LOC-триггеру (>400). Approach 2 — только после данных за 100 регистраций.

---

## Architectural Compliance

### ADR-016 — MCP thin adapter
Если появятся MCP endpoints для service flow — тонкий адаптер через `*_impl` pure-function. Прямые DB-вызовы из MCP forbidden.

### ADR-018 — Migrations
`CREATE INDEX` для `phone_hash` partial index — outside transaction если CONCURRENTLY. `WHERE phone_hash IS NOT NULL` использует IS NOT NULL оператор — IMMUTABLE safe (не `now()`).

### ADR-019 — Config-object pattern
`finalize_onboarding(tg_id, is_service_source=False)` — один boolean. НЕ нарушает ADR-019 (порог: ≥2 boolean с defaults). При добавлении второго boolean флага → немедленный переход на `@dataclass(frozen=True)`.

### Imports direction
`shared → infra → domains → api`. `onboarding.py` НЕ импортирует `seller.conversations_repo` в service-ветке — только `buyer.conversation_logs_repo` если нужен лог.

### Architectural Integrity (5 checks per `.claude/rules/architectural-integrity.md`)
1. **DRY:** ✓ `_insert_onboarding_event()` — новый helper без дублирования
2. **SSOT:** ✓ `acquisition_source`, `phone_hash`, `consents` — каждое в одном месте
3. **Imports:** ✓ новые импорты не идут upstream. `onboarding.py` → `buyers_repo` (buyer→buyer, OK)
4. **Boundary:** ⚠️ проверить что `onboarding.py` не тянет `seller.conversations_repo` в service-ветке (существующий top-level import — TODO для buyer domain cleanup, не блокирует FTR-897)
5. **Config:** ✓ нет функций с ≥2 boolean флагами с дефолтами

### Creator-extensibility (forward-looking)
Schema разработана с учётом будущей creator-ветки (см. `ai/inbox/creator-onboarding-flow.md`):
- `acquisition_source TEXT NULL` — generic enough для `creator`, `blogger_<id>`, etc.
- `onboarding_events.payload JSONB` — может расширяться creator-specific полями без миграции
- `consents.consent_type TEXT` — допускает разные типы (152-FZ, creator-agreement, NDA)
- `buyers.role` (будущая колонка для creator/standard) — additive миграция, не ломает текущий контракт

Cross-ref: при работе над creator-onboarding spec → проверить, что эти поля уже могут принять creator-flow без второй миграции.

---

## Definition of Done

- [ ] Миграции применяются на чистую DB без ошибок (`phone_hash` UNIQUE partial, `acquisition_source`, `onboarding_events`, `consents`)
- [ ] `parse_deep_link("src_blogger")` возвращает `source="blogger"` (EC-8)
- [ ] `/start src_blogger` для нового байера → screen 1 (service flow), не органический phone screen
- [ ] `/start src_blogger` для существующего байера → menu (EC-11)
- [ ] `/start` без параметров → органический flow (EC-10)
- [ ] Phone collision → `phone_collision` сообщение без продвижения FSM (EC-3)
- [ ] Phone hash сохранён на success (EC-4)
- [ ] `onboarding_events` содержит строки per step (EC-7)
- [ ] `buyers.acquisition_source` сохранён для новых байеров, не перезаписывается для существующих (EC-9)
- [ ] Consent checkbox — только explicit click, нет pre-checked (EC-5)
- [ ] Consent INSERT в `consents` ДО phone collection (EC-6)
- [ ] API v2 endpoints отдают consent + acquisition (Task 11): `submit_consent_impl`, `record_onboarding_event_impl`, `get_acquisition_attribution_impl`
- [ ] Все 9 активных eval criteria проходят (EC-3..EC-11)
- [ ] Тесты green (TDD order соблюдён)
- [ ] `onboarding.py` ≤ 400 LOC (если превышает → service handlers в `onboarding_service.py`)
- [ ] `ru.yaml` секция `onboarding.service` заполнена (founder copy в Localization)
- [ ] `buyers_repo.py` ≤ 400 LOC
- [ ] Commit на `develop` с тегом `feat(FTR-897):`

---

## Upstream Signals

### LOCAL (process improvement)
Council-driven headless spec creation работает хорошо — synthesis.md содержал всё необходимое для прямого написания спеки без Socratic dialogue. Pattern зафиксировать: для council-решений с synthesis.md → headless mode без вопросов.

### UPSTREAM (blueprint gap)
`src/domains/buyer/handlers/onboarding.py` имеет top-level cross-domain import `from src.domains.seller.repositories.conversations import conversations_repo` — нарушает `lazy imports only` rule из `.claude/rules/domains/buyer.md`. FTR-897 добавляет service-ветку без этого импорта, но legacy import остаётся. Рекомендация: при следующем существенном изменении `onboarding.py` — перевести на lazy import (Boy Scout rule).

---

## Related

- Council synthesis: `ai/.council/20260501-external-traffic-onboarding/synthesis.md`
- FTR-872: Morning campaign digest (empty-state CTA target)
- FTR-886: `buyer_platform_identities` backfill (identity infra)
- FTR-887: Auth lifecycle (queued — не блокирует)
- FTR-889: MiniApp infra (queued — Phase 2 dependency)
- Attribution Analytics Baseline (Спека 2 — после 50 регистраций, отдельный ID)
- FTR-898: Creator Onboarding MVP (role mechanics, account_kind ENUM)
- FTR-909: Creator Onboarding Verification Flow (selfie + VK/TikTok scraping pipeline на 5000 креаторов)

---

## Implementation Plan — Task 11 (catch-up 2026-05-02)

**Status (2026-05-02):** Tasks 1-10 закоммичены ранее (миграции применены, bot-handlers `onboarding_service.py` пишут в DB напрямую через `client.table(...)`). **Task 11 остался** — поднять v2 endpoints поверх тех же таблиц (per ADR-016, founder-requirement: drift prevention для miniapp/web).

### Drift Log

**Checked:** 2026-05-02 08:25 UTC
**Result:** light_drift (uncovered by Tasks 1-10 commits)

| File | Change vs spec | Action |
|------|----------------|--------|
| `src/domains/buyer/handlers/onboarding_service.py` | Уже создан в Task 6 (325 LOC). Содержит `_insert_consent`, `_insert_onboarding_event` — прямые `client.table(...)` writes (фактический канон bot-flow). | Reuse SQL shapes; bot-handler рефактор под impl-вызов = OUT-OF-SCOPE для Task 11 (founder explicitly said "v2 endpoints with first day"). Bot continues to write directly; v2 endpoints — параллельный путь для miniapp/web. Boy-Scout-перевод bot-handler позже, когда miniapp будет тестировать. Не ломаем working flow. |
| `src/api/v2/buyer/__init__.py` (line 8 / 16) | Re-exports `router` from `router.py` only. | Add `onboarding` sub-router import in `router.py` (NOT `__init__.py`). |
| `src/api/v2/buyer/router.py` | Mounts `auth/profile/tasks/slots/earnings`. No `onboarding`. | Add `from src.api.v2.buyer.onboarding import router as onboarding_router` + `router.include_router(onboarding_router)`. |
| `src/api/v2/admin/__init__.py` | Mounts 11 sub-routers. No `onboarding`. | Add `onboarding_router` for `GET /attribution`. |
| `consents` / `onboarding_events` table shapes | Migrations applied: `consents(buyer_id UUID, version TEXT, accepted_at TZ, ip_hash TEXT, ua_hash TEXT, consent_type TEXT='personal_data')` + `onboarding_events(buyer_id UUID, step TEXT, ref_source TEXT, ip_hash TEXT, ts TZ)`. | Pydantic схемы должны matchить ровно эти колонки. |
| `BuyerNotFoundError` / `ValidationError` | Уже в `src/api/v2/buyer/errors.py`. | Reuse — НЕ создавать новый `OnboardingError` enum. Спека упоминает enum, но проект использует typed `DomainError` subclasses. |

### References Updated
- Spec line 315 `OnboardingError` enum → реализуем через existing `BuyerNotFoundError` + `ValidationError` + новый `ConsentVersionInvalidError(DomainError)` (минимальный additive change в `errors.py`).
- Spec line 322 admin route → файл `src/api/v2/admin/onboarding.py` (NEW), mounted по pattern `pricing.py`.

---

### Task 11.1 — Add error type for consent

**File:** `src/api/v2/buyer/errors.py` (modify)

Add (after `ValidationError`, before `EligibilityReason`):
```python
class ConsentVersionInvalidError(DomainError):
    """Raised when ConsentSubmitRequest.version doesn't match accepted versions list."""
```
Add `ConsentVersionInvalidError` to `__all__`.

**File:** `src/api/v2/buyer/_result_http.py` (modify)

Add to `_ERROR_HTTP_MAP`:
```python
ConsentVersionInvalidError: (422, "CONSENT_VERSION_INVALID"),
```
Import `ConsentVersionInvalidError` at top of `_result_http.py`.

**Why:** ADR-016 requires typed errors per impl. `ValidationError` is reserved for Pydantic envelope; consent version mismatch = domain rule.

---

### Task 11.2 — Create `src/api/v2/buyer/onboarding.py` (NEW, ~150 LOC)

Module header (mandatory per architecture.md):
```python
"""
Module: api/v2/buyer/onboarding
Role: FTR-897 v2 buyer onboarding endpoints — Result-based pure-function impls
      + thin FastAPI route adapters. Per ADR-016: miniapp/web clients call these
      endpoints; bot-handler `onboarding_service.py` writes directly to DB
      (parallel path, kept for working flow — to be migrated post-miniapp).

Uses:
  - shared/result:Result, Ok, Err
  - api/v2/buyer/errors:BuyerNotFoundError, ConsentVersionInvalidError, ValidationError
  - api/v2/buyer/schemas:BuyerContext
  - api/v2/buyer/_result_http:unwrap_or_raise
  - api/v2/buyer/deps:get_current_buyer, rate_limit
  - infra/db/client:get_supabase_async (lazy)

Used by:
  - api/v2/buyer/router (include_router)

Glossary: ai/glossary/buyer.md
"""
```

#### 11.2.a Pydantic schemas (top of file)

```python
_ALLOWED_CONSENT_VERSIONS = {"2026-05-01"}  # SSOT — bump in lockstep with onboarding_service._CONSENT_VERSION

class ConsentSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(..., examples=["2026-05-01"])
    ip_hash: str | None = Field(None, max_length=128)
    ua_hash: str | None = Field(None, max_length=128)

class ConsentResponse(BaseModel):
    consent_id: int
    accepted_at: datetime
    version: str

class OnboardingEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: str = Field(..., min_length=1, max_length=64)
    ref_source: str | None = Field(None, max_length=128)
    ip_hash: str | None = Field(None, max_length=128)

class OnboardingEventResponse(BaseModel):
    event_id: int
    ts: datetime

class AcquisitionRow(BaseModel):
    acquisition_source: str | None  # NULL = organic
    total_buyers: int
    finalized_buyers: int
    finalize_rate: float = Field(..., ge=0.0, le=1.0)

class AcquisitionResponse(BaseModel):
    items: list[AcquisitionRow]
    total_buyers: int
```

#### 11.2.b Pure-function impls

```python
async def submit_consent_impl(
    buyer: BuyerContext,
    request: ConsentSubmitRequest,
) -> Result[ConsentResponse, BuyerNotFoundError | ConsentVersionInvalidError]:
    """Persist 152-FZ consent for the authenticated buyer.

    SQL shape mirrors onboarding_service._insert_consent() — same table,
    same columns, but called from miniapp/web instead of bot-FSM.
    """
    if request.version not in _ALLOWED_CONSENT_VERSIONS:
        return Err(ConsentVersionInvalidError(f"unsupported consent version: {request.version}"))

    from src.infra.db.client import get_supabase_async
    client = await get_supabase_async()

    # Pre-check buyer exists (404 contract)
    buyer_resp = await (
        client.table("buyers").select("id").eq("id", str(buyer.id)).limit(1).execute()
    )
    if not (buyer_resp.data or []):
        return Err(BuyerNotFoundError(buyer.id))

    payload = {
        "buyer_id": str(buyer.id),
        "version": request.version,
        "consent_type": "personal_data",
        "ip_hash": request.ip_hash,
        "ua_hash": request.ua_hash,
    }
    insert_resp = await (
        client.table("consents").insert(payload).execute()
    )
    rows = insert_resp.data or []
    if not rows:
        # supabase-py returns inserted row(s) by default — empty = unexpected
        return Err(BuyerNotFoundError(buyer.id))  # fail-loud; conservative
    row = rows[0]
    return Ok(ConsentResponse(
        consent_id=int(row["id"]),
        accepted_at=row["accepted_at"],
        version=row["version"],
    ))


async def record_onboarding_event_impl(
    buyer: BuyerContext,
    request: OnboardingEventCreate,
) -> Result[OnboardingEventResponse, BuyerNotFoundError]:
    """Fire-and-forget audit log INSERT into onboarding_events.

    Mirrors onboarding_service._insert_onboarding_event() shape (BUT this
    impl returns the inserted row; bot-flow's helper swallows errors —
    here we surface them so miniapp can retry on failure).
    """
    from src.infra.db.client import get_supabase_async
    client = await get_supabase_async()

    payload = {
        "buyer_id": str(buyer.id),
        "step": request.step,
        "ref_source": request.ref_source,
        "ip_hash": request.ip_hash,
    }
    resp = await (client.table("onboarding_events").insert(payload).execute())
    rows = resp.data or []
    if not rows:
        return Err(BuyerNotFoundError(buyer.id))
    row = rows[0]
    return Ok(OnboardingEventResponse(
        event_id=int(row["id"]),
        ts=row["ts"],
    ))
```

#### 11.2.c Thin route adapters (buyer-auth)

```python
router = APIRouter(prefix="/onboarding", tags=["v2-buyer-onboarding"])

@router.post("/consent", response_model=ConsentResponse)
async def submit_consent_route(
    request: ConsentSubmitRequest,
    _rl: None = Depends(rate_limit("onboarding_consent", 5, 60)),  # noqa: B008
    buyer: BuyerContext = Depends(get_current_buyer),  # noqa: B008
) -> ConsentResponse:
    result = await submit_consent_impl(buyer, request)
    return unwrap_or_raise(result)

@router.post("/event", response_model=OnboardingEventResponse)
async def record_event_route(
    request: OnboardingEventCreate,
    _rl: None = Depends(rate_limit("onboarding_event", 30, 60)),  # noqa: B008
    buyer: BuyerContext = Depends(get_current_buyer),  # noqa: B008
) -> OnboardingEventResponse:
    result = await record_onboarding_event_impl(buyer, request)
    return unwrap_or_raise(result)


__all__ = [
    "router",
    "submit_consent_impl",
    "record_onboarding_event_impl",
    "ConsentSubmitRequest", "ConsentResponse",
    "OnboardingEventCreate", "OnboardingEventResponse",
    "AcquisitionRow", "AcquisitionResponse",
    "get_acquisition_attribution_impl",
]
```

---

### Task 11.3 — Wire buyer router

**File:** `src/api/v2/buyer/router.py` (modify)

Add import:
```python
from src.api.v2.buyer.onboarding import router as onboarding_router
```

Add include after `earnings_router` line:
```python
router.include_router(onboarding_router)  # /onboarding/consent, /onboarding/event
```

Update module docstring `Uses:` block to reference `onboarding:router`.

---

### Task 11.4 — Create `src/api/v2/admin/onboarding.py` (NEW, ~80 LOC)

Admin-side aggregate endpoint (per ADR-017 — JWT human auth via `get_current_admin`).

Module header + impl + route:

```python
"""
Module: api/v2/admin/onboarding
Role: FTR-897 admin attribution dashboard data — finalize_rate per acquisition_source.
      Pure-function impl + thin route. Used by Mission Control and Спека 2 (Attribution Baseline).

Uses:
  - api/v2/admin/deps:get_current_admin
  - api/v2/admin/schemas:AdminUser
  - api/v2/buyer/onboarding:AcquisitionResponse, AcquisitionRow

Glossary: ai/glossary/buyer.md
"""

from fastapi import APIRouter, Depends

from src.api.v2.admin.deps import get_current_admin
from src.api.v2.admin.schemas import AdminUser
from src.api.v2.buyer.onboarding import AcquisitionResponse, AcquisitionRow

router = APIRouter(prefix="/onboarding", tags=["v2-admin-onboarding"])


async def get_acquisition_attribution_impl(
    _admin: AdminUser,  # actor for audit (currently unused; reserved)
) -> AcquisitionResponse:
    """Aggregate buyers × finalize_rate grouped by acquisition_source.

    Read-only. Computes finalize-rate as
        finalized = COUNT WHERE buyers.status = 'active'
        total     = COUNT WHERE buyers.archived_at IS NULL
    """
    from src.infra.db.client import get_supabase_async

    client = await get_supabase_async()
    resp = await (
        client.table("buyers")
        .select("acquisition_source,status,archived_at")
        .is_("archived_at", "null")
        .execute()
    )
    rows = resp.data or []

    buckets: dict[str | None, dict[str, int]] = {}
    for r in rows:
        key = r.get("acquisition_source")  # None = organic
        bucket = buckets.setdefault(key, {"total": 0, "finalized": 0})
        bucket["total"] += 1
        if r.get("status") == "active":
            bucket["finalized"] += 1

    items = [
        AcquisitionRow(
            acquisition_source=src,
            total_buyers=b["total"],
            finalized_buyers=b["finalized"],
            finalize_rate=(b["finalized"] / b["total"]) if b["total"] else 0.0,
        )
        for src, b in sorted(buckets.items(), key=lambda kv: -(kv[1]["total"]))
    ]
    return AcquisitionResponse(items=items, total_buyers=sum(b["total"] for b in buckets.values()))


@router.get("/attribution", response_model=AcquisitionResponse)
async def get_attribution_route(
    current_admin: AdminUser = Depends(get_current_admin),  # noqa: B008
) -> AcquisitionResponse:
    return await get_acquisition_attribution_impl(current_admin)


__all__ = ["router", "get_acquisition_attribution_impl"]
```

**Note on co-location:** `get_acquisition_attribution_impl` lives in `admin/onboarding.py`, NOT `buyer/onboarding.py` — admin-only by access pattern. Buyer module re-exports the symbol in `__all__` for symmetry with spec line 315 but lazy-imports from admin to avoid import cycle (or leave out — spec was illustrative). Decision: keep in `admin/onboarding.py` only; remove from `buyer/onboarding.py` `__all__`.

---

### Task 11.5 — Wire admin router

**File:** `src/api/v2/admin/__init__.py` (modify)

Add import + include after `pricing_router`:
```python
from src.api.v2.admin.onboarding import router as onboarding_router
...
router.include_router(onboarding_router)
```

Update module docstring `Uses:` block.

---

### Task 11.6 — Tests (TDD order)

**File:** `tests/unit/api/v2/buyer/test_onboarding_impl.py` (NEW)

Unit tests for `submit_consent_impl` + `record_onboarding_event_impl`:
- TC-1: `submit_consent_impl` with version `"2026-05-01"` → Ok + INSERT issued (mock supabase client at boundary, ADR-014).
- TC-2: `submit_consent_impl` with version `"2024-01-01"` → Err(ConsentVersionInvalidError).
- TC-3: `record_onboarding_event_impl(step="screen1", ref_source="blogger123")` → Ok with `OnboardingEventResponse`.
- TC-4: Pydantic `extra="forbid"` rejects unknown fields (`pytest.raises(ValidationError)` from pydantic).

**File:** `tests/integration/api/v2/buyer/test_onboarding_routes.py` (NEW)

Integration tests against real DEV DB (per ADR-013 — NO mocks):
- TC-5: POST `/api/v2/buyer/onboarding/consent` with valid Bearer JWT → 200 + row visible in `consents` table.
- TC-6: POST `/api/v2/buyer/onboarding/event` → 200 + row in `onboarding_events`.
- TC-7: GET `/api/v2/admin/onboarding/attribution` with admin JWT → returns aggregate (>= 1 row if any acquisition_source exists in DEV).
- TC-8: Architecture fitness: `tests/architecture/test_v2_layer.py` — `submit_consent_impl` must be importable WITHOUT importing `aiogram` or `src.domains.*` (lazy-only).

Skip `pytest.skip` if dev DB env not configured (use `DEV_DB_URL` env-guard pattern from existing buyer v2 integration tests).

---

### Execution Order

```
11.1 errors taxonomy  →  11.2 onboarding.py impl + Pydantic
                                 ↓
                        11.3 buyer/router wiring
                                 ↓
                        11.4 admin/onboarding.py
                                 ↓
                        11.5 admin/__init__ wiring
                                 ↓
                        11.6 tests (unit first, then integration)
```

### Dependencies

- 11.2 depends on 11.1 (imports `ConsentVersionInvalidError`)
- 11.3 depends on 11.2 (imports `router`)
- 11.4 depends on 11.2 (imports `AcquisitionResponse`, `AcquisitionRow` schemas)
- 11.5 depends on 11.4
- 11.6 covers 11.1-11.5 (golden-path integration)

### Reuse / SSOT

- **SQL shapes:** column names (`buyer_id`, `version`, `consent_type`, `ip_hash`, `ua_hash`; `step`, `ref_source`, `ts`) lifted from `onboarding_service._insert_consent` / `_insert_onboarding_event` — keep IDENTICAL or impl<->bot will drift.
- **Consent version SSOT:** `_ALLOWED_CONSENT_VERSIONS = {"2026-05-01"}` matches `_CONSENT_VERSION = "2026-05-01"` in `onboarding_service.py:39`. When founder bumps version → MUST update both files (TODO: lift to `src/shared/consent.py` in Boy-Scout pass).
- **DB access:** `get_supabase_async()` (lazy import) — same as profile.py:106.
- **Auth:** `get_current_buyer` (Bearer JWT path → BuyerContext) for buyer endpoints; `get_current_admin` (JWT) for admin. Per ADR-017 — both human actors, no X-Admin-Key needed.
- **Error mapping:** `unwrap_or_raise` from `_result_http.py` — already wired.

### Out of Scope (catch-up explicitly)

- Refactoring `onboarding_service.py` to call `submit_consent_impl(...)` instead of writing directly. Founder-requirement was "v2 endpoints from day one" — bot-flow keeps its working direct-write path. Migration to thin-adapter bot-handler = follow-up Boy Scout (when miniapp first connects).
- Idempotency-Key header on `/event` endpoint — fire-and-forget by design; replays = harmless duplicate audit rows.
- ip_hash/ua_hash extraction from request headers — caller (miniapp/web) responsible for hashing client-side per privacy contract; impl just persists what comes in.

### Acceptance (Task 11)

- [ ] `POST /api/v2/buyer/onboarding/consent` returns 200 with valid JWT + 422 with bad version
- [ ] `POST /api/v2/buyer/onboarding/event` returns 200 + row visible in `onboarding_events`
- [ ] `GET /api/v2/admin/onboarding/attribution` returns AcquisitionResponse with finalize_rate per source
- [ ] All 8 test cases (TC-1..TC-8) green
- [ ] `src/api/v2/buyer/onboarding.py` ≤ 200 LOC
- [ ] `src/api/v2/admin/onboarding.py` ≤ 100 LOC
- [ ] No new top-level `from src.domains.*` imports in v2 layer (architecture fitness)
- [ ] Bot-flow `onboarding_service.py` UNCHANGED (no regression)
- [ ] Commit: `feat(FTR-897): v2 buyer/admin onboarding endpoints (Task 11)`
