# ARCH-001: Project Context System

**Status:** done | **Priority:** P0 | **Date:** 2026-01-24
**Type:** ARCH (architectural enhancement)
**Based on:** ARCH-392 (Impact Tree Analysis) from awardybot

---

## Problem (Зачем)

### Боль пользователя

LLM-агент начинает рефакторинг, находит несколько файлов через grep, правит их — но **забывает про зависимые компоненты**. Результат: сломанный код в других частях системы.

### Реальные примеры боли (из awardybot)

| Инцидент | Что произошло | Последствия |
|----------|---------------|-------------|
| **TECH-093** | Переименовали `_rub → _kopecks` в DB, забыли тесты | 23 follow-up задачи |
| **TECH-055** | Поменяли Ledger на kopecks, забыли SQL RPCs с `/ 100` | **Broken production** |
| **TECH-070** | Начали менять accrual → обнаружили Dual System Problem уже в процессе | Переделка архитектуры |

### Root Cause Analysis

```
Задача: Рефакторинг billing.get_balance()

Что делает LLM:
1. grep находит 3 файла в billing/
2. Меняет API get_balance()
3. Коммитит

Что происходит:
- campaigns/ вызывает get_balance() → СЛОМАН
- seller/ вызывает get_balance() → СЛОМАН
- LLM про них не знал, grep их не показал
```

### Почему это происходит

1. **Нет алгоритма impact analysis** — агент не строит связи в голове
2. **Grep делается по узкой папке** — а проблемы везде
3. **Нет карты "если меняешь X → проверь Y"**
4. **Нет module headers** — контекст файла теряется
5. **Знания не накапливаются** — каждая сессия с нуля

### Гипотеза

Если создать **систему контекста проекта** с:
- **Impact Tree Algorithm** — обязательный анализ перед изменениями
- **Dependencies map** — карта кто кого использует
- **Module headers** — контекст в каждом файле
- **Domain glossary** — термины и правила домена

То:
- Агенты будут видеть все зависимости
- Знания будут накапливаться между сессиями
- Рефакторинг не будет ломать зависимые компоненты
- **Refactoring tasks: 23 → ≤5**

---

## Solution Overview

### Project Context System

Трёхуровневая система знаний о проекте:

```
┌──────────────────────────────────────────────────────────┐
│ Layer 1: dependencies.md + architecture.md               │
│ Граф связей + паттерны. Загружается ВСЕМИ агентами       │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2: domains/{name}.md                               │
│ Контекст домена. Загружается ЕСЛИ работаем с доменом     │
└────────────────────────┬─────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 3: Feature spec (ai/features/XXX.md)               │
│ Контекст задачи. Загружается исполнителем                │
└──────────────────────────────────────────────────────────┘
```

### Ключевые компоненты

| Компонент | Назначение | Кто обновляет |
|-----------|------------|---------------|
| `dependencies.md` | Граф зависимостей между компонентами | spark, coder |
| `architecture.md` | Паттерны, ADR, анти-паттерны | человек, reflect |
| `domains/*.md` | Контекст конкретного домена | coder |
| `glossary/*.md` | Термины и правила домена (self-contained) | coder, documenter |
| `context-loader.md` | Протокол загрузки (DRY) | — (статичный) |
| `context-updater.md` | Протокол обновления (DRY) | — (статичный) |

### Impact Tree Algorithm (5 шагов из ARCH-392)

**Input:** Файлы которые меняем + термины которые меняем

#### Step 1: ВВЕРХ — кто использует?

```bash
# Найти всех импортеров модуля
grep -r "from.*{module}" . --include="*.py" --include="*.ts" --include="*.sql"
grep -r "import.*{module}" . --include="*.py" --include="*.ts"

# Найти все вызовы функции/класса
grep -r "{function_name}" . --include="*.py" --include="*.ts" --include="*.sql"
```

**КРИТИЧЕСКИ ВАЖНО:** Точка `.` — весь проект, НЕ конкретная папка!

#### Step 2: ВНИЗ — от чего зависит?

```bash
# В файле который меняем — какие импорты?
grep "^from\|^import" {file}

# Какие внешние функции вызывает?
grep -E "[a-z_]+\.[a-z_]+\(" {file}
```

#### Step 3: ПО ТЕРМИНУ — grep по всему проекту

