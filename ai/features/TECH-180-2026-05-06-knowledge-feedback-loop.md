# Feature: [TECH-180] Knowledge Feedback Loop — Historical Risks в спеках
**Status:** done | **Priority:** P1 | **Date:** 2026-05-06

## Why

Spark пишет спеки с нуля, не зная о паттернах из прошлого. Анализ 939 задач за 5 месяцев AwardyBot показал: billing = 98 BUG (kopecks chain = 10 итераций одной и той же проблемы), campaigns = 81 BUG (slot-FSM = 5 итераций), db = 19 BUG с наибольшим риском потери данных. Ни один из этих уроков не появлялся автоматически в спеке новой задачи.

"The real problem wasn't recall — it was binding." (500 experiments, DEV 2026)

## Context

Уже есть: `ai/diary/`, `ai/reflect/`, `architectural-integrity.md` — но эти знания не инжектируются в новые спеки. Spark знает архитектуру, но не знает "мы уже обжигались на этом 10 раз".

Решение: knowledge feedback loop из 4 шагов:
1. **Ingestion** — одноразовое преобразование архива в structured lessons
2. **Retrieval** — spark-codebase тянет top-5 уроков для домена задачи
3. **Binding** — секция `## Historical Risks` в спеке как hard gate
4. **Closing loop** — при `debug_attempts > 0` автоматически дописывает урок в банк

Шаг 5 (monthly /reflect curation) — вне этой спеки, по запросу.

---

## Scope

**In scope:**
- Новая секция `## Historical Risks` в spec template (feature-mode.md)
- Gate 7 в Phase 6 Validation (spark)
- Lessons Retrieval шаг в spark-codebase агенте
- Lesson extraction в Step 6.5 task-loop (при debug_attempts > 0)
- Ingestion скрипт `scripts/build-lessons-index.py`
- Структура `ai/lessons/<domain>/L-NNN.md` + `ai/lessons/index.jsonl`
- Документация `ai/lessons/` в template CLAUDE.md project structure
- Template-sync: все изменения идут template/.claude/ → .claude/

**Out of scope:**
- Curation шаг (/reflect monthly promotion) — отдельно по запросу
- Веб-интерфейс для lessons
- Автоматический re-index при каждом пуше
- Изменение reflect/SKILL.md (входит в отдельный шаг 5)

---

## Impact Tree Analysis

### Step 1: UP — who uses?

spark-codebase.md используется Spark Phase 2 (Research) как один из 4 параллельных скаутов.
feature-mode.md — это SSOT шаблона спеки, читается Spark и autopilot.
task-loop.md — Step 6.5 читается autopilot при каждом завершении задачи.

| File | Used by | Function |
|------|---------|----------|
| template/.claude/agents/spark/codebase.md | Spark Phase 2 | research-codebase.md output |
| template/.claude/skills/spark/feature-mode.md | Spark Phase 5 | spec template |
| template/.claude/skills/autopilot/task-loop.md | Autopilot per-task | diary + commit |

### Step 2: DOWN — what depends on?

- spark-codebase.md читает: git log, grep, find в codebase
- feature-mode.md: не зависит от внешних файлов
- task-loop.md: зависит от autopilot-state.json, ai/diary/index.md

### Step 3: BY TERM

```bash
grep -rn "Historical Risks\|lessons-binding\|root_cause_class" . --include="*.md"
# Expected: 0 results (feature not yet implemented)
```

### Step 4: CHECKLIST

- [x] template/.claude/ checked
- [x] .claude/ checked (sync target)
- [x] ai/lessons/ — doesn't exist (will be created)
- [x] scripts/ — location for build-lessons-index.py

### Verification

- После реализации: `grep "Historical Risks" template/.claude/skills/spark/feature-mode.md` → 1 result
- После sync: `diff template/.claude/agents/spark/codebase.md .claude/agents/spark/codebase.md` → identical

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row -->

ONLY the files listed below may be modified during implementation.

- `template/.claude/agents/spark/codebase.md` — добавить Lessons Retrieval шаг (modify)
- `.claude/agents/spark/codebase.md` — sync from template (modify)
- `template/.claude/skills/spark/feature-mode.md` — добавить Historical Risks section + Gate 7 (modify)
- `.claude/skills/spark/feature-mode.md` — sync from template (modify)
- `template/.claude/skills/autopilot/task-loop.md` — Step 6.5: lesson extraction при debug (modify)
- `.claude/skills/autopilot/task-loop.md` — sync from template (modify)
- `template/CLAUDE.md` — добавить ai/lessons/ в project structure (modify)
- `scripts/build-lessons-index.py` — ingestion script (NEW)
- `ai/lessons/.gitkeep` — create ai/lessons/ directory (NEW)
- `ai/backlog.md` — добавить TECH-180 (modify)

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** DLD Framework (meta — infrastructure для Spark/Autopilot pipeline)
**Cross-cutting:** N/A (framework-level change, не domain)
**Data model:** New: ai/lessons/ directory tree. Index: JSONL append-only log.

