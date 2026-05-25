# Autostash silently overwrites fresh callback Status commits

**Status:** draft
**Source:** manual
**Route:** spark
**Context:** dfa026b (safe autostash), ADR-018 (callback as sole writer)

## Симптом

После callback'а, который коммитит `Status: done`/`blocked` в spec/backlog
и пушит в `origin/develop`, оркестратор на следующем цикле:

1. Видит грязное рабочее дерево (любые M/D/?? артефакты — QA-репорты,
   diary, мусор от прошлых ренеймов).
2. Делает `git stash push -m "orchestrator-autostash-<proj>-<ts>"`
   → в stash попадает СТАРАЯ версия spec/backlog (с `Status: queued` или
   `in_progress`, без callback'овой правки).
3. `git pull --ff-only origin develop` — подтягивает callback-коммит.
4. `git stash pop` — без конфликта (callback правил только Status,
   а в working tree эти файлы тоже были модифицированы по тем же местам
   но в stash попало "до"), pop **тихо перезаписывает** свежий done →
   working tree снова `Status: queued/in_progress`.

Через 5 минут `scan_backlog` видит `queued` (из-за dirty working tree)
и **снова диспатчит** уже сделанную задачу. Autopilot тратит ~$0.58
+ qa + reflect просто чтобы откатить откат.

## Свидетельства (2026-05-15)

- **dowry:FTR-429** — 6 повторов за 50 мин, ~$4 сожжено.
  Каждый прогон 11 turns с финальным сообщением:
  > "Локальный revert статуса в backlog/spec откачен. Spec: FTR-429 → done"
  (см. pueue log 2708)
- **awardybot:FTR-1012/1018** — те же autostash-флипы;
  HEAD = done, working tree = in_progress, не закоммичено.

## Корень

`dfa026b` («safe autostash») защищает только от **потери при конфликте**:
при конфликте stash остаётся на полке, оператора предупреждают.
Но при **бесконфликтном pop** старая версия молча применяется поверх
свежей — что и происходит для callback-marker полей (Status / Allowed
Files), потому что их формат и расположение стабильны и не дают
текстового конфликта.

## Предлагаемое решение

Перед `git stash pop` отбрасывать из stash все hunks, попадающие в
секции, обрамлённые `<!-- DLD-CALLBACK-MARKER-START v1 -->`/`-END`
(callback — единственный writer этих секций по ADR-018, TECH-172).

Варианты:
- (A) `git checkout stash@{0} -- <files>` через интерактивный extract
  по hunks: распарсить diff, отбросить hunks внутри CALLBACK-MARKER
  ranges, применить остаток.
- (B) Проще: `git stash show stash@{0} --name-only` → для каждого
  файла `git checkout HEAD -- <file>` после pop, чтобы перетереть
  оригиналом-из-HEAD; но это разрушит легитимные изменения.
- (C) Самый дешёвый: после pop запустить `verify_status_sync` на
  всех затронутых spec/backlog — если working tree Status ≠ HEAD
  Status, форсировать `git checkout HEAD -- <file>` именно для
  callback-marker секций (через regex-replace в файле).

Рекомендую (C): минимум кода, использует существующую инфру
verify_status_sync, не лезет в git internals.

## Дополнительно

- В каждом проекте уже накоплены сотни D-файлов (например, `dowry`
  имел 193 удалённых `ai/openclaw/pending-events/*` после ренейма
  OpenClaw→Hermes), которые держат рабочее дерево грязным
  бесконечно. Стоит написать health-check, который раз в день
  орёт в Hermes "у тебя в `<proj>` >50 untracked/modified".
- Тактически уборку в `dowry` и `awardybot` уже сделал
  (commits `1edd974d` / `7ccbd187`).
