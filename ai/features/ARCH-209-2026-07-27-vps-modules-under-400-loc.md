# Feature: [ARCH-209] scripts/vps под 400 LOC — эпик и финальный гейт

**Priority:** P1 | **Date:** 2026-07-27
**Size:** 3 tasks / 7 files — эпик, дети ведут основную работу.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`.claude/rules/architecture.md` § Limits задаёт «Max 400 LOC per file». Восемь файлов
в `scripts/vps/` нарушают правило, суммарно 6644 LOC:

| Файл | LOC | Превышение |
|---|---|---|
| `callback.py` | 1698 | +1298 |
| `lifecycle.py` | 1163 | +763 |
| `orchestrator.py` | 1078 | +678 |
| `claude-runner.py` | 717 | +317 |
| `db.py` | 602 | +202 |
| `lifecycle_audit.py` | 525 | +125 |
| `heartbeat_reaper.py` | 459 | +59 |
| `gate_logic.py` | 402 | +2 |

Правило написано против конкретного отказа, и отказ произошёл 2026-07-27: при починке
reconciliation-гейта был вызван `lifecycle.list_by_status()` с предположением, что она
возвращает список `spec_id`. Она возвращает список словарей — и это написано в её
собственном docstring, `lifecycle.py:715`. Файл в 1163 строки не был прочитан; контракт
функции узнали по имени. Operator-скрипт восстановления молча вернул «0 кандидатов»
при пяти реальных, и ошибка всплыла только на живом прогоне на VPS.

Второй отказ того же дня, тот же класс: dry-run печатал все 17 спек как восстановимые,
потому что валидация стояла не в той ветке кода.

## Context

`scripts/vps/` — прод-инфраструктура оркестратора, обслуживающая 10 проектов. Демоны
`dld-orchestrator.service` и `dld-gate-daemon.service` держат импортированные модули в
памяти на всё время жизни процесса.

Эпик закрывает работу: проверяет, что все восемь файлов уложились, чинит доковые
ссылки, которые разъедутся от переноса строк, и ставит автоматический сторож, чтобы
правило больше не нарушалось молча.

**Дети (порядок и зависимости):**

| ID | Что | Зависит от |
|---|---|---|
| TECH-210 | Дедупликация гейта (MP-011) + `gate_logic.py` ≤400 | — |
| TECH-211 | `heartbeat_reaper.py` + `lifecycle_audit.py` (нулевые потребители) | — |
| TECH-212 | `db.py` | — |
| TECH-213 | `claude-runner.py` (+ extract-function на `run_task`) | — |
| TECH-214 | `lifecycle.py` | — |
| TECH-215 | `orchestrator.py` (+ extract-function на `scan_queued`) | — |
| TECH-216 | `callback.py` (+ extract-function на `verify_status_sync`) | TECH-210 |

TECH-211..215 не пересекаются по файлам и могут идти параллельно на разных слотах.

---

## Scope

**In scope:** финальная верификация лимита; починка 10 hardcoded `file.py:NNN` цитат в
`docs/orchestrator/status-model.md`; обновление `.claude/rules/dependencies.md` под новые
модули; CI-сторож на 400 LOC.

