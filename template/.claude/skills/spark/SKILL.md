---
name: spark
description: Idea generation and specification with Exa research and structured dialogue
agent: .claude/agents/spark.md
---

# Spark — Idea Generation & Specification

Transforms raw ideas into specs via Exa research + structured dialogue.

**Activation:** `spark`, `spark quick`, `spark deep`

## When to Use
- New feature, user flow change, architecture decision
- New tool or prompt modification
- **Bug fix** — после диагностики причины, перед фиксом

**Don't use:** Hotfixes <5 LOC (fix directly), pure refactoring without spec

## Principles
1. **READ-ONLY MODE** — Spark NEVER modifies files (except creating spec in `ai/features/` and `ai/diary/`)
2. **AUTO-HANDOFF** — After spec is ready, auto-handoff to autopilot (no manual "plan" step)
3. **Research-First** — Search Exa + Context7 before designing
4. **AI-First** — Can we solve via prompt change?
5. **Socratic Dialogue** — Ask 5-7 deep questions before designing
6. **YAGNI** — Only what's necessary
7. **Explicit Allowlist** — Spec must list ONLY files that can be modified
8. **Learn from Corrections** — Auto-capture user corrections to diary


## Status Ownership

**See CLAUDE.md#Task-Statuses** for canonical status definitions.

**Key point:** Spark owns `queued` status. Plan subagent adds tasks but doesn't change status.

## Mode Detection

Spark работает в двух режимах:

| Trigger | Mode | Method |
|---------|------|--------|
| "новая фича", "добавь", "хочу", "оформи фичу", "оформи спеку", "создай спеку", "напиши спецификацию", "сделай фичу" | **Feature Mode** | Socratic Dialogue |
| "баг", "ошибка", "падает", "не работает" | **Bug Mode** | 5 Whys + Reproduce |

## Socratic Dialogue (Feature Mode)

For NEW features — ask 5-7 deep questions. One at a time!

**Question Bank (pick 5-7 relevant):**

1. **Problem:** "Какую проблему решаем?" (не фичу, а боль)
2. **User:** "Кто пользователь этой функции? Seller? Buyer? Admin?"
3. **Current state:** "Как сейчас решается без этой фичи?"
4. **MVP:** "Какой минимальный scope даст 80% ценности?"
5. **Risks:** "Что может пойти не так? Edge cases?"
6. **Verification:** "Как будем проверять что работает?"
7. **Existing:** "Есть ли готовое решение, которое можно адаптировать?"
8. **Priority:** "Насколько это срочно? P0/P1/P2?"
9. **Dependencies:** "От чего зависит? Что блокирует?"

**Rules:**
- Ask ONE question at a time — wait for answer
- Don't move to design until key questions are answered
- If user says "just do it" — ask 2-3 minimum clarifying questions anyway
- Capture insights for spec

## 5 Whys + Systematic Debugging (Bug Mode)

For BUGS — find ROOT CAUSE before creating spec!

### Phase 1: REPRODUCE

```
"Покажи точные шаги воспроизведения:"
1. Какая команда/действие?
2. Какой input?
3. Какой output получаем?
4. Какой output ожидаем?
```

**Get EXACT error output!** Not "тест падает" but actual traceback.

### Phase 2: ISOLATE

```
Найти границы проблемы:
- Когда началось? (последний working commit?)
- Где именно падает? (file:line)
- Воспроизводится ли всегда?
- Есть ли related файлы?
```

Read files, grep, find the exact location.

### Phase 3: ROOT CAUSE — 5 Whys

```
Why 1: Почему тест падает?
  → "Потому что функция возвращает None"

Why 2: Почему функция возвращает None?
  → "Потому что условие X не выполняется"

Why 3: Почему условие X не выполняется?
  → "Потому что переменная Y не инициализирована"

Why 4: Почему переменная Y не инициализирована?
  → "Потому что миграция не добавила default value"

Why 5: Почему миграция не добавила default?
  → "Потому что забыли при добавлении колонки"

ROOT CAUSE: Миграция XXX не имеет DEFAULT для новой колонки.
```

