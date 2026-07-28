# Bug: [BUG-218] Переход `queued → in_progress` не выполняется никогда

**Priority:** P1 | **Risk:** R1 | **Date:** 2026-07-28

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Статус `in_progress` не пишет **никто**. Не «сломалось» — не было реализовано ни разу.

Живое доказательство, снятое 2026-07-28: спека TECH-212 работала в pueue 1026 пятьдесят
две минуты, а её lifecycle-yaml всё это время читался как

```yaml
status: queued
pueue_id: null
started_at: null
updated_by: spark
```

Проверка по коду, а не по симптому. Продовых вызовов `write_lifecycle` ровно четыре:

| Файл:строка | Пишет |
|---|---|
| `callback.py:1338` | `done` / `blocked` |
| `lifecycle.py:894` (`reconcile_orphans`) | `queued` |
| `orchestrator.py:928` (reconciliation gate) | `done` |
| `spec_operator.py:86` | то, что задал оператор |

`grep -rn "in_progress" --include=*.py` по всему дереву даёт только перечисления enum,
читателей и тесты. Писателей — ноль.

`orchestrator.scan_queued:961-972` после успешного `_pueue_add` пишет **только в SQLite**
(`try_acquire_slot`, `log_task`, `update_project_phase`) и молча уходит:

```python
    db.try_acquire_slot(project_id, provider, pueue_id)
    db.log_task(project_id, task_label, "autopilot", "running", pueue_id,
                branch=f"feature/{spec_id}")
    db.update_project_phase(project_id, "autopilot", spec_id)
    log.info("autopilot submitted: %s spec=%s pueue_id=%d", project_id, spec_id, pueue_id)
    return True
```

### Что это ломает (цепочка проверена по коду)

| Потребитель | Почему мёртв |
|---|---|
| `lifecycle.py:254-259` | `started_at` штампуется **только** на переходе `queued\|resumed → in_progress`. Перехода нет → поле `null` у всех спек навсегда |
| `lifecycle.reconcile_orphans:886` | ищет `list_by_status(repo, "in_progress")` для восстановления после краха → множество всегда пусто → **аварийное восстановление не работает ни разу** |
| `gate-daemon.py:182` | читает `{"in_progress", "queued"}` — половина условия всегда пуста |
| `lifecycle.recover_false_reconciliation:1059-1066` | два из пяти критериев (`pueue_id is None`, `started_at is None`) не могут отличить «никогда не запускалась» от «запускалась, но мы не записали» — они не отвергают ничего |
| `docs/orchestrator/runbook.md:90` | сценарий «Спека застряла in_progress, pueue пуст» описывает состояние, которого не бывает |
| Наблюдаемость | час работы агента в `backlog.md` и в аудите выглядит как «в очереди» |

### Почему это не заметили раньше

`docs/orchestrator/README.md:134` называет писателя:

> `queued/resumed → in_progress` | поля `started_at` ставятся при записи; диспатч — orchestrator, **запись — callback**

Назначенный писатель структурно не может это написать: callback срабатывает на
**завершении** pueue-задачи, когда статус уже `done` или `blocked`. Документация назначила
ответственным того, кто в нужный момент не запускается, и на этом проверка кончилась.

`git log -S'"in_progress"' -- scripts/vps/orchestrator.py` даёт один коммит — `df1bdb6`
(TECH-195), добавивший строку в список валидных статусов. Записи не было никогда,
регрессии нет.

### Второй дефект — латентный, активируется первым

`orchestrator.get_live_pueue_ids:111-112` намеренно различает «ошибка» и «пусто»:

```python
def get_live_pueue_ids() -> set[int] | None:
    """Return live pueue task IDs. None on failure (skip watchdog, no false release)."""
```

`startup_reconcile:581` это различение уничтожает:

```python
    alive = get_live_pueue_ids() or set()
```

`None` схлопывается в пустое множество, и `reconcile_orphans` получает «живых задач нет».
Сегодня безвредно — демоутить нечего. **После первого фикса это становится массовым
демоутом живой работы при любом сбое `pueue status`.** Поэтому обе правки обязаны уехать
одним изменением: отдельно первая — регрессия.

---

## Scope

**In scope:** запись `in_progress` при диспатче; fail-closed в `startup_reconcile`;
исправление контракта переходов в трёх файлах `docs/orchestrator/`.

**Out of scope:** снятие `SHADOW_ONLY_MODE` в `gate-daemon.py` (Wave 3, не авторизован);
пересмотр критериев `recover_false_reconciliation` (после фикса они начинают
дискриминировать сами); перенос `started_at` в callback (он читает своё из SQLite
`task_log`, см. ниже); раскол `orchestrator.py` (это TECH-215).

**Что НЕ сломано и трогать не надо.** `callback._get_started_at:575-587` берёт `started_at`
из SQLite `task_log`, а не из lifecycle-yaml. Implementation guard и `_detect_out_of_scope_files`
работают корректно и от этого бага не зависят. Спека не должна их «чинить».

---

## Impact Tree Analysis

### Step 1: UP — who uses? (греп от корня репозитория, не от `scripts/vps/`)

```
grep -rn "scan_queued\|startup_reconcile" --include=*.py .
```

