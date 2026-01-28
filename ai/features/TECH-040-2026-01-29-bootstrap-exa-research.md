# TECH-040: Bootstrap Exa Research Validation

**Status:** done | **Priority:** P2 | **Date:** 2026-01-29

## Why

Bootstrap извлекает идею из головы фаундера через диалог, но все утверждения о рынке, конкурентах и архитектуре принимались на веру. Фаундер говорит "нет конкурентов" — bootstrap только challenge'ит вопросами, но не проверяет фактически.

Добавление Exa research в bootstrap:
- Валидирует утверждения о конкурентах реальным поиском
- Находит конкурентов, которых фаундер не знает
- Проверяет ценовые бенчмарки в нише
- Информирует архитектурные решения паттернами из реальных проектов

## Context

Bootstrap — самый длинный скилл (698 строк), диалоговый, 11 фаз. Research добавлен в 3 точки:

1. **Phase 5 (Market and Money)** — после обсуждения конкурентов, фактический поиск
2. **Phase 8.5 (Research Validation)** — новая фаза перед Synthesis, комплексная валидация
3. **Phase 10 (Architecture)** — поиск архитектурных паттернов перед предложением доменов

---

## Scope

**In scope:**
- Exa research в Phase 5 (competitor search)
- Новая Phase 8.5 (Research Validation) между Domain Dictionary и Synthesis
- Exa research в Phase 10 (architecture patterns)

**Out of scope:**
- Оптимизация/сжатие bootstrap (698+ строк — отдельная задача)
- Изменение структуры диалога
- Автоматизация bootstrap (остаётся интерактивным)

## Impact Tree Analysis

### Step 1: UP — who uses?
- `bootstrap/SKILL.md` вызывается пользователем через `/bootstrap`

### Step 2: DOWN — what depends on?
- Bootstrap создаёт `ai/idea/` файлы (vision, domain-context, product-brief, architecture)
- Эти файлы используются при создании CLAUDE.md и первого /spark

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/skills/bootstrap/SKILL.md` — добавить Exa research в 3 фазы

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### Phase 5: Market Research Hook

После обсуждения конкурентов:
- `mcp__exa__web_search_exa` → "{product} competitors alternatives"
- `mcp__exa__company_research_exa` → "{competitor_name}" для каждого названного
- Max 3 Exa calls, результаты шерятся conversationally

### Phase 8.5: Research Validation (NEW)

Комплексная валидация перед синтезом:
- Competitor landscape (web_search_exa)
- Problem validation (web_search_exa)
- Pricing benchmarks (web_search_exa)
- Max 6 Exa calls total
- Результаты влияют на Synthesis и Architecture

### Phase 10: Architecture Research

Перед предложением доменов:
- `mcp__exa__get_code_context_exa` → architecture patterns для домена
- Информирует domain split и dependency graph

## Implementation Plan

### Task 1: Add Exa Research to Bootstrap

**Type:** code
**Files:**
- Modify: `.claude/skills/bootstrap/SKILL.md`

**What was done:**
1. Phase 5: добавлен Research Check после обсуждения конкурентов (web_search + company_research)
2. Phase 8.5: новая фаза Research Validation (competitor, problem, pricing — 3 searches)
3. Phase 10: добавлен Research Architecture Patterns (get_code_context_exa)

**Acceptance:**
- ✅ Phase 5 ищет конкурентов через Exa
- ✅ Phase 8.5 валидирует рынок перед синтезом
- ✅ Phase 10 ищет архитектурные паттерны
- ✅ Лимиты вызовов указаны (3 + 6 + 1)

### Execution Order

Task 1 (single task)

---

## Definition of Done

### Functional
- [x] Phase 5 содержит Exa competitor search
- [x] Phase 8.5 содержит комплексную Research Validation
- [x] Phase 10 содержит architecture pattern search
- [x] Все Exa calls имеют лимиты
- [x] Результаты шерятся с фаундером conversationally

### Technical
- [x] No regressions in bootstrap dialogue flow
- [x] Research органично вписан в диалог (не прерывает)

## Autopilot Log

- 2026-01-29: Implemented manually during session (not via autopilot)
- Added research to 3 phases: Market (Phase 5), Validation (Phase 8.5), Architecture (Phase 10)

## Note

Bootstrap = 750+ строк после добавлений. Превышает лимит < 500 для skills. Оптимизация/сжатие через 3-Expert Gate — отдельная задача.