```bash
# КРИТИЧЕСКИ ВАЖНО: grep по ВСЕМУ проекту
grep -rn "{old_term}" . --include="*.py" --include="*.ts" --include="*.sql" --include="*.md"

# Для money changes — обязательные паттерны:
grep -rn "/ 100\|* 100\|_rub\|_kopecks" . --include="*.sql"
```

**ПРАВИЛО:** После всех изменений grep по старому термину = 0 результатов!

#### Step 4: CHECKLIST — обязательные папки

| Тип изменения | ОБЯЗАТЕЛЬНО проверить |
|---------------|----------------------|
| DB schema / columns | `tests/**`, `supabase/migrations/**`, `supabase/functions/**` |
| Money/amounts | `tests/**`, `*.sql`, `ai/glossary/**` |
| API signature | `tests/**`, все вызывающие модули |
| Model fields | `tests/**`, repositories, services |
| Naming convention | **ВСЁ** — grep по всему проекту |

#### Step 5: Dual System Check

Если меняем источник данных:
1. Кто ЧИТАЕТ из старого источника? Они увидят новые данные?
2. Кто ЧИТАЕТ из нового источника? Они увидят старые данные?
3. Есть ли переходный период когда оба источника активны?

### Module Headers (из ARCH-392)

В начале каждого значимого файла:

```python
"""
Module: pricing_service
Role: Calculate campaign costs (preview before creation)
Source of Truth: SQL RPC calculate_campaign_cost() — this file is wrapper only

Uses:
  - campaigns/models.py: Campaign, UgcType, SlotStatus
  - shared/types.py: UUID, Decimal

Used by:
  - seller/tools/campaigns: cost preview for agent
  - campaigns/activation: launch validation

Why here: Python нужен для preview ДО создания campaign в БД.
         После создания — SQL RPC is source of truth.

Glossary: ai/glossary/billing.md (money rules)
"""
```

### Module Headers Workflow (для Coder)

```
1. ОТКРЫЛ файл
   └── Прочитал module header (если есть)

2. ПРОВЕРИЛ consistency
   ├── Header пустой? → Оформи перед работой
   ├── Uses/Used by актуальны?
   └── Glossary ссылки валидны?

3. ВНЁС изменения в код

4. ПЕРЕЧИТАЛ module header
   ├── Добавил новые dependencies в Uses?
   ├── Изменился Role?
   └── Нужно обновить Used by? (grep кто использует)

5. СОХРАНИЛ файл
```

### Per-Domain Glossary (из ARCH-392)

```
ai/glossary/
├── billing.md      # transactions, balances + money rules
├── campaigns.md    # slots, offers + money rules
├── seller.md       # roles, companies + money rules
├── buyer.md        # states, proofs + money rules
└── outreach.md     # leads, scoring, nurturing
```

**Принцип: Self-Contained**

Каждый файл содержит ВСЁ что нужно для работы с доменом:

```markdown
# Billing Glossary

## Money Rules (CRITICAL)
All amounts in kopecks. 1 ruble = 100 kopecks.
Naming: `amount_kopecks`, never bare `amount`.
Why: Integer arithmetic prevents floating-point errors.
History: Ambiguous naming caused 23-task refactoring (Jan 2026).

## term_name
**What:** Краткое определение
**Why:** Почему так сделано (история, причина)
**Convention:** Правило использования
**Naming:** Как называть в коде
**Related:** Связанные термины
```

**Дублирование Money Rules в каждом domain файле — ок.**
LLM читает один файл и имеет весь контекст.

---

## Scope

### In scope

- Создание файловой структуры `.claude/rules/`
- Создание протоколов `_shared/context-loader.md` и `context-updater.md`
- Шаблоны для `dependencies.md`, `architecture.md`, `domains/_template.md`
- Шаблон для `ai/glossary/_template.md` (per-domain glossary)
- Интеграция Impact Tree Algorithm в spark (5-шаговый алгоритм)
- Module Headers workflow в coder
- Интеграция в агенты: spark, planner, coder, review, council, debugger, documenter
- Хук `validate-spec-complete.sh` — блокировка коммита если Impact Tree не заполнен
- Обновление документации

### Out of scope

- Автоматическое заполнение dependencies.md из кода (будущее)
- MCP-интеграция для контекста (будущее)
- Визуализация графа зависимостей (будущее)
- Автоматическая генерация glossary из docstrings (будущее)

### Already Implemented (from previous session)

