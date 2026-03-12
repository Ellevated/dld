# Feature: [TECH-081] Template Placeholder Fixes
**Status:** done | **Priority:** P2 | **Date:** 2026-02-02

## Why
Четыре проблемы с placeholder'ами в template файлах запутывают новых пользователей:

1. **localization.md** — `[Your Language]` и `"your word for spark"` вместо реального примера
2. **CLAUDE.md** — упоминается несуществующий скилл `commit`
3. **documenter.md** — project-specific примеры `dowry.md`, `awardy.md` вместо generic placeholder'ов
4. **architecture.md** — `YYYY-MM` в ADR таблице выглядит незаполненным

## Context
- `template/.claude/rules/localization.md:14-28` — абстрактные placeholder'ы
- `template/CLAUDE.md:20` — `Skills: spark, scout, commit, audit, review` (commit не существует)
- `template/.claude/agents/documenter.md:94-95` — примеры из реального проекта, не template
- `template/.claude/rules/architecture.md:53-54` — YYYY-MM вместо реальных дат
- DLD — международный open source проект

---

## Scope
**In scope:**
- Заменить placeholder на конкретный пример (испанский)
- Убрать несуществующий скилл `commit` из CLAUDE.md
- Заменить project-specific примеры в documenter.md на generic placeholder'ы
- Заменить YYYY-MM на реальную дату 2026-01 в architecture.md

**Out of scope:** Добавление множества языков, создание скилла commit

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- [ ] Только новые пользователи DLD при настройке локализации
- [ ] Файл не импортируется никуда

### Step 2: DOWN — what depends on?
- [ ] Нет зависимостей — это markdown документация

### Step 3: BY TERM — grep entire project
- [ ] `localization.md` упоминается только в правилах

### Step 4: CHECKLIST — mandatory folders
- [x] Это template file, не код

### Verification
- [x] Изменение одного файла, никаких side effects

---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `template/.claude/rules/localization.md` — добавить испанский пример вместо placeholder
2. `template/CLAUDE.md` — убрать несуществующий скилл `commit`
3. `template/.claude/agents/documenter.md` — заменить `dowry.md`, `awardy.md` на generic placeholder'ы
4. `template/.claude/rules/architecture.md` — заменить YYYY-MM на 2026-01

**New files allowed:**
- Нет

**FORBIDDEN:** Все остальные файлы.

---

## Environment

nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Spanish Example (Recommended)
**Summary:** Заменить `[Your Language]` на `Spanish (es)` с реальными испанскими триггерами
**Pros:**
- Испанский — второй по распространённости язык после английского
- Понятен международной аудитории
- Реальный пример вместо абстракции
**Cons:** Нет

### Selected: 1
**Rationale:** Простое и эффективное решение

---

## Design

### Изменения в файле

**Было (строки 14-28):**
```markdown
## [Your Language]

| Trigger | Skill |
|---------|-------|
| "your word for spark", "alternative trigger" | `/spark` |
| "your word for autopilot" | `/autopilot` |
...
```

**Стало:**
```markdown
## Spanish (es)

| Trigger | Skill |
|---------|-------|
| "chispa", "crear especificación" | `/spark` |
| "piloto automático", "ejecutar" | `/autopilot` |
| "consejo", "debate" | `/council` |
| "auditoría", "revisar código" | `/audit` |
| "explorador", "investigar" | `/scout` |
| "reflexionar" | `/reflect` |
| "probador", "ejecutar pruebas" | `/tester` |
| "codificador" | `/coder` |
| "planificador" | `/planner` |
| "revisión" | `/review` |
```

---

## Implementation Plan

### Task 1: Replace placeholder with Spanish example
**Type:** docs
**Files:**
  - modify: `template/.claude/rules/localization.md`
**Acceptance:**
- Нет `[Your Language]` в файле
- Нет `"your word for..."` placeholder'ов
- Есть реальные испанские слова

### Task 2: Fix skill list in CLAUDE.md
**Type:** docs
**Files:**
  - modify: `template/CLAUDE.md`
**Change:**
```
# Было:
Skills: spark, scout, commit, audit, review

# Стало:
Skills: spark, scout, audit, review
```
**Acceptance:**
- Нет упоминания `commit` в списке скиллов Standard тира
- Все перечисленные скиллы существуют в `template/.claude/skills/`

### Task 3: Replace project-specific examples in documenter.md
**Type:** docs
**Files:**
  - modify: `template/.claude/agents/documenter.md`
**Change:**
```markdown
# Было:
| `src/domains/seller/*` | `.claude/contexts/dowry.md` |
| `src/domains/buyer/*` | `.claude/contexts/awardy.md` |

# Стало:
| `src/domains/{domain1}/*` | `.claude/contexts/{domain1}.md` |
| `src/domains/{domain2}/*` | `.claude/contexts/{domain2}.md` |
```
**Acceptance:**
- Нет упоминания `dowry.md` или `awardy.md`
- Используются generic placeholder'ы `{domain1}`, `{domain2}`

### Task 4: Fix YYYY-MM dates in architecture.md
**Type:** docs
**Files:**
  - modify: `template/.claude/rules/architecture.md`
**Change:**
```markdown
# Было:
| ADR-001 | Money in cents | YYYY-MM | Avoid float precision errors |
| ADR-002 | Result instead of exceptions | YYYY-MM | Explicit error handling |
| ADR-003 | Async everywhere | YYYY-MM | Consistency, performance |

# Стало:
| ADR-001 | Money in cents | 2026-01 | Avoid float precision errors |
| ADR-002 | Result instead of exceptions | 2026-01 | Explicit error handling |
| ADR-003 | Async everywhere | 2026-01 | Consistency, performance |
```
**Acceptance:**
- Нет YYYY-MM в файле
- Используются реальные даты 2026-01

### Execution Order
1 → 2 → 3 → 4

---

## Definition of Done

### Functional
- [ ] Placeholder заменён на испанский пример в localization.md
- [ ] Пример содержит реальные испанские слова для всех скиллов
- [ ] Скилл `commit` убран из CLAUDE.md
- [ ] Project-specific примеры заменены на generic в documenter.md
- [ ] YYYY-MM заменены на 2026-01 в architecture.md

### Technical
- [ ] Файлы валидный markdown
- [ ] Комментарий HOW TO USE сохранён для пользователей
- [ ] Все скиллы в списке существуют
- [ ] Нет упоминаний проектов dowry/awardy
- [ ] Нет YYYY-MM placeholder'ов

---

## Autopilot Log

**2026-02-02:**
- Task 1: Replaced `[Your Language]` with `Spanish (es)` example in localization.md ✓
- Task 2: Removed non-existent `commit` skill from CLAUDE.md ✓
- Task 3: Replaced `dowry.md`/`awardy.md` with `{domain1}.md`/`{domain2}.md` in documenter.md ✓
- Task 4: Replaced `YYYY-MM` with `2026-01` in architecture.md ✓
- Commit: `9576c94` — fix(template): replace placeholders with real examples
