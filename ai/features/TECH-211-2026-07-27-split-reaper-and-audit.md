# Feature: [TECH-211] Раскол heartbeat_reaper.py и lifecycle_audit.py

**Priority:** P1 | **Date:** 2026-07-27

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Два файла превышают лимит 400 LOC: `heartbeat_reaper.py` (459) и `lifecycle_audit.py` (525).
Оба выбраны первыми среди расколов, потому что у них **ноль программных потребителей** —
`grep -rl "import heartbeat_reaper\|import lifecycle_audit" scripts/vps/` пуст. Ни один
модуль их не импортирует; оба вызываются как самостоятельные скрипты (cron и оператор).
Ошибка здесь не может распространиться по графу импортов.

`research-devil.md` § Conditions for success п.4 рекомендует ровно этот порядок: начинать с
файлов с наименьшим числом потребителей и только потом идти в горячий путь.

## Context

### `heartbeat_reaper.py` (459 LOC) — границы уже написаны автором

В файле есть секционные разделители, поставленные вручную:

| Строка | Комментарий | Содержимое |
|---|---|---|
| 48 | `Pueue helpers` | `get_running_claude_tasks`, `_project_from_command`, `_parse_iso` |
| 136 | `Heartbeat helpers` | `find_heartbeat_file`, `read_heartbeat` |
| 199 | `Process liveness check` | `_find_claude_pid`, `is_process_idle`, `_check_pueue_children_idle`, `_sample_cpu_idle` |
| 315 | `Kill + notify` | `kill_task`, `notify_reap` |
| 356 | `Main reaper logic` | `reap_stale_sessions`, `main` |

Это единственный из восьми файлов, где раскол не требует нового решения о границах —
достаточно взять те, что автор уже провёл.

### `lifecycle_audit.py` (525 LOC) — ноль тестов

`find . -name "test_lifecycle_audit*"` не находит ничего: ни в `scripts/vps/tests/`
(20 файлов), ни в корневом `tests/`. Файл в 525 строк с 14 категориями дрейфа и
функцией `audit_project` на 151 строку не имеет ни одной регрессионной сети.

Это меняет порядок работ: **сначала характеризационные тесты, потом раскол**. Обратный
порядок означает резать вслепую — та же ситуация, что с `list_by_status` 2026-07-27,
только без шанса заметить.

Инструмент READ-ONLY: он ничего не пишет, только читает git и yaml. Это делает
характеризационные тесты дешёвыми — достаточно зафиксировать вывод на подготовленном
репозитории.

---

## Scope

**In scope:** характеризационные тесты для `lifecycle_audit.audit_project` (14 категорий);
раскол обоих файлов на flat sibling-модули; оба файла ≤400 LOC.

**Out of scope:** изменение поведения (обе программы обязаны давать побайтово тот же
вывод); превращение в пакеты; трогать `event_writer.py` (уже под лимитом, вне скоупа).

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "import heartbeat_reaper" .` → **0** программных потребителей
- `grep -rn "import lifecycle_audit" .` → **0** программных потребителей
- `scripts/vps/setup-vps.sh:140,143,144,146` — cron-строка, зашивает абсолютный путь
  `${SCRIPT_DIR}/heartbeat_reaper.py`. Установлена один раз при развёртывании, **не
  перегенерируется по git push**
- `lifecycle_audit.py` вызывается вручную оператором (см. `docs/orchestrator/runbook.md`)

### Step 2: DOWN — what depends on?

```
heartbeat_reaper.py → event_writer (ленивый импорт, строка 340), stdlib
lifecycle_audit.py  → lifecycle (строка 56), stdlib
```

Новых зависимостей не появляется — sibling-модули наследуют те же импорты.

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/setup-vps.sh` | 140-146 | cron на `heartbeat_reaper.py` | **не трогать** — имя файла сохраняется |
| `scripts/vps/heartbeat_reaper.py` | 340 | `from event_writer import notify` | оставить как есть, вне скоупа |
| `scripts/vps/lifecycle_audit.py` | 26 | docstring ссылается на `ai/glossary/orchestrator.md` | директории не существует, предсуществующий дрейф, не чинить здесь |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — `test_heartbeat_reaper.py` существует (326 LOC);
      `test_lifecycle_audit.py` создаётся