Из awardybot уже перенесено в template:
- `validate-spec-complete.sh` — блокирует коммит если Impact Tree checkboxes не заполнены
- Impact Tree секция в `spark/SKILL.md` (4-шаговый алгоритм)
- Module Headers workflow в `coder.md`
- Consistency Verification в `documenter.md`

---

## Allowed Files

**ONLY these files may be created/modified:**

### New files to create

| # | File | Reason |
|---|------|--------|
| 1 | `template/.claude/rules/dependencies.md` | Шаблон графа зависимостей |
| 2 | `template/.claude/rules/architecture.md` | Шаблон архитектурных решений |
| 3 | `template/.claude/rules/domains/_template.md` | Шаблон контекста домена |
| 4 | `template/.claude/agents/_shared/context-loader.md` | Протокол загрузки контекста |
| 5 | `template/.claude/agents/_shared/context-updater.md` | Протокол обновления контекста |
| 6 | `template/ai/glossary/_template.md` | Шаблон per-domain glossary |

### Files to modify

| # | File | Action | Reason |
|---|------|--------|--------|
| 7 | `template/.claude/agents/spark.md` | modify | Добавить Phase 0.5 + update after |
| 8 | `template/.claude/agents/planner.md` | modify | Добавить Phase 0 |
| 9 | `template/.claude/agents/coder.md` | modify | Добавить Step 0 + Step 7 + Module Headers |
| 10 | `template/.claude/agents/review.md` | modify | Добавить Check 0 |
| 11 | `template/.claude/agents/debugger.md` | modify | Добавить Step 1.5 |
| 12 | `template/.claude/agents/documenter.md` | modify | Добавить Consistency Verification + Glossary Mapping |
| 13 | `template/.claude/skills/council/SKILL.md` | modify | Добавить context load before experts |
| 14 | `template/.claude/skills/spark/SKILL.md` | modify | Усилить Impact Tree + context integration |
| 15 | `template/CLAUDE.md` | modify | Добавить раздел про Context System |
| 16 | `docs/19-living-architecture.md` | modify | Добавить документацию Context System |

**FORBIDDEN:** All other files.

---

## Design

### File Structure

```
template/.claude/
├── rules/                           # ЗНАНИЯ (что знаем о проекте)
│   ├── dependencies.md              # Граф зависимостей
│   ├── architecture.md              # Паттерны и ADR
│   └── domains/
│       └── _template.md             # Шаблон для нового домена
│
├── agents/
│   ├── _shared/                     # ПРОТОКОЛЫ (как работать)
│   │   ├── context-loader.md        # Загрузка контекста
│   │   └── context-updater.md       # Обновление контекста
│   ├── spark.md                     # @import context-loader
│   ├── planner.md                   # @import context-loader
│   ├── coder.md                     # @import context-loader + updater
│   ├── review.md                    # @import context-loader
│   ├── debugger.md                  # @import context-loader
│   └── ...
│
└── skills/
    └── council/
        └── SKILL.md                 # Context load before experts
```

### dependencies.md Format

```markdown
# Project Dependencies

## Как читать
- `A → B` означает "A использует B"
- `A ← B` означает "A используется в B"

---

## {domain_name}

**Path:** `src/domains/{domain_name}/`

### Использует (→)

| Что | Где | Функция |
|-----|-----|---------|
| {dependency} | {path} | {function}() |

### Используется в (←)

| Кто | Файл:строка | Функция |
|-----|-------------|---------|
| {caller} | {file}:{line} | {function}() |

### При изменении API проверить

- [ ] {dependent_1}
- [ ] {dependent_2}

---

## Последнее обновление

| Дата | Что | Кто |
|------|-----|-----|
| YYYY-MM-DD | {change} | {agent} |
```

### architecture.md Format

```markdown
# Architecture

## Структура проекта

```
src/
├── shared/     # Result, exceptions, types (NO business logic)
├── infra/      # db, llm, external (technical adapters)
├── domains/    # Business logic
└── api/        # Entry points
```

## Направление импортов

```
shared ← infra ← domains ← api
       (НИКОГДА в обратную сторону)
```

## Паттерны (СЛЕДОВАТЬ)

| Паттерн | Где применять | Пример |
|---------|---------------|--------|
| {pattern} | {where} | {example} |

## Анти-паттерны (ЗАПРЕЩЕНО)

| Что | Почему | Вместо этого |
|-----|--------|--------------|
| {antipattern} | {reason} | {alternative} |

## ADR (Architecture Decision Records)

| ID | Решение | Дата | Причина |
|----|---------|------|---------|
| ADR-001 | {decision} | YYYY-MM | {rationale} |
```

