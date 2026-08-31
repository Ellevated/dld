# QA Report: TECH-214 — раскол lifecycle.py

**Date:** 2026-08-07
**Environment:** local-only (DEPLOY_URL=local-only) + VPS демоны `dld-orchestrator`, `dld-gate-daemon`
**Trigger:** `/qa TECH-214` — верификация закрытой спеки (lifecycle=done, 2026-08-07T03:53Z)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 13    | 13   | 0    | 0       |

## Deploy / CI gate

- Merge `53d2815d` в develop: 2026-08-07 06:51:40 +0300
- `dld-orchestrator` активен с 06:51:51, `dld-gate-daemon` с 06:51:52 → **демоны крутят новый код** (AV-F5 ✅)
- В журнале с момента рестарта — штатные циклы (`cycle complete in 76s`), ни одного traceback/ImportError

## Passed

| # | Сценарий | Результат |
|---|----------|-----------|
| 1 | AV-S1 `import lifecycle` | exit 0 |
| 2 | AV-S2 `import salvage, render_backlog, migrate_backlog_to_lifecycle` (связанные имена) | exit 0 |
| 3 | Публичный шов: 17 имён (`run_git`, `LIFECYCLE_DIR`, `build_initial_yaml`, ошибки, CAS, recovery) резолвятся из `lifecycle` | все OK |
| 4 | Один экземпляр `_write_lock` | `lifecycle._write_lock is lifecycle_cas._write_lock is lifecycle_const._write_lock` → True |
| 5 | LOC-лимит | lifecycle 372, cas 285, recovery 242, push 177, git 154, errors 69, const 45 — все ≤400 |
| 6 | Ни один sibling не импортирует `lifecycle` (нет цикла) | 0 совпадений |
| 7 | AV-F2 весь VPS-набор | **611 passed** за 145s |
| 8 | AV-F3 `tests/integration/test_lifecycle_identity.py` | 5 passed, файл не правился (последний коммит 2026-05-25) |
| 9 | `test_lifecycle_done_terminal.py` зелёный без правок | последний коммит 2026-07-27, до раскола |
| 10 | AV-F4 дрейф-аудит старый код vs новый на одних данных | `Total findings: 2519` и разбивка по 11 проектам **побитово совпадают** |
| 11 | Rule 7 (ADR-025) осталась в `write_lifecycle` | `write_lifecycle.__module__ == 'lifecycle'`, `LifecycleAlreadyDoneError` внутри; живой прогон: `done → queued` отбит |
| 12 | Guard писателя | `by='hacker'` → ValueError |
| 13 | 8 конкурентных `write_lifecycle` в песочнице | 0 ошибок, version 1→9, все 8 переходов в истории (взаимное исключение работает) |

Дополнительно (не из AV):
- `list_by_status()` возвращает **list[dict]** — тот самый контракт, из-за которого спека и родилась, сохранён
- Формат YAML не изменён: набор ключей в песочнице идентичен prod-файлу `ai/lifecycle/TECH-214.yaml`
- `read_lifecycle` несуществующей спеки → `None`; `assert_clean_lifecycle_tree` чист
- CLI-потребители живы: `spec_operator.py --help`, `render_backlog.py`, `lifecycle_audit.py` — exit как ожидается
- `python -m ruff check scripts/vps/` → All checks passed
- `git status --porcelain` в рабочем дереве чист (кроме неотслеживаемого `uv.lock`, к спеке отношения не имеет)

## Failures

Нет.

## Наблюдения (не баги TECH-214)

- `lifecycle_audit.py` показывает 2519 находок дрейфа по 11 проектам — состояние **идентично до и после** раскола, то есть это унаследованный дрейф данных (`bootstrap_as_done`, `missing_from_backlog`, `orphan_yaml`), а не регрессия. Отдельная тема для Hermes.
- В `dld`: `unauthorized_writer` на ARCH-209, TECH-189, TECH-216 (`by=['spark']`) — тоже пре-существующее.

## Fixes Applied

Нет — ничего чинить не потребовалось.
