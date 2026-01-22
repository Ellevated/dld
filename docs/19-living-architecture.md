# Living Architecture Documentation

**Проблема:** Проект растёт, спецификации архивируются, знания испаряются. Через 3 месяца никто не помнит почему billing отделён от campaigns.

**Решение:** Три уровня живой документации.

---

## Три уровня

```
ai/
├── ARCHITECTURE.md          # 1. Текущее состояние (живая карта)
├── decisions/               # 2. Почему так (ADR)
│   ├── 001-supabase.md
│   └── 002-billing-domain.md
└── changelog/               # 3. Как эволюционировало
    └── ARCHITECTURE-CHANGELOG.md
```

| Уровень | Вопрос | Обновляется |
|---------|--------|-------------|
| ARCHITECTURE.md | "Что сейчас есть?" | После каждой фичи |
| decisions/ | "Почему так решили?" | При важных решениях |
| changelog/ | "Как менялось?" | После каждой фичи |

---

## 1. ARCHITECTURE.md — Живая карта

### Когда обновлять
- После реализации каждой фичи (documenter agent)
- При добавлении нового домена
- При изменении зависимостей между доменами
- При добавлении нового entry point

### Кто обновляет
- **Documenter agent** — автоматически после autopilot
- **Вручную** — если autopilot не использовался

### Структура

```markdown
# Architecture: {Project Name}

**Last updated:** {date}
**Version:** {semver или просто номер}

---

## Overview (для человека)

{2-3 абзаца простым языком: что это за система,
кто пользователи, какую проблему решает}

---

## System Diagram

{ASCII-диаграмма или ссылка на Mermaid}

```
┌─────────────────────────────────────────────────────────────┐
│                      Entry Points                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ seller_bot  │  │ buyer_bot   │  │ HTTP API            │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼─────────────────────┼────────────┘
          ▼                ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                        Domains                              │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ seller  │  │  buyer  │  │ campaigns│  │   billing    │  │
│  └────┬────┘  └────┬────┘  └────┬─────┘  └──────┬───────┘  │
└───────┼────────────┼────────────┼───────────────┼──────────┘
        └────────────┴─────┬──────┴───────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Infrastructure                          │
│  ┌────────────┐    ┌────────────┐    ┌─────────────────┐   │
│  │  supabase  │    │   openai   │    │  external APIs  │   │
│  └────────────┘    └────────────┘    └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Domains

### `seller` — Продавцы
**Ответственность:** LLM-агент для продавцов, управление кампаниями через чат

**Ключевые компоненты:**
- `agent.py` — основной LLM агент
- `tools/` — инструменты агента (create_campaign, check_balance, etc.)
- `prompts/` — версионированные промпты

**Зависит от:** campaigns, billing
**Используется:** seller_bot (Telegram)

**Статус:** Production
**Последние изменения:** FTR-213 (autonomous error handling)

---

### `buyer` — Покупатели
**Ответственность:** FSM-бот для покупателей, участие в кампаниях

**Ключевые компоненты:**
- `handlers/` — FSM handlers
- `keyboards/` — inline keyboards
- `locales/` — i18n

**Зависит от:** campaigns, billing
**Используется:** buyer_bot (Telegram)

**Статус:** Production
**Последние изменения:** FTR-220 (new onboarding flow)

---

### `campaigns` — Кампании
...

---

### `billing` — Биллинг
...

---

## Entry Points

| Entry Point | Технология | Домены | Аудитория |
|-------------|------------|--------|-----------|
| seller_bot | aiogram 3.x | seller | Продавцы WB/Ozon |
| buyer_bot | aiogram 3.x | buyer | Покупатели |
| HTTP API | FastAPI | billing, campaigns | Webhooks, интеграции |

---

## Infrastructure

### Database
**Supabase (PostgreSQL)**
- Почему: managed, row-level security, realtime
- ADR: [001-supabase](./decisions/001-supabase.md)

### LLM
**OpenAI GPT-4**
- Используется: seller agent
- Почему: best reasoning for agent tasks
- ADR: [003-openai-for-agent](./decisions/003-openai-for-agent.md)

### External APIs
| API | Зачем | Домен |
|-----|-------|-------|
| DaData | Валидация банковских реквизитов | billing |
| WB API | Проверка товаров | campaigns |

---

## Key Decisions