### domains/_template.md Format

```markdown
---
domain: {name}
path: src/domains/{name}/
---

# {Name} Domain

## Назначение

{1-2 предложения о том, что делает этот домен}

## Сущности

| Сущность | Файл:строка | Описание |
|----------|-------------|----------|
| {Entity} | {file}:{line} | {description} |

## Публичный API

| Функция | Сигнатура | Описание |
|---------|-----------|----------|
| {func}() | `async def {func}(...) -> Result[T, E]` | {what it does} |

## Паттерны домена

- {pattern 1}
- {pattern 2}

## Запрещено в этом домене

- ❌ {forbidden 1}
- ❌ {forbidden 2}

## История изменений

| Дата | Что | Задача | Кто |
|------|-----|--------|-----|
| YYYY-MM-DD | {change} | {TASK-ID} | {agent} |
```

### context-loader.md Protocol

```markdown
# Context Loading Protocol

## WHEN

Execute this protocol BEFORE starting ANY work.

## STEPS

### Step 1: Load Project Context (ALWAYS)

```bash
Read: .claude/rules/dependencies.md
Read: .claude/rules/architecture.md
```

**Use for:**
- Understanding what depends on what
- Following established patterns
- Avoiding anti-patterns

### Step 2: Identify Affected Domains

From task/spec files → extract domain names.

**Example:**
- File `src/domains/billing/services.py` → domain = `billing`
- File `src/infra/db/supabase.py` → domain = `infra`

### Step 3: Load Domain Contexts

For each affected domain:

```bash
Read: .claude/rules/domains/{domain}.md (if exists)
```

**Use for:**
- Domain-specific patterns
- Known entities and their locations
- Forbidden actions

### Step 4: Mental Summary

After loading, note:

```yaml
key_dependencies:
  - {domain} is used by {list of callers}

patterns_to_follow:
  - {pattern 1}
  - {pattern 2}

forbidden:
  - {forbidden 1}
```

## WARNING TRIGGERS

WARN user if during work you discover:

| Situation | Warning |
|-----------|---------|
| Changing public API but dependents NOT in scope | ⚠️ "API change affects {list}, add to Allowed Files?" |
| Adding cross-domain import | ⚠️ "Cross-domain import, check architecture.md" |
| Creating similar function to existing | ⚠️ "Similar to {existing}, consider reusing" |

## OUTPUT

None (internal preparation). Continue with your main task.
```

### context-updater.md Protocol

```markdown
# Context Update Protocol

## WHEN

Execute this protocol AFTER completing work that changes project knowledge.

## TRIGGERS

| What you did | What to update |
|--------------|----------------|
| Created new public function/class | → Add to domain "Сущности" |
| Created new cross-domain call | → Add to dependencies.md |
| Established new pattern | → Add to domain "Паттерны" |
| Discovered forbidden action | → Add to domain "Запрещено" |
| Changed existing API signature | → Update dependents list |

## HOW TO UPDATE

### Adding new entity to domain context

In `.claude/rules/domains/{domain}.md`, section "Сущности":

```markdown
| {Name} | {file}:{line} | {description} |
```

### Adding new dependency

In `.claude/rules/dependencies.md`, section "{domain}":

```markdown
### Используется в (←)
| {caller_domain} | {file}:{line} | {function}() |
```

### Adding history entry

In `.claude/rules/domains/{domain}.md`, section "История":

```markdown
| {YYYY-MM-DD} | {what changed} | {TASK-ID} | coder |
```

## IMPORTANT

- Update IMMEDIATELY after code change
- Don't batch updates — update as you go
- If unsure whether to add — ADD (better too much than too little)
- Use exact file:line references

## VERIFICATION

Before finishing, verify:

```bash
# Check dependencies.md was updated if new cross-domain call
grep "{new_function}" .claude/rules/dependencies.md

# Check domain context was updated if new entity
grep "{new_entity}" .claude/rules/domains/{domain}.md
```

## OUTPUT

After updating, confirm:

```yaml
context_updates:
  - file: .claude/rules/domains/billing.md
    change: "Added Transaction.refund() to Сущности"
  - file: .claude/rules/dependencies.md
    change: "Added: seller → billing.refund()"
```
```

---

## Agent Integration

