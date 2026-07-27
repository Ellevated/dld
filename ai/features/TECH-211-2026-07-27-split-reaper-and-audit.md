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

### Research Sources
- `research-codebase.md` §1 — карта ответственностей обоих файлов с диапазонами строк
- `research-codebase.md` §5 — подтверждение нулевого покрытия `lifecycle_audit.py`
- [The Refactor That Broke Backups for Two Days](https://drunk.support/the-refactor-that-broke-backups-for-two-days/) — почему точка входа не становится пакетом

### Task 1: Характеризационные тесты для `lifecycle_audit`
**Type:** test
**Files:**
  - create: `scripts/vps/tests/test_lifecycle_audit.py`
**Pattern:** `scripts/vps/tests/test_orchestrator_bootstrap.py` — тот же приём подготовки
временного git-репозитория
**Acceptance:** каждая из 14 категорий дрейфа покрыта хотя бы одним кейсом; тесты зелёные
на **неизменённом** `lifecycle_audit.py`

### Task 2: Раскол `heartbeat_reaper.py`
**Type:** code
**Files:**
  - create: `scripts/vps/reaper_pueue.py`
  - create: `scripts/vps/reaper_liveness.py`
  - modify: `scripts/vps/heartbeat_reaper.py`
  - modify: `scripts/vps/tests/test_heartbeat_reaper.py`
**Pattern:** секционные разделители в самом файле (строки 48, 136, 199, 315, 356)
**Acceptance:** `wc -l scripts/vps/heartbeat_reaper.py` ≤ 400; `test_heartbeat_reaper.py` зелёный

### Task 3: Раскол `lifecycle_audit.py`
**Type:** code
**Files:**
  - create: `scripts/vps/audit_probe.py`
  - create: `scripts/vps/audit_categories.py`
  - modify: `scripts/vps/lifecycle_audit.py`
**Pattern:** Task 2
**Acceptance:** `wc -l` всех трёх ≤ 400; `test_lifecycle_audit.py` из Task 1 зелёный
**без единой правки** — это и есть доказательство сохранения поведения

### Execution Order
1 → 2 → 3

Task 1 строго первой. Task 3 без неё запрещена.

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
| AV-S1 | Оба скрипта компилируются | `python -m py_compile scripts/vps/heartbeat_reaper.py scripts/vps/lifecycle_audit.py` | exit 0 | 15s |
| AV-S2 | Аудитор запускается | `python3 scripts/vps/lifecycle_audit.py --help` | exit 0 | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты зелёные | — | `cd scripts/vps/tests && python -m pytest -q` | passed вырос на число новых тестов, 0 failed |
| AV-F2 | Лимит соблюдён | — | `wc -l scripts/vps/heartbeat_reaper.py scripts/vps/lifecycle_audit.py scripts/vps/reaper_*.py scripts/vps/audit_*.py` | все ≤ 400 |
| AV-F3 | Cron жив на VPS | VPS | `crontab -l \| grep heartbeat_reaper` затем запуск этой строки вручную | exit 0 |

### Verify Command

```bash
python -m py_compile scripts/vps/heartbeat_reaper.py scripts/vps/lifecycle_audit.py
wc -l scripts/vps/heartbeat_reaper.py scripts/vps/lifecycle_audit.py scripts/vps/reaper_*.py scripts/vps/audit_*.py
cd scripts/vps/tests && python -m pytest -q
```

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
