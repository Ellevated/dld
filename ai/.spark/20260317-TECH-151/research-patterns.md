# Pattern Research — TECH-151: Align Orchestrator with North-Star Flow

---

## Question 1: Spark Status on Exit

---

## Approach 1A: Always `queued` (unconditionally)

**Source:** [AEEF Orchestration State Machine](https://aeef.ai/transformation/agent-sdlc-orchestration/orchestration-rules) — strict state machine, each item is in exactly one state at any time.

### Description
Spark всегда выставляет статус `queued` при создании спека. Нет понятия "черновика, ожидающего человека". Оркестратор немедленно подхватывает spec из backlog и ставит его в очередь на autopilot. Это соответствует north-star flow: `inbox → spark → backlog(queued) → autopilot`.

### Pros
- Простота: один путь, один код, нет ветвления по режиму запуска
- Строгое следование north-star: spec существует только в двух состояниях — queued или in_progress
- `scan_drafts()` и `Step 5.5` кода в pueue-callback.sh становятся полностью мёртвым кодом — можно удалить
- Устраняет класс багов: "draft завис, никто не нажал approve"
- Соответствует тому, что OpenClaw уже провёл conversational gate до попадания в inbox

### Cons
- Нет паузы между Spark и Autopilot — если Spark сгенерировал плохой spec, он немедленно уйдёт в работу
- Оператор не видит spec перед запуском (нет информационного уведомления в Telegram)
- Если понадобится вернуть approval gate позже — потребует изменений и в Spark, и в orchestrator

### Complexity
**Estimate:** Easy — 1-2 часа
**Why:** Изменение строки `status: draft` на `status: queued` в шаблоне Spark. Удаление `scan_drafts()` из orchestrator.sh. Удаление Step 5.5 из pueue-callback.sh. Изменение grep-паттерна в scan_backlog() — уже ищет `queued`, ничего не менять.

### Example Source
Текущий `scan_backlog()` в orchestrator.sh уже ищет `queued`:
```bash
spec_id=$(grep -E '\|\s*queued\s*\|' "$backlog" | head -1 | grep -oE '...')
```
Достаточно изменить Spark-шаблон спека: `**Status:** queued`.

---

## Approach 1B: `queued` только в headless, `draft` в интерактивном

**Source:** [Draft-First Automation](https://operaitions.ai/blog/automation-you-can-trust/) — draft-first pattern, где автоматика создаёт черновик, человек одобряет.

### Description
Spark определяет режим запуска (headless pueue vs интерактивный Claude Code сеанс) и выставляет соответствующий статус. В headless: `queued` (OpenClaw уже дал approval в conversational loop). В интерактивном: `draft` (человек сам запустил `/spark`, хочет проверить перед запуском).

### Pros
- Сохраняет возможность review для интерактивного использования
- Операторская видимость: при `/spark` вручную человек видит spec, решает сам
- Backward-compatible: старые воркфлоу, где `/spark` + ручное одобрение, продолжают работать

### Cons
- Сложнее: Spark должен определять контекст вызова (headless vs interactive)
- Два пути — два места где что-то может пойти не так
- `scan_drafts()` остаётся нужным для интерактивного пути — мёртвый код не удалить
- Неочевидное поведение: один и тот же `/spark` работает по-разному в зависимости от контекста запуска
- Step 5.5 в callback тоже нельзя удалить полностью

### Complexity
**Estimate:** Medium — 3-5 часов
**Why:** Нужно добавить детектирование режима в Spark skill. Pueue добавляет env-переменные (PUEUE_GROUP, PUEUE_TASK_ID) в subprocess — можно использовать как сигнал. Но поддержка двух путей добавляет когнитивную нагрузку.

### Example Source
В headless вызове через pueue переменные окружения `PUEUE_TASK_ID` и `PUEUE_GROUP` присутствуют. Spark может проверять: `os.getenv("PUEUE_TASK_ID")` — если есть, статус `queued`; если нет — `draft`.

---

## Approach 1C: `queued` всегда, но с informational Telegram notification (без кнопок)

**Source:** [CircleCI Approval Jobs](https://oneuptime.com/blog/post/2026-02-02-circleci-approval-jobs/) — паттерн audit trail без блокирующего gate.

### Description
Spark всегда создаёт `queued` spec. Callback при завершении Spark отправляет информационное уведомление в Telegram (без кнопок approve/reject) — просто "Spark создал spec X, запускается autopilot". Operator visibility сохраняется, approval gate убирается.

### Pros
- Оператор видит что происходит (видимость)
- Нет blocking gate — цикл не зависает в ожидании нажатия кнопки
- Чище чем 1B: один путь, один статус
- Уведомление служит как audit trail

### Cons
- Step 5.5 не удаляется полностью — трансформируется в info-notification (меньший код, но остаётся)
- Всё равно нет возможности остановить плохой spec до запуска
- Notification fatigue: ещё одно сообщение в Telegram для каждого spec

### Complexity
**Estimate:** Easy — 1-2 часа
**Why:** Изменение Spark-шаблона на `queued`. Step 5.5 упрощается: убрать кнопки, оставить только `notify.py $PROJECT_ID "Spark создал $SPEC_ID, запускается"`. `scan_drafts()` удаляется.

---

## Comparison Matrix: Question 1

| Criteria | 1A: Always queued | 1B: Mode-aware | 1C: Queued + info notify |
|----------|------------------|----------------|--------------------------|
| Complexity | Low | Medium | Low |
| Correctness (north-star) | High | Medium | High |
| Operator visibility | Low | High | Medium |
| Dead code eliminated | High | Low | Medium |
| Backward compatibility | Low | High | Medium |
| Risk of stuck specs | Low | Medium | Low |

**Recommendation Q1:** Approach 1A (Always queued).

OpenClaw — это conversational gate ДО inbox. К моменту, когда spec попадает в backlog, approval уже дан неявно. `scan_drafts()` и Step 5.5 — остатки старой модели, когда approval gate был ПОСЛЕ Spark. Их нужно удалить. Если оператор хочет видимость — достаточно стандартного callback-уведомления "autopilot запущен на SPEC-ID".

**Trade-off accepted:** Нет паузы между Spark и Autopilot. Если spec плохой — autopilot начнёт работу. Mitigation: OpenClaw должен хорошо формулировать inbox-запросы, и Spark должен корректно писать spec.

---

---

## Question 2: Callback Step 5.5 — убрать полностью или сохранить информационным

---

## Approach 2A: Полное удаление Step 5.5

**Source:** [Event-Driven Orchestration vs Workflow Engines](https://medium.com/@raghbendrapandey/event-driven-orchestration-vs-workflow-engines-what-we-learned-while-scaling-distributed-systems-e97170ac082c) — события не должны содержать ничего, кроме сигнала о состоянии.

### Description
Удалить Step 5.5 из pueue-callback.sh целиком. `send_spec_approval()` в notify.py, `.notified-drafts-*` файлы — всё удаляется. Callback для Spark выглядит как для любого другого skill: просто уведомление "spark завершился".

### Pros
- Радикальная упрощение callback.sh (убираем ~50 строк кода + деплой логики)
- Удаление `.notified-drafts-*` файлов — устранение stateful side-effect вне БД
- Нет race condition между `scan_drafts()` и Step 5.5 (они оба сейчас защищаются от дубликатов через один и тот же файл)
- Меньше HTTP-вызовов в Telegram per cycle
- `send_spec_approval()` в notify.py тоже удаляется — чище

### Cons
- Теряется видимость: оператор не видит spec-summary перед autopilot
- Если Spark создал некорректный spec — узнаем только когда autopilot завершится (или упадёт)
- Кнопки "Доработать / Отклонить" полностью исчезают — нет способа остановить цикл без ручного редактирования backlog.md

### Complexity
**Estimate:** Easy — 1-2 часа
**Why:** Удалить блок строк 211-257 из pueue-callback.sh. Удалить `send_spec_approval()` и `_parse_spec_for_approval()` из notify.py (экономия ~100 строк). Удалить `.notified-drafts-*` файлы.

### Example Source
После удаления Step 5.5, Step 6 сам по себе отправит уведомление "✅ project: Спека — готово" при завершении Spark — и этого достаточно для operator awareness.

---

## Approach 2B: Сохранить как informational (без кнопок approve/reject)

**Source:** [Human-in-the-Loop Patterns](https://www.arunbaby.com/ai-agents/0025-human-in-the-loop-patterns/) — Intervention pattern: уведомление с контекстом, без блокирования.

### Description
Step 5.5 остаётся, но отправляет plain-text уведомление вместо inline keyboard. Показывает title, why, tasks — но не требует нажатия кнопки. Autopilot запускается автоматически. Оператор может прочитать что будет сделано.

### Pros
- Оператор видит spec-summary с задачами и rationale до того, как autopilot сделал изменения
- Audit trail в Telegram (spec создан, вот что планируется)
- Если оператор видит явную ошибку — может вручную поменять статус в backlog до следующего цикла orchestrator (5 минут)
- Меньше изменений в notify.py чем в 2A

### Cons
- `_parse_spec_for_approval()` и `send_spec_approval()` остаются — код живёт, но кнопки убраны
- `.notified-drafts-*` файлы остаются (dedup по-прежнему нужен для info-notify)
- Notification fatigue: два сообщения на один Spark (info + callback done)
- Сложнее объяснять новым операторам что происходит (зачем уведомление без кнопок?)

### Complexity
**Estimate:** Easy — 1 час
**Why:** Изменить `send_spec_approval()` — убрать inline_keyboard из payload, изменить текст. Или упростить Step 5.5 до вызова `notify.py $PROJECT_ID "$MSG"` с plain-text summary.

### Example Source
Изменение в pueue-callback.sh Step 5.5: вместо `--spec-approval` флага использовать обычный `notify.py "$PROJECT_ID" "📋 Spark создал $SPEC_ID: $TITLE"`.

---

## Approach 2C: Убрать Step 5.5 из callback, переместить в orchestrator.sh как scan_new_specs

**Source:** [CI/CD Pipeline Design Patterns 2026](https://zeonedge.com/sn/blog/cicd-pipeline-design-patterns-2026-advanced-deployment-strategies) — separation of concerns, scheduler handles visibility, not completion callback.

### Description
Вместо того чтобы callback отправлял spec-уведомление, оркестратор в своём цикле проверяет новые queued-спеки и отправляет уведомление один раз при первом обнаружении. Логика dedup та же (`.notified-*` файл), но в orchestrator.sh, а не в callback.

### Pros
- Callback остаётся простым и строго event-based (завершение → notify)
- Orchestrator видит весь контекст (все проекты, все backlog) и может группировать уведомления
- Лучше separation of concerns

### Cons
- Задержка: уведомление придёт не сразу после Spark, а через до 5 минут (следующий цикл orchestrator)
- Усложняет orchestrator: добавляем ещё одну scan-функцию (`scan_new_queued`), хотя сейчас цель — убирать функции
- `scan_drafts()` трансформируется в `scan_new_queued()` — объём работы тот же
- Фактически то же что 2B, только в другом месте

### Complexity
**Estimate:** Medium — 2-3 часа
**Why:** Переписать scan_drafts → scan_new_queued в orchestrator.sh. Нужно изменить grep с `draft` на `queued`. Callback упрощается. Но net-complexity не меняется.

---

## Comparison Matrix: Question 2

| Criteria | 2A: Полное удаление | 2B: Info без кнопок | 2C: Перенести в orchestrator |
|----------|--------------------|--------------------|------------------------------|
| Complexity | Low | Low | Medium |
| Code reduction | High | Medium | Low |
| Operator visibility | Low | Medium | Medium |
| Correctness | High | High | High |
| Maintenance burden | Low | Medium | Medium |
| Dedup files needed | No | Yes | Yes |

**Recommendation Q2:** Approach 2A (полное удаление).

Кнопки approve/reject были смыслом Step 5.5 — они позволяли блокировать autopilot. Без approval gate они теряют смысл. Информационное уведомление создаёт шум (два сообщения на один Spark). Стандартный Step 6 callback уже отправляет "✅ Спека — готово" — достаточно. `_parse_spec_for_approval()` — ~100 строк, которые можно удалить.

**Trade-off accepted:** Оператор не получает spec-summary. Вместо этого логируется в callback-debug.log. Если нужна видимость — можно позже добавить как отдельный скрипт, а не как blocking gate в цикле.

---

---

## Question 3: Dead code scan_drafts() — удалить или repurpose

---

## Approach 3A: Полное удаление scan_drafts()

**Source:** [AEEF Orchestration Rules](https://aeef.ai/transformation/agent-sdlc-orchestration/orchestration-rules) — state machine с явными переходами. `draft` как статус исчезает из системы.

### Description
`scan_drafts()` ищет спеки со статусом `draft` в backlog и отправляет approval notification. Если Spark всегда создаёт `queued` (Approach 1A), то `draft` в backlog никогда не появляется. Функция становится dead code. Удалить полностью вместе с вызовом в `process_project()`.

### Pros
- Orchestrator.sh теряет ~55 строк мёртвого кода
- Упрощается `process_project()`: 4 steps → 3 steps
- Устраняется зависимость от `.notified-drafts-*` файлов
- Чище тестировать: меньше branch points в main loop

### Cons
- Edge case: если кто-то вручную создаст spec со статусом `draft` в backlog — он будет проигнорирован молча
- Нельзя откатить approval gate без восстановления кода

### Complexity
**Estimate:** Easy — 30 минут
**Why:** Удалить функцию `scan_drafts()` (строки 371-425 orchestrator.sh). Убрать вызов `scan_drafts "$project_id" "$project_dir"` из `process_project()`. Удалить `.notified-drafts-*` файлы из SCRIPT_DIR.

---

## Approach 3B: Repurpose как scan_queued_notification (info-only)

**Source:** [Draft-First Automation](https://operaitions.ai/blog/automation-you-can-trust/) — visibility без approval.

### Description
Переименовать `scan_drafts()` в `scan_new_queued()`. Изменить grep с `draft` на `queued`. Отправлять plain-text уведомление "Новый spec в очереди: SPEC-ID — title". Убрать inline keyboard из notify.py путём добавления флага `--info` вместо `--spec-approval`.

### Pros
- Сохраняется оператору видимость новых spec в очереди
- Переиспользует существующую `.notified-*` dedup логику
- Меньше изменений чем в 3A (rename + grep change, не удаление)

### Cons
- Фактически дублирует уведомление с Step 6 callback "✅ Спека — готово"
- Добавляет новый флаг в notify.py — больше кода, не меньше
- `.notified-drafts-*` файлы превращаются в `.notified-queued-*` — overhead остаётся

### Complexity
**Estimate:** Medium — 2 часа
**Why:** Rename + изменение grep. Добавить `--info` режим в notify.py. Переименовать `.notified-drafts-*` файлы. Невысокая сложность, но сомнительная ценность.

---

## Approach 3C: Оставить как fallback recovery для edge cases

**Source:** [Pipeline Finisher executor](https://docs.streamsets.com/platform-datacollector/latest/datacollector/UserGuide/Executors/PipelineFinisher.html) — резервный путь, который срабатывает только при исключительных условиях.

### Description
`scan_drafts()` оставляется, но с флагом `ENABLE_DRAFT_SCAN=false` в `.env`. По умолчанию отключён. Включается оператором вручную если нужно провести batch approval старых спеков или если Spark упал до записи `queued`. Служит как manual recovery tool, не как часть основного flow.

### Pros
- Safety net: если что-то пошло не так и spec завис в `draft` — можно включить и пройтись
- Не удаляется код, который потенциально может понадобиться
- Оператор явно управляет activation

### Cons
- Мёртвый код с флагом — всё равно код, который нужно поддерживать
- Добавляет env-variable overhead
- Создаёт иллюзию "можно вернуться к draft flow" — ложное ощущение backward compat
- Если Spark всегда пишет `queued` — `draft`-спеки могут возникнуть только при баге; это отдельный сценарий, не требующий scan_drafts

### Complexity
**Estimate:** Easy — 30 минут (добавить guard)
**Why:** Добавить `[[ "${ENABLE_DRAFT_SCAN:-false}" != "true" ]] && return` в начало функции. Нет удалений.

---

## Comparison Matrix: Question 3

| Criteria | 3A: Удалить | 3B: Repurpose | 3C: Disabled fallback |
|----------|------------|---------------|----------------------|
| Code reduction | High | Low | Low |
| Correctness | High | High | Medium |
| Maintenance burden | Low | Medium | Low |
| Edge case handling | Low | Medium | Medium |
| Complexity to implement | Low | Medium | Low |

**Recommendation Q3:** Approach 3A (полное удаление).

`scan_drafts()` — это approval gate logic из старой модели. С переходом на `always queued` статус `draft` в backlog не появляется никогда (кроме ручных ошибок). Мёртвый код с protection guard (3C) создаёт ложную уверенность в том, что возврат к draft flow тривиален. Удалить cleanly.

**Trade-off accepted:** Edge case "spec вручную поставили в draft" обрабатывается не автоматически. Оператор должен вручную поменять на `queued` или запустить autopilot вручную через Telegram /run.

---

---

## Question 4: QA→Reflect chain — callback или orchestrator

---

## Approach 4A: Callback dispatches both QA + Reflect (текущий подход, оставить как есть)

**Source:** [Event-Driven Orchestration](https://medium.com/@matcha.2023/designing-event-driven-data-pipeline-orchestration-61971f98e3c9) — события реагируют на завершение, не на расписание.

### Description
Текущая логика в pueue-callback.sh: Step 7 при завершении autopilot диспатчит QA и Reflect в pueue. Обе задачи добавляются сразу, запускаются параллельно (или в порядке FIFO pueue-группы). Callback — источник правды для post-autopilot хвоста.

### Pros
- Event-driven: реакция мгновенная после завершения autopilot (не ждёт следующего цикла orchestrator в 5 минут)
- Контекст для dispatch уже есть в callback: project_path, provider, task_label
- Dedup logic уже реализована (check pueue status before add)
- Reflect имеет guard: `PENDING_COUNT < 1` → skip

### Cons
- Callback растёт: уже 450 строк, Step 7 добавляет ещё ~80 строк
- QA и Reflect dispatched параллельно — если QA находит проблемы, Reflect может запуститься на "плохом" состоянии
- Callback содержит бизнес-логику (когда dispatch, какой skill, какой label) — смешение concerns

### Complexity
**Estimate:** Zero (текущее состояние)
**Why:** Ничего не меняется. Это baseline.

### Example Source
Строки 367-445 в pueue-callback.sh: `if [[ "$STATUS" == "done" && "$SKILL" == "autopilot" ]]`.

---

## Approach 4B: Orchestrator dispatches Reflect ПОСЛЕ завершения QA (sequential chain)

**Source:** [AEEF State Machine](https://aeef.ai/transformation/agent-sdlc-orchestration/orchestration-rules) — строгий порядок этапов, TESTING → SECURITY последовательно.

### Description
Callback при завершении autopilot dispatches только QA. При завершении QA callback dispatches Reflect. Reflect получает полный context: и code changes (от autopilot), и QA findings. Orchestrator наблюдает за qa_pending → qa_running → qa_done → reflect_pending состояниями через DB.

### Pros
- Reflect запускается с QA findings в context — более качественный анализ
- Явная последовательность: autopilot → QA → Reflect (а не autopilot → QA+Reflect параллельно)
- Reflect не запускается на коде который QA ещё не проверил

### Cons
- Общее время удлиняется: QA + Reflect sequential, не parallel
- Сложнее: добавить `qa_done` фазу в DB schema, dispatch Reflect из QA callback
- В нынешней реализации Reflect не читает QA output (он читает diary entries, не qa-report) — sequential chain не даёт прироста качества без изменения Reflect skill prompt
- Добавляет новые фазы в state machine: `qa_running`, `qa_done`, `reflect_pending`

### Complexity
**Estimate:** Medium — 4-6 часов
**Why:** Изменить DB schema (новые фазы). Изменить callback: при завершении QA → dispatch Reflect. Изменить `dispatch_qa()` в orchestrator. Добавить guard на отсутствие qa_done без reflect. Риски регрессий.

---

## Approach 4C: Orchestrator dispatches QA+Reflect в следующем цикле через DB state

**Source:** [AI Agent Workflow Orchestration](https://medium.com/@dougliles/ai-agent-workflow-orchestration-d49715b8b5e3) — orchestrator as central control layer, не distributed event callbacks.

### Description
Callback при завершении autopilot только меняет фазу в DB на `qa_pending`. Orchestrator в следующем цикле (до 5 минут) видит `qa_pending`, dispatches QA и Reflect самостоятельно через `dispatch_qa()`. Нынешняя `dispatch_qa()` в orchestrator.sh уже частично это делает (но сейчас говорит "callback owns dispatch").

### Pros
- Orchestrator — единственный источник dispatch-логики: clean separation of concerns
- Callback максимально прост: slot release + phase update + notify
- `dispatch_qa()` уже есть в orchestrator — нужно только убрать "callback owns" комментарий и дописать

### Cons
- Задержка до 5 минут между autopilot done и QA start (POLL_INTERVAL=300)
- Потеря event-driven преимущества: QA не стартует сразу
- Если POLL_INTERVAL уменьшить — растёт нагрузка на DB/pueue status polling
- `dispatch_qa()` сейчас — только recovery guard (invariant check). Сделать его основным dispatch path — инверсия текущей архитектуры

### Complexity
**Estimate:** Medium — 3-4 часа
**Why:** Переписать `dispatch_qa()` как полноценный dispatcher (добавить Reflect dispatch). Убрать Step 7 из callback. Изменить POLL_INTERVAL или добавить event-файл `.qa-trigger-{project_id}` для немедленного polling.

---

## Comparison Matrix: Question 4

| Criteria | 4A: Callback (как сейчас) | 4B: Sequential QA→Reflect | 4C: Orchestrator cycle |
|----------|--------------------------|--------------------------|------------------------|
| Complexity | Zero | Medium | Medium |
| Event latency | Immediate | Immediate QA, delayed Reflect | Up to 5 min |
| Separation of concerns | Low | Low | High |
| Quality of Reflect | Medium | Medium+ | Medium |
| State machine clarity | Low | Medium | High |
| Regression risk | None | Medium | Medium |

**Recommendation Q4:** Approach 4A (оставить как есть для Reflect+QA dispatch).

Переход на sequential или orchestrator-dispatched chain требует либо нового state machine (4B) либо задержки 5 минут (4C). Текущая параллельная dispatch из callback работает корректно. Reflect уже имеет guard на pending diary entries. В рамках TECH-151 фокус — убрать draft gate и упростить callback, но не переписывать post-autopilot dispatch.

Единственное нужное изменение в Step 7: убедиться что QA/Reflect dispatch остаётся в callback, и никаких новых inbox-записей из QA/Reflect.

**Trade-off accepted:** Reflect запускается параллельно с QA, не после. Качество Reflect не ухудшается: он читает diary entries (записаны autopilot'ом), а не QA report. QA findings → inbox path уже заблокирован Step 6.5 (north-star compliance).

---

---

## Summary Recommendation Matrix

| Question | Chosen Approach | Key Rationale |
|----------|-----------------|---------------|
| Q1: Spark status | 1A: Always `queued` | North-star: OpenClaw уже дал approval до inbox |
| Q2: Step 5.5 callback | 2A: Полное удаление | Кнопки без gate теряют смысл; Step 6 достаточен |
| Q3: scan_drafts() | 3A: Полное удаление | `draft` в backlog не появляется при 1A; dead code |
| Q4: QA→Reflect chain | 4A: Оставить как есть | Event-driven dispatch работает; scope TECH-151 — не переписывать этот слой |

**Estimated total effort:** 3-5 часов (изменения в Spark шаблоне + удаление ~150 строк из callback + удаление scan_drafts)

---

## Research Sources

- [AEEF Orchestration Rules and State Machine](https://aeef.ai/transformation/agent-sdlc-orchestration/orchestration-rules) — strict state machine per work item, один статус в любой момент времени
- [Draft-First Automation Pattern](https://operaitions.ai/blog/automation-you-can-trust/) — когда draft-first нужен (high-stakes irreversible actions), а когда избыточен
- [Human-in-the-Loop Patterns](https://www.arunbaby.com/ai-agents/0025-human-in-the-loop-patterns/) — Approval vs Intervention vs Clarification patterns; когда blocking gate оправдан
- [Event-Driven Data Pipeline Orchestration](https://medium.com/@matcha.2023/designing-event-driven-data-pipeline-orchestration-61971f98e3c9) — события как сигналы о состоянии, не команды; event-driven vs scheduler tradeoffs
- [AI Agent Workflow Orchestration Production Guide](https://medium.com/@dougliles/ai-agent-workflow-orchestration-d49715b8b5e3) — structured plan-execute-test-fix с явными checkpoint'ами
- [CircleCI Approval Jobs](https://oneuptime.com/blog/post/2026-02-02-circleci-approval-jobs/) — approval gate as explicit human checkpoint; когда нужен, когда избыточен
- [Aperant CRITICAL Issue #509](https://github.com/AndyMik90/Aperant/issues/509) — реальный баг: state machine застрял в `human_review`, потому что transition post-approval отсутствовал — аналог нашего `draft` → `queued` gap
