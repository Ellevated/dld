# Agent Roles: Роли в DLD v3.0

## Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SPARK                                       │
│   Идея → Socratic Dialogue → Research (Exa/Context7) → Spec        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ auto-handoff
┌─────────────────────────────────────────────────────────────────────┐
│                        AUTOPILOT                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 0: Worktree + CI check + baseline                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 1: PLAN SUBAGENT (ultrathink → detailed tasks)         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 2: FOR EACH TASK (fresh subagent per task!)            │  │
│  │                                                              │  │
│  │   CODER → TESTER → DOCUMENTER → TWO-STAGE REVIEW → COMMIT   │  │
│  │              ↓ fail                         ↓ needs_refactor │  │
│  │          DEBUGGER ←────────────────────────────┘             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 3: Final verify → merge → push → cleanup               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              ↓ stuck (3+ retries)                  │
│                          COUNCIL                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Spark (Specification)

**Скилл:** `/spark`
**Модель:** Opus (глубокий анализ)

### Что делает
1. **Socratic Dialogue** — 5-7 глубоких вопросов (один за раз)
2. **Research** — Exa (паттерны, примеры) + Context7 (official docs)
3. **5 Whys** — для багов (root cause до spec)
4. **Spec** — `ai/features/TYPE-XXX.md` с Allowed Files

### Границы (из "Planner")

| Spark спрашивает | Spark решает сам |
|------------------|------------------|
| "Какую проблему решаем?" | Технический подход |
| "Кто пользователь?" | Паттерны реализации |
| "Какой минимальный scope?" | API design |
| "Как проверим что работает?" | Тайминги, ретраи |

### Результат
```
ai/features/FTR-XXX-YYYY-MM-DD-name.md
├── Зачем / Контекст
├── Scope (in/out)
├── Allowed Files (STRICT!)
├── Approaches (с Research Sources)
├── Implementation Plan
└── Definition of Done
```

### Auto-handoff
После spec → автоматически запускает Autopilot (без ручного шага).

---

## Plan Subagent (Детализация)

**Тип:** Subagent в Autopilot
**Модель:** Opus + ultrathink

### Когда включается
Если spec не содержит `## Detailed Implementation Plan`.

### Что делает
1. **Ultrathink** — глубокий анализ spec + codebase
2. **Декомпозиция** — разбивает на атомарные задачи
3. **Acceptance criteria** — для каждой задачи
4. **Execution order** — зависимости между задачами

### Результат
Добавляет в spec:
```markdown
## Detailed Implementation Plan

### Task 1: Create model
Type: code | Files: create src/domains/X/models.py | Acceptance: ...

### Task 2: Add repository
Type: code | Files: create src/domains/X/repository.py | Acceptance: ...

### Execution Order
1 → 2 → 3
```

---

## Coder (Реализация)

**Тип:** Fresh subagent per task
**Модель:** Sonnet (90% capability, 2x speed)

### Что делает
1. Читает task из плана
2. **Проверяет Allowed Files** — файл не в списке = STOP
3. Использует Research Sources из spec
4. Пишет код + тесты
5. Возвращает `files_changed`

### Ключевое
- **Fresh context** — каждая задача = новый subagent
- **No gold plating** — только то что в spec
- **Allowlist enforcement** — не в списке = blocked

### LLM-Friendly Gates
- ≤400 LOC per file (600 for tests)
- ≤5 exports in `__init__.py`
- Import direction: `shared ← infra ← domains ← api`

---

## Tester (Проверка)

**Тип:** Fresh subagent per task
**Модель:** Sonnet

### Smart Testing
Не гоняет всё подряд — выбирает по `files_changed`:

| Changed file | Tests to run |
|--------------|--------------|
| `src/domains/seller/prompts/*` | `./test llm -k seller` |
| `src/domains/buyer/*` | `pytest tests/test_buyer_*.py -n auto` |
| `src/infra/db/*` | `./test fast` |

