# FTR-909 — Creator Onboarding Verification Flow

**Status:** blocked
**Priority:** P1
**Date:** 2026-05-01
**Effort:** ~2 weeks / ~$22 LLM (8-12 tasks)
**Decision mode:** spark auto (Approach B, scout convergence + 2 ACTION REQUIRED items for founder ACK)
**Prerequisite:** **FTR-898 must merge first** (creator_applications table, account_kind ENUM, promote_creator_impl) + FTR-897 merged (onboarding_events, consents helpers)
**Spark session:** `ai/.spark/20260501-FTR-909/`
**Blueprint reference:** `.claude/rules/domains/buyer.md`, `.claude/rules/domains/campaigns.md`, ADR-016/017/018/019

---

## Problem

Готовится крупная маркетинговая кампания: ~5000 креаторов онбординга за месяц (~167/день, peaks 30+ concurrent). Текущая инфраструктура верификации блогеров недостаточна:

- **Существующая `BloggerHandler` (FTR-162/437):** Vision-only анализ скриншота, `MIN_FOLLOWERS=1000`, нет URL парсинга, нет селфи, нет async job queue. Ручной онбординг = операторская перегрузка при 5000/мес. Не соответствует требованиям founder (минимум 100 подписчиков, селфи, ссылки на VK/TikTok).
- **Существующий `blogger.py` нарушает ADR-016:** пишет напрямую в `buyers_repo.update()` из Telegram handler — байпасс `*_impl` pattern. Дрейф business logic между MCP и v2 API неизбежен при масштабировании.
- **Нет SSOT-перехода с `is_premium` на `account_kind='creator'`:** FTR-898 определяет новую роль, но без верификационного слоя `account_kind='creator'` ставится только через ручную операторскую approval — не масштабируется.
- **152-ФЗ риск селфи:** без чёткой архитектурной декомпозиции (face-presence-only vs identification system) есть риск переквалификации в биометрические данные → особое согласие + локализация.
- **Нет VK/TikTok scraping infrastructure:** в `src/infra/external/` только `wb_parser.py`, `wb_product_parser.py`, `dadata.py`. Нулевая интеграция социальных платформ.

**Kill question:** без верификационного слоя на 5000 креаторов поступит >60% фейков (купленные подписчики + Photoshop скриншоты + AI-сгенерированные селфи); creator-tier cashback платится за коммодити-контент → потеря ~1.5M ₽/месяц при 30% fake share.

---

## Scope

**Включено (MVP):**

- **Migration wave 6** (`20260501120006_creator_applications_ext.sql`): расширение `creator_applications` (FTR-898) — `selfie_url TEXT NULL`, `vk_url TEXT NULL`, `tiktok_url TEXT NULL`, `parsed_follower_count_vk INT NULL`, `parsed_follower_count_tiktok INT NULL`, `verification_confidence FLOAT NULL`, `verification_method TEXT NULL` CHECK in (`'vision_ocr','vk_api','vk_api+vision','manual'`), `selfie_verified_at TIMESTAMPTZ NULL`, `social_api_verified_at TIMESTAMPTZ NULL`, `avg_views_30d_vk INT NULL`, `avg_views_90d_vk INT NULL`. **Partial UNIQUE INDEX** `creator_applications_pending_uniq ON creator_applications(buyer_id) WHERE status='pending'` (anti-double-submit, ADR-018 CONCURRENTLY вне транзакции).
- **Migration wave 7** (`20260501120007_creator_scraping_jobs.sql`): новая таблица `creator_scraping_jobs` (зеркалит `proof_jobs` schema): `id UUID PK, application_id UUID FK creator_applications, status TEXT CHECK in (pending|processing|completed|failed), attempts INT DEFAULT 0, payload JSONB NOT NULL, error TEXT NULL, created_at, updated_at`. Index на `(status, updated_at)` для polling.
- **Migration wave 8** (`20260501120008_creator_scraping_status_ext.sql`): расширение `creator_applications.status` CHECK — добавить `'pending_scraping'` к существующим `pending|approved|rejected|needs_info|banned` (статус "анкета принята, парсинг в очереди"). Update `_insert_onboarding_event` step values.
- **`apply_creator_verify_impl(actor, CreatorVerifyRequest) -> Result[CreatorVerifyResponse, CreatorVerifyError]`** (`src/api/v2/buyer/creator_verify.py`) — новая пур-функция (ADR-016). Принимает `selfie_base64`, `vk_url`, `tiktok_url` (хотя бы один из двух), `screenshot_base64` (опционально). Steps:
  1. Eligibility gate: rate limit 1/24h (FTR-890 `creator_verify_apply` scope), URL format validation, ≥1 social URL.
  2. Inline Vision selfie check: `face_present`, `likely_spoofed`, `likely_synthetic` через `SELFIE_VERIFICATION_PROMPT`. На fail → instant reject (`status='rejected'`, reason из Vision response).
  3. Selfie storage: `StorageService.upload_creator_selfie()` → `selfie_url`.
  4. INSERT `creator_applications(status='pending_scraping', selfie_url, vk_url, tiktok_url, ...)`.
  5. INSERT `creator_scraping_jobs(application_id, status='pending', payload={vk_url, tiktok_url, screenshot_base64})`.
  6. Schedule `asyncio.create_task` (через `_creator_jobs.schedule_creator_scraping`) для немедленной обработки.
  7. Return `CreatorVerifyResponse(application_id, status='pending_scraping')` — bot polls `/creator/status` или ждёт push.