- [x] `db/migrations/**` — в проекте нет
- [x] `ai/glossary/**` — не существует

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] Имена `heartbeat_reaper.py` и `lifecycle_audit.py` сохранены — cron не ломается

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/heartbeat_reaper.py` — оставить main + reap, вынести остальное (modify)
- `scripts/vps/reaper_pueue.py` — Pueue helpers (NEW)
- `scripts/vps/reaper_liveness.py` — проверка живости процесса (NEW)
- `scripts/vps/lifecycle_audit.py` — оставить CLI + main, вынести остальное (modify)
- `scripts/vps/audit_probe.py` — git-пробы и парсинг спек (NEW)
- `scripts/vps/audit_categories.py` — 14 категорий дрейфа (NEW)
- `scripts/vps/tests/test_heartbeat_reaper.py` — импорты под новые модули (modify)
- `scripts/vps/tests/test_lifecycle_audit.py` — характеризационные тесты (NEW)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — `lifecycle_audit` READ-ONLY, не смеет писать ни при каких условиях
**Data model:** не затрагивается

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

---

## Approaches

### Approach 1: Flat sibling-модули, имя точки входа сохраняется (выбран)
**Source:** `research-web.md` § Approach 1 и § Best Practice 4
**Summary:** `heartbeat_reaper.py` остаётся исполняемым файлом по тому же пути, его тело
худеет за счёт `import reaper_pueue` / `import reaper_liveness` рядом
**Pros:** cron-строка в `setup-vps.sh` не трогается; соответствует уже существующему
неймингу директории (`orchestrator_monitor.py`, `heartbeat_monitor.py`)
**Cons:** новые модули глобально импортируемы, приватности на уровне языка нет

### Approach 2: Пакет `heartbeat_reaper/__main__.py`
**Source:** `research-web.md` § Approach 2 (отклонён там же)
**Summary:** каталог-пакет с `__init__.py`
**Cons:** воспроизводит инцидент AutoMem (2026-06-09): `python script.py` кладёт в
`sys.path[0]` каталог самого скрипта, и cron-строка с зашитым путём перестаёт
резолвиться. Cron установлен на каждом VPS отдельно и не перегенерируется push'ем

### Selected: 1
**Rationale:** цель — «файл под 400», а не «правильная упаковка». Пакет платит риском
сломать четыре независимые поверхности развёртывания за выгоду, которой в этой
кодовой базе никто не пользуется: ни один вызывающий не делает `from X.y import z`.

---

## Design

### Правило именования и импорта

Новые модули — плоские файлы в той же директории, импортируются как `import reaper_pueue`
и вызываются через атрибут (`reaper_pueue.get_running_claude_tasks(...)`).
**Никаких `from reaper_pueue import ...`** — связанное имя ломает `monkeypatch.setattr`
на модуле, см. `research-devil.md` DA-4.

### `heartbeat_reaper.py` после раскола

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `reaper_pueue.py` | `get_running_claude_tasks`, `_project_from_command`, `_parse_iso` | ~90 |
| `reaper_liveness.py` | `_find_claude_pid`, `is_process_idle`, `_check_pueue_children_idle`, `_sample_cpu_idle` | ~115 |
| `heartbeat_reaper.py` | `find_heartbeat_file`, `read_heartbeat`, `kill_task`, `notify_reap`, `reap_stale_sessions`, `main` | ~250 |

### `lifecycle_audit.py` после раскола

| Модуль | Содержимое | ~LOC |
|---|---|---|
| `audit_probe.py` | `_git`, `_ls_tree`, `_git_dirty`, `_git_divergence`, `_spec_id_from_filename`, `_list_feature_specs`, `_md_status`, `_parse_backlog_columns`, `_read_counter`, `_is_bootstrap_as_done`, `_yaml_writers` | ~160 |
| `audit_categories.py` | тело `audit_project`, разложенное по категориям | ~160 |
| `lifecycle_audit.py` | `audit_project` (тонкая оркестрация), `_load_projects`, `run`, `_print_text`, `main` | ~200 |

`audit_project` — 151 строка в одной функции. Перенос её целиком в другой файл лимит
удовлетворит, а читаемость нет. Она разбирается на функцию-на-категорию в
`audit_categories.py`, а в `lifecycle_audit.py` остаётся сборка результата.

### Порядок для `lifecycle_audit.py`

1. Характеризационные тесты на **текущем** коде — зафиксировать вывод всех 14 категорий
2. Прогнать, убедиться, что зелёные
3. Только потом резать

Шаг 1 не пропускается. Это единственная сеть, которая будет у этого файла.

---

## Implementation Plan

> **Verified against worktree HEAD 2026-07-27.** Все номера строк ниже — фактические.
> `python` НЕ в PATH в этом окружении. Все команды — `python3`.
> Baseline: `cd scripts/vps/tests && python3 -m pytest -q` → **421 passed**.

### Research Sources
- `research-codebase.md` §1 — карта ответственностей обоих файлов с диапазонами строк
- `research-codebase.md` §5 — «нулевое покрытие `lifecycle_audit.py`» — **частично опровергнуто**,
  см. § Проверенные границы ниже
- [The Refactor That Broke Backups for Two Days](https://drunk.support/the-refactor-that-broke-backups-for-two-days/) — почему точка входа не становится пакетом

---

### Проверенные границы (факт, а не память спеки)

**`scripts/vps/heartbeat_reaper.py` — 459 LOC.** Разделители автора подтверждены дословно:

| Разделитель | Заголовок | Функции | Диапазон тела |
|---|---|---|---|
| 48–50 | `Pueue helpers` | `get_running_claude_tasks`, `_project_from_command`, `_parse_iso` | 52–133 |
| 136–138 | `Heartbeat helpers` | `find_heartbeat_file`, `read_heartbeat` | 140–196 |
| 199–201 | `Process liveness check` | `_find_claude_pid`, `is_process_idle`, `_check_pueue_children_idle`, `_sample_cpu_idle` | 203–312 |
| 315–317 | `Kill + notify` | `kill_task`, `notify_reap` | 319–353 |
| 356–358 | `Main reaper logic` | `reap_stale_sessions`, `main` | 360–459 |

Шапка 1–46: docstring, импорты, `SCRIPT_DIR`/`LOG_DIR`, пять констант, `basicConfig`, `log`.

**Привязка констант (кто реально читает):**

| Константа | Читатель | Куда едет |
|---|---|---|
| `GRACE_SECONDS`, `STALE_SECONDS` | `reap_stale_sessions` | остаётся в `heartbeat_reaper.py` |
| `STARTED_AT_TOLERANCE` | `find_heartbeat_file` | остаётся |
| `LOG_DIR`, `SCRIPT_DIR` | `find_heartbeat_file`, `notify_reap` | остаётся |
| `CPU_SAMPLE_SECONDS`, `CPU_IDLE_THRESHOLD` | **только** `_sample_cpu_idle` | → `reaper_liveness.py` |

**`scripts/vps/lifecycle_audit.py` — 525 LOC.** Фактический состав:

| Строки | Имя | Назначение |
|---|---|---|
| 60–75 | `CATEGORIES` | tuple из 14 строк |
| 82–90 | `_git` | обёртка над git |
| 93–98 | `_ls_tree` | |
| 101–106 | `_git_dirty` | |
| 109–120 | `_git_divergence` | |
| 128 | `_SPEC_ID_RE` | **не перечислен в спеке — едет с парсерами** |
| 129 | `_MD_STATUS_RE` | **не перечислен в спеке — едет с парсерами** |
| 132–135 | `_spec_id_from_filename` | |
| 138–148 | `_list_feature_specs` | |
| 151–159 | `_md_status` | |
| 162–208 | `_parse_backlog_columns` | |
| 216–223 | `_read_counter` | |
| 226–232 | `_is_bootstrap_as_done` | |
| 235–240 | `_yaml_writers` | |
| 243–386 | `audit_project` | 144 строки, 14 детекторов |
| 394–402 | `_load_projects` | |
| 405–464 | `run` | |
| 467–492 | `_print_text` | |
| 495–521 | `main` | |

Список хелперов для `audit_probe.py` из § Design подтверждён — все 11 существуют
под указанными именами. **Дополнение:** `_SPEC_ID_RE` и `_MD_STATUS_RE` тоже переезжают
в `audit_probe.py` (их читают `_parse_backlog_columns` и `_md_status`).

**14 категорий — точные строки-ключи, как они появляются в выводе** (поле `"category"`;
порядок = порядок появления в `audit_project`, он же порядок `CATEGORIES`):

| # | Ключ | Условие | Формат `detail` |
|---|---|---|---|
| 1 | `orphan_spec_md` | `md_ids - yaml_ids` | имя md-файла |
| 2 | `orphan_yaml` | `yaml_ids - md_ids` | `"no md"` |
| 3 | `missing_from_backlog` | `yaml_ids - backlog_ids` | `"no row"` |
| 4 | `bootstrap_as_done` | `_is_bootstrap_as_done` | `"status=done, no transitions, no pueue_id, no finished_at"` |
| 5 | `markdown_status_mismatch` | `md_st and md_st != ya_st` | `f"md={md_st} yaml={ya_st}"` |
| 6 | `backlog_status_mismatch` | `b_st is not None and b_st != ya_st` | `f"backlog={b_st} yaml={ya_st}"` |
| 7 | `backlog_format_unparsed` | `backlog_map[sid] is None` | `"row found but status not extracted"` |
| 8 | `wt_lifecycle_dirty` | `_git_dirty(repo, lifecycle.LIFECYCLE_DIR)` | porcelain-строка |
| 9 | `wt_features_dirty` | `_git_dirty(repo, "ai/features")` | porcelain-строка |
| 10 | `unauthorized_writer` | `_yaml_writers & {"spark","autopilot"}` | `f"by={sorted(bad)}"` |
| 11 | `git_divergence` | `(ahead,behind) != (-1,-1)` и есть ненулевое | `f"ahead={ahead} behind={behind}"` |
| 12 | `push_failures_counter` | `ai/.lifecycle-push-failures > 0` | `f"count={n}"` |
| 13 | `bootstrap_anomaly` | `ai/.bootstrap-anomaly-count > 0` | `f"count={n}"` |
| 14 | `bootstrap_unparsable` | `ai/.bootstrap-unparsable-count > 0` | `f"count={n}"` |

У 8, 9, 11, 12, 13, 14 поле `spec_id` — литерал `"-"`.

---

### БЛОКИРУЮЩИЙ ФАКТ, которого нет в теле спеки

`find . -name "test_lifecycle_audit*"` действительно пуст — но это **не значит, что тестов
нет**. `scripts/vps/tests/test_orchestrator_bootstrap.py` (691 LOC, **вне Allowed Files**)
содержит 12 тестов аудитора в строках 509–691 и делает на строках 513–519:

```python
import lifecycle_audit  # noqa: E402,F401
from lifecycle_audit import (  # noqa: E402
    CATEGORIES,
    _parse_backlog_columns as audit_parse_backlog,
    audit_project,
    run as audit_run,
)
```

**Следствие — жёсткое ограничение Task 3.** После раскола эти четыре имени ОБЯЗАНЫ остаться
атрибутами модуля `lifecycle_audit`, иначе `test_orchestrator_bootstrap.py` падает на
импорте, а править его нельзя. `audit_project` и `run` остаются определены в файле;
`CATEGORIES` и `_parse_backlog_columns` вводятся как **алиасы присваиванием**:

```python
CATEGORIES = audit_categories.CATEGORIES
_parse_backlog_columns = audit_probe._parse_backlog_columns
```

Присваивание — не `from`-импорт, EC-8 (`grep "^from audit_"` = 0) выполняется.

---

### Task 1: Характеризационные тесты для `lifecycle_audit` (СТРОГО ПЕРВАЯ)

**Type:** test
**Files:**
  - create: `scripts/vps/tests/test_lifecycle_audit.py`

**Context.** Единственная сеть, которая будет у этого файла. Пишется против
**неизменённого** `lifecycle_audit.py` и после Task 3 не правится ни на символ — это и
есть доказательство EC-5.

**Step 1: шапка и фикстура.** Копируется приём `tmp_git_repo` из
`test_orchestrator_bootstrap.py:150–173` дословно (реальный git-репозиторий, ADR-013,
без моков):

```python
"""TECH-211 — характеризационные тесты lifecycle_audit.audit_project.

Написаны ДО раскола файла и НЕ правятся ПОСЛЕ (Feathers characterization).
Любое расхождение после Task 3 = регрессия поведения, а не «тест устарел».
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import lifecycle_audit  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    """Реальный git-репозиторий (приём из test_orchestrator_bootstrap.py:150)."""
    r = tmp_path / "repo"
    r.mkdir()

    def git(*args):
        subprocess.run(["git"] + list(args), cwd=str(r), check=True,
                       capture_output=True, text=True)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    (r / "ai" / "lifecycle").mkdir(parents=True)
    (r / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    (r / "ai" / "features").mkdir(parents=True, exist_ok=True)
    git("add", ".")
    git("commit", "-m", "init")
    return r


def _cats(findings):
    return {f["category"] for f in findings}


def _of(findings, category):
    return [f for f in findings if f["category"] == category]
```

**Step 2: по одному тесту на каждую из 14 категорий (EC-1).** Как именно поднимается
каждая категория на подготовленном репозитории:

| Категория | Setup |
|---|---|
| `orphan_spec_md` | записать `ai/features/TECH-666-x.md`, yaml не создавать |
| `orphan_yaml` | `lifecycle.create_initial(repo, "TECH-555", "p1", "tech")`, md не создавать |
| `missing_from_backlog` | `create_initial(...)`, `ai/backlog.md` отсутствует или без строки |
| `bootstrap_as_done` | `create_initial(repo, "TECH-1082", "p2", "tech", status="done")` |
| `markdown_status_mismatch` | `create_initial(..., status="queued")` + md с `**Status:** done` |
| `backlog_status_mismatch` | `create_initial(..., status="queued")` + backlog-строка `done` |
| `backlog_format_unparsed` | backlog `\| ID \| description \|` со строкой без статуса |
| `wt_lifecycle_dirty` | записать `ai/lifecycle/DIRTY.yaml` и **не** коммитить |
| `wt_features_dirty` | записать `ai/features/TECH-700-x.md` и **не** коммитить |
| `unauthorized_writer` | закоммитить рукописный yaml с `by: spark` — приём из `test_orchestrator_bootstrap.py:555–589` |
| `git_divergence` | второй коммит, затем `git update-ref refs/remotes/origin/develop <sha_первого>` → `ahead=1 behind=0` |
| `push_failures_counter` | `ai/.lifecycle-push-failures` = `"7"` |
| `bootstrap_anomaly` | `ai/.bootstrap-anomaly-count` = `"1"` |
| `bootstrap_unparsable` | `ai/.bootstrap-unparsable-count` = `"3"` |

Форма каждого теста — фиксируем и категорию, и `spec_id`, и `detail` (не только
присутствие ключа):

```python
def test_category_bootstrap_as_done(repo):
    lifecycle.create_initial(repo, "TECH-1082", "p2", "tech", status="done")
    hits = _of(lifecycle_audit.audit_project(str(repo)), "bootstrap_as_done")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [
        ("TECH-1082", "status=done, no transitions, no pueue_id, no finished_at")
    ]


def test_category_git_divergence(repo):
    def git(*a):
        return subprocess.run(["git"] + list(a), cwd=str(repo), check=True,
                              capture_output=True, text=True).stdout.strip()

    base = git("rev-parse", "HEAD")
    (repo / "README.md").write_text("x", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-m", "second")
    git("update-ref", "refs/remotes/origin/develop", base)

    hits = _of(lifecycle_audit.audit_project(str(repo)), "git_divergence")
    assert [(h["spec_id"], h["detail"]) for h in hits] == [("-", "ahead=1 behind=0")]
```

Остальные 12 — по тому же шаблону. `detail` берётся из таблицы «14 категорий» выше.

**Step 3: golden-снимок всех 14 сразу (EC-5).** Один тест собирает репозиторий, в
котором горят все 14 категорий, и сверяет **полный список** кортежей:

```python
def test_all_fourteen_categories_golden(repo):
    ...  # setup всех 14 условий в одном репозитории
    actual = [(f["category"], f["spec_id"], f["detail"])
              for f in lifecycle_audit.audit_project(str(repo))]
    assert actual == EXPECTED   # литерал, записанный с ТЕКУЩЕЙ реализации
```

`EXPECTED` **записывается прогоном текущего кода** — это и есть характеризация по
Фезерсу, а не выдумывание ожиданий. Порядок детерминирован: категории идут в порядке
исходника, внутри категории — `sorted()` по `spec_id`, porcelain-строки git отдаёт
отсортированными по пути. Процедура записи:

```bash
cd /home/dld/projects/dld/.worktrees/TECH-211/scripts/vps/tests
python3 -m pytest test_lifecycle_audit.py::test_all_fourteen_categories_golden -q
# первый прогон падает на assert → скопировать actual из diff в EXPECTED
```

**Step 4: поверхность CLI + защита импортов (страховка от поломки
`test_orchestrator_bootstrap.py`).**

```python
def test_module_surface_stays_importable():
    """test_orchestrator_bootstrap.py:513-519 импортирует эти 4 имени из lifecycle_audit.

    Файл вне Allowed Files — раскол не смеет убрать ни одно из них.
    """
    for name in ("CATEGORIES", "_parse_backlog_columns", "audit_project", "run"):
        assert hasattr(lifecycle_audit, name), name
    assert len(lifecycle_audit.CATEGORIES) == 14


def test_run_json_shape(repo, tmp_path, capsys): ...      # rc=1, payload["total"], projects[0]
def test_run_quiet_shape(repo, tmp_path, capsys): ...     # "tmp: N" + "TOTAL: N"
def test_run_text_shape(repo, tmp_path, capsys): ...      # "=== lifecycle_audit ===" + "Total findings:"
def test_run_unknown_category_rc2(tmp_path): ...          # rc == 2
def test_run_clean_rc0(repo, tmp_path): ...               # rc == 0
```

**Step 5: READ-ONLY контракт (EC-7).**

```python
def test_audit_writes_nothing(repo):
    """Аудитор не смеет менять ни git-состояние, ни файлы."""
    def porcelain():
        return subprocess.run(["git", "status", "--porcelain"], cwd=str(repo),
                              capture_output=True, text=True).stdout
    lifecycle.create_initial(repo, "TECH-1082", "p2", "tech", status="done")
    (repo / "ai" / ".bootstrap-anomaly-count").write_text("1", encoding="utf-8")
    before_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                                 capture_output=True, text=True).stdout
    before = porcelain()
    lifecycle_audit.audit_project(str(repo))
    assert porcelain() == before
    assert subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                          capture_output=True, text=True).stdout == before_head
```

**Step 6: прогон на НЕИЗМЕНЁННОМ `lifecycle_audit.py` (EC-2).**

```bash
cd /home/dld/projects/dld/.worktrees/TECH-211/scripts/vps/tests
python3 -m pytest test_lifecycle_audit.py -q
python3 -m pytest -q     # ожидание: 421 + N passed, 0 failed
```

**Acceptance:**
- [ ] ≥14 тестов, ровно по одному на каждый ключ из `CATEGORIES` (EC-1)
- [ ] golden-тест сверяет полный список кортежей `(category, spec_id, detail)`
- [ ] `test_module_surface_stays_importable` присутствует
- [ ] `test_lifecycle_audit.py` ≤ 600 LOC
- [ ] Зелёные на **неизменённом** `lifecycle_audit.py` (EC-2); общий счёт вырос, 0 failed
- [ ] `git diff scripts/vps/lifecycle_audit.py` пуст после Task 1

---

### Task 2: Раскол `heartbeat_reaper.py`

**Type:** code
**Files:**
  - create: `scripts/vps/reaper_pueue.py`
  - create: `scripts/vps/reaper_liveness.py`
  - modify: `scripts/vps/heartbeat_reaper.py`
  - modify: `scripts/vps/tests/test_heartbeat_reaper.py`

**Context.** Чистый перенос по разделителям автора. Ни одна строка тела функции не
меняется. Меняются только: место жительства, импорты и квалификация вызовов.

**Step 1: `scripts/vps/reaper_pueue.py` (новый, ~105 LOC).**

Шапка + дословный перенос строк 52–133 из `heartbeat_reaper.py`:

```python
#!/usr/bin/env python3
"""
Module: reaper_pueue
Role: Pueue inventory for heartbeat_reaper — enumerate Running claude-runner
      tasks and parse their metadata. Extracted from heartbeat_reaper (TECH-211).