| Потребитель | Природа |
|---|---|
| `scripts/vps/tests/test_orchestrator.py` | 13 вызовов `scan_queued`, **10 из них happy-path** (`assert result is True`) |
| `scripts/vps/tests/test_autopilot_scope_guard.py:87-112` | читает **исходник** `scan_queued` как текст, ищет `pueue_env` — правки тела не ломают, пока `env=pueue_env` остаётся |
| `scripts/vps/tests/test_orchestrator_lifecycle.py` | зовёт `lifecycle.reconcile_orphans` напрямую, не `startup_reconcile` — не затрагивается |

**Корневой `tests/` не содержит ни одного вызова** — иммутабельный regression-корпус
(`tests/regression/`, `tests/contracts/`) не задет. Проверено грепом от корня; ровно эта
проверка была пропущена в TECH-210 и дала блокер.

### Step 2: DOWN — what depends on?

`scan_queued` уже импортирует `lifecycle` и вызывает `lifecycle.write_lifecycle` на строке
928 (reconciliation gate). Новых зависимостей не появляется. `orchestrator ∈ _ALLOWED_WRITERS`
(`lifecycle.py:59`) — identity gate пройден без изменений.

### Step 3: BY TERM — grep entire project

| Файл | Строка | Что | Действие |
|---|---|---|---|
| `docs/orchestrator/README.md` | 134 | «запись — callback» — ложь | **исправить** |
| `docs/orchestrator/status-model.md` | 70 | «orchestrator пишет статус в двух местах» — станет в трёх | **исправить** |
| `docs/orchestrator/components.md` | 44, 196 | crash recovery через `reconcile_orphans` — описание станет правдой | **дополнить** инвариантом диспатча |
| `docs/orchestrator/runbook.md` | 90-113 | сценарий «застряла in_progress» — станет достижим | не трогать: текст уже верен для починенной системы |
| `CLAUDE.md` | 367 | `Default Flow: queued → in_progress → done` | не трогать: фикс делает эту строку правдой |
| `scripts/vps/audit_probe.py` | 107 | `valid_statuses` содержит `in_progress` | не трогать |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — новый `test_orchestrator_in_progress.py` + правка 10 happy-path тестов
- [x] `tests/regression/`, `tests/contracts/` — **не затронуты** (Step 1)
- [x] `db/migrations/**` — в проекте нет
- [x] `ai/glossary/**` — не существует

### Step 5: DUAL SYSTEM — кто читает из старого/нового

Источников состояния действительно два, и это не устраняется здесь:

| Система | Что держит | Кто читает |
|---|---|---|
| SQLite (`task_log`, `compute_slots`, `project_state`) | рантайм-факт запуска, `started_at` для guard | `callback`, `orchestrator_monitor` |
| git yaml (`ai/lifecycle/`) | статус-SoT (ADR-023) | `orchestrator`, `gate-daemon`, `render_backlog`, `lifecycle_audit`, оператор |

