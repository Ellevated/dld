# Tech: [TECH-074] Sync Root .claude from Template

**Status:** done | **Priority:** P1 | **Date:** 2026-02-02

## Why

Root `.claude/` отстаёт от `template/.claude/`. Улучшения сделанные в template не попали в root, поэтому наш рабочий автопилот работает на устаревшей версии.

## Context

При сравнении найдены расхождения где template ЛУЧШЕ:
- Новые проверки в review агенте
- Escaped defect tracking в diary
- Code hygiene проверки в spec-reviewer
- Отсутствующий task-loop.md
- Устаревший scaffold skill (заменён на skill-writer)

## Scope

**In scope:**
1. Скопировать `task-loop.md` из template в root
2. Синхронизировать `agents/review.md` — добавить Anti-Patterns секцию
3. Синхронизировать `agents/diary-recorder.md` — добавить escaped_defect
4. Синхронизировать `agents/spec-reviewer.md` — добавить Code Hygiene
5. Удалить устаревший `skills/scaffold/` (заменён на skill-writer)

**Out of scope:**
- Council агенты (URLs vs placeholders) — отдельная задача
- Поведенческие различия autopilot (ALWAYS vs if no plan) — требует анализа

## Allowed Files

**ONLY these files may be modified:**

1. `.claude/skills/autopilot/task-loop.md` — **CREATE** (скопировать из template)
2. `.claude/agents/review.md` — добавить секцию 3.5 Anti-Patterns
3. `.claude/agents/diary-recorder.md` — добавить escaped_defect тип
4. `.claude/agents/spec-reviewer.md` — добавить Code Hygiene секцию
5. `.claude/skills/scaffold/SKILL.md` — **DELETE** (устарел)

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Implementation Plan

### Task 1: Copy task-loop.md
**Type:** code
**Action:** Скопировать `template/.claude/skills/autopilot/task-loop.md` → `.claude/skills/autopilot/task-loop.md`
**Acceptance:** Файл существует, идентичен template

### Task 2: Sync review.md
**Type:** code
**Action:** Добавить секцию 3.5 "Anti-Patterns" из template версии
**Source:** `template/.claude/agents/review.md` lines 90-128
**Target:** `.claude/agents/review.md` после секции 3 (перед секцией 4)
**Acceptance:** `diff .claude/agents/review.md template/.claude/agents/review.md` показывает только ожидаемые различия

### Task 3: Sync diary-recorder.md
**Type:** code
**Action:** Добавить поддержку `escaped_defect` типа
**Changes:**
- Добавить в список типов: `escaped_defect`
- Добавить поля: `escaped_from`, `found_by`
- Добавить секцию "Escaped Defect Entry"
- Добавить "Index Row (Escaped Defect)"
**Acceptance:** `diff` показывает только placeholders различия

### Task 4: Sync spec-reviewer.md
**Type:** code
**Action:** Добавить секцию "Code Hygiene"
**Source:** `template/.claude/agents/spec-reviewer.md` lines 73-90
**Acceptance:** TODO/FIXME проверки включены

### Task 5: Delete scaffold
**Type:** code
**Action:** `rm -rf .claude/skills/scaffold/`
**Reason:** Заменён на skill-writer (в template scaffold не существует)
**Acceptance:** Папка удалена

### Execution Order
1 → 2 → 3 → 4 → 5

## Definition of Done

### Functional
- [ ] task-loop.md существует в root
- [ ] review.md имеет Anti-Patterns проверку
- [ ] diary-recorder.md поддерживает escaped_defect
- [ ] spec-reviewer.md имеет Code Hygiene проверку
- [ ] scaffold удалён

### Technical
- [ ] Все файлы синхронизированы (diff показывает только ожидаемые различия)
- [ ] Нет регрессий

## Autopilot Log
<!-- filled by autopilot -->