### spark.md Changes

Add after existing Phase 1:

```markdown
## Process

### Phase 0.5: Load Context (MANDATORY - NEW)

@.claude/agents/_shared/context-loader.md

**Use context for Impact Tree:**
- Check dependencies.md BEFORE grep
- Known dependencies → add to Allowed Files immediately
- Grep for NEW dependencies not in map

### Phase 7: Update Context (MANDATORY - NEW)

After creating spec:

@.claude/agents/_shared/context-updater.md

**If discovered new dependencies via grep:**
- Add them to dependencies.md
- This captures knowledge for future tasks
```

### planner.md Changes

Add at the beginning of Process:

```markdown
## Process

### Phase 0: Load Context (MANDATORY - NEW)

@.claude/agents/_shared/context-loader.md

**Use context for planning:**
- Order tasks by dependency (dependents last)
- Include dependency updates in task list
- Flag if spec missing dependent components
```

### coder.md Changes

Add Step 0 and Step 7:

```markdown
## Process

### Step 0: Load Context (MANDATORY - NEW)

@.claude/agents/_shared/context-loader.md

**Before writing any code:**
- Know the patterns to follow
- Know what's forbidden
- Know who depends on code you're changing

### Step 7: Update Context (MANDATORY - NEW)

@.claude/agents/_shared/context-updater.md

**After completing code:**
- Add new entities to domain context
- Add new dependencies to map
- Add history entry
```

### review.md Changes

Add Check 0:

```markdown
## What You Check

### Check 0: Context Completeness (NEW)

```bash
# Load context
Read: .claude/rules/dependencies.md
```

**Red flags:**
- [ ] Changed API signature but dependents NOT in files_changed
- [ ] New public function not added to domain context
- [ ] New cross-domain call not in dependencies.md
- [ ] Context files not updated after code changes

**If red flag found:**
```yaml
verdict: needs_refactor
reason: "Context not updated: {specific issue}"
```
```

### debugger.md Changes

Add Step 1.5:

```markdown
### Step 1.5: Check Dependencies (NEW)

After scope check, before root cause:

```bash
Read: .claude/rules/dependencies.md
```

**Check if failure could be caused by:**
- Dependent not updated after API change
- Circular dependency introduced
- Pattern violation (check architecture.md)
- Missing entity in domain context
```

### council/SKILL.md Changes

Add before expert dispatch:

```markdown
## Before Expert Analysis (NEW)

Load context ONCE, include in expert prompts:

```bash
Read: .claude/rules/dependencies.md
Read: .claude/rules/architecture.md
```

**Each expert receives:**
- Current dependency graph
- Established patterns
- Known anti-patterns

This ensures all 5 experts have architectural awareness.
```

---

## Implementation Plan

### Task 1: Create rules/ directory structure

**Files:**
- Create: `template/.claude/rules/dependencies.md`
- Create: `template/.claude/rules/architecture.md`
- Create: `template/.claude/rules/domains/_template.md`

**Steps:**
1. Create directory structure
2. Write dependencies.md template with format and examples
3. Write architecture.md template with format and examples
4. Write _template.md for domain context

**Acceptance:**
- [ ] All 3 files created
- [ ] Each file < 200 LOC
- [ ] Clear format with examples

### Task 2: Create shared protocols

**Files:**
- Create: `template/.claude/agents/_shared/context-loader.md`
- Create: `template/.claude/agents/_shared/context-updater.md`

**Steps:**
1. Create _shared/ directory
2. Write context-loader.md with full protocol
3. Write context-updater.md with full protocol
4. Ensure protocols are self-contained

**Acceptance:**
- [ ] Both protocols complete
- [ ] Each file < 150 LOC
- [ ] Clear step-by-step instructions

### Task 3: Integrate into spark

**Files:**
- Modify: `template/.claude/agents/spark.md`
- Modify: `template/.claude/skills/spark/SKILL.md`

**Steps:**
1. Add Phase 0.5 with @import context-loader
2. Add Phase 7 update with @import context-updater
3. Update Impact Tree section to use dependencies.md first
4. Test that flow still makes sense

**Acceptance:**
- [ ] Context load integrated
- [ ] Context update integrated
- [ ] Impact Tree enhanced
- [ ] File < 400 LOC

### Task 4: Integrate into planner

**Files:**
- Modify: `template/.claude/agents/planner.md`

