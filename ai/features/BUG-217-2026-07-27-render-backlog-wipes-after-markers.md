# Bug: [BUG-217] ОТОЗВАНА — премиса неверна

**Priority:** P1 | **Date:** 2026-07-27

> ## ⛔ WITHDRAWN 2026-07-27 — не воспроизводится, дефекта нет
>
> Спека утверждает, что `callback._render_and_commit_backlog` разрушает `ai/backlog.md`
> на каждом цикле. **У этой функции ноль call-sites.**
>
> `grep -rn "_render_and_commit_backlog" --include="*.py" .` → одно попадание, само
> определение (`callback.py:1095`). Вызов удалён в **ARCH-196** (2026-05-27), что
> зафиксировано в `CHANGELOG.md:26`: «removed inline `_render_and_commit_backlog` call —
> `ai/backlog.md` is now exclusively written by spark/autopilot (CQRS principle).
> Function retained as emergency operator CLI only».
>
> Живой путь записи — `lifecycle._atomic_write` → `render_backlog.sync_status`, который
> переписывает только ячейку статуса. Доказано на реальном прогоне: коммит `ee6aaec`
> (`lifecycle(TECH-210): blocked`) изменил в backlog **одну строку** — ячейку статуса —
> и оба `AFTER`-маркера остались нетронутыми.
>
> **Как я ошибся.** Прочитал тело функции, увидел внутри вызов разрушительного
> `render_backlog.render_backlog()` и заключил, что путь живой — не грепнув call-sites.
> Это тот же отказ, что с `lifecycle.list_by_status` в тот же день: контракт взят из
> чтения фрагмента без проверки, как он подключён. Ровно то, против чего написан
> эпик ARCH-209.
>
> Второе доказательство, которое я истолковал наоборот: `grep -c "AFTER " ai/backlog.md`
> = 0 означало не «маркеры стёрли», а «их никто никогда не писал». Механизм не был
> сломан — он был неиспользован.
>
> **Что из этого остаётся правдой:** зависимости `AFTER` действительно живут только в
> `ai/backlog.md`, а не в lifecycle-SoT. Это по-прежнему архитектурная асимметрия,
> и upstream-сигнал о ней сохранён (в исправленной формулировке). Но это вопрос к
> `/architect`, а не дефект.
>
> Ничего по этой спеке не реализовывать. Оставлена в репозитории целиком, не удалена —
> отозванная гипотеза с разбором ошибки полезнее пустого места.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Механизм зависимостей между спеками (`AFTER <SPEC-ID>` в строке backlog) не работает
дольше одного цикла: первый же callback перезаписывает `ai/backlog.md` целиком и стирает
маркер.

Найдено при написании ARCH-209 — эпик расщепления `scripts/vps/`, где TECH-216 обязана
идти после TECH-210. Объявить это оказалось нечем.

## Механизм (подтверждён чтением обоих концов)

**Читатель.** `orchestrator._backlog_deps` (`orchestrator.py:737-755`) берёт зависимости
**только** из строки backlog:

```python
_AFTER_DEP_RE = re.compile(r"\bafter\s+([A-Z]{2,5}-\d+)", re.IGNORECASE)   # :734
```

`_unmet_dependencies` (`:758`) сверяет их статус с lifecycle-SoT и не даёт `scan_queued`
диспатчить спеку с незакрытой зависимостью. Комментарий на `:728-733` называет инцидент,
ради которого это написано: ARCH-1246/FTR-1245 против ещё открытой TECH-1244 на awardybot,
2026-06-20.

**Разрушитель.** `callback._render_and_commit_backlog` (`callback.py:1095-1120`) зовёт
`render_backlog.render_backlog(project_path)` — полную пересборку. Она строит файл с нуля
из lifecycle-YAML (`render_backlog.py:160-220`: `lines = [HEADER]`, группировка по
приоритету, секция Done) и **не читает существующий backlog вообще**. `_render_table_row`
выдаёт `| ID | status | kind | date | [spec](...) |` — места для `AFTER` в этом формате нет.