Uses: subprocess (pueue status --json), json, re, datetime, pathlib
Used by: heartbeat_reaper.py
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

log = logging.getLogger("heartbeat-reaper")   # то же имя — вывод не меняется
```

Далее — `get_running_claude_tasks`, `_project_from_command`, `_parse_iso` **без единой
правки тела** (внутри `get_running_claude_tasks` вызов `_parse_iso(start_iso)` остаётся
неквалифицированным — он в том же модуле).

Имя логгера обязано остаться `"heartbeat-reaper"`: иначе меняется вывод, а требование —
байт-в-байт. `logging.basicConfig` в новых модулях **не вызывается** — он остаётся
единственным в точке входа.

**Step 2: `scripts/vps/reaper_liveness.py` (новый, ~135 LOC).**

```python
#!/usr/bin/env python3
"""
Module: reaper_liveness
Role: Process liveness probe for heartbeat_reaper — is the claude process for a
      pueue task idle enough to reap? Fail-open: None means "don't kill".
      Extracted from heartbeat_reaper (TECH-211).
Uses: subprocess (pgrep), /proc/<pid>/stat, os.sysconf, time
Used by: heartbeat_reaper.py
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger("heartbeat-reaper")

CPU_SAMPLE_SECONDS = 2     # CPU sampling window for idle check
CPU_IDLE_THRESHOLD = 1.0   # % — below this = idle
```

Далее — `_find_claude_pid`, `is_process_idle`, `_check_pueue_children_idle`,
`_sample_cpu_idle` дословно из строк 203–312. Внутримодульные вызовы
(`_find_claude_pid`, `_check_pueue_children_idle`, `_sample_cpu_idle`) остаются
неквалифицированными.

**Step 3: `scripts/vps/heartbeat_reaper.py` — вырезать и подключить.**

1. Удалить блоки строк **48–133** (`Pueue helpers`) и **199–312** (`Process liveness check`)
   вместе с их разделителями.
2. Удалить из констант `CPU_SAMPLE_SECONDS` и `CPU_IDLE_THRESHOLD` (строки 35–36).
3. Из импортов удалить `re` и `time` (после выноса не используются). `os` — тоже
   (использовался только в `_sample_cpu_idle`). `json`, `subprocess`, `sys`,
   `datetime/timedelta/timezone`, `Path`, `logging` остаются.
4. Сразу после `LOG_DIR = SCRIPT_DIR / "logs"` добавить sys.path-вставку и sibling-импорты
   — тот же приём, что в `lifecycle_audit.py:53–56`:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR / "logs"
sys.path.insert(0, str(SCRIPT_DIR))

import reaper_liveness  # noqa: E402
import reaper_pueue  # noqa: E402
```

**Никаких `from reaper_pueue import ...`** (EC-8, devil DA-4): связанное имя ломает
`patch.object` на модуле.

5. Квалифицировать пять вызовов (это ВСЕ переходы через новую границу):

| Было | Стало | Место |
|---|---|---|
| `_parse_iso(data.get("started_at", ""))` | `reaper_pueue._parse_iso(...)` | в `find_heartbeat_file` (было 172) |
| `tasks = get_running_claude_tasks()` | `tasks = reaper_pueue.get_running_claude_tasks()` | в `reap_stale_sessions` (было 366) |
| `_parse_iso(hb_data.get("updated_at", ""))` | `reaper_pueue._parse_iso(...)` | в `reap_stale_sessions` (было 405) |
| `idle = is_process_idle(tid)` | `idle = reaper_liveness.is_process_idle(tid)` | в `reap_stale_sessions` (было 426) |

Больше пересечений границы нет: `kill_task`, `notify_reap`, `find_heartbeat_file`,
`read_heartbeat` остаются в файле и вызываются неквалифицированно.

6. Обновить docstring-строку `Uses:` — добавить `reaper_pueue`, `reaper_liveness`.

Ожидаемый размер: ~250 LOC.

**Step 4: `scripts/vps/tests/test_heartbeat_reaper.py` — цели патчей.**

Файл 327 LOC. Правки — только цели `patch.object` и квалификация прямых вызовов.
Полный перечень, ничего сверх него не трогать:

| Строка (до) | Что | Действие |
|---|---|---|
| 21 | `import heartbeat_reaper as reaper` | оставить + добавить `import reaper_liveness` и `import reaper_pueue` |
| 173, 200, 221, 244, 268, 281 | `patch.object(reaper, "get_running_claude_tasks", …)` | → `patch.object(reaper_pueue, "get_running_claude_tasks", …)` (**6 мест**) |
| 174, 245, 269 | `patch.object(reaper, "is_process_idle", …)` | → `patch.object(reaper_liveness, "is_process_idle", …)` (**3 места**) |
| 294, 299, 303, 306, 309 | `reaper._parse_iso(…)` | → `reaper_pueue._parse_iso(…)` (**5 мест**, класс `TestParseIso`) |
| 320, 323, 326 | `reaper._project_from_command(…)` | → `reaper_pueue._project_from_command(…)` (**3 места**, класс `TestProjectFromCommand`) |
| 80, 92, 103, 109, 115, 172, 199, 220, 243, 267, 280 | `patch.object(reaper, "LOG_DIR", tmp_path)` | **не трогать** — `LOG_DIR` остаётся в `heartbeat_reaper` |
| 175, 201, 222, 246, 270 | `patch.object(reaper, "kill_task", …)` | **не трогать** |
| 176 | `patch.object(reaper, "notify_reap", …)` | **не трогать** |
| 81, 94, 104, 110, 116, 129, 136, 139 | `reaper.find_heartbeat_file` / `reaper.read_heartbeat` | **не трогать** |
| 178, 203, 224, 248, 272, 283 | `reaper.reap_stale_sessions()` | **не трогать** |

Итого 17 замен. Неиспользуемые импорты (`os`, `subprocess`, `time`, `pytest`) в тест-файле
уже были — не чистить, это вне задачи.

**Step 5: проверка.**

```bash
cd /home/dld/projects/dld/.worktrees/TECH-211
python3 -m py_compile scripts/vps/heartbeat_reaper.py scripts/vps/reaper_pueue.py scripts/vps/reaper_liveness.py
wc -l scripts/vps/heartbeat_reaper.py scripts/vps/reaper_pueue.py scripts/vps/reaper_liveness.py
cd scripts/vps/tests && python3 -m pytest test_heartbeat_reaper.py -q
```

Ожидание: 22 passed, все три файла ≤ 400.

**Acceptance:**
- [ ] `wc -l scripts/vps/heartbeat_reaper.py` ≤ 400 (EC-3)
- [ ] `reaper_pueue.py`, `reaper_liveness.py` ≤ 400 (EC-6)
- [ ] `test_heartbeat_reaper.py` зелёный, число тестов не изменилось (22)
- [ ] `grep -c "^from reaper_" scripts/vps/*.py` = 0 (EC-8)
- [ ] Имя файла `heartbeat_reaper.py` не изменилось — cron жив
- [ ] `logging.basicConfig` вызывается ровно один раз, в `heartbeat_reaper.py`
- [ ] Логгер во всех трёх модулях — `"heartbeat-reaper"`

---

### Task 3: Раскол `lifecycle_audit.py`

**Type:** code
**Files:**
  - create: `scripts/vps/audit_probe.py`
  - create: `scripts/vps/audit_categories.py`
  - modify: `scripts/vps/lifecycle_audit.py`

**Context.** Единственная задача с настоящей декомпозицией: `audit_project` (144 строки)
разбирается на функцию-на-категорию. `test_lifecycle_audit.py` из Task 1 не правится —
он и есть приёмка.

**Step 1: `scripts/vps/audit_probe.py` (новый, ~175 LOC).**

Дословный перенос строк 82–120, 128–129, 132–208, 216–240:

```python
#!/usr/bin/env python3
"""
Module: audit_probe
Role: READ-ONLY probes for lifecycle_audit — git inventory, spec/backlog parsing,
      counter reads, yaml predicates. No writes, ever.
      Extracted from lifecycle_audit (TECH-211).
