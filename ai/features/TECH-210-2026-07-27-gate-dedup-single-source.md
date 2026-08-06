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

После работы (уточнено 2026-07-28 под решение «алиас»):

```
grep -c "_subject_implements\|_is_done_on_develop\|_fetch_develop" scripts/vps/callback.py  → 0
grep -c "^def _parse_allowed_files"                                 scripts/vps/callback.py  → 0
grep -c "^_parse_allowed_files = gate_logic.parse_allowed_files"    scripts/vps/callback.py  → 1
```

То есть определений парсера не остаётся ни одного, остаётся одно присваивание имени.

### Step 4: CHECKLIST — mandatory folders

- [x] `scripts/vps/tests/**` — три файла затронуты
- [x] `tests/**` (корень) — **исправлено 2026-07-28.** Первая редакция утверждала, что
      `tests/regression/test_callback_spec_corpus.py` «вызывает `callback.main`, не
      приватные имена». **Ложь**: строка 45 — `actual = callback._parse_allowed_files(spec_path)`.
      Утверждение сделано без чтения файла, и Step 1 грепал только `scripts/vps/`.
      Фактически корневое дерево держит ~70 обращений к удаляемым именам в 10 файлах.
      После решения от 2026-07-28 (алиас на парсер) правятся **два**:
      `tests/unit/test_callback_branch_awareness.py` и
      `tests/unit/test_callback_implementation_guard.py` — оба в Allowed Files.
      Остальные восемь, включая иммутабельный regression-корпус, ходят через алиас
      и не трогаются
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
- `tests/unit/test_callback_branch_awareness.py` — BUG-1039 regression по `_is_done_on_develop` (modify)
- `tests/unit/test_callback_implementation_guard.py` — TECH-166 guard, 14 ассертов (modify)
- `scripts/vps/tests/test_gate_logic_subject.py` — вынос кейсов матчера, если файл не влезает в 600 (NEW)
- `tests/integration/test_callback_already_merged.py` — 22 monkeypatch на gate-функции, DA-4 (modify)
- `tests/integration/test_callback_feature_branch.py` — 22 monkeypatch на gate-функции, DA-4 (modify)
- `tests/integration/test_callback_status_sync.py` — 22 monkeypatch на gate-функции, DA-4 (modify)
- `tests/integration/test_callback_no_impl_demote.py` — 22 monkeypatch на gate-функции, DA-4 (modify)
- `tests/integration/test_callback_blocked_no_dispatch.py` — 22 monkeypatch на gate-функции, DA-4 (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

> ## ✅ РЕШЕНО 2026-08-07 — owner approval for cycle-2 ACTION REQUIRED
>
> Владелец одобрил расширение `## Allowed Files` пятью интеграционными тест-файлами
> ровно как запрошено в блоке ACTION REQUIRED (цикл 2, 2026-07-28): перенацелить их
> 22 `monkeypatch.setattr(callback, "_fetch_develop"/"_is_done_on_develop", ...)` на
> `gate_logic.fetch_develop`/`gate_logic.find_implementation_commit`
> (`True` → строка-SHA, `False` → `None`). Поправки D2/D3/§7 из того же блока —
> применить вместе. Блокер снят, спека исполнима.

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

> **Plan re-verified against the worktree on 2026-08-07 (cycle 3).** Every number below was
> re-read from the files in `.worktrees/TECH-210`, not copied forward. Where this section
> contradicts §Context, §Impact Tree or the §Autopilot Log, **this section wins**.
> Corrections made in this pass are marked **[DRIFT-N]** and are binding.
>
> **Both prior blockers are RESOLVED by owner approval.** The parser survives as a one-line
> alias; the five `tests/integration/test_callback_*.py` files are in `## Allowed Files`.
> Task 2 has no STOP-condition any more. Do not re-block on either.

### Drift Log — 2026-08-07 re-verification

**Unchanged (re-read, still exactly true — do not "fix" these):**

| Claim | Status |
|---|---|
| `callback.py` = 1698 LOC | ✓ |
| Every row of the Verified line map (43-45, 447, 451-459, 467-471, 474-510, 513-533, 536-572, 741-807, 810-827, 830-894) | ✓ byte-exact |
| `_SPEC_ID_RE` live users at 329, 335, 347 inside `resolve_spec_id` | ✓ — **must NOT be deleted** |
| `_ALLOWED_FILES_HEADING_RE` (467-470) sole consumer is `_parse_allowed_files_legacy:525` | ✓ — **must go** |
| 9 live call-sites: 731, 1217, 1255, 1257, 1272, 1273, 1514, 1522, 1523 | ✓ still 9, all boolean-context |
| `spec_verify.py`: docstring 11, comment 32, try 39, from-import 40, print 42, `sys.exit` 43, call-site 230 | ✓ |
| `test_callback.py` monkeypatch 174, 175, 214, 215 | ✓ |
| Matcher class heads 351 / 390 / 418 / 450 (parity class ends 490) | ✓ |
| `test_callback_branch_awareness.py` gate asserts 75, 94, 106, 118, 132, 144 | ✓ |
| `test_callback_implementation_guard.py` gate asserts 114, 123, 133, 146, 173 | ✓ |
| `gate_logic.py` = 402 LOC; stale docstring lines at 102, 141, 162 | ✓ |
| `test.yml` `--cov=callback` on :69, `--cov-fail-under=54` on :72 | ✓ |
| `test_claude_runner_timeout.py` = 222 LOC | ✓ |
| `tests/integration/` monkeypatch total = 22 | ✓ |

**Drifted (corrected below — coder uses the NEW number):**

| ID | Was stated | Actually is |
|---|---|---|
| **[DRIFT-1]** | `test_gate_logic.py` 720 LOC | **723** |
| **[DRIFT-2]** | `test_callback.py` 870 LOC | **869** |
| **[DRIFT-3]** | monkeypatch at 690, 704, 800, 801 | **689, 703, 799, 800** (−1) |
| **[DRIFT-4]** | `_delayed_is_done` body 692-702, comment 544 | **691-701** (`return False` on **694**), comment **543** |
| **[DRIFT-5]** | Task 4c: 196, 199, 201, 204, 212, 218, 220-221 | **200, 203, 204, 206, 213, 219, 221-222** |
| **[DRIFT-6]** | D2: docstring 195, comment 219; tests at 194-214 / 216-222 | docstring **199**, comment **220**; tests at **198-215** / **217-222** |
| **[DRIFT-7]** | `test_callback_status_sync.py` 334/335 | **343/344** (+9) |
| **[DRIFT-8]** | `test_callback_blocked_no_dispatch.py` 192/193 | **174/175** (−18) |
| **[DRIFT-9]** | §7: "13 matcher cases migrate" | **14** — §7 missed `feat(other): see also FTR-925` (441) / `feat(other): see FTR-925` (480) |
| **[DRIFT-10]** | Task 5: "cut exactly 3 docstring lines 102/141/162" | Cutting only those 3 leaves orphan blank lines inside two docstrings. Correct edit: delete **101-102** and **140-141** (4 lines), **rewrite 162 in place** → **398 LOC** |
| **[DRIFT-11]** | AV-F1 "≥419 passed"; log's "498 passed" | **606 passed, 0 failed** (measured in this worktree, 2026-08-07) |
| **[DRIFT-12]** | AV-F2 "184 passed, 6 failed"; log's "187 passed, 3 failed" | **242 passed, 1 skipped, 0 failed.** There are **no** pre-existing failures left. AV-F2 must be read against **242 / 0-failed** — any red root test after this work is caused by this work |

**Drift class: light.** Nothing was deleted, renamed or moved; the callback/gate_logic
production surface is byte-identical to what cycle 2 measured. All twelve items are
line-number and count corrections, fixed in place here. No `/council` escalation.

### Research Sources
- `research-codebase.md` §2 — построчная диффа трёх пар, включая `%H`/`%h`
- `research-devil.md` DA-4 — ловушка monkeypatch, определившая выбор подхода
- [Ned Batchelder — One way to fix Python circular imports](https://nedbatchelder.com/blog/202405/one_way_to_fix_python_circular_imports) — различие `import X` и `from X import y`

### Hard constraints (restated — Coder must not relax any of these)

1. `callback.py` зовёт только через атрибут модуля: `gate_logic.match_subject(...)`.
   `from gate_logic import ...` в `callback.py` — **запрещено** (ломает monkeypatch, EC-5/EC-8).
   Правило действует ТОЛЬКО для `callback.py`; в `spec_verify.py` форма `from` допустима,
   и там она предпочтительна.
2. Семантика гейта не меняется ни в одном из **EC-1..EC-14**. Ни один тест не удаляется
   «чтобы позеленело»: удаляются только те кейсы, что дословно переехали в другой файл.
3. Трогать можно ТОЛЬКО файлы из `## Allowed Files` (их **15**). Ничего больше — даже если
   тест красный. Расширять список автопилоту запрещено (BUG-199 fence).
4. `--cov-fail-under=54` в `.github/workflows/test.yml:72` **понижать нельзя** — ни на единицу.
   Менять разрешено только **чем** измеряется (строка **69**, `--cov=callback` →
   `--cov=callback --cov=gate_logic`), и только если прогон реально красный.
5. `tests/regression/**` и `tests/contracts/**` неприкосновенны (правило проекта + EC-11).
   `tests/regression/test_callback_spec_corpus.py:45` зовёт `callback._parse_allowed_files`
   напрямую — ради него и живёт алиас.
6. **Ни один коммит не оставляет дерево красным.** Где перенаправление call-site и правка
   его monkeypatch-мишеней неразделимы, они идут ОДНИМ коммитом (Task 2, Task 4) — это
   сознательное отступление от «≤3 файла на задачу», обоснованное в самих задачах.
7. `tests/integration/**` — ADR-013 (mock ban, hook-enforced). Новых моков не добавляется:
   существующие `monkeypatch.setattr` только меняют мишень с `callback.*` на `gate_logic.*`.
   Если hook заругается — это баг перенацеливания, а не повод добавить `# noqa`.

### Verified line map (`scripts/vps/callback.py`, 1698 LOC)

| Что | Строки | Судьба |
|---|---|---|
| `import gate_logic` | 38 | остаётся (комментарий «keep the two copies in sync» переписать) |
| `_SPEC_ID_RE` | 43-45 | **ОСТАЁТСЯ** — см. [VERIFIED-FIX 1] |
| `_ALLOWED_FILE_EXT_RE` | 443-447 | удалить |
| `_ALLOWED_FILES_V1_HEADING_RE` | 449-451 | удалить |
| `_ALLOWED_FILES_V1_MARKER_RE` | 452-453 | удалить |
| `_ALLOWED_FILES_V1_BULLET_RE` | 454-455 | удалить |
| `_ALLOWED_FILES_V1_NUMBERED_RE` | 456-459 | удалить |
| `_ALLOWED_FILES_HEADING_RE` | 461-470 | удалить — **не был в списке спеки** [VERIFIED-FIX 1] |
| `_NEXT_H2_RE` | 471 | удалить |
| `_parse_allowed_files_v1` | 474-510 | удалить |
| `_parse_allowed_files_legacy` | 513-533 | удалить |
| `_parse_allowed_files` | 536-572 | удалить |
| `_subject_implements` | 741-807 | удалить |
| `_fetch_develop` | 810-827 | удалить |
| `_is_done_on_develop` | 830-894 | удалить |

Баннер `# --- TECH-166 / TECH-167: Implementation guard helpers ---` (441) **оставить** —
под ним продолжают жить `_get_started_at` (575), `_audit_log_path` (591), `_commit_stats` (627),
`_detect_out_of_scope_files` (692).

`import re` (27) и `import subprocess` (28) **остаются** — у обоих есть живые потребители
вне удаляемого кода (`re`: 45/224/345/393; `subprocess`: 97/162/297/356/386/655/717/947/971/1237).

**Живые call-sites (9, а не 5):**

| Строка | Сейчас | Станет |
|---|---|---|
| 731 | `_subject_implements(current_subject, spec_id)` | `gate_logic.match_subject(current_subject, spec_id)` |
| 1217 | `_parse_allowed_files(spec_file)` | `gate_logic.parse_allowed_files(spec_file)` |
| 1255 | `_fetch_develop(project_path)` | `gate_logic.fetch_develop(project_path)` |
| 1257 | `if _is_done_on_develop(project_path, spec_id, allowed):` | `if gate_logic.find_implementation_commit(project_path, spec_id, allowed):` |
| 1272 | `_fetch_develop(project_path)` | `gate_logic.fetch_develop(project_path)` |
| 1273 | `if _is_done_on_develop(project_path, spec_id, allowed):` | `if gate_logic.find_implementation_commit(project_path, spec_id, allowed):` |
| 1514 | `_parse_allowed_files(spec_file)` | `gate_logic.parse_allowed_files(spec_file)` |
| 1522 | `_fetch_develop(project_path)` | `gate_logic.fetch_develop(project_path)` |
| 1523 | `if _is_done_on_develop(project_path, spec_id, allowed):` | `if gate_logic.find_implementation_commit(project_path, spec_id, allowed):` |

Строка **892** (`_subject_implements` внутри `_is_done_on_develop`) в этом списке **отсутствует
намеренно**: она живёт внутри удаляемой функции и исчезает вместе с ней. Спека числила её
как call-site для перенаправления — это ошибка учёта.

### [VERIFIED-FIX 1] — состав семи регэкспов другой

`_SPEC_ID_RE` (callback.py:45) используется **вне** удаляемого кода: строки **329, 335, 347**
внутри `resolve_spec_id`, который никуда не уезжает. Удалить его = `NameError` на резолве
spec_id из pueue-лейбла, то есть сломать callback целиком.

Зато `_ALLOWED_FILES_HEADING_RE` (461-470) в списке спеки отсутствовал, а удалять его надо —
единственный потребитель `_parse_allowed_files_legacy` уезжает.

Итог: удаляемых регэкспов по-прежнему семь, но множество другое:
**−`_SPEC_ID_RE`, +`_ALLOWED_FILES_HEADING_RE`**. `gate_logic` держит собственную копию
`_SPEC_ID_RE` (gate_logic.py:36), она используется только внутри `match_subject` — дубль
остаётся сознательно и в scope этой спеки не входит.

### [VERIFIED-FIX 2] — сверка сигнатур (утверждение «байт-в-байт» проверено)

| Пара | `callback` | `gate_logic` | Вердикт |
|---|---|---|---|
| A | `_subject_implements(subject: str, spec_id: str) -> bool` :741 | `match_subject(subject: str, spec_id: str) -> bool` :203 | сигнатура и тело **идентичны** (779-807 ≡ 248-276); различаются только docstring'и. Claim подтверждён |
| C1 | `_parse_allowed_files_v1(spec_text: str) -> list[str] \| None` :474 | то же имя/сигнатура :95 | тело идентично; в callback два лишних комментария (502-503) |
| C2 | `_parse_allowed_files_legacy(spec_text: str) -> list[str] \| None` :513 | то же :134 | идентично |
| C3 | `_parse_allowed_files(spec_path: Path) -> list[str] \| None` :536 | `parse_allowed_files(spec_path: Path) -> list[str] \| None` :159 | логика идентична. **Два отличия в наблюдаемом выводе:** log-строки используют `→` (U+2192) в callback и `->` в gate_logic; логгер меняется с `callback` на `gate_logic`. Гейт от этого не меняется, но операторские грепы по логам — да |
| D | `_fetch_develop(project_path: str) -> None`, **timeout=30** :810 | `fetch_develop(project_path: str, timeout: int = 15) -> bool` :279 | **не «одна логика»**: лишний defaulted-аргумент, другой возврат и **бюджет fetch урезается вдвое** (30s → 15s). Возврат нигде не используется; урезание таймаута — сознательно принимаемое последствие (best-effort fetch, gate fail-closed), но это изменение поведения, и его надо назвать вслух |
| B | `_is_done_on_develop(...) -> bool`, `%h` :830 | `find_implementation_commit(...) -> str \| None`, `%H` :311 | позиционные аргументы совпадают; возврат/pretty/текст WARNING'а различаются. Все 3 живых call-site используют результат в булевом контексте — безопасно |

### [VERIFIED-FIX 3] — БЫВШИЙ BLOCKER, снят; разбор сохранён

> **Снят дважды и окончательно.** 2026-07-28 владелец выбрал вариант **(a)** — алиас на
> парсер (см. Task 4 шаг 2). 2026-08-07 владелец добавил в `## Allowed Files` пять
> `tests/integration/test_callback_*.py`, что закрыло остаток DA-4 (см. Task 2).
> Всего в `## Allowed Files` теперь **15** файлов, и их достаточно: перепроверено грепом
> 2026-08-07 — вне списка не осталось ни одной ссылки на удаляемые имена, кроме
> `tests/regression/test_callback_spec_corpus.py:45`, которая ходит через алиас.
> **STOP-условия в плане больше нет. Повторно блокироваться по этому пункту запрещено.**

`## Impact Tree` грепал только `scripts/vps/`. Корневое дерево `tests/` содержит **~70**
обращений к удаляемым именам:

| Файл | Обращений | В Allowed Files? | Иммутабелен? |
|---|---|---|---|
| `tests/regression/test_callback_spec_corpus.py` :45 | 1 (`callback._parse_allowed_files(spec_path)`) | нет | **ДА** |
| `tests/unit/test_callback_parser.py` | 19 | нет | нет |
| `tests/unit/test_callback_implementation_guard.py` | 14 | нет | нет |
| `tests/unit/test_callback_allowlist_v1.py` | 11 | нет | нет |
| `tests/unit/test_callback_branch_awareness.py` | 7 | нет | нет |
| `tests/integration/test_callback_already_merged.py` | 13 | нет | нет |
| `tests/integration/test_callback_feature_branch.py` | 7 | нет | нет |
| `tests/integration/test_callback_blocked_no_dispatch.py` | 3 | нет | нет |
| `tests/integration/test_callback_no_impl_demote.py` | 2 | нет | нет |
| `tests/integration/test_callback_status_sync.py` | 2 | нет | нет |

Спека прямо утверждает обратное («он вызывает `callback.main`, не приватные имена») —
утверждение **ложно**, проверено чтением файла: строка 45 вызывает приватное имя напрямую,
и падёт на `AttributeError` во всех 25+ параметризованных кейсах.

Это ровно те файлы, которые гоняет coverage-гейт `test.yml:65-72`, то есть EC-12 падает вместе
с EC-11.

**Противоречие неразрешимо внутри текущих границ спеки:** DoD требует удалить
`_parse_allowed_files`, EC-11 + правило проекта требуют, чтобы неизменённый
`tests/regression/test_callback_spec_corpus.py` остался зелёным. Одновременно выполнить нельзя.

Требуется решение владельца (одно из):
- **(a)** расширить `## Allowed Files` девятью `tests/unit/**` + `tests/integration/**` файлами и
  оставить в `callback.py` **ровно один** тонкий делегат `_parse_allowed_files = gate_logic.parse_allowed_files`
  ради иммутабельного корпуса. Ловушка DA-4 здесь не срабатывает: ни один тест в дереве не
  патчит `callback._parse_allowed_files` (проверено грепом) — это чистый парсер, а не точка мока;
- **(b)** то же расширение + разовое разрешение владельца на правку одной строки в
  `tests/regression/test_callback_spec_corpus.py:45`;
- **(c)** сузить спеку: удалить только матчер + гейт + fetch, а три парсера
  (`_parse_allowed_files*`) оставить до отдельной спеки.

### Task 1: Перенаправить три немокаемых call-site `callback.py` → `gate_logic`
**Type:** code
**Files:**
  - Modify: `scripts/vps/callback.py:38`, `:731`, `:1217`, `:1514`

**Context.** Три из девяти call-sites (`_subject_implements` ×1, `_parse_allowed_files` ×2)
**никем в дереве не патчатся** — проверено грепом по всему репозиторию: `monkeypatch.setattr`
на эти два имени = 0. Значит их можно перевести отдельным коммитом, не трогая ни одного теста,
и дерево останется зелёным. Шесть оставшихся (гейт + fetch) патчатся 26 раз и едут в Task 2.

**Steps:**

1. Показать, что сейчас вызовы локальные:
   ```bash
   cd /home/dld/projects/dld/.worktrees/TECH-210
   grep -n "_subject_implements(current_subject\|_parse_allowed_files(spec_file)" scripts/vps/callback.py
   ```
   Ожидаемо ровно 3 строки: `731`, `1217`, `1514`.

2. Правки (посимвольно):

   `:38` — комментарий больше не описывает реальность, переписать строку целиком:
   ```python
   import gate_logic  # noqa: E402 — single source of gate logic (TECH-210)
   ```

   `:731`
   ```python
               is_spec_commit = gate_logic.match_subject(current_subject, spec_id)
   ```

   `:1217`
   ```python
       allowed = gate_logic.parse_allowed_files(spec_file) if spec_file else None
   ```

   `:1514`
   ```python
               allowed = gate_logic.parse_allowed_files(spec_file) if spec_file else None
   ```
   (отступ на 1514 — 12 пробелов, он внутри `try:` внутри `if`; на 1217 — 4. Скопировать
   отступ из существующей строки, не набирать заново.)

3. Проверка:
   ```bash
   python -m py_compile scripts/vps/callback.py                       # exit 0
   grep -c "^from gate_logic import" scripts/vps/callback.py          # 0
   cd scripts/vps/tests && python -m pytest -q                        # 606 passed, 0 failed
   cd /home/dld/projects/dld/.worktrees/TECH-210 && python -m pytest tests/ -q   # 242 passed, 1 skipped, 0 failed
   ```

**Acceptance:**
- оба прогона зелёные ровно на baseline-числах (**606 / 0** и **242 / 1 skipped / 0**) — EC-9, EC-11, EC-12
- `grep -c "^from gate_logic import" scripts/vps/callback.py` = 0 — **EC-8**
- ни одна функция не удалена: `grep -c "^def _subject_implements\|^def _parse_allowed_files" scripts/vps/callback.py` = 4
- отдельный коммит

---

### Task 2: Атомарный своп гейта — call-sites + все 26 monkeypatch-мишеней
**Type:** code + test
**Files (9 — сознательное превышение «≤3», см. Context):**
  - Test: `scripts/vps/tests/test_callback.py` (EC-5 новый, + 4 monkeypatch)
  - Modify: `scripts/vps/callback.py:1255,1257,1272,1273,1522,1523`
  - Modify: `tests/integration/test_callback_already_merged.py` (10)
  - Modify: `tests/integration/test_callback_feature_branch.py` (6)
  - Modify: `tests/integration/test_callback_status_sync.py` (2)
  - Modify: `tests/integration/test_callback_no_impl_demote.py` (2)
  - Modify: `tests/integration/test_callback_blocked_no_dispatch.py` (2)
  - Modify: `tests/unit/test_callback_branch_awareness.py` (6 прямых вызова)
  - Modify: `tests/unit/test_callback_implementation_guard.py` (5 прямых вызова)

**Context — почему одним коммитом.** Это ловушка DA-4 в чистом виде. В момент, когда
`callback.py:1257` начинает звать `gate_logic.find_implementation_commit`, все 22
`monkeypatch.setattr(callback, "_is_done_on_develop", ...)` в `tests/integration/`
становятся **инертными** — не падают, а молча пропускают настоящий гейт в tmp-репозиторий
без implementation-коммита, и `done` переворачивается в `blocked`. Обратный порядок
(сначала тесты) ломает ровно так же. Свопнуть можно только вместе. Правило «≤3 файла»
уступает правилу «ни одного красного коммита» — и это записано здесь, а не в чьей-то памяти.

**Steps:**

1. **EC-5 первым (TDD, devil DA-4 — он решает, годен ли паттерн вообще).**
   В `scripts/vps/tests/test_callback.py` добавить `import gate_logic  # noqa: E402`
   рядом с `import callback` (:24-26) и новый класс в конец файла:
   ```python
   class TestGateLogicMonkeypatchIntercepts:
       """EC-5 / devil DA-4: патч gate_logic ДОЛЖЕН перехватывать вызов из callback.

       Если callback снова свяжет имя через `from gate_logic import ...`, патч станет
       инертным и настоящий гейт побежит по tmp-репозиторию — тест покраснеет.
       """

       def test_find_implementation_commit_patch_reaches_callback(self, tmp_path, monkeypatch):
           calls = []

           def _fake(project_path, spec_id, allowed_files):
               calls.append(spec_id)
               return "deadbee"

           monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
           monkeypatch.setattr(gate_logic, "find_implementation_commit", _fake)
           origin, repo = _make_origin_repo(tmp_path)
           (repo / "ai" / "features").mkdir(parents=True)
           (repo / "ai" / "features" / "TECH-EC5-x.md").write_text(
               "# TECH-EC5\n\n## Allowed Files\n\n- `src/g.py`\n", encoding="utf-8"
           )
           lifecycle.write_lifecycle(str(repo), "TECH-EC5", "in_progress")
           monkeypatch.setattr(callback, "_commit_stats", lambda *a: (10, 0, 1))

           callback.verify_status_sync(str(repo), "TECH-EC5", target="blocked")

           assert calls == ["TECH-EC5"], "gate_logic patch did not intercept callback"
   ```
   Запустить — **должен упасть** (`calls == []`, потому что `callback` ещё зовёт свою копию):
   ```bash
   cd scripts/vps/tests && python -m pytest test_callback.py -q -k TestGateLogicMonkeypatchIntercepts
   # ожидаемо: 1 failed — assert [] == ['TECH-EC5']
   ```
   *Если сигнатура `verify_status_sync` не принимает такой вызов — скопировать форму вызова
   из соседнего теста `TestGraceRetry` (`test_callback.py:707-712`), не изобретать.*

2. **`callback.py` — шесть строк.** Ничего не удалять, тела функций остаются:

   | Строка | Было | Стало |
   |---|---|---|
   | 1255 | `_fetch_develop(project_path)` | `gate_logic.fetch_develop(project_path)` |
   | 1257 | `if _is_done_on_develop(project_path, spec_id, allowed):` | `if gate_logic.find_implementation_commit(project_path, spec_id, allowed):` |
   | 1272 | `_fetch_develop(project_path)` | `gate_logic.fetch_develop(project_path)` |
   | 1273 | `if _is_done_on_develop(project_path, spec_id, allowed):` | `if gate_logic.find_implementation_commit(project_path, spec_id, allowed):` |
   | 1522 | `_fetch_develop(project_path)` | `gate_logic.fetch_develop(project_path)` |
   | 1523 | `if _is_done_on_develop(project_path, spec_id, allowed):` | `if gate_logic.find_implementation_commit(project_path, spec_id, allowed):` |

   Все три результата используются **только** в булевом контексте (проверено чтением
   1248-1285 и 1508-1535) — `str` истинна, `None` ложна, `if`-ветки не меняются.
   Возврат `fetch_develop` (`bool` вместо `None`) нигде не читается.

3. **`scripts/vps/tests/test_callback.py` — 4 monkeypatch + 1 комментарий**
   *(номера **[DRIFT-3]/[DRIFT-4]**, сдвиг −1 от прежнего плана):*

   | Строка | Было | Стало |
   |---|---|---|
   | 174 | `setattr(callback, "_fetch_develop", lambda *a: None)` | `setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)` |
   | 175 | `setattr(callback, "_is_done_on_develop", lambda *a: True)` | `setattr(gate_logic, "find_implementation_commit", lambda *a: "deadbee")` |
   | 214 | `setattr(callback, "_fetch_develop", lambda *a: None)` | `setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)` |
   | 215 | `setattr(callback, "_is_done_on_develop", lambda *a: False)` | `setattr(gate_logic, "find_implementation_commit", lambda *a: None)` |
   | **689** | `original_is_done = callback._is_done_on_develop` | `original_is_done = gate_logic.find_implementation_commit` |
   | **694** | `return False  # first check: not visible yet` | `return None  # first check: not visible yet` |
   | **703** | `setattr(callback, "_is_done_on_develop", _delayed_is_done)` | `setattr(gate_logic, "find_implementation_commit", _delayed_is_done)` |
   | **799** | `setattr(callback, "_fetch_develop", lambda *a: None)` | `setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)` |
   | **800** | `setattr(callback, "_is_done_on_develop", lambda *a: False)` | `setattr(gate_logic, "find_implementation_commit", lambda *a: None)` |
   | **543** | `# Do NOT stub _fetch_develop or _is_done_on_develop — let them run real` | `# Do NOT stub gate_logic.fetch_develop or find_implementation_commit — let them run real` |

   `_delayed_is_done` (**691-701**) остаётся функцией того же тела; меняется только `return False`
   → `return None` на **694**. Хвостовой `return original_is_done(pp, sid, af)` (**701**) теперь
   вернёт SHA-строку — это и есть желаемое.
   Строка 543 — комментарий теста EC-9, который **намеренно** гоняет настоящий git. Поведение
   не менять, только имена в тексте.

4. **Пять `tests/integration/` — 22 monkeypatch. Полная таблица (перепроверена 2026-08-07):**

   В каждый из пяти файлов добавить `import gate_logic  # noqa: E402` сразу после
   `import callback  # noqa: E402`.

   | Файл | Строка | Было (`callback`) | Стало (`gate_logic`) |
   |---|---|---|---|
   | `test_callback_already_merged.py` | 150 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 151 | `"_is_done_on_develop", lambda *a: True` | `"find_implementation_commit", lambda *a: "deadbee"` |
   | | 169 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 170 | `"_is_done_on_develop", lambda *a: False` | `"find_implementation_commit", lambda *a: None` |
   | | 193 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 194 | `"_is_done_on_develop", lambda *a: False` | `"find_implementation_commit", lambda *a: None` |
   | | 219 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 220 | `"_is_done_on_develop", lambda *a: False` | `"find_implementation_commit", lambda *a: None` |
   | | 242 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 243 | `"_is_done_on_develop", lambda *a: True` | `"find_implementation_commit", lambda *a: "deadbee"` |
   | `test_callback_feature_branch.py` | 141 | комментарий `# _is_done_on_develop sees only origin/develop → False` | `# find_implementation_commit sees only origin/develop → None` |
   | | 142 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 143 | `"_is_done_on_develop", lambda *a: False` | `"find_implementation_commit", lambda *a: None` |
   | | 164 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 165 | `"_is_done_on_develop", lambda *a: True` | `"find_implementation_commit", lambda *a: "deadbee"` |
   | | 183 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 184 | `"_is_done_on_develop", lambda *a: False` | `"find_implementation_commit", lambda *a: None` |
   | `test_callback_status_sync.py` **[DRIFT-7]** | **343** | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | **344** | `"_is_done_on_develop", lambda *a: True` | `"find_implementation_commit", lambda *a: "deadbee"` |
   | `test_callback_no_impl_demote.py` | 180 | `"_fetch_develop", lambda *a: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | 181 | `"_is_done_on_develop", lambda *a: True` | `"find_implementation_commit", lambda *a: "deadbee"` |
   | `test_callback_blocked_no_dispatch.py` **[DRIFT-8]** | **174** | `"_fetch_develop", lambda *a, **kw: None` | `"fetch_develop", lambda *a, **kw: True` |
   | | **175** | `"_is_done_on_develop", lambda *a, **kw: merged_on_develop` | `"find_implementation_commit", lambda *a, **kw: "deadbee" if merged_on_develop else None` |

   Плюс docstring'и, называющие старые имена (только текст, не логика):
   `test_callback_already_merged.py` **:7, :9, :10**;
   `test_callback_blocked_no_dispatch.py` **:164**.

   ⚠️ **`blocked_no_dispatch:175` — единственный параметризованный стаб.** `merged_on_develop`
   это `bool` (дефолт `False`, `_run_main` :155). Прямая замена на `lambda: merged_on_develop`
   вернула бы `True`/`False` вместо `str | None` — гейт бы отработал, но тип соврал бы.
   Нужна именно тернарная форма выше. Прошлая редакция плана числила этот файл как «стаба
   `→ True` нет» — неверно, он есть, просто через параметр.

5. **`tests/unit/test_callback_branch_awareness.py` — 6 прямых вызовов (D3).**
   Добавить `import gate_logic  # noqa: E402` после `import callback` (:25).

   | Строка | Было | Стало |
   |---|---|---|
   | 75 | `assert callback._is_done_on_develop(str(repo_with_remote), "TECH-170", ["src/x.py"]) is True` | `assert gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", ["src/x.py"]) is not None` |
   | 94 | `... is False` | `assert gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", ["src/x.py"]) is None` |
   | 106 | `... is False` | `... is None` |
   | 118 | `... is False` | `... is None` |
   | 132 | `assert callback._is_done_on_develop(str(repo), "TECH-170", ["src/x.py"]) is False` | `assert gate_logic.find_implementation_commit(str(repo), "TECH-170", ["src/x.py"]) is None` |
   | 144 | `assert callback._is_done_on_develop(str(repo_with_remote), "TECH-170", []) is False` | `assert gate_logic.find_implementation_commit(str(repo_with_remote), "TECH-170", []) is None` |

   Docstring файла (**:1** «unit tests for callback._is_done_on_develop», **:6-11** «→ True/False»)
   переписать на `gate_logic.find_implementation_commit` и `→ SHA / None`. **Ни один кейс не
   удаляется** — это BUG-1039 regression, сторож за конкретным инцидентом.

6. **`tests/unit/test_callback_implementation_guard.py` — 5 прямых вызовов (D3).**
   Добавить `import gate_logic  # noqa: E402` после `import callback` (:18).

   | Строка | Было | Стало |
   |---|---|---|
   | 114 | `assert callback._is_done_on_develop(str(dev_repo), "TECH-XXX", ["src/foo.py"]) is True` | `assert gate_logic.find_implementation_commit(str(dev_repo), "TECH-XXX", ["src/foo.py"]) is not None` |
   | 123 | `... is False` | `... is None` |
   | 133 | `assert callback._is_done_on_develop(str(repo), "TECH-XXX", ["src/foo.py"]) is False` | `... gate_logic.find_implementation_commit(...) is None` |
   | 146 | `assert callback._is_done_on_develop(str(dev_repo), "BUG-339", ["src/foo.py"]) is True` | `... is not None` |
   | 173 | `assert callback._is_done_on_develop(str(dev_repo), "BUG-338", ["src/text.py"]) is True` | `... is not None` |

   Строки **151, 152** (`callback._subject_implements(...) is False`) **в этой задаче не
   трогать** — `_subject_implements` ещё жив и патчей не имеет; они едут в Task 4.
   Docstring **:4** и баннер **:70** переписать на `find_implementation_commit`.

7. **Зелёный прогон:**
   ```bash
   cd /home/dld/projects/dld/.worktrees/TECH-210/scripts/vps/tests && python -m pytest -q
   # 607 passed, 0 failed  (606 baseline + 1 новый EC-5)
   cd /home/dld/projects/dld/.worktrees/TECH-210 && python -m pytest tests/ -q
   # 242 passed, 1 skipped, 0 failed
   ```

**Acceptance:**
- EC-5 зелёный; вернуть в `callback.py` форму `from gate_logic import find_implementation_commit`
  → EC-5 краснеет (проверить руками, откатить) — **EC-5, EC-8**
- `grep -c 'callback, "_is_done_on_develop"\|callback, "_fetch_develop"' -r tests/ scripts/vps/tests/` = **0**
- `grep -rn "_is_done_on_develop\|_fetch_develop" tests/integration/ tests/unit/` = 0
- `scripts/vps/tests`: **607 passed, 0 failed**; корень: **242 passed, 1 skipped, 0 failed** — EC-9, EC-11, EC-12
- функции в `callback.py` всё ещё существуют (ничего не удалено), один коммит

### Task 3: Переезд кейсов матчера в новый `test_gate_logic_subject.py`
**Type:** test
**Files:**
  - Create: `scripts/vps/tests/test_gate_logic_subject.py` (~200 LOC)
  - Modify: `scripts/vps/tests/test_gate_logic.py` (**723** LOC → ≤600)

**Context.** Задача чисто тестовая, производственного кода не касается, и выполняется
**до** удаления копий — новый файл проверяет `gate_logic.match_subject`, который уже
существует, поэтому зеленеет сразу. Старые классы в `test_callback.py` пока живы и тоже
зелёные; их удаление — Task 4, когда исчезнет `callback._subject_implements`.

`test_gate_logic.py` = **723 LOC [DRIFT-1]** при лимите 600 для тестов. Это нарушение
досталось по наследству, не создано этой спекой, но `## Allowed Files` **заранее** разрешает
новый файл — значит чинится здесь, а не откладывается.

**Steps:**

1. **Создать `scripts/vps/tests/test_gate_logic_subject.py`.** Шапка — копия
   `test_gate_logic.py:1-29`, урезанная до одного импорта:
   ```python
   # scripts/vps/tests/test_gate_logic_subject.py
   """Subject-matcher tests for gate_logic.match_subject (TECH-210).

   Split out of test_gate_logic.py (which was 723 LOC against the 600 test limit) and
   merged with the 14 cases that lived only in test_callback.py against the now-deleted
   callback._subject_implements. Nothing here is new coverage — every case is a case
   that already guarded a real incident.
   """

   import sys
   from pathlib import Path

   VPS_DIR = str(Path(__file__).resolve().parent.parent)
   if VPS_DIR not in sys.path:
       sys.path.insert(0, VPS_DIR)

   from gate_logic import match_subject  # noqa: E402
   ```

2. **Перенести дословно** `test_gate_logic.py:130-242` (баннер Part 1 + 14 тест-функций
   `test_match_subject_*` и `test_DA4_growth_spec_id_match_subject`). Копировать, не
   переписывать: там сидят BUG-338/339/346, TECH-349 и DA-4.

3. **Дописать 14 кейсов, которых в `test_gate_logic.py` НЕТ** — полный перечень, сверен
   построчно с `test_callback.py` 2026-08-07. **[DRIFT-9]: их 14, а не 13** — §7 Autopilot
   Log пропустил `feat(other): see also FTR-925`.

   | # | Кейс | Источник в `test_callback.py` | Ожидание |
   |---|---|---|---|
   | 1 | conventional multi-scope без пробела и с пробелом | 360-362 | True, True |
   | 2 | `merge FTR-925` / `merge FTR-925: impl` (строчная + двоеточие после id) | 368-369 | True |
   | 3 | `feat(FTR-923): impl X (see also FTR-925)` | 375-377 | **False** |
   | 4 | `feat: FTR-925 something` и `feat: FTR-1076 implementation` — id без scope | 380, 447 | **False** |
   | 5 | пустые входы: `("", "FTR-925")`, `("feat(FTR-925): x", "")` | 386-387 | **False** |
   | 6 | lowercase scope: `feat(ftr-1076)`, `chore(ftr-1076)` | 395-401, 459 | True |
   | 7 | mixed-case scope `feat(Ftr-1076)` | 404 | True |
   | 8 | `Merge feature/FTR-1076: SRID — MC admin endpoint` | 407-409, 460 | True |
   | 9 | `Merge autopilot/BUG-1065 into develop` | 410, 461 | True |
   | 10 | `Merge fix/BUG-439 — restore constraint` | 411 | True |
   | 11 | case-insensitive multi-scope `feat(area, ftr-1076, FTR-1077)` — обе стороны | 413-415, 462 | True, True |
   | 12 | `feat(billing): SRID pre-withdrawal gate (FTR-1077 Task 3)` | 429-431 | **False** |
   | 13 | `feat(other): see also FTR-925` / `feat(other): see FTR-925` | 441, 480 | **False** |
   | 14 | `Refs: FTR-925` | 444, 481 | **False** |

   Форма (пример для #1 и #13, остальные по образцу):
   ```python
   def test_match_subject_conventional_multi_scope():
       """Multi-spec scope, with and without whitespace (test_callback.py:360-362)."""
       assert match_subject("feat(FTR-925,FTR-926): both", "FTR-925") is True
       assert match_subject("feat(FTR-925, FTR-926): both", "FTR-926") is True


   def test_match_subject_see_also_in_message_rejected():
       """TECH-177: id in the description with a foreign scope is a cross-reference."""
       assert match_subject("feat(other): see also FTR-925", "FTR-925") is False
       assert match_subject("feat(other): see FTR-925", "FTR-925") is False
   ```

4. **Уже покрыто в `test_gate_logic.py` — НЕ дублировать** (проверено 2026-08-07):
   conventional feat :137, `fix(...)!` :142, `Merge SPEC-A` :148, bare prefix :153,
   чужой spec_id :158, GROWTH :163, trailing parens со scope :171 и без :183,
   multi-spec tail :193-196, `(see BUG-339)` reject :201, mid-subject parens reject :206,
   `merge: feature/TECH-349 —` :212, `Merge branch '...'` :223, чужая ветка + граница
   `BUG-3468` :233-241. Это 3 из 7 позитивов и 1 из 3 негативов класса
   `TestMatchSubjectParityWithCallback` — остальные 4+2 попали в таблицу шага 3
   (позитивы 459-462, негативы 480-481). §7 Autopilot Log здесь **подтверждён**.

5. **Ужать `test_gate_logic.py` до ≤600.** Арифметика (проверить `wc -l` после каждого шага):
   - удалить строки **130-243** (баннер Part 1 + 14 функций + разделитель): 723 → **609**
   - убрать `match_subject,` из `from gate_logic import (...)` (**строка 26**) — он больше
     нигде в файле не используется (единственное оставшееся упоминание — комментарий :652): → **608**
   - схлопнуть пять оставшихся 3-строчных баннеров `# ===` / `# Part N: ...` / `# ===`
     (**244-246, 365-367, 416-418, 456-458, 477-479**) в одну строку каждый,
     `# --- Part N: ... ---`: 5 × 2 = 10 строк → **598**
   - строку **5** docstring'а поправить: `match_subject` уехал, назвать новый файл
   - `# ---` шапку регрессии **647-657** (birth-commit, dowry BUG-460) **НЕ трогать** —
     она несущая
   - `ruff format --check` должен пройти: после удаления 130-243 перед баннером Part 2
     оставить ровно две пустые строки

6. **Проверка:**
   ```bash
   cd /home/dld/projects/dld/.worktrees/TECH-210
   wc -l scripts/vps/tests/test_gate_logic.py scripts/vps/tests/test_gate_logic_subject.py
   ruff check scripts/vps/tests/ && ruff format --check scripts/vps/tests/
   cd scripts/vps/tests && python -m pytest test_gate_logic.py test_gate_logic_subject.py -q
   ```

**Acceptance:**
- `wc -l scripts/vps/tests/test_gate_logic.py` ≤ **600** (ожидаемо 598) — DoD «≤600»
- `wc -l scripts/vps/tests/test_gate_logic_subject.py` ≤ 600 (ожидаемо ~200)
- `grep -c "^def test_match_subject\|^def test_DA4_growth_spec_id_match_subject" scripts/vps/tests/test_gate_logic_subject.py` = **28** (14 перенесённых + 14 новых)
- `cd scripts/vps/tests && python -m pytest -q` → **621 passed, 0 failed** (607 + 14) — **EC-1**
- корневой `pytest tests/ -q` не тронут: 242 passed, 1 skipped, 0 failed

### Task 4: Удалить пять функций и семь регэкспов, поставить алиас
**Type:** code + test
**Files (4 — все ломаются в один момент, см. Context):**
  - Modify: `scripts/vps/callback.py` (−~270 строк)
  - Modify: `scripts/vps/tests/test_callback.py` (удалить 4 класса матчера, **869** LOC **[DRIFT-2]**)
  - Modify: `tests/unit/test_callback_implementation_guard.py:151,152`
  - Modify: `scripts/vps/tests/test_claude_runner_timeout.py:198-222`

**Context.** STOP-условие прежней Task 2 **снято** (владелец одобрил 2026-07-28 и 2026-08-07).
Четыре файла едут вместе, потому что ломаются одной и той же секундой: как только исчезает
`def _subject_implements`, краснеют 29 ассертов в `test_callback.py` и 2 в
`test_callback_implementation_guard.py`; как только исчезает `def _fetch_develop`, краснеет
source-ассерт в `test_claude_runner_timeout.py`. Кейсы матчера к этому моменту уже живут в
`test_gate_logic_subject.py` (Task 3) — здесь они именно **удаляются как переехавшие**,
а не теряются.

**Steps:**

1. **`callback.py` — удалить блоки** (сверху вниз, чтобы номера не поехали — или снизу вверх,
   что надёжнее):

   | Строки | Что | Примечание |
   |---|---|---|
   | 830-894 | `def _is_done_on_develop` | вместе с внутренним вызовом на 892 |
   | 810-827 | `def _fetch_develop` | |
   | 741-807 | `def _subject_implements` | |
   | 536-572 | `def _parse_allowed_files` | **заменить на алиас**, см. шаг 2 |
   | 513-533 | `def _parse_allowed_files_legacy` | |
   | 474-510 | `def _parse_allowed_files_v1` | |
   | 443-471 | 7 регэкспов + их комментарии | `_ALLOWED_FILE_EXT_RE` (443-447), `_ALLOWED_FILES_V1_HEADING_RE` (449-451), `_MARKER_RE` (452-453), `_BULLET_RE` (454-455), `_NUMBERED_RE` (456-459), `_ALLOWED_FILES_HEADING_RE` (461-470), `_NEXT_H2_RE` (471) |

   **НЕ трогать:**
   - `_SPEC_ID_RE` (**43-45**) — живёт в `resolve_spec_id` (329, 335, 347). Удалить =
     `NameError` на каждом резолве pueue-лейбла, то есть сломать callback целиком.
     После работы `grep -c "_SPEC_ID_RE" scripts/vps/callback.py` = **4**, а не 0.
   - баннер **441** `# --- TECH-166 / TECH-167: Implementation guard helpers ---` — под ним
     остаются `_get_started_at` (575), `_audit_log_path` (591), `_commit_stats` (627),
     `_detect_out_of_scope_files` (692)
   - `import re` (27) и `import subprocess` (28) — живые потребители остаются
     (`re`: 45, 224, 345, 393; `subprocess`: 97, 162, 297, 356, 386, 655, 717, 947, 971, 1237)

2. **Вместо тела `_parse_allowed_files` (536-572) — ровно одна строка + комментарий:**
   ```python
   # Дедупликация — это одна реализация, а не ноль имён. Алиас держит публичный шов
   # для иммутабельного tests/regression/test_callback_spec_corpus.py:45 и прямых
   # вызовов в tests/unit/; тело живёт в gate_logic (TECH-210, решение 2026-07-28).
   _parse_allowed_files = gate_logic.parse_allowed_files
   ```
   Ловушка DA-4 сюда не достаёт: `monkeypatch.setattr(callback, "_parse_allowed_files", ...)`
   в дереве **ноль раз** (перепроверено 2026-08-07). Это чистый парсер, а не точка мока.
   Строка обязана стоять **после** `import gate_logic` (:38) — иначе `NameError` на импорте.

3. **`scripts/vps/tests/test_callback.py` — удалить четыре класса целиком:**
   `TestSubjectImplements` (**351-387**), `TestSubjectImplementsRealWorld` (**390-415**),
   `TestSubjectImplementsAntiFalsePositive` (**418-447**),
   `TestMatchSubjectParityWithCallback` (**450-490**), вместе с баннером **348**
   (`# --- TECH-177: Subject-only matcher ... ---`). Диапазон удаления: **348-491**.
   Все 29 ассертов к этому моменту живут в `test_gate_logic_subject.py` — сверить
   поштучно по таблице Task 3 шаг 3/шаг 4 **до** удаления, а не после.
   Класс паритета удаляется по существу: паритет двух копий бессмыслен, когда копия одна;
   его 4 непокрытых позитива (459-462) и 2 негатива (480-481) уже уехали в Task 3.

4. **`tests/unit/test_callback_implementation_guard.py:151,152`** — единственные оставшиеся
   ссылки на `_subject_implements`. `import gate_logic` уже добавлен в Task 2.
   ```python
       assert gate_logic.match_subject("fix: adjust helper (see BUG-339)", "BUG-339") is False
       assert gate_logic.match_subject("fix: revert (BUG-339) partial now", "BUG-339") is False
   ```
   `match_subject` возвращает `bool`, поэтому `is False` здесь остаётся корректным —
   в отличие от `find_implementation_commit` из Task 2.

5. **`scripts/vps/tests/test_claude_runner_timeout.py` — `TestVariantCNeverIntroduced`
   (195-222). Все номера ниже перепроверены 2026-08-07 [DRIFT-5]/[DRIFT-6];
   прежний план называл 196/199/201/204/212/218/220-221 — **неверно**.**

   **5a. `test_no_local_develop_gate_path` (198-215) — переезжает на `gate_logic.py`:**

   | Строка | Было | Стало |
   |---|---|---|
   | **199** (docstring) | `"""_is_done_on_develop must check origin/develop, never just 'develop'."""` | `"""find_implementation_commit must check origin/develop, never just 'develop'."""` |
   | **200** | `source = (Path(VPS_DIR) / "callback.py").read_text(...)` | `source = (Path(VPS_DIR) / "gate_logic.py").read_text(...)` |
   | **203** | `re.search(r"def _is_done_on_develop\(.*?\).*?(?=\ndef \|\Z)", source, re.DOTALL)` | `re.search(r"def find_implementation_commit\(.*?\).*?(?=\ndef \|\Z)", source, re.DOTALL)` |
   | **204** | `assert fn_match, "_is_done_on_develop function not found"` | `assert fn_match, "find_implementation_commit function not found"` |
   | **206** | `assert "origin/develop" in fn_body, "_is_done_on_develop must check origin/develop"` | `... "find_implementation_commit must check origin/develop"` |
   | **213-214** | `f"_is_done_on_develop must not use bare 'develop' ref: {...}"` | `f"find_implementation_commit must not use bare 'develop' ref: {...}"` |

   Regex проверен против реального файла: сигнатура `find_implementation_commit`
   многострочная (`gate_logic.py:311-315`), `.*?\)` доедает до `)` на 315, дальше `.*?`
   с lookahead `(?=\ndef |\Z)` растягивается до конца файла — это **последняя** функция
   модуля. `origin/develop` в теле есть (379); строк с bare `"develop"` в 311-402 нет.
   Обе проверки остаются в силе.

   **5b. `test_push_local_is_best_effort_not_gate` (217-222) — ОСТАЁТСЯ на `callback.py`.
   Это поправка D2, она обязательна.** Прежний план велел перенацелить и её на
   `gate_logic.py` — тогда `assert "fetch_develop(" in source` совпало бы с
   **определением** функции, стало бы вечно истинным, и сторож умер бы молча.
   Он стережёт, что гейт зовётся **из callback**, а не что он где-то существует.

   | Строка | Было | Стало |
   |---|---|---|
   | **219** | `source = (Path(VPS_DIR) / "callback.py").read_text(...)` | **без изменений** — продолжает читать `callback.py` |
   | **220** (комментарий) | `# push-local block must NOT skip _fetch_develop or _is_done_on_develop` | `# push-local block must NOT skip the gate_logic gate calls` |
   | **221** | `assert "_fetch_develop(" in source, "_fetch_develop must still be called"` | `assert "gate_logic.fetch_develop(" in source, "gate_logic.fetch_develop must still be called"` |
   | **222** | `assert "_is_done_on_develop(" in source, "_is_done_on_develop must still be the gate"` | `assert "gate_logic.find_implementation_commit(" in source, "gate_logic.find_implementation_commit must still be the gate"` |

   Строку **196** (docstring класса, `"""EC-5: callback gate NEVER returns done from
   local-only develop."""`) не трогать — она не называет удалённых имён.

6. **Проверка:**
   ```bash
   cd /home/dld/projects/dld/.worktrees/TECH-210
   python -m py_compile scripts/vps/callback.py
   grep -c "_subject_implements\|_is_done_on_develop\|_fetch_develop" scripts/vps/callback.py   # 0
   grep -c "^def _parse_allowed_files"                                scripts/vps/callback.py   # 0
   grep -c "^_parse_allowed_files = gate_logic.parse_allowed_files"   scripts/vps/callback.py   # 1
   grep -c "_SPEC_ID_RE"                                              scripts/vps/callback.py   # 4
   grep -c "_ALLOWED_FILE_EXT_RE\|_ALLOWED_FILES\|_NEXT_H2_RE"        scripts/vps/callback.py   # 0
   wc -l scripts/vps/callback.py                                                                # ~1430
   PYTHONPATH=scripts/vps python -c "import callback; assert not hasattr(callback,'_is_done_on_develop'); assert callback._parse_allowed_files is __import__('gate_logic').parse_allowed_files"
   cd scripts/vps/tests && python -m pytest -q            # 592 passed, 0 failed (621 − 29 переехавших)
   cd /home/dld/projects/dld/.worktrees/TECH-210 && python -m pytest tests/ -q   # 242 passed, 1 skipped, 0 failed
   ```

**Acceptance:**
- `hasattr(callback, "_is_done_on_develop")` = `False` — **EC-6**
- `callback._parse_allowed_files is gate_logic.parse_allowed_files` = `True` — **EC-13**
- `pytest tests/regression/test_callback_spec_corpus.py -q` зелёный **без единой правки файла** — **EC-11**
- `grep -c "^from gate_logic import" scripts/vps/callback.py` = 0 — **EC-8**
- корневой прогон **242 passed, 1 skipped, 0 failed** (не «184/6» и не «187/3» — **[DRIFT-12]**)
- ни один кейс матчера не потерян: суммарное число ассертов `match_subject` в
  `test_gate_logic_subject.py` ≥ числа удалённых из `test_callback.py`

---

### Task 5: `spec_verify.py` на публичный парсер
**Type:** code
**Files:**
  - Modify: `scripts/vps/spec_verify.py:11`, `:32`, `:39-43`, `:230`

**Context.** Единственный deep-import `from callback import _parse_allowed_files` во всём
дереве. Он не сломается после Task 4 (алиас на месте), но docstring файла обещает «Reuse the
canonical allowlist parser — single source of truth», а тянет копию через чужой приватный
шов. Здесь форма `from ... import ...` **разрешена** — `spec_verify` ничего не патчит и
никем не патчится (hard constraint 1 действует только для `callback.py`).
**Pattern:** `gate-daemon.py` — существующий потребитель `gate_logic.parse_allowed_files`.

**Steps** (4 точки, номера перепроверены 2026-08-07, дрейфа нет):

- **:11** `Uses: scripts.vps.callback._parse_allowed_files (TECH-167 canonical parser).`
  → `Uses: scripts.vps.gate_logic.parse_allowed_files (TECH-167 canonical parser).`
- **:32** `# Reuse the canonical allowlist parser from callback.py — single source of truth.`
  → `# Reuse the canonical allowlist parser from gate_logic.py — single source of truth.`
- **:39-43** блок целиком:
  ```python
  try:
      from gate_logic import parse_allowed_files  # type: ignore
  except Exception as exc:  # noqa: BLE001
      print(f"spec_verify: cannot import gate_logic.parse_allowed_files: {exc}", file=sys.stderr)
      sys.exit(2)
  ```
  (`try` 39, импорт 40, `print` 42, `sys.exit` 43. Строка 37 — `import console_safe`,
  её не трогать: прежняя редакция плана числила блок как «37-41» и это была ошибка на +2.)
- **:230** `allowed = _parse_allowed_files(spec_path)` → `allowed = parse_allowed_files(spec_path)`
  — без этой строки модуль падает на `NameError`. Прежняя редакция числила «228».

**Проверка (EC-10 — вывод обязан совпасть побайтово):**
```bash
cd /home/dld/projects/dld/.worktrees/TECH-210
git stash && python3 scripts/vps/spec_verify.py . TECH-208 > /tmp/sv-before.txt; echo "rc=$?" >> /tmp/sv-before.txt
git stash pop
python3 scripts/vps/spec_verify.py . TECH-208 > /tmp/sv-after.txt; echo "rc=$?" >> /tmp/sv-after.txt
diff /tmp/sv-before.txt /tmp/sv-after.txt   # пусто
```
*(если `git stash` неудобен на этой стадии — снять эталон ДО первой правки этой задачи
и сравнить после; важен сам факт побайтового сравнения, а не способ его получить)*

**Acceptance:**
- `grep -c "callback" scripts/vps/spec_verify.py` = **0**
- `diff /tmp/sv-before.txt /tmp/sv-after.txt` пуст, exit code тот же — **EC-10**
- `python -m py_compile scripts/vps/spec_verify.py` → exit 0

---

### Task 6: `gate_logic.py` ≤400 LOC + coverage-гейт
**Type:** code
**Files:**
  - Modify: `scripts/vps/gate_logic.py` (**402** → 398)
  - Modify: `.github/workflows/test.yml:69` — **только если** прогон красный

**Context.** 402 LOC при лимите 400. Резать код не нужно и нельзя: после Task 4 три строки
docstring'ов ссылаются на несуществующий уже `callback._parse_allowed_files*`.

**[DRIFT-10] — прежний план ошибался в механике.** Он велел удалить ровно строки 102, 141,
162. Строки 101 и 140 — пустые разделители перед ними внутри docstring'ов; удалив только
текст, получим висящую пустую строку перед `"""`. Правильно:

| Действие | Строки | Дельта |
|---|---|---|
| удалить пустую + текст «Copied verbatim from callback._parse_allowed_files_v1.» | **101-102** | −2 |
| удалить пустую + текст «Copied verbatim from callback._parse_allowed_files_legacy.» | **140-141** | −2 |
| **переписать** :162 `Public API (gate-daemon entry point). Mirrors callback._parse_allowed_files.` → `Public API (gate-daemon entry point) — the single implementation (TECH-210).` | **162** | 0 |

Итог: 402 − 4 = **398** ≤ 400.

**Сохранить дословно, ни строки не тронуть:** FF-09 invariant (19-20); birth-commit / ADR-025
(62-68, 347-354); «Renamed from callback._subject_implements» (205), «Renamed from
callback._fetch_develop» (282-283), «Renamed from callback._is_done_on_develop» (318-319) —
они исторически верны и после удаления оригиналов остаются единственной записью о том,
откуда код пришёл; TECH-177 / L-derived-3 (321-325); BUG-192; plpilot BUG-338/339/346
(327-332); Devil Attack 2/3/10 (283, 321); урезание таймаута 30s→15s (282-283, 292) —
это объявленное изменение поведения, **EC-14**.

**Coverage-гейт.** Сначала измерить, потом решать:
```bash
cd /home/dld/projects/dld/.worktrees/TECH-210
PYTHONPATH=scripts/vps pytest \
  tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/ \
  --cov=callback --cov-report=term-missing --cov-fail-under=54
```
- **Зелено** → `test.yml` не трогать вообще.
- **Красно** → изменить **строку 69** `--cov=callback` на `--cov=callback --cov=gate_logic`
  и перемерить. Строку **72** (`--cov-fail-under=54`) не трогать ни при каком исходе:
  падение порога означает настоящую дыру, и её закрывают тестами, а не порогом.

**Acceptance:**
- `wc -l scripts/vps/gate_logic.py` = **398** (≤400) — **EC-7**
- `grep -c "BUG-338\|TECH-177\|BUG-346\|ADR-025\|FF-09\|BUG-192\|Devil Attack" scripts/vps/gate_logic.py` не уменьшился относительно замера до правки (снять до!)
- `PYTHONPATH=scripts/vps python -c "import gate_logic"` → exit 0, без вывода — **AV-S2**
- `grep -c -- "--cov-fail-under=54" .github/workflows/test.yml` = **1**
- coverage-прогон зелёный — **EC-12**

---

### Execution Order

```
Task 1 ──► Task 2 ──► Task 3 ──► Task 4 ──► Task 5 ──► Task 6
```

Зависимости — явно, а не «по смыслу»:

| Задача | Зависит от | Почему именно так |
|---|---|---|
| 1 | — | три call-site, которых никто не патчит; изолирована по построению |
| 2 | 1 | не жёстко, но 1 снимает шум из диффа 2; главное — 2 **обязана** быть одним коммитом |
| 3 | — (формально) | ставится третьей, чтобы `test_gate_logic_subject.py` существовал **до** удаления классов в Task 4. Переставить 3 после 4 = потерять кейсы между коммитами |
| 4 | **2 и 3** | 2 убирает живые вызовы, 3 сохраняет кейсы. Без любой из них Task 4 либо красит дерево, либо теряет покрытие |
| 5 | 4 (мягко) | алиас из Task 4 делает переход безопасным в обе стороны; формально исполнима и раньше |
| 6 | 4 | docstring'и в `gate_logic.py` становятся stale только после удаления оригиналов; coverage меряется на финальном коде |

Разделение «перенаправить» (1-2) и «удалить» (4) на разные коммиты — сознательное:
при регрессии видно, какой из двух шагов виноват. Схлопывать их в один нельзя.

**Число файлов на задачу.** Task 2 (9) и Task 4 (4) превышают ориентир «≤3». Это не
недосмотр планировщика: оба — атомарные свопы, где производственная строка и её
monkeypatch-мишени физически не могут разъехаться по коммитам без красного дерева.
Правило «ни одного красного коммита» здесь старше правила «≤3 файла».

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Гейт вызывается из одного места | Task 1 + Task 2 | ✓ |
| 2 | Monkeypatch перехватывает через модуль (DA-4) | Task 2 (EC-5) | ✓ |
| 3 | Копий в `callback.py` не осталось | Task 4 | ✓ |
| 4 | Кейсы матчера не потеряны | Task 3 (EC-1) | ✓ |
| 5 | Тесты адресуют живые имена | Task 2 + Task 3 + Task 4 | ✓ |
| 6 | Operator-инструмент не сломан | Task 5 (EC-10) | ✓ |
| 7 | `gate_logic.py` под лимитом, coverage не просел | Task 6 (EC-7, EC-12) | ✓ |
| 8 | Поведение гейта не изменилось | Task 2 + Task 3 (EC-1..EC-4) | ✓ |

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
| EC-13 | Алиас парсера делегирует, а не копирует | `callback._parse_allowed_files is gate_logic.parse_allowed_files` | `True` | deterministic | решение 2026-07-28 | P0 |
| EC-14 | Урезание fetch-бюджета объявлено | `gate_logic.fetch_develop` на медленном remote | таймаут 15s, возврат `False`, гейт даёт `blocked`, **не** `done` | deterministic | planner [VERIFIED-FIX 2] пара D | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-9 | Реальный git-репозиторий с коммитом `fix(TECH-210): x` | полный `verify_status_sync` | статус `done`, тот же audit-JSONL, что до правки | integration | TECH-171 | P0 |
| EC-10 | Существующая спека с v1-маркером | `python3 scripts/vps/spec_verify.py <spec>` | вывод побайтово совпадает с прогоном до правки | integration | devil SA-1 | P0 |
| EC-11 | Корпус регрессии allowlist | `pytest tests/regression/test_callback_spec_corpus.py` | зелёный **без правок самого теста** | integration | правило иммутабельных тестов | P0 |
| EC-12 | Coverage-гейт проходит | команда из `test.yml:65-72` | ≥54%, порог **не понижен** | integration | devil SA-3 | P0 |

### Coverage Summary
Deterministic: 10 | Integration: 4 | LLM-Judge: 0 | Total: 14 (min 3 ✓)

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
| AV-F1 | Тесты VPS зелёные | — | `cd scripts/vps/tests && python -m pytest -q` | **592 passed, 0 failed** (baseline 606 + 1 EC-5 + 14 новых кейсов матчера − 29 переехавших). Прежние «≥419» и «498» — устарели, **[DRIFT-11]** |
| AV-F2 | Корневые тесты не деградировали | — | `python -m pytest tests/ -q` | **242 passed, 1 skipped, 0 failed.** Baseline замерен в этом worktree 2026-08-07: предсуществующих падений **нет**. Числа «184 passed, 6 failed» и «187 passed, 3 failed» из прежних циклов — обе устарели, **[DRIFT-12]**. Любой красный корневой тест после работы вызван этой работой, а не наследием |
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
- [ ] **Пять** функций и семь регэкспов удалены из `callback.py` (состав семи — по
      [VERIFIED-FIX 1]: без `_SPEC_ID_RE`, с `_ALLOWED_FILES_HEADING_RE`)
- [ ] `_parse_allowed_files` остаётся **одной строкой-алиасом** на `gate_logic.parse_allowed_files`
- [ ] Все девять call-sites зовут `gate_logic.*` через атрибут модуля (Task 1: 731/1217/1514; Task 2: 1255/1257/1272/1273/1522/1523)
- [ ] `spec_verify.py` использует публичный `gate_logic.parse_allowed_files` (строки **40** и **230**)
- [ ] `gate_logic.py` ≤ 400 LOC (**398**)
- [ ] `scripts/vps/tests/test_gate_logic.py` ≤ 600 LOC (**598**, было 723)
- [ ] `scripts/vps/tests/test_gate_logic_subject.py` создан, ≤600 LOC

### Tests
- [ ] EC-1..EC-14 проходят
- [ ] 29 кейсов матчера **переехали** (14 функций-дублей уже были в `test_gate_logic.py`,
      **14** отсутствовавших дописаны — **[DRIFT-9]**, §7 числил 13), ни один не потерян
- [ ] `tests/regression/test_callback_spec_corpus.py` зелёный без правок
- [ ] 22 monkeypatch в пяти `tests/integration/` перенацелены; `True → "deadbee"`, `False → None`

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1, AV-F2, AV-F3 локально
- [ ] AV-F4 на VPS — **рестарт демонов обязателен**: они держат старый код в памяти,
      на этом уже потеряли цикл 2026-07-27

### Technical
- [ ] Поведение гейта не изменилось ни в одном из 14 EC (единственное объявленное
      изменение — fetch-бюджет 30s → 15s, зафиксирован в EC-14)
- [ ] `grep "^from gate_logic import" scripts/vps/callback.py` = 0

---

## Autopilot Log

### 2026-07-28 (цикл 2) — BLOCKED at PHASE 1, zero code written

**Причина: резолюция от 2026-07-28 опирается на ложный замер. Ловушка DA-4 существует
и срабатывает на Task 1 — до единого удаления.**

Блок «✅ РЕШЕНО» утверждает:

> | `_is_done_on_develop` | 13 | **0** monkeypatch | 13 прямых вызовов |
>
> У гейтовых функций monkeypatch есть, но только в `scripts/vps/tests/test_callback.py`,
> который уже в Allowed Files и переписывается штатно.

**Проверено грепом — неверно.** В корневом `tests/integration/` лежат **22
`monkeypatch.setattr(callback, "_fetch_develop"/"_is_done_on_develop", ...)`** в **пяти**
файлах, ни один из которых не в `## Allowed Files`:

| Файл | Строки | Есть стаб `→ True`? |
|---|---|---|
| `tests/integration/test_callback_already_merged.py` | 150/151, 169/170, 193/194, 219/220, 242/243 | **да** (151, 243) |
| `tests/integration/test_callback_feature_branch.py` | 142/143, 164/165, 183/184 | **да** (165) |
| `tests/integration/test_callback_status_sync.py` | 334/335 | **да** (335) |
| `tests/integration/test_callback_no_impl_demote.py` | 180/181 | **да** (181) |
| `tests/integration/test_callback_blocked_no_dispatch.py` | 192/193 | нет |

**Механика отказа (подтверждена чтением `test_callback_already_merged.py:143-156`):**
`test_ec1_gate_true_becomes_done` стабит `callback._is_done_on_develop → True` и ассертит
`status == "done"`. После Task 1 `verify_status_sync` уходит в
`gate_logic.find_implementation_commit`, патч становится инертным, настоящий гейт бежит
по tmp-репозиторию без implementation-коммита на `origin/develop`, возвращает `None` —
и статус переворачивается `done → blocked`. Тест краснеет.

Это ровно ловушка DA-4, из-за которой § Approaches отверг делегаты. Она **не про парсер**
(там замер верен — 0 monkeypatch, алиас безопасен), а про пару B, и алиас до неё не достаёт.

**Срабатывает на Task 1, не на Task 2.** STOP-условие Task 2 действительно снято, но это
не помогает: перенаправление call-sites само по себе ломает пять файлов вне allowlist.
`test.yml:50` гоняет `tests/integration/test_callback_*.py` отдельным шагом **и** внутри
coverage-гейта (65-72) — EC-11/EC-12 падают так же, как в первом блокере.

Расширять `## Allowed Files` самостоятельно автопилоту запрещено (BUG-199 fence).

#### ACTION REQUIRED — решение владельца (одна строка разрешения)

Добавить в `## Allowed Files` пять файлов и перенацелить их 22 `monkeypatch.setattr`
на `gate_logic.fetch_develop` / `gate_logic.find_implementation_commit`
(`True` → строка-SHA, `False` → `None`):

- `tests/integration/test_callback_already_merged.py`
- `tests/integration/test_callback_feature_branch.py`
- `tests/integration/test_callback_status_sync.py`
- `tests/integration/test_callback_no_impl_demote.py`
- `tests/integration/test_callback_blocked_no_dispatch.py`

С этим расширением Tasks 1-5 исполнимы как написано, с поправками D2/D3/§7 ниже.

#### Ещё четыре расхождения, найденные в этом цикле (чинить вместе с разрешением)

- **D2 — Task 4c ослабляет регрессионный тест.** `test_push_local_is_best_effort_not_gate`
  (`test_claude_runner_timeout.py:216-222`) читает исходник `callback.py` и стережёт, что
  гейт зовётся **из callback**. Перенацеливание :218 на `gate_logic.py`, как велит план,
  превращает `assert "fetch_develop(" in source` в совпадение с **определением** — вечно
  истинно, сторож мёртв. Правильно: :218 продолжает читать `callback.py`, ассерты стают
  `"gate_logic.fetch_develop("` / `"gate_logic.find_implementation_commit("`. На
  `gate_logic.py` переезжает только `test_no_local_develop_gate_path` (194-214). Строки
  **195** (docstring) и **219** (комментарий) тоже называют старые имена и в списке правок
  плана отсутствуют.
- **D3 — несовпадение типа возврата в двух разрешённых корневых файлах.** Все 11 прямых
  вызовов в `test_callback_branch_awareness.py` (75, 94, 106, 118, 132, 144) и
  `test_callback_implementation_guard.py` (114, 123, 133, 146, 173) ассертят `is True` /
  `is False`. `find_implementation_commit` возвращает `str | None` — `is True` падает на
  SHA-строке. План называет эту конверсию для `test_callback.py:690-704`, но не для
  корневых файлов, которые сам же и добавил.
- **§7 — переезжают 13 кейсов матчера, не 12**, и `TestMatchSubjectParityWithCallback`
  **нельзя просто удалить**: 4 из 7 позитивов (459-462) и 2 из 3 негативов (480, 481) в
  `test_gate_logic.py` отсутствуют. Недостающие классы реджектов: `Refs: FTR-925` (443-444)
  и `feat: FTR-925 something` — ID в теле без scope (380, 447).
- **Task 3 — номера строк `spec_verify.py` сдвинуты на +2.** Исправлено в § Task 3 прямо
  сейчас: `try` 39, `from callback import` 40, текст ошибки 42, `sys.exit` 43, call-site
  **230** (не 228). Строка 37 — это `import console_safe`.

#### Baseline этого цикла (чистый `origin/develop`, worktree `tech/TECH-210`)

- `scripts/vps/tests` → **498 passed**, 0 failed (спека числила 421 — устарело, не дефект)
- корневой `pytest tests/` → **187 passed, 3 failed**, а не «184 passed, 6 failed», как
  говорит AV-F2. Предсуществующие падения: `test_callback_blocked_no_dispatch.py::test_missing_task_status_dispatches`,
  `test_callback_status_sync.py::test_ec15_operator_uncommitted_edits_in_spec_survive`,
  `test_callback_allowlist_v1.py::test_ec3_v1_marker_numbered_list_ignored`.
  **AV-F2 надо переписать на 187/3** при следующем заходе.
- Дрейфа строк нет: LOC всех восьми файлов и вся «Verified line map» совпали точно.

---

### 2026-07-27 — BLOCKED at PHASE 1 (planner validation), zero code written

> ## ✅ РЕШЕНО 2026-07-28 — resolution 1 (тонкий делегат для парсера)
>
> Владелец выбрал вариант 1. Блокер снят, спека исполнима. Ниже — что именно меняется;
> при расхождении с текстом ACTION REQUIRED **побеждает этот блок**.
>
> ### Решение
>
> `callback._parse_allowed_files` **остаётся** — одной строкой:
>
> ```python
> # Дедупликация — это одна реализация, а не ноль имён. Алиас держит публичный шов
> # для 35 прямых вызовов в корневом tests/, иммутабельного regression-корпуса и
> # spec_verify.py; тело живёт в gate_logic.
> _parse_allowed_files = gate_logic.parse_allowed_files
> ```
>
> Удаляются по-прежнему: `_parse_allowed_files_v1`, `_parse_allowed_files_legacy`,
> `_subject_implements`, `_fetch_develop`, `_is_done_on_develop` и семь регэкспов
> в составе по [VERIFIED-FIX 1].
>
> ### Почему алиас здесь безопасен, а для гейта — нет
>
> Отказ от делегатов в § Approaches был аргументирован ловушкой DA-4: тест патчит
> `callback._is_done_on_develop`, конвейер уходит в `gate_logic`, мок молча не срабатывает.
> Ловушка требует monkeypatch. Замер по корневому дереву:
>
> | Имя | Ссылок в `tests/` | `monkeypatch.setattr` | Прямых вызовов |
> |---|---|---|---|
> | `_parse_allowed_files` | 36 | **0** | 35 |
> | `_parse_allowed_files_v1` / `_legacy` | 0 | 0 | 0 |
> | `_is_done_on_develop` | 13 | 0 | 13 |
> | `_subject_implements` | 2 | 0 | 2 |
> | `_fetch_develop` | 0 | 0 | 0 |
>
> У парсера **ноль** monkeypatch-потребителей во всём дереве — ловушке нечем сработать.
> У гейтовых функций monkeypatch есть, но только в `scripts/vps/tests/test_callback.py`,
> который уже в Allowed Files и переписывается штатно.
>
> ### Границы правятся меньше, чем оценил planner
>
> Resolution 1 предполагала «всё равно нужны 9 мутабельных тест-файлов». Это оценка
> сверху: она считала все ~70 обращений, но 36 из них — к парсеру, и алиас их закрывает.
> Ломаются **два** файла, оба из-за пар A и B:
>
> - `tests/unit/test_callback_branch_awareness.py` — BUG-1039 regression по `_is_done_on_develop`
> - `tests/unit/test_callback_implementation_guard.py` — TECH-166 guard
>
> Оба добавлены в `## Allowed Files`. Ссылки в них перенацеливаются на
> `gate_logic.find_implementation_commit` / `gate_logic.match_subject`; **ни один кейс
> не удаляется** — это регрессионные сторожа за конкретными инцидентами.
>
> Остальные восемь корневых файлов (`test_callback_parser.py`,
> `test_callback_allowlist_v1.py`, `test_callback_already_merged.py`,
> `test_callback_feature_branch.py`, `test_callback_blocked_no_dispatch.py`,
> `test_callback_no_impl_demote.py`, `test_callback_status_sync.py`,
> `tests/regression/test_callback_spec_corpus.py`) **не трогаются** — они ходят через
> алиас. EC-11 и EC-12 снова достижимы.
>
> ### Три довеска от planner — приняты
>
> 1. **`_SPEC_ID_RE` не удалять** (живёт в `resolve_spec_id`), вместо него уходит
>    `_ALLOWED_FILES_HEADING_RE`. Состав семи меняется, число остаётся.
> 2. **Call-sites 9, а не 5** — таблица в § Verified line map каноническая. Две строки
>    `_parse_allowed_files` (1217, 1514) при алиасе можно оставить как есть или перевести
>    на `gate_logic.parse_allowed_files` — семантика одна; предпочтительно перевести,
>    чтобы алиас остался чисто внешним швом. Плюс `spec_verify.py:228`.
> 3. **Пара D меняет поведение: fetch-бюджет 30s → 15s.** Принимается сознательно и
>    объявляется здесь: fetch best-effort, гейт fail-closed, недобор истории даёт
>    `blocked`, а не ложный `done`. Новый EC-13 это фиксирует.
>
> ### Лимит тестового файла
>
> `test_gate_logic.py` — 720 LOC при лимите 600 для тестов, миграция кейсов даёт ~790.
> Из 29 ассертов матчера **новых только 12**, а класс
> `TestMatchSubjectParityWithCallback` (`test_callback.py:450-490`) после схлопывания
> копий теряет смысл и **удаляется, а не переезжает**. Если после этого файл всё ещё
> над 600 — разрешено вынести матчер в `scripts/vps/tests/test_gate_logic_subject.py`
> (добавлен в Allowed Files заранее, чтобы не упереться в BUG-199 fence второй раз).
>
> ### Причина блокера — дефект авторства спеки, записан
>
> § Impact Tree Step 1 грепал только `scripts/vps/`. Корневое дерево `tests/` не
> проверялось, и Step 4 CHECKLIST утверждал про regression-корпус «вызывает
> `callback.main`, не приватные имена» — ложь, строка 45 зовёт приватное имя напрямую.
> Правило на будущее: **Impact Tree Step 1 грепает от корня репозитория, а не от
> директории правки.** Утверждение о содержимом файла делается после чтения файла.

---

**ACTION REQUIRED — снят 2026-07-28, см. блок «РЕШЕНО» выше. Текст ниже сохранён как
разбор блокера.**

Baseline captured before blocking: `scripts/vps/tests` = **421 passed** on `origin/develop`.
Line numbers in the spec had **not** drifted — every symbol sits exactly where § Context says.
The blocker is a spec-authoring defect, not staleness.

#### Blocker: Impact Tree Step 1 grepped only `scripts/vps/`, missing the root `tests/` tree

The spec asserts (§ Impact Tree Step 1) that the 29 matcher references are "все в
`tests/test_callback.py`". Re-grepping the whole repo finds **48 further direct
`callback.<removed_name>` references in 10 root test files**, none of which are in
`## Allowed Files`, and **none** of which are `monkeypatch` (all are real call-sites that
break loudly on deletion):

| File | Refs | Mutable? |
|---|---|---|
| `tests/unit/test_callback_parser.py` | 19 | yes |
| `tests/unit/test_callback_implementation_guard.py` | 14 | yes |
| `tests/integration/test_callback_already_merged.py` | 13 | yes |
| `tests/unit/test_callback_allowlist_v1.py` | 11 | yes |
| `tests/unit/test_callback_branch_awareness.py` | 7 | yes |
| `tests/integration/test_callback_feature_branch.py` | 7 | yes |
| `tests/integration/test_callback_blocked_no_dispatch.py` | 3 | yes |
| `tests/integration/test_callback_status_sync.py` | 2 | yes |
| `tests/integration/test_callback_no_impl_demote.py` | 2 | yes |
| `tests/regression/test_callback_spec_corpus.py` | 1 | **NO — immutable** |

#### The hard contradiction

`tests/regression/test_callback_spec_corpus.py:45` is literally
`actual = callback._parse_allowed_files(spec_path)`.

The spec claims this file "вызывает `callback.main`, не приватные имена" (§ Step 4
CHECKLIST) — **false**, verified by reading the file. Therefore:

- **DoD** requires `callback._parse_allowed_files` be deleted.
- **EC-11** requires that regression test green **without editing it**, and CLAUDE.md
  forbids modifying `tests/regression/` at all.

Both cannot hold. `callback._parse_allowed_files` must survive in some form.

**EC-12 falls with EC-11:** `.github/workflows/test.yml:65-72` runs the coverage gate over
exactly `tests/unit/test_callback_*.py`, `tests/integration/test_callback_*.py` and
`tests/regression/` — the same 10 files. They cannot be left broken.

Autopilot may not widen `## Allowed Files` on its own (BUG-199 fence), so no resolution is
reachable in-session.

#### Three resolutions for the owner

1. **Thin delegate for the parser only** — keep `callback._parse_allowed_files` as a
   one-line delegate to `gate_logic.parse_allowed_files`, delete the other five. The
   § Approaches rejection of delegates was argued against `_is_done_on_develop`, where
   DA-4's silent-mock trap is real; a pure parser with no monkeypatch users anywhere does
   not carry that risk. Still requires adding the 9 mutable test files to Allowed Files.
2. **Widen `## Allowed Files`** by the 9 mutable test files and rewrite all 47 refs;
   the regression test still needs resolution 1 or 3 on top.
3. **Narrow the spec** to pairs A/B/D (`_subject_implements`, `_is_done_on_develop`,
   `_fetch_develop`) and defer the three allowlist parsers (C1-C3) to a follow-up that
   owns the root test tree. This keeps the *demonstrated* defect (pair B divergence) in
   scope and drops the part with the immutable-test conflict.

#### Three further discrepancies found (fix in whichever resolution is chosen)

- **`_SPEC_ID_RE` must NOT be deleted.** Spec lists it among the 7 regexes to remove, but
  `callback.py:329,335,347` use it inside `resolve_spec_id`, which stays. Deleting it =
  `NameError` on every pueue-label resolve. Conversely `_ALLOWED_FILES_HEADING_RE`
  (`callback.py:461-470`) is missing from the spec's list and *should* go. Set stays 7,
  membership swaps.
- **Call-sites are 9, not 5.** Real: 731, 1217, 1255, 1257, 1272, 1273, 1514, 1522, 1523.
  The spec's list missed both `_parse_allowed_files` calls (1217, 1514) and all three
  `_fetch_develop` calls (1255, 1272, 1522); its `892` is *inside* the deleted function.
  Also `spec_verify.py:228` calls the name — absent from the spec's 11/32/38/40 list.
- **Pair D is a behaviour change, undeclared.** `callback._fetch_develop(path) -> None`
  hardcodes `timeout=30`; `gate_logic.fetch_develop(path, timeout=15) -> bool`. The fetch
  budget **halves**. Defensible (best-effort, gate is fail-closed) but it should be a
  stated decision, not a side effect. Log output also shifts: logger name
  `callback`→`gate_logic`, arrow glyph `→`→`->`.

#### Non-blocking warnings for the eventual run

- `scripts/vps/tests/test_gate_logic.py` is already **720 LOC** against the 600 test limit;
  migrating the matcher cases pushes it to ~790, and splitting it is not permitted by
  the current Allowed Files.
- Only **12** of the 29 matcher assertions are genuinely new — `test_gate_logic.py` already
  covers 14 cases. `TestMatchSubjectParityWithCallback` (`test_callback.py:450-490`) becomes
  meaningless once one copy remains and should be deleted, not migrated.
- `gate_logic.py` is 402 LOC — exactly 3 over. The three "Copied verbatim from callback…"
  docstring lines (102, 141, 162) go stale after deletion and are precisely 3 lines.