**Безопасная функция существует и не вызывается отсюда.** `render_backlog.sync_status`
(`:246-273`) переписывает только ячейку статуса, сохраняя каждый остальной байт. Её
docstring говорит прямым текстом:

> Unlike `render_backlog()` (which rebuilds the whole file and destroys founder
> descriptions / section structure / **AFTER markers**), this rewrites just the status value.

`lifecycle.py:332` использует именно `sync_status`. `callback.py:1105` — разрушительную.
Оба пути живые.

## Доказательство

```
grep -n "AFTER " ai/backlog.md   →  0 попаданий
```

Механизм существует в коде с указанием на реальный инцидент, а маркеров в backlog нет
ни одного. Ни у одной спеки за всю историю проекта зависимость не пережила первый callback.

Отказ молчаливый: маркер исчезает, `_backlog_deps` возвращает пустое множество,
`_unmet_dependencies` — пустой список, `scan_queued` диспатчит. В логах ничего.

## Context

Затрагивает все 10 оркестрируемых проектов — код общий.

Прямое следствие для ARCH-209: `TECH-216` (раскол `callback.py`) обязана идти после
`TECH-210` (дедупликация гейта), потому что TECH-210 удаляет из `callback.py` ~270 строк,
вокруг которых иначе будут проведены границы модулей. Объявленный `AFTER TECH-210`
проживёт до первого callback'а.

---

## Scope

**In scope:** callback перестаёт разрушать backlog; `AFTER`-маркеры переживают цикл;
регрессионный тест на выживание маркера.

**Out of scope:** перенос зависимостей в lifecycle-YAML (это была бы смена SoT — отдельное
архитектурное решение, ADR); изменение синтаксиса `AFTER`; графы зависимостей глубже
одного уровня.

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "_render_and_commit_backlog" scripts/vps/` → определение + вызовы из
  `verify_status_sync`
- `grep -rn "render_backlog\.render_backlog" scripts/vps/` → `callback.py:1105` +
  3 тест-файла
- `grep -rn "sync_status" scripts/vps/` → `lifecycle.py:332` + `test_render_backlog.py` (5 кейсов)

### Step 2: DOWN — what depends on?

```
callback.py       → render_backlog (ленивый импорт внутри функции), lifecycle
render_backlog.py → from lifecycle import LIFECYCLE_DIR
```

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/callback.py` | 1105 | зовёт разрушительный рендер | заменить на `sync_status` |
| `scripts/vps/render_backlog.py` | 246 | `sync_status` уже готова | не менять |
| `scripts/vps/render_backlog.py` | 140-220 | `render_backlog()` | оставить для полной пересборки вручную |
| `ai/backlog.md` | — | 0 маркеров `AFTER` | восстановить нечего, история потеряна |

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — `test_render_backlog.py` (7 кейсов), `test_callback.py`
- [x] `tests/**` (корень) — `tests/integration/test_callback_status_sync.py`; **не правится**
- [x] `db/migrations/**` — нет
- [x] `ai/glossary/**` — не существует

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] После правки `AFTER` переживает полный цикл callback'а

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/callback.py` — `_render_and_commit_backlog` на неразрушающий путь (modify)
- `scripts/vps/render_backlog.py` — fallback на полную сборку, если строки ещё нет (modify)
- `scripts/vps/tests/test_render_backlog.py` — регрессия на выживание `AFTER` (modify)
- `scripts/vps/tests/test_callback.py` — покрытие нового пути рендера (modify)
- `docs/orchestrator/components.md` — записать, какой рендер живой и почему (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — отказ обязан быть громким; сейчас зависимость исчезает молча
**Data model:** `ai/backlog.md` — рендер, не SoT (ADR-023). Но `AFTER` живёт **только**
здесь, и это делает его де-факто SoT для одного поля. Записать это противоречие в доки —
часть работы

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

---

## Approaches

### Approach 1: callback переходит на `sync_status`, полная сборка — fallback (выбран)
**Source:** docstring `render_backlog.sync_status:246-257` — функция написана ровно для этого
**Summary:** `_render_and_commit_backlog` читает текущий `ai/backlog.md` из HEAD, зовёт
`sync_status`; если строки спеки в файле нет вообще (новая спека) — дописывает её,
не пересобирая остальное
**Pros:** безопасная функция уже существует, покрыта пятью тестами и используется
`lifecycle.py:332`; правка сводится к смене вызываемого
**Cons:** нужен путь «строки ещё нет» — сейчас `sync_status` такие строки просто пропускает

### Approach 2: Перенести зависимости в lifecycle-YAML
**Summary:** поле `after: [TECH-210]` в `ai/lifecycle/{id}.yaml`, `_backlog_deps` читает его
**Pros:** зависимость переезжает в настоящий SoT, рендер становится неважен
**Cons:** меняет формат lifecycle-YAML на всех 10 проектах и 197 существующих файлах;
требует ADR; Spark не вправе решать такое сам. Правильное направление на будущее,
неправильный размер для бага

### Approach 3: Научить `render_backlog()` сохранять `AFTER`
**Summary:** парсить старый файл, вытаскивать маркеры, вклеивать в новый
**Cons:** восстанавливает одно поле из тех, что перечислены в docstring как разрушаемые
(«founder descriptions / section structure / AFTER markers»). Остальные два останутся
разрушенными, и следующий, кто на это напорется, начнёт сначала

### Selected: 1
**Rationale:** самая узкая правка, которая закрывает дефект. Approach 2 — верное
направление, но это смена SoT, ей место в ADR через `/architect`, а не в багфиксе.
Записать это как upstream-сигнал.

---

## Design

### Что меняется

```python
# callback._render_and_commit_backlog — было
content = render_backlog.render_backlog(project_path)