- **`creator_scraping_runner.py`** (`src/domains/buyer/services/creator_scraping.py`, ≤300 LOC) — async worker, зеркалит `proof_job_runner.py`:
  - `run_creator_scraping_job(job_id, application_id, payload, max_attempts=3)` — idempotency guard, atomic attempts increment.
  - VK path: Official VK API service token → `users.get(fields=counters)` для личных профилей OR `groups.getById(fields=members_count,counters)` для групп → `wall.get(count=100, extended=1)` → compute `avg_views_30d`, `avg_views_90d`. Rate limit: 3 RPS (group token: 20 RPS via `execute` batch).
  - TikTok path: Vision OCR на screenshot (Gemini Flash) с `CREATOR_TIKTOK_PROMPT` → extract `follower_count`, `recent_views` (3-5 постов).
  - Cross-validation: если screenshot загружен И VK API дал результат → сравнить >20% mismatch → `verification_method='manual'` (escalate).
  - UPDATE `creator_applications` с metrics + `verification_confidence` + `verification_method` + `social_api_verified_at`.
  - Tiered routing:
    - `min(vk_followers, tiktok_followers) < 100` OR Vision detected `not_real_profile` → call `promote_creator_impl(action='reject', reason=..., actor='cron:creator_scraping_verifier')`.
    - `max(vk_followers, tiktok_followers) >= 500 AND confidence >= 0.95 AND no flags` → call `promote_creator_impl(action='approve', actor='cron:creator_scraping_verifier')` (auto). `account_kind='creator'`, ALSO set `is_premium=True` (backward compat).
    - middle band → UPDATE status='needs_info' → operator queue (Mission Control HTMX).
  - `notify_buyer(...)` через FTR-872 morning digest channel с `priority=high`. На fail после 3 попыток: `status='needs_info'` + ops alert.
- **`SELFIE_VERIFICATION_PROMPT`** + **`CREATOR_TIKTOK_PROMPT`** (`src/domains/buyer/services/vision_prompts_creator.py`, новый файл — `vision_prompts.py` уже 515 LOC, превышает 400 LOC лимит). Pydantic models `SelfieAnalysis`, `TikTokScreenshotAnalysis` через structured output (`response_format=PydanticModel`).
- **`StorageService.upload_creator_selfie(buyer_id, image_bytes) -> str`** (`src/infra/storage/service.py`) — путь `buyers/{buyer_id}/selfie_creator_{ts}.jpg`, bucket `photos`. **ACTION REQUIRED:** founder/ops подтверждают регион bucket = РФ перед launch. Если EU/US — миграция на Yandex Object Storage до launch.
- **152-ФЗ consent extension:** новый `consent_type='creator_verification'` в `consents` table (FTR-897 wave 3 reuses helper `_insert_consent`). Текст согласия — стандартное PD согласие (НЕ биометрия), включает: фото-селфи (для proof-of-personhood, не identification), скриншоты соцсетей, ссылки. Срок хранения 90 дней. Шаблон в `src/domains/buyer/locales/ru.yaml` (key `creator.consent.text`).
- **Selfie retention cron** — extension to existing `scripts/cron/` или новый `scripts/cron/creator_selfie_cleanup.sh`: DELETE `selfie_url` (set NULL + storage delete) на `creator_applications` где `selfie_verified_at < now() - 90 days` AND `status IN ('approved','rejected','banned')`.
- **Bot UX (eligibility-first FSM):**
  - Точка входа: `/menu` → CTA "Стать креатором" (после FTR-898 base CTA). Pre-screen: "Минимум 100 подписчиков ВКонтакте или TikTok. Подробнее →" (founder upfront expectation).
  - FSM states (extend `BuyerStates` в `src/domains/buyer/states.py`): `creator_verify_url`, `creator_verify_selfie`, `creator_verify_screenshot`, `creator_verify_consent`, `creator_verify_waiting`.
  - Шаги:
    1. URL input — VK URL (обязательно или опционально, см. ниже) + TikTok URL (опционально/обязательно), валидация формата (`vk.com/...` или `tiktok.com/@...`). **Min one of two.**
    2. Selfie upload (`creator_verify_selfie`) — explicit illustrated instructions ("Фото ВАШЕГО лица в камеру, не скриншот"). На no-photo retry / на бот-photo-of-photo retry с подсказкой.
    3. Screenshot upload (`creator_verify_screenshot`) — опциональный для VK (если URL дан, scraper попробует API), обязательный для TikTok если TikTok URL submitted. Подсказка: "Скриншот должен включать число подписчиков + 3-5 последних постов с просмотрами".
    4. Consent checkbox с inline keyboard (`creator_verify_consent`).
    5. Submit → POST `/api/v2/buyer/creator/verify_apply` → return 202 → bot переходит в `creator_verify_waiting` state с сообщением "Проверяем заявку, ответ в течение 5 минут". Параллельно planning notification (FTR-872 digest или прямой `notify_buyer` при ready).
