# DLD v2: Архитектура потока Board → Architect → Spark → Autopilot

**Date:** 2026-02-15
**Status:** Design COMPLETE — all levels detailed, ready for implementation
**Context:** Продолжение `dld-v2-vision.md`. Результат анализа PLPilot (246 коммитов, 8 дней, 132 задачи).

---

## 1. Проблема: что показал PLPilot

PLPilot — первый полный проект на DLD. Bootstrap-сессия ~1 час, затем 8 дней разработки.

### Наблюдения

| Факт | Значение |
|------|----------|
| 246 коммитов за 8 дней | Высокая скорость |
| 50+ багов и 40+ TECH-задач после бутстрапа | Скорость → долг |
| Float для денег найден 4 раза (BUG-058, 080, 111, 120) | ADR написан, но не enforcement |
| Auth inconsistencies найдены 3 раза | Нет единой auth strategy |
| Telegram bot: 1,547 LOC, 0 unit тестов | Архитектура не спроектирована |
| Rename SubTracker → PLPilot на день 2 | Идея менялась на ходу |
| Биллинг добавлен на день 5 как "ещё одна фича" | Бизнес-модель не определена заранее |
| На каждую фичу бутстрапа ~1.5 фикса после | Системная проблема, не случайности |

### Корневая причина

**Два уровня принятия решений отсутствуют:**
1. **Бизнес-архитектура** — зачем, для кого, на какие деньги, через какие каналы
2. **Системная архитектура** — домены, данные, контракты, cross-cutting rules

Spark получал фичи и **сам принимал архитектурные решения на лету**. Каждый спарк решал локально, никто не видел систему целиком.

---

## 2. Текущий vs Новый flow

### Текущий (v1)

```
Bootstrap (CEO)  →  Spark (нач. отдела)  →  Autopilot (сотрудник)
   "что"              "как фича"              "код"
```

### Новый (v2)

```
Bootstrap (CEO)     →  Board (Совет Директоров)  →  Architect (Тех. Директор)  →  Spark (PM)  →  Autopilot (Dev)
"что и зачем"          "бизнес-архитектура"          "системная архитектура"      "фича"         "код"
```

### Воронка человеческого внимания

```
Bootstrap    ████████████  человек 100% (час-два разговора, brainstorm)
Board        ██████████    человек 80%  (критикует, возвращает, 2-3 раунда)
Architect    ██████        человек 40%  (верифицирует, approves)
Spark        ██            человек 0%   (вопросы → к Architect, не к человеку)
Autopilot    █             человек 0%   (полный аутсорс)
```

Принцип: **Founder решает "куда", а не "как".** Чем выше уровень — тем больше человеческого внимания. Чем ниже — тем больше автономии.

---

## 3. Универсальный паттерн: CRSДWR

Каждый уровень (Board, Architect, Spark, Autopilot) внутри устроен по одному паттерну:

```
Collect → Research → Synthesize → Decide → Write → Reflect
```

| Фаза | Кто | Что делает | Ключевое ограничение |
|------|-----|-----------|---------------------|
| **Collect** | Фасилитатор | Собирает информацию (диалог / чтение артефактов) | НЕ формирует решение |
| **Research** | N изолированных агентов параллельно | Исследуют каждый со своей линзы | НЕ видят друг друга |
| **Synthesize** | Один агент (opus) | Собирает все research в 2-3 альтернативы | НЕ выбирает |
| **Decide** | Человек или совещание | Выбирает подход из подготовленных | Видит trade-offs |
| **Write** | Механический агент (sonnet) | Записывает решение в формат | НЕ принимает решений |
| **Reflect** | Отдельный агент | Извлекает learnings | Два выхода: local + upstream |

### Почему разделение критично

**Confirmation bias:** Один агент, который и спрашивает, и исследует, и решает — к 3-му вопросу уже "знает" ответ. Остальные фазы становятся формальностью.

**Решение:** Тот, кто собирает → не исследует. Тот, кто исследует → не синтезирует. Тот, кто синтезирует → не решает. Тот, кто решает → не пишет.

---

## 4. Reflect Pipeline — нервная система между уровнями

### 4.1 Два выхода reflect

```
reflect
  ├→ LOCAL:    улучшить следующую итерацию ЭТОГО уровня
  └→ UPSTREAM: сигнал уровню ВЫШЕ, что допущение не работает
```

### 4.2 Четыре типа обратной связи

| Тип | Когда | Пример | Действие |
|-----|-------|--------|----------|
| **Local** | После каждого раунда | "Board R1: забыли unit economics → R2: спросить" | Следующая итерация этого уровня |
| **Upstream** | Нижний уровень нашёл противоречие с верхним | "Autopilot → Architect: auth strategy не покрывает Telegram" | Сигнал уровню выше |
| **Cross-level** | Паттерн повторяется N раз | "4-й раз float → дыра не в архитектуре" | Агрегация → эскалация |
| **Meta** | Процесс не работает | "Cross-critique не нашёл конфликт, synthesis пропустил" | Улучшение промпта/процесса |

### 4.3 Поток обратной связи

```
Board       ← "бизнес-модель не учитывает X"     ← Architect reflect
  ↓                                                  ↑
Architect   ← "домен Y не ложится в архитектуру"  ← Spark reflect
  ↓                                                  ↑
Spark       ← "фича Z противоречит фиче W"        ← Autopilot reflect
  ↓                                                  ↑
Autopilot   → reflect: "float для денег опять"  ────┘
```

### 4.4 Транспорт: файлы, не агенты

**Принцип:** Upstream сигналы передаются через файлы, не через live agents.
Уровни работают АСИНХРОННО — Board не ждёт пока Autopilot закончит.

```
ai/reflect/
├── upstream-signals.md     — append-only лог ВСЕХ upstream сигналов
├── cross-level-patterns.md — агрегированные паттерны (N повторов)
├── process-improvements.md — meta: что улучшить в процессе
└── digest-R{N}.md          — периодический digest для человека
```

### 4.5 Формат upstream сигнала

```markdown
## SIGNAL-{timestamp}

| Field | Value |
|-------|-------|
| Source | autopilot / spark / architect |
| Spec ID | FTR-042 |
| Target | spark / architect / board |
| Type | gap / contradiction / missing_rule / pattern |
| Severity | info / warning / critical |

### Message
{Что именно не работает}

### Evidence
{файл:строка, тест, ошибка — конкретное доказательство}

### Suggested Action
{Что, по мнению источника, нужно сделать}

---
```

### 4.6 Кто пишет upstream signals

| Уровень | Когда пишет | Куда пишет | Что пишет |
|---------|-------------|-----------|-----------|
| **Autopilot** | Phase 3 (после всех тасков) | upstream-signals.md | Gaps в спеке, blueprint conflicts, повторяющиеся баги |
| **Spark** | Phase 7 (Reflect) | upstream-signals.md | Blueprint gaps, недостающие cross-cutting rules |
| **Architect** | Phase 8 (Reflect) | upstream-signals.md | Business blueprint gaps, неверные допущения |
| **Board** | Phase 8 (Reflect) | process-improvements.md | Только meta (Board — верхний уровень) |

### 4.7 Кто читает upstream signals

| Уровень | Когда читает | Что читает | Что делает |
|---------|-------------|-----------|-----------|
| **Spark** | Phase 1 (Collect) | Signals с target=spark | Учитывает в problem-statement |
| **Architect** | Phase 1 (Brief) | Signals с target=architect | Добавляет в architecture-agenda |
| **Board** | Phase 1 (Brief) | Signals с target=board | Добавляет в board-agenda |
| **Reflect skill** | По запросу человека | ВСЕ signals | Агрегирует, предлагает системные изменения |

### 4.8 Cross-level паттерны: пороги и агрегация

