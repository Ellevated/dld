---
id: EXP-013
title: Headless-прогоны теряют инструменты ожидания; автопилот теряет фон механически
opened: 2026-09-23
status: open
metric: автопилот bg_killed и QA ended_on_wait по scripts/metrics/bg_turn_endings.py, только строки `+guards` (срез по полю headless_guards, а не по дате — урок EXP-009); вторичная — автопилот timeout_rate по run_metrics.py
baseline: замер 23.09 (bg_turn_endings.py --log-dir ~/projects/dld/scripts/vps/logs --since 2026-09-23 --until 2026-09-23) — autopilot 39 прогонов, bg_killed 1 (awardybot-20260923-115025 = FTR-1515 #2), ended_on_wait 1; qa 27 прогонов, bg_killed 0, ended_on_wait 6; dispatcher 95/0/0; reflect 27/0/0. Ни один прогон в этом срезе не нёс headless_guards (раннер выкатился позже) — строк `+guards` в базовом срезе нет
expected: autopilot+guards bg_killed = 0; qa+guards ended_on_wait ≤ 1 из 15 (было 6 из 27 ≈ 22%); autopilot timeout_rate не выше 13% (EXP-011 baseline, Opus 5, срез 05.09–22.09, n=61, timeout=8)
command: python3 scripts/metrics/bg_turn_endings.py --log-dir ~/projects/dld/scripts/vps/logs --since 2026-09-24
check_after_runs: 15
check_after_date: 2026-10-07
verdict:
---

## Что было

Замер 23.09 (`~/projects/dld/scripts/vps/logs`, разбор `ai/features/TECH-223-…md` §Why):
main loop headless-прогонов с 23.09 идёт с системным промптом Claude Code (EXP-009), который
учит модель запускать долгое в фоне и ждать уведомления. Уведомлять в headless некого — ход
закончен, сессия закончена. Два случая с ценой:

- автопилот awardybot FTR-1515 #2: два `Agent`-кодера **в фоне** + `ScheduleWakeup(1800)` →
  `Background tasks still running after 600s; terminating.` — $14.16, 73 мин, спека в
  `blocked`, задачи 3–5 переделывал третий прогон.
- QA: 6 из 27 прогонов 23.09 закончили ход фоновым ожиданием (`until`/`for`-опрос CI,
  `Monitor`, обещание «пришлю итог, когда закончится») — итог не приходил, хвост отчёта
  терялся.

Прозе автопилота это уже запрещено (`safety-rules.md` §«Ход не заканчивается ожиданием»),
FTR-1515 всё равно ушёл в фон. У QA такого правила не было вовсе.

## Что изменено

- `runner_cli.HEADLESS_DISALLOWED_TOOLS` (6 инструментов: `ScheduleWakeup`, `Monitor`,
  `CronCreate`, `CronDelete`, `CronList`, `RemoteTrigger`) — снято через `disallowed_tools`
  у **всех** headless-скиллов: будить некого ни одному из них.
- `runner_cli.NO_BACKGROUND_SKILLS = frozenset({"autopilot"})` — только автопилоту
  `runner_loop.build_options` кладёт `env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] = "1"`:
  фоновый `Bash` исчезает как параметр, фоновый `Agent` исполняется синхронно.
- Рычаг отката в `.env`, как у EXP-009: `HEADLESS_BACKGROUND_TASKS=on` возвращает фон
  автопилоту (флаг просто не выставляется).
- Run-лог: `runner_loop.headless_guards(options)` пишется в `log_data["headless_guards"]`
  (`claude-runner.py:312`) — с какими ограничениями реально шёл прогон, из объекта опций,
  ушедшего в SDK, а не из даты деплоя.
- QA-скилл (оба дерева): правило не ждать CI/выкатку — ни циклом, ни в фоне, ни обещанием
  прислать итог позже.
- `safety-rules.md` автопилота (оба дерева): абзац, что запрет теперь механический.

## Механизм

Автопилот закрыт дважды: параметр `run_in_background` у `Bash` пропадает из контекста
(`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`), а `ScheduleWakeup`/`Monitor`/`Cron*` сняты
`disallowed_tools` у всех — это закрывает именно путь FTR-1515 (фоновые субагенты +
будильник), который флаг фона сам по себе не ловил (проба probe-results.md P2). QA
получает не механику, а прозу — решение основателя: QA законно держит dev-сервер в фоне
(devil EC-8), автопилот такого легитимного случая не имеет.

## Пересечения

EXP-011 (Opus 5.5 + системный промпт + раскрытые модули) идёт по тем же прогонам —
автопилот теперь синхронизирует фоновых субагентов, поэтому его `p50_min`/`timeout_rate`
из EXP-011 стоит читать вместе с этим экспериментом, не по отдельности: рост wall-clock
может быть следствием TECH-223, а не 5.5. EXP-009 (системный промпт Claude Code) — причина,
по которой модель вообще стала уходить в фон; сама правка EXP-009 не откатывается, этот
эксперимент лечит следствие, а не источник.

## Если не сработает

- QA `ended_on_wait` не сдвинулся → добавить `qa` в `NO_BACKGROUND_SKILLS` ценой легитимного
  фонового dev-сервера (devil EC-8) — компромисс, а не бесплатный шаг.
- Автопилот упирается в таймаут `Bash`, потому что синхронный `Agent`/`Bash` теперь не
  влезает в отведённое время → сужать набор команд в репо проекта (например, `./test ci` в
  awardybot), лимиты `BASH_*_TIMEOUT_MS`/`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` не поднимать
  (решение основателя, TECH-223 Why).
- В run-логе нет поля `headless_guards` → на VPS работает не этот раннер; сначала проверить,
  какой `claude-runner.py` на самом деле запускает pueue (тот же диагностический шаг, что и
  в EXP-009).