- **Migrate `blogger.py` to ADR-016 thin adapter** (Boy Scout Rule):
  - Создать `verify_blogger_impl(actor, BloggerVerifyRequest) -> Result[BloggerVerifyResponse, BloggerError]` (`src/api/v2/buyer/blogger_verify.py`) — wraps existing `BloggerHandler.analyze_social_profile()` + `save_blogger_info()`.
  - `src/domains/buyer/handlers/blogger.py` теперь thin: callback → POST к v2 endpoint OR direct call `verify_blogger_impl`. Никаких прямых `buyers_repo.update()` из handler.
  - **`MIN_FOLLOWERS = 1000` → `100`** (founder requirement).
  - `is_premium=True` пишется параллельно (legacy), `account_kind='creator'` через `promote_creator_impl` (новая SSOT).
- **Mission Control extension:** `src/api/admin/templates/creator_applications.html` (создаётся в FTR-898) — добавить колонки: `selfie_thumbnail` (URL → IMG), `vk_url`/`tiktok_url` (clickable), `parsed_follower_count_vk`, `parsed_follower_count_tiktok`, `verification_confidence`, `verification_method` (badge). Optimistic lock через `updated_at` ETag → 409 на stale. Action `reject` обязательно требует `reason` (FTR-898 spec позволял `None` — fix как часть FTR-909).
- **48h SLA cron** (`scripts/cron/creator_review_sla.sh`): scan `creator_applications` где `status='needs_info'` AND `updated_at < now() - 48h` AND `verification_confidence >= 0.8` AND `parsed_follower_count >= 200` → auto-promote через `promote_creator_impl(action='approve', actor='cron:creator_sla_promoter')`. Иначе ops alert "borderline application past SLA".
- **Notifications:** статус changes (verified/needs_info/rejected) — через FTR-872 morning digest (FTR-898 pattern), priority=high. Auto-approve ALSO шлёт immediate `notify_buyer` "Поздравляем, вы прошли верификацию!".
- **Rate limit registry update (FTR-890):** новый scope `creator_verify_apply` = 1/24h per buyer + per ip_hash (anti-spam multi-account creation).

**Исключено (строго out of scope):**

- **Phyllo / HypeAuditor / Modash интеграция** — Vision OCR fallback покрывает TikTok. Phyllo не поддерживает VK + payment from RU проблематичен. Trigger для добавления: если manual moderation queue >60/день из-за false-rejections от Vision → FTR-9XX intergration.
- **AWS Rekognition Face Liveness / iProov / FaceTec** — full liveness API. Vision passive check достаточен при текущем fraud tolerance. Trigger: если fraud loss >$500/мес → economic ROI для $100/мес Rekognition.
- **Face matching селфи vs profile avatar** — Vision compare_images ~70% accurate, marginal value, удвоение Vision cost.
- **Telegram WebApp (TWA) для камеры** — bot-only photo upload sufficient (RU market standard). TWA нужен только для активного liveness (active challenge), что out of scope.
- **OAuth-based VK verification** — требует registered VK app + 2-3 недели approval. Service token (server-side) + scraping API достаточно для MVP. Trigger: если VK банит service token за scraping public data.
- **Instagram, YouTube, Facebook, Twitter scraping** — founder указал только VK + TikTok.
- **Age verification (>18 / >14 для TikTok-VK rules)** — separate consent stub, не блокер MVP. Add в Phase 2.
- **Crypto / wallet выплаты** — используется existing buyer payout rails.
- **Direct payments to creators** — separate accounting, used `payout` skill rails.
- **Реальное Instagram parsing** — не в scope.
- **Migration `is_premium` → `account_kind='creator'` для existing buyers** — separate TECH-XXX (5 call sites: `menu.py`, `offers_view.py`, `keyboards/menu.py`, `offers_listing.py`, `offer_repo.py:200`). FTR-909 пишет ОБА флага параллельно (additive).
- **Visible-locked creator slots для non-creators (Phase 2)** — наследуется от FTR-898.
- **Seller UI toggle для `is_creator_only`** — admin-only at MVP (FTR-898).
- **Creator-tier velocity / dispersion cashback rules** — наследуется от FTR-898 (role-agnostic первые 3 месяца).
- **`creator_application_data JSONB` под raw KYC blobs** — column ТОЛЬКО для moderator notes (FTR-898 council vetoed). Verification metrics — typed columns в wave 6.
- **Dedicated landing page** — out of scope per FTR-897 architecture.

---

## Architectural Decision (locked — Approach B from synthesis)

**Eligibility-first hybrid pipeline**, scout convergence (3 of 4 scouts: external/codebase/patterns recommend; devil recommends Alternative 2 manual-only — REJECTED at scale).

