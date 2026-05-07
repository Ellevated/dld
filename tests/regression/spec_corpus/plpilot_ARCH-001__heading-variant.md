# ARCH-001: PLPilot Project Roadmap

**Status:** done
**Created:** 2026-02-07
**Type:** Architecture / Roadmap

---

## Research Summary

### Tech Decisions (backed by research)

| Decision | Choice | Why |
|----------|--------|-----|
| TG Bot Framework | **grammY** | TypeScript-first, активная разработка (v1.39+), встроенный webhook для serverless, plugin conversations для диалогов, официальный гайд Supabase Edge Functions |
| Backend | **Supabase Edge Functions** (Deno) | Free tier 500K вызовов/мес, TypeScript, рядом с БД, pg_cron для расписания напоминалок |
| AI Provider | **OpenRouter** (`@openrouter/sdk`) | Официальный TS SDK, structured output (json_schema), auto-routing к дешёвым провайдерам, prompt caching (до 90% экономии) |
| OCR Model | **Gemini 2.0 Flash** (primary) / **Claude 3.5 Sonnet** (fallback) | Gemini Flash — самая популярная модель для structured output на OpenRouter (1.6M req/week), дешёвая. Claude — точнее на сложных чеках |
| NLP Model | **Claude 3.5 Sonnet** через OpenRouter | Лучшее понимание контекста, поддержка русского языка |
| Auth | **Clerk** (native Supabase integration) | Уже настроен в проекте. С апреля 2025 — нативная интеграция Clerk+Supabase (не JWT template). RLS через `auth.jwt()->>'sub'` |
| Storage | **Supabase Storage** | 1GB free, RLS для доступа, рядом с БД |
| CRON | **pg_cron + pg_net** | Расписание напоминалок прямо из PostgreSQL, вызывает Edge Functions по расписанию |
| State (frontend) | **Zustand slices** + **TanStack Query** | Slices для модульности (payments, cards, tags). TQ для серверного состояния + optimistic updates |
| DB Schema | **Деньги в центах** (int), enum для статусов и периодов | ADR-001, избежание float precision errors |

---

## Database Schema (core tables)

```sql
-- Карты
create table cards (
  id uuid primary key default gen_random_uuid(),
  user_id text not null default (auth.jwt()->>'sub'),
  name text not null,              -- "Тинькофф Visa"
  last_four text,                  -- "4242"
  color text,                      -- для UI
  created_at timestamptz default now()
);

-- Теги
create table tags (
  id uuid primary key default gen_random_uuid(),
  user_id text not null default (auth.jwt()->>'sub'),
  name text not null,              -- "работа", "семья"
  color text,
  created_at timestamptz default now()
);

-- Платежи (ядро)
create table payments (
  id uuid primary key default gen_random_uuid(),
  user_id text not null default (auth.jwt()->>'sub'),
  name text not null,              -- "Netflix", "Ипотека"
  amount_cents int not null,       -- в центах/копейках
  currency text not null default 'RUB', -- RUB, USD, EUR
  period text not null,            -- monthly, yearly, quarterly, weekly, custom
  period_days int,                 -- для custom периодов
  next_payment_date date not null,
  end_date date,                   -- null = бессрочный
  card_id uuid references cards(id),
  is_active boolean default true,
  notes text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Связка платежей и тегов (many-to-many)
create table payment_tags (
  payment_id uuid references payments(id) on delete cascade,
  tag_id uuid references tags(id) on delete cascade,
  primary key (payment_id, tag_id)
);

-- Чеки
create table receipts (
  id uuid primary key default gen_random_uuid(),
  user_id text not null default (auth.jwt()->>'sub'),
  payment_id uuid references payments(id),
  storage_path text not null,      -- путь в Supabase Storage
  raw_ai_response jsonb,           -- сырой ответ AI для дебага
  created_at timestamptz default now()
);

-- Напоминалки
create table reminders (
  id uuid primary key default gen_random_uuid(),
  payment_id uuid references payments(id) on delete cascade,
  remind_at timestamptz not null,
  status text default 'pending',   -- pending, sent, acknowledged, snoozed
  telegram_message_id bigint,      -- для обновления сообщения
  created_at timestamptz default now()
);

-- RLS policies
alter table cards enable row level security;
alter table tags enable row level security;
alter table payments enable row level security;
alter table payment_tags enable row level security;
alter table receipts enable row level security;
alter table reminders enable row level security;

-- Пример RLS policy (для всех таблиц аналогично)
create policy "Users can manage own cards"
  on cards for all to authenticated
  using ((select auth.jwt()->>'sub') = user_id)
  with check ((select auth.jwt()->>'sub') = user_id);
```