Uses: subprocess (git ls-tree/status/rev-list), re, pathlib
Used by: lifecycle_audit.py, audit_categories.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
```

Порядок содержимого: `_git`, `_ls_tree`, `_git_dirty`, `_git_divergence`, `_SPEC_ID_RE`,
`_MD_STATUS_RE`, `_spec_id_from_filename`, `_list_feature_specs`, `_md_status`,
`_parse_backlog_columns`, `_read_counter`, `_is_bootstrap_as_done`, `_yaml_writers`.
Тела не меняются. `_parse_backlog_columns` использует `_SPEC_ID_RE` — оба в этом модуле,
квалификация не нужна.

**Step 2: `scripts/vps/audit_categories.py` (новый, ~205 LOC).**

`CATEGORIES` переезжает сюда (SSOT), плюс 14 функций и реестр. Каждая функция получает
готовый контекст-словарь и возвращает список находок. Порядок в `CHECKS` **обязан**
совпадать с порядком в исходном `audit_project` — от него зависит порядок вывода:

```python
#!/usr/bin/env python3
"""
Module: audit_categories
Role: One function per drift category (14). Each takes the prepared audit context
      and returns findings. Extracted from lifecycle_audit.audit_project (TECH-211).
Uses: audit_probe
Used by: lifecycle_audit.py

Context dict keys:
    repo          str   — project root
    lifecycle_dir str   — lifecycle.LIFECYCLE_DIR, passed in to keep this module
                          free of a lifecycle import
    yaml_ids      set[str]
    md_ids        set[str]
    md_map        dict[str, str]        spec_id -> md filename
    backlog_ids   set[str]
    backlog_map   dict[str, str | None] spec_id -> status or None
    yaml_data     dict[str, dict]       spec_id -> parsed lifecycle yaml
"""

