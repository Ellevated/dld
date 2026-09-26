---
id: EXP-016
title: gate-daemon (ARCH-190 shadow merge-gate) снят — код, юнит, теневой журнал; проверяем, что без него ничего не ломается
opened: 2026-09-27
status: open
metric: (1) строки «git fetch failed» и «Cannot fast-forward to multiple branches» в /var/log/dld-orchestrator/orchestrator.log*; (2) у каждого вердикта callback-гейта после 27.09 есть поле gate_via в scripts/vps/callback-audit.jsonl; (3) ни одной ошибки или алерта, где упоминается gate-daemon, gate_health или gate-daemon-shadow — journalctl --user, hermes-wake.log, orchestrator.log
baseline: 19–26.09 — multiple_branches 0, fetch_failed 8 (2 за 23.09, 6 за 24.09). gate-daemon active с 23.08 18:08 и ни разу не перезапускался, теневой JSONL 73 МБ, в его строках нет gate_via (поле добавлено 30.08). Потребителя нет — проверено grep по ~/ops, ~/.hermes, ~/deploy, crontab, user-таймерам; из кода журнал читал только тест
expected: за 7 дней после снятия — multiple_branches = 0, fetch_failed ≤ 8, 0 упоминаний gate-daemon/gate_health в ошибках и алертах, gate_via есть у 100% вердиктов callback-гейта
command: ssh dld@5.61.91.190 'cd /var/log/dld-orchestrator && for f in orchestrator.log*; do echo "$f $(grep -c "multiple branches" $f) $(grep -c "git fetch failed" $f)"; done; grep -c gate-daemon ~/projects/dld/scripts/vps/logs/hermes-wake.log; journalctl --user --since 2026-09-27 -p warning | grep -ci gate'
check_after_runs: 10
check_after_date: 2026-10-04
verdict:
---

## Что изменено

Проход «что снять» (стандарт «Агент вместо рельсов»), срез 1 из описи
`docs/2026-09-27-snyatie-relsov-dispetchera.md`. Это одно изменение:

| Где | Что сделано |
|---|---|
| Репо | удалены `scripts/vps/gate-daemon.py` и `scripts/vps/tests/test_gate_daemon.py`; из `db_decisions.py` / `db.py` ушли `log_gate_cycle` и `get_gate_health`; `setup-vps.sh` не пишет и не включает `dld-gate-daemon.service`; EC-12 в `tests/unit/test_callback_implementation_guard.py` проверяет три точки вызова `find_implementation` вместо четырёх; доки оркестратора и `dependencies.md` |
| Оставлено | таблица `gate_health` в `schema.sql` и `_MIGRATIONS` — без писателя. Снести её — решение про данные, не чистка кода |
| VPS | `dld-gate-daemon.service` остановлен и выключен, unit-файл убран, теневой JSONL сжат в `~/.local/log/archive/` |

Поведение флота не меняется: демон ничего не решал и статус не писал.

## Механизм, который проверяем

Гипотеза: у демона не было потребителя, поэтому его снятие ничего не ломает, но убирает `git fetch` по
всем проектам раз в минуту, ротацию журнала до 600 МБ на хосте с дефицитом диска и пятую точку вызова
`find_implementation`, которую приходилось держать в синхроне с боевыми.

## Если не сработает

Если что-то окажется читателем теневого журнала или `gate_health` (ошибка, алерт, пустой отчёт) —
`git revert` коммита и `systemctl --user enable --now dld-gate-daemon` из восстановленного
`setup-vps.sh`. Если вырастет `fetch_failed` — это не демон (он только добавлял фетчей), смотреть сеть и
`orchestrator_git`.
