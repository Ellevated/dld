---
id: EXP-017
title: builtin-путь диспатча снят (scan_queued, orchestrator_ci_gate, гейты orchestrator_queue) — решение «что запускать» остаётся только у LLM-диспетчера; проверяем на откат, что ничего не ломается
opened: 2026-09-27
status: open
metric: (1) доля успешных пассов диспетчера — логи scripts/vps/logs/dld-YYYYMMDD-*.log с "exit_code": 0 (исход процесса, а не вывод dispatch_one); (2) транскрипты пассов диспетчера (~/.claude/projects/-home-dld-projects-dld/*.jsonl, где есть dispatch_summary.py), в которых Traceback называет orchestrator_queue, dispatch_one, dispatch_summary, spec_deps или fleet_pause — трейсбек dispatch_one попадает в вывод Bash-вызова модели, а не в orchestrator.log и не в exit_code пасса; (3) только если dld-orchestrator перезапущен до check_after_date — в orchestrator.log после рестарта есть «cycle complete», нет «cycle error» и «startup_reconcile FATAL»
baseline: (1) 23.09 — 94 из 96 пассов успешны, 26.09 — 94 из 94. (2) 20–26.09 — 0 транскриптов с таким трейсбеком в сутки при 92–97 транскриптах диспетчера в сутки. (3) рестарта не было с 07.09 19:54. Builtin-путь не вызывался с 07.09 19:52 (DISPATCH_MODE не задан, по умолчанию llm), так что выбор спек с 07.09 уже идёт без него — это проверка на откат, а не на улучшение
expected: за 7 дней — (1) ≥ 95% успешных пассов; (2) 0 транскриптов с трейсбеком по этим модулям; (3) если рестарт был — цикл без ошибок. Любое нарушение — refuted
command: ssh dld@5.61.91.190 'cd ~/projects/dld/scripts/vps/logs && for d in $(seq -f "202609%02g" 27 30) $(seq -f "202610%02g" 1 4); do t=$(ls dld-$d-*.log 2>/dev/null | wc -l); ok=$(grep -l "\"exit_code\": 0" dld-$d-*.log 2>/dev/null | wc -l); echo "$d passes $ok/$t"; done; find ~/.claude/projects/-home-dld-projects-dld -name "*.jsonl" -newermt "2026-09-27 02:00" -exec grep -l dispatch_summary.py {} + | xargs -r grep -lE "Traceback[^\"]{0,4000}(orchestrator_queue|dispatch_one|dispatch_summary|spec_deps|fleet_pause)" | wc -l; grep -hE "cycle error|startup_reconcile FATAL" /var/log/dld-orchestrator/orchestrator.log* | tail -3'
check_after_runs: 10
check_after_date: 2026-10-04
verdict:
---

## Что изменено

Проход «что снять» (стандарт «Агент вместо рельсов»), срез 2 из описи
`docs/2026-09-27-snyatie-relsov-dispetchera.md`. Одно изменение: удалён путь, который не
вызывался с 07.09. Отдельным коммитом того же прохода (`fix(dispatch)`) исправлен
`spec_body_files` — он брал тело чужой спеки по префиксу ID; это исправление дефекта, которое
замер не меняет.

| Где | Что сделано |
|---|---|
| `orchestrator.py` | ушли `scan_queued`, `_select_dispatchable_spec`, `MAX_DISPATCH_CANDIDATES`, `DISPATCH_MODE`, импорты `orchestrator_ci_gate` / `orchestrator_queue` / `gate_logic`; 412 → 305 строк, файл вышел из реестра LOC-долга |
| `orchestrator_ci_gate.py` | удалён целиком (выключен с 07.09) |
| `orchestrator_queue.py` | остались `spec_body_files`, `record_dispatch`, `dispatch_night_review` — их зовёт `dispatch_one.py`; ушли `gate_before_pueue_add`, `recently_processed`, `spec_has_allowlist`, `resolve_provider`, `status_still_dispatchable`, `reconcile`, `reconcile_if_implemented`, `_unmet_dependencies` и алиасы `spec_deps`; 373 → 119 |
| Тесты | удалены тесты удалённых гейтов (`test_orchestrator_ci_gate.py`, 7 классов `test_orchestrator.py`, reconcile/CLAUDE_CONTINUE_BRANCH, builtin-случаи `test_dispatch_one_pause.py`). Покрытие живого кода перенесено: BUG-218 (`in_progress`, `pueue_id`, `started_at`, отказ записи не откатывает запуск, восстановление сирот) гоняется через `dispatch_one.dispatch`; BUG-199 (`CLAUDE_CURRENT_SPEC_PATH`) — поведенческий тест на `dispatch_one` вместо грепа текста `scan_queued`; ветки `spec_deps.declared` — в `test_spec_deps.py`; поиск тела спеки и стена «нет тела» — в `test_dispatch_one.py` |
| Доки | `docs/orchestrator/*`, `.claude/rules/dependencies.md`, `loc-limit-baseline.txt` (снижение) |

## Что уходит вместе с путём

Ни одна из проверок не проходит тест стены: всё это обратимо и стоит максимум одного прогона. Но
не всё из этого чем-то заменено — так и записано.

- Откат `DISPATCH_MODE=builtin`: за 11 дней простоя (11–22.09) им не воспользовались, и он бы не
  помог — падали все claude-прогоны.
- TOCTOU-перепроверка статуса: второй запуск живой спеки держит стена `dispatch_one` «уже живая в
  pueue»; сводка показывает только queued/resumed. Статус спеки `dispatch_one` сам не читает — что
  спека, названная диспетчером, действительно queued/resumed, держит только его суждение.
- «Уже на develop → `done` без запуска»: **не заменено.** Ранний выход autopilot (BUG-188) ищет ID
  спеки в заголовке коммита, а 9 из 15 проектов пишут `feat(managed): …` — та же проверка, которую
  TECH-220 признал ложной в 31 из 61 вердикта. Два сценария, где слитая спека стоит в `queued`:
  exit 5 после мержа (`callback_ratelimit.requeue` пишет `queued` без гейта) и сироты при рестарте
  оркестратора (`reconcile_orphans` переводит `in_progress` с мёртвым pueue_id в `queued`). Итог —
  полный прогон autopilot на готовой работе, который закончится `done` от callback-гейта. С 07.09
  так уже было; снятие дыру не создало и не закрыло. Закрывать — фактом «уже на develop: <sha>» в
  сводке диспетчера (упряжь), следующим шагом.
- Проверка allowlist: снятый гейт звал тот же парсер, что callback; сводка проверяет только
  заголовок секции регэкспом (`dispatch_summary._spec_problem`). Секция с маркером v1 без путей в
  backticks пройдёт сводку и будет заблокирована callback'ом (`empty_allowed_files`). Тоже так с
  07.09; следующим шагом — `_spec_problem` на `gate_logic.parse_allowed_files`.
- Продолжение ветки после таймаута (TECH-221 `"continue"`): флаг `CLAUDE_CONTINUE_BRANCH` никто не
  читал — autopilot-промпты находят `origin/<type>/<ID>` сами через `git ls-remote`.

## Если не сработает

Трейсбек по снятым модулям или провал пассов — `git revert` коммита; процесс оркестратора до
рестарта держит старый код, так что откат безопасен в любой момент. Две незакрытые дыры выше в
вердикт этого эксперимента не входят: у каждой будет свой замер, когда её закроют.
