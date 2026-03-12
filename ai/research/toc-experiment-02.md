# TOC Experiment #2: Vanilla vs TOC v1 vs TOC v2 (Multi-Pass Single Agent)

**Date:** 2026-02-13
**Status:** Complete
**Project:** Awardybot (BUG-477: Buyer flow breaks)
**Previous:** `toc-experiment-01.md` (Round 1)

---

## Experiment Design

**Goal:** Compare three approaches on the SAME bug with controlled prompt injection.

**Bug:** Same BUG-477 as Round 1 — "Разрывы в User Flow байер-бота"

**Key difference from Round 1:** This time Spark had explicit bug-mode (5 Whys baseline), and TOC versions were injected into bug-mode Phase 3.

### Three runs

| ID | File | Spark Config |
|----|------|-------------|
| A | `round 2/BUG-477-...(ванила).md` | Vanilla Spark (5 Whys bug-mode) |
| B | `round 2/BUG-477-...(toc v1).md` | TOC v1: CRT single-agent (`toc-v1-crt.md`) |
| C | `round 2/BUG-477-...(toc v2).md` | TOC v2: Multi-pass single-agent (`toc-layer.md` with Pass 1/2/3) |

---

## Raw Results

### Spec A — Vanilla (5 Whys)

**Problems found (2):**
1. Двойное сообщение "✅ Принято!" при переходе между шагами
2. Reply keyboard сбрасывает FSM state в proof flow

**Methodology:** 5 Whys (4 levels each), separate root cause per problem.

**Strengths:**
- Нашёл ОБЕ user-facing проблемы (двойное сообщение + reply keyboard)
- Конкретные code examples (StateFilter)
- Impact Tree Analysis
- Balanced — не ушёл в одну сторону

**Weaknesses:**
- Только 2 проблемы (поверхностный поиск)
- 0 NBR
- Нет convergence analysis
- Нет fix validation

### Spec B — TOC v1 (CRT single-agent)

**Problems found (5 UDEs):**
1. Reply keyboard в slot_proof перебрасывает
2. Потеря контекста при возврате к заданию
3. Race condition set_state в proofs.py
4. Навигация "нет пути назад к текущему шагу"
5. Разное поведение search_flow vs proofs при approve

**Methodology:** CRT with causal chains, convergence, core problem, EC injection, fix validation.

**Strengths:**
- 5 UDEs (vs 2 у vanilla) — "bugs travel in packs" работает
- Convergence: все 5 UDE к одному core problem (100% coverage)
- Fix Conflict + EC injection (state filter + inline кнопка "Отменить")
- 3 NBR с safeguards
- VERDICT: GO

**Weaknesses:**
- Пропустил "двойное сообщение ✅ Принято!" (крупный user-facing симптом)
- Нет code examples (кроме StateFilter)
- Нет reproduction steps для UDE-3,4,5
- Нет прогресс-бара, задержки DB, мигания photo

### Spec C — TOC v2 (Multi-Pass single agent)

**Problems found (6 UDEs + 7 Code Issues = 10+ unique):**

UDEs:
1. Двойное сообщение "✅ Принято!"
2. FSM state flip-flop SEARCH → ORDER
3. Нет прогресс-бара
4. Несогласованные клавиатуры search vs step
5. Задержка DB re-fetch между confirm и instructions
6. Photo delete + new message = мигание

Code Issues (A1-A7):
- A1: Dead-end промежуточный state
- A2: Двойной save_fsm_to_db
- A3: Данные не передаются по цепочке
- A4: "✅ Принято!" — лишнее сообщение
- A5: Разные клавиатуры
- A6: Нет индикатора прогресса
- A7: show_search_instructions не мигрирована

**Methodology:** Three-section output: Pass 1 (TOC), Pass 2 (Code Audit), Pass 3 (Adversarial + Merge)

**Strengths:**
- Максимум находок (10+)
- Лучший code audit (A1-A7 с категориями)
- 5 fixes с code examples (включая progress bar implementation)
- 7 NBR с safeguards
- Cross-check Pass 1 ↔ Pass 2
- Adversarial challenges (Reversal, Alternative, Predicted)

**Weaknesses:**
- ПРОПУСТИЛ reply keyboard (основной user-reported баг!)
- Scope creep: прогресс-бар, миграция search flow — это enhancement, не bugfix
- 323 строки (vs 124 vanilla) — дорого

---

## Comparison Matrix

### Issues found

| Issue | A (Vanilla) | B (TOC v1) | C (TOC v2) |
|-------|:-----------:|:----------:|:----------:|
| Reply keyboard сбрасывает FSM | **+** | **+** (deep) | - |
| Двойное сообщение "✅ Принято!" | **+** | - | **+** |
| Race condition / state flip-flop | - | **+** | **+** |
| Разное поведение search vs proofs | - | **+** | **+** |
| Навигация "нет пути назад" | - | **+** | - |
| Несогласованные клавиатуры | - | - | **+** |
| Нет прогресс-бара | - | - | **+** |
| Задержка DB re-fetch | - | - | **+** |
| Photo delete мигание | - | - | **+** |
| show_search_instructions не мигрирована | - | - | **+** |
| **TOTAL unique** | **2** | **5** | **6 UDE + 7 code** |