**Composed dimensions** (per `ai/.spark/20260501-FTR-909/research-patterns.md`):
- 1A (Eligibility-first FSM ordering)
- 2C → 2B upgrade path (Pure Vision OCR at MVP, Phyllo optional in Sprint 2)
- 3A (Vision passive selfie check, no liveness API)
- 4E (proof_jobs pattern reuse — `creator_scraping_jobs`)
- 5A (Bot-only frontend)
- 6A+B+C+D (Tiered moderation: auto-reject + auto-approve + manual middle + 48h SLA)
- 7A (Extend `creator_applications` typed columns, no JSONB blob)

**SSOT decision (locked, founder ACK 2026-05-01):** Bulk migrate. Read sites переписываются на `buyer.account_kind == 'creator'`. Write sites (`blogger.py`, `blogger_handler.py`) переключаются на `promote_creator_impl(action='approve', actor=...)` через thin adapter; колонка `buyers.is_premium` остаётся в схеме (drop — отдельная TECH-XXX после мониторинга 2-4 недели), но `BuyerUpdate(is_premium=...)` больше не пишется из приложения. Все 5 read sites (`offer_repo.py:200`, `offers_listing.py:38,53`, `menu.py:85,89,224,351,355`, `offers_view.py:173,201`, `keyboards/menu.py:26,53`) — в Task 17.

**152-ФЗ status (locked):** Селфи — обычные ПД (не биометрия) per Constitutional Court Определение № 2298-О / 2023 — нет face embedding system, нет identification database, только presence check. Standard PD consent, 90-day retention, РФ-region storage required.

---

## ACTION REQUIRED (founder review before autopilot picks up)

1. **Storage region:** Spark подтвердил prod Supabase = `aws-1-eu-north-1` (Stockholm). 152-ФЗ ст.18(5) формально требует РФ-storage для ПД. Founder ACK 2026-05-01: «похуй пока» — селфи всё равно идут в bucket `photos` (EU). Documented как known legal risk, не блокер кода. **Trigger для возврата:** РКН проверка / штраф / запрос на data localization → срочная миграция селфи на Yandex Object Storage (отдельный TECH).
2. **152-ФЗ consent text:** Шаблон в research-external.md §E.5 — нужно юр review перед activation. Не блокер для кода, блокер для launch.
3. **SSOT decision (founder ACK 2026-05-01):** Bulk migrate в FTR-909. Read sites переписываются на `account_kind`, write sites — на `promote_creator_impl`. Task 17 добавлен.

---

## Approach (selected) — Eligibility-first hybrid с reuse infrastructure

| Layer | Что делается | Reuse pattern |
|-------|-------------|---------------|
| Schema | Wave 6 extends creator_applications, Wave 7 creator_scraping_jobs, Wave 8 status CHECK | FTR-898 wave 4 + proof_jobs schema |
| API v2 | apply_creator_verify_impl (new), verify_blogger_impl (migrate existing) | ADR-016 thin adapter |
| Async | creator_scraping_runner, schedule_creator_scraping fire-and-forget | proof_job_runner.py + _proof_jobs.py (TECH-891) |
| External | VK Official API service token (free) + Gemini Vision OCR (existing infra) | Mirror wb_parser.py module structure |
| Storage | StorageService.upload_creator_selfie | photos bucket reuse |
| Notifications | FTR-872 digest priority=high + immediate notify on auto-approve | NotificationService existing |
| Bot UX | Eligibility-first FSM with 5 new states | aiogram FSM pattern (existing onboarding_*) |
| Operator | Mission Control HTMX extension | FTR-898 templates |

---

## Tasks

### Task 0: Boy Scout — unit tests for existing BloggerHandler
**Why:** No test coverage exists; refactoring is risky без regression net.
**What:** `tests/unit/test_blogger_handler.py` — 5+ tests covering analyze_social_profile, save_blogger_info, skip_blogger_check.

### Task 1: Migration wave 6 — extend creator_applications
**Why:** FTR-898 schema lacks verification columns.
**What:** `supabase/migrations/20260501120006_creator_applications_ext.sql` — add 11 columns + partial UNIQUE index (CONCURRENTLY вне транзакции, ADR-018 IMMUTABLE WHERE only).
**Risk:** R0 (irreversible schema change but additive — drop-column rollback safe).

### Task 2: Migration wave 7 — creator_scraping_jobs table
**Why:** Async pipeline needs durable state.
**What:** `supabase/migrations/20260501120007_creator_scraping_jobs.sql` — table mirrors proof_jobs (id, application_id FK, status CHECK, attempts INT, payload JSONB, error TEXT, created_at, updated_at) + index (status, updated_at).

### Task 3: Migration wave 8 — extend creator_applications.status CHECK
**Why:** Need `pending_scraping` value для new state.
**What:** `supabase/migrations/20260501120008_creator_scraping_status_ext.sql` — DROP + recreate CHECK constraint.

