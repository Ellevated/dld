# Architecture: [ARCH-147] Full Monetization User Journey — Blueprint

**Status:** done | **Priority:** P0 | **Date:** 2026-02-16
**Type:** Blueprint (master map, NOT an execution spec)

## Purpose

Полная карта пути пользователя от регистрации до многолетнего подписчика. Каждый touchpoint привязан к execution-спеке. Этот документ — SSOT для всех решений по монетизации.

---

## Decision Log

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Free tier limits | **5 payments, 1 card** (was 10/1) | Drives faster conversion; 10 too generous for finance app |
| 2 | Trial period | **No trial** — pure freemium | Already tightening limits; trial adds complexity |
| 3 | Primary upgrade trigger | **Inline feature gates** at point of use | 15-20% CTR vs 2-3% for settings page (research data) |
| 4 | Cancellation flow | **Full 4-step salvage** (pause, discount, survey, confirm) | Saves 15-30% of cancellation attempts |
| 5 | Dunning | **Full sequence** (email/TG, 14-day grace, in-app banner) | Recovers 17%+ of failed payments |
| 6 | Refund policy | **7-day money-back** via UI + salvage flow | Trust signal, Russian market standard |
| 7 | Spec structure | **Blueprint + 5 execution specs** | Manageable autopilot chunks |

---

## Pricing

| Plan | Price | Period | Notes |
|------|-------|--------|-------|
| Free | 0 ₽ | forever | 5 payments, 1 card, basic dashboard |
| Pro Monthly | 299 ₽/мес | 30 days | Unlimited everything |
| Pro Yearly | 2 990 ₽/год | 365 days | "2 месяца бесплатно" (17% экономия) |

**SSOT:** `supabase/functions/_shared/billing/plans.ts`

---

## Complete User Journey

### Stage 0: Discovery → Sign-Up

```
Landing page (/):
  └── Pricing section (3 cards: Free / Pro Monthly / Pro Yearly)
       └── All CTAs → /sign-up
            └── Clerk sign-up
                 └── Referral survey (onboarding)
                      └── → /dashboard (Free plan, 0 payments)
```

**Touchpoints:**
- Pricing section clearly shows Free vs Pro differences
- "2 месяца бесплатно" badge on yearly plan
- Social proof: "X users trust PLPilot"
- **Spec:** FTR-152 (Billing UX Overhaul)

---

### Stage 1: Free Tier — Building Value (Days 1-14)

```
User adds payments:
  ├── Payment 1-3: Full access, no friction
  ├── Payment 4: Subtle hint "Осталось 1 платёж на бесплатном плане"
  └── Payment 5: Last one added successfully
       └── Payment 6 attempt → HARD GATE
            └── Modal: "Лимит 5 платежей. Перейди на Pro для безлимита"
                 └── [Перейти на Pro] → UpgradeDialog
                 └── [Позже] → dismiss

User tries locked features:
  ├── Receipt OCR scan → HARD GATE after 3 scans/month
  │    └── "Безлимитное сканирование в Pro"
  ├── Calendar view → SOFT GATE (blurred preview + overlay)
  │    └── "Полный календарь платежей в Pro"
  ├── Reports → SOFT GATE (blurred charts)
  │    └── "Детальная аналитика в Pro"
  └── Multi-currency → SOFT GATE
       └── "Автоматическая конвертация в Pro"
```

**Free tier limits (SSOT):**

| Feature | Free | Pro |
|---------|------|-----|
| Active payments | 5 | Unlimited |
| Cards | 1 | Unlimited |
| Receipt OCR | 3/month | Unlimited |
| Calendar | Blurred preview | Full access |
| Reports | Blurred preview | Full access |
| Multi-currency | Manual only | Auto exchange rates |
| AI negotiation | 1/month | Unlimited |
| Telegram reminders | Basic | Advanced (custom schedule) |
| What If? simulator | 1/month | Unlimited |

**"Aha moment" triggers (server-tracked):**