---

## Lessons Schema

### Файл `ai/lessons/<domain>/L-NNN.md`

```markdown
---
id: L-{NNN}
domain: {domain_name}
root_cause_class: {class}
severity: critical | high | medium
created: YYYY-MM-DD
occurrence_count: {N}
related: [TASK-ID, TASK-ID]
---

# {root_cause_class}: {short_title}

## Prevention Rule
{One-sentence actionable rule}

## Context
{What happened, what was the mistake}

## Keywords
{comma-separated terms for retrieval matching}
```

### Файл `ai/lessons/index.jsonl`

One JSON object per line:
```json
{"id":"L-001","domain":"billing","root_cause_class":"money-precision","prevention_rule":"Использовать kopecks (int), никогда float/rub","keywords":["kopecks","rub","money","price","amount","balance"],"severity":"critical","related":["BUG-350","BUG-386"],"created":"2026-05-06","occurrence_count":10}
```

### Root Cause Class Taxonomy (12 классов)

| Class | Description | Example |
|-------|-------------|---------|
| `money-precision` | Неправильные единицы/тип для денег | float вместо int(kopecks) |
| `race-condition` | Конкурентные записи без блокировки | два слота одновременно |
| `ssot-violation` | Одни данные в нескольких местах | billing + campaign оба хранят баланс |
| `migration-drift` | Миграция БД не синхронна с кодом | column exists in code, not in DB |
| `atomicity` | Multi-step операция падает посередине | update без транзакции |
| `idempotency` | Повторный вызов = разный результат | webhook double-deposit |
| `boolean-trap` | Неоднозначные boolean поля | is_active не покрывает все состояния |
| `fsm-deadlock` | State machine застряла или нелегальный переход | slot stuck in pickup |
| `cross-layer-import` | Нарушение направления импортов | domain импортирует api |
| `pydantic-coercion` | Тихое приведение типов Pydantic | string "123" → int 123 |
| `case-mismatch` | snake_case vs camelCase несоответствие | db field vs API field |
| `null-safety` | Необработанный None/null | missing None check crashes |

---

## Design

### Новая секция в spec template (Phase 5, feature-mode.md)

Вставить ПОСЛЕ `## Blueprint Reference`, ПЕРЕД `## Approaches`:

```markdown
## Historical Risks

<!-- lessons-binding v1 -->

_Auto-populated by spark-codebase from `ai/lessons/{domain}/`_

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| {L-ID} | {root_cause_class} | {prevention_rule} | {TASK-IDs} |

_Write "none" explicitly if spark-codebase found no historical lessons for this domain._
```

### Новый Gate 7 в Phase 6 Validation (feature-mode.md)

```markdown
### Gate 7: Historical Risks

□ `## Historical Risks` section present?
□ `<!-- lessons-binding v1 -->` marker present?
□ Has ≥1 lesson row OR explicit "none"?
□ If lessons found: prevention rules are actionable (not vague)?
```

**Soft gate:** Если `ai/lessons/` не существует в проекте → Gate 7 auto-passes с отметкой "no lessons bank yet".

### Изменения в spark-codebase.md

Добавить новый раздел `## Lessons Retrieval` в конец (после Risks):