### Task 4: Vision prompts module
**Why:** vision_prompts.py over 400 LOC; new prompts for selfie + TikTok extraction.
**What:** `src/domains/buyer/services/vision_prompts_creator.py` — `SELFIE_VERIFICATION_PROMPT`, `CREATOR_TIKTOK_PROMPT`, Pydantic models `SelfieAnalysis(face_present, likely_spoofed, likely_synthetic, confidence)`, `TikTokScreenshotAnalysis(follower_count, recent_views, confidence)`.

### Task 5: Storage method для selfie
**What:** `src/infra/storage/service.py` — add `upload_creator_selfie(buyer_id, image_bytes) -> str` метод. Path `buyers/{buyer_id}/selfie_creator_{ts}.jpg`, bucket `photos`.

### Task 6: VK API client
**What:** `src/infra/external/social/vk_client.py` (new module) — `VKClient` with `get_user_followers(user_id) -> int`, `get_group_members(group_id) -> int`, `get_wall_views(owner_id, days=30|90) -> float`. Service token from settings. Rate limit handling (3 RPS user / 20 RPS group via `execute` batch). Result-based.

### Task 7: Creator scraping runner
**What:** `src/domains/buyer/services/creator_scraping.py` (≤300 LOC) — `run_creator_scraping_job(job_id, application_id, payload, max_attempts=3)`. Mirrors `proof_job_runner.py`. Includes tiered routing logic + calls `promote_creator_impl`.

### Task 8: Creator jobs scheduler
**What:** `src/api/v2/buyer/_creator_jobs.py` (≤100 LOC) — `schedule_creator_scraping(job_id, coro)` mirror `_proof_jobs.py:schedule_slow_vision`. Strong reference set, startup recovery `recover_stale_creator_jobs_on_startup()`.

### Task 9: apply_creator_verify_impl
**What:** `src/api/v2/buyer/creator_verify.py` — `apply_creator_verify_impl(actor, CreatorVerifyRequest) -> Result[CreatorVerifyResponse, CreatorVerifyError]`. Inline selfie Vision check, INSERT application + job, schedule async, return 202 status.
**Pydantic:** `CreatorVerifyRequest(selfie_base64: str, vk_url: HttpUrl | None, tiktok_url: HttpUrl | None, screenshot_base64: str | None)` with validator: `at least one of vk_url/tiktok_url`.

### Task 10: FastAPI route + bot FSM integration
**What:**
- `src/api/v2/buyer/router.py` — mount `creator_verify_router` (POST `/creator/verify_apply`, GET `/creator/status`).
- `src/domains/buyer/states.py` — add 5 states.
- `src/domains/buyer/handlers/creator_verify.py` (new) — FSM handlers for 5 steps.
- `src/domains/buyer/keyboards/__init__.py` — add `creator_url_keyboard`, `creator_selfie_keyboard`, `creator_consent_keyboard`.
- `src/domains/buyer/locales/ru.yaml` — add `creator.verify.*` keys (10-15 strings).

### Task 11: Migrate blogger.py to ADR-016 + lower threshold
**What:**
- `src/api/v2/buyer/blogger_verify.py` (new) — `verify_blogger_impl` thin wrapper.
- `src/domains/buyer/handlers/blogger.py` — replace direct `buyers_repo.update()` with call to `verify_blogger_impl`.
- `src/domains/buyer/services/blogger_handler.py:59` — `MIN_FOLLOWERS = 1000` → `100`.
- `src/infra/config/constants.py:64` — `BLOGGER_MIN_FOLLOWERS = 1000` → `100`.

### Task 12: Mission Control UI extension
**What:** `src/api/admin/templates/creator_applications.html` (extend FTR-898 file) — add columns selfie thumbnail, URLs, parsed metrics, confidence, method badge. Optimistic lock via `updated_at` ETag. Make `reason` required for `reject`/`needs_info` actions.

### Task 13: 48h SLA + retention cron jobs
**What:**
- `scripts/cron/creator_review_sla.sh` — daily auto-promote borderline past 48h.
- `scripts/cron/creator_selfie_cleanup.sh` — daily DELETE selfies >90d.
- Wire into Supabase edge functions (existing pattern).

### Task 14: Integration tests (mock-ban, ADR-013)
**What:** `tests/integration/test_creator_verify_flow.py` — E2E happy path (URL → selfie → screenshot → consent → 202 → poll → approved). Real DB, mocked external (VK API, Vision API at boundary only).

### Task 15: Eval criteria (LLM judge)
**What:** `ai/.spark/20260501-FTR-909/eval-criteria.md` — 22 deterministic + 7 integration + 4 LLM-judge.

