# TECH-041: Bootstrap Three-Expert Compression

**Status:** done | **Priority:** P2 | **Date:** 2026-01-29

## Why

Bootstrap — самый большой скилл в системе (766 строк). Каждый вызов `/bootstrap` сжигал ~1500 лишних токенов на промпт. Большая часть контента — полные markdown-шаблоны файлов (293 строки), скриптованные диалоги в code blocks, и дублирующие секции.

Применена техника Three-Expert Quality Gate для сжатия без потери смысла.

## Context

Анализ через трёх экспертов:

**Karpathy (избыточность):**
- File Templates: 293 строки пустых `{placeholder}` шаблонов — Claude знает markdown
- Extraction Techniques: 43 строки с code blocks — хватит 1 строки на технику
- Anti-patterns: 12 строк, дублируют Philosophy
- Behavior Modes: 18 строк → 4 строки (имя + триггер)
- "Why this matters" объяснения — Claude выведет сам

**Sutskever (против возможностей):**
- Скриптованные диалоги в code blocks ограничивают естественный диалог Claude
- Жёсткие Exa yaml блоки — Claude составит лучшие запросы из контекста
- Фазы как Goals (цели) работают лучше чем фазы как Scripts (скрипты)

**Murati (UX):**
- 766 строк = massive token burn каждый вызов
- 3 секции говорят одно: Philosophy + Behavior Modes + Anti-patterns
- Тайминги "(10-15 min)" — Claude не контролирует время

---

## Scope

**In scope:**
- Сжатие bootstrap/SKILL.md через Three-Expert Gate
- Сохранение всех фаз, техник, триггеров, research, exit criteria

**Out of scope:**
- Изменение логики bootstrap
- Изменение output формата (4 файла в ai/idea/)
- Добавление новой функциональности (research уже добавлен в TECH-040)

## Impact Tree Analysis

### Step 1: UP — who uses?
- `bootstrap/SKILL.md` вызывается пользователем через `/bootstrap`

### Step 2: DOWN — what depends on?
- Bootstrap создаёт `ai/idea/` файлы
- Эти файлы используются при создании CLAUDE.md и первого /spark

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/skills/bootstrap/SKILL.md` — сжатие через Three-Expert Gate

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### Что убрано

| Компонент | Было | Стало | Эксперт |
|-----------|------|-------|---------|
| File Templates (4 шт.) | 293 строк | 11 строк (списки секций) | Karpathy |
| Phase scripts (code blocks) | ~200 строк | ~65 строк (Goal + key points) | Sutskever |
| Extraction Techniques | 43 строки | 5 строк (1 на технику) | Karpathy |
| Exa yaml blocks | ~40 строк | ~10 строк (inline) | Sutskever |
| Behavior Modes | 18 строк | 4 строки (имя + триггер) | Karpathy |
| Anti-patterns table | 12 строк | 0 (merged в Identity) | Karpathy |
| Timing annotations | на каждой фазе | 0 | Murati |
| "Why this matters" | разбросаны | 0 | Karpathy |

### Что сохранено

- **Identity** — 5 core behaviors + 4 named modes (Explorer, Devil's Advocate, Synthesizer, Challenger)
- **Output** — 4 файла в ai/idea/
- **Dialogue Triggers** — fuzzy words, red flags, contradictions
- **Techniques** — Specific Vasya, Show Screen, Why not, Will Pay, Day in Life
- **Все 12 фаз** — как Goals с ключевыми моментами
- **Research (Exa)** — Phase 5, 8.5, 10
- **File Structure** — списки секций для каждого файла (заменяют полные шаблоны)
- **Exit Criteria** — ready / not ready
- **After Bootstrap** — next steps

## Implementation Plan

### Task 1: Compress bootstrap/SKILL.md

**Type:** code
**Files:**
- Modify: `.claude/skills/bootstrap/SKILL.md`

**What was done:**
1. Philosophy + Behavior Modes + Anti-patterns → единая секция Identity (5 behaviors + 4 modes)
2. Clarification Triggers: 3 таблицы → 3 компактных блока в Dialogue Triggers
3. Extraction Techniques: 5 code blocks → 5 однострочных описаний
4. 12 фаз: скрипты → Goal + ключевые моменты (2-4 строки на фазу)
5. File Templates: 293 строки → 11 строк (списки секций по файлам)
6. Exit criteria + After Bootstrap: без изменений

**Acceptance:**
- ✅ 766 → 178 строк (−77%)
- ✅ Все фазы сохранены
- ✅ Все техники сохранены
- ✅ Research (Exa) сохранён
- ✅ Behavior Modes сохранены (компактно)
- ✅ Exit criteria сохранены

### Execution Order

Task 1 (single task)

---

## Definition of Done

### Functional
- [x] Все 12 фаз присутствуют с Goals
- [x] Dialogue Triggers сохранены (fuzzy, red flags, contradictions)
- [x] 5 техник сохранены
- [x] 4 Behavior Modes сохранены
- [x] Research (Exa) в 3 точках сохранён
- [x] File Structure описывает секции всех 4 файлов
- [x] Exit Criteria сохранены

### Technical
- [x] 766 → 178 строк (−77%)
- [x] Укладывается в лимит < 500 строк для skills
- [x] No regressions — все компоненты bootstrap сохранены

## Autopilot Log

- 2026-01-29: Implemented manually during session (not via autopilot)
- Three-Expert analysis: Karpathy (templates, techniques, anti-patterns), Sutskever (scripts → goals, yaml → inline), Murati (token burn, timing, duplication)
- Result: 766 → 178 lines (−77%)