**Steps:**
1. Add Phase 0 with @import context-loader
2. Add guidance on using dependencies for task ordering
3. Verify no duplicate instructions

**Acceptance:**
- [ ] Context load integrated
- [ ] Clear usage guidance
- [ ] File < 400 LOC

### Task 5: Integrate into coder

**Files:**
- Modify: `template/.claude/agents/coder.md`

**Steps:**
1. Add Step 0 with @import context-loader
2. Add Step 7 with @import context-updater
3. Add warning triggers for API changes
4. Verify step numbering is correct

**Acceptance:**
- [ ] Both protocols integrated
- [ ] Warning triggers clear
- [ ] File < 400 LOC

### Task 6: Integrate into review

**Files:**
- Modify: `template/.claude/agents/review.md`

**Steps:**
1. Add Check 0 for context completeness
2. Add red flags for missing updates
3. Add verdict guidance

**Acceptance:**
- [ ] Context check integrated
- [ ] Red flags clear
- [ ] File < 400 LOC

### Task 7: Integrate into debugger

**Files:**
- Modify: `template/.claude/agents/debugger.md`

**Steps:**
1. Add Step 1.5 for dependency check
2. Add guidance on dependency-related failures

**Acceptance:**
- [ ] Context check integrated
- [ ] File < 400 LOC

### Task 8: Integrate into council

**Files:**
- Modify: `template/.claude/skills/council/SKILL.md`

**Steps:**
1. Add context load before expert dispatch
2. Ensure all experts receive context
3. Verify expert prompts include architectural awareness

**Acceptance:**
- [ ] Context load integrated
- [ ] All 5 experts receive context
- [ ] File < original + 50 LOC

### Task 9: Create glossary template

**Files:**
- Create: `template/ai/glossary/_template.md`

**Steps:**
1. Create ai/glossary/ directory
2. Write _template.md with self-contained format
3. Include Money Rules example
4. Include term format (What/Why/Convention/Naming/Related)

**Acceptance:**
- [ ] Template file created
- [ ] Self-contained format documented
- [ ] Money Rules example included

### Task 10: Update documentation

**Files:**
- Modify: `template/CLAUDE.md`
- Modify: `docs/19-living-architecture.md`

**Steps:**
1. Add Context System section to CLAUDE.md
2. Add Context System documentation to docs/
3. Add Impact Tree Algorithm reference
4. Add Module Headers reference
5. Cross-reference with existing documentation

**Acceptance:**
- [ ] CLAUDE.md updated
- [ ] docs/ updated
- [ ] No broken references

### Execution Order

```
Task 1 (rules/) → Task 2 (protocols) → Tasks 3-9 (agents + glossary, parallel) → Task 10 (docs)
```

### Dependencies

- Task 2 depends on Task 1 (protocols reference rules/)
- Tasks 3-9 depend on Task 2 (agents @import protocols)
- Task 10 depends on Tasks 3-9 (docs describe final state)

---

## Impact Tree Analysis

### Компоненты которые затрагиваются

| Компонент | Тип изменения | Риск |
|-----------|---------------|------|
| spark | Добавление фаз | Средний — ядро workflow |
| planner | Добавление фазы | Низкий — изолированный агент |
| coder | Добавление шагов | Средний — часто используется |
| review | Добавление проверки | Низкий — не блокирует |
| debugger | Добавление шага | Низкий — редко используется |
| council | Добавление контекста | Низкий — изолированный |

### Что может сломаться

| Риск | Митигация |
|------|-----------|
| Агенты станут слишком медленными | Протоколы минимальны, только Read операции |
| @import не работает в subagents | Проверить в реальном Task tool вызове |
| Контекст не обновляется | review.md проверяет обновление |
| Файлы раздуваются | Лимит 200 LOC на rules/ файлы |

---

## Definition of Done

### Functional

- [x] dependencies.md template создан и понятен
- [x] architecture.md template создан и понятен
- [x] domains/_template.md создан и понятен
- [x] glossary/_template.md создан (self-contained format)
- [x] context-loader.md протокол полный и ясный
- [x] context-updater.md протокол полный и ясный
- [x] Все 7 агентов интегрированы (spark, planner, coder, review, debugger, council, documenter)
- [x] Impact Tree Algorithm (5 шагов) интегрирован в spark
- [x] Module Headers Workflow интегрирован в coder
- [x] Consistency Verification интегрирована в documenter
- [x] validate-spec-complete.sh хук работает (уже был в template)
- [x] Документация обновлена