# стало: читаем текущий backlog из HEAD, синхронизируем только статусы
existing = <git show HEAD:ai/backlog.md>
content = render_backlog.sync_status(project_path, existing)
```

Если `ai/backlog.md` в HEAD отсутствует (новый проект) — падаем на полную сборку
`render_backlog()`, это единственный корректный случай её применения.

Если строки спеки в файле нет (спека родилась только что) — она дописывается в секцию
своего приоритета, остальной файл не трогается.

### Что не меняется

`render_backlog()` остаётся в модуле для ручной полной пересборки и для
`migrate_backlog_to_lifecycle.py`. Она не удаляется — она перестаёт быть тем, что
callback зовёт на каждом цикле.

---

## Implementation Plan

### Research Sources
- `scripts/vps/render_backlog.py:246-273` — `sync_status` и её docstring о разрушении
- `scripts/vps/orchestrator.py:728-771` — читатель `AFTER` и инцидент, ради которого написан
- `.claude/rules/architecture.md` ADR-023 — backlog как рендер

### Task 1: Регрессионный тест (падающий)
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_render_backlog.py`
**Pattern:** `test_sync_status_updates_only_status_preserving_content` — уже существующий кейс
**Acceptance:** тест «`AFTER` переживает `_render_and_commit_backlog`» **падает** на текущем коде

### Task 2: Переключить callback
**Type:** code
**Files:**
  - modify: `scripts/vps/callback.py`
  - modify: `scripts/vps/render_backlog.py`
**Pattern:** `lifecycle.py:321-332` — уже существующий безопасный вызов
**Acceptance:** тест из Task 1 зелёный; статусы по-прежнему синхронизируются