### Task 16: Bulk migrate `is_premium` read sites → `account_kind == 'creator'` (founder ACK 2026-05-01)
**Why:** SSOT collision: после Task 9 + Task 11 в БД одновременно живут `is_premium=True` и `account_kind='creator'` для тех же байеров. Read sites читают `is_premium` — drift при добавлении новых не-blogger creators возможен.
**What:**
- `src/domains/campaigns/repositories/offer_repo.py:115,123,200` — параметр `is_premium: bool` → `account_kind: str | None` (или derived inside via buyer fetch). FTR-170 premium-offer filter переключить на `account_kind != 'creator'` (preserve current behavior + extend для future tiers).
- `src/domains/buyer/services/offers_listing.py:38-59` — `buyer.is_premium` → `buyer.account_kind == 'creator'`.
- `src/domains/buyer/handlers/menu.py:85-89,224,351-355` — `is_premium` → `is_creator = buyer.account_kind == 'creator'`. Variable rename + downstream calls.
- `src/domains/buyer/handlers/offers_view.py:173,201` — `buyer_is_premium` → `buyer_is_creator`. Premium UGC variant gating переключается на `account_kind`.
- `src/domains/buyer/keyboards/menu.py:26-53` — `more_menu_keyboard(is_premium=...)` → `more_menu_keyboard(is_creator=...)`. Signature + caller updates.

### Task 17: Drop `is_premium` writes from blogger handler
**Why:** Task 11 уже мигрирует `blogger.py` на ADR-016 thin adapter. Дополнительно убираем `BuyerUpdate(is_premium=True)` из write path — `verify_blogger_impl` теперь вызывает только `promote_creator_impl(action='approve')`.
**What:**
- `src/domains/buyer/handlers/blogger.py:131` — удалить `is_premium=True` из BuyerUpdate.
- `src/domains/buyer/services/blogger_handler.py:215,229,276,285` — удалить `is_premium` writes (FSM `data["is_premium"]` остаётся как session state, но в БД не пишется).
- Тесты в `tests/unit/test_blogger_handler.py` (Task 0) асертят что `is_premium` НЕ пишется через `BuyerUpdate`.
- `buyers.is_premium` column остаётся в схеме (drop — отдельная TECH-XXX после 2-4 недель мониторинга, что нет регрессий).

---

## Eval Criteria

### Deterministic (18 — pytest assertions)

- **EC-1** Migration wave 6 applied: `\d creator_applications` shows 11 new columns + partial UNIQUE index.
- **EC-2** Migration wave 7 applied: `creator_scraping_jobs` table exists with 8 columns, FK to `creator_applications`.
- **EC-3** Migration wave 8 applied: `creator_applications.status` CHECK includes `pending_scraping`.
- **EC-4** `apply_creator_verify_impl` rejects `vk_url=None AND tiktok_url=None` with `CreatorVerifyError.NO_SOCIAL_URL`.
- **EC-5** `apply_creator_verify_impl` rate-limited via FTR-890 `creator_verify_apply` scope (1/24h per buyer + per ip_hash).
- **EC-6** Inline selfie Vision check: `face_present=False` → instant `status='rejected'` (НЕ создаётся scraping job).
- **EC-7** Inline selfie Vision check: `likely_spoofed=True` → instant reject.
- **EC-8** `StorageService.upload_creator_selfie` writes to `photos/buyers/{buyer_id}/selfie_creator_{ts}.jpg`, returns URL.
- **EC-9** `creator_scraping_jobs` row created with `status='pending'` after successful `apply_creator_verify_impl`.
- **EC-10** `run_creator_scraping_job` idempotency: повторный вызов с `status='completed'` — no-op.
- **EC-11** `run_creator_scraping_job` retry: `attempts >= 3` → `status='failed'` + ops alert.
- **EC-12** Tiered routing: `parsed_follower_count_vk < 100` → `promote_creator_impl(action='reject', reason='min_followers')`.
- **EC-13** Tiered routing: `max(vk_followers, tiktok_followers) >= 500 AND confidence >= 0.95` → `promote_creator_impl(action='approve', actor='cron:creator_scraping_verifier')`.
- **EC-14** Auto-approve sets BOTH `is_premium=True` AND `account_kind='creator'` (additive SSOT).
- **EC-15** Partial UNIQUE: concurrent INSERT `(buyer_id, status='pending')` second fails with PG `unique_violation`.
- **EC-16** `verify_blogger_impl` thin adapter: handler НЕ вызывает `buyers_repo.update()` напрямую.
- **EC-17** `MIN_FOLLOWERS = 100` (was 1000) в `blogger_handler.py:59` AND `constants.py:64`.
- **EC-18** Mission Control `reject`/`needs_info` actions без `reason` → 400.
- **EC-19** Bulk migration: `grep -rn "buyer.is_premium\|\.is_premium" src/domains/ src/api/` returns ZERO matches outside `src/domains/buyer/models.py` (column accessor allowed) и `src/domains/buyer/services/blogger_handler.py` FSM data writes (session-only).
- **EC-20** Bulk migration: `grep -rn "is_premium=True" src/` returns ZERO matches (no application-layer writes).
- **EC-21** `more_menu_keyboard` signature changed `is_premium` → `is_creator` (parameter rename). All callers updated.
- **EC-22** `offer_repo.list_available_offers(is_premium=...)` parameter renamed to `account_kind` (or derived internally). FTR-170 premium-offer filtering preserves current behavior verified by `tests/integration/test_offers_listing.py` regression.

### Integration (7 — real DB, real Storage, mocked VK API + Vision API at boundary)

