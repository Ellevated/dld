# DLD v2 Vision: TOC-Powered AI Agent Framework

**Date:** 2026-02-12
**Status:** Early exploration
**Context:** See also:
- `toc-thinking-processes.md` — TOC methodology research (14 sections, 80+ sources)
- `agent-teams-anthropic.md` — Agent Teams / Mailbox research

---

## Origin Story

DLD v1 — удачная сборка существующих идей:
- Super Power Skills → .claude/skills/
- Ralph Loop → autopilot loop mode
- Claude Agent patterns → subagent orchestration

DLD v2 — **новая парадигма**: AI агенты, которые ДУМАЮТ, а не pattern-match.

---

## Core Insight

### Проблема масштабирования (человеческая аналогия)

Каждый новый человек в команде добавляет:
- Неопределённость
- Communication overhead
- Coordination cost

Этот паттерн **переносится на AI-агентов**:
- Люди экономят токены
- Упрощают pipeline
- Сокращают количество агентов
- Ищут "короткий путь"

**Результат:** Короткий путь = кривой и нестабильный.

### Решение: Не экономить, а ДУМАТЬ правильно

TOC Thinking Processes — это не "ещё один агент в pipeline".
Это **навык мышления**, встроенный в КАЖДОГО агента, которому он нужен.

---

## Три ключевых направления DLD v2

### 1. TOC как встроенный навык мышления (не отдельный слой)

**Принцип:** При малейшем подозрении, что агент может "задуматься не о том" — загрузить ему TOC паттерн.

**Где нужно:**

| Агент/Скилл | Какие TOC инструменты | Зачем |
|---|---|---|
| **Bootstrap** | CRT + EC + Socratic | Извлечь ВСЁ на старте. Найти конфликты в требованиях. Разрешить через EC, не спрашивая человека |
| **Spark** | EC + FRT + Scout | Разрешать конфликты в требованиях самостоятельно. Валидировать решения через FRT. Исследовать реализацию через Scout |
| **Planner** | CRT + PRT + FRT | Root cause для drift detection. Obstacle-driven planning. Валидация плана через FRT (negative branches) |
| **Reviewer** | CRT + NBR | Находить root cause проблем в коде (не симптомы). NBR: "Какие проблемы создаст этот код?" |
| **Debugger** | CRT (усиленный) | Формальный root cause analysis вместо "попробуем починить" |
| **Council** | EC (нативно) | Разрешение конфликтов между экспертами через invalidation assumptions |

**Где НЕ нужно (escalate к старшему):**

| Агент | Почему не нужно | Escalation path |
|---|---|---|
| Coder | Исполнитель, не мыслитель | → Planner или Debugger |
| Tester | Запускает тесты, не анализирует | → Debugger |
| Documenter | Фиксирует, не решает | → Planner |
| DevOps/Committer | Механический процесс | → Debugger при ошибках |
| Diary-recorder | Capture only | → Reflect для анализа |

### 2. Адаптация TOC под LLM агентов

**Вопрос:** Фреймворк Голдратта создан для людей/организаций. Что адаптировать для AI?

**Гипотезы для исследования:**

- **CRT**: LLM может hallucinate causation → нужен более строгий evidence grounding
- **EC**: LLM склонен к compromise → нужен explicit FORBIDDEN: compromise
- **FRT/NBR**: LLM оптимистичен → нужен adversarial agent для NBR
- **Sufficiency logic**: LLM хорош в if-then → это его сильная сторона
- **Assumption surfacing**: LLM может генерить 100 assumptions → нужен фильтр качества
- **Формат**: Деревья TOC → JSON/DAG структуры (машиночитаемые)

**Что может быть ЛУЧШЕ чем у людей:**
- LLM может держать в голове всё дерево целиком (200K context)
- LLM не устаёт — может проверить ВСЕ 8 CLR для каждой связи
- LLM может параллельно запустить adversarial agent для NBR
- LLM + Exa = мгновенный research для grounding assumptions

### 3. Agent Teams / Real-time Collaboration (Opus 4.6)

**Текущий DLD v1 flow:**
```
Autopilot → Planner → Coder → Tester → Debugger → Review → Commit
(последовательно, каждый агент = изолированный subprocess)
```