### Task 3: Покрытие и доки
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_callback.py`
  - modify: `docs/orchestrator/components.md`
**Pattern:** —
**Acceptance:** покрыт путь «строки ещё нет»; в доках записано, какой рендер живой

### Execution Order
1 → 2 → 3

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Дефект воспроизведён тестом | Task 1 | ✓ |
| 2 | callback не разрушает backlog | Task 2 | ✓ |
| 3 | Новая спека попадает в файл | Task 2, 3 | ✓ |
| 4 | Статусы синхронизируются как раньше | Task 2 | ✓ |
| 5 | Противоречие записано в доках | Task 3 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | `AFTER` переживает рендер | backlog со строкой `\| TECH-216 \| queued \| TECH \| ... AFTER TECH-210 \|`, затем `_render_and_commit_backlog` | маркер на месте | deterministic | этот баг | P0 |
| EC-2 | Статус всё ещё синхронизируется | lifecycle `done`, backlog `queued` | ячейка стала `done` | deterministic | Rule 5 | P0 |
| EC-3 | Прозаические секции целы | backlog с заголовками и текстом | байт-в-байт кроме ячеек статуса | deterministic | docstring `sync_status` | P0 |
| EC-4 | Новая спека дописывается | lifecycle есть, строки в backlog нет | строка появилась в секции своего приоритета | deterministic | Approach 1 | P0 |
| EC-5 | Отсутствующий backlog | `ai/backlog.md` нет в HEAD | полная сборка, файл создан | deterministic | Approach 1 | P1 |
| EC-6 | `_backlog_deps` видит маркер | backlog после рендера | `{"TECH-210"}` | deterministic | `orchestrator.py:737` | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-7 | TECH-216 с `AFTER TECH-210`, TECH-210 в `queued` | полный цикл: callback → `scan_queued` | TECH-216 **не** диспатчится | integration | ARCH-1246 | P0 |
| EC-8 | То же, TECH-210 переведена в `done` | следующий `scan_queued` | TECH-216 диспатчится | integration | ARCH-1246 | P0 |

### Coverage Summary
Deterministic: 6 | Integration: 2 | LLM-Judge: 0 | Total: 8 (min 3 ✓)

### TDD Order
1. EC-1 — падающий тест первым, он и есть воспроизведение
2. EC-2, EC-3 — не сломать то, что работало
3. EC-4, EC-5 — новые пути
4. EC-6, EC-7, EC-8 — сквозная проверка через читателя

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Модули компилируются | `python -m py_compile scripts/vps/callback.py scripts/vps/render_backlog.py` | exit 0 | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты рендера | — | `cd scripts/vps/tests && python -m pytest -q -k "render_backlog or callback"` | 0 failed |
| AV-F2 | Весь VPS-набор | — | `cd scripts/vps/tests && python -m pytest -q` | 0 failed |
| AV-F3 | Маркер выжил вживую | VPS | добавить `AFTER` в строку, дождаться цикла callback'а, `grep "AFTER " ai/backlog.md` | ≥1 попадание |
| AV-F4 | Демоны на новом коде | VPS | `systemctl --user restart dld-orchestrator dld-gate-daemon && systemctl --user is-active dld-orchestrator dld-gate-daemon` | `active` дважды |

### Verify Command

```bash
python -m py_compile scripts/vps/callback.py scripts/vps/render_backlog.py
cd scripts/vps/tests && python -m pytest -q -k "render_backlog or callback"
grep -c "AFTER " ai/backlog.md
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `AFTER`-маркер переживает полный цикл callback'а
- [ ] Статусы синхронизируются как раньше
- [ ] Новая спека попадает в backlog

### Tests
- [ ] EC-1..EC-8 проходят
- [ ] EC-1 доказанно падал до правки

### Acceptance Verification
- [ ] AV-S1, AV-F1, AV-F2 локально
- [ ] AV-F3, AV-F4 на VPS

### Technical
- [ ] `render_backlog()` не удалена, но больше не вызывается на каждом цикле
- [ ] В `docs/orchestrator/components.md` записано, какой рендер живой

---

## Autopilot Log