| # | Решение | Дата | ADR |
|---|---------|------|-----|
| 001 | Supabase вместо raw Postgres | 2025-11-15 | [→](./decisions/001-supabase.md) |
| 002 | Отдельный billing домен | 2025-11-20 | [→](./decisions/002-billing-domain.md) |
| 003 | LLM agent для seller (не FSM) | 2025-12-01 | [→](./decisions/003-llm-agent.md) |

---

## Evolution Timeline

| Дата | Что изменилось | Фича/Причина |
|------|----------------|--------------|
| 2025-11-15 | Initial architecture | — |
| 2025-12-01 | Добавлен seller agent | FTR-100 |
| 2025-12-15 | Разделение billing | FTR-150 |
| 2026-01-05 | Autonomous error handling | FTR-213 |

[Полный changelog →](./changelog/ARCHITECTURE-CHANGELOG.md)

---

## Current Metrics

| Метрика | Значение | Порог |
|---------|----------|-------|
| Domains | 4 | — |
| Max LOC in file | 380 | 400 |
| Test coverage | 41% | 40% |
| Avg exports per __init__ | 3.2 | 5 |
```

---

## 2. ADR (Architecture Decision Records)

### Когда создавать
- Выбор технологии (БД, фреймворк, API)
- Структурное решение (новый домен, разделение существующего)
- Отказ от чего-то (почему НЕ выбрали X)
- Trade-off решения

### Шаблон ADR

```markdown
# ADR-{NNN}: {Title}

**Status:** Accepted | Superseded by ADR-XXX | Deprecated
**Date:** {YYYY-MM-DD}
**Deciders:** {who}

---

## Context

{Какая была ситуация? Какую проблему решали?}

## Decision

{Что решили? Одно предложение.}

## Rationale

{Почему именно так?}

### Alternatives Considered

| Вариант | Плюсы | Минусы | Почему отклонили |
|---------|-------|--------|------------------|
| {alt1} | ... | ... | ... |
| {alt2} | ... | ... | ... |

## Consequences

### Positive
- {что стало лучше}

### Negative
- {какие trade-offs приняли}

### Risks
- {что может пойти не так}

---

## Related
- Фича: {FTR-XXX}
- Другие ADR: {links}
```

---

## 3. Architecture Changelog

### Формат

```markdown
# Architecture Changelog

Все значимые изменения в архитектуре проекта.

---

## [2026-01-06]

### Added
- Домен `outreach` для lead generation (FTR-225)

### Changed
- `campaigns` теперь зависит от `outreach` (была независимой)

### Decisions
- ADR-015: Отдельный домен для outreach vs расширение campaigns

---

## [2026-01-03]

### Changed
- `seller` agent: autonomous error handling без auto-escalation (FTR-213)

### Architecture Impact
- Новый паттерн: agent сам решает когда эскалировать

---

## [2025-12-15]

### Added
- Домен `billing` выделен из `campaigns` (FTR-150)

### Decisions
- ADR-002: Почему отдельный billing

### Migration
- transactions таблица перенесена
- Старые импорты deprecated
```

---

## Процесс обновления

### После каждой фичи (Documenter agent)

```
1. Фича реализована
2. Documenter проверяет:
   - Изменились ли домены?
   - Новые зависимости?
   - Новые entry points?
   - Было ли архитектурное решение?
3. Если да → обновляет:
   - ARCHITECTURE.md (соответствующие секции)
   - changelog/ARCHITECTURE-CHANGELOG.md
   - Создаёт ADR если нужно
```

### При архивировании спецификации

```
1. Спецификация идёт в archive/
2. Documenter извлекает:
   - Архитектурные изменения → ARCHITECTURE.md
   - Решения → ADR (если были)
   - Timeline entry → changelog
3. Знания "оседают" в живой документации
```

---

## Интеграция с Documenter

Добавить в промпт documenter агента:

```
После обновления обычной документации, проверь:

1. ARCHITECTURE.md
   - Актуальны ли домены?
   - Актуальны ли зависимости?
   - Добавить в Evolution Timeline?

2. ADR нужен?
   - Было ли важное архитектурное решение?
   - Был ли выбор между альтернативами?

3. Changelog
   - Добавить запись о том, что изменилось
```

---

## Checklist для ревью

При code review проверять:

- [ ] Если новый домен → добавлен в ARCHITECTURE.md
- [ ] Если новая зависимость → обновлена диаграмма
- [ ] Если архитектурное решение → есть ADR
- [ ] Changelog обновлён