**Vision DLD v2 flow:**
```
Autopilot (Team Lead) создаёт "комнату"
  ├─ Planner (System Analyst) — анализирует задачу
  ├─ Coder (Developer) — пишет код
  ├─ Tester (QA) — готовит тесты
  ├─ Reviewer (Senior Dev) — следит за качеством
  ├─ DevOps — управляет git
  └─ Documenter — документирует

Все в одной "комнате" (Mailroom):
- Coder пишет → сразу спрашивает Planner если что-то неясно
- Tester готовит test plan ПОКА Coder пишет
- Reviewer видит код в реальном времени
- Если Coder сомневается → не гадает, а спрашивает
- Если Tester видит edge case → сообщает Coder ДО того как тот закончит
```

**Преимущества:**
- Параллельная работа где возможно
- Real-time feedback (не ждать 3 debug loops)
- Меньше итераций (проблемы ловятся раньше)
- Ближе к реальной команде разработки

**Результаты исследования (см. agent-teams-anthropic.md):**
- Research preview, flag: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Mailbox (не Mailroom) — `~/.claude/teams/{team-name}/`
- Каждый teammate = полная Claude сессия (token cost linear)
- Proof: 16 агентов собрали C compiler, 100K LOC, $20K
- Ограничения: нельзя resume, нет file locking для edits, ephemeral
- **Гибридный подход для DLD:** Agent Teams для complex tasks, subagents для simple

---

## CRT Analysis: Текущие проблемы DLD v1

### Core Problem

> "DLD приоритизирует AI-агентные capabilities над детерминистической инфраструктурой
> (тесты, checks, sync enforcement, feedback loops)"

### 14 UDE (Undesirable Effects)

| # | UDE | Chain |
|---|-----|-------|
| 1 | Autopilot останавливается после approval вместо commit | A: No enforcement |
| 2 | Git hooks падают в worktrees | B: No tests |
| 3 | Context accumulation mid-spec | D: No deterministic context |
| 4 | Hooks zero test coverage | B: No tests |
| 5 | Template↔Root docs drift | A: No enforcement |
| 6 | AI review wastes tokens on obvious | C: No feedback loops |
| 7 | Loop mode docs miss git push | A: No enforcement |
| 8 | No escaped defect tracking | C: No feedback loops |
| 9 | Hooks migration incomplete | B: No tests |
| 10 | No deterministic pre-review checks | C: No feedback loops |
| 11 | Debug loops = main bottleneck | C: No feedback loops |
| 12 | Domain contexts empty | A: No enforcement |
| 13 | Effort parameter unclear | D: No deterministic context |
| 14 | Drift monitoring only at planning | C: No feedback loops |

### Evaporating Cloud

```
A: Выпустить мощный AI-agent фреймворк быстро

B: Max AI capabilities          C: Ensure reliability
   ↓                               ↓
D: Spend time on features       D': Spend time on infra

CONFLICT: D vs D'
```

**Weakest assumption:** "AI агенты не могут сами строить свою инфраструктуру"

**Injection:** Встроить генерацию инфраструктуры В САМИ агенты.
Каждый агент порождает тесты/checks как побочный продукт основной работы.

---

## Фильтр вопросов (Bootstrap → TOC Layer → Specs)

```
Bootstrap собрал requirements от человека
    ↓
TOC Layer анализирует каждый вопрос:
    ├─ Domain question? → СПРОСИТЬ человека
    │   "Кто твой клиент? Какая бизнес-модель?"
    │
    ├─ Implementation question? → Scout/Exa НАЙТИ
    │   "Какой стек для real-time? Как платежи?"
    │
    ├─ Logical conflict? → EC РАЗРЕШИТЬ
    │   "Нужна скорость И надёжность — как?"
    │
    ├─ Potential problem? → CRT ПРЕДВИДЕТЬ
    │   "Что может пойти не так с этим подходом?"
    │
    └─ Needs validation? → FRT ПРОВЕРИТЬ
        "Если мы сделаем X, действительно ли получим Y?"
    ↓
Только НАСТОЯЩИЕ domain-вопросы доходят до человека
Всё остальное решается автоматически
    ↓
Auto-generate specs → Autopilot executes
```