Баг в том, что диспатч писал только в первую. Фикс синхронизирует их в точке диспатча;
слияние систем — не задача этой спеки.

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] Корневой `tests/` проверен грепом от корня и чист
- [x] `orchestrator` уже в `_ALLOWED_WRITERS` — новых прав не требуется

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/orchestrator.py` — запись `in_progress` в `scan_queued` + fail-closed в `startup_reconcile` (modify)
- `scripts/vps/tests/test_orchestrator_in_progress.py` — регрессионные тесты обоих дефектов (NEW)
- `scripts/vps/tests/test_orchestrator.py` — 10 happy-path тестов получают явный патч `write_lifecycle` (modify)
- `docs/orchestrator/README.md` — строка 134 таблицы переходов (modify)
- `docs/orchestrator/status-model.md` — «в двух местах» → «в трёх» (modify)
- `docs/orchestrator/components.md` — инвариант диспатча (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — запись статуса не смеет отменять уже совершённый диспатч
**Data model:** `ai/lifecycle/*.yaml` — поля `status`, `pueue_id`, `started_at`, `transitions`

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

---

## Approaches

### Approach 1: писать `in_progress` ПОСЛЕ успешного `_pueue_add` (выбран)
**Summary:** одна запись, сразу с настоящим `pueue_id`.
**Pros:** `pueue_id` известен и попадает в yaml — именно он нужен `reconcile_orphans`;
если запись падает, задача уже в очереди и продолжает работать.
**Cons:** окно между `_pueue_add` и записью. Крах внутри него оставит спеку в `queued` при
живой задаче.
**Почему окно безопасно:** `pueue_has_active_label:883` не даст передиспатчить ту же спеку,
пока задача жива. То есть окно воспроизводит ровно сегодняшнее поведение и ничего не ухудшает.

### Approach 2: писать `in_progress` ДО `_pueue_add`
**Summary:** CAS-запись как распределённый захват спеки между узлами.
**Pros:** закрывает multi-master гонку строже.
**Cons:** `pueue_id` ещё не существует → пишется `null` → на следующем старте
`reconcile_orphans:890` увидит `pueue_id is None`, не найдёт совпадения в живых и
демоутнет живую спеку. Лечится второй записью — две git-коммит-операции на диспатч.
Плюс отказ `_pueue_add` оставляет `in_progress` на незапущенной спеке.

### Approach 3: писать из `claude-runner` в начале сессии
**Cons:** `_ALLOWED_WRITERS` не содержит `autopilot`, и это сознательное решение ADR-025.
Потребовало бы ослабить identity gate ради наблюдаемости.

### Selected: 1
**Rationale:** единственный вариант, где `pueue_id` попадает в yaml одной записью, а
неудачная запись не может навредить уже запущенной работе.

---

## Design

### Правка 1 — `scan_queued`, сразу после блока записи в SQLite

```python
    db.update_project_phase(project_id, "autopilot", spec_id)
    # Lifecycle SoT must show the spec is running (ADR-023). Without this the
    # documented queued → in_progress → done flow never happens: started_at stays
    # null forever and reconcile_orphans has nothing to reconcile.
    #
    # After _pueue_add, never before: the yaml needs the real pueue_id, and
    # reconcile_orphans keys crash recovery on it.
    #
    # A failed write must NEVER unwind the dispatch — the task is already queued
    # in pueue and will run regardless. Worst case we degrade to today's
    # behaviour (status stays queued), which pueue_has_active_label already
    # tolerates. So: log and continue, never re-raise, never return False.
    try:
        lifecycle.write_lifecycle(
            project_dir,
            spec_id,
            "in_progress",
            by="orchestrator",
            pueue_id=pueue_id,
        )
    except lifecycle.LifecycleAlreadyDoneError:
        # Rule 7 (ADR-025): callback closed the spec between the TOCTOU re-check
        # and here. Benign — the run will find nothing to do and exit.
        log.warning("in_progress skipped: %s already done (race)", spec_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("in_progress write failed for %s (dispatch stands): %s", spec_id, exc)
    log.info("autopilot submitted: %s spec=%s pueue_id=%d", project_id, spec_id, pueue_id)
    return True
```

Широкий `except` здесь — осознанный, а не небрежность: любое исключение из git-плюмбинга
(CAS-гонка, таймаут, недоступный remote) не должно превращаться в отказ от уже
совершённого диспатча. Тот же приём, что в `reconciliation gate:940-943`, но там отказ
допустим, а тут — нет.

### Правка 2 — `startup_reconcile`, fail-closed

```python
def startup_reconcile() -> None:
    """One-shot at daemon boot: assert clean lifecycle WT + reconcile orphans.

    For every project, abort if ai/lifecycle/ working-tree is dirty (uncommitted
    drift = data loss risk). Then demote any in_progress lifecycle whose
    pueue_id is not alive (crash recovery).
    """
    # get_live_pueue_ids returns None on failure and an empty set when pueue is
    # genuinely idle — the distinction is the whole point of its contract. Folding
    # None into set() (`or set()`, until BUG-218) made an unreachable pueue look
    # like "nothing is running", which demotes every live spec. Harmless while
    # nothing was ever in_progress; a mass-demote of running work now that specs
    # actually reach that status.
    alive = get_live_pueue_ids()
    if alive is None:
        log.warning("startup_reconcile: pueue status unavailable — skipping orphan reconciliation")
    for proj in db.get_all_projects():
        pdir = proj["path"]
        if not os.path.isdir(os.path.join(pdir, "ai", "lifecycle")):
            continue
        cleanup_stale_stashes(pdir)
        lifecycle.assert_clean_lifecycle_tree(pdir)  # raises on dirty
        if alive is None:
            continue
        reconciled = lifecycle.reconcile_orphans(pdir, alive)
        ...
```

Пропуск **узкий**: `assert_clean_lifecycle_tree` и `cleanup_stale_stashes` продолжают
работать при недоступном pueue — это стартовые проверки целостности, они от pueue не зависят.
Не выполняется только демоут.

### Правка 3 — документация

| Файл | Было | Стало |
|---|---|---|
| `README.md:134` | `диспатч — orchestrator, запись — callback` | `диспатч и запись — orchestrator (scan_queued, после pueue add, by=orchestrator)` |
| `README.md:127` | заголовок таблицы «пишет только `callback`/`operator`» | добавить `orchestrator` |
| `status-model.md:70` | «`orchestrator` пишет статус в **двух** местах» | «в **трёх** местах», третьим пунктом — диспатч `in_progress` с `pueue_id` |
| `components.md` | инвариантов диспатча про статус нет | добавить: «диспатч обязан оставить `in_progress` + `pueue_id` в lifecycle; отказ записи не отменяет диспатч» |

---

## Implementation Plan

> **Verified against HEAD `1003bb0` 2026-07-28.** Все номера строк фактические.
> Baseline: `cd scripts/vps/tests && python3 -m pytest -q` — снять перед началом и
> сверить в конце. На Windows-машине автора было 445 passed; на VPS число своё
> (SIGTERM-тест пропускается только на `nt`), поэтому фиксируется **дельта**, не абсолют.

### Drift Log — пересверка с HEAD `384244d` (autopilot PHASE 1, 2026-07-28)

Baseline на VPS: **487 passed** (не 445 — машина другая). Фиксируется дельта.

Все номера строк в `orchestrator.py` (961–972, 581, 922–928), все шесть сигнатур
`lifecycle.py`, фикстура `tmp_git_repo`, все шесть patch-таргетов, `orchestrator ∈
_ALLOWED_WRITERS` (`lifecycle.py:59`), `README.md:134`, `status-model.md:70` и десять
строк `assert result is True` — **точны**. Премиса бага перепроверена грепом: писателей
`in_progress` в проде по-прежнему ноль. Расходится следующее:

| # | Claimed | Actual | Действие |
|---|---|---|---|
| D1 | Task 4: десять тестов получают патч `write_lifecycle` | **Три из них (`:954`, `:989`, `:1144`) уже патчат его как `mock_write` и ассертят `mock_write.assert_not_called()`** на строках 956, 991, 1146 | **Блокер.** После Task 2 эти три падают. Нужна правка *ассерции*, а не добавление патча |
| D2 | Порядок Task 2 → 3 → 4 | Три падающих теста проедут через два коммита | Правка D1 переносится **внутрь Task 2** |
| D3 | «Ровно 10 тестов изменено» | Мест правки **8**: строки 1238/1253/1282 делят хелпер `_dispatch` (`test_orchestrator.py:1196–1225`) | Task 4 правит 5 мест (637, 726, 842, 1179, хелпер) |
| D4 | AV-S2 cap `≤ 1090` (было 1078, «+12 допустимо») | Комментарные блоки самого § Design дают **+35** → ~1113 | Cap поднимается до **≤ 1120** |
| D5 | `README.md:127` — подзаголовок таблицы | Фактически строка **129** | Правится 129 |
| D6 | — (не отмечено) | `README.md:151` (Контракт A, п.1): «Статус пишет только `callback`» — ложь уже сегодня (reconciliation gate пишет `done` by=orchestrator) | Добавляется в Task 5 |
| D7 | `components.md`: три `-` буллета в инварианты | Секция `## Инварианты диспатча` (строка 193) — **нумерованный список 1–14** | Добавить как `15.`/`16.`/`17.`; секцию искать **по заголовку**, не по номеру строки (BUG-217 правит этот файл параллельно) |
| D8 | Task 1 `_dispatch` — шесть патчей | `scan_queued:804` читает `SCRIPT_DIR / "callback-audit.jsonl"`, а файл в воркtree **существует** → тест негерметичен | Добавить `patch("orchestrator.SCRIPT_DIR", repo)` |
| D9 | Косметика | ctor-указатель `lifecycle.py:75-95` → **77–100**; Impact Tree `components.md:196` → **207**; «цикл CAS-ретраев» в Task 4 Context — на деле один `FileNotFoundError` (в `tmp_path` нет `.git`), стоимость ~3 спавна git, а не ретраи | Действие не меняется |

**D1 подробнее.** Правка ассерций — это *усиление*, а не ослабление: `assert_not_called()`
заменяется на проверку, что запись состоялась именно с теми аргументами:

```python
mock_write.assert_called_once()
assert mock_write.call_args[0][2] == "in_progress"
assert mock_write.call_args[1]["by"] == "orchestrator"
```

Acceptance Task 4 «ни одна ассерция не ослаблена» этим не нарушается, но формулировка
авторизует правку явно, иначе кодер упрётся в собственный гейт.

**Итоговый порядок с учётом дрейфа:**

```
Task 1 ──▶ Task 2 ──▶ Task 3 ──▶ Task 4 ──▶ Task 5
(тесты)   (запись     (fail-     (5 мест   (доки:
          + D1: три    closed)    патча)    129, 134, 151,
          ассерции)                          status-model, 15–17)
```

### Порядок относительно TECH-215 — жёсткая зависимость

TECH-215 переносит **обе** правящиеся здесь функции: `scan_queued` → `orchestrator_queue.py`,
`startup_reconcile` → `orchestrator_backlog.py`, и правит тот же `test_orchestrator.py`.
Если TECH-215 отработает первой, Allowed Files этой спеки (`scripts/vps/orchestrator.py`)
перестанут покрывать нужный код, и фикс станет неприменим без переработки.

Порядок сортировки (`list_by_status:724` сортирует по имени, `BUG-218` идёт раньше любого
`TECH-*`) даёт нужный результат, но неявно: одна отправка BUG-218 в `blocked` — и гарантия
исчезает. Поэтому зависимость записана явно:

```
| TECH-215 | queued | tech | ... | [spec](...) — AFTER BUG-218 |
```

`_unmet_dependencies` (`orchestrator.py:758`) будет пропускать TECH-215 в `DEP_GATE`, пока
эта спека не `done`. Направление именно такое — маленький фикс вперёд: у TECH-215 есть
фаза Drift Log, которая переcверяет номера строк с HEAD и поглотит +12 строк, а обратный
порядок потребовал бы переписывать BUG-218 целиком.

---

### Task 1: Регрессионные тесты обоих дефектов (СТРОГО ПЕРВАЯ)

**Type:** test
**Files:**
  - create: `scripts/vps/tests/test_orchestrator_in_progress.py`

**Context.** Пишутся против **неизменённого** `orchestrator.py`. Тесты на запись
`in_progress` обязаны на этом шаге **падать** — это и есть доказательство, что баг есть,
а не что тест удобно сформулирован. Тест на `startup_reconcile` обязан падать тоже.

Фикстура `tmp_git_repo` копируется дословно из `test_orchestrator_lifecycle.py:25-46`
(реальный git-репозиторий, ADR-013, без моков).

**Step 1: шапка и фикстуры.**

```python
"""BUG-218 — переход queued → in_progress выполняется при диспатче.

Написаны ДО фикса: тесты класса TestDispatchWritesInProgress обязаны падать на
неизменённом orchestrator.py. Тест TestStartupReconcileFailClosed тоже.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import orchestrator  # noqa: E402


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Реальный git-репозиторий — приём из test_orchestrator_lifecycle.py:25."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(["git"] + list(args), cwd=str(repo), check=True,
                       capture_output=True, text=True)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    (repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
    git("add", ".")
    git("commit", "-m", "init")
    return repo


def _dispatch(repo, spec_id, pueue_id=42):
    """Прогнать scan_queued до конца happy-path на реальном репозитории."""
    (repo / "ai" / "features" / f"{spec_id}-x.md").write_text("# spec\n", encoding="utf-8")
    with (
        patch("orchestrator.pueue_has_active_label", return_value=False),
        patch("orchestrator.pueue_has_active_spec", return_value=False),
        patch("orchestrator.db.get_available_slots", return_value=1),
        patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
        patch("orchestrator._pueue_add", MagicMock(return_value=pueue_id)),
        patch("orchestrator.db.try_acquire_slot"),
        patch("orchestrator.db.log_task"),
        patch("orchestrator.db.update_project_phase"),
        patch("orchestrator.gate_logic.parse_allowed_files", return_value=[]),
    ):
        return orchestrator.scan_queued("testproject", str(repo))
```

`parse_allowed_files` возвращает `[]`, чтобы reconciliation gate (`:923`) не сработал —
он тестируется отдельно в `TestReconciliationGate` и здесь только мешает.

**Step 2: класс `TestDispatchWritesInProgress` — ядро (EC-1..EC-4).**

```python
class TestDispatchWritesInProgress:
    def test_status_becomes_in_progress(self, tmp_git_repo):
        """EC-1: после диспатча lifecycle читается как in_progress."""
        lifecycle.create_initial(tmp_git_repo, "TECH-901", "p1", "tech")
        assert _dispatch(tmp_git_repo, "TECH-901") is True
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-901")["status"] == "in_progress"

    def test_pueue_id_recorded(self, tmp_git_repo):
        """EC-2: pueue_id попадает в yaml — на нём висит crash recovery."""
        lifecycle.create_initial(tmp_git_repo, "TECH-902", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-902", pueue_id=1026)
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-902")["pueue_id"] == 1026

    def test_started_at_stamped(self, tmp_git_repo):
        """EC-3: lifecycle.py:254-259 наконец срабатывает."""
        lifecycle.create_initial(tmp_git_repo, "TECH-903", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-903")
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-903")["started_at"] is not None

    def test_writer_identity_is_orchestrator(self, tmp_git_repo):
        """EC-4: by=orchestrator — не callback, не spark."""
        lifecycle.create_initial(tmp_git_repo, "TECH-904", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-904")
        d = lifecycle.read_lifecycle(tmp_git_repo, "TECH-904")
        assert d["updated_by"] == "orchestrator"
        assert d["transitions"][-1]["from"] == "queued"
        assert d["transitions"][-1]["to"] == "in_progress"
```

**Step 3: класс `TestWriteFailureNeverUnwindsDispatch` (EC-5, EC-6).** Самая важная пара —
она защищает инвариант «запись не отменяет диспатч».

```python
class TestWriteFailureNeverUnwindsDispatch:
    def test_cas_race_still_returns_true(self, tmp_git_repo):
        """EC-5: CAS исчерпал ретраи → диспатч всё равно состоялся."""
        lifecycle.create_initial(tmp_git_repo, "TECH-905", "p1", "tech")
        boom = lifecycle.LifecycleWriteRaceError("TECH-905", 5)
        with patch.object(orchestrator.lifecycle, "write_lifecycle", side_effect=boom):
            assert _dispatch(tmp_git_repo, "TECH-905") is True

    def test_already_done_still_returns_true(self, tmp_git_repo):
        """EC-6: Rule 7 (callback закрыл спеку в гонке) не откатывает диспатч."""
        lifecycle.create_initial(tmp_git_repo, "TECH-906", "p1", "tech")
        boom = lifecycle.LifecycleAlreadyDoneError(
            spec_id="TECH-906", attempted="in_progress", by="orchestrator"
        )
        with patch.object(orchestrator.lifecycle, "write_lifecycle", side_effect=boom):
            assert _dispatch(tmp_git_repo, "TECH-906") is True
```

> Сигнатуры конструкторов обоих исключений сверить с `lifecycle.py:75-95` перед
> написанием — если они отличаются, использовать фактические. Тест не должен падать
> на способе создания исключения.

**Step 4: класс `TestOrphanRecoveryNowWorks` (EC-7) — доказательство, ради чего всё.**

```python
class TestOrphanRecoveryNowWorks:
    def test_dispatched_spec_is_reconcilable_after_crash(self, tmp_git_repo):
        """EC-7: сквозной сценарий — диспатч, смерть pueue, восстановление.

        До BUG-218 reconcile_orphans не находил кандидатов НИКОГДА: список
        in_progress был пуст по построению.
        """
        lifecycle.create_initial(tmp_git_repo, "TECH-907", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-907", pueue_id=777)
        # задача умерла — её id больше не среди живых
        reconciled = lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids=set())
        assert "TECH-907" in reconciled
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-907")["status"] == "queued"

    def test_live_task_is_not_demoted(self, tmp_git_repo):
        """Обратная сторона: живую задачу восстановление не трогает."""
        lifecycle.create_initial(tmp_git_repo, "TECH-908", "p1", "tech")
        _dispatch(tmp_git_repo, "TECH-908", pueue_id=778)
        assert lifecycle.reconcile_orphans(tmp_git_repo, pueue_alive_ids={778}) == []
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-908")["status"] == "in_progress"
```

**Step 5: класс `TestStartupReconcileFailClosed` (EC-8, EC-9).**

```python
class TestStartupReconcileFailClosed:
    def test_pueue_unavailable_demotes_nothing(self, tmp_git_repo):
        """EC-8: get_live_pueue_ids() is None → ни одного демоута.

        Это регрессия, которую вносит сам фикс: `or set()` превращал отказ pueue
        в "живых нет" и снёс бы всю работающую очередь.
        """
        lifecycle.write_lifecycle(tmp_git_repo, "TECH-909", "in_progress", pueue_id=999)
        with (
            patch("orchestrator.get_live_pueue_ids", return_value=None),
            patch("orchestrator.db.get_all_projects",
                  return_value=[{"project_id": "t", "path": str(tmp_git_repo)}]),
            patch("orchestrator.lifecycle.assert_clean_lifecycle_tree"),
            patch("orchestrator.cleanup_stale_stashes"),
            patch.object(orchestrator.lifecycle, "reconcile_orphans") as mock_rec,
        ):
            orchestrator.startup_reconcile()
        mock_rec.assert_not_called()
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-909")["status"] == "in_progress"

    def test_empty_set_still_reconciles(self, tmp_git_repo):
        """EC-9: пустое множество — это НЕ ошибка. pueue жив и пуст → демоут идёт."""
        lifecycle.write_lifecycle(tmp_git_repo, "TECH-910", "in_progress", pueue_id=998)
        with (
            patch("orchestrator.get_live_pueue_ids", return_value=set()),
            patch("orchestrator.db.get_all_projects",
                  return_value=[{"project_id": "t", "path": str(tmp_git_repo)}]),
            patch("orchestrator.lifecycle.assert_clean_lifecycle_tree"),
            patch("orchestrator.cleanup_stale_stashes"),
        ):
            orchestrator.startup_reconcile()
        assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-910")["status"] == "queued"

    def test_integrity_checks_still_run_when_pueue_is_down(self, tmp_git_repo):
        """Пропуск узкий: проверка чистоты WT от pueue не зависит."""
        with (
            patch("orchestrator.get_live_pueue_ids", return_value=None),
            patch("orchestrator.db.get_all_projects",
                  return_value=[{"project_id": "t", "path": str(tmp_git_repo)}]),
            patch("orchestrator.cleanup_stale_stashes"),
            patch.object(orchestrator.lifecycle, "assert_clean_lifecycle_tree") as mock_assert,
        ):
            orchestrator.startup_reconcile()
        mock_assert.assert_called_once()
```

**Step 6: прогон на НЕИЗМЕНЁННОМ `orchestrator.py` (EC-10).**

```bash
cd scripts/vps/tests
python3 -m pytest test_orchestrator_in_progress.py -q
```

Ожидание: **красный**. Падают все тесты `TestDispatchWritesInProgress`,
`TestOrphanRecoveryNowWorks`, плюс `test_pueue_unavailable_demotes_nothing`.
Зелёными обязаны быть `TestWriteFailureNeverUnwindsDispatch` (сегодня записи нет — она
не может и упасть) и `test_empty_set_still_reconciles`.

Если что-то из «обязано падать» проходит — тест не проверяет то, что заявлено; чинить
тест, не переходить к Task 2.

**Acceptance:**
- [ ] Файл создан, ≤ 600 LOC
- [ ] Прогон на неизменённом `orchestrator.py` красный ровно в ожидаемых местах (EC-10)
- [ ] Зафиксировать вывод прогона в коммит-сообщении Task 1
- [ ] `git diff scripts/vps/orchestrator.py` пуст после Task 1

---

### Task 2: Запись `in_progress` при диспатче

**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.py`

**Step 1.** Вставить блок из § Design «Правка 1» между `db.update_project_phase(...)`
(строка 970) и `log.info("autopilot submitted: ...")` (строка 971).

**Step 2.** Порядок вызовов внутри блока не менять: сначала три записи в SQLite, затем
lifecycle, затем лог. `log.info` об успешном диспатче обязан остаться **последним** — он
маркер завершённого диспатча в логах, по нему читается VPS.

**Step 3.** `return True` не трогать. Ни одна ветка нового блока не смеет вернуть `False`.

**Step 4: проверка.**

```bash
python3 -m py_compile scripts/vps/orchestrator.py
cd scripts/vps/tests
python3 -m pytest test_orchestrator_in_progress.py -q     # TestStartupReconcileFailClosed ещё красный
python3 -m pytest test_orchestrator.py -q
```

**Acceptance:**
- [ ] `TestDispatchWritesInProgress` и `TestOrphanRecoveryNowWorks` зелёные (EC-1..EC-4, EC-7)
- [ ] `TestWriteFailureNeverUnwindsDispatch` зелёный (EC-5, EC-6)
- [ ] `test_pueue_unavailable_demotes_nothing` всё ещё **красный** — это Task 3
- [ ] `grep -c "return False" scripts/vps/orchestrator.py` не вырос
- [ ] `test_autopilot_scope_guard.py` зелёный — `env=pueue_env` в `_pueue_add` цел

---

### Task 3: Fail-closed в `startup_reconcile`

**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.py`

**Step 1.** Заменить `alive = get_live_pueue_ids() or set()` (строка 581) на форму из
§ Design «Правка 2»: вызов без `or set()`, предупреждение при `None`, `continue` перед
`reconcile_orphans` внутри цикла.

**Step 2.** `assert_clean_lifecycle_tree` и `cleanup_stale_stashes` обязаны остаться **до**
проверки на `None` — они от pueue не зависят и на старте нужны всегда.

**Step 3: проверка.**

```bash
cd scripts/vps/tests
python3 -m pytest test_orchestrator_in_progress.py test_orchestrator_lifecycle.py -q
python3 -m pytest -q
```

**Acceptance:**
- [ ] Все три теста `TestStartupReconcileFailClosed` зелёные (EC-8, EC-9)
- [ ] `test_orchestrator_lifecycle.py` зелёный и **не изменён**
- [ ] `grep -c "get_live_pueue_ids() or set()" scripts/vps/orchestrator.py` = 0 (EC-11)

---

### Task 4: 10 happy-path тестов получают явный патч записи

**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_orchestrator.py`

**Context.** В этих тестах `tmp_path` — обычная временная директория, **не git-репозиторий**
(`seed_project` наполняет только SQLite, `conftest.py:41-56`). После Task 2 каждый успешный
диспатч будет звать `write_lifecycle` на не-репозитории: исключение поглотится, тест
останется зелёным, но каждый прогон потратит цикл CAS-ретраев на заведомо провальные
git-команды. Тихая деградация скорости — чинится явным патчем.

**Step 1.** Тесты с `assert result is True` — строки **637, 726, 842, 954, 989, 1144,
1179, 1238, 1253, 1282** (10 штук). В каждый добавить в стек патчей:

```python
patch.object(orchestrator.lifecycle, "write_lifecycle"),
```

**Step 2.** Тесты, где `result is False`, **не трогать** — до записи они не доходят.

**Step 3.** Стиль патчей внутри каждого теста не менять: где вложенные `with` — добавить
уровень, где кортеж в скобках — добавить строку. Переписывание чужого стиля не входит в задачу.

**Step 4: проверка.**

```bash
cd scripts/vps/tests
python3 -m pytest test_orchestrator.py -q
python3 -m pytest -q
```

**Acceptance:**
- [ ] Ровно 10 тестов изменено, число тестов в файле не изменилось
- [ ] `python3 -m pytest -q` — дельта только на новые тесты Task 1, 0 failed
- [ ] Ни одна ассерция существующих тестов не ослаблена

---

### Task 5: Документация контракта переходов

**Type:** docs
**Files:**
  - modify: `docs/orchestrator/README.md`
  - modify: `docs/orchestrator/status-model.md`
  - modify: `docs/orchestrator/components.md`

**Step 1: `README.md:127`** — подзаголовок таблицы переходов. Было «пишет только
`callback`/`operator`», стало — с `orchestrator`.

**Step 2: `README.md:134`** — строка перехода:

```markdown
| `queued/resumed → in_progress` | orchestrator `scan_queued` после `pueue add`: `write_lifecycle(..., "in_progress", by="orchestrator", pueue_id=<id>)`; `started_at` ставится этим переходом |
```

Добавить под таблицей одно предложение: до BUG-218 переход был документирован за
callback'ом и не выполнялся — callback срабатывает на завершении задачи и в этот момент
пишет уже `done`/`blocked`.

**Step 3: `status-model.md:70`** — «в двух местах» → «в трёх», третьим пунктом:

```markdown
- **диспатч** в `scan_queued` — после успешного `pueue add` пишет `in_progress` с `pueue_id`.
  Отказ этой записи логируется и НЕ отменяет диспатч: задача уже в очереди pueue.
  Это единственная запись `in_progress` во всей системе — она включает `started_at`
  (`lifecycle.py:254-259`) и делает `reconcile_orphans` работоспособным.
```

**Step 4: `components.md`** — в инварианты диспатча:

```markdown
- **Диспатч обязан оставить след в SoT.** После `pueue add` статус спеки — `in_progress`
  с записанным `pueue_id`. Без этого `reconcile_orphans` не видит кандидатов, а `started_at`
  остаётся null навсегда (BUG-218).
- **Запись статуса не отменяет диспатч.** Любой отказ `write_lifecycle` на этом пути —
  WARNING в лог, не `return False`.
- **`startup_reconcile` fail-closed.** `get_live_pueue_ids() is None` (pueue недоступен) —
  восстановление пропускается целиком. Демоут по предположению снёс бы живую очередь.
```

**Acceptance:**
- [ ] `grep -n "запись — callback" docs/orchestrator/README.md` = 0
- [ ] `grep -n "в двух местах" docs/orchestrator/status-model.md` = 0
- [ ] Три инварианта в `components.md` присутствуют

---

### Execution Order

```
Task 1 ──▶ Task 2 ──▶ Task 3 ──▶ Task 4 ──▶ Task 5
(тесты)   (запись)   (fail-closed)  (моки)   (доки)
```

Строго последовательно. **Task 1 первая и не переставляется:** её ценность в красном
прогоне до фикса. Написанная после Task 2, она зафиксирует то, что получилось, а не то,
что требовалось.

Task 3 не откладывается на потом: после Task 2 система входит в состояние, где сбой
`pueue status` на старте демоутит живую очередь. Между Task 2 и Task 3 деплоя быть не может.

**Один коммит на задачу.**

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Диспатч пишет статус | `scan_queued` happy-path на реальном репо | `status == "in_progress"` | deterministic | orchestrator.py:961-972 | P0 |
| EC-2 | `pueue_id` в yaml | диспатч с `pueue_id=1026` | `pueue_id == 1026` | deterministic | reconcile_orphans:889 | P0 |
| EC-3 | `started_at` проставлен | диспатч | `started_at is not None` | deterministic | lifecycle.py:254-259 | P0 |
| EC-4 | Идентичность писателя | диспатч | `updated_by == "orchestrator"`, transition `queued→in_progress` | deterministic | ADR-025 | P0 |
| EC-5 | CAS-гонка не отменяет диспатч | `write_lifecycle` → `LifecycleWriteRaceError` | `scan_queued` вернул `True` | deterministic | § Design | P0 |
| EC-6 | Rule 7 не отменяет диспатч | `write_lifecycle` → `LifecycleAlreadyDoneError` | `scan_queued` вернул `True` | deterministic | ADR-025 | P0 |
| EC-7 | Восстановление сирот работает | диспатч, затем `reconcile_orphans(alive=set())` | спека в списке, статус `queued` | deterministic | lifecycle.py:886 | P0 |
| EC-8 | pueue недоступен → ноль демоутов | `get_live_pueue_ids() → None` | `reconcile_orphans` не вызван, статус цел | deterministic | orchestrator.py:581 | P0 |
| EC-9 | Пустое множество ≠ ошибка | `get_live_pueue_ids() → set()` | демоут состоялся | deterministic | get_live_pueue_ids:111 | P0 |
| EC-10 | Тесты падают ДО фикса | Task 1 на неизменённом коде | красный в ожидаемых местах | deterministic | Feathers | P0 |
| EC-11 | Свёртка `None` устранена | `grep "get_live_pueue_ids() or set()" scripts/vps/orchestrator.py` | 0 попаданий | deterministic | § Design | P1 |
| EC-12 | Диспатч не научился отказывать | `grep -c "return False" scripts/vps/orchestrator.py` | не больше, чем до правки | deterministic | § Design | P1 |
| EC-13 | Доки не лгут | `grep "запись — callback" docs/orchestrator/README.md` | 0 попаданий | deterministic | README.md:134 | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-14 | Демон перезапущен на VPS, спека в `queued` | дождаться диспатча | `git show origin/develop:ai/lifecycle/<ID>.yaml` → `in_progress` + непустой `pueue_id` | integration | живой инцидент TECH-212 | P0 |
| EC-15 | Спека `in_progress`, pueue остановлен | `systemctl --user restart dld-orchestrator` | в логе `pueue status unavailable — skipping`, статус не изменился | integration | EC-8 | P1 |

### Coverage Summary
Deterministic: 13 | Integration: 2 | LLM-Judge: 0 | Total: 15 (min 3 ✓)

### TDD Order
1. EC-10 — красный прогон до фикса
2. EC-1..EC-4, EC-7 — запись работает
3. EC-5, EC-6, EC-12 — запись не вредит диспатчу
4. EC-8, EC-9, EC-11 — fail-closed
5. EC-13 — доки
6. EC-14, EC-15 — VPS

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Модуль компилируется | `python3 -m py_compile scripts/vps/orchestrator.py` | exit 0 | 15s |
| AV-S2 | Лимит LOC не превышен | `wc -l scripts/vps/orchestrator.py` | ≤ 1090 (был 1078; +12 допустимо, раскол — TECH-215) | 5s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Полный прогон | — | `cd scripts/vps/tests && python3 -m pytest -q` | дельта только на новые тесты, 0 failed |
| AV-F2 | Демон перезапущен | VPS | `systemctl --user restart dld-orchestrator && systemctl --user is-active dld-orchestrator` | `active` |
| AV-F3 | Статус виден живьём | VPS, спека диспатчится | `git show origin/develop:ai/lifecycle/<ID>.yaml` | `status: in_progress`, `pueue_id` непустой, `started_at` непустой |
| AV-F4 | Аудит видит категорию | VPS | `python3 scripts/vps/lifecycle_audit.py --quiet` | exit 0/1, без новых `orphan_yaml` |

> **AV-F2 обязателен.** Демоны держат код в памяти: без рестарта работает старая версия.
> На этом уже потеряли цикл 2026-07-27.

### Verify Command

```bash
python3 -m py_compile scripts/vps/orchestrator.py
grep -c "get_live_pueue_ids() or set()" scripts/vps/orchestrator.py    # 0
grep -c "запись — callback" docs/orchestrator/README.md                 # 0
cd scripts/vps/tests && python3 -m pytest -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `scan_queued` пишет `in_progress` с `pueue_id` после успешного `pueue add`
- [ ] Отказ записи логируется и не отменяет диспатч
- [ ] `startup_reconcile` не демоутит ничего при недоступном pueue

### Tests
- [ ] EC-1..EC-15 проходят
- [ ] Тесты Task 1 написаны ДО фикса и дали красный прогон
- [ ] Существующие тесты не ослаблены

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1 локально
- [ ] AV-F2, AV-F3, AV-F4 на VPS после рестарта демона

### Technical
- [ ] `docs/orchestrator/` описывает фактического писателя
- [ ] Поток `queued → in_progress → done` из CLAUDE.md стал правдой

---

## Autopilot Log