**Out of scope:** сам раскол файлов (это дети TECH-210..216); `event_writer.py`,
`gate-daemon.py`, `spec_operator.py` и прочие файлы `scripts/vps/` уже под лимитом;
изменение самого лимита 400.

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "\.py:[0-9]" docs/` → 10 попаданий, все в `status-model.md`
- `.claude/rules/dependencies.md` — таблицы обратных указателей на все модули `scripts/vps/`
- CI: `.github/workflows/ci.yml:90` (`--cov=scripts/vps`), `test.yml:65` (`PYTHONPATH=scripts/vps`)

### Step 2: DOWN — what depends on?

Эпик ничего не импортирует. Читает результат детей.

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `docs/orchestrator/status-model.md` | 15, 21, 28, 30, 63, 64, 80, 97, 118 | 9 цитат в `lifecycle.py` | перепроверить и обновить |
| `docs/orchestrator/status-model.md` | 169 | `callback.py:1067-1357` — **уже неверна** (`verify_status_sync` на 1123) | обновить |
| `.claude/rules/dependencies.md` | — | нет строк для новых sibling-модулей | добавить |

`callback.py:1067` промахивается на 56 строк уже сегодня, до всякого рефакторинга — доки
разъехались по мере роста файла. Это и есть механизм, против которого правило написано.

### Step 4: CHECKLIST — mandatory folders

- [x] `tests/**` — новый тест на LOC-сторож
- [x] `db/migrations/**` — директории нет в проекте (`db.py` использует `schema.sql`)
- [x] `ai/glossary/**` — директории **не существует**; `gate_logic.py:17` и
      `lifecycle.py:26` ссылаются на несуществующий файл. Предсуществующий дрейф, вне скоупа

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] `bash scripts/vps/check-loc-limit.sh` = 0 нарушений после всех детей

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/check-loc-limit.sh` — сторож лимита 400 LOC (NEW)
- `scripts/vps/tests/test_check_loc_limit.py` — тесты сторожа (NEW)
- `.github/workflows/ci.yml` — вызов сторожа в CI (modify)
- `docs/orchestrator/status-model.md` — 10 цитат `file.py:NNN` (modify)
- `docs/orchestrator/components.md` — покомпонентный справочник под новые модули (modify)
- `.claude/rules/dependencies.md` — граф зависимостей под новые модули (modify)
- `.claude/rules/architecture.md` — запись о сторожe в § Limits (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (инфраструктура, вне доменной модели продукта)
**Cross-cutting:** Errors — сторож обязан падать громко (exit≠0), не предупреждать
**Data model:** не затрагивается

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep` (0 байт, 2026-05-10) — банка уроков нет,
`index.jsonl` отсутствует. Gate 7 auto-pass (no lessons bank).

---

## Approaches

### Approach 1: Сторож как отдельный shell-скрипт в CI (выбран)
**Source:** `research-codebase.md` §3 — CI уже гоняет `pytest` с `PYTHONPATH=scripts/vps`,
добавить шаг дешевле, чем плагин
**Summary:** `check-loc-limit.sh` считает `wc -l` по `scripts/vps/*.py`, падает при >400
**Pros:** нулевые зависимости; воспроизводится локально одной командой; тот же паттерн,
что `check-doc-references.sh`, который уже живёт в этой директории
**Cons:** shell; лимит зашит в скрипт, а не читается из `architecture.md`

### Approach 2: `pytest-imports` + правило на длину
**Source:** `research-web.md` §Libraries — `pytest-imports` предлагался под FF-09-инвариант
**Summary:** новый dev-dependency, декларативные правила
**Pros:** заодно закрепляет «`gate_logic` не импортирует `callback`» как тест
**Cons:** решает другую задачу (направление импортов, не длину); новая зависимость ради
одного `wc -l`

### Selected: 1
**Rationale:** длина файла — это `wc -l`, а не задача для AST-плагина. Инвариант
направления импортов ценен, но это отдельная работа: сейчас он выражен docstring'ом
`gate_logic.py:19` и подтверждается грепом, а превращение его в тест не входит в
«уложиться в 400».

---

## Design

### Architecture

```
TECH-210 ─┐
TECH-211 ─┤
TECH-212 ─┼─→ ARCH-209 (AFTER всех) → verify + docs + сторож
TECH-213 ─┤
TECH-214 ─┤
TECH-215 ─┤
TECH-216 ─┘  (сама AFTER TECH-210)
```

### Сторож

```bash
#!/usr/bin/env bash
set -euo pipefail
# 400 для исходников, 600 для тестов — .claude/rules/architecture.md § Limits
```

Проверяет `scripts/vps/*.py` (не рекурсивно — `tests/` отдельным лимитом 600).
Печатает каждое нарушение как `path:LOC (limit N)` и падает с exit 1.

### Database Changes

Нет.

---

## Implementation Plan

### Research Sources
- [Working Effectively With Legacy Code — Feathers](http://objectmentor.com/resources/articles/WorkingEffectivelyWithLegacyCode.pdf) — extract-method-then-extract-class как техника детей
- `research-codebase.md` §3 — граф импортов и hardcoded-пути
- `research-devil.md` §SA-5 — цитаты в доках никем не валидируются

### Task 1: Сторож лимита
**Type:** code
**Files:**
  - create: `scripts/vps/check-loc-limit.sh`
  - create: `scripts/vps/tests/test_check_loc_limit.py`
  - modify: `.github/workflows/ci.yml`
**Pattern:** `scripts/vps/check-doc-references.sh` — тот же shell-стиль, `set -euo pipefail`
**Acceptance:** скрипт падает на подсунутом 401-строчном файле и проходит на текущем дереве

### Task 2: Доковые ссылки
**Type:** code
**Files:**
  - modify: `docs/orchestrator/status-model.md`
  - modify: `docs/orchestrator/components.md`
**Pattern:** —
**Acceptance:** каждая цитата `file.py:NNN` проверена командой `sed -n 'NNNp' <file>` и
указывает на заявленный символ; ноль промахов

### Task 3: Граф зависимостей
**Type:** code
**Files:**
  - modify: `.claude/rules/dependencies.md`
  - modify: `.claude/rules/architecture.md`
**Pattern:** существующие таблицы обратных указателей в `dependencies.md`
**Acceptance:** каждый новый sibling-модуль от TECH-210..216 имеет строку с «Uses» и
«Used by»; в `architecture.md` § Limits добавлена ссылка на сторож

### Execution Order
1 → 2 → 3

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Все 7 детей закрыты | — | зависимость (AFTER) |
| 2 | Ни один файл `scripts/vps/*.py` не превышает 400 | Task 1 | ✓ |
| 3 | Нарушение лимита ловится в CI, а не глазами | Task 1 | ✓ |
| 4 | Доковые цитаты указывают на реальные строки | Task 2 | ✓ |
| 5 | Граф зависимостей описывает новые модули | Task 3 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Сторож ловит нарушение | временный `.py` на 401 строку в `scripts/vps/` | exit 1, в stdout путь и число строк | deterministic | user | P0 |
| EC-2 | Сторож зелёный на чистом дереве | `scripts/vps/` после всех детей | exit 0, ноль строк нарушений | deterministic | user | P0 |
| EC-3 | Лимит тестов отдельный | тест-файл на 550 строк в `scripts/vps/tests/` | exit 0 — лимит тестов 600 | deterministic | blueprint (`architecture.md` § Limits) | P1 |
| EC-4 | Доковые цитаты честные | каждая `file.py:NNN` из `status-model.md` | `sed -n 'NNNp'` содержит заявленный символ | deterministic | devil SA-5 | P1 |
| EC-5 | Сторож не трогает чужие директории | `.py` на 900 строк вне `scripts/vps/` | exit 0 — скоуп только `scripts/vps/` | deterministic | devil | P2 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-6 | CI-воркфлоу с сторожем | push ветки с 401-строчным файлом | job падает на шаге LOC, а не на pytest | integration | user | P1 |

### Coverage Summary
Deterministic: 5 | Integration: 1 | LLM-Judge: 0 | Total: 6 (min 3 ✓)

### TDD Order
1. EC-1 → FAIL → написать скрипт → PASS
2. EC-2, EC-3, EC-5
3. EC-4 (ручная сверка + фиксация), EC-6

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Сторож исполним | `bash scripts/vps/check-loc-limit.sh` | exit 0 | 10s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Лимит соблюдён | все дети done | `wc -l scripts/vps/*.py \| sort -rn \| head -3` | максимум ≤ 400 |
| AV-F2 | Тесты не сломаны | — | `cd scripts/vps/tests && python -m pytest -q` | passed ≥ 419, 0 failed |
| AV-F3 | Демоны живы после деплоя | VPS | `systemctl --user restart dld-orchestrator dld-gate-daemon && systemctl --user is-active dld-orchestrator dld-gate-daemon` | `active` дважды |

### Verify Command

```bash
bash scripts/vps/check-loc-limit.sh
wc -l scripts/vps/*.py | sort -rn | head -3
cd scripts/vps/tests && python -m pytest -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Все 7 детей в статусе `done`
- [ ] Ни один `scripts/vps/*.py` не превышает 400 LOC

### Tests
- [ ] EC-1..EC-6 проходят
- [ ] `scripts/vps/tests/` зелёные, счётчик не упал

### Acceptance Verification
- [ ] AV-S1, AV-F1, AV-F2 локально
- [ ] AV-F3 на VPS — **рестарт демонов обязателен**, иначе живёт старый код

### Technical
- [ ] Нет регрессий
- [ ] `docs/orchestrator/` цитаты сверены

---

## Autopilot Log