from __future__ import annotations

import audit_probe

CATEGORIES = (
    "orphan_spec_md",
    "orphan_yaml",
    "missing_from_backlog",
    "bootstrap_as_done",
    "markdown_status_mismatch",
    "backlog_status_mismatch",
    "backlog_format_unparsed",
    "wt_lifecycle_dirty",
    "wt_features_dirty",
    "unauthorized_writer",
    "git_divergence",
    "push_failures_counter",
    "bootstrap_anomaly",
    "bootstrap_unparsable",
)


def check_orphan_spec_md(ctx: dict) -> list[dict]:
    """md exists but yaml absent in HEAD."""
    return [
        {"category": "orphan_spec_md", "spec_id": sid, "detail": ctx["md_map"][sid]}
        for sid in sorted(ctx["md_ids"] - ctx["yaml_ids"])
    ]


def check_orphan_yaml(ctx: dict) -> list[dict]:
    """yaml present, no md."""
    return [
        {"category": "orphan_yaml", "spec_id": sid, "detail": "no md"}
        for sid in sorted(ctx["yaml_ids"] - ctx["md_ids"])
    ]


def check_missing_from_backlog(ctx: dict) -> list[dict]:
    """yaml exists, backlog has no row."""
    return [
        {"category": "missing_from_backlog", "spec_id": sid, "detail": "no row"}
        for sid in sorted(ctx["yaml_ids"] - ctx["backlog_ids"])
    ]


