# Bug Hunt: Архитектура

**Date:** 2026-02-14
**Based on:** Round 4 results (H1-H5), 42 agent runs, ~730 raw findings

---

## Как выглядит СЕЙЧАС (audit skill)

```
User: /audit buyer
  ↓
Claude (один контекст, один агент):
  - Читает файлы
  - Анализирует
  - Пишет отчёт
  ↓
Отчёт: ~10-15 findings
```

**Проблема:** Один агент = одна линза = <17% покрытия (Round 1 "ground truth").

---

## Как должно выглядеть (bug-hunt)

```
User: /bug-hunt src/domains/buyer/

  ┌─── PHASE 1: HUNT (параллельно, изолированно) ───┐
  │                                                    │
  │  Task(Explore) ──→ UX Designer findings            │
  │  Task(Explore) ──→ Security Engineer findings       │
  │  Task(Explore) ──→ Architect findings               │
  │  Task(Explore) ──→ Code Reviewer findings           │
  │  Task(Explore) ──→ QA Engineer findings             │
  │  Task(Explore) ──→ Junior Developer findings        │
  │                                                    │
  └────────────────────────────────────────────────────┘
                          ↓
                    GATE 1: Все 6 вернулись?
                    ├─ Нет → retry failed agents
                    └─ Да ↓

  ┌─── PHASE 2: DEDUP (один агент, sonnet) ──────────┐
  │                                                    │
  │  Вход: 6 списков findings (~100-120 raw)           │
  │  Действие: семантическая дедупликация              │
  │  Выход: ~70-80 unique, categorized, severity-rated │
  │                                                    │
  └────────────────────────────────────────────────────┘
                          ↓
                    GATE 2: Dedup complete?
                    ├─ Нет → error, return raw
                    └─ Да ↓

  ┌─── PHASE 3: CROSS-POLLINATION (опционально) ─────┐
  │                                                    │
  │  Вход: Phase 2 deduped list + target files         │
  │  "Вот что нашли другие. Найди что ПРОПУСТИЛИ."     │
  │                                                    │
  │  Task(Explore) ──→ Architect (100% precision)       │
  │  Task(Explore) ──→ UX Designer                      │
  │  Task(Explore) ──→ QA Engineer                      │
  │                                                    │
  └────────────────────────────────────────────────────┘
                          ↓
                    GATE 3: Merge + final dedup
                          ↓

  ┌─── PHASE 4: REPORT ─────────────────────────────┐
  │                                                    │
  │  Выход: ai/bug-hunt/YYYY-MM-DD-{target}.md        │
  │  Формат: categories, severity, code refs           │
  │  Метрика: N unique / M raw / K agents              │
  │                                                    │
  └────────────────────────────────────────────────────┘
```

---

## Ключевые принципы (из Round 4)

| Принцип | Реализация | Откуда знаем |
|---------|------------|--------------|
| Isolated contexts | Каждая персона = отдельный Task(Explore) | Все эксперименты |
| Formal prompts | Agent Role Definition, не "порви проект" | H1: +27% vs emotional |
| Free exploration | Агенты сами выбирают файлы | H5: fixed files = -9% |
| Personas essential | 6 конкретных ролей | H2: без персон = -23% |
| Two-pass multiplier | Phase 3 cross-pollination | H3-proxy: +68% |
| Frameworks for RCA | Не в discovery phase | H4: marginal for discovery |

---

## 6 персон (Phase 1)

Из H1, ranked by unique rate:

### 1. UX Designer (70% unique rate — highest)

```
You are a UX Designer reviewing this codebase.

EXPERTISE: User journey, interaction flow, feedback loops, error states visible to users.

FOCUS:
- Walk through every user-facing flow end-to-end
- Identify dead-ends, missing feedback, confusing transitions
- Check: does the user ALWAYS know what to do next?
- Check: does every error state have a recovery path?

OUTPUT: List of findings. Each finding:
- ID (UX-001, UX-002...)
- File:line
- Severity (CRITICAL/HIGH/MEDIUM/LOW)
- Description: what's wrong from user perspective
- Expected: what user should experience
```

### 2. Security Engineer (64% unique rate)

```
You are a Security Engineer auditing this codebase.

EXPERTISE: OWASP Top 10, input validation, auth bypass, data leakage, injection.

FOCUS:
- Every user input → where does it go? Sanitized?
- Every auth check → can it be bypassed?
- Every data query → can user access others' data?
- Every external call → SSRF? Injection?

OUTPUT: List of findings. Each finding:
- ID (SEC-001, SEC-002...)
- File:line
- Severity (CRITICAL/HIGH/MEDIUM/LOW)
- Attack vector: how to exploit
- Impact: what attacker gets
```

### 3. Architect (61% unique rate)

```
You are a Software Architect reviewing this codebase.

EXPERTISE: System design, state management, coupling, consistency patterns, race conditions.

FOCUS:
- State management: is state consistent across components?
- Coupling: which modules know too much about each other?
- Race conditions: concurrent access to shared state?
- Error propagation: do errors bubble up correctly?

OUTPUT: List of findings. Each finding:
- ID (ARCH-001, ARCH-002...)
- File:line
- Severity (CRITICAL/HIGH/MEDIUM/LOW)
- Pattern: what architectural principle is violated
- Impact: what breaks under load/scale
```

### 4. Code Reviewer (48% unique rate)

