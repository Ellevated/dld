# Feature: [TECH-210] Дедупликация гейта — один источник вместо двух копий

**Priority:** P1 | **Date:** 2026-07-27

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

`callback.py` и `gate_logic.py` держат **шесть** одинаковых функций и семь одинаковых
регэкспов. Синхронизация ручная и записана в код как обещание:

```python
import gate_logic  # noqa: E402 — shared gate helpers, keep the two copies in sync
```

Цена обещания уже заплачена трижды. Каждая правка гейта требовала двух правок:

| Дата | Правка | Где чинили |
|---|---|---|
| 2026-07-02 | plpilot BUG-338 false-blocked, merge-subject форма | обе копии |
| 2026-07-27 | спека закрывалась против собственного birth-коммита | обе копии |
| ARCH-190 Wave 1 | извлечение `gate_logic.py` из `callback.py` | копии созданы, оригиналы не удалены |

Извлечение уже произошло — просто не было доведено до конца. `gate_logic.py` сам
пишет в docstring'ах: «Renamed from `callback._subject_implements`»,
«Copied verbatim from `callback._parse_allowed_files_v1`». `callback.py` уже
импортирует `gate_logic` (строка 38) и уже вызывает из него один символ
(`strip_bookkeeping_paths`, строка 857) — направление зависимости однонаправленное
и закреплено собственным инвариантом `gate_logic.py:19` («FF-09 invariant: ZERO
imports from callback, lifecycle, db, orchestrator»).

Одна из пар уже **разошлась**, молча.

## Context

### Полная карта дублей

| # | `callback.py` | `gate_logic.py` | Состояние |
|---|---|---|---|
| A | `_subject_implements` :741 | `match_subject` :203 | идентичны байт-в-байт |
| B | `_is_done_on_develop` :830 | `find_implementation_commit` :311 | **разошлись** |
| C1 | `_parse_allowed_files_v1` :474 | `_parse_allowed_files_v1` :95 | verbatim |
| C2 | `_parse_allowed_files_legacy` :513 | `_parse_allowed_files_legacy` :134 | verbatim |
| C3 | `_parse_allowed_files` :536 | `parse_allowed_files` :159 | verbatim |
| D | `_fetch_develop` :810 | `fetch_develop` :279 | одна логика |

Плюс 7 регэкспов: `_SPEC_ID_RE`, `_ALLOWED_FILE_EXT_RE`, `_ALLOWED_FILES_V1_HEADING_RE`,
`_ALLOWED_FILES_V1_MARKER_RE`, `_ALLOWED_FILES_V1_BULLET_RE`,
`_ALLOWED_FILES_V1_NUMBERED_RE`, `_NEXT_H2_RE` (`callback.py:443-471` ↔ `gate_logic.py:43-60`).

### Расхождение пары B — сейчас инертно, потом мина

| Аспект | `gate_logic.find_implementation_commit` | `callback._is_done_on_develop` |
|---|---|---|
| Возврат | `str \| None` (SHA коммита) | `bool` |
| `--pretty` | `%H%x00%s` (**полный** SHA) | `%h%x00%s` (**короткий**) |
| Распаковка | `sha, _, subject = ...` | `_, _, subject = ...` (SHA выброшен) |
| Матчер | `match_subject` (свой модуль) | `_subject_implements` (**своя копия**, хотя `gate_logic` импортирован двумя строками выше) |

Сегодня разница не видна, потому что `callback` выбрасывает SHA. Она станет видна в
момент, когда SHA понадобится — и тогда придётся менять сигнатуру функции, под которой
уже лежит разошедшийся формат лога.

### Почему это первым

Это единственная часть работы по 400 LOC, за которой стоит **предъявленный дефект**, а не
рассуждение. `research-devil.md` § Alternative 1 приходит к тому же выводу независимо:
«ship it regardless of what happens to the rest of the proposal». Побочно снимает ~270
строк с `callback.py` — треть пути к лимиту без единой новой абстракции.

---

## Scope

**In scope:** удаление шести функций и семи регэкспов из `callback.py`; перенаправление
всех call-sites на `gate_logic`; переезд `spec_verify.py` на публичный
`gate_logic.parse_allowed_files`; `gate_logic.py` ≤400 LOC; переписывание тестов,
адресующих удалённые имена.

**Out of scope:** раскол `callback.py` на модули (это TECH-216, которая идёт **после**
этой); изменение поведения гейта — семантика обязана остаться побайтово той же;
превращение FF-09-инварианта в тест (`pytest-imports` — отдельная работа).

---