---

## Переход от v1 к v2

| Аспект | DLD v1 | DLD v2 |
|--------|--------|--------|
| Мышление | Pattern matching | Logical derivation (TOC) |
| Человек | Bottleneck между этапами | Только domain expertise |
| Вопросы | Все к человеку | Только domain → человеку |
| Конфликты | Обнаруживаются при coding | EC разрешает ДО кода |
| Агенты | Последовательная цепочка | Real-time team (Agent Teams) |
| Инфраструктура | Отдельная задача | Побочный продукт каждого агента |
| TOC | Не используется | Встроен в каждый ключевой агент |
| Оркестрация | subprocess isolation | Mailroom collaboration |

---

## Open Questions

1. Насколько хорошо LLM реально выполняет sufficiency logic? (нужен PoC)
2. Как адаптировать TOC diagrams для machine-readable формата?
3. Agent Teams — production-ready или research preview?
4. Стоимость полного TOC pipeline per spec ($4-8) — acceptable?
5. Как измерить улучшение quality от TOC? (A/B test on specs)

---

## Next Steps

- [x] Research: Agent Teams / Mailbox (Anthropic 2026) → see `agent-teams-anthropic.md`
- [x] Research: Адаптация TOC для LLM → see `toc-experiment-01.md`
- [x] PoC: CRT Agent на реальном баге (BUG-477 Awardybot) → see `toc-experiment-01.md`
- [ ] PoC: EC Agent на реальном архитектурном конфликте
- [ ] Experiment #2: TOC v1 vs TOC v2 (multi-team) vs vanilla на том же баге
- [ ] Spec: TOC Thinking Layer architecture (based on experiment insights)
- [ ] Spec: Two-Teammate Spark architecture (Code Auditor + TOC Analyst)
- [ ] Spec: Bootstrap v2 (heavy, TOC-powered)
- [ ] Spec: Agent Teams integration

## Evolution of Thinking (chain of thought — do not overwrite, append only)

### 2026-02-12: Initial Vision

Три направления DLD v2:
1. TOC как встроенный навык мышления (не отдельный слой)
2. Адаптация TOC под LLM (6 гипотез: hallucinated causation, optimism bias и т.д.)
3. Agent Teams / Real-time Collaboration

Начальная идея: встроить TOC в КАЖДОГО агента которому нужно. CRT для debugger, EC для council, FRT для planner. Один агент = одна методология.

### 2026-02-13 (утро): Experiment #1 — CRT vs 5 Whys

Провели эксперимент на реальном баге (BUG-477 Awardybot).
Три прогона: Original (code audit), Vanilla (5 Whys), TOC (CRT).

**Неожиданный результат:** Три подхода нашли РАЗНЫЕ баги (~15% overlap).
Мы ожидали что TOC найдёт ТО ЖЕ САМОЕ но глубже. Оказалось — другую ПЛОСКОСТЬ.

- Original видит код (infrastructure, dead code, gaps)
- Vanilla видит симптомы (state bugs, interaction gaps)
- TOC видит систему (UX patterns, convergence, risk)

See `toc-experiment-01.md` for full comparison matrix.

### 2026-02-13 (день): Два тиммейта, не один гибрид

Из эксперимента родилась новая идея: **не мержить подходы в один промпт**, а запускать два отдельных агента с разным фокусом.

Первая мысль: просто параллельные subagents → два списка → merge.
Развитие: Agent Teams с mailbox → агенты ОБЩАЮТСЯ → cross-pollination.
Ещё глубже: adversarial phase → агенты АТАКУЮТ выводы друг друга.

**Ключевой инсайт (самый важный за день):**

> LLM не может self-validate. Anchoring bias: написал A←B, потом спрашиваешь "может ли A без B?" — он говорит "нет" потому что только что написал что не может.

