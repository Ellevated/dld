# QA Report: TECH-170 — Implementation guard sees feature-branch commits

**Date:** 2026-05-02
**Environment:** VDS prod — `dld-orchestrator.service`, sqlite `scripts/vps/orchestrator.db`, pueue daemon
**Trigger:** `/qa TECH-170`
**Local HEAD:** `05d6a6b` (includes TECH-170 commit `e3aa2e2`)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 5     | 2    | 2    | 1       |

Spec помечен `done`, код в `develop` есть, но **в продакшене фича не работает** — orchestrator process не перезапущен после деплоя.

## Failures

### F1: Orchestrator process не перезапущен — новый код TECH-170 не загружен

**Severity:** Critical
**Reproducibility:** Always
**Expected:** После мержа `feat(TECH-170)` в develop, orchestrator пишет `branch=feature/<spec_id>` в `task_log` для каждого autopilot dispatch.
**Actual:** Process PID 2560681 запущен **2026-04-27 11:02** (uptime 5d 2h), а коммит TECH-170 — **2026-05-02 13:23**. Python модули загружаются один раз при старте → деплой dead-code, поведение pre-TECH-170.

**Evidence:**
```
$ ps -o pid,etime,cmd -p 2560681
PID     ELAPSED CMD
2560681 5-02:39:29 python3 .../orchestrator.py

$ sqlite3 orchestrator.db "SELECT COUNT(*) total, COUNT(branch) with_branch
                           FROM task_log WHERE skill='autopilot'
                           AND started_at > '2026-05-02';"
13|0    ← 0 из 13 autopilot-dispatches имеют branch (EC-4 fail в проде)

$ sqlite3 ... "SELECT id,task_label,branch FROM task_log
               WHERE task_label LIKE '%TECH-170%';"
673|dld:TECH-170|<NULL>   ← сам TECH-170 dispatch тоже без branch
```

**User impact:** Guard продолжает фолзить feature-branch коммиты → autopilot specs продолжают демоутиться done → blocked, как BUG awardybot/FTR-898 описанный в спеке. Деплой формально прошёл, фича недоступна.

**Hint:** `systemctl --user restart dld-orchestrator.service`. Стоит добавить deploy hook / restart на git pull или health-check на uptime vs HEAD-commit-time.

---

### F2: TECH-170 был сам демоутнут собственным guard'ом (commit `05d6a6b`)

**Severity:** Major
**Reproducibility:** Once (история, сейчас Status=done в spec и backlog)
**Expected:** Спека с реальными коммитами в `feature/TECH-170` остаётся `done`.
**Actual:** Через ~30 секунд после `pueue` complete callback демоутнул backlog → `blocked` (`docs: mark TECH-170 as blocked (callback auto-fix)`). Кто-то/что-то потом откатил обратно в `done` (видно в `ai/backlog.md` сейчас).

**Evidence:**
```
e3aa2e2 13:24 feat(TECH-170): ...        ← коммит в develop
05d6a6b 13:39 docs: mark TECH-170 as blocked (callback auto-fix)
$ grep TECH-170 ai/backlog.md
| TECH-170 | ... | done | P1 | ...      ← сейчас done (ручной revert?)
```

**User impact:** Подтверждение F1 — guard НЕ видит свежие коммиты в feature/TECH-170 worktree, так как сам guard ещё old-code (см. F1). Замкнутый круг: фича призвана исправить демоут, и её собственная установка попала в этот баг.

**Hint:** После рестарта orchestrator в F1 — повторно прогнать verify_status_sync на TECH-170 чтобы убедиться что новый код видит коммиты `--all` правильно.

---

## Blocked

### B1: Прямая проверка callback IMPL_GUARD логов

**Reason:** В `journalctl --user -u dld-orchestrator` нет ни одной записи `IMPL_GUARD` / `MERGE_CHECK` с 2026-05-02. Pueue task callbacks логируются отдельно (через pueue daemon), доступа к их stderr из-под user-сессии нет — нужен `sudo journalctl -u pueued` или путь к log-файлу `pueued`. Без этих логов невозможно подтвердить EC-1/EC-2/EC-5 на работающей системе.

## Passed

| # | Сценарий | Notes |
|---|----------|-------|
| 1 | Schema migration (`task_log.branch` колонка) | `PRAGMA table_info(task_log)` показывает `branch TEXT` на позиции 10 — `_ensure_migrations()` отработал ✅ |
| 2 | Source-code деплой | `scripts/vps/orchestrator.py:424` содержит `branch=f"feature/{spec_id}"`, callback.py содержит `--all` и `is_merged_to_develop` (по grep) ✅ |

## Out of Scope (сигналы для бэклога)

- **Pre-existing test failures**: result_preview autopilot'а упомянул `test_ec7` и `test_callback_no_impl_demote` как непрошедшие — не регрессия TECH-170, но в репорт стоит отдельный BUG.
- **Deploy-reload gap**: систематическая дыра — нет автоматического restart orchestrator на git pull. Кандидат на TECH-спеку.
- **`/qa` mismatch**: TECH-170 — чистая инфра без UI/API/бота. Black-box проверка возможна только через состояние БД и логи. Для таких спек уместнее `/tester` (запуск unit/integration suite) или dedicated infra-smoke skill.