- **EC-INT-1** Happy path: POST `/creator/verify_apply` → 202 → poll `/creator/status` after job completion → `status='approved'`, `verification_confidence >= 0.9`.
- **EC-INT-2** Auto-reject path: selfie Vision returns `face_present=False` → POST returns 200 with `status='rejected'`, no scraping job created.
- **EC-INT-3** Manual middle band: VK API returns `followers=200` → application stuck в `status='needs_info'`, появляется в Mission Control queue.
- **EC-INT-4** 48h SLA promotion: cron promotes borderline application с `confidence=0.85, count=250` past 48h.
- **EC-INT-5** Retention: cron удаляет `selfie_url` после 90d, `creator_applications.status='approved'`.
- **EC-INT-6** ADR-016 boundary: `tests/architecture/test_mcp_layer.py` passes after blogger.py migration.
- **EC-INT-7** SSOT bulk migration regression: байер с `account_kind='creator'` видит premium UGC variant в offers_view, кнопка "Стать блогером" скрыта в menu, premium-only offers фильтруются корректно — все ранее работавшие через `is_premium` сценарии работают через `account_kind`.

### LLM-judge (4 — quality of Vision prompts + UX text)

- **EC-LLM-1** `SELFIE_VERIFICATION_PROMPT`: judge оценивает 10 reference images (5 real selfies + 5 fakes/AI/screenshots) — recall ≥0.85 на fakes, precision ≥0.9 на reals.
- **EC-LLM-2** `CREATOR_TIKTOK_PROMPT`: judge на 10 reference TikTok screenshots — `follower_count` extraction accuracy ≥85%.
- **EC-LLM-3** Bot UX clarity: judge оценивает onboarding flow text — "пользователь понимает что от него хотят на каждом шаге" ≥4/5.
- **EC-LLM-4** Consent text: judge оценивает соответствие 152-ФЗ требованиям (цель, срок, оператор, способ отзыва) — checklist 5/5.

---

## Allowed Files (whitelist)

Only these files may be modified/created in FTR-909 implementation:

**Migrations:**
- `supabase/migrations/20260501120006_creator_applications_ext.sql`
- `supabase/migrations/20260501120007_creator_scraping_jobs.sql`
- `supabase/migrations/20260501120008_creator_scraping_status_ext.sql`

**API v2 (new + extended):**
- `src/api/v2/buyer/creator_verify.py` (new)
- `src/api/v2/buyer/blogger_verify.py` (new)
- `src/api/v2/buyer/_creator_jobs.py` (new)
- `src/api/v2/buyer/router.py` (mount router)

**Domain layer:**
- `src/domains/buyer/services/creator_scraping.py` (new)
- `src/domains/buyer/services/vision_prompts_creator.py` (new)
- `src/domains/buyer/services/blogger_handler.py` (MIN_FOLLOWERS 1000→100 + drop `is_premium` writes per Task 17)
- `src/domains/buyer/services/offers_listing.py` (Task 16: is_premium → account_kind read)
- `src/domains/buyer/handlers/menu.py` (Task 16: is_premium → is_creator rename)
- `src/domains/buyer/handlers/offers_view.py` (Task 16: buyer_is_premium → buyer_is_creator)
- `src/domains/buyer/keyboards/menu.py` (Task 16: more_menu_keyboard signature)
- `src/domains/campaigns/repositories/offer_repo.py` (Task 16: list_available_offers param rename + filter logic)
- `src/domains/buyer/handlers/creator_verify.py` (new)
- `src/domains/buyer/handlers/blogger.py` (migrate to thin adapter)
- `src/domains/buyer/states.py` (add 5 states)
- `src/domains/buyer/keyboards/__init__.py` (3 new keyboards)
- `src/domains/buyer/locales/ru.yaml` (creator.verify.* + creator.consent.*)

**Infra:**
- `src/infra/external/social/vk_client.py` (new)
- `src/infra/external/social/__init__.py` (new)
- `src/infra/storage/service.py` (add upload_creator_selfie)
- `src/infra/config/constants.py` (BLOGGER_MIN_FOLLOWERS 1000→100)

**Admin/Mission Control:**
- `src/api/admin/templates/creator_applications.html` (extend FTR-898 file)
- `src/api/v2/admin/creator.py` (extend reason-required validation)

**Cron:**
- `scripts/cron/creator_review_sla.sh` (new)
- `scripts/cron/creator_selfie_cleanup.sh` (new)

**Tests:**
- `tests/unit/test_blogger_handler.py` (new — Task 0)
- `tests/unit/test_creator_scraping.py` (new)
- `tests/unit/test_vision_prompts_creator.py` (new)
- `tests/integration/test_creator_verify_flow.py` (new, ADR-013 mock-ban, real DB)
- `tests/architecture/test_mcp_layer.py` (no edits needed; should pass after blogger.py migration)

**Glossary + docs:**
- `ai/glossary/buyer.md` (add creator_scraping_job, selfie_url, verification_method terms)
- `ai/.spark/20260501-FTR-909/eval-criteria.md` (new)