### Scope Protection
```
TEST FAILED
  │
  ├─ Related to files_changed?
  │   └─ YES → DEBUGGER → fix
  │
  └─ NOT related?
      └─ DON'T FIX! Log: "⚠️ Out-of-scope: test_X. SKIPPED."
```

Не чинит чужие баги — только то что сломал.

---

## Debugger (Root Cause)

**Тип:** Fresh subagent (вызывается при fail)
**Модель:** Opus (глубокий анализ)

### Когда включается
Tester fails + in-scope failure.

### Что делает
1. Анализирует traceback
2. 4-phase debugging: Reproduce → Isolate → Root Cause → Hypothesis
3. Возвращает `fix_hypothesis` + `affected_files`

### Лимиты
- Max 3 debug loops per task
- After 3 → Council escalation

---

## Two-Stage Review

### Stage 1: Spec Reviewer
**Модель:** Sonnet

**Вопрос:** "Код соответствует spec ТОЧНО?"

| Результат | Действие |
|-----------|----------|
| `approved` | → Stage 2 |
| `needs_implementation` | → CODER добавляет |
| `needs_removal` | → CODER удаляет лишнее |

### Stage 2: Code Quality Reviewer
**Модель:** Opus
**Скилл:** `/review`

**Вопрос:** "Архитектура, дублирование, качество?"

| Результат | Действие |
|-----------|----------|
| `approved` | → COMMIT |
| `needs_refactor` | → CODER fix → re-review (max 2) |

### Commit Gate
```
⛔ NO COMMIT without BOTH reviewers approved!

Only path:
  SPEC REVIEWER: approved
    → CODE QUALITY REVIEWER: approved
      → COMMIT
```

---

## Documenter

**Тип:** Runs in main context
**Модель:** Sonnet

### Что делает
1. Проверяет — нужно ли обновить docs?
2. Обновляет: README, ARCHITECTURE.md, ADR
3. Пишет Autopilot Log в spec

### Когда пропускает
- Файлы `.claude/*`, `*.md` — no tests, no docs needed

---

## Council (Escalation)

**Скилл:** `/council`
**Модель:** Opus (5 экспертов)

### Когда включается
- Debug loop > 3
- Refactor loop > 2
- Architecture decision нужен

### Состав
| Эксперт | Фокус |
|---------|-------|
| Product Manager | UX, user journey, edge cases |
| Architect | DRY, SSOT, dependencies |
| Pragmatist | YAGNI, complexity, feasibility |
| Security | OWASP, attack surfaces |
| **Synthesizer** | Финальное решение |

### Возвращает
```yaml
decision: solution_found | architecture_change | needs_human
solution: "..."
fix_steps: [...]
```

---

## Model Routing (Cost Optimization)

| Agent | Model | Rationale |
|-------|-------|-----------|
| Spark | Opus | Deep analysis, architecture |
| Plan | Opus + ultrathink | Task decomposition |
| Coder | Sonnet | 90% capability, 2x speed |
| Tester | Sonnet | Running tests, parsing |
| Debugger | Opus | Root cause analysis |
| Spec Reviewer | Sonnet | Spec matching |
| Code Quality Reviewer | Opus | Architecture review |
| Documenter | Sonnet | Routine updates |
| Council | Opus | Complex decisions |

**Экономия:** Sonnet для routine → 50%+ cost reduction.

---

## Резюме: Mapping концепция → реализация

| Концепция (исходная) | Реализация DLD v3.0 |
|----------------------|---------------------|
| Planner | **Spark** + **Plan Subagent** |
| Developer | **Coder** (fresh per task) |
| Tester | **Tester** + Smart Testing + Scope Protection |
| Supervisor | **Autopilot orchestrator** + **Two-Stage Review** |
| Anti-looping | **Debug/Refactor limits** → **Council escalation** |

---

**Назад:** [01-double-loop.md](01-double-loop.md) — концепция двух петель
**К практике:** [../00-bootstrap.md](../00-bootstrap.md) — как начать проект
