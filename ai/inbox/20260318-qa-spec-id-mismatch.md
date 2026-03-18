# Idea: 20260318-202000
**Source:** openclaw
**Route:** spark
**Status:** new
---

QA получает `inbox-20260318-XXXXXX` как SPEC_ID вместо реального TECH/BUG ID который
создал Spark. Это приводит к "QA skipped: spec file not found".

**Причина:** `pueue-callback.sh` Step 7 передаёт `/qa ${TASK_LABEL}` в QA-агент.
`TASK_LABEL` = label pueue-задачи = `inbox-20260318-XXXXXX`. Но spec-файл в
`ai/features/` создан Spark с ID `TECH-NNN` или `BUG-NNN`.

**Цикл:** inbox → Spark (создаёт TECH-157) → autopilot (label=`inbox-XXXXXX`) →
callback передаёт `inbox-XXXXXX` в QA → QA не находит spec.

**Решение:** Spark должен записывать созданный SPEC_ID обратно в inbox-файл
(или в отдельный state), чтобы callback мог его прочитать и передать в QA.

Вариант А: Spark дописывает в inbox-файл строку `**SpecID:** TECH-157`
Callback читает её перед dispatch QA.

Вариант Б: Spark создаёт файл `ai/openclaw/spec-map/{inbox-label}.txt` с SPEC_ID.
Callback читает mapping.

Предпочтительно Вариант А — меньше движущихся частей.
