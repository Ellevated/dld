# Theory of Constraints: Thinking Processes for LLM Agents

**Research Date:** 2026-02-12
**Status:** Complete
**Agents Used:** 7 (scout x4, sequential-thinking x1, prior research x2)
**Sources:** 80+ (Reddit, GitHub, arXiv, Exa, practitioner blogs, books)

---

## Executive Summary

**Theory of Constraints (TOC)** Goldratt's Thinking Processes — формальный фреймворк логического рассуждения для решения сложных системных проблем. Исследование показало:

1. **Никто не применил TOC к LLM агентам** — ноль реализаций (Reddit, GitHub, arXiv)
2. **Множественные независимые переизобретения** кусков TOC в ML-сообществе
3. **Научное подтверждение** необходимости: LLM делают shallow causal reasoning
4. **Greenfield opportunity** для DLD — первая формальная реализация

---

## Table of Contents

1. [Обзор TOC](#1-обзор-toc)
2. [Current Reality Tree (CRT)](#2-current-reality-tree-crt)
3. [Evaporating Cloud (EC)](#3-evaporating-cloud-ec)
4. [Future Reality Tree (FRT)](#4-future-reality-tree-frt)
5. [Prerequisite Tree (PRT)](#5-prerequisite-tree-prt)
6. [Transition Tree (TT)](#6-transition-tree-tt)
7. [Five Focusing Steps](#7-five-focusing-steps)
8. [Drum-Buffer-Rope (DBR)](#8-drum-buffer-rope-dbr)
9. [Throughput Accounting](#9-throughput-accounting)
10. [TOC в Software Development](#10-toc-в-software-development)
11. [Gap Analysis: TOC vs LLM Frameworks](#11-gap-analysis-toc-vs-llm-frameworks)
12. [Implementation Patterns для LLM агентов](#12-implementation-patterns-для-llm-агентов)
13. [Применение в DLD](#13-применение-в-dld)
14. [Источники](#14-источники)

---

## 1. Обзор TOC

### Три фундаментальных вопроса

TOC Thinking Processes отвечают на три вопроса:

| Вопрос | Инструмент | Назначение |
|--------|-----------|------------|
| **Что менять?** | Current Reality Tree (CRT) | Найти корневую проблему |
| **На что менять?** | Evaporating Cloud (EC) + Future Reality Tree (FRT) | Спроектировать решение |
| **Как внедрить?** | Prerequisite Tree (PRT) + Transition Tree (TT) | Спланировать реализацию |

### Полный поток

```
CRT → EC → FRT → PRT → TT
 │      │     │      │     │
 │      │     │      │     └─ Пошаговый план действий
 │      │     │      └─ Препятствия и промежуточные цели
 │      │     └─ Валидация решения + Negative Branches
 │      └─ Разрешение конфликта через invalidation assumptions
 └─ Корневая проблема через sufficiency logic
```

### Два типа логики TOC

**Sufficiency logic (достаточность):** Используется в CRT, FRT, TT
- Формат: "ЕСЛИ [причина], ТО [следствие] (ПОТОМУ ЧТО [обоснование])"
- Стрелка означает: причина ДОСТАТОЧНА для следствия

**Necessity logic (необходимость):** Используется в EC, PRT
- Формат: "ЧТОБЫ [цель], НЕОБХОДИМО [условие]"
- Стрелка означает: условие НЕОБХОДИМО для цели

### AND vs OR логика

- **OR (несколько стрелок в одну сущность):** Каждая причина достаточна сама по себе
  - "Если A ИЛИ B, то C" — любая из причин вызывает эффект
- **AND (junctor/эллипс):** Все причины необходимы одновременно
  - "Если A И B, то C" — обе причины нужны для эффекта

---

## 2. Current Reality Tree (CRT)

### Назначение

CRT отвечает на вопрос **"Что менять?"** — находит корневую проблему через построение причинно-следственных цепочек от наблюдаемых симптомов вниз к корневым причинам.

### Ключевые понятия

| Термин | Определение |
|--------|------------|
| **UDE** (Undesirable Effect) | Наблюдаемый негативный симптом (не причина, а следствие) |
| **Entity** | Утверждение о реальности (факт или наблюдение) |
| **Causal link** | Связь "если → то" между entities |
| **Root cause** | Entity с высокой исходящей связностью и низкой входящей |
| **Core problem** | Одна корневая причина, объясняющая 70%+ всех UDE |

### Пошаговый процесс построения CRT

**Шаг 1: Определить систему**
- Очертить границы анализируемой системы
- Определить, что входит в scope, а что нет

**Шаг 2: Собрать UDE (5-10 штук)**

UDE должен быть:
- **Наблюдаемый** (не предположение) — есть данные/метрики
- **Негативный** (нежелательный эффект)
- **В настоящем времени** (происходит сейчас)
- **Конкретный** (не "плохо работает", а "API response > 2s для 15% запросов")

Источники UDE:
- Логи, метрики, мониторинг
- Жалобы пользователей, тикеты поддержки
- Ретроспективы команды
- Бизнес-метрики (churn, revenue, conversion)

**Шаг 3: Построить первые два уровня причинности**

Для каждого UDE спросить: "Почему это происходит?"
- Записать непосредственную причину
- Связать: "Если [причина], то [UDE]"

**Шаг 4: Углубить дерево**

Для каждой причины снова спросить "Почему?"
- Продолжать до тех пор, пока не дойдём до сущностей без входящих стрелок
- Это кандидаты в root causes

**Шаг 5: Связать ветки**

Искать общие причины между разными UDE:
- Если причина A объясняет и UDE-1, и UDE-3 — это leverage point
- Чем больше UDE объясняет одна причина, тем ближе она к core problem

**Шаг 6: Идентифицировать core problem**

Критерии core problem:
- Много исходящих стрелок (вызывает много следствий)
- Высокая достижимость (70%+ UDE трассируются к ней)
- Мало входящих стрелок (0-2) — это корень, а не промежуточное звено
- Actionable — можно на неё повлиять

**Шаг 7: Валидировать через CLR**

### 8 Categories of Legitimate Reservation (CLR)

CLR — формальные проверки логической корректности каждой связи в дереве:

| # | Проверка | Вопрос | Действие при провале |
|---|----------|--------|---------------------|
| 1 | **Clarity** | Сущность сформулирована ясно? Нет жаргона, двусмысленности? | Переформулировать |
| 2 | **Entity Existence** | Сущность реально существует? Есть доказательства? | Удалить или найти evidence |
| 3 | **Causality Existence** | Связь A→B реально существует? | Привести пример, когда A привело к B |
| 4 | **Cause Sufficiency** | A достаточно для B? Или нужны дополнительные условия? | Добавить AND-junctor с недостающими условиями |
| 5 | **Additional Cause** | Есть другие причины B помимо A? | Добавить альтернативные причины (OR) |
| 6 | **Cause-Effect Reversal** | Не перепутаны ли причина и следствие? Может B→A? | Проверить хронологию и логику |
| 7 | **Predicted Effect** | Если A→B верно, какие ещё следствия A мы должны видеть? | Проверить, наблюдаются ли предсказанные эффекты |
| 8 | **Tautology** | A→B не является определением? (доход низкий → бизнес убыточен) | Убрать тавтологию |

### Пример CRT: Software Team

```
UDE-1: Пользователи жалуются на медленный API
UDE-2: Частые инциденты в production
UDE-3: Команда постоянно в firefighting mode
UDE-4: Новые фичи задерживаются
UDE-5: Растёт technical debt

CRT Analysis:
┌─ UDE-1: API медленный
│    ↑
│  N+1 queries в ключевых эндпоинтах
│    ↑
├─ UDE-2: Частые инциденты
│    ↑
│  Нет мониторинга + нет тестов на perf
│    ↑
├─ UDE-3: Firefighting mode
│    ↑
│  Инциденты отвлекают от planned work
│    ↑
├─ UDE-4: Фичи задерживаются
│    ↑
│  Firefighting + tech debt замедляют разработку
│    ↑
└─ UDE-5: Tech debt растёт
     ↑
   Нет времени на рефакторинг (firefighting)
     ↑
   ═══════════════════════════════
   CORE PROBLEM: "Мы не инвестируем в
   инфраструктуру качества (тесты, мониторинг,
   perf benchmarks), потому что всё время
   тушим пожары"
   ═══════════════════════════════
```

Core problem объясняет все 5 UDE (100% coverage).

---

## 3. Evaporating Cloud (EC)

### Назначение

EC отвечает на вопрос **"На что менять?"** — разрешает конфликт, лежащий в основе core problem, через **invalidation assumptions** (не через компромисс).

### Структура A-B-C-D-D'

```
        ┌── B (Need 1) ←── D (Want/Action 1)
        │                         ↕ CONFLICT
A (Goal)│
        │                         ↕ CONFLICT
        └── C (Need 2) ←── D'(Want/Action 2)
```

| Элемент | Роль | Логика |
|---------|------|--------|
| **A** | Common Goal | Общая цель обеих сторон |
| **B** | Need 1 | Необходимое условие для A |
| **C** | Need 2 | Другое необходимое условие для A |
| **D** | Want 1 | Действие для достижения B |
| **D'** | Want 2 | Действие для достижения C (конфликтует с D) |

### Пошаговый процесс

**Шаг 1: Идентифицировать конфликт**

Из core problem CRT определить две несовместимые позиции:
- D: "Мы должны [действие 1]"
- D': "Мы должны [действие 2]" (противоречит D)

**Шаг 2: Найти потребности (Needs)**

Для каждого действия спросить "ЗАЧЕМ?"
- "Зачем нужно D?" → Потому что нужно B
- "Зачем нужно D'?" → Потому что нужно C

**Шаг 3: Найти общую цель (Common Goal)**

Спросить: "Зачем нужны и B, и C?"
- И B, и C необходимы для достижения A

**Шаг 4: Валидировать облако**

- A действительно общая цель? (обе стороны хотят)
- B→D необходимо? (D единственный способ достичь B?)
- C→D' необходимо? (D' единственный способ достичь C?)
- D и D' действительно конфликтуют?

**Шаг 5: Surfacing Assumptions (КЛЮЧЕВОЙ НАВЫК)**

Для КАЖДОЙ стрелки облака перечислить assumptions:

Формат: "Чтобы иметь [голова стрелки], мы должны [хвост стрелки], **ПОТОМУ ЧТО** ___"

Фраза после "потому что" = assumption.

Пример для стрелки B→D:
```
"Чтобы обеспечить качество (B), мы должны тестировать вручную (D),
ПОТОМУ ЧТО:
1. Автоматические тесты не покрывают edge cases
2. Только человек может оценить UX
3. Написание автотестов занимает больше времени чем ручное тестирование
4. У нас нет навыков для автоматизации
5. Тесты нужно запускать на реальных данных"
```

Генерировать **5-10 assumptions на каждую стрелку**.

**Шаг 6: Challenge Assumptions**

Для каждого assumption:
1. Это ПРАВДА? (evidence за/против)
2. Это НЕОБХОДИМО? (что если наоборот?)
3. Можно ли ИНВАЛИДИРОВАТЬ? (какое действие сделает это assumption ложным?)

**Шаг 7: Найти Injection**

Injection = действие, которое инвалидирует ключевой assumption, разрушая конфликт.

Правила хорошего injection:
- Конкретное действие (не "улучшить")
- Инвалидирует assumption (не компромисс!)
- Достижимо (feasible)
- Достигает И B, И C одновременно (win-win)

**Стратегический фокус:** Самые мощные injections приходят из challenge assumptions на стрелке D↔D' (сам конфликт).

### Пример EC: Software Team

```
A (Goal): Выпускать качественный продукт быстро

B (Need): Обеспечить качество кода
  → D (Want): Проводить thorough code review (2-3 дня)

C (Need): Быстро доставлять фичи
  → D'(Want): Мержить PR без ожидания (сразу)

CONFLICT: D (долгий review) vs D'(мержить сразу)
```

Assumptions под B→D:
1. "Только senior developer может найти баги в code review"
2. "Code review — единственный способ обеспечить качество"
3. "Чем дольше review, тем больше багов найдём"

Challenge #2: "Code review — единственный способ?"
- **НЕТ!** Есть: автотесты, статический анализ, pair programming, feature flags

**Injection:** "Внедрить automated quality gates (linting, type checking, test coverage threshold) + pair programming для сложных PR"

Результат: Качество обеспечивается автоматически (B), PR мержатся быстро (C). Конфликт исчезает.

### Антипаттерны EC

| Антипаттерн | Почему плохо | Правильно |
|---|---|---|
| Компромисс | "Давайте review 1 день" — не решает проблему | Инвалидировать assumption |
| Магическое решение | "Нанять гения" — не actionable | Конкретное действие |
| Игнор assumption | Не challenge, а просто решение | Systematically surface все assumptions |

---

## 4. Future Reality Tree (FRT)

### Назначение

FRT отвечает на **"Будет ли это работать?"** — валидирует injection из EC, строя причинно-следственные цепочки вперёд и проверяя на негативные последствия.

### Пошаговый процесс

**Шаг 1: Начать с injection**

Поместить injection в основание дерева.

**Шаг 2: Построить позитивные ветки**

Используя sufficiency logic:
```
ЕСЛИ [injection], ТО [intermediate effect 1]
ЕСЛИ [intermediate effect 1], ТО [intermediate effect 2]
...
ЕСЛИ [intermediate effect N], ТО [Desired Effect]
```

**Шаг 3: Конвертировать UDE в DE**

Каждый UDE из CRT должен стать Desired Effect (DE) в FRT:
- UDE: "API медленный" → DE: "API отвечает < 200ms"
- UDE: "Частые инциденты" → DE: "Стабильная production среда"

**Шаг 4: Искать Negative Branch Reservations (NBR)**

**NBR — критический элемент.** Это adversarial thinking: "Что может пойти не так?"

Систематические вопросы для каждого injection:

1. **Resource constraints:** Нужны ли ресурсы, которых нет?
2. **System dynamics:** Не сдвинет ли проблему в другое место?
3. **Second-order effects:** Что произойдёт если это сработает? Не создаст ли успех новые проблемы?
4. **Resistance:** Кто может сопротивляться? Почему?
5. **Failure modes:** Что если injection не сработает как ожидается?
6. **Scale effects:** Что произойдёт при масштабировании?

**Шаг 5: Trimming (сафегарды для NBR)**

Для каждого NBR — добавить supporting injection (safeguard):

```
NBR: "Automated quality gates пропускают бизнес-логику баги"
Trimming: "Добавить property-based тесты для критических бизнес-правил"
```

Правила хорошего trimming:
- Не блокирует основной injection
- Пропорционален риску (cost ≤ risk)
- Может быть внедрён параллельно

**Шаг 6: Инженерить Positive Reinforcing Loops**

Искать самоусиливающиеся циклы:
```
Быстрые PR → Быстрый feedback → Меньше багов в production
→ Меньше firefighting → Больше времени на quality
→ Ещё быстрее PR
```

**Шаг 7: Финальная валидация**

Checklist:
- [ ] Все UDE из CRT конвертированы в DE
- [ ] Все DE логически связаны с injection
- [ ] Хотя бы 1 positive reinforcing loop
- [ ] Все NBR имеют trimmings
- [ ] Логика читается снизу вверх

Итоговая рекомендация: **GO / ITERATE / REJECT**
- GO: решение работает, NBR закрыты
- ITERATE: нужны корректировки (→ назад к EC)
- REJECT: фатальные NBR (→ назад к EC за новым injection)

---

## 5. Prerequisite Tree (PRT)

### Назначение

PRT отвечает на **"Как внедрить?"** (высокий уровень) — находит все препятствия на пути к реализации и определяет промежуточные цели для их преодоления.

### Ключевые понятия

| Термин | Определение |
|--------|------------|
| **Objective** | Конечная цель (injection из FRT) |
| **Obstacle** | Барьер, мешающий достижению цели |
| **IO (Intermediate Objective)** | Промежуточная цель, преодолевающая obstacle |

### 8 категорий препятствий

| Категория | Вопрос | Пример |
|-----------|--------|--------|
| Knowledge/Skills | "Мы не знаем как" | "Команда не умеет писать property-based тесты" |
| Resources | "У нас нет X" | "Нет бюджета на CI/CD инфраструктуру" |
| Authority | "Нам не разрешено" | "CTO не одобрил новый подход" |
| Buy-in | "Люди сопротивляются" | "Seniors привыкли к manual review" |
| Dependencies | "Нужно X от внешней стороны" | "Нужна интеграция с CI провайдером" |
| Capacity | "Нет времени" | "Все заняты текущими фичами" |
| Policy | "Правила не позволяют" | "SOX compliance требует manual approval" |
| Environment | "Внешние факторы" | "Vendor не поддерживает нужные API" |

### Пошаговый процесс

**Шаг 1: Определить objective** (injection из FRT)

**Шаг 2: Brainstorm ALL obstacles**
- "Что мешает нам реализовать это ПРЯМО СЕЙЧАС?"
- Пройти по всем 8 категориям
- Crawford Slip Method: каждый записывает obstacles анонимно

**Шаг 3: Конвертировать obstacles в IOs**
- Obstacle: "Команда не умеет X" → IO: "Команда обучена и уверенно применяет X"

**Шаг 4: Секвенирование IOs (necessity logic)**
- "Можно ли достичь IO-B без IO-A?" → Нет → A перед B
- Определить параллельные пути (независимые IO)

**Шаг 5: Critical path**
- Самый длинный путь зависимостей = critical path
- Параллельные IO можно выполнять одновременно

### Пример PRT

```
Objective: "Automated quality gates + pair programming"

Obstacles & IOs:
OBS-1: "CTO не знает о подходе" → IO-1: "CTO одобрил подход"
OBS-2: "Нет CI pipeline"       → IO-2: "CI pipeline настроен"
OBS-3: "Нет linting rules"     → IO-3: "Linting rules определены"
OBS-4: "Команда не умеет pair"  → IO-4: "Команда практикует pair programming"
OBS-5: "Нет test coverage tool" → IO-5: "Coverage tool интегрирован в CI"

Sequence:
IO-1 (approval) → IO-2 (CI) → IO-3 + IO-5 (parallel) → IO-4
                                                          ↓
                                                    OBJECTIVE
```

---

## 6. Transition Tree (TT)

### Назначение

TT отвечает на **"Как внедрить?"** (детальный уровень) — пошаговый план действий с if-then логикой и contingencies.

### 4-элементная структура (repeating cycle)

```
Current Reality → Need → Action → Expected Effect
                                       ↓
                              (becomes new Current Reality)
```

Каждый цикл:
1. **Current Reality:** Текущее состояние
2. **Need:** Что необходимо изменить
3. **Action:** Конкретное действие
4. **Expected Effect:** Ожидаемый результат (проверяется на sufficiency)

### Contingency Planning

Для каждого Expected Effect:
```
IF expected effect occurs → next step
IF NOT:
  CONTINGENCY-A: [alternative action for scenario A]
  CONTINGENCY-B: [alternative action for scenario B]
  ESCALATE: [if all contingencies fail → back to PRT]
```

### Пример TT для IO-2 "CI Pipeline настроен"

```
CYCLE 1:
Reality: Нет CI pipeline
Need: Выбрать CI provider
Action: Сравнить GitHub Actions vs GitLab CI vs CircleCI
Expected: CI provider выбран
  IF OK → cycle 2
  IF NOT (не можем выбрать): schedule decision meeting с tech lead

CYCLE 2:
Reality: CI provider выбран (GitHub Actions)
Need: Настроить базовый pipeline
Action: Создать .github/workflows/ci.yml с lint + test + build
Expected: PR trigger запускает pipeline
  IF OK → cycle 3
  IF NOT (fails): debug, check docs, ask community

CYCLE 3:
Reality: Базовый pipeline работает
Need: Добавить quality gates
Action: Добавить linting threshold + test coverage minimum
Expected: PR блокируется при нарушении quality gates
  IF OK → IO-2 COMPLETE ✓
  IF NOT: adjust thresholds, fix flaky tests
```

### Когда создавать TT (а когда нет)

**Создавать:**
- IO включает несколько людей/команд
- Есть существенный риск failure
- Нужна точная последовательность
- Требуется shared understanding

**Не создавать:**
- IO очевидный и тривиальный
- Один человек выполняет
- Нет значимого риска

---

## 7. Five Focusing Steps

### Циклический процесс непрерывного улучшения

### Step 1: IDENTIFY the Constraint

**Physical constraints:**
- Capacity: оборудование/сервис не справляется с нагрузкой
- Market: недостаточно спроса
- Material: нехватка ресурсов

**Policy constraints (невидимые, но самые опасные):**
- Правила batch size ("минимум 1000 единиц для эффективности")
- Метрики, ведущие к wrong behavior (utilization targets)
- Approval processes, замедляющие работу
- "Так исторически сложилось"

**Методы идентификации:**
1. Визуальный: где самая большая очередь/backlog?
2. Capacity analysis: load vs capacity для каждого ресурса
3. Firefighter tracking: куда бегут "тушители пожаров"?
4. Cycle time: у какого процесса самое большое время обработки?

**Частая ошибка:** "Bottleneck двигается каждый день" — значит, не множественные constraints, а плохое управление workflow скрывает реальный constraint.

### Step 2: EXPLOIT the Constraint

**Цель:** Максимум output от constraint БЕЗ инвестиций.

- Убрать простои (stagger breaks — constraint никогда не стоит)
- Проверять качество ДО constraint (не тратить его время на брак)
- Предварительно готовить материалы (constraint не ждёт)
- Уменьшить переключения (batch similar work)
- Перенести операции с constraint на другие ресурсы

**Software пример:** Senior architect = constraint:
- Убрать из meetings
- Junior devs готовят контекст перед review
- Автоматизировать рутину, которую делает architect
- Batch similar architecture decisions

### Step 3: SUBORDINATE Everything Else

**Самый контринтуитивный шаг:** Все non-constraints работают В РИТМЕ constraint, даже если простаивают.

- Non-constraints НЕ должны быть 100% loaded
- Protective capacity: 25-30% slack на non-constraints
- Это предотвращает WIP buildup и ускоряет flow

**Пример:**
- Dev team может делать 15 features/sprint
- Testing constraint обрабатывает 10/sprint
- **WRONG:** Dev делает 15 → testing backlog растёт
- **RIGHT:** Dev ограничивает WIP до 10 → features flow быстрее end-to-end

**Почему это трудно:** Традиционные метрики эффективности наказывают subordination ("простаивающие ресурсы!"). Это **policy constraint** — самое частое.

### Step 4: ELEVATE the Constraint

**Только ПОСЛЕ exploit и subordinate!**

- Купить дополнительное оборудование
- Нанять людей
- Добавить смены
- Аутсорс constraint work
- Инвестиции в технологии

**Почему ждать:** Elevation стоит денег. Exploit часто даёт достаточно capacity бесплатно. Пример: вместо покупки второй машины за $500K — просто запустить первую в обеденный перерыв.

### Step 5: Don't Let INERTIA Become the Constraint

Когда constraint снят (elevated), **новый constraint появляется в другом месте**. Но организация продолжает оптимизировать старый constraint по инерции.

**Решение:** Вернуться к Step 1. Повторить цикл с новым constraint.

---

## 8. Drum-Buffer-Rope (DBR)

### Три компонента

**DRUM = Расписание constraint**
- Constraint задаёт "ритм" (drumbeat) для всей системы
- Только constraint получает детальное расписание

**BUFFER = Временная защита (НЕ количество!)**
- Измеряется во ВРЕМЕНИ (часы/дни), не в штуках
- Защищает constraint от disruptions
- Размещается: перед constraint, перед shipping, в точках сборки

**ROPE = Механизм запуска работы**
- Сигнал, запускающий работу за "длину верёвки" до момента, когда она нужна на constraint
- Предотвращает перегрузку системы WIP

### Buffer Sizing

**Начальное правило:** Текущий lead time ÷ 2 = размер buffer.
(Большая часть lead time — это ожидание в очереди, не обработка)

**Buffer Zones (правило третей):**

| Зона | Диапазон | Действие |
|------|----------|----------|
| **Green** | 0-33% потреблено | Всё в норме, не вмешиваться |
| **Yellow** | 34-66% потреблено | Мониторить, быть готовым |
| **Red** | 67-100% потреблено | Немедленно expedite |

**Здоровый buffer:** Red zone срабатывает только в 5% случаев.

### Simplified DBR (S-DBR)

Для make-to-order сред:
- Нет drum schedule на internal constraint
- Единый shipping buffer (защита due dates)
- Простая rope: запуск работы за buffer-length до due date

---

## 9. Throughput Accounting

### Три метрики

| Метрика | Формула | Значение |
|---------|---------|----------|
| **T** (Throughput) | Sales - Truly Variable Costs | Скорость генерации денег через продажи |
| **I** (Investment) | Assets tied up | Деньги, связанные в системе |
| **OE** (Operating Expense) | All costs except TVC | Деньги на конвертацию I в T |

### T/CU — ключевая формула

**T/CU** = Throughput ÷ Constraint Unit (время на constraint)

| Продукт | Price | TVC | T | Constraint Min | T/CU |
|---------|-------|-----|---|---------------|------|
| A | $100 | $40 | $60 | 10 | **$6/min** |
| B | $80 | $30 | $50 | 15 | $3.33/min |
| C | $90 | $25 | $65 | 20 | $3.25/min |

**Решение:** Делать A первым (highest T/CU), хотя C имеет highest absolute T.
Каждая минута constraint бесценна — максимизировать RATE, не absolute.

### Ловушка локальной оптимизации

Оптимизация non-constraint (большие batch для "эффективности") → рост WIP → длинные lead times → **вредит** глобальному throughput.

**Правило:** Никогда не оптимизировать non-constraint за счёт системного throughput.

---

## 10. TOC в Software Development

### Kanban вырос из TOC

David Anderson's Kanban method напрямую из TOC:
- **WIP limits** = Subordination to constraint
- **Pull system** = Rope mechanism
- **Flow efficiency** = Throughput focus
- **Expedite lane** = Buffer management (red zone)

### Critical Chain Project Management (CCPM)

Отличие от Critical Path:
- Critical Path: только зависимости задач
- **Critical Chain: задачи + ресурсные зависимости**

Ключевые концепции:
1. **Remove local safety, add project buffer:** Урезать оценки вдвое, добавить 50% buffer в конец проекта
2. **Feeding buffers:** Защита critical chain от задержек на non-critical paths
3. **Buffer management:** Green/Yellow/Red для статуса проекта

### Policy Constraints в Software Teams

| Policy Constraint | Реальность | Лучше |
|---|---|---|
| "Все stories должны быть estimated" | Estimation theatre, низкая accuracy | Focus на WIP limits и flow |
| "Deploy каждые 2 недели" | Фичи ждут до 13 дней | Continuous deployment |
| "Dev → QA handoff" | Testing constraint, очереди | Cross-functional teams |
| "100% utilization" | Multitasking, context-switching | 70-80% utilization + protective capacity |

### Phoenix Project Connection

Gene Kim's "The Phoenix Project" = TOC для DevOps:
- **The Three Ways:**
  1. Flow (subordination — optimize whole system)
  2. Feedback (fast loops = smaller buffers)
  3. Continuous Learning (Step 5 — overcome inertia)

---

## 11. Gap Analysis: TOC vs LLM Frameworks

### Что переизобрели без Голдратта

| Framework | Год | Что это по сути в TOC | Чего не хватает |
|---|---|---|---|
| [Tree of Thoughts](https://neurips.cc/virtual/2023/oral/73874) | 2023 | FRT (branching exploration) | Нет "что менять", нет sufficiency |
| [Graph of Thoughts](https://ojs.aaai.org/index.php/AAAI/article/view/29720) | 2024 | CRT (причинный DAG) | Все связи равнозначны, нет CLR |
| [Causal Sufficiency CoT](https://arxiv.org/abs/2506.09853) | 2025 | **Sufficiency logic TOC** | Валидирует цепочки, не строит деревья |
| [Constraints-of-Thought](https://arxiv.org/html/2510.08992v1) | 2025 | FRT + constraint checking | Satisfies constraints, не ищет root |
| [TRIZ-GPT](https://arxiv.org/abs/2408.05897) | 2024 | EC (технические противоречия) | Только технические, не системные |
| [Socratic Prompting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5053915) | 2025 | Challenge assumptions (как EC) | Нет A-B-C-D-D' структуры |
| [Architecture of Thought](https://github.com/domelic/architecture-of-thought) | 2025 | Socratic method (как у Голдратта) | 24 режима, нет формальной логики |
| [Cohen's Conjecture](https://gist.github.com/ruvnet/a872ec910082974116584f623a33b068) | 2025 | Dual-process + sufficiency | TOC без имени Голдратта |
| [Generate-Verify-Revise](https://arxiv.org/abs/2601.07180) | 2025 | NBR (verify before commit) | Нет систематического поиска NBR |

### Уникальность TOC (чего нет ни у кого)

| Свойство | TOC | Ближайший аналог | Gap |
|----------|-----|-------------------|-----|
| Sufficiency logic | Формальная: "если A, то всегда B" | Causal Sufficiency CoT | CoT валидирует, TOC строит |
| Core problem identification | CRT → 1 root cause → 70%+ UDE | 5 Whys | 5 Whys линейный, CRT — дерево |
| Conflict resolution без компромисса | EC → invalidate assumptions | TRIZ | TRIZ технический, EC системный |
| Proactive solution validation | FRT + NBR | - | Никто не делает |
| Complete methodology | What→What to→How | - | Все фреймворки покрывают 1 из 3 |
| 40 лет battle-tested | Manufacturing, services, software | - | Все LLM frameworks < 3 лет |

### Почему LLM нужен TOC

Статья ["Unveiling Causal Reasoning in LLMs"](https://arxiv.org/html/2506.21215v1) (2025):
> LLM делают **shallow causal reasoning** на основе запомненных паттернов.
> На свежих сценариях accuracy резко падает.

TOC даёт LLM то, чего не хватает: **формальную структуру для логического выведения решений**, а не pattern matching.

### Почему gap существует

1. **Силосы:** r/TheoryOfConstraints = 379 человек; r/MachineLearning = 3M+
2. **TOC = "менеджерская штука":** ML-сообщество не читает бизнес-романы
3. **Нет формализации для кода:** TOC описан диаграммами, не как API

---

## 12. Implementation Patterns для LLM агентов

### CRT Agent

```yaml
name: toc-crt
model: opus
effort: max
purpose: Root cause analysis через sufficiency logic

input:
  - Симптомы (UDE) от пользователя или системы
  - Данные: логи, метрики, тикеты

process:
  1. Collect UDEs (observable, negative, present, specific)
  2. Build cause-effect chains (if A then B because C)
  3. Self-validate with 8 CLR checks
  4. Identify core problem (70%+ UDE coverage)

output:
  core_problem: string
  ude_coverage: float  # 0.0-1.0
  confidence: high|medium|low
  tree: CRTTree  # structured JSON
  validation_report: CLRReport

anti-hallucination:
  - Every causal link needs evidence field (NOT optional)
  - Counter-check: "Can B exist without A?"
  - If no evidence: mark as "hypothesis - needs validation"
  - Confidence decreases with chain length
```

**Prompt template для sufficiency check:**
```
Для каждой связи A→B:
1. "Если A, то B" — это ВСЕГДА верно?
2. Механизм: КАК именно A вызывает B?
3. Доказательства: какие данные подтверждают?
4. Counter-check: может ли B существовать без A?
   Если да → связь НЕВЕРНА или НЕПОЛНА
```

### EC Agent

```yaml
name: toc-ec
model: opus
effort: max
purpose: Conflict resolution через invalidation assumptions

input:
  - Core problem из CRT
  - Контекст конфликта

process:
  1. Map conflict: A-B-C-D-D'
  2. Surface 5-10 assumptions per arrow
  3. Challenge each assumption (true? necessary? invalidatable?)
  4. Find injection that invalidates weakest assumption
  5. Verify injection achieves both B and C (win-win)

output:
  cloud: ECStructure
  assumptions: list[Assumption]
  injections: list[Injection]  # ranked by feasibility
  recommended: Injection

forbidden:
  - Compromises ("давайте частично")
  - Magic solutions ("наймём гения")
  - Solutions that don't invalidate any assumption
```

### FRT Agent

```yaml
name: toc-frt
model: opus
effort: high
purpose: Solution validation + adversarial NBR search

input:
  - Injection из EC
  - UDEs из CRT (для проверки coverage)

process:
  1. Build positive branches (injection → intermediate effects → DEs)
  2. Verify all UDEs converted to DEs
  3. ADVERSARIAL: systematically search for NBRs
  4. Propose trimmings for each NBR
  5. Engineer positive reinforcing loops
  6. Final verdict: GO / ITERATE / REJECT

output:
  recommendation: GO|ITERATE|REJECT
  de_coverage: float
  nbrs: list[NBR]
  trimmings: list[Trimming]
  reinforcing_loops: list[Loop]
```

### PRT Agent

```yaml
name: toc-prt
model: sonnet
effort: high
purpose: Obstacle identification + task decomposition

input:
  - Validated injection из FRT

process:
  1. List obstacles (8 categories)
  2. Convert to Intermediate Objectives
  3. Sequence with necessity logic
  4. Identify critical path + parallel opportunities

output:
  obstacles: list[Obstacle]
  ios: list[IntermediateObjective]
  phases: list[Phase]  # groups of parallel IOs
  critical_path: list[IO]
  total_duration_estimate: string
```

### TT Agent

```yaml
name: toc-tt
model: sonnet
effort: medium
purpose: Step-by-step execution plan with contingencies

input:
  - IOs из PRT

process:
  1. For each IO: build Need → Action → Expected Effect cycles
  2. Validate sufficiency at each step
  3. Plan contingencies for high-risk steps
  4. Map to coder/tester tasks

output:
  execution_plan: list[TTCycle]
  contingencies: list[Contingency]
  coder_tasks: list[Task]
  tester_tasks: list[Task]
```

### Full Pipeline Flow

```
User: "У нас проблема X"
         │
    ┌────▼─────┐
    │ CRT Agent │  opus/max    $1-2    2-5 min
    │           │  "Что менять?"
    └────┬─────┘
         │ core_problem + confidence
         │
    ┌────▼─────┐
    │ EC Agent  │  opus/max    $1.50-3  3-8 min
    │           │  "На что менять?"
    └────┬─────┘
         │ injection + assumptions
         │
    ┌────▼─────┐
    │ FRT Agent │  opus/high   $1-2    2-4 min
    │           │  Валидация + NBR
    └────┬─────┘
         │ GO / ITERATE / REJECT
         │
    ┌────▼─────┐  (if GO)
    │ PRT Agent │  sonnet      $0.30   1-2 min
    │           │  Obstacles → IOs
    └────┬─────┘
         │ task tree + critical path
         │
    ┌────▼─────┐
    │ TT Agent  │  sonnet      $0.30   1-2 min
    │           │  Execution plan
    └────┬─────┘
         │ coder_tasks + tester_tasks
         │
    ┌────▼─────┐
    │ DLD std   │  coder → tester → review
    └──────────┘

Total: $4-8, 10-20 min
```

### Iteration Points

- **FRT → EC:** NBR найден критический → новый injection
- **PRT → FRT:** Obstacle непреодолим → modify injection
- **TT → PRT:** Contingency exhausted → revise IO

### Human Checkpoints

| После | Зачем | Когда escalate to Council |
|-------|-------|--------------------------|
| CRT | Validate core problem | confidence < 70% |
| EC | Review assumptions + injection | feasibility = uncertain |
| FRT | Review NBRs + GO/REJECT | unmitigated high-severity NBR |
| PRT | Review execution plan | critical path > 6 months |

### When to Use Full vs Individual

| Ситуация | Что использовать |
|----------|-----------------|
| Сложная проблема, неясная причина | Full pipeline |
| Стратегическое решение (architecture) | Full pipeline |
| "В чём root cause?" | CRT only |
| "Как разрешить конфликт X vs Y?" | EC only |
| "Сработает ли это решение?" | FRT only |
| "Как это внедрить?" | PRT + TT |
| Quick hunch validation | EC (assumptions only) |

---

## 13. Применение в DLD

### Mapping на существующие агенты

| TOC Tool | DLD Agent | Когда вызывать |
|----------|-----------|---------------|
| CRT | Новый: `toc-crt` | `/scout` с debugging задачей |
| EC | Новый: `toc-ec` | `/council` при конфликте требований |
| FRT | Новый: `toc-frt` | `/planner` после решения, до реализации |
| PRT | Расширение `planner` | `/planner` → obstacle-driven planning |
| TT | Расширение `coder` | `/autopilot` → if-then execution |

### Интеграция с Council

Council может использовать EC для разрешения конфликтов между экспертами:
```
Product Manager: "Нужна фича X" (D)
Architect: "Нужен рефакторинг Y" (D')

EC Agent:
A: Sustainable product growth
B: User value → D: Build feature X
C: Technical health → D': Refactor Y

Assumptions под D↔D':
1. "X и Y нельзя делать одновременно"
2. "Рефакторинг блокирует feature work"

Injection: "Refactor Y КАК ЧАСТЬ feature X
(feature flag + incremental refactor)"
```

### Применение 5 Focusing Steps к Agent Pipeline

```
Step 1: IDENTIFY constraint в autopilot pipeline
  → Замерить latency каждого агента
  → Найти bottleneck (planner? coder? tester? review?)

Step 2: EXPLOIT constraint
  → Если planner = bottleneck: оптимизировать prompt, кэшировать паттерны
  → Если coder = bottleneck: лучший контекст, предзагрузка файлов

Step 3: SUBORDINATE
  → Не оптимизировать non-constraint агентов
  → Не запускать задачи быстрее чем constraint обрабатывает

Step 4: ELEVATE
  → Параллельные planner agents
  → Переход на 1M context (Opus 4.6 beta)
  → Лучшая модель для constraint agent

Step 5: Repeat
  → diary-recorder мониторит новые bottlenecks
```

### DBR для Agent Orchestration

```
DRUM: constraint agent задаёт темп
BUFFER: queue задач перед constraint (не больше 2-3)
ROPE: autopilot запускает новую задачу только когда
      constraint обработал предыдущую

Buffer zones:
- Green: constraint idle < 10% → всё ОК
- Yellow: queue > 3 tasks → monitor
- Red: queue > 5 tasks → stop feeding, wait
```

---

## 14. Источники

### TOC Fundamentals
- [TOC Institute: Thinking Processes](https://www.tocinstitute.org/toc-thinking-processes.html)
- [TOC Institute: Five Focusing Steps](https://www.tocinstitute.org/five-focusing-steps.html)
- [Fortelabs: Five Focusing Steps](https://fortelabs.com/blog/theory-of-constraints-107-identifying-the-constraint/)
- [6sigma.us: Current Reality Tree](https://www.6sigma.us/six-sigma-in-focus/current-reality-tree/)
- [Wikipedia: Evaporating Cloud](https://en.wikipedia.org/wiki/Evaporating_cloud)
- [Vithanco: CRT Notation](https://vithanco.com/notations/TOC/current-reality-tree/)
- [Vithanco: EC Notation](https://vithanco.com/notations/TOC/evaporating-cloud/)
- [Flying Logic: CRT Documentation](https://docs.flyinglogic.com/thinking-with-flying-logic/current-reality-tree)
- [Flying Logic: FRT Documentation](https://docs.flyinglogic.com/thinking-with-flying-logic/future-reality-tree)
- [Eponine Pauchard: EC in Practice](https://www.eponine-pauchard.com/en/2021/12/evaporating-cloud-conflict-management-in-practice/)
- [Chris Hohmann: CRT](https://hohmannchris.wordpress.com/2014/11/06/thinking-processes-current-reality-tree/)
- [Chris Hohmann: EC](https://hohmannchris.wordpress.com/2014/11/17/conflict-resolution-diagram-evaporating-cloud/)
- [a-dato: Deep Dive into TOC TP](https://www.a-dato.com/learning/a-deep-dive-into-toc-thinking-processes/)

### Books (Essential Reading)
- Goldratt, E. "The Goal" (1984) — Foundation
- Goldratt, E. "It's Not Luck" (1994) — All 5 Thinking Processes
- Dettmer, H.W. "The Logical Thinking Process" (2007) — Most detailed methodology
- Scheinkopf, L. "Thinking for a Change" (1999) — Practical guide
- Kim, G. "The Phoenix Project" (2013) — TOC for DevOps

### Academic: LLM Reasoning Frameworks
- [Tree of Thoughts (NeurIPS 2023)](https://neurips.cc/virtual/2023/oral/73874)
- [Graph of Thoughts (AAAI 2024)](https://ojs.aaai.org/index.php/AAAI/article/view/29720)
- [Skeleton-of-Thought (NeurIPS 2023)](https://openreview.net/pdf?id=mqVgBbNCm9)
- [Causal Sufficiency CoT (arXiv 2025)](https://arxiv.org/abs/2506.09853)
- [Constraints-of-Thought (arXiv 2025)](https://arxiv.org/html/2510.08992v1)
- [C2P: Pearl's Ladder (arXiv 2024)](https://arxiv.org/html/2407.18069v4)
- [Unveiling Causal Reasoning in LLMs (arXiv 2025)](https://arxiv.org/html/2506.21215v1)
- [Generate-Verify-Revise (arXiv 2025)](https://arxiv.org/abs/2601.07180)
- [Verifiable Process Rewards (arXiv 2025)](https://www.arxiv.org/abs/2601.17223)
- [TRIZ-GPT (arXiv 2024)](https://arxiv.org/abs/2408.05897)
- [AutoTRIZ (arXiv 2024)](https://arxiv.org/abs/2403.13002)
- [Socratic Iterative Prompting (SSRN 2025)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5053915)
- [Agentic AI Needs Systems Theory (arXiv 2026)](https://arxiv.org/html/2503.00237v1)
- [Agent Contracts (arXiv 2026)](https://arxiv.org/abs/2601.08815)
- [Murakkab: Resource-Efficient Orchestration (arXiv 2025)](https://arxiv.org/abs/2508.18298)
- [LLM Causal Loop Diagrams (MDPI 2025)](https://www.mdpi.com/2079-8954/13/9/784)

### TOC + AI (Emerging)
- [Transforming TOC to Agent-Based AI](https://procureinsights.com/2025/01/23/transforming-the-theory-of-constraints-to-the-agent-based-development-and-implementation-model-for-todays-ai/)
- [Dr. Alan Barnard: Goldratt's Challenge with AI](https://www.linkedin.com/posts/dralanbarnard_goldratt-ai-hownotwhat-activity-7400920602347278336-_iO3)
- [From Line Cook to Head Chef: Orchestrating AI Teams](https://itrevolution.com/articles/from-line-cookto-head-chef-orchestrating-ai-teams/)
- [Gene Kim: Agentic DevOps (Microsoft Build)](https://www.youtube.com/watch?v=xuvejc3Y5tA)

### GitHub: Related Projects
- [Architecture of Thought (DCF)](https://github.com/domelic/architecture-of-thought)
- [Cohen's Agentic Conjecture](https://gist.github.com/ruvnet/a872ec910082974116584f623a33b068)
- [LLM Knowledge Conflict](https://github.com/OSU-NLP-Group/LLM-Knowledge-Conflict)
- [PyRCA (Salesforce)](https://github.com/salesforce/PyRCA)
- [Diagram-of-Thought](https://github.com/diagram-of-thought/diagram-of-thought)

### Community
- [r/TheoryOfConstraints](https://www.reddit.com/r/TheoryOfConstraints/) (379 members)
- [When Your AI Agent Is the Bottleneck](https://medium.com/@mbonsign/when-your-ai-agent-is-the-bottleneck-e2ce29f2c8eb)
- [The Real Bottleneck in Enterprise AI: Context](https://thenewstack.io/the-real-bottleneck-in-enterprise-ai-isnt-the-model-its-context/)

---

*Research conducted by 7 parallel scout agents using Exa MCP, WebSearch, Sequential Thinking.*
*Total research cost: ~$15 | Total tokens: ~400K | Duration: ~25 min*