| Event | Threshold | Action |
|-------|-----------|--------|
| Payments added | 4 of 5 | In-app hint: "Осталось 1 слот" |
| Payments added | 5 of 5 (limit hit) | Upgrade modal on next attempt |
| Receipt scans | 3 of 3 | "Безлимитное сканирование в Pro" |
| Calendar views | 3+ visits | Inline CTA in calendar |
| Days of usage | 7 | Dashboard banner: "You saved ₽X. Go Pro for more" |
| Days of usage | 14 | Telegram message: "14 дней с PLPilot! Попробуй Pro" |

**Spec:** FTR-148 (Free Tier Limits & Feature Gates)

---

### Stage 2: Decision to Pay

```
User decides to upgrade (multiple entry points):
  ├── Inline feature gate modal → [Перейти на Pro]
  ├── Dashboard banner → [Подробнее]
  ├── Sidebar "Free" badge → click → /settings/billing
  ├── Settings > Billing > [Перейти на Pro]
  └── Telegram bot → /upgrade → deep link to /settings/billing

All paths lead to:
  └── UpgradeDialog
       ├── Phase 1: Plan selection
       │    ├── Pro Monthly — 299 ₽/мес [Оплатить]
       │    └── Pro Yearly — 2 990 ₽/год (экономия 17%) [Оплатить]
       ├── Phase 2: YooKassa Widget (embedded checkout)
       │    ├── Bank card (Mir, Visa, MC)
       │    ├── SberPay
       │    ├── YooMoney
       │    └── FPS
       └── Phase 3: Result handling
            ├── Success → "Добро пожаловать в Pro!" → Pro onboarding
            ├── Fail → "Оплата не прошла. Попробуйте снова" → retry
            └── Pending → "Обрабатывается..." → polling
```

**Trust signals on payment screen:**
- "Отменить можно в любой момент"
- "Гарантия возврата 7 дней"
- YooKassa logo (trusted in Russia)
- "Безопасная оплата" lock icon

**Spec:** BUG-145 (payment flow fix — already queued)

---

### Stage 3: Post-Purchase — Pro Onboarding

```
Payment succeeds:
  └── UpgradeDialog shows "Добро пожаловать в Pro! 🎉"
       └── Quick tour (3 steps):
            ├── "Теперь у тебя безлимитные платежи — добавь остальные"
            ├── "Попробуй сканирование чеков с AI"
            └── "Загляни в календарь — все платежи на одном экране"
       └── [Начать] → close dialog, dashboard updated

Background:
  ├── Webhook updates user_subscriptions → Pro
  ├── billing_history record created
  ├── payment_method_id saved (for auto-renewal)
  ├── Telegram notification: "Подписка Pro активирована! Следующее продление {date}"
  └── Email: receipt + getting started guide
```

**Spec:** FTR-152 (Billing UX Overhaul — post-purchase section)

---

### Stage 4: Active Pro User (Days 1-365)

```
Daily experience:
  ├── Sidebar badge: "Pro" (crown icon)
  ├── All features unlocked
  ├── Dashboard shows value: "Вы сэкономили ₽X с Pro"
  └── No upgrade prompts (clean experience)

Settings > Billing shows:
  ├── Текущий план: Pro Monthly / Pro Yearly
  ├── Следующее продление: {date} — {amount}
  ├── Способ оплаты: •••• 1234 (Tinkoff) [Обновить]
  ├── [Сменить план] (monthly ↔ yearly, with proration)
  ├── [Отменить подписку]
  └── История платежей (table)
```

**Monthly value reinforcement:**
- Telegram summary: "В этом месяце PLPilot помог отследить {N} платежей на ₽{X}"
- Dashboard widget: running savings counter

**Spec:** FTR-146 (Subscription Lifecycle) + FTR-152 (Billing UX)

---

### Stage 5: Auto-Renewal

```
7 days before renewal:
  └── Telegram: "Подписка продлится {date} за {amount}. Всё ок?"
       └── [Ок] [Отменить подписку]

Renewal day (06:00 UTC cron):
  ├── createRecurringPayment() via saved payment_method_id
  ├── Success:
  │    ├── Update current_period_start/end
  │    ├── billing_history record
  │    └── Telegram: "Подписка продлена до {date}. Спасибо!"
  └── Failure → DUNNING FLOW (Stage 6)
```

