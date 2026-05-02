# ARCH-073: LLM-Native Contract Hub Architecture

**Дата:** 2026-02-05
**Статус:** done
**Приоритет:** P0
**Scope:** Phase 10 — Cross-Project Sync (1/4)
**Зависимости:** нет (standalone)
**Время:** 4-6 часов

---

## Контекст

3 проекта (Dowry, AwardyBot, dowry-mc) разрабатываются LLM-агентами в отдельных репозиториях. Изменения в одном репо создают drift в остальных, потому что LLM при старте сессии не знает о контексте соседних проектов.

**Исследование (Feb 2026):** 50+ источников подтверждают — polyrepo + Contract Hub = оптимальный подход для LLM-first solo founder. Монорепо ROI отрицательный.

**Источники:**
- [Multi-Repo AI Setup](https://www.bishoylabib.com/posts/ai-coding-assistants-multi-repo-solutions) (Dec 2025)
- [AI Rules Sharing — 74% token savings](https://www.paulmduvall.com/sharing-ai-development-rules-across-your-organization/) (Jan 2026)
- [AGENTS.md pattern — Fima Furman](https://www.linkedin.com/posts/fima-furman-74133a) (Jan 2026)

---

## Что делаем

### Task 1: Обновить contracts.md как SSoT

**Файл:** `ai/integration/contracts.md`

Дополнить существующий файл:
1. Добавить секцию **AwardyBot API Surface** (фактические endpoints из кода AwardyBot)
2. Добавить секцию **Sync Protocol v2** с автоматизированным workflow
3. Добавить секцию **CLAUDE.md Rules** — правила для LLM в каждом репо

**Формат AwardyBot API Surface:**
```markdown
## NEIGHBOR: AwardyBot — API Surface (фактическая)

### Admin API (потребляется MC)
| Method | Path | Response | Файл |
|--------|------|----------|------|
| POST | `/api/admin/auth/telegram` | `{token, user}` | `src/api/admin/auth.py` |
| GET | `/api/admin/dashboard/rnp` | `RnpDashboard` | `src/api/admin/dashboard.py` |
...
```

Для заполнения — прочитать файлы из `/Users/desperado/dev/Awardybot/src/api/`.

### Task 2: Добавить contract rules в CLAUDE.md (Dowry)

Добавить в `CLAUDE.md` секцию:

```markdown
### Cross-Repo Contract Awareness
- При изменении API endpoints (src/api/) — ОБЯЗАТЕЛЬНО обновить `ai/integration/contracts.md`
- При добавлении нового endpoint — запустить `python scripts/export_openapi.py`
- Перед потреблением данных из AwardyBot — проверить contracts.md секцию NEIGHBOR
- При изменении Pydantic response models — отметить в Type Sync Map
```

### Task 3: Создать зеркальный контракт для dowry-mc

**Файл:** `/Users/desperado/dev/dowry-mc/ai/integration/dowry-api.md`

Содержимое — выжимка из contracts.md:
- Dowry API endpoints (полная таблица)
- Response types (Pydantic model definitions)
- Known GAPs

### Task 4: Создать зеркальный контракт для AwardyBot

**Файл:** `/Users/desperado/dev/Awardybot/ai/integration/dowry-contracts.md`

Содержимое:
- Что Dowry читает из public.* (таблицы, поля)
- Что Dowry пишет в public.* (processed_at, processed_by)
- Dowry API surface (если AwardyBot будет вызывать)

### Task 5: Добавить contract rules в CLAUDE.md (dowry-mc)

Создать/обновить `/Users/desperado/dev/dowry-mc/CLAUDE.md`:

```markdown
### Cross-Repo Contracts
- Source of truth: `ai/integration/dowry-api.md`
- При изменении API calls — проверить соответствие endpoints из dowry-api.md
- При добавлении нового API call — сначала проверить, существует ли endpoint в Dowry
- Типы API: будут генерироваться из OpenAPI (TECH-074), пока — ручные в src/types/
```

### Task 6: Добавить contract rules в CLAUDE.md (AwardyBot)

Создать/обновить `/Users/desperado/dev/Awardybot/CLAUDE.md` (добавить секцию):

```markdown
### Cross-Repo Contracts
- Source of truth: `ai/integration/dowry-contracts.md`
- Dowry читает public.slot_events, public.slots, public.campaigns, public.sellers, public.buyers
- При изменении структуры этих таблиц — обновить dowry-contracts.md
- НИКОГДА не трогать dowry.* схему — владелец Dowry CI
```

---

## Acceptance Criteria

- [ ] contracts.md содержит фактический API surface AwardyBot (из кода)
- [ ] CLAUDE.md Dowry содержит секцию Cross-Repo Contract Awareness
- [ ] dowry-mc имеет `ai/integration/dowry-api.md` с Dowry endpoints
- [ ] AwardyBot имеет `ai/integration/dowry-contracts.md`
- [ ] CLAUDE.md dowry-mc содержит contract rules
- [ ] CLAUDE.md AwardyBot содержит contract rules

---

## Риски

- AwardyBot CLAUDE.md может не существовать — создать с нуля
- Endpoints AwardyBot могут отличаться от документированных — проверить из кода

---

## Связанные задачи

- **TECH-074:** OpenAPI Export + Type Generation (зависит от этой)
- **TECH-075:** CI Cross-Repo Sync
- **TECH-076:** Contract Testing