**Forbidden:**
- `tests/contracts/`, `tests/regression/` — never modify
- `src/domains/seller/orchestrator.py` — `analyze_social_profile` tool name string is correct
- `src/infra/config/timers.py` — rebalance territory, stay away
- `vision_prompts.py` — already 515 LOC over limit; do not extend, use new `vision_prompts_creator.py`
- `supabase/migrations/*` — НЕ дропать `buyers.is_premium` column в FTR-909 (drop отдельная TECH-XXX после 2-4 недель мониторинга)
- `src/domains/buyer/handlers/onboarding.py` — already 578 LOC over limit; new states go to `creator_verify.py` handler

---

## Risk Profile

| Layer | Risk | Likelihood | Mitigation |
|-------|------|------------|------------|
| Schema | R0 (additive, drop-column rollback safe) | Low | All migrations CONCURRENTLY where applicable; ADR-018 compliant |
| 152-ФЗ selfie | R1 (legal exposure if region non-RU) | Medium | ACTION REQUIRED #1 (storage region check); 90-day retention cron; standard PD consent text |
| VK API ToS | R1 (service token rate limit / key revoke) | Low | Service token (not user token) is allowed for public profile data per VK ToS; rate limit 3/20 RPS handled via async queue |
| TikTok scraping | R2 (Vision OCR is creator-uploaded screenshot, no scraping ToS issue) | Low | OCR fallback only; no automated scraping of tiktok.com |
| `is_premium` SSOT | R1 (additive write — both flags set, 5 call sites unchanged) | Low | Documented decision; future TECH spec to deprecate |
| Operator overload | R1 (5000/мес × 20% manual = ~33/day per operator) | Low | Tiered moderation reduces queue 80%; SLA cron auto-promotes borderline |
| Vision API cost | R2 ($25-50/мес at 5000 selfie+screenshot calls) | Low | Gemini Flash pricing; budget tracked in EC-LLM-1/2 |
| Async job race | R1 (proof_jobs pattern proven via TECH-891) | Low | Mirror battle-tested pattern; idempotency + retry |
| FTR-898 dependency | R1 (FTR-898 must merge first) | High | Explicit prerequisite gate в Status; backlog ordering |

---

## Dependencies

- **Hard:** FTR-898 (creator_applications, account_kind, promote_creator_impl) merged first
- **Hard:** FTR-897 (onboarding_events, consents helpers, _insert_consent / _insert_onboarding_event) merged first
- **Soft:** FTR-872 morning digest infra (notifications priority=high)
- **Soft:** FTR-890 rate limit middleware (creator_verify_apply scope)
- **Soft:** TECH-891 proof_jobs recovery pattern (template для creator_scraping_jobs recovery)

---

## Cross-References

- **FTR-897** — External Traffic Onboarding MVP (parent migration wave, onboarding_events, consents reuse)
- **FTR-898** — Creator Onboarding MVP (architectural layer: account_kind, role mechanics, promote_creator_impl SSOT)
- **FTR-872** — Morning digest notification infra
- **FTR-890** — Rate limit middleware
- **TECH-891** — proof_jobs recovery pattern
- **FTR-162 / FTR-437** — original blogger handler (legacy, migrated to ADR-016 in Task 11)

---

## Cost Model (5000 креаторов/мес)

| Component | Method | Cost/unit | Volume | $/мес |
|-----------|--------|-----------|--------|-------|
| Selfie Vision check | Gemini Flash | $0.001 | 5000 | ~$5 |
| TikTok OCR | Gemini Flash, 1-2 screenshots | $0.003 | 5000 | ~$15 |
| VK API metrics | Official API service token | $0 | 4000 (80% VK audience) | $0 |
| Selfie storage | Supabase Storage | $0.021/GB | 10 GB | ~$0.21 |
| Manual moderation (~20% queue) | $1/case operator time | 1000 cases | ~$1000 |
| **Infra total** | | | | **~$20-25** |
| **Total с manual** | | | | **~$1020-1025** |

При scale до 50,000 (10x campaign): ~$200 infra + $10000 operator (требует 1 dedicated moderator).

---

## Notes

- **Spark session:** `ai/.spark/20260501-FTR-909/` (state.json, research-{external,codebase,patterns,devil}.md, synthesis.md)
- **Research lead time:** VK app registration не требуется (service token доступен сразу для public profile data per VK ToS).
- **152-ФЗ resolution:** External scout researched Constitutional Court precedent — passive face presence check ≠ биометрия per Определение № 2298-О / 2023.
- **Devil's caveats addressed:** Tiered moderation (Devil's #1 concern), partial UNIQUE migration (Devil's data integrity #4), `reason` required for reject (Devil's UX #6), 48h SLA cron (Devil's operational #4), is_premium dual-write SSOT clarification (Devil's #2).
- **Boy Scout Rule:** Migration of legacy blogger.py to ADR-016 thin adapter is bundled (Task 11) since FTR-909 already touches the blogger flow. Avoids "starts many, finishes few" anti-pattern.