**STOP when you find the REAL cause, not symptom!**

### Phase 4: CREATE BUG SPEC

Only after root cause is found → create BUG-XXX spec:

```markdown
# Bug: [BUG-XXX] Title

**Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD

## Симптом
[What user sees / test failure]

## Root Cause (5 Whys Result)
[The REAL cause, not symptom]

## Reproduction Steps
1. [exact step]
2. [exact step]
3. Expected: X, Got: Y

## Fix Approach
[How to fix the root cause]

## Impact Tree Analysis (ARCH-392)

### Step 1: ВВЕРХ — кто использует?
- [ ] `grep -r "from.*{module}" . --include="*.py"` → ___ results
- [ ] All callers identified: [list files]

### Step 2: ВНИЗ — от чего зависит?
- [ ] Imports in changed file checked
- [ ] External dependencies: [list]

### Step 3: ПО ТЕРМИНУ — grep по всему проекту
- [ ] `grep -rn "{old_term}" . --include="*.py" --include="*.sql"` → ___ results

| File | Line | Status | Action |
|------|------|--------|--------|
| _fill_ | _fill_ | _fill_ | _fill_ |

### Step 4: CHECKLIST — обязательные папки
- [ ] `tests/**` checked
- [ ] `db/migrations/**` checked
- [ ] `ai/glossary/**` checked (if money-related)

### Verification
- [ ] Все найденные файлы добавлены в Allowed Files
- [ ] grep по старому термину = 0 (или добавлена cleanup задача)

## Allowed Files
1. `path/to/file.py` — fix location
2. `path/to/test.py` — add regression test

## Definition of Done
- [ ] Root cause fixed
- [ ] Original test passes
- [ ] Regression test added
- [ ] No new failures
```

### Bug Mode Rules

- ⛔ **NEVER guess the cause** — investigate first!
- ⛔ **NEVER fix symptom** — fix root cause!

### Exact Paths Required (BUG-328)

**RULE:** Allowed Files must contain EXACT file paths, not placeholders.

```markdown
# ❌ WRONG — CI validation fails
## Allowed Files
1. `db/migrations/YYYYMMDDHHMMSS_create_function.sql`

# ✅ CORRECT — exact timestamp
## Allowed Files
1. `db/migrations/20260116153045_create_function.sql`
```

**For migrations:** Generate timestamp first, then write spec.

```bash
# 1. Create migration (gets timestamp)
# Use your DB tool: alembic, prisma, knex, etc.

# 2. Note exact filename
ls db/migrations/*.sql | tail -1

# 3. Use exact name in spec
```

**Why:** CI validator (`validate_spec.py`) does literal string matching, not pattern recognition.
- ⛔ **NEVER skip reproduction** — must have exact steps!
- ✅ **ALWAYS create spec** — Autopilot does the actual fix
- ✅ **ALWAYS add regression test** — in spec's DoD

## Execution Style (No Commentary)

When invoking spark for bugs:
- ✅ "Запускаю spark для BUG-XXX"
- ❌ "Это BUG, не feature, но раз просите спеку..."
- ❌ "This is not a Spark task, but since you asked..."

**Rule:** Не комментируй процесс — просто выполняй. Баги идут через spark → plan → autopilot.

## STRICT RULES

**During Spark phase:**
- READ files — allowed
- SEARCH/GREP — allowed
- CREATE spec file in `ai/features/` — allowed
- WRITE to `ai/diary/` — allowed (corrections capture)
- MODIFY any other file — **FORBIDDEN**

**If task is not suitable for Spark:**
- Hotfix <5 LOC → fix directly without spec
- Pure refactoring without user request → ask user first

## Auto-Capture Corrections (MANDATORY)

When user corrects you during Spark dialogue — capture the learning!

**Detection:** User says something that contradicts/corrects your assumption

**Action:**
1. Acknowledge: "Понял, учту: [краткое правило]"
2. Append to `ai/diary/corrections.md`:
```markdown
## YYYY-MM-DD: During TYPE-XXX

**Context:** [what we were discussing]
**I proposed:** [what I suggested]
**User corrected:** [what user said]
**Why:** [reason if given]
**Rule:** [generalized learning in imperative form]
```

**Examples of corrections to capture:**
- "Нет, у нас не так работает" → capture how it actually works
- "Это слишком сложно, сделай проще" → capture simplicity preference
- "Всегда используй X вместо Y" → capture tool/pattern preference
- "Это уже есть в Z" → capture existing solution location

**Goal:** Build project memory. Same mistakes won't repeat.

**In resulting spec:**
- Must include `## Allowed Files` section with explicit list
- Files NOT in allowlist — **FORBIDDEN** to modify during implementation
- Autopilot/Coder must refuse to touch files outside allowlist

## UI Event Completeness (REQUIRED for UI features)

If creating UI elements with callbacks/events — fill this table in spec:

| Producer (keyboard/button) | callback_data | Consumer (handler) | Handler File in Allowed Files? |
|---------------------------|---------------|-------------------|-------------------------------|
| `start_keyboard()` | `guard:start` | `cb_guard_start()` | `onboarding.py` ✓ |

**RULE:** Every `callback_data` MUST have a handler in Allowed Files!

- No handler = No commit (Autopilot will block)
- If handler file missing from Allowed Files — add it or explain why not needed
- This prevents orphan callbacks (BUG-156 post-mortem)

## LLM-Friendly Architecture Checks

**See CLAUDE.md#Forbidden-CI-enforced and CLAUDE.md#Structure** for architecture rules.

Quick checklist before creating spec:
- Files < 400 LOC (600 for tests)
- New code in `src/domains/` or `src/infra/`, NOT legacy folders
- Max 5 exports per `__init__.py`
- Imports follow: shared → infra → domains → api


## Research Phase (via Scout)

Use Scout subagent for external research:
- Library/framework questions
- Best practices
- Architecture patterns

**Call:**
```yaml
Task tool:
  subagent_type: "scout"
  prompt: |
    QUERY: {question}
    TYPE: library | pattern | architecture
```

See `.claude/agents/scout.md` for details.


## ID Determination Protocol (MANDATORY)

Перед созданием спеки — определи следующий ID:

1. **Определи тип:** FTR | BUG | SEC | REFACTOR | ARCH | TECH
2. **Сканируй backlog:** Открой ai/backlog.md
3. **Найди все ID типа:** Используй паттерн TYPE-\d+
4. **Возьми максимальный:** Сортируй числа, возьми max
5. **Добавь +1:** Следующий ID = max + 1

**Пример:**
- Backlog содержит: FTR-179, FTR-180, FTR-181
- Следующий ID: FTR-182

**ЗАПРЕЩЕНО:** Угадывать ID или использовать "примерно следующий".

## Impact Tree Analysis (MANDATORY)

Перед созданием плана:

1. Определи ключевые термины/файлы которые меняются
2. Выполни Impact Tree Analysis:
   - ВВЕРХ: `grep -r "from.*{module}" . --include="*.py"`
   - ПО ТЕРМИНУ: `grep -rn "{term}" . --include="*.py" --include="*.sql" --include="*.ts" --include="*.md"`
   - CHECKLIST: проверь tests/, migrations/, edge functions/, glossary/
3. ВСЕ найденные файлы включи в Allowed Files
4. Если grep по старому термину > 0 → добавь задачу на cleanup
5. Проверь glossary — нужно ли добавить новые термины?

**ЗАПРЕЩЕНО:**
- Grep только по одной папке
- Пропускать tests/ в анализе
- Помечать done если grep по старому термину > 0

## Process (7 Phases)

**See `.claude/agents/spark.md`** for detailed phases.

Summary: Context → Exa Research → Clarify → Deep Search → Approaches → Design → Spec

## Flow Coverage Matrix (REQUIRED)

Map every User Flow step to Implementation Task:

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User clicks menu button | - | existing |
| 2 | Guard shows message + button | Task 1,2,3 | ✓ |
| 3 | User clicks [Start] button | Task 4 | ✓ |
| 4 | Onboarding starts | - | existing |

**GAPS = BLOCKER:**
- Every step must be covered by a task OR marked "existing"
- If gap found → add task or explain why not needed
- Uncovered steps = incomplete spec (Council may reject)

## Spec Template

```markdown
# Feature: [FTR-XXX] Title
**Status:** queued | **Priority:** P0/P1/P2 | **Date:** YYYY-MM-DD

## Зачем (RU)
## Контекст (RU)

---
## Scope
In scope: ... | Out of scope: ...

## Impact Tree Analysis (ARCH-392)

### Step 1: ВВЕРХ — кто использует?
- [ ] `grep -r "from.*{module}" . --include="*.py"` → ___ results
- [ ] All callers identified: [list files]

### Step 2: ВНИЗ — от чего зависит?
- [ ] Imports in changed file checked
- [ ] External dependencies: [list]

### Step 3: ПО ТЕРМИНУ — grep по всему проекту
- [ ] `grep -rn "{old_term}" . --include="*.py" --include="*.sql"` → ___ results

| File | Line | Status | Action |
|------|------|--------|--------|
| _fill_ | _fill_ | _fill_ | _fill_ |

### Step 4: CHECKLIST — обязательные папки
- [ ] `tests/**` checked
- [ ] `db/migrations/**` checked
- [ ] `ai/glossary/**` checked (if money-related)

### Verification
- [ ] Все найденные файлы добавлены в Allowed Files
- [ ] grep по старому термину = 0 (или добавлена cleanup задача)

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `path/to/file1.py` — reason
2. `path/to/file2.py` — reason
3. `path/to/file3.py` — reason

**New files allowed:**
- `path/to/new_file.py` — reason

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

## Environment

<!-- Smart defaults: adjust based on your stack -->
nodejs: false
docker: false
database: false

## Approaches
### Approach 1: [Name] (based on [source])
Source: URL | Summary: ... | Pros/Cons: ...

### Selected: [N]
Rationale: ...

## Design
User Flow: ... | Architecture: ... | DB: ...

## Implementation Plan
### Research Sources
- [Pattern](url) — description

### Task 1: [Name]
Type: code | Files: create/modify | Pattern: [url] | Acceptance: ...

### Execution Order
1 → 2 → 3

---
## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks from Implementation Plan completed

### E2E User Journey (REQUIRED for UI features)
- [ ] Every UI element is interactive (buttons respond to clicks)
- [ ] User can complete full journey from start to finish
- [ ] No dead-ends or hanging states
- [ ] Manual E2E test performed

### Technical
- [ ] Tests pass (./test fast)
- [ ] No regressions

## Autopilot Log
```

## Pre-Completion Checklist (BLOCKING)

⛔ **НЕ ЗАВЕРШАЙ SPARK** без выполнения ВСЕХ пунктов:

1. [ ] **ID определён по протоколу** — не угадан!
2. [ ] **Проверка уникальности** — grep по backlog не нашёл такого ID
3. [ ] **Файл спеки создан** — ai/features/TYPE-XXX-YYYY-MM-DD-name.md
4. [ ] **Запись добавлена в backlog** — в секцию `## Очередь`
5. [ ] **Статус = queued** — спека готова для autopilot!
6. [ ] **Function overlap check** (ARCH-226) — grep other queued specs for same function names
   - If overlap found: merge into single spec OR mark dependency
7. [ ] **Auto-commit выполнен** — `git add -A && git commit` (без push!)

Если любой пункт не выполнен — **СТОП и выполни**.

### Backlog Entry Verification (BLOCKING — BUG-358)

After creating spec file, **VERIFY** backlog entry exists:

```bash
# 1. Run verification
grep "{TASK_ID}" ai/backlog.md

# 2. If NOT found → ADD NOW (don't proceed!)
# Edit ai/backlog.md → add entry to ## Очередь table

# 3. Re-verify
grep "{TASK_ID}" ai/backlog.md
# Must show the entry!

# 4. Only then → complete spark
```

⛔ **Spark без backlog entry = DATA LOSS!**
Autopilot reads ONLY backlog — orphan spec files are invisible to it.

### Status Sync Self-Check (SAY OUT LOUD — BUG-358)

When setting status in spec, **verbally confirm**:

```
"Setting spec file: Status → queued"       [Write/Edit spec]
"Setting backlog entry: Status → queued"   [Edit backlog]
"Both set? ✓"                              [Verify match]
```

⛔ **Одно место = рассинхрон = autopilot не увидит задачу!**

### Формат записи в backlog:
```
| ID | Задача | Status | Priority | Feature.md |
|----|--------|--------|----------|------------|
| FTR-XXX | Название задачи | queued | P1 | [FTR-XXX](features/FTR-XXX-YYYY-MM-DD-name.md) |
```

### Статусы при выходе из Spark:
| Ситуация | Статус | Причина |
|----------|--------|---------|
| Spark завершился полностью | `queued` | Autopilot может подхватить |
| Спека создана, но прервались | `draft` | Autopilot НЕ берёт draft |
| Нужно обсудить/отложить | `draft` | Остаётся на доработку |

## Backlog Format (STRICT)

**Структура ai/backlog.md — неизменяема:**

```
## Очередь          ← единственная таблица задач
## Статусы          ← справочник статусов
## Архив            ← ссылка на архив
## Ideas            ← ссылка на ideas.md
```

**ЗАПРЕЩЕНО:**
- Создавать новые секции/таблицы
- Группировать задачи по категориям
- Добавлять заголовки типа "## Tests" или "## Legacy"

**При добавлении записи:**
1. Открыть `ai/backlog.md`
2. Найти секцию `## Очередь`
3. Добавить строку в **конец** таблицы (перед `---`)
4. НЕ создавать новые секции

**Почему:** LLM путается при множестве таблиц и не знает куда добавлять новые записи. Одна таблица = одно место = нет путаницы.

## Auto-Commit (MANDATORY before handoff!)

After spec file is created and backlog updated — commit ALL changes locally:

```bash
# 1. Stage ALL changes (spec, backlog, diary, docs, screenshots, etc.)
git add -A

# 2. Commit locally (NO PUSH!)
git commit -m "docs: create spec ${TASK_ID}"
```

**Why `git add -A`:**
- Captures everything: spec, backlog, diary, docs, screenshots
- Saves work from other agents (scout, manual edits)
- .gitignore protects from junk (.env, __pycache__)

**Why NO push:**
- CI doesn't trigger (saves money)
- Spec validation doesn't fail
- Commit is protected locally — won't be lost
- Autopilot will push everything at the end of PHASE 3

**When:** ALWAYS before asking "Запускаю autopilot?"

## Auto-Handoff to Autopilot

After Spec is complete — auto-handoff to Autopilot. No manual "plan" step!

**Flow:**
1. Spec saved to `ai/features/TYPE-XXX.md`
2. Ask user: "Spec готов. Запускаю autopilot?"
3. If user confirms → invoke Skill tool with `skill: "autopilot"`
4. If user declines → stop and let user decide

**Announcement format:**
```
Spec готов: `ai/features/TYPE-XXX-YYYY-MM-DD-name.md`

**Summary:**
- [2-3 bullet points what will be done]

Запускаю autopilot?
```

**What happens in Autopilot:**
- Plan Subagent creates detailed tasks
- Fresh Coder/Tester/Reviewer subagents per task
- Auto-commit after each task
- All in isolated worktree branch

**Exception: Council first**
If task is complex/controversial (architecture change, >10 files, breaking change):
```
Spec готов, но рекомендую Council review перед имплементацией.
Причина: [why controversial]

Запустить council?
```

## Output

### If running as subagent (Task tool — no user interaction):
⛔ **MUST use Write tool to create spec file BEFORE returning!**
⛔ **MUST use Edit tool to add backlog entry BEFORE returning!**

Returning spec_path without creating file = DATA LOSS (subagent context dies).

### If running interactively (Skill tool):
Write spec file when Phase 7 complete, then ask about autopilot handoff.

### Return format:
```yaml
status: complete | needs_discussion | blocked
spec_path: ai/features/TYPE-XXX.md  # file MUST exist
handoff: autopilot | council | blocked
```