**Overlap:** Reply keyboard найден в A+B. Двойное сообщение в A+C. State race в B+C. Остальное — уникальные находки.

### Metrics

| Metric | A (Vanilla) | B (TOC v1) | C (TOC v2) |
|--------|-------------|------------|------------|
| Issues found | 2 | 5 | 10+ |
| Root cause structure | Linear (5 Whys) | Tree (CRT) | Tree + Checklist |
| Convergence | No | Yes (100%) | Yes (100%) |
| NBR count | 0 | 3 | 7 |
| Code examples | 1 | 1 | 5 |
| Reproduction steps | 2 scenarios | 2 scenarios | 2 scenarios |
| Fix approaches | 2 | 4 | 5 |
| Allowed Files | 7 | 5 | 8 |
| Spec size (lines) | 124 | 179 | 323 |
| **Missed main symptom?** | No | Partially | **YES** |

---

## Critical Finding: Multi-Pass ≠ Multi-Agent

### What we expected

Three separate analytical passes:
1. Pass 1 (TOC Analyst): build CRT independently
2. Pass 2 (Code Auditor): scan code with fresh eyes, different lens
3. Pass 3 (Adversarial): genuinely challenge both analyses

### What actually happened (from conversation log)

```
1. Agent read toc-layer.md (prompt with 3-pass instructions)
2. Agent read ~20 code files (standard investigation)
3. Agent said: "Переходю к multi-pass анализу"
4. ONE Write call → 324 lines → complete spec with all 3 "passes"
```

**Three passes did NOT happen.** The agent did ONE generation pass and FORMATTED the output as three sections.

### Evidence

1. **Pass 3 (Adversarial) is weak** — "Reversal UDE-2: Может state flip-flop не ощущается? — Нет..." — rubber-stamp, not genuine challenge
2. **Cross-check is perfect** — "A1↔UDE-2 ✓, A3↔UDE-5 ✓" — of course it maps perfectly, same brain wrote both
3. **All three "passes" have the same blind spot** — reply keyboard missing from ALL sections. If passes were truly independent, at least one might have caught it.

### Root Cause

**Single agent = single context = single lens.** No matter how many "passes" the prompt requests, the agent builds ONE mental model during code reading and generates ONE analysis from it. The "passes" are structural sections, not cognitive phases.

This is the same anchoring bias we identified in Experiment #1, now proven empirically:
- Self-validation in prompt = performative
- "Different lens" requires different context (different agent)

### Implication

**Multi-pass single-agent is WORSE than separate subagents**, because:
1. It costs MORE tokens (324 lines vs 179 for v1)
2. It gives FALSE confidence (looks thorough, has blind spots)
3. The adversarial phase is fake (no genuine challenge)
4. Same blind spot across all "passes" (reply keyboard missed by all three)

---

## Updated Architecture Decision

### Previous (from Experiment #1)

> "Two teammates, not one hybrid"

### Updated (from Experiment #2)

> "Two teammates via SEPARATE AGENTS, not separate sections in one prompt"

Implementation options:
1. **Sequential subagents** (Task tool) — available now
2. **Agent Teams** (mailbox) — research preview, better but experimental

### Next: Experiment #3

Real multi-agent: TOC Analyst as subagent → Code Auditor as subagent → Lead merges.

Key difference: each subagent has its OWN context, reads files independently, builds its OWN mental model. No anchoring between them.

---

## Comparison: Round 1 vs Round 2

| Insight | Round 1 | Round 2 |
|---------|---------|---------|
| Different approaches find different things | Confirmed (3 lenses) | Confirmed again |
| ~15% overlap | ~15% | Similar (~20%) |
| TOC finds more UDEs | 5 vs 4 (vanilla) | 5 vs 2 (vanilla) |
| CRT convergence works | Yes | Yes (100% both) |
| Self-validation doesn't work | Suspected | **Proven** (multi-pass = decoration) |
| Code audit + TOC = complementary | Suspected | **Proven** (unique finds per approach) |
| NBR quality | 6 (v1) | 3 (v1), 7 (v2) |

### New insights (Round 2 only)

1. **Multi-pass single prompt doesn't work** — formatting, not cognition
2. **TOC v2 has scope creep** — progress bar, migration = enhancement, not bugfix
3. **Vanilla is most balanced** — finds both user-facing symptoms, doesn't overcommit
4. **Best combination** = Vanilla balance + TOC depth + Code Audit breadth = need separate agents

---

*Experiment conducted by human + Claude Opus 4.6 on Awardybot project.*
*Conversation log confirms single-pass generation despite multi-pass prompt.*