def check_bootstrap_as_done(ctx: dict) -> list[dict]:
    """TECH-195 signature: done with empty history."""
    return [
        {
            "category": "bootstrap_as_done",
            "spec_id": sid,
            "detail": "status=done, no transitions, no pueue_id, no finished_at",
        }
        for sid in sorted(ctx["yaml_ids"])
        if audit_probe._is_bootstrap_as_done(ctx["yaml_data"].get(sid, {}))
    ]


def check_markdown_status_mismatch(ctx: dict) -> list[dict]:
    out: list[dict] = []
    for sid in sorted(ctx["yaml_ids"] & ctx["md_ids"]):
        md_st = audit_probe._md_status(ctx["repo"], ctx["md_map"][sid])
        ya_st = ctx["yaml_data"].get(sid, {}).get("status")
        if md_st and md_st != ya_st:
            out.append({
                "category": "markdown_status_mismatch",
                "spec_id": sid,
                "detail": f"md={md_st} yaml={ya_st}",
            })
    return out


def check_backlog_status_mismatch(ctx: dict) -> list[dict]:
    """Only when backlog actually carries a status."""
    out: list[dict] = []
    for sid in sorted(ctx["yaml_ids"] & ctx["backlog_ids"]):
        b_st = ctx["backlog_map"].get(sid)
        ya_st = ctx["yaml_data"].get(sid, {}).get("status")
        if b_st is not None and b_st != ya_st:
            out.append({
                "category": "backlog_status_mismatch",
                "spec_id": sid,
                "detail": f"backlog={b_st} yaml={ya_st}",
            })
    return out


def check_backlog_format_unparsed(ctx: dict) -> list[dict]:
    """Row matched spec_id but status is None."""
    return [
        {
            "category": "backlog_format_unparsed",
            "spec_id": sid,
            "detail": "row found but status not extracted",
        }
        for sid in sorted(ctx["backlog_ids"])
        if ctx["backlog_map"].get(sid) is None
    ]


def check_wt_lifecycle_dirty(ctx: dict) -> list[dict]:
    return [
        {"category": "wt_lifecycle_dirty", "spec_id": "-", "detail": line}
        for line in audit_probe._git_dirty(ctx["repo"], ctx["lifecycle_dir"])
    ]


def check_wt_features_dirty(ctx: dict) -> list[dict]:
    return [
        {"category": "wt_features_dirty", "spec_id": "-", "detail": line}
        for line in audit_probe._git_dirty(ctx["repo"], "ai/features")
    ]


def check_unauthorized_writer(ctx: dict) -> list[dict]:
    """ADR-025: spark / autopilot must never appear as writers."""
    out: list[dict] = []
    for sid in sorted(ctx["yaml_ids"]):
        bad = audit_probe._yaml_writers(ctx["yaml_data"].get(sid, {})) & {"spark", "autopilot"}
        if bad:
            out.append({
                "category": "unauthorized_writer",
                "spec_id": sid,
                "detail": f"by={sorted(bad)}",
            })
    return out


def check_git_divergence(ctx: dict) -> list[dict]:
    ahead, behind = audit_probe._git_divergence(ctx["repo"])
    if (ahead, behind) != (-1, -1) and (ahead > 0 or behind > 0):
        return [{
            "category": "git_divergence",
            "spec_id": "-",
            "detail": f"ahead={ahead} behind={behind}",
        }]
    return []


def _counter_finding(ctx: dict, category: str, filename: str) -> list[dict]:
    n = audit_probe._read_counter(ctx["repo"], filename)
    if n > 0:
        return [{"category": category, "spec_id": "-", "detail": f"count={n}"}]
    return []