---

## Roadmap

### Phase 1: Foundation (TECH)

**Цель:** Рабочий скелет — БД, авторизация, базовый API, деплой.

| ID | Task | Description |
|----|------|-------------|
| TECH-001 | Настроить Supabase проект | Создать проект, подключить Clerk native integration, настроить RLS |
| TECH-002 | Создать схему БД | Миграции для всех core таблиц (cards, tags, payments, receipts, reminders) |
| TECH-003 | Настроить Supabase Edge Functions | Базовый hello-world function, shared Supabase client, деплой |
| TECH-004 | Подключить фронт к Supabase | Supabase client с Clerk accessToken, TanStack Query hooks |
| TECH-005 | Очистить шаблон | Убрать demo-страницы shadcn-admin, оставить layout + auth |
| TECH-006 | CI/CD | Vercel деплой фронта, Supabase CLI для миграций и Edge Functions |

### Phase 2: Core CRUD (FTR)

**Цель:** Можно руками добавлять/редактировать платежи, карты, теги через веб.

| ID | Task | Description |
|----|------|-------------|
| FTR-001 | CRUD карт | Страница управления картами (создать, редактировать, удалить) |
| FTR-002 | CRUD тегов | Управление тегами с цветами |
| FTR-003 | CRUD платежей | Форма платежа: имя, сумма, валюта, период, карта, теги, дата |
| FTR-004 | Список платежей | Таблица с фильтрами (по карте, тегу, статусу), сортировка |

### Phase 3: Telegram Bot + AI (FTR)

**Цель:** Бот распознаёт чеки и управляет платежами через естественный язык.

| ID | Task | Description |
|----|------|-------------|
| FTR-005 | Telegram Bot: scaffold | grammY + webhook на Supabase Edge Function, регистрация бота |
| FTR-006 | Привязка TG аккаунта | Связка Telegram user → Clerk user (deep link или код) |
| FTR-007 | AI Receipt Scanner | Фото/скрин → OpenRouter (Gemini Flash) → structured JSON → предложение сохранить |
| FTR-008 | AI Conversational Assistant | NLP-команды: "сколько в этом месяце?", "покажи подписки по работе", "добавь платёж" |
| FTR-009 | Хранение чеков | Загрузка в Supabase Storage, привязка к платежу, просмотр в вебе |

### Phase 4: Notifications (FTR)

**Цель:** Напоминалки работают, пени больше не грозят.

| ID | Task | Description |
|----|------|-------------|
| FTR-010 | Система напоминалок | pg_cron job → проверяет reminders → отправляет в ТГ |
| FTR-011 | Действия на напоминалках | Inline кнопки: "Оплатил", "Отложить на день", "Пропустить" |
| FTR-012 | Авто-создание напоминалок | При сохранении платежа — автоматически создавать reminder на next_payment_date - 1 день |
| FTR-013 | Сдвиг next_payment_date | После подтверждения оплаты — автоматически сдвигать на следующий период |

### Phase 5: Dashboard (FTR)

**Цель:** Воскресный сценарий — "сколько куда положить".

| ID | Task | Description |
|----|------|-------------|
| FTR-014 | Сводка по картам | Главная страница: "На следующей неделе: Тинькофф — 3,200₽, Сбер — 2,100₽, Revolut — €9.99" |
| FTR-015 | Календарь платежей | Визуальный календарь с метками платежей |
| FTR-016 | Отчёт по месяцам | Recharts: расходы по месяцам, трендовая линия |
| FTR-017 | Отчёт по тегам | Pie chart: распределение расходов по тегам |
| FTR-018 | Отчёт по картам | Bar chart: расходы по картам |

### Phase 6: Polish (TECH/FTR)

**Цель:** Продукт приятно использовать каждый день.

| ID | Task | Description |
|----|------|-------------|
| FTR-019 | Мультивалютная сводка | Показ общей суммы в базовой валюте (с курсами) |
| FTR-020 | PWA | Manifest, service worker, иконка — для добавления на телефон |
| TECH-007 | Error handling | Глобальная обработка ошибок, retry, offline support |
| TECH-008 | Seed data | Скрипт для наполнения тестовыми данными |

---

