---
id: EXP-009
title: Main loop получает системный промпт Claude Code вместо пустого; алиасы субагентов запинены на поколение main loop
opened: 2026-09-23
status: open
metric: автопилот по флоту и по awardybot — timeout_rate, p50_min, p50_usd, доля ok; плюс model_drift и поле system_prompt в run-логах (run_metrics.py --split 2026-09-23)
baseline: срез с 05.09 по 22.09 — n=61, ok=45, timeout=8 (13%), p50_min 74, p50_usd 10.4 (awardybot n=38, ok=30, t/o 8%, p50 75 мин, $10.6). Все 251 прогон на claude-opus-5 шли с --system-prompt "" и effort medium из .env; model_drift 0 из 251
expected: не хуже baseline при лучшем соответствии конфигурации — timeout_rate <= 15%, p50_usd <= 12.0, p50_min <= 85, доля ok не ниже 70%; model_drift остаётся 0 после ближайшего обновления CLI на VPS; в каждом новом run-логе system_prompt=claude_code и заполнен alias_pins
command: python3 scripts/metrics/run_metrics.py --split 2026-09-23 --by none && python3 scripts/metrics/run_metrics.py --split 2026-09-23 --project awardybot
check_after_runs: 15
check_after_date: 2026-10-14
verdict:
---

## Что было

**Пустой системный промпт.** `runner_loop.build_options` не передавал `system_prompt`, а
`claude_agent_sdk` 0.1.81 в этом случае запускает CLI с `--system-prompt ""`
(`_internal/transport/subprocess_cli.py:209-210`, проверено на VPS). Main loop всех
прогонов автопилота шёл без собственного промпта Claude Code — того, который Anthropic
урезает и перенастраивает под каждое поколение («lean system prompt is now the default…»,
changelog 2.1.154), и в котором на Opus 5 живёт инструкция по делегированию. Решения об
этом не было нигде: ни в ADR, ни в `docs/orchestrator/`, ни в правилах.

Проба на том же SDK 0.1.81 (23.09, sonnet-5, один вопрос «в каком продукте ты работаешь»):

| `system_prompt` | ответ | контекст на старте |
|---|---|---|
| `{"type": "preset", "preset": "claude_code"}` | Claude Code | 32 977 |
| не задан (так было) | NONE | 24 289 |

**Плавающие алиасы.** Frontmatter агентов говорит `model: opus` / `sonnet` / `haiku`, и CLI
резолвит алиас по своей версии. CLI 2.1.280 уже отвечает `claude-opus-5-5`, VPS на 2.1.263
пока `claude-opus-5`, main loop запинен на `claude-opus-5`. Ближайшее обновление CLI на VPS
молча перевело бы planner, debugger, review и всех bughunt- и council-персон на новое
поколение — ровно поломка июля (main 4-8, субагенты 4-6), только в обратную сторону.
Проверено, что пин через env действует на субагента: без него `model: opus` ушёл в
`claude-opus-5-5[1m]`, с `ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-5` — в `claude-opus-5[1m]`.

## Что изменено

- `runner_loop.build_options` передаёт пресет `claude_code` (SDK тогда не передаёт флаг
  вовсе, CLI берёт свой промпт) и кладёт в env `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`.
- `runner_models.py` (новый) — умолчание main loop, пины алиасов (opus следует за Opus-main
  loop, каждый можно задать отдельно), ожидаемый набор для model_drift и каноническое имя
  модели. Суффиксы `[1m]` и дата сборки отбрасываются, версия — нет.
- `claude-runner.py` — `AUTOPILOT_SYSTEM_PROMPT=claude_code|empty` (умолчание
  `claude_code`), пины и режим промпта пишутся в лог запуска и в run-лог
  (`alias_pins`, `system_prompt`).

Пины на VPS сейчас поведенчески нейтральны — там алиас и так резолвится в
`claude-opus-5`. Они в этом же эксперименте потому, что держат модель постоянной, пока
он идёт: смена поколения посреди замера сделала бы его несравнимым.

## Механизм, который проверяем

Промпт Claude Code — это то, что Anthropic меряет на своих coding-evals для каждой модели.
Прогон без него — конфигурация, которую не мерил никто. Ждём не выигрыша, а отсутствия
проигрыша при конфигурации, которая наконец совпадает с задуманной. Возможный выигрыш —
меньше самостоятельных спавнов main loop (инструкция по делегированию) и меньше ходов.

Возможный проигрыш, названный заранее: в промпте Claude Code есть «Commit or push only
when the user asks». Скилл автопилота явно велит коммитить и пушить, и пользовательская
инструкция должна перевешивать, но если main loop начнёт останавливаться перед коммитом
или пушем — это будет видно как рост `needs_review` и `branch_pushed_not_merged`.

## Пересечения

EXP-005 (граф кода снят 21.09) идёт по тем же прогонам awardybot. Оба — проверки «не
хуже». Если срез просядет, откат этого эксперимента — одна переменная, и он делается
первым: `AUTOPILOT_SYSTEM_PROMPT=empty` в `scripts/vps/.env` и следующий срез.

Флот с 11.09 почти стоит (один прогон автопилота 22.09), поэтому страховочная дата — через
три недели, а не через одну.

## Если не сработает

- Просели таймауты, цена или доля ok за порог → `AUTOPILOT_SYSTEM_PROMPT=empty`, verdict
  `refuted`, и отдельный разбор: какие инструкции пресета спорят со скиллом (кандидат номер
  один — commit/push).
- `model_drift` не ноль после обновления CLI → пин не доходит до субагентов на этой
  версии; чинить до перехода на Opus 5.5, иначе переход смешает поколения.
- В run-логе нет `system_prompt` / `alias_pins` → на VPS работает не этот код; сначала
  выяснить, какой `claude-runner.py` на самом деле запускает pueue.