def check_push_failures_counter(ctx: dict) -> list[dict]:
    return _counter_finding(ctx, "push_failures_counter", ".lifecycle-push-failures")


def check_bootstrap_anomaly(ctx: dict) -> list[dict]:
    return _counter_finding(ctx, "bootstrap_anomaly", ".bootstrap-anomaly-count")


def check_bootstrap_unparsable(ctx: dict) -> list[dict]:
    """TECH-195 Task 1 counter."""
    return _counter_finding(ctx, "bootstrap_unparsable", ".bootstrap-unparsable-count")


# Order is load-bearing: it reproduces the emission order of the original
# audit_project, and the audit's output must stay byte-identical (TECH-211).
CHECKS = (
    check_orphan_spec_md,
    check_orphan_yaml,
    check_missing_from_backlog,
    check_bootstrap_as_done,
    check_markdown_status_mismatch,
    check_backlog_status_mismatch,
    check_backlog_format_unparsed,
    check_wt_lifecycle_dirty,
    check_wt_features_dirty,
    check_unauthorized_writer,
    check_git_divergence,
    check_push_failures_counter,
    check_bootstrap_anomaly,
    check_bootstrap_unparsable,
)
```

**Step 3: `scripts/vps/lifecycle_audit.py` — оставить сборку.**

1. Удалить строки 60–75 (`CATEGORIES`), 77–240 (все хелперы и разделители).
2. Заменить тело `audit_project` (243–386) на сборку контекста + прогон реестра:

```python
def audit_project(repo: str) -> list[dict]:
    """Run all 14 detectors against a single project. Returns list of findings."""
    if not Path(repo).is_dir():
        return []

    # ── Inventory: yaml from HEAD, md from filesystem, backlog parse
    yaml_names = audit_probe._ls_tree(repo, lifecycle.LIFECYCLE_DIR)
    yaml_ids = {n[:-5] for n in yaml_names if n.endswith(".yaml")}
    md_map = audit_probe._list_feature_specs(repo)
    backlog_path = Path(repo) / "ai" / "backlog.md"
    backlog_text = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    backlog_map = audit_probe._parse_backlog_columns(backlog_text)

    # Pre-load all yamls (single pass)
    yaml_data: dict[str, dict] = {}
    for sid in yaml_ids:
        d = lifecycle.read_lifecycle(repo, sid)
        if d:
            yaml_data[sid] = d

    ctx = {
        "repo": repo,
        "lifecycle_dir": lifecycle.LIFECYCLE_DIR,
        "yaml_ids": yaml_ids,
        "md_ids": set(md_map.keys()),
        "md_map": md_map,
        "backlog_ids": set(backlog_map.keys()),
        "backlog_map": backlog_map,
        "yaml_data": yaml_data,
    }

    findings: list[dict] = []
    for check in audit_categories.CHECKS:
        findings.extend(check(ctx))
    return findings
```

3. Импорты и алиасы обратной совместимости — сразу после `import lifecycle`:

```python
import audit_categories  # noqa: E402
import audit_probe  # noqa: E402
import lifecycle  # noqa: E402

log = logging.getLogger("lifecycle_audit")