```
Порог для эскалации:

  1 повтор → info (записать, ничего не делать)
  2 повтора → warning (добавить в digest)
  3 повтора → critical (автоматическая эскалация на уровень выше)

Агрегация:
  Reflect skill (opus) читает upstream-signals.md и:
  1. Группирует по topic (grep по ключевым словам)
  2. Считает повторы (сколько раз одна тема встречается)
  3. Если ≥3 → создаёт запись в cross-level-patterns.md
  4. Предлагает action: "Architect, обновите cross-cutting rule X"

Что считается "повтором":
  НЕ точное совпадение текста.
  Один topic = один bounded context / один cross-cutting concern.
  Пример: "float для денег" и "decimal для цены" = ОДИН topic (Money type).
```

### 4.9 Digest: как человек узнаёт о проблемах

```
Digest генерируется:
  - АВТОМАТИЧЕСКИ: после каждого 5-го upstream signal
  - ПО ЗАПРОСУ: /reflect (существующий скилл)
  - В КОНЦЕ ПРОЕКТА: Phase 3 Autopilot последней спеки

Формат digest:
  ## Reflect Digest — {date}

  ### Critical (требует действия)
  - [3×] Money type не enforcement → Architect: добавить validator
  - [3×] Auth inconsistency → Architect: unified auth strategy

  ### Warning (мониторить)
  - [2×] Telegram webhook timeout → возможно нужен retry

  ### Info (для контекста)
  - [1×] Новый edge case в billing → добавлен в тесты

  ### Process
  - Cross-critique пропустил конфликт Domain vs Security (Round 2)
  - Рекомендация: усилить prompt Security Architect
```

### 4.10 Meta-learning: как reflect кормит СЛЕДУЮЩИЙ проект

```
ai/reflect/process-improvements.md — копится от проекта к проекту.

Формат:
  ## {date}: {project_name}

  ### Board
  - CFO prompt: добавить вопрос про churn rate (пропустили в R1)
  - Devil: слишком мягкий, усилить contrarian stance

  ### Architect
  - Data Architect: нужен вопрос про migration strategy с дня 1
  - LLM-Ready Check: добавить "tool description overlap" check

  ### Spark
  - Devil scout: edge cases → mandatory в Tests секции (уже добавлено)
  - Auto-decide порог: поднять с "один подход" до "один подход + score >0.8"

  ### Autopilot
  - Blueprint compliance: false positive на legacy code → добавить exclude

/reflect скилл:
  1. Читает process-improvements.md
  2. Предлагает КОНКРЕТНЫЕ изменения в промптах/правилах
  3. Человек одобряет → изменения записываются в CLAUDE.md / agents / skills
```

### 4.11 Reflect vs Diary

```
Diary (существующий):
  ЧТО: проблемы и learnings ВНУТРИ одного уровня
  КОГДА: по триггерам (test_retry, escalation, bash_instead_of_tools)
  ГДЕ: ai/diary/
  КТО ЧИТАЕТ: /reflect skill

Reflect (новый):
  ЧТО: сигналы МЕЖДУ уровнями
  КОГДА: после каждого spec / раунда
  ГДЕ: ai/reflect/
  КТО ЧИТАЕТ: каждый уровень в Phase 1 (Brief/Collect)

Связь:
  Diary → входные данные для Reflect.
  Diary: "тест упал 3 раза на Money type" (факт)
  Reflect: "Money type нужен enforcement в Architect" (вывод)

  /reflect skill объединяет оба:
  Diary (проблемы) + Reflect (сигналы) → конкретные изменения в промптах
```

---

## 5. Уровень Board (Совет Директоров)

### Отличие от Council

| | Council (v1) | Board (v2) |
|--|-------------|------------|
| Уровень | Инженерный | Стратегический |
| Вопросы | "Как реализовать?" | "Нужно ли реализовывать?" |
| Участники | DevOps, Security, QA | Product, Finance, Marketing, Business Dev |
| Когда | Перед реализацией фичи | Перед проектированием системы |

### Состав Board