## Impact Tree Analysis

### Step 1: UP — who uses?

- `grep -rn "callback\._subject_implements" scripts/vps/` → **29** попаданий, все в
  `tests/test_callback.py` (прямые ассерты матчера, не monkeypatch)
- `grep -rn "callback\._is_done_on_develop"` → 1 прямая ссылка + 4 `monkeypatch.setattr`
  (`test_callback.py:175, 215, 704, 801`)
- `grep -rn "callback\._fetch_develop"` → 3 `monkeypatch.setattr`
  (`test_callback.py:174, 214, 800`)
- `grep -rn "_parse_allowed_files" scripts/vps/spec_verify.py` → `spec_verify.py:38`,
  `from callback import _parse_allowed_files` — **единственный deep-import в дереве**,
  падает громко (`sys.exit(2)`), не тихо
- `test_claude_runner_timeout.py:216-222` — класс `TestVariantCNeverIntroduced`
  ассертит **текст исходника** `callback.py`: `assert "_fetch_develop(" in source`

### Step 2: DOWN — what depends on?

`callback.py` → `db`, `event_writer`, `gate_logic`, `lifecycle`.
`gate_logic.py` → ничего из `scripts/vps/` (FF-09, подтверждено грепом).
Новых рёбер импорта не появляется — `import gate_logic` уже есть.

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/callback.py` | 443-471 | 7 регэкспов | удалить |
| `scripts/vps/callback.py` | 474, 513, 536 | парсеры allowlist | удалить |
| `scripts/vps/callback.py` | 741, 810, 830 | матчер, fetch, гейт | удалить |
| `scripts/vps/callback.py` | 731, 892, 1257, 1273, 1523 | call-sites | перенаправить на `gate_logic.*` |
| `scripts/vps/spec_verify.py` | 11, 32, 38, 40 | deep-import из `callback` | на `gate_logic.parse_allowed_files` |
| `scripts/vps/tests/test_callback.py` | 29 + 8 мест | ассерты и monkeypatch | переписать |
| `scripts/vps/tests/test_claude_runner_timeout.py` | 194-222 | ассерты по тексту `callback.py` | перенацелить на `gate_logic.py` |

После работы: `grep -n "_subject_implements\|_is_done_on_develop\|_parse_allowed_files"
scripts/vps/callback.py` = **0**.

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — три файла затронуты
- [x] `tests/**` (корень) — `tests/regression/test_callback_spec_corpus.py` гоняет
      корпус спек через парсер allowlist. **Не редактируется** (правило иммутабельных
      тестов), обязан остаться зелёным как есть — он вызывает `callback.main`, не приватные имена
- [x] `db/migrations/**` — в проекте нет
- [x] `ai/glossary/**` — директории не существует (предсуществующий дрейф)

### Verification

- [x] Все найденные файлы в Allowed Files
- [x] grep по удалённым именам в `callback.py` = 0

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/callback.py` — удалить 6 функций и 7 регэкспов, перенаправить call-sites (modify)
- `scripts/vps/gate_logic.py` — единственный источник, довести до ≤400 LOC (modify)
- `scripts/vps/spec_verify.py` — импорт на публичный `gate_logic.parse_allowed_files` (modify)
- `scripts/vps/tests/test_callback.py` — 29 ассертов матчера + 7 monkeypatch (modify)
- `scripts/vps/tests/test_gate_logic.py` — принять кейсы матчера из `test_callback.py` (modify)
- `scripts/vps/tests/test_claude_runner_timeout.py` — перенацелить source-ассерты (modify)
- `.github/workflows/test.yml` — coverage-гейт привязан к имени модуля `callback` (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

### Почему здесь `test.yml`

`.github/workflows/test.yml:69,72` гоняет `--cov=callback --cov-fail-under=54`. Из
`callback.py` уезжает ~270 строк, из которых блок матчера покрыт особенно плотно —
29 прямых ассертов. Удаление **хорошо покрытого** кода понижает общий процент модуля,
даже если ни одна строка не стала непокрытой. Порог может не пройти по арифметике, а не
по существу.

Разрешено скорректировать, **чем именно измеряется** покрытие. **Не разрешено** понижать
`--cov-fail-under=54` — падение порога означает настоящую дыру, и её закрывают тестами.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — гейт fail-closed: любая неоднозначность → `blocked`, не `done`
**Data model:** не затрагивается; статусы пишет `lifecycle`, гейт только читает git

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep` — банка уроков пуста. Gate 7 auto-pass
(no lessons bank). Дефектный след взят напрямую из git-истории и docstring'ов, см. § Why.

---

## Approaches

### Approach 1: Удалить копии из `callback.py`, звать `gate_logic` через атрибут модуля (выбран)
**Source:** `research-web.md` § Approach 1; `research-codebase.md` §9 Reuse Opportunities
**Summary:** шесть функций и семь регэкспов исчезают из `callback.py`; вызовы становятся
`gate_logic.match_subject(...)`, `gate_logic.find_implementation_commit(...)` и т.д.
**Pros:** ноль новых рёбер импорта (импорт уже есть); ноль риска цикла (FF-09);
`monkeypatch.setattr(gate_logic, "...")` продолжает перехватывать, потому что вызов —
это атрибутный поиск в момент вызова, а не связанное при импорте имя
**Cons:** 36 мест в тестах требуют правки; правка громкая (`AttributeError`), не тихая

### Approach 2: Оставить в `callback.py` тонкие обёртки-делегаты
**Source:** `research-web.md` § Best Practice 3 (Feathers — сохранить публичный шов)
**Summary:** `def _subject_implements(s, i): return gate_logic.match_subject(s, i)`
**Pros:** ни один тест не правится; диф минимальный
**Cons:** дублирование не исчезает, а маскируется — остаётся шесть имён, которые читатель
обязан проследить до настоящей реализации; `callback.py` худеет на ~200 строк вместо 270;
и главное — обёртка воспроизводит ровно ту ловушку, о которой предупреждает
`research-devil.md` DA-4: тест патчит `callback._is_done_on_develop`, а
`verify_status_sync` через обёртку уходит в `gate_logic`, и мок не срабатывает молча

### Approach 3: Вынести гейт в третий модуль, оба зовут его
**Source:** `research-web.md` § Approach 3 (facade), применён к гейту
**Summary:** новый `gate_core.py`, и `callback`, и `gate_logic` импортируют его
**Cons:** `gate_logic.py` **уже является** этим третьим модулем — он ровно для этого и
извлечён (ARCH-190 Wave 1 MP-001). Создавать четвёртый слой для той же цели — это
повторить незаконченное извлечение ещё раз

### Selected: 1
**Rationale:** Approach 2 сохраняет тесты ценой того самого молчаливого отказа, который
devil назвал главным новым риском всей затеи. Здесь у нас редкая ситуация, когда громкая
поломка предпочтительнее: удалённое имя даёт `AttributeError` немедленно, а обёртка даёт
не сработавший мок и зелёный тест, гоняющий настоящий git. 36 правок в тестах — цена,
которую видно; молчаливый мок — цена, которую не видно.

---

## Design

### Правило вызова (обязательное, проверяемое)

`callback.py` обязан звать `gate_logic` **через атрибут модуля**:

```python
import gate_logic                                   # ✅ уже есть, строка 38
gate_logic.match_subject(subject, spec_id)          # ✅ поиск атрибута в момент вызова
```

и **никогда** через связывание имени:

```python
from gate_logic import match_subject                # ⛔ связывает имя при импорте
```

Это не стилистика. При `import gate_logic` тест может подменить
`gate_logic.find_implementation_commit`, и `callback` увидит подмену. При
`from ... import ...` — не увидит, и мок молча не сработает. В дереве уже есть живой
пример второй формы: `salvage.py:35` делает `from lifecycle import run_git as _git`.

### Соответствие call-sites

| Было в `callback.py` | Стало | Замечание |
|---|---|---|
| `_subject_implements(subj, id)` | `gate_logic.match_subject(subj, id)` | идентичны, риска нет |
| `_fetch_develop(path)` | `gate_logic.fetch_develop(path)` | `fetch_develop` возвращает `bool`, `_fetch_develop` — `None`; возврат нигде не используется |
| `_is_done_on_develop(...)` → `bool` | `gate_logic.find_implementation_commit(...)` → `str \| None` | все 3 живых call-site используют результат в булевом контексте; `str` истинна, `None` ложна |
| `_parse_allowed_files(path)` | `gate_logic.parse_allowed_files(path)` | сигнатура и возврат совпадают |

**Побочная выгода:** после перехода `callback` начинает логировать полный SHA (`%H`)
вместо короткого — расхождение пары B исчезает само, потому что реализация остаётся одна.

### `spec_verify.py`

```python
from gate_logic import parse_allowed_files      # публичное имя вместо приватного
```

Его собственный docstring обещает «Reuse the canonical allowlist parser — single source
of truth». После правки обещание становится правдой: сейчас он тянет копию.

### `gate_logic.py` ≤400

Файл 402 строки, из них 76 — шапка модуля и комментарии к регэкспам до первой функции.
Резать функции не нужно: сократить дублирующиеся куски docstring'ов, оставив ссылки на
инциденты (BUG-338, TECH-177, birth-commit 2026-07-27) — они несущие. Целевой размер
≤400 без потери ни одного зафиксированного правила.

---

## Implementation Plan

### Research Sources
- `research-codebase.md` §2 — построчная диффа трёх пар, включая `%H`/`%h`
- `research-devil.md` DA-4 — ловушка monkeypatch, определившая выбор подхода
- [Ned Batchelder — One way to fix Python circular imports](https://nedbatchelder.com/blog/202405/one_way_to_fix_python_circular_imports) — различие `import X` и `from X import y`

### Task 1: Перевести call-sites `callback.py` на `gate_logic`
**Type:** code
**Files:**
  - modify: `scripts/vps/callback.py`
**Pattern:** `callback.py:857` — уже существующий вызов `gate_logic.strip_bookkeeping_paths`
**Acceptance:** пять call-sites (731, 892, 1257, 1273, 1523) зовут `gate_logic.*`;
функции ещё на месте, тесты зелёные — это шаг без удаления

### Task 2: Удалить копии и регэкспы
**Type:** code
**Files:**
  - modify: `scripts/vps/callback.py`
**Pattern:** —
**Acceptance:** `grep -cn "_subject_implements\|_is_done_on_develop\|_fetch_develop\|_parse_allowed_files\|_ALLOWED_FILES_V1\|_ALLOWED_FILE_EXT_RE\|_NEXT_H2_RE" scripts/vps/callback.py` = 0;
`wc -l scripts/vps/callback.py` ≈ 1430

### Task 3: `spec_verify.py` на публичный парсер
**Type:** code
**Files:**
  - modify: `scripts/vps/spec_verify.py`
**Pattern:** `gate-daemon.py` — существующий потребитель `gate_logic.parse_allowed_files`
**Acceptance:** `python3 scripts/vps/spec_verify.py <любая спека>` даёт тот же вывод, что до правки

### Task 4: Переписать тесты
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_callback.py`
  - modify: `scripts/vps/tests/test_gate_logic.py`
  - modify: `scripts/vps/tests/test_claude_runner_timeout.py`
**Pattern:** `test_gate_logic.py` — уже содержит тесты матчера в правильной форме
**Acceptance:** 29 ассертов матчера переехали в `test_gate_logic.py` (не удалены — переехали,
каждый кейс сохранён); 7 `monkeypatch.setattr` целятся в `gate_logic.*`; source-ассерты
`TestVariantCNeverIntroduced` читают `gate_logic.py` и сохраняют исходный смысл
(гейт не смеет ходить в голый локальный `develop`)

### Task 5: `gate_logic.py` под 400
**Type:** code
**Files:**
  - modify: `scripts/vps/gate_logic.py`
**Pattern:** —
**Acceptance:** `wc -l scripts/vps/gate_logic.py` ≤ 400; ни одна ссылка на инцидент
(BUG-338, TECH-177, plpilot BUG-346, birth-commit) не потеряна

### Execution Order
1 → 2 → 3 → 4 → 5

Порядок не переставлять: Task 1 отдельно от Task 2 — это разделение «перенаправить» и
«удалить» на два коммита, чтобы при регрессии было видно, какой из двух шагов виноват.

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Гейт вызывается из одного места | Task 1 | ✓ |
| 2 | Копий в `callback.py` не осталось | Task 2 | ✓ |
| 3 | Operator-инструмент не сломан | Task 3 | ✓ |
| 4 | Тесты адресуют живые имена | Task 4 | ✓ |
| 5 | `gate_logic.py` под лимитом | Task 5 | ✓ |
| 6 | Поведение гейта не изменилось | Task 4 (EC-1..EC-4) | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Матчер сохраняет все формы | 29 кейсов из `test_callback.py:355-420` | `gate_logic.match_subject` даёт тот же вердикт на каждом | deterministic | codebase §2 | P0 |
| EC-2 | Birth-коммит по-прежнему не считается реализацией | allowlist `[ai/lifecycle/BUG-460.yaml]`, коммит `lifecycle(BUG-460): queued` | `find_implementation_commit` → `None` | deterministic | инцидент 2026-07-27 | P0 |
| EC-3 | Merge-форма по-прежнему ловится | `Merge branch 'fix/BUG-338-slug'`, allowlist с реальным путём | возвращает SHA | deterministic | plpilot BUG-338 | P0 |
| EC-4 | Body-упоминание по-прежнему НЕ считается | subject `feat(other): x`, в теле `Refs: FTR-925` | `None` | deterministic | TECH-177 | P0 |
| EC-5 | Monkeypatch перехватывает через модуль | `monkeypatch.setattr(gate_logic, "find_implementation_commit", fake)` → `callback.verify_status_sync` | вызывается `fake`, настоящая функция НЕ исполняется | deterministic | devil DA-4 | P0 |
| EC-6 | Удалённые имена отсутствуют | `hasattr(callback, "_is_done_on_develop")` | `False` | deterministic | user | P1 |
| EC-7 | `gate_logic.py` под лимитом | `wc -l scripts/vps/gate_logic.py` | ≤ 400 | deterministic | user | P1 |
| EC-8 | `callback` не связывает имена | `grep "^from gate_logic import" scripts/vps/callback.py` | 0 попаданий | deterministic | design-правило | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-9 | Реальный git-репозиторий с коммитом `fix(TECH-210): x` | полный `verify_status_sync` | статус `done`, тот же audit-JSONL, что до правки | integration | TECH-171 | P0 |
| EC-10 | Существующая спека с v1-маркером | `python3 scripts/vps/spec_verify.py <spec>` | вывод побайтово совпадает с прогоном до правки | integration | devil SA-1 | P0 |
| EC-11 | Корпус регрессии allowlist | `pytest tests/regression/test_callback_spec_corpus.py` | зелёный **без правок самого теста** | integration | правило иммутабельных тестов | P0 |
| EC-12 | Coverage-гейт проходит | команда из `test.yml:65-72` | ≥54%, порог **не понижен** | integration | devil SA-3 | P0 |

### Coverage Summary
Deterministic: 8 | Integration: 4 | LLM-Judge: 0 | Total: 12 (min 3 ✓)

### TDD Order
1. EC-5 **первым** — он определяет, годен ли выбранный паттерн вообще (devil DA-4)
2. EC-1..EC-4 — характеризационные: снять поведение до правки, зафиксировать
3. EC-9..EC-11 — интеграция
4. EC-6..EC-8 — проверки формы, последними

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | `callback.py` компилируется | `python -m py_compile scripts/vps/callback.py` | exit 0 | 15s |
| AV-S2 | Импорт без побочных эффектов | `PYTHONPATH=scripts/vps python -c "import gate_logic"` | exit 0, нет вывода | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты VPS зелёные | — | `cd scripts/vps/tests && python -m pytest -q` | ≥419 passed, 0 failed |
| AV-F2 | Корневые тесты не деградировали | — | `python -m pytest tests/ -q --ignore=tests/integration/test_claude_runner_post_result_exception.py` | 184 passed, 6 failed (те же 6 предсуществующих Windows-падений, не больше) |
| AV-F3 | Operator-инструменты живы | — | `python3 scripts/vps/spec_verify.py ai/features/TECH-208-*.md` | exit 0 |
| AV-F4 | Демоны на новом коде | VPS | `systemctl --user restart dld-orchestrator dld-gate-daemon && systemctl --user is-active dld-orchestrator dld-gate-daemon` | `active` дважды |

### Verify Command

```bash
python -m py_compile scripts/vps/callback.py scripts/vps/gate_logic.py scripts/vps/spec_verify.py
grep -c "_subject_implements\|_is_done_on_develop\|_fetch_develop\|_parse_allowed_files" scripts/vps/callback.py
wc -l scripts/vps/callback.py scripts/vps/gate_logic.py
cd scripts/vps/tests && python -m pytest -q
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] Шесть функций и семь регэкспов удалены из `callback.py`
- [ ] Все call-sites зовут `gate_logic.*` через атрибут модуля
- [ ] `spec_verify.py` использует публичный `gate_logic.parse_allowed_files`
- [ ] `gate_logic.py` ≤ 400 LOC

### Tests
- [ ] EC-1..EC-11 проходят
- [ ] 29 кейсов матчера **переехали**, ни один не потерян
- [ ] `tests/regression/test_callback_spec_corpus.py` зелёный без правок

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2, AV-F3 локально
- [ ] AV-F4 на VPS — **рестарт демонов обязателен**: они держат старый код в памяти,
      на этом уже потеряли цикл 2026-07-27

### Technical
- [ ] Поведение гейта не изменилось ни в одном из 11 EC
- [ ] `grep "^from gate_logic import" scripts/vps/callback.py` = 0

---

## Autopilot Log