### Technical

- [x] Каждый файл в rules/ < 200 LOC (max: 67 LOC)
- [x] Каждый протокол < 150 LOC (max: 96 LOC)
- [x] Каждый агент < 400 LOC после изменений
- [x] Нет дублирования — протоколы используют @import
- [x] Нет циклических зависимостей
- [x] Glossary format LLM-readable (self-contained)

### Verification

- [ ] Smoke test: создать фичу с spark, проверить что Impact Tree выполняется
- [ ] Smoke test: написать код с coder, проверить что Module Headers обновляются
- [ ] Smoke test: review проверяет что context обновлён
- [ ] Smoke test: попытка коммита с пустым Impact Tree → блокируется
- [ ] Retrospective: алгоритм на TECH-093 нашёл бы tests/

---

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| @import не работает для subagents | Medium | High | Тестировать первым, иметь fallback (inline) |
| Агенты игнорируют протоколы | Medium | Medium | review.md проверяет, добавить MANDATORY |
| Контекст быстро устаревает | Low | Medium | context-updater.md обязателен для coder |
| Слишком много overhead | Low | Low | Минимальные протоколы, только Read |

---

## Future Enhancements (Out of Scope)

1. **Auto-generation** — скрипт который генерирует dependencies.md из import statements
2. **MCP Context Server** — отдельный сервер который кэширует и отдаёт контекст
3. **Visualization** — граф зависимостей в Mermaid или D2
4. **CI Integration** — проверка что dependencies.md актуален

---

## Success Metrics (from ARCH-392)

| Metric | Before (Jan 2026) | After (target) |
|--------|-------------------|----------------|
| Tasks for refactoring | 23 | ≤5 |
| Time to complete | 3 days | 1 day |
| Forgotten files | Multiple | 0 (grep catches all) |
| Production issues | Yes | No |

---

## Anti-patterns to Prevent (from ARCH-392)

| Anti-pattern | Correct |
|--------------|---------|
| `grep "term" src/domains/billing/` | `grep "term" .` (весь проект!) |
| "Tests are separate, update later" | Tests in same PR |
| Grep only `*.py` | Include `*.sql *.ts *.md` |
| "TECH-093 is done" | Verify grep=0 |
| "Billing is in src/domains/billing/" | Check tests/, migrations/, edge functions/ |
| Skip module header | Create/update on every file change |
| "I'll document later" | Document in glossary now |

---

## Enforcement Mechanisms

| Механизм | Что делает | Когда |
|----------|------------|-------|
| `validate-spec-complete.sh` | Блокирует коммит если Impact Tree checkboxes пустые | PreToolUse:Bash |
| Spark Phase 0.5 | Обязательная загрузка context | Каждая спека |
| Coder Step 0 / Step 7 | Загрузка + обновление context | Каждый код |
| Review Check 0 | Проверка что context обновлён | Каждый PR |
| Documenter Consistency | grep=0 по старым терминам | Финализация |

---

## Research References

Based on Exa deep research (Jan 2026):