| Директор | Мировоззрение (чей mindset) | Линза | Вопрос-убийца |
|----------|----------------------------|-------|---------------|
| **CPO** | Jeanne Bliss (CCO Lands' End) | "CX — growth engine, не cost center" | "Что потеряет пользователь, если мы исчезнем завтра?" |
| **CFO** | Unit Economics мышление | "Не сходится юнит-экономика → масштаб убьёт" | "CAC payback < 12 мес? Если нет — бизнес не живёт" |
| **CMO** | Tim Miller (CRO Stack Overflow) | "Revenue ops — наука" | "Какой один повторяемый канал работает прямо сейчас?" |
| **COO** | Keith Rabois (COO Square) | "Triage. Barrels vs ammunition." | "Что сломается при ×10? Что агенты, что люди?" |
| **CTO** | Piyush Gupta (DBS Bank) | "Думай как стартап" | "Если бы строили с нуля — тот же стек?" |
| **Devil's Advocate** | Peter Thiel | Contrarian thinking | "Что ты знаешь такого, с чем никто не согласен?" |
| **Facilitator** | Chief of Staff | Ведёт процесс, НЕ голосует | Организует agenda, собирает артефакты |

### Внутренний процесс Board (8 фаз)

```
Phase 1: BRIEF (фасилитатор)
  Читает ai/idea/* от Bootstrap
  Формирует agenda из open-questions.md
  Раздаёт каждому директору контекст + его фокус
  Output: board-agenda.md

Phase 2: RESEARCH (6 директоров, параллельно, изолированно)
  Каждый получает:
  ├── ai/idea/* (общий контекст от Bootstrap)
  ├── board-agenda.md (фокус для его роли)
  └── Инструкция: "мин. 5 поисковых запросов, из них 2 deep research"

  Каждый директор:
  - Читает ТОЛЬКО input от фасилитатора
  - Выполняет МИНИМУМ 5 запросов через Exa/web
  - Из них МИНИМУМ 2 через deep_research (не просто web_search)
  - НЕ видит выводы других директоров

  CPO:  PMF, конкуренты, user needs, UX patterns
  CFO:  Unit economics, pricing benchmarks, TAM/SAM/SOM
  CMO:  Channels, CAC benchmarks, acquisition strategies
  COO:  Operating model, automation vs human, agent architecture
  CTO:  Build vs buy, стек, масштабируемость, tech trends
  Devil: Почему не взлетит, kill scenarios, competitive threats

  Output: research-{role}.md × 6

Phase 3: CROSS-CRITIQUE (Karpathy Protocol, как в Council)
  Каждый директор видит АНОНИМНЫЕ research от других:
  - "Research A: [content]" (не "CFO сказал...")
  - "Research B: [content]"
  - ...

  Каждый отвечает:
  - Agree/disagree с каждым + почему
  - Какие gaps и слабые места видит
  - Ranking: лучший → худший research

  Labels вместо имён → снижает anchoring bias
  Output: critique-{role}.md × 6

Phase 4: SYNTHESIS (фасилитатор, opus)
  Читает:
  ├── 6 research files
  ├── 6 cross-critique files
  └── board-agenda.md

  Собирает 2-3 альтернативных стратегии
  Для каждой стратегии — подробная структура:

  ## Стратегия A: {название}

  ### Суть
  {2-3 абзаца}

  ### Почему именно так
  - Канал: X → потому что [CMO research: "данные..."]
  - Модель: Y → потому что [CFO research: "данные..."]

  ### Сложные места (⚠️)
  - ⚠️ {проблема}: {контекст}
    [CTO: "цитата из research"]
    Альтернатива: {что делать если не сработает}

  ### Цифры
  | Метрика | Значение | Источник |
  |---------|----------|----------|
  | TAM | ... | CFO research |
  | Target CAC | ... | CMO research |

  ### Org model (COO)
  | Процесс | Кто | Почему |
  |---------|-----|--------|
  | ... | AI agent / Human / Hybrid | [COO: "..."] |

  ### Риски (Devil's Advocate)
  1. {риск} — вероятность — митигация

  Если стратегии конфликтуют → Evaporating Cloud
  Output: strategies.md

Phase 5: PRESENTATION (→ человеку)
  Founder видит strategies.md — подробный, структурированный документ
  Каждое решение — с ссылкой на research конкретного директора
  Founder критикует: "вот это хорошо, вот это переделать, вот это выкинуть"
  Output: founder-feedback-R{N}.md

Phase 6: ITERATE (раунд 2-3)
  ВСЕ 6 директоров идут заново:
  - Получают: предыдущий research + cross-critique + founder feedback
  - Исследуют ЗАНОВО с учётом новых данных (мин. 5 запросов)
  - Изменение в одной области может повлиять на все остальные
  - Cross-critique повторяется на новых research
  - Synthesis заново

  НЕ "только затронутые переисследуют" — ВСЕ заново.
  Каждый раунд = полный цикл Phase 2-3-4-5.

  Contradiction log: каждая проблема записывается,
  следующий раунд ОБЯЗАН адресовать каждый пункт.
  Валидатор проверяет: "все пункты из лога адресованы?"

Phase 7: WRITE (многошаговая цепочка)
  Step 1: DATA CHECK (validator, haiku)
    □ Все 6 директоров дали финальный research?
    □ Founder approved стратегию?
    □ Contradiction log пуст (все адресованы)?
    □ Нет открытых вопросов без ответов?
    GATE: pass / fail

  Step 2: DRAFT (sonnet)
    Пишет Business Blueprint по шаблону
    Все секции, все данные, все обоснования
    Качество: "можно идти рейзить деньги с этим документом"

  Step 3: EDIT (opus)
    Проверяет связность между секциями
    Добавляет cross-references
    Убирает противоречия
    Усиливает слабые места

  Step 4: VALIDATE (чеклист, haiku)
    □ Revenue model определён с конкретными цифрами?
    □ Каждый канал обоснован данными из research?
    □ Org model: для каждого процесса — agent/human/hybrid?
    □ Риски с митигациями для каждого?
    □ Unit economics: CAC, LTV, payback — все заполнены?
    □ Нет пустых секций, TBD, "later", TODO?
    □ Каждое утверждение имеет источник?
    GATE: pass / reject с причинами

  Output: ai/blueprint/business-blueprint.md

Phase 8: REFLECT (многоуровневый)
  LOCAL:   "В следующем Board спросить про X раньше"
  PROCESS: "Cross-critique нашёл gap, который research пропустил — усилить CMO prompt"
  META:    "Какие вопросы founder задал, которых не было в agenda?"
  UPSTREAM: (нет — Board верхний уровень, upstream = только founder)
  Output: reflect-board.md
```

---

## 6. Уровень Architect (Технический Директор)

### Вход

Business Blueprint (approved)

### Состав (7 персон + Devil + Facilitator)

| # | Роль | Чей mindset | Линза | Kill Question |
|---|------|-------------|-------|---------------|
| 1 | **Domain Architect** | Eric Evans (DDD) | "Границы по языку, не по технологиям" | "Можешь объяснить архитектуру только терминами бизнеса?" |
| 2 | **Data Architect** | Martin Kleppmann (DDIA) | "Data outlives code — модель первична" | "Что является system of record для каждой сущности?" |
| 3 | **Ops/Observability** | Charity Majors (Honeycomb) | "Если не видишь — не управляешь" | "Как ты узнаешь что это сломалось в проде?" |
| 4 | **Security Architect** | Threat modeling / shift-left | "Каждая система — один exploit от катастрофы" | "Какова модель угроз? Какая attack surface?" |
| 5 | **Evolutionary Architect** | Neal Ford (ThoughtWorks) | "Design for change — fitness functions" | "Какие fitness functions защищают это решение?" |
| 6 | **DX / Pragmatist** | Dan McKinley (Boring Tech) | "Innovation tokens — тратим на бизнес" | "Это решает бизнес-проблему или инженерное любопытство?" |
| 7 | **LLM Architect** | Erik Schluntz (Anthropic) | "Простота > сложность. Tools > prompts. Context = RAM" | "Может ли агент работать с этим API без чтения исходников?" |
| — | **Devil's Advocate** | Fred Brooks | "Conceptual integrity — или есть, или каша" | "Кто единственный отвечает за целостность системы?" |
| — | **Facilitator** | Chief Architect | Ведёт процесс, НЕ голосует | Agenda + artifacts + gates |

### LLM Architect — двойная роль

LLM Architect участвует дважды:
1. **Phase 2 (Research)** — за столом наравне со всеми, влияет на API design, domain boundaries, data contracts
2. **Phase 7 Step 4 (LLM-Ready Check)** — отдельный gate при записи System Blueprint

Что видит, чего другие не видят:
- Tool descriptions важнее промптов — API documentation = prompt для агента
- Context window = RAM — архитектура должна помещаться в контекст
- Structured outputs = контракты между агентами
- Overlap в tools = confusion для LLM
- Evals > unit tests для LLM-поведения
- "Start simple, add complexity only when measurable improvement"

Sources: Anthropic "Building Effective Agents", "Context Engineering", Chip Huyen "GenAI Platform", Eugene Yan "LLM Patterns"

### Внутренний процесс (8 фаз)

```
Phase 1: BRIEF (Facilitator)
  Читает Business Blueprint
  Извлекает:
  ├── Domains implied by business
  │   "подписки + биллинг + Telegram → 3 домена минимум"
  ├── Data needs
  │   "деньги → Money type, подписки → lifecycle states"
  ├── Integration needs
  │   "Telegram API, платёжка, email"
  ├── Constraints from Board
  │   "бюджет X, команда Y, дедлайн Z"
  └── Open questions
      "Board решил 'подписки' — но какой тип? Stripe? Внутренний?"

  Для каждой из 7 персон — фокусное задание:
  - Domain Architect: "определи bounded contexts из бизнес-процессов"
  - Data Architect: "предложи data model для каждого домена"
  - Ops: "как деплоить, мониторить, откатывать"
  - Security: "threat model для каждого integration point"
  - Evolutionary: "где будут точки изменений через 6 мес?"
  - DX/Pragmatist: "стек, tooling, developer workflow"
  - LLM Architect: "какие части agent-driven? tool design?"
  Output: architecture-agenda.md

Phase 2: RESEARCH (7 персон, параллельно, изолированно)
  Каждый получает:
  ├── Business Blueprint (контекст)
  ├── architecture-agenda.md (его фокус)
  └── Инструкция: "мин. 5 запросов, из них 2 deep research"

  НЕ видят выводы друг друга.

  Domain Architect:
    DDD patterns, bounded contexts, context mapping, ACL
    → research-domain.md

  Data Architect:
    Schema patterns, миграция, event sourcing vs CRUD, storage
    → research-data.md

  Ops/Observability:
    Deployment, SLOs, alerting, tracing, CI/CD, rollback
    → research-ops.md

  Security Architect:
    Threat model (STRIDE/OWASP), auth patterns, encryption
    → research-security.md

  Evolutionary Architect:
    Fitness functions, change points, tech debt prevention
    → research-evolutionary.md

  DX/Pragmatist:
    Tech stack (boring tech vs shiny), dev workflow, build vs buy
    → research-dx.md

  LLM Architect:
    Agent patterns, tool design, context budget, eval strategy,
    structured outputs, LLM anti-patterns
    → research-llm.md

  Output: research-{role}.md × 7

Phase 3: CROSS-CRITIQUE (Karpathy Protocol)
  Каждая персона получает АНОНИМНЫЕ research от остальных 6:
  - "Research A: [content]" (не "Data Architect сказал...")
  - "Research B: [content]"

  Каждый отвечает:
  - Agree/disagree с каждым + почему
  - Gaps и слабые места
  - Конфликты: "Research A предлагает X, но это ломает Y"
  - Ranking: лучший → худший research

  Labels вместо имён → снижает anchoring bias
  Output: critique-{role}.md × 7

Phase 4: SYNTHESIS (Facilitator, opus)
  Читает:
  ├── 7 research files
  ├── 7 cross-critique files
  └── architecture-agenda.md + Business Blueprint

  Строит 2-3 архитектурных варианта. Для каждого:

  ## Architecture A: {название}
  ### Domain Map
    [bounded contexts + interfaces]
  ### Data Model
    [entities, types, relationships]
    Обоснование: [Data Architect research: "..."]
  ### Tech Stack
    [language, framework, DB, infra]
    Обоснование: [DX research: "..."]
    Риск: [Evolutionary: "через 6 мес..."]
  ### Cross-Cutting Rules (КОД, не текст)
    Money type, Auth strategy, Error pattern
  ### Agent Architecture
    [tools, context, evals, structured outputs]
    Обоснование: [LLM Architect research: "..."]
  ### Ops Model
    [deploy, monitor, rollback]
  ### Risks (Devil's Advocate)

  Если архитектуры конфликтуют → Evaporating Cloud
  Output: architectures.md

Phase 5: PRESENTATION (→ человеку, 40% внимания)
  Founder верифицирует:
  - "Это бьётся с тем что Board решил?"
  - "Стек адекватен для моей команды?"
  - "Сложность соответствует appetite из Bootstrap?"
  НЕ принимает технических решений — валидирует соответствие
  бизнес-стратегии.
  Output: founder-feedback-R{N}.md

Phase 6: ITERATE (раунд 2-3)
  ВСЕ 7 персон идут заново:
  - Получают: предыдущий research + cross-critique + founder feedback
  - Исследуют ЗАНОВО (мин. 5 запросов)
  - Cross-critique повторяется
  - Synthesis заново

  НЕ "только затронутые переисследуют" — ВСЕ заново.
  Каждый раунд = полный цикл Phase 2-3-4-5.

  Contradiction log: каждый конфликт записывается,
  следующий раунд ОБЯЗАН адресовать каждый пункт.

Phase 7: WRITE (многошаговая цепочка)
  Step 1: DATA CHECK (validator, haiku)
    □ Все 7 персон дали финальный research?
    □ Founder approved архитектуру?
    □ Contradiction log пуст?
    □ Business Blueprint полностью покрыт?
    GATE: pass / fail

  Step 2: DRAFT (sonnet)
    System Blueprint:
    ├── domain-map.md         — bounded contexts + interfaces
    ├── data-architecture.md  — schema + types + constraints
    ├── api-contracts.md      — endpoints + auth + errors
    ├── cross-cutting.md      — Money, Auth, Errors, Logging (КОД!)
    ├── integration-map.md    — data flow between domains
    └── agent-architecture.md — tools, context, evals, structured outputs

  Step 3: EDIT (opus)
    Связность между файлами
    Cross-references: domain-map ↔ data-architecture ↔ api-contracts
    Убирает противоречия

  Step 4: LLM-READY CHECK (LLM Architect, отдельный gate)
    □ Tool descriptions не overlap?
    □ APIs описаны для агента без исходников?
    □ Structured outputs определены для LLM-взаимодействий?
    □ Context budget реалистичен?
    □ Eval strategy определена?
    GATE: pass / reject с причинами

  Step 5: STRUCTURAL VALIDATE (checklist, haiku)
    □ Каждый домен из Business Blueprint покрыт?
    □ У каждого домена: Data Model + API Surface + Integration?
    □ Cross-cutting определены: Money, Auth, Errors, Logging?
    □ Нет "TODO", "TBD", "later"?
    □ Data Model использует типы из cross-cutting?
    □ Каждое решение обосновано ссылкой на research?
    GATE: pass / reject

  Output: ai/blueprint/system-blueprint/

Phase 8: REFLECT (многоуровневый)
  LOCAL:    "В следующем Architect: Data нашёл gap в Phase 3 —
             усилить prompt"
  UPSTREAM: "Board, допущение 'один тип подписки' ведёт к
             3× сложности billing — пересмотрите?"
  PROCESS:  "Cross-critique нашёл конфликт Domain vs Security,
             который synthesis пропустил"
  META:     "Какие вопросы founder задал, которых не было в agenda?"
  Output: reflect-architect-R{N}.md
```

---

## 7. Уровень Spark (PM фичи)

### Ключевые изменения в v2

1. **Spark НЕ принимает архитектурных решений** — работает ВНУТРИ System Blueprint
2. **Мультиагентный** — 4 скаута + facilitator + validator (вместо 1 агента)
3. **Devil's advocate обязателен** — один из 4 скаутов
4. **Тесты обязательны** — секция Tests в шаблоне + gate в validator
5. **Эскалация к Architect**, не к человеку — для технических вопросов
6. **Auto-decide для простых фич** — человек 0% involvement
7. **Council для споров** — не дублируем cross-critique, используем существующий skill

### Почему НЕТ cross-critique на Spark

- Board/Architect: 1-3 раза на проект, stakes высокие → cross-critique оправдан
- Spark: 20+ раз на проект, feature-level → cross-critique дорого
- Если фича спорная → эскалация к Council (у которого cross-critique встроен)
- 4 isolated scouts + devil's advocate = достаточная diversity для feature-level

### Внутренний процесс (8 фаз)

```
Phase 1: COLLECT (Facilitator)
  Два режима:

  A) Человек инициирует фичу:
     Facilitator ведёт Socratic Dialogue (5-7 вопросов)
     Facilitator ТОЛЬКО собирает, НЕ формирует решение
     Вопросы: Problem, User, Current state, MVP, Risks
     + новые из Bootstrap v2 (Past Behavior, Kill Question)

  B) Architect/Board передаёт задачу:
     Facilitator читает задачу из blueprint
     Уточняющие вопросы → к Architect, НЕ к человеку

  В обоих случаях facilitator НЕ предлагает решений.
  Output: problem-statement.md

Phase 2: RESEARCH (4 скаута, параллельно, изолированно)
  Каждый получает:
  ├── problem-statement.md (контекст)
  ├── system-blueprint/ (constraint! НЕ для пересмотра)
  └── Инструкция: "мин. 3 запроса через Exa/Context7"

  НЕ видят выводы друг друга.

  scout-external:
    Best practices, библиотеки, production patterns
    Exa + Context7 (library docs)
    → research-external.md

  scout-codebase:
    grep, git log, зависимости, Impact Tree
    Что уже есть, что переиспользовать
    → research-codebase.md

  scout-patterns:
    Альтернативные подходы, trade-offs
    "Как это решают в похожих архитектурах?"
    → research-patterns.md

  devil's-advocate:
    "Почему это НЕ нужно делать?"
    "Можно ли решить промпт-изменением? Без кода?"
    "Что сломается? Какие edge cases?"
    → research-devil.md

  Output: research-{role}.md × 4

Phase 3: SYNTHESIZE (opus)
  Читает:
  ├── problem-statement.md
  ├── 4 research files
  └── system-blueprint/ (как constraint)

  2-3 подхода В РАМКАХ system blueprint:
  - Суть + основание из research
  - Файлы из scout-codebase
  - Риски из devil
  - Тесты для каждого подхода
  - Blueprint compliance: ✓ / ⚠️

  Если подходы конфликтуют → Evaporating Cloud
  Output: approaches.md

Phase 4: DECIDE
  A) AUTO (простая фича, один подход)
     → переходим к Write
  B) HUMAN (2-3 подхода)
     → человек выбирает
  C) COUNCIL (спорная/рискованная)
     → /council (5 экспертов + cross-critique)
  D) ARCHITECT (конфликт с blueprint)
     → architect обновляет blueprint → retry

Phase 5: WRITE (spec по шаблону, sonnet)
  Ключевые ДОБАВЛЕНИЯ к шаблону v1:

  ## Blueprint Reference (NEW)
    Domain: {какой домен из system blueprint}
    Cross-cutting: {Money? Auth? Errors?}
    Data model: {какие entities затрагиваются}

  ## Tests (NEW, MANDATORY)
    ### What to test
    - [ ] {test case 1}
    - [ ] {edge case from devil's advocate}
    ### How to test
    - Unit / Integration / E2E
    ### TDD Order
    1. Write test → FAIL → Implement → PASS
    ### DoD includes
    - [ ] Все test cases проходят
    - [ ] Coverage не упал

  Остальное как v1: Why, Scope, Allowed Files,
  Approaches, Design, Implementation Plan, DoD
  Output: ai/features/{TASK-ID}.md

Phase 6: VALIDATE (изолированный агент)
  Читает ТОЛЬКО spec + system-blueprint (не process history!)

  Spec gate:
  □ Достаточно информации для реализации?
  □ Нет противоречий с system blueprint?
  □ Allowed Files покрывают все tasks?
  □ Edge cases покрыты?
  □ DoD измеримо?

  Tests gate (NEW):
  □ Секция Tests заполнена?
  □ Минимум 3 test case?
  □ Есть edge case от devil's advocate?
  □ TDD Order определён?
  □ DoD включает тесты?

  Blueprint gate (NEW):
  □ Blueprint Reference заполнен?
  □ Cross-cutting rules применены?
  □ Data model соответствует data-architecture.md?

  GATE: pass / reject с причинами
  Reject → возврат к Phase 3

Phase 7: REFLECT
  LOCAL:    "В следующей спеке: devil нашёл edge case,
             который scout-external пропустил"
  UPSTREAM: "Architect, в blueprint не хватает
             webhook retry strategy — добавьте"
  PROCESS:  "Auto-select сработал для простой фичи"
  Output: reflect-spark.md (appended)

Phase 8: COMPLETION
  1. ID (sequential across all types)
  2. Write to ai/features/{ID}.md
  3. Add to ai/backlog.md (status: queued)
  4. Commit spec
  5. Handoff to autopilot
```

---

## 8. Уровень Autopilot v2

### Что НЕ меняется

Текущий autopilot v3.5 уже хорошо спроектирован:
- PHASE 0: Worktree Setup
- PHASE 1: Plan (planner subagent)
- PHASE 2: Task Loop (coder → tester → pre-check → spec-reviewer → code-quality → commit)
- PHASE 3: Finish (push → merge → cleanup)
- Escalation: debug 3× → Spark, architecture → Council
- Loop mode: fresh context per spec

Всё это остаётся.

### Что добавляется (3 изменения)

```
Изменение 1: REFLECT AFTER EACH SPEC (новый Step в Phase 3)
  После COMMIT всех тасков, ПЕРЕД push:

  reflect-autopilot (haiku):
    Читает:
    ├── spec (что планировали)
    ├── git diff (что реально сделали)
    ├── debug log (были ли retry?)
    └── escalation log (были ли)

    Output:
      LOCAL:    "В следующей спеке: X"
      UPSTREAM: "Spark, в спеке {ID} не хватало Y"
                "Architect, cross-cutting rule Z не работает в контексте W"

    Формат upstream сигнала:
      {
        source: "autopilot",
        spec_id: "FTR-042",
        target: "spark" | "architect",
        type: "gap" | "contradiction" | "missing_rule",
        message: "...",
        evidence: "файл:строка — что именно не работает"
      }

    Записывается в: ai/reflect/upstream-signals.md (append)

    GATE: reflect всегда pass (информационный, не блокирующий)

Изменение 2: ESCALATION ROUTING v2
  Текущая маршрутизация:
    code bug → Spark (BUG spec)
    architecture → Council

  Новая маршрутизация:
    code bug → Spark (BUG spec)                    ← без изменений
    spec gap → Spark (уточнение спеки)             ← NEW
    blueprint conflict → Architect (обновление)    ← NEW
    architecture decision → Council                ← без изменений
    business question → STOP + upstream to Board   ← NEW

  Правило: Autopilot НИКОГДА не решает вопросы выше своего уровня.
  Если вопрос не про код — эскалация вверх.

Изменение 3: BLUEPRINT COMPLIANCE CHECK (новый Step в Pre-Check)
  После pre-review-check.py, ПЕРЕД spec-reviewer:

  Если ai/blueprint/system-blueprint/ существует:
    □ Используемые типы = типы из cross-cutting.md?
    □ Imports direction = architecture.md?
    □ Domain placement = domain-map.md?
    □ Error pattern = cross-cutting.md?

  Если не существует (legacy проект без blueprint):
    → skip (backwards compatible)

  GATE: pass / fail → coder fix → retry
```

### Что НЕ добавляется (и почему)

- **Cross-critique** — нет. Autopilot = execution, не discussion.
- **Персоны** — нет. Coder, tester, reviewer = функции, не personas.
- **Research** — нет. Всё исследовано на предыдущих уровнях.
- **Iterative rounds** — нет. Task loop уже итеративный (debug/refactor loops).

### Обновлённый Phase 3 (Finish)

```
Phase 3: FINISH (обновлённый)
  1. Final test suite (как сейчас)
  2. REFLECT (NEW — см. Изменение 1)
     └─ записать upstream signals
  3. Status → done (как сейчас)
  4. Push feature branch (как сейчас)
  5. Merge develop (как сейчас)
  6. Push develop (как сейчас)
  7. Cleanup worktree (как сейчас)
```

### Обновлённый Task Loop (Step 3 расширен)

```
Step 3: PRE-CHECK (обновлённый)
  3a. pre-review-check.py (как сейчас, если существует)
  3b. BLUEPRINT COMPLIANCE (NEW, если blueprint существует)
      □ Типы из cross-cutting?
      □ Import direction?
      □ Domain placement?
      GATE: pass / fail → coder fix → retry
```

---

## 9. Принципы проектирования

### Из исследований Bug Hunt (Round 1-4)

| Принцип | Применение |
|---------|-----------|
| **Persona Identity > Methodology** | Директора — это ПЕРСОНЫ (CFO, CMO), не "функции" |
| **Isolation** | Каждый исследователь не видит других |
| **Research-first** | Минимум 3 поисковых запроса перед рекомендацией |
| **Formal > Emotional** | Промпты формальные, структурированные |
| **Free exploration** | Не указываем ГДЕ искать, только ЧТО |
| **Cross-pollination** | Synthesis как second pass поверх isolated research |

### Из анализа PLPilot

| Принцип | Обоснование |
|---------|-------------|
| **Фасилитатор ≠ Решатель** | Confirmation bias к 3-му вопросу |
| **Devil's Advocate обязателен** | На каждом уровне — изолированный скептик |
| **Человек ВЫБИРАЕТ, не одобряет** | 2-3 варианта с trade-offs, не "согласен / не согласен" |
| **Правила как код, не как текст** | ADR-001 написан — float всё равно 4 раза |
| **Итеративность by design** | Линейный проход невозможен, архитектура сразу под 2-3 раунда |
| **Стоимость не ограничение** | $100-250 на Board << $2-3K на ручной дебаг после |

### TRIZ: Separation on Condition

**Противоречие:** Процесс должен быть детерминированным (не срезает углы) И адаптивным (бизнесы разные).

**Решение:** Процесс (фазы, gates, чеклисты) — фиксированный. Контент (ответы, решения, архитектура) — адаптивный. Как налоговая декларация: форма одна, цифры разные.

---

## 10. Escalation Routing

```
Autopilot вопрос по коду → Spark (спека)
Spark вопрос по архитектуре → Architect (system blueprint)
Architect вопрос по бизнесу → Board (business blueprint)
Board стратегический вопрос → Founder (человек)
```

Каждый уровень отвечает только на вопросы своей компетенции. Человек вовлекается только на уровне Board и выше.

---

## 11. Стоимость и ROI

### Оценка стоимости одного проекта (полный цикл)

| Уровень | Агентов | Модель | Оценка |
|---------|---------|--------|--------|
| Board (3 раунда × 5 директоров) | ~15 runs | sonnet + opus | $60-100 |
| Architect (2 раунда × 4 scouts) | ~8 runs | sonnet + opus | $30-50 |
| Spark (per feature, ~20 features) | ~80 runs | sonnet + opus | $100-200 |
| Autopilot (per feature) | ~100 runs | sonnet | $50-100 |
| **Итого** | | | **$240-450** |

### ROI

| Без Board+Architect (PLPilot) | С Board+Architect (projected) |
|-------------------------------|-------------------------------|
| 50+ багов после бутстрапа | Предотвращены на уровне blueprint |
| 4× float для денег | Money type определён в cross-cutting |
| Bot monolith 1,547 LOC | Service layer с дня 1 |
| Auth inconsistencies 3× | Auth strategy единая |
| ~40 TECH-задач на чистку | Шаблон соответствует архитектуре |
| Оценка: $500-2000 на фиксы | Оценка: $240-450 на prevention |

---

## 12. Bootstrap v2: Интервьюер, не решатель

### Что убираем

- **Phase 10 (Architecture)** — полностью. Это работа Architect.
- **Phase 8.5 (Research Validation)** — это работа Board, не Bootstrap.
- **Бизнес-решения** из product-brief (MLP scope, monetization choice) — Bootstrap записывает мысли founder, Board решает.

### Новый выход Bootstrap

```
ai/idea/
├── founder.md           — кто строит (опыт, мотивация, constraints, risk appetite)
├── problem.md           — боль, персона, частота, стоимость, текущие решения
├── solution-sketch.md   — видение founder (сырое, НЕ формализованное)
├── market-raw.md        — что founder ЗНАЕТ о рынке (beliefs, не факты)
├── terms.md             — словарь терминов
└── open-questions.md    — противоречия, красные флаги, что надо исследовать
```

**Принцип:** Bootstrap **открывает** информацию (сырая фактура + список неясностей). Board **закрывает** бизнес-решения. Architect **закрывает** технические решения.

### Новые блоки вопросов (из research)

Добавлены на основе YC interviews, M&A due diligence, Mom Test, JTBD, Shape Up:

| Блок | Вопросы | Источник | Чего не было |
|------|---------|----------|-------------|
| **Why Now** | "Почему сейчас? Что изменилось в мире?" / "Почему ещё никто не решил?" | YC, Sequoia | Отсутствовал полностью |
| **Past Behavior** | "Как решаешь сейчас? Сколько тратишь?" / "Что уже пробовал?" | Mom Test | Были гипотетики ("would you pay?") |
| **Purchase Timeline** | "Когда впервые подумал об этом? Что триггернуло?" | JTBD | Отсутствовал полностью |
| **Appetite** | "Это на 6 недель или 6 месяцев? Что готов вложить?" | Shape Up | Был только "hours per week" |
| **Kill Question** | "Что убьёт проект? Что сломается при ×10 росте?" | M&A DD | Были только yellow flags |

### Ключевые правила интервью (Mom Test)

- Спрашивай о **прошлом поведении**, не о гипотетическом будущем
- "Ты бы заплатил $10?" → ПЛОХО (гипотетика)
- "Сколько ты тратишь на это сейчас?" → ХОРОШО (факт)
- Если founder говорит "все" / "всегда" / "обычно" — это fluff, копай глубже
- Комплименты ("отличная идея!") = fool's gold

### Новые фазы Bootstrap

```
Phase 0: Founder (10-15 мин) — как сейчас
Phase 1: First Contact (5-10 мин) — как сейчас
Phase 2: Persona / Specific Vasya (10-15 мин) — как сейчас
Phase 3: Problem deep-dive (10-15 мин) — как сейчас
Phase 4: Past Behavior & Timeline (NEW, 10 мин)
  - "Как решаешь сейчас? Что уже пробовал?"
  - "Когда впервые подумал? Что триггернуло?"
  - "Сколько это стоит тебе сегодня?"
Phase 5: Solution sketch (10 мин) — записываем видение, НЕ формализуем
Phase 6: Market awareness (10 мин) — записываем beliefs founder, НЕ как факты
Phase 7: Why Now + Kill Question (NEW, 10 мин)
  - "Почему сейчас? Что изменилось?"
  - "Что убьёт проект? Что сломается при ×10?"
  - "Почему большая компания не скопирует за месяц?"
Phase 8: Appetite (NEW, 5 мин)
  - "Это на 6 недель или 6 месяцев?"
  - "Что готов вложить? Что готов потерять?"
Phase 9: Terms (5 мин) — как сейчас
Phase 10: Synthesis + Open Questions (10 мин)
  - Суммирует ВСЁ
  - Записывает ВСЕ противоречия и неясности в open-questions.md
  - "Это всё пойдёт в Совет Директоров для проработки"
```

### Что НЕ делает Bootstrap

- Не исследует рынок (это Board)
- Не выбирает монетизацию (это Board)
- Не проектирует домены (это Architect)
- Не определяет MLP scope (это Board → Architect → Spark)
- Не принимает никаких решений — только собирает и структурирует

### Research Sources

- **YC Interview Questions**: 78 вопросов, фокус на "why now?", traction, defensibility
- **M&A Due Diligence**: "Что сломается при ×3 росте?", customer concentration, key person risk
- **Mom Test (Fitzpatrick)**: Прошлое поведение > гипотетики, commitment > compliments
- **JTBD (Christensen/Moesta)**: Timeline покупки, struggling moment, switching forces
- **Shape Up (Singer)**: Appetite framing, anti-scope, rabbit holes
- **Lean Canvas (Maurya)**: Customer forces canvas, existing alternatives, inertia
- **SVPG (Cagan)**: Four Big Risks (value, usability, feasibility, viability)

---

## 13. Spark v2: Тесты как обязательная часть спеки

В шаблон спеки `/spark` добавляется обязательная секция:

```markdown
## Tests

### What to test
- [ ] {test case 1 — конкретный сценарий}
- [ ] {test case 2}
- [ ] {edge case 1}

### How to test
- Unit: {что покрыть unit тестами}
- Integration: {что требует интеграционных тестов}
- E2E: {если нужно — какой user flow}

### DoD includes
- [ ] Все test cases из этой секции проходят
- [ ] Coverage не упал
```

**Gate:** Spec-reviewer проверяет: "Секция Tests заполнена? Есть минимум 3 test case? DoD включает тесты?"

---

## 14. Structural Validators — gates как код

### 14.1 Проблема

Gates упомянуты на каждом уровне (Board Phase 7 Step 4, Architect Phase 7 Step 5, Spark Phase 6, Autopilot Pre-Check). Но:
- Нет единого формата
- Нет единого reject → retry flow
- Нет изоляции (validator не должен видеть process history)
- Нет ответа: кто валидирует? haiku agent? script? hook?

### 14.2 Два типа validators

```
DETERMINISTIC (script / hook):
  Проверяет ФОРМАТ, не СОДЕРЖАНИЕ.
  Примеры:
  - "Нет пустых секций?"
  - "Все обязательные поля заполнены?"
  - "Нет TODO/TBD/later?"
  - "Blueprint Reference секция есть?"
  - "Минимум 3 test case?"

  Реализация: Node.js script (как pre-review-check.py, но для specs/blueprints)
  Стоимость: 0 tokens
  Скорость: мгновенно

AI-BASED (haiku / sonnet agent):
  Проверяет СОДЕРЖАНИЕ и СВЯЗНОСТЬ.
  Примеры:
  - "Revenue model реалистичен?"
  - "Data model покрывает все use cases?"
  - "Cross-cutting rules непротиворечивы?"
  - "LLM-ready: tool descriptions не overlap?"

  Реализация: Isolated subagent с чеклистом
  Стоимость: $0.01-0.10 per check
  Скорость: 5-15 сек
```

### 14.3 Единый формат чеклиста

```markdown
## Gate: {gate_name}

**Level:** board / architect / spark / autopilot
**Phase:** {N}
**Type:** deterministic / ai-based
**Model:** haiku / sonnet (для ai-based)

### Checks

- [ ] {check_1} — {что проверяет}
- [ ] {check_2} — {что проверяет}
- [ ] {check_3} — {что проверяет}

### On Fail

**Retry to:** Phase {N} — {кто переделывает}
**Max retries:** {2-3}
**After max retries:** escalate to {level / human}
```

### 14.4 Каталог всех gates

```
BOARD:
  Gate B1: DATA CHECK (deterministic)
    Phase 7, Step 1
    □ Все 6 research files существуют?
    □ Founder approved стратегию?
    □ Contradiction log пуст?
    □ Нет открытых вопросов?
    On fail: → Phase 6 (Iterate)
    Max retries: 2

  Gate B2: BLUEPRINT VALIDATE (ai-based, haiku)
    Phase 7, Step 4
    □ Revenue model с конкретными цифрами?
    □ Каждый канал обоснован данными из research?
    □ Org model для каждого процесса?
    □ Риски с митигациями?
    □ Unit economics заполнены?
    □ Нет пустых секций, TBD, TODO?
    □ Каждое утверждение имеет источник?
    On fail: → Phase 7 Step 2 (re-draft)
    Max retries: 2

ARCHITECT:
  Gate A1: DATA CHECK (deterministic)
    Phase 7, Step 1
    □ Все 7 research files существуют?
    □ Founder approved архитектуру?
    □ Contradiction log пуст?
    □ Business Blueprint полностью покрыт?
    On fail: → Phase 6 (Iterate)
    Max retries: 2

  Gate A2: LLM-READY CHECK (ai-based, sonnet)
    Phase 7, Step 4
    □ Tool descriptions не overlap?
    □ APIs описаны для агента без исходников?
    □ Structured outputs определены?
    □ Context budget реалистичен?
    □ Eval strategy определена?
    On fail: → Phase 7 Step 2 (re-draft)
    Max retries: 2

  Gate A3: STRUCTURAL VALIDATE (deterministic + ai)
    Phase 7, Step 5
    □ Каждый домен из Business Blueprint покрыт?
    □ У каждого домена: Data Model + API + Integration?
    □ Cross-cutting определены: Money, Auth, Errors?
    □ Нет TBD/TODO/later?
    □ Каждое решение обосновано ссылкой?
    On fail: → Phase 7 Step 2 (re-draft)
    Max retries: 2

SPARK:
  Gate S1: SPEC VALIDATE (deterministic)
    Phase 6
    □ Все обязательные секции заполнены?
    □ Allowed Files перечислены?
    □ Implementation Plan с тасками?
    □ DoD измеримо?
    On fail: → Phase 5 (re-write)
    Max retries: 2

  Gate S2: TESTS VALIDATE (deterministic)
    Phase 6
    □ Секция Tests существует?
    □ Минимум 3 test case?
    □ Есть edge case от devil?
    □ TDD Order определён?
    □ DoD включает тесты?
    On fail: → Phase 5 (re-write)
    Max retries: 2

  Gate S3: BLUEPRINT COMPLIANCE (ai-based, haiku)
    Phase 6
    □ Blueprint Reference заполнен?
    □ Cross-cutting rules применены?
    □ Data model соответствует data-architecture.md?
    □ Нет конфликтов с system blueprint?
    On fail: → Phase 3 (re-synthesize) | → Architect (если blueprint нужно обновить)
    Max retries: 1 (затем эскалация)

AUTOPILOT:
  Gate P1: PRE-CHECK (deterministic, существующий)
    Step 3a в task-loop
    □ Нет TODO/FIXME?
    □ Файлы < 400 LOC?
    □ Bare except без re-raise?
    On fail: → coder fix → retry
    Max retries: 2

  Gate P2: BLUEPRINT COMPLIANCE (deterministic, новый)
    Step 3b в task-loop
    □ Типы из cross-cutting?
    □ Import direction?
    □ Domain placement?
    On fail: → coder fix → retry
    Max retries: 2

  Gate P3: SPEC REVIEW (ai-based, sonnet, существующий)
    Step 4 в task-loop
    On fail: → coder fix → retry
    Max retries: 2

  Gate P4: CODE QUALITY (ai-based, opus, существующий)
    Step 5 в task-loop
    On fail: → coder fix → retry → escalate to Council
    Max retries: 2
```

### 14.5 Reject → Retry flow

```
Универсальный flow для ВСЕХ gates:

  validator(input) → result
    ├── PASS → continue to next phase
    └── FAIL(reasons)
        ├── retry_count < max_retries?
        │   ├── YES → назад к retry_target phase
        │   │         с reasons как дополнительный input
        │   │         ("Validator отклонил: {reasons}. Исправь.")
        │   └── NO → escalate
        │       ├── Autopilot gate → Spark/Council
        │       ├── Spark gate → Architect/Council
        │       ├── Architect gate → Board
        │       └── Board gate → Human
        └── CRITICAL_FAIL (данных нет, файлы missing)
            → STOP + notify human
```

### 14.6 Context isolation для validators

```
Validator получает ТОЛЬКО:
  1. Артефакт для проверки (spec / blueprint / code)
  2. Чеклист (что проверять)
  3. Reference docs (blueprint, cross-cutting — для compliance checks)

Validator НЕ получает:
  ✗ Research files
  ✗ Cross-critique history
  ✗ Founder feedback
  ✗ Process history
  ✗ Previous validator results
  ✗ Debug/retry history

Почему:
  Validator с историей процесса = confirmation bias.
  "Я видел что это прошло через 3 раунда critique, наверно ок" — WRONG.
  Validator должен оценивать артефакт КАК ЕСЛИ БЫ видел его впервые.
```

### 14.7 Реализация

```
Deterministic gates:
  Реализация: .claude/scripts/validate-{level}-{gate}.mjs
  Runner: node .claude/scripts/validate-{level}-{gate}.mjs <input_file>
  Exit: 0 = pass, 1 = fail (reasons на stdout)
  Можно зашить в hooks (PreToolUse / PostToolUse)

AI-based gates:
  Реализация: Subagent с model: haiku или sonnet
  Prompt: чеклист + input артефакт + reference docs
  Output: JSON { pass: bool, reasons: string[] }
  Dispatch через Task tool (как остальные subagents)

Hybrid (рекомендуемый порядок):
  1. Deterministic gate FIRST (мгновенно, бесплатно)
  2. AI-based gate SECOND (только если deterministic passed)
  → Экономит tokens: ~80% ошибок ловятся deterministic
```

---

## 15. Синтез — план реализации (SKILL.md файлы)

### 15.1 Что нужно создать/переписать

```
НОВЫЕ скиллы (template/.claude/skills/):
  board/
  ├── SKILL.md           — главный файл скилла
  ├── research-phase.md  — промпт для 6 параллельных директоров
  ├── critique-phase.md  — промпт для Karpathy cross-critique
  ├── synthesis-phase.md — промпт для синтеза 2-3 стратегий
  └── write-phase.md     — промпт для написания Business Blueprint

  architect/
  ├── SKILL.md           — главный файл скилла
  ├── research-phase.md  — промпт для 7 параллельных персон
  ├── critique-phase.md  — промпт для Karpathy cross-critique
  ├── synthesis-phase.md — промпт для синтеза 2-3 архитектур
  ├── write-phase.md     — промпт для написания System Blueprint
  └── llm-ready-check.md — промпт для LLM-Ready gate

ОБНОВЛЁННЫЕ скиллы:
  spark/
  ├── SKILL.md           — обновить: multi-agent, blueprint constraint
  ├── feature-mode.md    — обновить: 4 скаута, devil, Tests секция
  ├── bug-mode.md        — без изменений (Bug Hunt уже multi-agent)
  └── completion.md      — без изменений

  autopilot/
  ├── SKILL.md           — минимальные: reflect step, blueprint check
  ├── task-loop.md       — добавить Step 3b (blueprint compliance)
  ├── escalation.md      — обновить routing (Spark/Architect/Board)
  ├── finishing.md       — добавить reflect step
  └── остальные          — без изменений

  bootstrap/
  └── SKILL.md           — переписать: убрать architecture, добавить 5 блоков

НОВЫЕ agent prompts (template/.claude/agents/):
  board-facilitator.md   — ведёт Board процесс
  board-director.md      — общий промпт для директоров (с переменной ROLE)
  architect-facilitator.md
  architect-persona.md   — общий промпт для 7 архитекторов (с переменной ROLE)
  spark-facilitator.md   — ведёт Spark multi-agent процесс
  spark-scout.md         — общий промпт для 4 скаутов (с переменной ROLE)
  reflect-aggregator.md  — агрегация upstream signals

НОВЫЕ scripts (template/.claude/scripts/):
  validate-board-data.mjs
  validate-architect-data.mjs
  validate-spark-spec.mjs
  validate-spark-tests.mjs
  validate-blueprint-compliance.mjs

НОВАЯ структура ai/ (создаётся Board/Architect при первом запуске):
  ai/blueprint/
  ├── business-blueprint.md    — output Board
  └── system-blueprint/
      ├── domain-map.md
      ├── data-architecture.md
      ├── api-contracts.md
      ├── cross-cutting.md
      ├── integration-map.md
      └── agent-architecture.md
  ai/reflect/
  ├── upstream-signals.md
  ├── cross-level-patterns.md
  ├── process-improvements.md
  └── digest-R{N}.md
```

### 15.2 Порядок реализации (зависимости)

```
Wave 1: Foundation (нет зависимостей)
  1. ai/reflect/ структура + reflect-aggregator agent
  2. Deterministic validator scripts (validate-*.mjs)
  3. Bootstrap v2 — переписать SKILL.md (удалить, добавить)

Wave 2: Board (зависит от Wave 1)
  4. Board SKILL.md + модули
  5. Board agent prompts (facilitator + directors)
  6. Board deterministic gate (validate-board-data.mjs)

Wave 3: Architect (зависит от Wave 2)
  7. Architect SKILL.md + модули
  8. Architect agent prompts (facilitator + personas)
  9. LLM-Ready Check gate
  10. Architect structural gate

Wave 4: Spark v2 (зависит от Wave 3)
  11. Spark SKILL.md + feature-mode.md rewrite
  12. Spark scout agents (4 roles)
  13. Tests section + blueprint reference в шаблоне
  14. Spark gates (spec + tests + blueprint compliance)

Wave 5: Autopilot v2 (зависит от Wave 4)
  15. task-loop.md — add Step 3b
  16. escalation.md — update routing
  17. finishing.md — add reflect step
  18. Blueprint compliance gate

Wave 6: Integration (зависит от Wave 1-5)
  19. CLAUDE.md — обновить Skills секцию
  20. localization.md — добавить триггеры для board/architect
  21. /reflect skill — обновить для чтения ai/reflect/
  22. E2E test: Bootstrap → Board → Architect → Spark → Autopilot
```

### 15.3 Что готово из дизайна (закрытые вопросы)

| Вопрос | Ответ | Где спроектировано |
|--------|-------|--------------------|
| Состав директоров Board | 5 + Devil + Facilitator | Секция 5 |
| Состав архитекторов | 7 + Devil + Facilitator | Секция 6 |
| Формат артефактов | Markdown (как всё остальное в DLD) | Секция 14.3 |
| Architect отвечает Spark как? | Через файлы (async) — Spark читает blueprint | Секция 7, Phase 1 |
| Cross-level порог | 1=info, 2=warning, 3=critical+auto-escalate | Секция 4.8 |
| Board для каждого проекта? | Да — это $60-100, дешевле чем без него | Секция 11 |
| Reject → retry flow | Единый: fail → retry_target с reasons → max → escalate | Секция 14.5 |
| Validator context isolation | Только артефакт + чеклист + reference docs | Секция 14.6 |
| Deterministic vs AI gates | Deterministic FIRST, AI SECOND | Секция 14.7 |

### 15.4 Открытые вопросы (требуют решения при реализации)

| # | Вопрос | Когда решать | Кто решает |
|---|--------|-------------|-----------|
| 1 | Board промпт: сколько tokens на директора? Context budget | Wave 2 | Эмпирически при первом запуске |
| 2 | Architect: 7 parallel agents × research = дорого? Может 2 раунда по 3-4? | Wave 3 | Эмпирически |
| 3 | Spark 4 scouts: хватит ли, или нужно 6 как в Bug Hunt? | Wave 4 | Эмпирически |
| 4 | Cross-critique: latency 7 agents × 6 reviews = 42 calls | Wave 2-3 | Оптимизация: batch, parallel |
| 5 | Agent Teams (Anthropic research preview) — заменит ли Task-based dispatch? | Мониторить | Когда выйдет GA |
| 6 | Backward compatibility: как работает без blueprint (legacy проекты)? | Wave 4-5 | Blueprint = optional, skip if missing |

### 15.5 Оценка объёма

| Wave | Файлов | Новых | Обновлённых | Оценка сложности |
|------|--------|-------|-------------|-----------------|
| 1 | 5 | 4 | 1 | Low |
| 2 | 6 | 6 | 0 | High (новый скилл с нуля) |
| 3 | 5 | 5 | 0 | High (новый скилл с нуля) |
| 4 | 5 | 2 | 3 | Medium (рефакторинг существующего) |
| 5 | 4 | 0 | 4 | Low (мелкие дополнения) |
| 6 | 4 | 0 | 4 | Medium (интеграция + тест) |
| **Итого** | **29** | **17** | **12** | |

### 15.6 Как реализовывать

```
Каждый Wave = один spark + autopilot цикл:
  1. /spark создаёт спеку для Wave N
  2. /autopilot реализует
  3. Manual E2E test (запустить новый скилл на тестовом проекте)
  4. Следующий Wave

Для Wave 2-3 (Board + Architect — новые скиллы):
  Рекомендация: итеративно.
  Первая версия = МИНИМАЛЬНЫЙ процесс (3 фазы вместо 8).
  Потом добавлять: cross-critique, iterate, multi-step write.
  Потому что промпты для 6-7 параллельных агентов = много iteration.

Для Wave 4-5 (Spark + Autopilot — обновления):
  Проще — существующий код + дополнения.
  Можно автопилотить.
```

---

## 16. Связанные документы

- `dld-v2-vision.md` — исходный vision (Feb 12)
- `frameworks-deep-research.md` — TRIZ, Cynefin, Pearl, OODA
- `hypotheses-persona-diversity.md` — эксперименты с персонами
- `bug-hunt-architecture.md` — архитектура Bug Hunt pipeline
- `test/round 4/ROUND-4-SUMMARY.md` — результаты Round 4 (42 agent runs)
- `architect-personas-research.md` — research по персонам Architect
- `board-directors-research.md` — research по персонам Board
- PLPilot repository — эмпирические данные (246 коммитов, 132 задачи)
