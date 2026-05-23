# QA Report: ARCH-186 — Orchestrator Lifecycle State SoT

**Date:** 2026-05-16
**Environment:** /home/dld/projects/dld (develop @ a0c5287, ветка arch/ARCH-186 @ 7e32f3d)
**Trigger:** `/qa ARCH-186` — пользователь попросил проверить спек.
**Mode:** Spec-verification protocol (спек помечен `done` на develop HEAD, но операторская правка локально вернула его в `queued` — классический сигнал false-done).

---

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 6     | 0    | 3    | 3       |

**VERDICT: HARD-FAIL.** Спек ARCH-186 — false-done. На develop отмечен callback'ом как `done`, но 6 из 11 заявленных в Definition of Done артефактов отсутствуют. Реальная реализация — только Tasks 1-3 (~50% LOC) на неcмерженной ветке `arch/ARCH-186`.

---

## Pre-flight (Step 0 / Step 1)

- Project: dld. Это инфраструктурный спек (orchestrator/callback). Web/API/Bot не задействован.
- Deploy URL: N/A — все артефакты живут локально в git и на VPS systemd unit `dld-orchestrator.service`.
- CI: `gh` недоступен в этом окружении (skip).
- Working tree dirty: операторские правки в `ai/backlog.md`, `ai/features/ARCH-186-…md`, `ai/diary/.last_reflect`. Спек руками возвращён в `queued`.
- Branch state:
  - `develop` @ `a0c5287 docs: mark ARCH-186 as done (callback auto-fix)` — спек помечен done **без** мерджа реализации
  - `arch/ARCH-186` @ `7e32f3d refactor(orchestrator): lifecycle.yaml as SoT…` — 3 коммита впереди develop, **не смержена**

---

## Failures

### F1: False-done на develop без реализации

**Severity:** Critical
**Reproducibility:** Always

**Expected:** Спек, помеченный `done`, имеет реализацию в смерженной ветке (все Allowed Files изменены, тесты добавлены, DoD выполнен).

**Actual:** На `develop` HEAD:
- `**Status:** done` в spec.md (коммит `a0c5287`)
- Никакого мерджа `arch/ARCH-186` в develop **не было**
- Все три feature-коммита (`038a325`, `46a4a87`, `7e32f3d`) живут только на ветке `arch/ARCH-186`

**Steps to reproduce:**
```bash
git log --oneline --all --grep="ARCH-186"
# 7e32f3d refactor(orchestrator): lifecycle.yaml as SoT… (Task 3) — arch/ARCH-186
# 46a4a87 refactor(callback): delegate status writes… (Task 2) — arch/ARCH-186
# 038a325 feat(lifecycle): add atomic git-plumbing…   (Task 1) — arch/ARCH-186
# a0c5287 docs: mark ARCH-186 as done (callback auto-fix) — develop  ← false-done
git branch --contains 038a325
# + arch/ARCH-186                                       ← НЕ develop
```

**Evidence:**
- spec_verify HARD-FAIL: 6 missing files (см. F2)
- Callback audit log (`scripts/vps/callback-audit.jsonl`) показывает корень причины (см. F3)

**User impact:** Backlog врёт оператору про прогресс. Если этот спек удалят/архивируют как done — потеряется частичная реализация Tasks 1-3 (~628 LOC новой логики на ветке). Кроме того, ARCH-186 был задизайнен ИМЕННО для устранения этого класса ошибок — а сам стал его жертвой.

**Hint for developers:** Реальный статус — `in_progress` (Tasks 1-3 готовы, Tasks 4-11 ждут). `spec_operator.py demote done→blocked` подходит, если решение — приостановить; правильнее — продолжить работу на feature-ветке.

---

### F2: 6 файлов из Allowed Files / DoD отсутствуют на develop

**Severity:** Critical
**Reproducibility:** Always

**Expected:** Все 16 файлов из `## Allowed Files` спека либо изменены, либо помечены как `**DELETE**` и удалены.

**Actual:** `spec_verify.py` репортит:

```
Step 2 — File existence:
  MISS scripts/vps/lifecycle.py                              ← Task 1, NEW
  MISS scripts/vps/render_backlog.py                          ← Task 4, NEW
  MISS scripts/vps/migrate_backlog_to_lifecycle.py            ← Task 5, NEW
  MISS scripts/vps/tests/test_lifecycle.py                    ← Task 10, NEW
  MISS scripts/vps/tests/test_orchestrator_lifecycle.py       ← Task 10, NEW
  MISS ai/lifecycle/*.yaml                                    ← Task 11 pilot, NEW

  OK   scripts/vps/marker_utils.py            (1 коммит — НЕ удалён!)
  OK   scripts/vps/tests/test_marker_utils.py (1 коммит — НЕ удалён!)
  OK   scripts/vps/tests/test_orchestrator_autostash_marker.py (2 — НЕ удалён!)
```

**Steps to reproduce:**
```bash
python3 scripts/vps/spec_verify.py /home/dld/projects/dld ARCH-186 | tail -10
# VERDICT: HARD-FAIL — 6 missing file(s)
```

**Evidence:** Полный вывод `spec_verify.py` — 6 missing, ни один из трёх `**DELETE**`-файлов не удалён.

**User impact:** Definition of Done заявляет:
- ✗ `marker_utils.py` удалён → **не удалён**
- ✗ `verify_status_sync` < 50 LOC → **остался 284 LOC на develop** (переписан только на ветке)
- ✗ orchestrator: `assert_clean_lifecycle_tree() + reconcile_orphans()` → **нет на develop**
- ✗ 714 LOC старых тестов удалены → **на месте**
- ✗ Pilot на dld → **миграционный скрипт даже не существует**

Состояние «done» = заведомо ложное по 6+ критериям из DoD.

**Hint:** Спек должен быть `in_progress` (Tasks 1-3 на feature-ветке) или `blocked` с явной причиной "false-done; Tasks 4-11 pending". См. F3 для понимания, как callback ошибся.

---

### F3: Callback auto-close сработал на коммите-переименовании, не на реализации