```
You are a Senior Code Reviewer doing a thorough PR review.

EXPERTISE: Code quality, error handling, edge cases, silent failures, dead code.

FOCUS:
- Every try/except → what's caught? What's silenced?
- Every conditional → what's the else case?
- Every TODO/FIXME → is it actually a bug?
- Dead code, unreachable branches, unused imports

OUTPUT: List of findings. Each finding:
- ID (CR-001, CR-002...)
- File:line
- Severity (CRITICAL/HIGH/MEDIUM/LOW)
- Description: what's wrong with this code
- Fix: concrete suggestion
```

### 5. QA Engineer (44% unique rate)

```
You are a QA Engineer designing test scenarios for this codebase.

EXPERTISE: Edge cases, boundary conditions, integration failures, data flow validation.

FOCUS:
- What happens with empty/null/zero inputs?
- What happens when external services timeout?
- What happens with concurrent requests?
- What's NOT tested that should be?

OUTPUT: List of findings. Each finding:
- ID (QA-001, QA-002...)
- File:line
- Severity (CRITICAL/HIGH/MEDIUM/LOW)
- Scenario: reproduction steps
- Expected vs Actual behavior
```

### 6. Junior Developer (33% unique rate — lowest but finds different things)

```
You are a Junior Developer reading this codebase for the first time.

EXPERTISE: Fresh eyes. You don't know "how it's supposed to work."

FOCUS:
- What's confusing? What took you multiple reads to understand?
- What looks like a bug but might be intentional? (flag it anyway)
- Where is the documentation wrong or missing?
- What would you break if you tried to modify this code?

OUTPUT: List of findings. Each finding:
- ID (JR-001, JR-002...)
- File:line
- Severity (CRITICAL/HIGH/MEDIUM/LOW)
- Confusion: what's unclear
- Risk: what could go wrong if someone misunderstands this
```

---

## Phase 3 персоны (cross-pollination)

Только high-precision агенты. Получают deduped list из Phase 2.

```
Here are {N} findings from 6 independent reviewers:

{deduped_findings}

You are {persona}. Your job: find what they ALL MISSED.
Do NOT repeat findings from the list.
Focus on gaps between their findings — systemic issues that fall
between individual perspectives.
```

Агенты: Architect (100% precision в H3), UX Designer, QA Engineer.

---

## Gate Checks (детерминистические)

### Gate 1: Phase 1 Complete
```
Проверить: все 6 Task agents вернули результат
Проверить: каждый результат содержит хотя бы 1 finding
Проверить: формат parseable (ID, file:line, severity)

Если < 4 из 6 вернулись → STOP, report partial results
Если формат broken → попробовать распарсить best-effort
```

### Gate 2: Dedup Complete
```
Проверить: dedup agent вернул structured output
Проверить: total unique < total raw (dedup happened)
Проверить: каждый finding имеет severity

Если dedup failed → вернуть raw concatenated (degraded mode)
```

### Gate 3: Cross-pollination Complete
```
Проверить: new findings ∩ Phase 2 findings = ∅ (no duplicates)
Если есть дупликаты → удалить, логировать dedup failure rate
Merge Phase 2 + Phase 3 → final report
```

---

## Стоимость

| Mode | Agents | Expected Yield | Cost |
|------|--------|----------------|------|
| Single-pass (default) | 6 Explore | ~76 unique | $6-10 |
| Two-pass (--deep) | 6 + 3 | ~128 unique | $12-20 |
| Manual dev review | 1 human | ~10-15 | $2,000 |

**ROI: 1000-1800x vs manual.** (Round 4 data)

---

## Что НЕ входит в bug-hunt

| Задача | Где делать |
|--------|-----------|
| Fix bugs | `/spark` → `/autopilot` |
| Root cause analysis | `/spark` debug mode (TOC/Pearl для RCA) |
| Architectural decisions | `/council` |
| Single-zone audit | `/audit {zone}` |

Bug-hunt = DISCOVERY only. Максимальное покрытие, минимальная глубина на каждый баг.
Depth = другие скиллы (spark, council).

---

## Реализация в DLD

### Файлы

```
.claude/skills/bug-hunt/SKILL.md     — orchestrator prompt
.claude/agents/bug-hunter.md          — НЕ НУЖЕН (Explore agents, не custom)
ai/bug-hunt/                          — output reports
```

### SKILL.md структура

Скилл описывает ПРОЦЕСС, не результат:

```
Phase 1: Launch 6 Task(Explore) in parallel
  → each gets persona prompt + target path
  → each returns structured findings

Gate 1: Validate all returned

Phase 2: Launch 1 Task(general-purpose) for dedup
  → input: all 6 results concatenated
  → output: deduped, categorized, severity-rated

Gate 2: Validate dedup output

[If --deep]: Phase 3: Launch 3 Task(Explore) with Phase 2 output
  Gate 3: Merge

Phase 4: Write report to ai/bug-hunt/
```

Каждая Phase = явный шаг с явным выходом.
Каждый Gate = проверка ПЕРЕД следующим шагом.
Агент-оркестратор НЕ МОЖЕТ пропустить Phase 2 потому что Phase 3 ЗАВИСИТ от её output.

---

## Отличие от autopilot (BUG-084 prevention)

| Autopilot (BUG-084) | Bug-hunt |
|---------------------|----------|
| 7 шагов в ОДНОМ промпте | 4 фазы с GATES между ними |
| Агент сам решает порядок | Порядок физически enforced зависимостями |
| Может забатчить 29 задач | Каждая фаза ЖДЁТ предыдущую |
| "Не пропускай шаги" (инструкция) | Следующий шаг невозможен без output предыдущего (архитектура) |