**Spec:** FTR-146 (Subscription Lifecycle — renewal cron)

---

### Stage 6: Failed Payment — Dunning Flow

```
Day 0: Payment fails
  ├── Status → 'past_due'
  ├── Silent retry (often succeeds — card network issues)
  └── Telegram: "Не удалось продлить подписку. Обновите способ оплаты."
       └── [Обновить оплату] → deep link to /settings/billing

Day 1: Second retry + email
  └── Email: "Оплата не прошла — обновите карту"
       └── One-click link to update payment method

Day 3: Third retry + urgent notification
  ├── Telegram: "⚠️ Подписка истекает через 11 дней. Обновите оплату."
  └── In-app banner (persistent, yellow): "Проблема с оплатой — обновите способ оплаты"
       └── [Обновить] → payment method update flow

Day 7: Grace period starts
  ├── Pro features STILL ACTIVE (goodwill)
  ├── Telegram: "Последняя попытка оплаты не удалась. У вас 7 дней."
  └── In-app banner (persistent, red): "Pro истекает через 7 дней"

Day 14: Grace period ends → downgrade
  ├── Status → 'canceled', plan → 'free'
  ├── Telegram: "Подписка отменена. Ваши данные сохранены."
  │    └── "Вернуться на Pro со скидкой 25%? /reactivate"
  ├── Email: "Ваш Pro закончился"
  │    └── Reactivation CTA with discount
  └── In-app: Plan badge → "Free", features gated again
       └── Dashboard banner: "Вернитесь на Pro — скидка 25% на первый месяц"
```

**Grace period rules:**
- 14 days total (Day 0-14)
- Pro features stay active during grace (builds goodwill)
- 3 retry attempts (Day 0, 1, 3) with exponential backoff
- After Day 14: hard downgrade, no further retries

**Spec:** FTR-150 (Full Dunning & Grace Period)

---

### Stage 7: Voluntary Cancellation — Salvage Flow

```
User clicks "Отменить подписку":
  └── 4-Step Salvage Sequence:

Step 1: PAUSE OFFER
  "Может, просто пауза? Подписка заморозится на 1-3 месяца."
  ├── [Пауза на 1 мес] → pause subscription, keep payment method
  ├── [Пауза на 3 мес] → pause subscription
  └── [Нет, отменить] → Step 2

Step 2: FEEDBACK SURVEY
  "Помогите нам стать лучше. Почему вы уходите?"
  ├── Слишком дорого → Step 3a (discount offer)
  ├── Не пользуюсь → Step 3b (pause reminder)
  ├── Не хватает функций → Step 3c (roadmap preview)
  ├── Нашёл альтернативу → Step 3d (competitive comparison)
  └── Другое (text field) → Step 3e (generic)

Step 3: PERSONALIZED OFFER
  3a (price): "Скидка 25% на 3 месяца — 224 ₽/мес вместо 299 ₽"
       ├── [Принять скидку] → apply discount, keep Pro
       └── [Нет, спасибо] → Step 4
  3b (not using): "Попробуйте паузу? Ваши данные сохранятся."
       ├── [Поставить на паузу] → pause
       └── [Нет, отменить] → Step 4
  3c (features): "Мы работаем над {feature}. Хотите ранний доступ?"
       ├── [Хочу ранний доступ] → flag user, keep Pro
       └── [Нет, отменить] → Step 4
  3d (alternative): "Мы отслеживаем {N} платежей бесплатно. Сравните:"
       ├── [Остаться] → keep Pro
       └── [Отменить] → Step 4
  3e (other): "Спасибо за отзыв."
       └── → Step 4

Step 4: FINAL CONFIRMATION
  "Вы уверены? После {date} вы потеряете:"
  ├── ✗ Безлимитные платежи (сейчас {N})
  ├── ✗ Сканирование чеков
  ├── ✗ Полный календарь
  ├── ✗ Детальные отчёты
  └── "Ваши данные сохранятся, но доступ к Pro-функциям закроется."
       ├── [Оставить Pro] → cancel flow, keep subscription
       └── [Да, отменить] → cancel_at_period_end = true
            └── Telegram: "Подписка отменена. Активна до {date}."
            └── "Передумали? Вы можете возобновить в любой момент."
```