# Public surface of this module — `scripts/vps/tests/test_orchestrator_bootstrap.py`
# (out of this spec's Allowed Files) imports both names from here. Plain assignment,
# not `from ... import`: a bound name would break monkeypatching (devil DA-4).
CATEGORIES = audit_categories.CATEGORIES
_parse_backlog_columns = audit_probe._parse_backlog_columns
```

4. Из импортов удалить `re` и `subprocess` (после выноса не используются). `argparse`,
   `json`, `logging`, `os`, `sys`, `Path` остаются.
5. `_load_projects`, `run`, `_print_text`, `main` — **не трогать**. `run` и `_print_text`
   читают `CATEGORIES` — алиас это обеспечивает.
6. Обновить docstring `Uses:` — добавить `audit_probe`, `audit_categories`. Строку
   `Categories (14):` в docstring оставить как есть (это документация вывода).

Ожидаемый размер: ~225 LOC.

**Step 4: проверка (EC-5 — доказательство сохранения поведения).**

```bash
cd /home/dld/projects/dld/.worktrees/TECH-211
python3 -m py_compile scripts/vps/lifecycle_audit.py scripts/vps/audit_probe.py scripts/vps/audit_categories.py
python3 scripts/vps/lifecycle_audit.py --help
wc -l scripts/vps/lifecycle_audit.py scripts/vps/audit_probe.py scripts/vps/audit_categories.py
cd scripts/vps/tests
git diff --stat -- test_lifecycle_audit.py     # ОБЯЗАН быть пуст
python3 -m pytest test_lifecycle_audit.py test_orchestrator_bootstrap.py -q
python3 -m pytest -q
```

**Acceptance:**
- [ ] `wc -l` всех трёх ≤ 400 (EC-4, EC-6)
- [ ] `test_lifecycle_audit.py` зелёный **без единой правки** — `git diff` по нему пуст (EC-5)
- [ ] `test_orchestrator_bootstrap.py` зелёный и **не изменён** (вне Allowed Files)
- [ ] `python3 scripts/vps/lifecycle_audit.py --help` → exit 0 (AV-S2)
- [ ] `grep -c "^from audit_" scripts/vps/*.py` = 0 (EC-8)
- [ ] Порядок `audit_categories.CHECKS` = порядок `CATEGORIES`
- [ ] Полный прогон: 421 + N passed, 0 failed

---

### Execution Order

```
Task 1  ──▶  Task 2  ──▶  Task 3
(тесты)     (reaper)     (audit)
```

Строго последовательно, параллелизма нет.

**Зависимости:**
- Task 1 не зависит ни от чего и обязана быть первой: её единственная ценность в том,
  что она зафиксировала поведение **до** резки. Написанная после Task 3 — она
  зафиксирует баг.
- Task 2 не зависит от Task 1 технически, но идёт второй: это более простой и полностью
  покрытый тестами раскол, он отлаживает сам приём (flat sibling + attribute access)
  на безопасном материале.
- Task 3 зависит от Task 1 жёстко. Без `test_lifecycle_audit.py` она запрещена.

**Один коммит на задачу.** После Task 3 `git diff` по `test_lifecycle_audit.py` обязан
быть пуст — это встроенная проверка, а не пожелание.

---

## Drift Log

**Checked:** 2026-07-27 UTC
**Result:** light_drift

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/heartbeat_reaper.py` | нет изменений — 459 LOC, разделители 48/136/199/315/356 подтверждены дословно | — |
| `scripts/vps/lifecycle_audit.py` | нет изменений — 525 LOC, все 11 хелперов на месте | — |
| `scripts/vps/tests/test_heartbeat_reaper.py` | 327 LOC, спека говорила 326 (off-by-one) | AUTO-FIX: план оперирует фактическими номерами строк |
| `scripts/vps/tests/test_orchestrator_bootstrap.py` | **не существовало в модели спеки**: 12 тестов аудитора (509–691) + `from lifecycle_audit import CATEGORIES, _parse_backlog_columns, audit_project, run` (513–519); файл ВНЕ Allowed Files | AUTO-FIX: Task 3 Step 3 обязывает сохранить 4 имени как атрибуты модуля через алиасы-присваивания; Task 1 Step 4 добавляет `test_module_surface_stays_importable` |
| `scripts/vps/lifecycle_audit.py:128–129` | `_SPEC_ID_RE`, `_MD_STATUS_RE` не перечислены в списке `audit_probe` в § Design | AUTO-FIX: добавлены в Task 3 Step 1 |
| `scripts/vps/audit_digest.py` | существует и к этой спеке отношения не имеет | не трогать |
| Окружение | `python` отсутствует в PATH, только `python3` | AUTO-FIX: все команды плана и § Acceptance Verification переведены на `python3` |

### References Updated
- Task 2: `_parse_iso` теперь переносится в `reaper_pueue` с явным перечислением
  4 точек пересечения границы (было: «квалифицировать вызовы» без списка)
- Task 2: перечислены все 17 замен в `test_heartbeat_reaper.py` с номерами строк
- Task 3: `CATEGORIES` объявлен в `audit_categories.py`, в `lifecycle_audit.py` — алиас
- AV-S1 / AV-F1 / Verify Command: `python` → `python3`

### Не найдено
- Новых программных потребителей `heartbeat_reaper` / `lifecycle_audit` нет
  (кроме двух тест-файлов выше). Утверждение § Impact Tree Step 1 в силе.
- `reaper_pueue.py`, `reaper_liveness.py`, `audit_probe.py`, `audit_categories.py`,
  `tests/test_lifecycle_audit.py` — отсутствуют, создаются с нуля.

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | У `lifecycle_audit` появляется регрессионная сеть | Task 1 | ✓ |
| 2 | `heartbeat_reaper.py` под 400 | Task 2 | ✓ |
| 3 | `lifecycle_audit.py` под 400 | Task 3 | ✓ |
| 4 | Cron продолжает находить reaper | — | имя файла не меняется |
| 5 | Вывод аудитора не изменился | Task 3 (EC-5) | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Все 14 категорий покрыты | `test_lifecycle_audit.py` | ≥14 тест-кейсов, по одному на категорию | deterministic | codebase §5 | P0 |
| EC-2 | Тесты зелёные до раскола | неизменённый `lifecycle_audit.py` | passed | deterministic | Feathers | P0 |
| EC-3 | Reaper под лимитом | `wc -l scripts/vps/heartbeat_reaper.py` | ≤ 400 | deterministic | user | P0 |
| EC-4 | Аудитор под лимитом | `wc -l scripts/vps/lifecycle_audit.py` | ≤ 400 | deterministic | user | P0 |
| EC-5 | Вывод аудитора побайтово тот же | один и тот же репозиторий, до и после | `diff` пуст | deterministic | Feathers | P0 |
| EC-6 | Новые модули под лимитом | `wc -l` четырёх новых файлов | каждый ≤ 400 | deterministic | user | P1 |
| EC-7 | Аудитор ничего не пишет | прогон на грязном репозитории | `git status --porcelain` не меняется | deterministic | READ-ONLY контракт | P0 |
| EC-8 | Нет связанных имён | `grep "^from reaper_\|^from audit_" scripts/vps/*.py` | 0 попаданий | deterministic | devil DA-4 | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-9 | Работающий pueue со свежей задачей | `python3 scripts/vps/heartbeat_reaper.py` | не убивает живую сессию, exit 0 | integration | TECH-198 | P0 |
| EC-10 | Cron-строка из `setup-vps.sh` дословно | вызов по абсолютному пути | exit 0 | integration | devil SA-7 | P0 |

### Coverage Summary
Deterministic: 8 | Integration: 2 | LLM-Judge: 0 | Total: 10 (min 3 ✓)

### TDD Order
1. EC-1, EC-2 — характеризация до всякой резки
2. EC-5, EC-7 — сохранение поведения
3. EC-3, EC-4, EC-6, EC-8 — форма
4. EC-9, EC-10 — интеграция

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Оба скрипта компилируются | `python3 -m py_compile scripts/vps/heartbeat_reaper.py scripts/vps/lifecycle_audit.py` | exit 0 | 15s |
| AV-S2 | Аудитор запускается | `python3 scripts/vps/lifecycle_audit.py --help` | exit 0 | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты зелёные | — | `cd scripts/vps/tests && python3 -m pytest -q` | 421 + N passed, 0 failed |
| AV-F2 | Лимит соблюдён | — | `wc -l` шести файлов поимённо (см. Verify Command; `audit_*.py` глобом захватит посторонний `audit_digest.py`) | все ≤ 400 |
| AV-F3 | Cron жив на VPS | VPS | `crontab -l \| grep heartbeat_reaper` затем запуск этой строки вручную | exit 0 |

### Verify Command

```bash
python3 -m py_compile scripts/vps/heartbeat_reaper.py scripts/vps/lifecycle_audit.py \
  scripts/vps/reaper_pueue.py scripts/vps/reaper_liveness.py \
  scripts/vps/audit_probe.py scripts/vps/audit_categories.py
wc -l scripts/vps/heartbeat_reaper.py scripts/vps/lifecycle_audit.py \
  scripts/vps/reaper_pueue.py scripts/vps/reaper_liveness.py \
  scripts/vps/audit_probe.py scripts/vps/audit_categories.py
grep -c "^from reaper_\|^from audit_" scripts/vps/*.py | grep -v ":0$" || echo "EC-8 ok"
cd scripts/vps/tests && python3 -m pytest -q
```

> `scripts/vps/audit_digest.py` существует независимо от этой спеки — глоб
> `scripts/vps/audit_*.py` его захватит. Поэтому файлы перечислены поимённо.

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `heartbeat_reaper.py` и `lifecycle_audit.py` ≤ 400 LOC
- [ ] Четыре новых модуля ≤ 400 LOC каждый
- [ ] Имена точек входа не изменились

### Tests
- [ ] EC-1..EC-10 проходят
- [ ] `test_lifecycle_audit.py` написан ДО раскола и не правился ПОСЛЕ

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2 локально
- [ ] AV-F3 на VPS

### Technical
- [ ] Вывод обеих программ не изменился
- [ ] `grep "^from reaper_\|^from audit_"` = 0

---

## Autopilot Log