**Severity:** Critical (root cause — bug в самом callback'е, тот самый который ARCH-186 чинит)
**Reproducibility:** Воспроизведено в SQLite + audit log

**Expected:** Callback auto-close (TECH-176/177 — `_spec_has_merged_implementation`) должен срабатывать только когда коммит реально реализует спек.

**Actual:** Хронология из `scripts/vps/orchestrator.db::callback_decisions` + `callback-audit.jsonl`:

```
2026-05-16T08:25:08Z  ARCH-975 demote     no_implementation_commits   demoted=1
                      (старый ID; код был ARCH-975 до переименования)

2026-05-16T08:42:58Z  ARCH-186 sync→done  reason=fixed                code_commits=1, code_loc=4
                      ↑ ЭТОТ КОММИТ — f41903f "docs: renumber drifted spec IDs back to sequential
                        (973/974/975 -> 184/185/186)"
                        Тронул ai/backlog.md (в Allowed Files ARCH-186) — false positive!
                        Реализации НОЛЬ, но callback засчитал = done.

2026-05-16T08:48:55Z  ARCH-186 sync→done  spec_already_done           (закрепил false-done)
2026-05-16T10:23:15Z  ARCH-186 sync→done  spec_already_done           (был blocked, переведён в done)
2026-05-16T10:26:26Z  ARCH-186 sync→done  spec_already_done           (закрепил снова)
```

**Steps to reproduce:**
```bash
sqlite3 scripts/vps/orchestrator.db \
  "SELECT * FROM callback_decisions WHERE spec_id IN ('ARCH-186','ARCH-975') ORDER BY rowid"
grep ARCH-186 scripts/vps/callback-audit.jsonl
```

**Evidence:**
- `callback-audit.jsonl:5` запись `target_in=done, target_out=done, reason=fixed, code_loc=4, code_commits=1` — этот коммит сделал именно переименование ID, а не реализацию.
- `git show f41903f --stat` подтверждает: трогает только `ai/backlog.md` и `ai/features/ARCH-9*.md` → `ai/features/ARCH-18*.md`.

**User impact:** Любой спек, у которого `ai/backlog.md` в Allowed Files (а это очень многие architecture-уровневые спеки) подвержен false-positive auto-close на любом editing-коммите backlog'а. Это **новый рецидив** паттерна `callback false-done` (project memory: callback-false-done-pattern.md).

**Hint for developers:** Тот же класс багов, что TECH-176/177/179 пытались закрыть. ARCH-186 решает его архитектурно (lifecycle.yaml как SoT, callback не трогает spec.md). Пока ARCH-186 не доделан — нужен hot-fix в `_spec_has_merged_implementation`: исключать subject-matches вида "docs:" или "renumber", или требовать минимум N не-md LOC в коммите.

---

## Blocked

### B1: DoD проверка — невозможно завершить

**Reason:** 6 файлов из Allowed Files отсутствуют. DoD checklist (15 пунктов) проверять бессмысленно — большинство автоматически FAIL.

### B2: Тестирование `lifecycle.py` API через CLI

**Reason:** Модуля `scripts/vps/lifecycle.py` на develop нет. На ветке `arch/ARCH-186` есть, но переключение веток не входит в QA-протокол (это запустит реальный orchestrator daemon, что может вызвать запуск других задач на других проектах). Тест API → `/tester` на ветке `arch/ARCH-186`.

### B3: Тест миграции (Tasks 5, 11)

**Reason:** `migrate_backlog_to_lifecycle.py` не существует ни в develop, ни на feature-ветке. Pilot-rollout на dld не выполнен.

---

## Fixes Applied

**Nothing applied.** Сценарий не относится к классу «light fix < 5 LOC». Это R1 P0 архитектурный спек, требующий human review (spec явно говорит: **ACTION REQUIRED: HUMAN REVIEW BEFORE AUTOPILOT**).

Локальная правка спека `done → queued` уже сделана оператором в working tree — это попытка восстановить корректный статус, но технически неточная (правильно `in_progress`, не `queued` — работа же начата на feature-ветке).

---

## Passed

Ни одного сценария не прошло. Все 6 заявленных проверок упали либо в FAIL, либо в BLOCKED.

---

## Recommended Next Actions (для founder'а, не для autopilot)

1. **Восстановить правду в spec/backlog:**
   ```bash
   python3 scripts/vps/spec_operator.py demote dld ARCH-186 \
     "false-done: callback auto-closed on renumber commit f41903f, only Tasks 1-3 done on arch/ARCH-186"
   ```
   Это пишет `Status: blocked` + `Blocked Reason`. Не идеально (правильнее `in_progress`), но честнее текущего `done`/`queued`.

2. **Решить судьбу `arch/ARCH-186`:**
   - (a) Continue manually — это R1 P0, явно требует human-review-before-autopilot. Tasks 4-11 + миграция.
   - (b) Откатить и переделать через `/spark` с уточнённым scope.
   - (c) Merge Tasks 1-3 как promo + создать отдельный spec ARCH-187 для остатка.

3. **Hot-fix `_spec_has_merged_implementation` (callback.py)** — пока ARCH-186 не доделан, добавить эвристику:
   - Игнорировать коммиты, у которых subject начинается с `docs:` / `chore:` и тронуты только `*.md` файлы.
   - Или: требовать хотя бы 1 .py LOC в коммите для auto-close.

4. **Обновить project memory** `callback-false-done-pattern.md` — добавить 4-й корень (renumbering commits) и сценарий `f41903f`.

---

## Out of Scope (не делал, потому что /qa)

- `pytest scripts/vps/tests/test_lifecycle.py` (на ветке) — это работа `/tester`.
- Code review модуля `lifecycle.py` — это работа `/review` или `/audit`.
- Запуск `migrate_backlog_to_lifecycle.py --dry-run` — скрипт не существует.