**Post-cancellation state:**
- Pro features active until `current_period_end`
- Billing page shows: "Подписка будет отменена {date}" + [Возобновить]
- Sidebar badge: "Pro" with countdown indicator

**Spec:** FTR-149 (Cancellation Salvage & 7-Day Refund)

---

### Stage 7b: Refund Request

```
Within 7 days of FIRST payment:
  Settings > Billing > [Запросить возврат]
  └── Salvage attempt first:
       "Прежде чем вернуть деньги — может, стоит попробовать ещё?"
       ├── [Дайте мне ещё неделю] → extend Pro, reset 7-day window
       └── [Нет, верните деньги] → Refund confirmation
            └── "Возврат 299 ₽ будет обработан в течение 5-7 дней"
                 ├── YooKassa refund API → refund.succeeded webhook
                 ├── Immediate downgrade to Free
                 ├── billing_history: negative record
                 └── Telegram: "Возврат ₽299 оформлен. Деньги вернутся на карту."

After 7 days:
  └── [Запросить возврат] → "Свяжитесь с support@plpilot.ru"
```

**Refund eligibility:**
- First payment only (not renewals)
- Within 7 calendar days
- Automatic via UI (no support tickets)
- One refund per user (anti-abuse)

**Spec:** FTR-149 (Cancellation Salvage & 7-Day Refund)

---

### Stage 8: Churned User — Win-Back

```
After cancellation/downgrade:

Day 0: Cancellation confirmed
  └── Email: "Мы будем скучать. Ваши данные в безопасности."

Day 30: First win-back
  ├── Email: "Что нового в PLPilot: {feature updates}"
  │    └── "Вернитесь на Pro — 50% на первый месяц"
  │    └── [Вернуться на Pro] → /settings/billing?offer=comeback50
  └── Telegram: "Привет! У нас новый {feature}. Попробуйте Pro снова?"

Day 60: Feature-focused
  ├── Email: "Вы пропускаете: {personalized stats}"
  │    └── "У вас {N} платежей без контроля. Pro всё исправит."
  │    └── [1 месяц бесплатно] → /settings/billing?offer=free30
  └── In-app (if user visits): Banner "Скучаем! Скидка 50% ждёт вас"

Day 90: Final offer
  ├── Email: "Последнее предложение: 3 месяца по цене 1"
  │    └── 299 ₽ за 3 месяца (99 ₽/мес)
  └── After Day 90: Stop outreach (respect user choice)

Trigger-based reactivation (any time):
  ├── User adds 5th payment → "Упёрлись в лимит? Pro решит это"
  ├── User visits 3+ times in a week → "Вы активный пользователь — Pro для вас"
  └── Major feature launch → one-time email to all churned users
```

**Win-back discount tiers:**

| Day | Offer | Code | Duration |
|-----|-------|------|----------|
| 30 | 50% off first month | COMEBACK50 | 30 days |
| 60 | 1 month free | FREE30 | 30 days |
| 90 | 3 months for price of 1 | TRIPLE90 | 7 days |

**Spec:** FTR-151 (Win-Back & Re-engagement)

---

### Stage 9: Long-term Pro User (Year 1+)

```
Annual touchpoints:
  ├── Anniversary: "1 год с PLPilot Pro! Вы сэкономили ₽{X}"
  │    └── Achievement unlock: "Veteran" badge
  ├── Yearly plan reminder (if monthly):
  │    └── "Переход на годовой план экономит ₽798/год"
  │    └── [Перейти на годовой] → plan change with proration
  ├── Feature launches: Early access notification
  └── Referral program: "Пригласите друга — получите месяц бесплатно"

Ongoing value reinforcement:
  ├── Monthly Telegram summary with savings metrics
  ├── Achievement unlocks (streak, savings milestones)
  └── Dashboard: cumulative savings counter
```

**Retention signals to monitor:**
- Login frequency (weekly active)
- Feature usage depth (OCR, calendar, reports)
- Payment tracking accuracy (missed vs caught)
- Engagement with Telegram bot

