# Idea: 20260316-203720
**Source:** human
**Route:** spark
**Status:** processing
---
Нужно оформить spec-задачу на изменение orchestration logic DLD в supervised режиме с участием OpenClaw.

Контекст идеи:

Текущий цикл слишком автономный и местами самогенерирует лишние хвосты. Мы хотим изменить его так, чтобы OpenClaw был встроен в контур как conversational gate между циклами, а не только внешним наблюдателем.

Целевой цикл:

1. Пользователь пишет запрос в чат.
2. OpenClaw обсуждает задачу с пользователем, уточняет, формулирует intent.
3. OpenClaw кладёт итоговую мысль в `ai/inbox/`.
4. Inbox подхватывает Spark и оформляет spec.
5. Spark кладёт spec в backlog.
6. Backlog подхватывает Autopilot и реализует задачу.
7. После завершения Autopilot запускаются QA и Reflect.
8. QA и Reflect **ничего не кладут обратно в inbox**.
9. QA и Reflect только репортят результаты.
10. На этом автоматический цикл останавливается.
11. После этого OpenClaw подключается снова, анализирует:
   - что сделал autopilot
   - что сказал QA
   - что сказал reflect
   - есть ли реальные следующие шаги
12. И только после этого OpenClaw предлагает пользователю, что делать дальше, и при необходимости сам кладёт новую мысль в inbox.

Ключевой принцип:

- `inbox -> spark -> backlog -> autopilot -> qa/reflect -> stop`
- Никакого `qa/reflect -> inbox -> spark -> backlog -> autopilot` без участия OpenClaw/человека

Что нужно исследовать и заспекать:

1. Как поменять текущий DLD orchestration contract с autonomous loop на supervised loop.
2. Какие части текущей логики нужно отключить или переписать:
   - `pueue-callback.sh`
   - `orchestrator.sh`
   - `qa-loop.sh`
   - fallback inbox-writing logic
   - все места, где QA/Reflect/Council/Architect сейчас могут писать обратно в inbox автоматически
3. Кто должен стать canonical owner для post-autopilot summary.
4. Как OpenClaw должен подхватывать итоги post-autopilot цикла.
5. Какой должен быть формат финального summary, чтобы OpenClaw мог:
   - коротко доложить человеку
   - выделить реальные проблемы
   - предложить следующий шаг
   - и только потом, при необходимости, положить новую задачу в inbox
6. Как избежать возврата к бесконечным циклам и self-propelling orchestration.

Что важно в итоговой spec:

- опора на текущий код и текущие спеки оркестратора
- не фантазировать мимо реального пайплайна
- явно разделить:
  - automated execution loop
  - conversational decision loop
- зафиксировать, что OpenClaw — это не executor backlog, а supervisory layer между циклами

Нужен нормальный DLD spec с:

- symptom
- target flow
- why / architectural rationale
- impact
- required changes
- ownership model
- allowed files
- tests
- definition of done

Особо важно:

- Spark должен оформить это как изменение orchestration policy / execution model DLD
- В спеке явно зафиксировать, что после autopilot QA/Reflect только report-only
- Новые мысли в inbox после post-autopilot анализа кладёт только OpenClaw (или человек через OpenClaw), а не сам pipeline
