# QA Report: BUG-218 — переход `queued → in_progress`

**Date:** 2026-07-28
**Environment:** VPS `claude`, systemd `dld-orchestrator` (user unit), repo `/home/dld/projects/dld` @ `61eb8ed`
**Trigger:** `/qa BUG-218` — верификация закрытой спеки (lifecycle `done`, 2026-07-28T08:17:25Z)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 11    | 9    | 1    | 1       |

**Вердикт: код правильный, но НЕ РАБОТАЕТ на проде.** Фикс смёржен в `develop` и функционально
подтверждён на живом модуле, но демон держит в памяти версию, загруженную за 9 часов ДО фикса.
Ни одна спека до сих пор не получает `in_progress`. Спека закрыта `done` при невыполненном
обязательном пункте AV-F2 (рестарт демона), про который сама спека предупреждает:
«На этом уже потеряли цикл 2026-07-27».

## Failures

### F1: Фикс не задеплоен — демон работает на старом коде, баг живёт

**Severity:** Critical
**Reproducibility:** Always
**Expected:** после дispatch'а спека в `ai/lifecycle/<ID>.yaml` читается как
`status: in_progress`, `pueue_id` непустой, `started_at` непустой (AV-F3 / EC-14).
**Actual:** статус остаётся `queued` до самого закрытия; `started_at: null` у всех 207 спек.

**Steps to reproduce:**
1. `systemctl --user show dld-orchestrator -p ExecMainStartTimestamp`
   → `Tue 2026-07-28 01:31:31 EEST`
2. `git show -s --format=%cI 38d77d5` → `2026-07-28T10:29:32+03:00` (сам фикс)
   `git show -s --format=%cI d3748b7` → `2026-07-28T10:44:47+03:00` (fail-closed)
   → процесс загрузил `orchestrator.py` **на 9 часов раньше**, чем фикс появился
3. `grep -L "started_at: null" ai/lifecycle/*.yaml | wc -l` → **0** из 207
4. `grep -l "^status: in_progress" ai/lifecycle/*.yaml` → пусто
5. `journalctl --user -u dld-orchestrator --since "2026-07-28 01:31" | grep -c in_progress`
   → **0** за всё время работы демона

**Живое доказательство на самой BUG-218.** Демон диспатчнул её уже после того, как
Task 2 был закоммичен:

```
Jul 28 10:07:22 claude dld-orchestrator[3788122]:
  {"msg":"autopilot submitted: dld spec=BUG-218 pueue_id=1029"}
```

а её собственный `ai/lifecycle/BUG-218.yaml` — ровно тот симптом, который она описывает:

```yaml
started_at: null
transitions:
- from: queued
  to: done        # перехода in_progress не было
  by: callback
```

**User impact (оператор):** всё, ради чего делалась спека, не работает ни на грамм:
`reconcile_orphans` по-прежнему не видит кандидатов → аварийное восстановление после краха
демона не сработает; `started_at` не пишется → нет измерения длительности прогонов;
час работы агента в `backlog.md` и в аудите выглядит как «в очереди». Плюс отдельный риск:
`TECH-215` разблокируется по `done` BUG-218 и перенесёт обе пропатченные функции — если
рестарт не сделать до этого, вживую фикс так и не проверят.

**Hint for developers:** это не дефект кода — это невыполненный шаг деплоя.
`systemctl --user restart dld-orchestrator`, затем дождаться диспатча одной из шести
`queued`-спек и сверить её yaml. Рестарт — операторское действие: в очереди
ARCH-209, TECH-210, TECH-213, TECH-214, TECH-215, TECH-216, они начнут диспатчиться сразу.
QA намеренно не рестартовала прод-демон сама.

## Blocked

### B1: EC-14 / EC-15 — интеграционные проверки на живом демоне
**Reason:** невыполним до рестарта демона (F1). Обе проверки по построению требуют кода,
которого в запущенном процессе нет. Проверять их сейчас — проверять старую версию.

## Passed

Функциональные сценарии прогнаны **на живом модуле** (`scripts/vps/venv/bin/python3`,
одноразовый git-репозиторий + `DB_PATH=/tmp/qa218_throwaway.db`, прод-состояние не тронуто).
Это отвечает на вопрос «фикс вообще правильный?» независимо от вопроса «он задеплоен?».

| # | Сценарий | Результат |
|---|----------|-----------|
| 1 | Диспатч пишет статус (EC-1) | `queued` → `in_progress` ✓ |
| 2 | `pueue_id` попадает в yaml (EC-2) | `pueue_id: 4242` ✓ |
| 3 | `started_at` штампуется (EC-3) | `2026-07-28T08:19:36Z` — впервые в истории проекта ✓ |
| 4 | Идентичность писателя (EC-4) | `updated_by: orchestrator`, transition `queued→in_progress` ✓ |
| 5 | Восстановление сирот ожило (EC-7) | `reconcile_orphans(alive=∅)` → `['TECH-999']`, статус вернулся в `queued` ✓ |
| 6 | **[NEGATIVE]** CAS-гонка не отменяет диспатч (EC-5) | `LifecycleWriteRaceError` → `scan_queued` вернул `True`, запись была попытана ✓ |
| 7 | **[NEGATIVE]** произвольный сбой git не отменяет диспатч | `RuntimeError("git exploded")` → `True` ✓ |
| 8 | **[NEGATIVE]** pueue недоступен → ноль демоутов (EC-8) | `reconcile_orphans` не вызван, статус цел; при этом `assert_clean_lifecycle_tree` и `cleanup_stale_stashes` выполнились — пропуск действительно узкий ✓ |
| 9 | **[NEGATIVE]** пустое множество ≠ ошибка (EC-9) | демоут состоялся, статус → `queued` ✓ |

Детерминированные гейты: EC-11 `or set()` = 0 ✓ · EC-13 «запись — callback» = 0,
«в двух местах» = 0 ✓ · AV-S1 компиляция ok ✓ · AV-S2 1117 ≤ 1120 ✓ ·
AV-F4 `lifecycle_audit --quiet` exit 0, новых `orphan_yaml` нет ✓ ·
инвариант диспатча в `components.md` присутствует ✓

Негативных сценариев 4 из 9 прогнанных (44%).

## Fixes Applied

Нет. Единственная найденная проблема — деплой, а не код; она вне полномочий QA (<5 LOC).

## Тестовые данные

Всё в `/tmp` (`qa218_probe.py`, `qa218_probe2.py`, `qa218_throwaway.db`, временные репозитории
в `/tmp/tmp*/repo`). Прод-репозиторий, прод-SQLite и `ai/lifecycle/` не изменялись.
Чистить не обязательно — `/tmp`.