**Spec:** Outside current scope (future FTR)

---

## Spec Dependency Chain

```
                    ┌─────────────┐
                    │  ARCH-147   │ ← You are here (Blueprint)
                    │  Blueprint  │
                    └──────┬──────┘
                           │
              ┌────────────┼─────────────┐
              │            │             │
              ▼            ▼             ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ BUG-145  │ │ FTR-148  │ │ FTR-152  │
        │ Payment  │ │ Free Tier│ │ Billing  │
        │ Flow Fix │ │ & Gates  │ │ UX       │
        └────┬─────┘ └──────────┘ └──────────┘
             │         (independent)  (independent)
             ▼
        ┌──────────┐
        │ FTR-146  │
        │ Lifecycle│
        │ Backend  │
        └────┬─────┘
             │
     ┌───────┼────────┐
     ▼       ▼        ▼
┌────────┐┌────────┐┌────────┐
│FTR-149 ││FTR-150 ││FTR-151 │
│Salvage ││Dunning ││Win-Back│
│+Refund ││+Grace  ││        │
└────────┘└────────┘└────────┘
```

**Execution order:**

| Phase | Spec | Can start | Depends on |
|-------|------|-----------|------------|
| 1 | BUG-145 Payment flow fix | NOW | nothing |
| 1 | FTR-148 Free tier & gates | NOW | nothing (independent) |
| 1 | FTR-152 Billing UX overhaul | NOW | nothing (independent) |
| 2 | FTR-146 Subscription lifecycle | After BUG-145 | BUG-145 |
| 3 | FTR-149 Cancellation salvage + refund | After FTR-146 | FTR-146 (cancel API) |
| 3 | FTR-150 Full dunning + grace | After FTR-146 | FTR-146 (renewal cron) |
| 4 | FTR-151 Win-back & re-engagement | After FTR-149 | FTR-149 (churned users exist) |

---

## Spec Index

| ID | Title | Status | Scope |
|----|-------|--------|-------|
| **ARCH-147** | Monetization Blueprint (this doc) | queued | Master map |
| **BUG-145** | Payment flow fix (webhook + widget events) | queued | Backend + frontend payment |
| **FTR-146** | Subscription lifecycle (renewal, cancel API, expiration) | queued | Backend infrastructure |
| **FTR-148** | Free tier tightening & inline feature gates | draft | Limits + paywalls |
| **FTR-149** | Cancellation salvage & 7-day refund | draft | 4-step retention + refund |
| **FTR-150** | Full dunning & grace period | draft | Failed payment recovery |
| **FTR-151** | Win-back & re-engagement | draft | Churned user campaigns |
| **FTR-152** | Billing UX overhaul | draft | Pricing page + CTAs + post-purchase |

---

## Metrics to Track

| Metric | Target | How to measure |
|--------|--------|----------------|
| Freemium → Pro conversion | 5-7% | (Pro signups / total signups) per month |
| Monthly churn | <8% | (Canceled / Total Pro) per month |
| Involuntary churn | <3% | (Failed renewals / Total renewals) per month |
| Salvage rate (cancellation) | 15-30% | (Salvaged / Cancel attempts) per month |
| Dunning recovery rate | 17%+ | (Recovered / Failed payments) per month |
| Win-back reactivation | 5-10% | (Reactivated / Churned) within 90 days |
| 7-day refund rate | <5% | (Refunds / New Pro) per month |
| Annual plan adoption | >30% | (Yearly / Total Pro) ratio |
| LTV | ₽4,500+ | ARPU x (1 / churn rate) |

---

## Research Sources

- Exa Deep Research: SaaS monetization 2025-2026 (178 pages, 44 searches)
- ChartMogul SaaS Conversion Report 2026
- Stripe Freemium Business Model Guide
- Paddle State of Subscription Apps 2025
- FirstPageSage SaaS Freemium Conversion Rates 2026
- Churnkey State of Retention Report 2025
- YooKassa Widget & Recurring Payments docs
- Russian Consumer Protection Law (Federal Law 2300-1)
- Sberbank Russia Consumer Trends 2025
- PLPilot codebase audit (Explore agent, 36 tool uses)