Из этого следует:
- Self-validation в промпте = performative (checkbox ticking)
- CLR checks (#5 Additional Cause, #6 Reversal, #7 Predicted Effect) НЕ РАБОТАЮТ если делает тот же агент
- Валидация ДОЛЖНА быть от другого агента (нет anchoring к дереву)
- Один counter-example ("сломай своё дерево") > 120 checkbox-ов

Это LLM-специфичная адаптация TOC, аналог "файл < 400 LOC" для архитектуры.

### Design: Two-Teammate Architecture

```
Code Auditor (strengthened vanilla)    TOC Analyst (strengthened CRT)
Focus: CODE                            Focus: SYSTEM
Finds: infrastructure, dead code       Finds: patterns, convergence, risk
Output: issues[], code examples        Output: CRT, EC, FRT, NBR

Phase 1: independent investigation (parallel)
Phase 2: cross-pollination via mailbox
Phase 3: adversarial challenge (CLR by proxy)
```

Промпты:
- TOC v1 (tested): `ai/research/prompts/toc-v1-crt.md`
- TOC v2 multi-team (to test): `ai/research/prompts/toc-v2-multiteam.md`

Experiment #2 plan: три варианта на том же BUG-477:
1. Vanilla (baseline)
2. TOC v1 (single CRT agent)
3. TOC v2 (Code Auditor + TOC Analyst multi-team)

### 2026-02-13 (вечер): Experiment #2 — Multi-Pass = Фейк

Прогнали три варианта: Vanilla, TOC v1, TOC v2 (multi-pass).

**Главный результат:** TOC v2 нашёл БОЛЬШЕ ВСЕГО issues (10+), но ПРОПУСТИЛ reply keyboard — основной user-reported баг. А главное — три "прохода" оказались фикцией.

**Доказательство из лога:** Агент прочитал все файлы, сказал "переходю к multi-pass анализу", и записал 324 строки ОДНИМ вызовом Write. Никаких трёх отдельных проходов. Секции Pass 1/2/3 — форматирование, не когнитивный процесс.

**Почему:** Single agent = single context = single mental model. Агент строит ОДНУ картину при чтении кода, и раскладывает её по секциям. Pass 3 (Adversarial) не может честно атаковать Pass 1, потому что ТА ЖЕ голова писала оба.

**Доказательства:**
1. Adversarial = rubber-stamp: "Может UDE-2 не ощущается? — Нет..." (0.5 сек назад сам написал что ощущается)
2. Cross-check идеальный: "A1↔UDE-2 ✓" — одна голова = идеальный маппинг
3. ВСЕ три "прохода" пропустили reply keyboard — одно слепое пятно на все три

**Вывод:** Multi-pass в одном промпте ≠ multi-agent. Нужны ОТДЕЛЬНЫЕ субагенты с изолированными контекстами.

See `toc-experiment-02.md` for full comparison matrix.

### 2026-02-13 (вечер): Переход к реальным субагентам

Следующий шаг — Experiment #3: настоящий мультиагентный подход.

**Архитектура:**
```
Spark (Lead / Orchestrator)
  ├─ Phase 1-2: Reproduce + Isolate (сам)
  ├─ Phase 3a: Task(TOC Analyst) → CRT, UDEs, convergence, NBR
  ├─ Phase 3b: Task(Code Auditor + CRT) → code issues, challenges to CRT
  └─ Phase 3c: Merge → final spec
```

Каждый субагент:
- Своя сессия (изолированный контекст)
- Свой промпт (focus на своей линзе)
- Свои файлы для чтения (читает сам, строит свою картину)
- Code Auditor получает CRT от Analyst → cross-check + adversarial challenge

**Ключевое отличие от v2:** Код Auditor НЕ ВИДЕЛ как Analyst строил дерево. У него нет anchoring. Его challenges будут настоящими.

Промпты: `ai/research/prompts/toc-analyst.md`, `ai/research/prompts/code-auditor.md`

---

## Next Steps

- [x] Research: Agent Teams / Mailbox (Anthropic 2026) → see `agent-teams-anthropic.md`
- [x] Research: Адаптация TOC для LLM → see `toc-experiment-01.md`
- [x] PoC: CRT Agent на реальном баге (BUG-477 Awardybot) → see `toc-experiment-01.md`
- [x] Experiment #2: Vanilla vs TOC v1 vs TOC v2 (multi-pass) → see `toc-experiment-02.md`
- [ ] Experiment #3: Real multi-agent (subagents) на том же BUG-477
- [ ] PoC: EC Agent на реальном архитектурном конфликте
- [ ] Spec: TOC Thinking Layer architecture (based on experiment insights)
- [ ] Spec: Two-Teammate Spark architecture (Code Auditor + TOC Analyst)
- [ ] Spec: Bootstrap v2 (heavy, TOC-powered)
- [ ] Spec: Agent Teams integration (when GA)

---

## 2026-02-13 (ночь): Experiment #3 Results + v4 Prep

### Key Discovery: Agent Registration

Custom agents in `.claude/agents/` load at SESSION START only.
v3 corrected failed because files were written mid-session or just before session start.
Spark smartly fell back to general-purpose but methodology was degraded.

### Mega-Table Insight

22 unique bugs found across 10 runs. Key finding:
- CRT v1 ∩ Multi-pass = ZERO overlap
- Each methodology reproducibly finds its own cluster
- Need ALL approaches for >80% coverage

### v4 Changes

1. Agent files committed BEFORE session (registration fix)
2. effort: high for toc-analyst
3. toc-layer.md: "preserve CRT structure" + "don't fallback to general-purpose"
4. Troubleshooting section added

### Next Steps

- [x] Experiment #3 analyzed (v3 corrected = degraded mode)
- [ ] Experiment #4: v4 with proper agent registration
- [ ] If v4 works: compare CRT structure quality vs v1
- [ ] Long-term: investigate Agent Teams for parallel execution

---

## 2026-02-13 (ночь, продолжение): Frameworks Deep Research

4 параллельных скаута исследовали фреймворки за пределами TOC. Бюджет ~$5.

**Что нашли:**
- **TRIZ**: AutoTRIZ + TRIZ Agents (multi-agent LLM). IFR = "агенты координируются без координатора"
- **Cynefin**: Маршрутизация по типу проблемы (Clear→runbook, Complex→multi-agent probe)
- **Systems Thinking**: Leverage points Meadows = software. "Agentic AI Needs Systems Theory" (arXiv 2026-02-14)
- **Pearl Causal Inference**: STRONGEST формальный кандидат. do-calculus = provably correct RCA. IBM 2025 — уже в проде.
- **OODA Loop**: Темп. Orient = всё. Цикли быстрее чем баги накапливаются.
- **Kepner-Tregoe IS/IS-NOT**: Evidence BEFORE hypothesis. VDA-endorsed.
- **Morphological Analysis (Zwicky)**: Exhaustive exploration of solution space.

**Meta-наблюдение:** Скауты = чёрные ящики. Мы не знаем какие запросы они НЕ сделали, какие результаты отбросили. Та же проблема что BUG-477 (no single run >50%).

Full report: `ai/research/frameworks-deep-research.md`

---

## 2026-02-13 (ночь, продолжение): Experiment #4 (v4) Results

v4 с proper agent registration, effort:high, architectural lens.

**Результат: 7 UDEs** (архитектурный фокус):
- Reply keyboard handlers БЕЗ StateFilter → menu.py:278-325
- Router registration order → menu_router second in __init__.py
- Missing keyboards при rejection/cancel/moderation (proofs.py)
- Double state transition (search_flow.py:236-237)
- Orphan slot_proof_keyboard (keyboards/slots.py:146-157)

Все claims верифицированы по исходникам Awardybot.

Real teammates (Agent Teams) нашли 6 UDEs с UX-фокусом:
- UGC_PUBLISHED blank screen (CRITICAL) — через adversarial challenge
- Double message при одобрении proof
- No CTA в инструкциях

**Overlap v4 ∩ teammates: 1 из ~11 уникальных.** Разные линзы = разные баги.

---

## 2026-02-13 (поздняя ночь): PLOT TWIST — Persona Diversity > Frameworks

После всего framework research, эмпирика показала паттерн проще.

### Stout Prompt

Самый эффективный промпт пользователя на код-ревью:
> "Ты яростный критик опенсорс проектов на гитхаб. Порви этот молодой проект. За каждый найденный баг — бутылка стаута."

Ни фреймворка. Ни методологии. Просто **персона с мотивацией**.

### Experiment #5 Run 1: 27 defects

6 персон через parallel Explore agents:
1. Яростный критик (стаут за баг)
2. Параноидальный безопасник
3. UX-дизайнер (прошёл весь флоу руками)
4. Джун (читает код впервые)
5. Архитектор (тошнит от связности)
6. QA (платят за каждый баг)

**Результат: 27 defects** (5 critical, 10 high, 12 medium).
Compare: v4=7, teammates=6.
Стоимость: $6-10. Та же что v4 или teammates.

### Experiment #5 Run 2: 60 defects

Перезапуск того же подхода с лучшей дедупликацией.

**Результат: 60 unique defects** across 11 categories:
- A. State Persistence (11)
- B. State Recovery (3)
- C. Silent Bot (4)
- D. Dead/Stuck States (4)
- E. Race Conditions (8)
- F. Stale Callbacks (2)
- G. Validation (7)
- H. Navigation/UX (10)
- I. Error Handling (8)
- J. Architecture/Code Quality (10)
- K. Cosmetic (3)

Severity: 12 CRITICAL, 18 HIGH, 22 MEDIUM, 8 LOW.
Raw data: 105 entries from 6 agents → 60 unique after dedup.
Per-persona: Critic=24, Security=15, UX=20, Junior=12, Architect=18, QA=16 raw entries.

Spec: `test/round 3/BUG-477-2026-02-13-buyer-flow-breaks stout-run2-spec.md`

### Почему это работает

Смена персоны меняет не методологию, а КТО агент В КОНТЕКСТЕ:
- **Identity > Methodology**: Персона АКТИВИРУЕТ разные области знаний модели. Фреймворк ОГРАНИЧИВАЕТ до одной методологии.
- **Activation vs Constraint**: Для exploration (bug finding) activation wins. Для execution constraint wins.
- Frameworks (TOC, TRIZ, Pearl) = объяснение ПОЧЕМУ разные персоны находят разное. Но операционный механизм проще: разные персоны → разное поведение → разные баги.

### Пересмотр "ground truth"

Мы думали 22 бага (10 ранов, 3 раунда) = исчерпывающий список.
Stout нашёл 60. Наш "ground truth" покрывал менее 50% реального пространства проблем.

### Updated DLD v2 Vision

**Было:** TOC как встроенный навык мышления в каждого агента.
**Стало:** Persona diversity как PRIMARY механизм когнитивного разнообразия.

Фреймворки не бесполезны — они объясняют ПОЧЕМУ diversity работает и дают структуру для EXECUTION (фикс, а не поиск). Но для DETECTION — 6 простых персон × $6-10 = $36-60 дают покрытие, которое ни один фреймворк в одиночку не даёт.

### Оговорки

- N=2 на одном проекте (Awardybot BUG-477). Нужна проверка generalizability.
- Adversarial interaction (agent challenges agent) может добавлять ценность поверх parallel independent runs — UDE-7 в teammates нашёлся через challenge.
- Stout не нашёл Reply keyboard state filters и router priority (v4 нашёл). Полное покрытие = personas + architectural lens.

---

## Updated Next Steps

- [x] Research: Frameworks beyond TOC → see `frameworks-deep-research.md`
- [x] Experiment #4: v4 architectural lens = 7 UDEs
- [x] Experiment #5: 6-persona stout = 27 (run 1), 60 (run 2) defects
- [ ] **Generalizability test**: Persona approach on different project/bug
- [ ] **Cross-model diversity**: Test Gemini, GPT, DeepSeek with same persona prompts
- [ ] **Persona + Framework hybrid**: Architecture lens + persona diversity for max coverage
- [ ] **Skill design**: Encode persona-based review as DLD skill (structural, not instructional)
- [ ] PoC: EC Agent на реальном архитектурном конфликте
- [ ] Spec: Agent Teams integration (when GA)

---

*This document is the working vision for DLD v2.*
*Continue from here in next session: read ai/research/dld-v2-vision.md*
