---
id: EXP-017
title: builtin-путь диспатча снят (scan_queued, orchestrator_ci_gate, гейты orchestrator_queue) — решение «что запускать» остаётся только у LLM-диспетчера; проверяем, что ничего не ломается
opened: 2026-09-27
status: open
metric: (1) доля успешных пассов диспетчера — логи scripts/vps/logs/dld-YYYYMMDD-*.log с "exit_code": 0; (2) Traceback/ImportError с упоминанием orchestrator_queue, dispatch_one, spec_deps, orchestrator в логах пассов и /var/log/dld-orchestrator/orchestrator.log; (3) после рестарта dld-orchestrator — строки «cycle complete» есть, «cycle error» и «startup_reconcile FATAL» нет; (4) autopilot-прогоны, которые вышли на «работа уже на develop» (ADR-024 early exit) — builtin-путь закрывал их без запуска
baseline: 23.09 — 94 из 96 пассов успешны, 26.09 — 94 из 94 (dld-2026092{3,6}-*.log). Builtin-путь не вызывался с 2026-09-07 19:52 (DISPATCH_MODE не задан в .env, по умолчанию llm), поэтому поведение флота с 07.09 уже равно поведению после снятия. Процесс dld-orchestrator с 07.09 19:54 держит в памяти код той даты, включая scan_queued
expected: за 7 дней — успешных пассов ≥ 95%, 0 трейсбеков по снятым модулям, после рестарта оркестратора цикл идёт без ошибок, прогонов с ранним выходом «уже на develop» ≤ 2
command: ssh dld@5.61.91.190 'cd ~/projects/dld/scripts/vps/logs && for d in $(seq -f "202609%02g" 27 30) $(seq -f "202610%02g" 1 4); do t=$(ls dld-$d-*.log 2>/dev/null | wc -l); ok=$(grep -l "\"exit_code\": 0" dld-$d-*.log 2>/dev/null | wc -l); echo "$d $ok/$t"; done; grep -c "Traceback" /var/log/dld-orchestrator/orchestrator.log*'
check_after_runs: 10
check_after_date: 2026-10-04
verdict:
---

## Что изменено

Проход «что снять» (стандарт «Агент вместо рельсов»), срез 2 из описи
`docs/2026-09-27-snyatie-relsov-dispetchera.md`. Одно изменение: удалён путь, который не
вызывался с 07.09.

| Где | Что сделано |
|---|---|
| `orchestrator.py` | ушли `scan_queued`, `_select_dispatchable_spec`, `MAX_DISPATCH_CANDIDATES`, `DISPATCH_MODE`, импорты `orchestrator_ci_gate` / `orchestrator_queue` / `gate_logic`; 412 → 305 строк, файл вышел из реестра LOC-долга |
| `orchestrator_ci_gate.py` | удалён целиком (выключен с 07.09) |
| `orchestrator_queue.py` | остались `spec_body_files`, `record_dispatch`, `dispatch_night_review` — их зовёт `dispatch_one.py`; ушли `gate_before_pueue_add`, `recently_processed`, `spec_has_allowlist`, `resolve_provider`, `status_still_dispatchable`, `reconcile`, `reconcile_if_implemented`, `_unmet_dependencies` и алиасы `spec_deps`; 373 → 119 |
| Тесты | удалены тесты удалённых гейтов (`test_orchestrator_ci_gate.py`, 7 классов `test_orchestrator.py`, reconcile/CLAUDE_CONTINUE_BRANCH, builtin-случаи `test_dispatch_one_pause.py`). Покрытие живого кода перенесено, а не потеряно: BUG-218 (`in_progress`, `pueue_id`, `started_at`, отказ записи не откатывает запуск, восстановление сирот) теперь гоняется через `dispatch_one.dispatch`; BUG-199 (`CLAUDE_CURRENT_SPEC_PATH`) — поведенческий тест на `dispatch_one` вместо грепа текста `scan_queued`; ветки `spec_deps.declared` (нет ключа, `DEP_SHAPE`, legacy-backlog) — в `test_spec_deps.py` |
| Доки | `docs/orchestrator/*`, `.claude/rules/dependencies.md`, `loc-limit-baseline.txt` (снижение) |

## Что уходит вместе с путём и почему это не стены

- Откат `DISPATCH_MODE=builtin`: за 11 дней простоя (11–22.09) им не воспользовались, и он бы не
  помог — падали все claude-прогоны.
- TOCTOU-перепроверка статуса: второй запуск живой спеки держит стена `dispatch_one` «уже живая в
  pueue»; сводка показывает только queued/resumed.
- «Уже на develop → `done` без запуска»: это был третий писатель статуса в обход callback;
  работу, лежащую на develop, закрывает ранний выход autopilot (ADR-024) и callback-гейт.
- Продолжение ветки после таймаута (TECH-221 `"continue"`): флаг `CLAUDE_CONTINUE_BRANCH` никто не
  читал — autopilot-промпты находят `origin/<type>/<ID>` сами через `git ls-remote`.

## Если не сработает

Трейсбек по снятым модулям или провал пассов — `git revert` коммита; процесс оркестратора до
рестарта всё равно держит старый код, так что откат безопасен в любой момент. Если прогонов с ранним
выходом «уже на develop» больше двух — вернуть проверку «уже на develop» не в оркестратор, а в
`dispatch_one.py` как стену с причиной, одним местом.
