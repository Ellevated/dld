# Tech: [TECH-071] Spark Modules Cleanup

**Status:** done | **Priority:** P2 | **Date:** 2026-02-02

## Why

После разбиения spark/SKILL.md на модули (TECH-058) остались дублирования и мёртвые ссылки на несуществующие фазы. Нужно почистить.

## Context

TECH-058 разбил монолитный SKILL.md (736 LOC) на 4 модуля:
- SKILL.md (152 LOC) — orchestrator
- feature-mode.md (347 LOC) — feature flow
- bug-mode.md (317 LOC) — bug flow
- completion.md (199 LOC) — shared completion logic

При разбиении некоторые секции были скопированы в несколько мест.

---

## Scope

**In scope:**
- Удалить дублирующиеся секции
- Убрать мёртвые ссылки на Phase 3/7/8
- Синхронизировать template/.claude/ и .claude/

**Out of scope:**
- Изменение логики работы spark
- Добавление новой функциональности

---

## Analysis

### Дублирования найдены:

| Секция | Где дублируется | Каноническое место |
|--------|-----------------|-------------------|
| Output секция | SKILL.md:136-152, feature-mode.md:341-347, completion.md:185-199 | completion.md |
| LLM-Friendly Architecture Checks | SKILL.md:122-133, feature-mode.md:317-324 | SKILL.md |
| STRICT READ-ONLY MODE | SKILL.md:80-92, bug-mode.md:256-268 | SKILL.md |
| Completion Checklist | feature-mode.md:329-338, completion.md:25-37 | completion.md |

### Мёртвые ссылки на фазы:

| Файл | Строка | Что написано | Проблема |
|------|--------|--------------|----------|
| feature-mode.md | 100 | "Phase 3" | Фазы не определены |
| feature-mode.md | 116, 124, 125 | "Phase 3", "Phase 5", "Phase 8" | Фазы не определены |
| completion.md | 192 | "Phase 7" | Фазы не определены |

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.claude/skills/spark/SKILL.md` — убрать Output секцию (есть в completion.md)
2. `template/.claude/skills/spark/feature-mode.md` — убрать LLM-Friendly, Completion Checklist, Output; исправить ссылки на фазы
3. `template/.claude/skills/spark/bug-mode.md` — убрать STRICT READ-ONLY (есть в SKILL.md)
4. `template/.claude/skills/spark/completion.md` — исправить ссылку на Phase 7
5. `.claude/skills/spark/SKILL.md` — sync from template
6. `.claude/skills/spark/feature-mode.md` — sync from template
7. `.claude/skills/spark/bug-mode.md` — sync from template
8. `.claude/skills/spark/completion.md` — sync from template

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Implementation Plan

### Task 1: Clean feature-mode.md

**Type:** refactor
**Files:**
  - modify: `template/.claude/skills/spark/feature-mode.md`

**Changes:**
1. Удалить секцию "LLM-Friendly Architecture Checks" (строки 317-324) — уже есть в SKILL.md
2. Удалить секцию "Completion Checklist" (строки 329-338) — уже есть в completion.md
3. Удалить секцию "Output" (строки 341-347) — уже есть в completion.md
4. Заменить "Phase 3" на конкретное описание (например "after Socratic Dialogue")
5. Заменить "Phase 5" на "Approaches section"
6. Заменить "Phase 8" на "Implementation Plan"

**Acceptance:** Файл не содержит дублирований, нет ссылок на несуществующие фазы

### Task 2: Clean bug-mode.md

**Type:** refactor
**Files:**
  - modify: `template/.claude/skills/spark/bug-mode.md`

**Changes:**
1. Удалить секцию "STRICT READ-ONLY MODE" (строки 256-268) — уже есть в SKILL.md
2. Добавить ссылку: "See SKILL.md for READ-ONLY rules"

**Acceptance:** Файл не содержит дублирования READ-ONLY правил

### Task 3: Clean SKILL.md

**Type:** refactor
**Files:**
  - modify: `template/.claude/skills/spark/SKILL.md`

**Changes:**
1. Удалить секцию "Output" (строки 136-152) — уже есть в completion.md
2. Добавить в конец: "## Output\n\nSee `completion.md` for output format."

**Acceptance:** Output определён только в completion.md

### Task 4: Clean completion.md

**Type:** refactor
**Files:**
  - modify: `template/.claude/skills/spark/completion.md`

**Changes:**
1. Строка 192: заменить "Phase 7 complete" на "spec is complete"

**Acceptance:** Нет ссылок на несуществующие фазы

### Task 5: Sync to root .claude/

**Type:** sync
**Files:**
  - modify: `.claude/skills/spark/SKILL.md`
  - modify: `.claude/skills/spark/feature-mode.md`
  - modify: `.claude/skills/spark/bug-mode.md`
  - modify: `.claude/skills/spark/completion.md`

**Changes:**
1. Скопировать все 4 файла из template/.claude/skills/spark/ в .claude/skills/spark/

**Acceptance:** Файлы идентичны

### Execution Order

1 → 2 → 3 → 4 → 5

---

## Definition of Done

### Functional
- [ ] Нет дублирований между модулями
- [ ] Нет ссылок на несуществующие фазы (Phase 3/5/7/8)
- [ ] template/ и root .claude/ синхронизированы

### Technical
- [ ] Все файлы < 400 LOC
- [ ] spark skill работает корректно (ручная проверка)

---

## Expected LOC After Cleanup

| File | Before | After (approx) |
|------|--------|----------------|
| SKILL.md | 152 | ~140 |
| feature-mode.md | 347 | ~300 |
| bug-mode.md | 317 | ~300 |
| completion.md | 199 | ~199 |
| **Total** | 1015 | ~940 |

---

## Autopilot Log

[Auto-populated by autopilot during execution]