```markdown
## Lessons Retrieval

After completing Impact Tree and Affected Files sections, check project lesson bank.

**Step 1: Check if lessons exist**
```bash
ls ai/lessons/ 2>/dev/null && echo "EXISTS" || echo "NONE"
```

**Step 2: If EXISTS — read domain lessons**
- Glob `ai/lessons/{primary_domain}/*.md`
- Also check `ai/lessons/index.jsonl` for cross-domain matches on feature keywords
- Select TOP-5 by: same domain first → keyword overlap → severity (critical > high > medium)

**Step 3: Write findings to research-codebase.md**

Section to append:
```markdown
## Historical Risks (from ai/lessons/)

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| L-001 | money-precision | ... | BUG-350, BUG-386 |
```
Or if nothing found:
```markdown
## Historical Risks (from ai/lessons/)
_No lessons bank for domain '{domain}' yet._
```
```

### Изменения в task-loop.md Step 6.5

После index row, добавить под-шаг "Lesson Extraction":

```markdown
### Lesson Extraction (conditional — только при debug_attempts > 0)

**Trigger:** debug_attempts > 0 (что-то сломалось и было починено)

Inline (ADR-007, no subagent):

1. Derive `domain` from files_changed paths (e.g., `src/domains/billing/` → `billing`)
2. Map `category` from diary (code_bug | spec_gap | environment | architecture) to `root_cause_class`:
   - code_bug + atomicity keywords → atomicity
   - code_bug + money keywords → money-precision
   - code_bug + concurrent/lock → race-condition
   - architecture → cross-layer-import | fsm-deadlock
   - spec_gap → ssot-violation | boolean-trap
   - Default: use diary category name as-is if no mapping
3. Extract `prevention_rule` from diary Resolution field (1 sentence)
4. Assign `severity`: critical if P0 task, high if P1, medium if P2
5. Determine next L-ID: `ls ai/lessons/{domain}/ | grep -oE "L-[0-9]+" | sort | tail -1` → increment
6. Write `ai/lessons/{domain}/L-{NNN}.md` (create domain dir if missing)
7. Append to `ai/lessons/index.jsonl`

**Rules:**
- ONLY fire when debug_attempts > 0 (don't pollute with trivial tasks)
- If domain cannot be determined from files_changed → skip silently
- If ai/lessons/ directory doesn't exist → create it
- Never block commit — lesson extraction is best-effort
```

### Ingestion script `scripts/build-lessons-index.py`

Назначение: one-time seeding уроков из архива (`ai/archive/`) в `ai/lessons/`.

Алгоритм:
1. Читает `ai/archive/*.md` (BUG- задачи)
2. Для каждого файла извлекает: domain (из заголовка/контента), root_cause_class (по keywords), prevention (из resolution/fix), related IDs
3. Записывает `ai/lessons/<domain>/L-NNN.md` + `ai/lessons/index.jsonl`

Опции:
- `--dry-run` — показать что будет создано
- `--domain DOMAIN` — только один домен
- `--min-severity critical` — только критичные

---

## Implementation Plan

### Research Sources
- Pattern: "spec template = response to past failure mode" — Augment Code (2026)
- Pattern: "domain-scoped retrieval" — DEV Memory Binding article (2026)
- Pattern: "lessons bank + root_cause_class" — ACE paper arXiv 2602.20478

### Task 1: Ingestion Script + ai/lessons/ Structure
**Type:** code
**Files:**
  - create: `scripts/build-lessons-index.py`
  - create: `ai/lessons/.gitkeep`
**Pattern:** Простой Python скрипт, pattern-matching + optional LLM-assisted classification
**Acceptance:** `python scripts/build-lessons-index.py --dry-run` без ошибок на пустом ai/archive/

### Task 2: Update spark-codebase Agent
**Type:** code
**Files:**
  - modify: `template/.claude/agents/spark/codebase.md`
  - modify: `.claude/agents/spark/codebase.md`
**Pattern:** Добавить раздел `## Lessons Retrieval` в конец файла (после Risks)
**Acceptance:** Раздел присутствует, содержит Step 1-3, output section в template

### Task 3: Update Spark Feature Mode (Historical Risks + Gate 7)
**Type:** code
**Files:**
  - modify: `template/.claude/skills/spark/feature-mode.md`
  - modify: `.claude/skills/spark/feature-mode.md`
**Pattern:** Вставить секцию в Phase 5 template + Gate 7 в Phase 6 Validation
**Acceptance:** `grep "Historical Risks" template/.claude/skills/spark/feature-mode.md` → 2 результата (template + gate)

### Task 4: Update Autopilot Task-Loop (Lesson Extraction)
**Type:** code
**Files:**
  - modify: `template/.claude/skills/autopilot/task-loop.md`
  - modify: `.claude/skills/autopilot/task-loop.md`
**Pattern:** Добавить Lesson Extraction под-шаг в Step 6.5 DIARY RECORD
**Acceptance:** Раздел присутствует, trigger указан (debug_attempts > 0), inline pattern (ADR-007)

### Task 5: Template CLAUDE.md — document ai/lessons/
**Type:** code
**Files:**
  - modify: `template/CLAUDE.md`
**Pattern:** Добавить `ai/lessons/` в Project Structure section
**Acceptance:** `grep "ai/lessons/" template/CLAUDE.md` → 1 result

### Task 6: Backlog Entry
**Type:** code
**Files:**
  - modify: `ai/backlog.md`
**Pattern:** Добавить TECH-180 в Active Tasks таблицу
**Acceptance:** `grep "TECH-180" ai/backlog.md` → 1 result

### Execution Order
1 → 2 → 3 → 4 → 5 → 6

---

## Flow Coverage Matrix

| # | Step | Covered by Task | Status |
|---|------|-----------------|--------|
| 1 | Ingestion script создаёт ai/lessons/ из архива | Task 1 | ✓ |
| 2 | spark-codebase читает ai/lessons/ для домена | Task 2 | ✓ |
| 3 | research-codebase.md содержит Historical Risks секцию | Task 2 | ✓ |
| 4 | Spark Phase 5 template содержит ## Historical Risks | Task 3 | ✓ |
| 5 | Spark Phase 6 Gate 7 проверяет наличие секции | Task 3 | ✓ |
| 6 | Autopilot Step 6.5 извлекает урок при debug_attempts > 0 | Task 4 | ✓ |
| 7 | Урок пишется в ai/lessons/<domain>/L-NNN.md | Task 4 | ✓ |
| 8 | ai/lessons/ задокументирован в project structure | Task 5 | ✓ |
| 9 | Backlog обновлён | Task 6 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Spark-codebase находит уроки для домена | ai/lessons/billing/ содержит L-001.md | research-codebase.md содержит ## Historical Risks с L-001 | deterministic | design | P0 |
| EC-2 | Spark-codebase обрабатывает отсутствие ai/lessons/ | ai/lessons/ не существует | research-codebase.md содержит "No lessons bank" | deterministic | design | P0 |
| EC-3 | Gate 7 блокирует спеку без секции | spec без ## Historical Risks | validation fails gate 7 | deterministic | design | P0 |
| EC-4 | Gate 7 проходит при "none" | spec с "none" в Historical Risks | validation passes gate 7 | deterministic | design | P1 |
| EC-5 | Lesson extraction при debug | debug_attempts=2, domain=billing | ai/lessons/billing/L-NNN.md создан | deterministic | design | P1 |
| EC-6 | Lesson extraction НЕ срабатывает при success | debug_attempts=0 | ai/lessons/ не изменился | deterministic | design | P1 |
| EC-7 | Ingestion script с --dry-run | пустой ai/archive/ | exit 0, no files created | deterministic | design | P1 |

### Coverage Summary
- Deterministic: 7 | Integration: 0 | LLM-Judge: 0 | Total: 7

### TDD Order
EC-2 → EC-1 → EC-3 → EC-4 → EC-5 → EC-6 → EC-7

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command | Expected | Timeout |
|----|-------|---------|----------|---------|
| AV-S1 | Ingestion script синтаксически корректен | `python -m py_compile scripts/build-lessons-index.py` | exit 0 | 5s |
| AV-S2 | Historical Risks section в feature-mode.md | `grep "lessons-binding v1" template/.claude/skills/spark/feature-mode.md` | exit 0 | 2s |
| AV-S3 | Lesson Extraction в task-loop.md | `grep "Lesson Extraction" template/.claude/skills/autopilot/task-loop.md` | exit 0 | 2s |
| AV-S4 | Lessons Retrieval в codebase.md | `grep "Lessons Retrieval" template/.claude/agents/spark/codebase.md` | exit 0 | 2s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Template-sync корректен | - | `diff template/.claude/agents/spark/codebase.md .claude/agents/spark/codebase.md` | exit 0 (identical) |
| AV-F2 | ai/lessons/ directory exists | - | `ls ai/lessons/` | exit 0 |
| AV-F3 | Gate 7 присутствует в валидации | - | `grep "Gate 7" template/.claude/skills/spark/feature-mode.md` | exit 0 |

### Verify Command

```bash
# Smoke
python -m py_compile scripts/build-lessons-index.py
grep "lessons-binding v1" template/.claude/skills/spark/feature-mode.md
grep "Lesson Extraction" template/.claude/skills/autopilot/task-loop.md
grep "Lessons Retrieval" template/.claude/agents/spark/codebase.md
# Functional
diff template/.claude/agents/spark/codebase.md .claude/agents/spark/codebase.md
diff template/.claude/skills/spark/feature-mode.md .claude/skills/spark/feature-mode.md
diff template/.claude/skills/autopilot/task-loop.md .claude/skills/autopilot/task-loop.md
ls ai/lessons/
grep "Gate 7" template/.claude/skills/spark/feature-mode.md
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] spark-codebase агент читает ai/lessons/ и включает топ-5 в research-codebase.md
- [ ] Spec template содержит ## Historical Risks с корректным маркером
- [ ] Gate 7 в Phase 6 validation проверяет наличие секции
- [ ] task-loop Step 6.5 записывает уроки при debug_attempts > 0
- [ ] build-lessons-index.py работает без ошибок

### Tests
- [ ] EC-1 через EC-7 проверены вручную или через smoke tests

### Technical
- [ ] template/.claude/ и .claude/ идентичны для изменённых файлов (diff = 0)
- [ ] ai/lessons/.gitkeep committed
- [ ] No regressions (другие spark/autopilot функции не сломаны)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
