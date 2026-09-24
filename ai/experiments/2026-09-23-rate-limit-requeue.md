---
id: EXP-014
title: Упор в лимит подписки возвращает спеку в очередь вместо blocked
opened: 2026-09-24
status: open
metric: autopilot-прогоны с `"exit_code": 5` в `~/projects/dld/scripts/vps/logs/*.log` с даты выкатки и что стало с их спекой — `grep "REQUEUE_RATE_LIMIT" scripts/vps/callback-debug.log` против `STATUS_SYNC … blocked` для тех же спек
baseline: 23.09 — 2 прогона упёрлись в лимит подписки (awardybot, dowry), 2 из 2 → `blocked` (`branch_pushed_not_merged:2 ahead`), run-лог `exit_code: 1`, стандартный stderr пуст, причина нигде не записана — найдена только чтением транскрипта сессии вручную
expected: 100% упёршихся в лимит прогонов → exit 5 с блоком `rate_limit` в run-логе; первый возврат каждой спеки за 24ч → `queued` (`rate_limited`), не `blocked`; ни одного `blocked` из-за лимита, кроме `repeated_rate_limit:<n>` на третьем возврате той же спеки
command: find ~/projects/dld/scripts/vps/logs -name '*.log' -newermt 2026-09-24 | xargs grep -l '"exit_code": 5'
check_after_runs: 40
check_after_date: 2026-10-15
verdict:
---

## Что меняется и зачем

23.09 флот упёрся в пятичасовой лимит подписки Max посреди прогона. CLI прислал синтетическое
сообщение с `error: "rate_limit"`, но ничего не бросило исключение по этому поводу — раннер
записал обычный `exit_code: 1`, пустой stderr, и обе задетые спеки (`TECH-1535` в awardybot,
`TECH-526` в dowry) улетели в `blocked`. Причину нашли только вручную, чтением транскрипта
сессии.

TECH-225 даёт раннеру и callback общий структурный сигнал вместо разбора текста:
`runner_ratelimit.from_message` распознаёт `AssistantMessage.error == "rate_limit"` и
`RateLimitEvent.rate_limit_info.status == "rejected"`, `decide_exit` поднимает exit-код до
нового значения **5** (`rate_limited`), если отказ был и прогон не получил успешного результата
(ADR-024 — успешный `ResultMessage` не перебивается). Run-лог всегда несёт блок `rate_limit`.
Callback на exit 5 у autopilot зовёт `callback_ratelimit.requeue` вместо обычного
`verify_status_sync`: пишет `in_progress → queued` с причиной `rate_limited`, решение `requeue`
в `callback_decisions` (`demoted=0` — не считается в circuit breaker), и логирует
`REQUEUE_RATE_LIMIT <spec> → <status> (<reason>)` — строка, по которой замеряет этот эксперимент.
Третий возврат одной спеки за 24 часа эскалирует в `blocked repeated_rate_limit:<n>` через тот
же путь, что и обычный demote.

## Известный потолок: без TECH-226 быстрые повторы сами упрутся в потолок

Эта спека — только распознавание и возврат в очередь. Паузы диспетчинга до `resets_at` нет —
это TECH-226 (AFTER TECH-225), ещё не выкачена на момент открытия эксперимента. Из-за этого
спека, возвращённая в `queued`, диспатчится немедленно и с высокой вероятностью снова упирается
в тот же самый пятичасовой лимит (окно не истекло) — три таких круга за считаные минуты дают
`repeated_rate_limit:3` и спека всё равно уходит в `blocked`, просто по другой причине и после
трёх задокументированных попыток вместо нуля.

Это ожидаемый и известный потолок поведения этой спеки в одиночку, а не опровержение гипотезы.
`expected` про "0 blocked из-за лимита, кроме repeated_rate_limit" сформулирован с учётом этого:
`repeated_rate_limit:<n>` не считается провалом гипотезы EXP-014 — считается сигналом, что
TECH-226 ещё не выкачена. Вердикт по основной гипотезе (первый возврат → `queued`, причина
видна) выносится по срезу **после** выкатки TECH-226, когда пауза флота перестаёт давать
повторные упоры в первые же минуты.

## Если `rate_limit_event` не приходит

Детектор берёт сигнал из двух источников: `RateLimitEvent.rate_limit_info` (даёт `resets_at`,
`rate_limit_type`) и синтетический `AssistantMessage.error == "rate_limit"` (не даёт ничего,
кроме факта отказа). Если сервер/CLI по какой-то причине не пришлёт `rate_limit_event`,
детектор видит только `assistant_error`, и `resets_at` в блоке `rate_limit` run-лога
остаётся `null`. TECH-226 в этом случае не знает, когда
кончается окно, и живёт на запасном фиксированном интервале паузы вместо точного `resets_at`
(её собственный design, не этой спеки). Долгосрочное исправление — поднять
`claude-agent-sdk` до версии ≥ 0.1.81, где у `ResultMessage` появляется `api_error_status`:
боевой venv сейчас на 0.1.63, где этого поля нет (см. TECH-225 Context).

## Если лимит не случился за срок

Если за `check_after_runs`/`check_after_date` флот ни разу не упёрся в лимит подписки — метрика
не даёт данных ни в одну сторону. Статус в этом случае — `inconclusive`, с формулировкой "лимит
за срок не случился, поведение непроверено", а не `confirmed` по умолчанию.