1. **Memory Bank pattern** — популярный, но часто забрасывается из-за manual overhead
2. **Claude Code native rules/** — официально поддерживается, globs-based loading
3. **Context rot** — слишком много контекста ухудшает recall, решение: модульные файлы < 500 LOC
4. **Staleness problem** — 22% команд забрасывают обновление через 2 недели, решение: обязательный протокол + review check

---

## Related Specs

| Spec | Связь |
|------|-------|
| **ARCH-392** (awardybot) | Оригинальная спека Impact Tree Analysis |
| **validate-spec-complete.sh** | Хук уже перенесён в template |
| **spark/SKILL.md** | Уже содержит Impact Tree секцию |
| **coder.md** | Уже содержит Module Headers Workflow |
| **documenter.md** | Уже содержит Consistency Verification |

---

## Appendix A: Example dependencies.md (filled)

```markdown
# Project Dependencies

## billing

**Path:** `src/domains/billing/`

### Использует (→)

| Что | Где | Функция |
|-----|-----|---------|
| users | infra/db | get_user() |
| supabase | infra/db | transactions table |

### Используется в (←)

| Кто | Файл:строка | Функция |
|-----|-------------|---------|
| campaigns | services.py:45 | get_balance() |
| campaigns | services.py:78 | check_can_spend() |
| seller | actions.py:23 | deduct_balance() |

### При изменении API проверить

- [ ] campaigns
- [ ] seller

---

## campaigns

**Path:** `src/domains/campaigns/`

### Использует (→)

| Что | Где | Функция |
|-----|-----|---------|
| billing | domains/billing | get_balance(), check_can_spend() |
| users | infra/db | get_user() |

### Используется в (←)

| Кто | Файл:строка | Функция |
|-----|-------------|---------|
| api/routes | campaigns.py:12 | create_campaign() |
| bot/handlers | wizard.py:34 | start_campaign_wizard() |

---

## Последнее обновление

| Дата | Что | Кто |
|------|-----|-----|
| 2026-01-20 | Добавлен seller → billing.deduct | coder |
| 2026-01-15 | Инициализация карты зависимостей | spark |
```

---

## Appendix B: Example Session Flow

```
User: /spark Добавить возможность возврата денег

SPARK:
1. Phase 0.5: Load Context
   → Read dependencies.md
   → See: billing используется в campaigns, seller

2. Impact Tree Analysis
   → Уже знаем зависимости из карты
   → Grep только для новых терминов "refund"

3. Allowed Files includes campaigns, seller (из карты!)

4. Phase 7: Update Context
   → Добавить новую функцию billing.refund() в dependencies.md

PLANNER:
1. Phase 0: Load Context
   → Видит зависимости
   → Планирует: billing first, then campaigns, then seller

CODER:
1. Step 0: Load Context
   → Знает паттерны billing (копейки, RPC)
   → Знает кто зависит

2. Writes code

3. Step 7: Update Context
   → Добавляет refund() в domains/billing.md
   → Обновляет dependencies.md

REVIEW:
1. Check 0: Context Completeness
   → Проверяет что dependencies.md обновлён
   → Проверяет что все dependents в scope
   → ✓ Pass
```

---

## Appendix C: Checklist for Implementation

Before starting each task, verify:

- [ ] Read the relevant files first
- [ ] Understand existing structure
- [ ] Make minimal changes
- [ ] Test @import works
- [ ] Verify file stays under LOC limit
- [ ] Update this spec's Autopilot Log

---

## Autopilot Log

*(Filled by Autopilot during execution)*

### Task 1/10: Create rules/ structure — done
**Files created:**
- `template/.claude/rules/dependencies.md` (66 LOC)
- `template/.claude/rules/architecture.md` (67 LOC)
- `template/.claude/rules/domains/_template.md` (55 LOC)

### Task 2/10: Create shared protocols — done
**Files created:**
- `template/.claude/agents/_shared/context-loader.md` (79 LOC)
- `template/.claude/agents/_shared/context-updater.md` (96 LOC)

### Task 3/10: Integrate spark — done
**Modified:** `template/.claude/agents/spark.md`
- Added Phase 0: Load Project Context (@import context-loader.md)
- Added Phase 7.5: Update Context (@import context-updater.md)

### Task 4/10: Integrate planner — done
**Modified:** `template/.claude/agents/planner.md`
- Added Phase 0: Load Project Context (@import context-loader.md)
- Added guidance on using dependencies for task ordering

### Task 5/10: Integrate coder — done
**Modified:** `template/.claude/agents/coder.md`
- Added Step 0: Load Context (@import context-loader.md)
- Added Step 7: Update Context (@import context-updater.md)
- Added Module Headers Workflow section

### Task 6/10: Integrate review — done
**Modified:** `template/.claude/agents/review.md`
- Added Check 0: Context Completeness
- Added red flags for missing context updates

### Task 7/10: Integrate debugger — done
**Modified:** `template/.claude/agents/debugger.md`
- Added Step 1.5: Check Dependencies (@import context-loader.md)
- Added guidance on dependency-related failures

### Task 8/10: Integrate council — done
**Modified:** `template/.claude/skills/council/SKILL.md`
- Added Phase 0: Load Context before expert analysis
- Ensures all 5 experts receive architectural context

### Task 9/10: Create glossary template — done
**Created:** `template/ai/glossary/_template.md` (89 LOC)
- Self-contained format with Money Rules example
- Term format: What/Why/Convention/Naming/Related
- Anti-patterns section

### Task 10/10: Update documentation — done
**Modified:**
- `template/CLAUDE.md` — Added "Project Context System (v3.4)" section
- `docs/19-living-architecture.md` — Added "4. Project Context System (ARCH-001)" section with full documentation