## Tech Stack (final)

```
Frontend:
  React 19 + Vite 7 + TypeScript
  TanStack Router (file-based routing)
  TanStack Query (server state)
  Zustand (client state, slices pattern)
  shadcn/ui (new-york) + Tailwind 4
  Recharts (graphs)
  React Hook Form + Zod (forms)
  Clerk (auth)

Backend:
  Supabase PostgreSQL (database)
  Supabase Edge Functions (Deno, API + TG webhook)
  Supabase Storage (receipt images)
  pg_cron + pg_net (scheduled reminders)

AI:
  OpenRouter (@openrouter/sdk)
  Gemini 2.0 Flash (OCR, structured output)
  Claude 3.5 Sonnet (NLP assistant, complex receipts)

Telegram:
  grammY (TypeScript, webhook mode)
  Conversations plugin (multi-step dialogs)
  Session middleware (Supabase-backed)

Deploy:
  Vercel (frontend SPA)
  Supabase Cloud (backend, free tier)
```

---

## Key Implementation Patterns

### 1. Clerk + Supabase (native integration)
```typescript
// Frontend: Supabase client with Clerk token
import { createClient } from '@supabase/supabase-js'
import { useAuth } from '@clerk/clerk-react'

function useSupabaseClient() {
  const { getToken } = useAuth()
  return createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    async accessToken() {
      return await getToken()
    },
  })
}
```

### 2. grammY webhook on Supabase Edge Function
```typescript
// supabase/functions/telegram-webhook/index.ts
import { Bot, webhookCallback } from "https://deno.land/x/grammy/mod.ts"

const bot = new Bot(Deno.env.get("BOT_TOKEN")!)

bot.on("message:photo", async (ctx) => {
  // Receipt scanning flow
})

bot.on("message:text", async (ctx) => {
  // NLP assistant flow via OpenRouter
})

const handleUpdate = webhookCallback(bot, "std/http")
Deno.serve(async (req) => {
  return await handleUpdate(req)
})
```

### 3. OpenRouter Receipt Scanning
```typescript
import OpenRouter from '@openrouter/sdk'

const openrouter = new OpenRouter({ apiKey: OPENROUTER_API_KEY })

const result = await openrouter.chat.completions.create({
  model: 'google/gemini-2.0-flash',
  response_format: {
    type: 'json_schema',
    json_schema: { name: 'receipt', schema: receiptSchema }
  },
  messages: [{
    role: 'user',
    content: [
      { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${base64}` } },
      { type: 'text', text: 'Extract payment data from this receipt/screenshot...' }
    ]
  }]
})
```

### 4. pg_cron для напоминалок
```sql
-- Каждые 15 минут проверять напоминалки
select cron.schedule(
  'check-reminders',
  '*/15 * * * *',
  $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'project_url')
      || '/functions/v1/check-reminders',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'service_role_key')
    ),
    body := '{}'::jsonb
  ) as request_id;
  $$
);
```

---

## Execution Order

```
Phase 1 (Foundation)  → TECH-001..006
Phase 2 (Core CRUD)   → FTR-001..004
Phase 3 (TG Bot + AI) → FTR-005..009
Phase 4 (Notifications) → FTR-010..013
Phase 5 (Dashboard)   → FTR-014..018
Phase 6 (Polish)      → FTR-019..020, TECH-007..008
```

**Каждая фаза — рабочий инкремент.** После Phase 2 уже можно пользоваться вебом. После Phase 3 — вводить данные через бота. После Phase 4 — не пропускать платежи.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Supabase free tier pause (7 days inactive) | Бот перестанет работать | Пользоваться регулярно или перейти на Pro ($25/мес) |
| AI неточно распознаёт чеки | Неправильные данные | Всегда показывать результат и спрашивать подтверждение |
| Clerk + Supabase Edge Functions auth | Возможны edge cases | Тестировать auth flow тщательно |
| grammY session в serverless | Потеря контекста разговора | Хранить сессии в Supabase (не in-memory) |
| Vercel timeout (10s hobby) | AI-скан не успеет | Gemini Flash быстрый (~2-3s), но backup — увеличить timeout или Pro plan |

---

## Files Allowed to Modify

**Phase 1:**
- `src/**` (очистка шаблона)
- `supabase/migrations/**` (новые)
- `supabase/functions/**` (новые)
- `package.json` (новые зависимости)

**All phases:** согласно CLAUDE.md allowlist per task.
