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

> **Plan verified against the worktree on 2026-07-27.** All line numbers below are the
> CURRENT ones. Four claims in the sections above turned out to be wrong; the corrections
> are marked **[VERIFIED-FIX]** and are binding — where this section contradicts §Context
> or §Impact Tree, this section wins.

### Research Sources
- `research-codebase.md` §2 — построчная диффа трёх пар, включая `%H`/`%h`
- `research-devil.md` DA-4 — ловушка monkeypatch, определившая выбор подхода
- [Ned Batchelder — One way to fix Python circular imports](https://nedbatchelder.com/blog/202405/one_way_to_fix_python_circular_imports) — различие `import X` и `from X import y`

### Hard constraints (restated — Coder must not relax any of these)

1. `callback.py` зовёт только через атрибут модуля: `gate_logic.match_subject(...)`.
   `from gate_logic import ...` в `callback.py` — **запрещено** (ломает monkeypatch, EC-5/EC-8).
   Правило действует ТОЛЬКО для `callback.py`; в `spec_verify.py` форма `from` допустима.
2. Семантика гейта не меняется ни в одном из EC-1..EC-11.
3. Трогать можно ТОЛЬКО файлы из `## Allowed Files`. Ничего больше — даже если тест красный.
4. `--cov-fail-under=54` в `.github/workflows/test.yml` **понижать нельзя**.
5. `tests/regression/**` и `tests/contracts/**` неприкосновенны (правило проекта + EC-11).

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

### [VERIFIED-FIX 3] — BLOCKER: удаление ломает 10 файлов вне Allowed Files

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

### Task 1: Перевести call-sites `callback.py` на `gate_logic`
**Type:** code
**Files:**
  - modify: `scripts/vps/callback.py`
**Pattern:** `callback.py:857` — существующий вызов `gate_logic.strip_bookkeeping_paths`
**Изменения:** ровно девять строк из таблицы «Живые call-sites» (731, 1217, 1255, 1257, 1272,
1273, 1514, 1522, 1523). Ничего не удалять, тела шести функций остаются на месте нетронутыми.
Комментарий на строке 38 переписать: `# noqa: E402 — single source of gate logic (TECH-210)`.
**Acceptance:**
- `grep -n "^from gate_logic import" scripts/vps/callback.py` → 0
- `python -m py_compile scripts/vps/callback.py` → exit 0
- девять вызовов идут через `gate_logic.`; функции ещё существуют; коммит без удалений
- `cd scripts/vps/tests && python -m pytest -q` зелёный (тесты всё ещё патчат
  `callback._is_done_on_develop`, но эти патчи теперь **не перехватывают** — ожидается, что
  часть тестов пойдёт в настоящий git; если какой-то тест из-за этого красный, это Task 4,
  а не повод откатывать Task 1)

### Task 2: Удалить копии и регэкспы — **ГЕЙТ, не выполнять без решения**
**Type:** code
**Files:**
  - modify: `scripts/vps/callback.py`

**STOP-условие.** Перед первой правкой проверить, разрешено ли одно из (a)/(b)/(c) из
[VERIFIED-FIX 3]. Если решения нет — **остановиться, ничего не удалять**, зафиксировать
в `## Autopilot Log` и уйти в `blocked` с причиной
`allowed_files_insufficient: 10 test files outside allowlist reference the removed names, one of them immutable`.
Догадываться и расширять `## Allowed Files` самостоятельно — запрещено.

**Если решение получено — удалить:** блоки строк 443-471 (семь регэкспов, состав по
[VERIFIED-FIX 1] — `_SPEC_ID_RE` на 43-45 **не трогать**), 474-510, 513-533, 536-572,
741-807, 810-827, 830-894. Баннер 441 и импорты 27/28 оставить.
При варианте (a) вместо удаления 536-572 поставить одну строку
`_parse_allowed_files = gate_logic.parse_allowed_files  # immutable regression corpus, TECH-210`.

**Acceptance:**
- `grep -c "_subject_implements\|_is_done_on_develop\|_fetch_develop\|_ALLOWED_FILES\|_ALLOWED_FILE_EXT_RE\|_NEXT_H2_RE" scripts/vps/callback.py` = 0
- `grep -c "_SPEC_ID_RE" scripts/vps/callback.py` = **4** (объявление + 3 использования в `resolve_spec_id`)
- `wc -l scripts/vps/callback.py` ≈ 1430 (было 1698)
- `python -c "import callback; assert not hasattr(callback,'_is_done_on_develop')"` (EC-6)
- отдельный коммит от Task 1

### Task 3: `spec_verify.py` на публичный парсер
**Type:** code
**Files:**
  - modify: `scripts/vps/spec_verify.py`
**Pattern:** `gate-daemon.py` — существующий потребитель `gate_logic.parse_allowed_files`
**Изменения (4 точки, все проверены):**
- :11 docstring `Uses:` → `scripts.vps.gate_logic.parse_allowed_files (TECH-167 canonical parser)`
- :32 комментарий → `# Reuse the canonical allowlist parser from gate_logic.py — single source of truth.`
- :37-41 `try: from callback import _parse_allowed_files` →
  `try: from gate_logic import parse_allowed_files` + текст ошибки на строке 40 привести к
  `gate_logic.parse_allowed_files`
- :228 `allowed = _parse_allowed_files(spec_path)` → `allowed = parse_allowed_files(spec_path)`
  — **эта строка в спеке не числилась**, без неё модуль падает на `NameError`

Задача независима от Task 2: `gate_logic.parse_allowed_files` существует уже сейчас.
**Acceptance:**
- `grep -c "callback" scripts/vps/spec_verify.py` = 0
- `python3 scripts/vps/spec_verify.py . TECH-208` даёт тот же вывод и тот же exit code, что до правки (EC-10)

### Task 4: Переписать тесты (только три файла из Allowed Files)
**Type:** test
**Files:**
  - modify: `scripts/vps/tests/test_callback.py` (870 LOC)
  - modify: `scripts/vps/tests/test_gate_logic.py` (720 LOC)
  - modify: `scripts/vps/tests/test_claude_runner_timeout.py` (222 LOC)

**4a. `test_callback.py` — 7 `monkeypatch.setattr` перенацелить на `gate_logic`:**

| Строка | Сейчас | Станет |
|---|---|---|
| 174 | `setattr(callback, "_fetch_develop", lambda *a: None)` | `setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)` |
| 175 | `setattr(callback, "_is_done_on_develop", lambda *a: True)` | `setattr(gate_logic, "find_implementation_commit", lambda *a: "deadbee")` |
| 214 | `_fetch_develop` | `gate_logic.fetch_develop` |
| 215 | `_is_done_on_develop` → `False` | `gate_logic.find_implementation_commit` → `None` |
| 690 | `original_is_done = callback._is_done_on_develop` | `original_is_done = gate_logic.find_implementation_commit` |
| 704 | `setattr(callback, "_is_done_on_develop", _delayed_is_done)` | `setattr(gate_logic, "find_implementation_commit", _delayed_is_done)` |
| 800 | `_fetch_develop` | `gate_logic.fetch_develop` |
| 801 | `_is_done_on_develop` → `False` | `gate_logic.find_implementation_commit` → `None` |

Внутри `_delayed_is_done` (692-702) первый возврат `False` заменить на `None` — тип теперь
`str | None`. Добавить `import gate_logic` рядом с `import callback` в шапке файла.
Строку-комментарий 544 («Do NOT stub `_fetch_develop` or `_is_done_on_develop`») переписать
на новые имена — тест EC-9 намеренно гоняет настоящий git, поведение не менять.

**4b. 29 ассертов матчера (355-447) → `test_gate_logic.py`.** Уже покрыто в
`test_gate_logic.py` (не дублировать): conventional feat :135, conventional fix+bang :140,
merge-форма :145, bare prefix :151, чужой spec_id :156, GROWTH :161, trailing parens со
scope :169 и без :180, multi-spec tail :191, `(see ID)` reject :199, mid-subject parens
reject :204, `merge:` colon-форма :209, `Merge branch '...'` :220, чужая ветка reject :231.

**Реально переезжают 12 кейсов, которых в `test_gate_logic.py` НЕТ:**
multi-scope `feat(FTR-925,FTR-926)` и с пробелом (361-362); lowercase scope (396-398);
mixed-case `feat(Ftr-1076)` (404); `merge FTR-925: impl` (369); `Merge feature/FTR-1076: ...` (407);
`Merge autopilot/BUG-1065 into develop` (410); `Merge fix/BUG-439 — restore constraint` (411);
case-insensitive multi-scope (414-415); `(FTR-1077 Task 3)` reject (429); пустые входы (386-387);
`feat(FTR-923): impl X (see also FTR-925)` reject (375).

Классы `TestSubjectImplements` (351), `TestSubjectImplementsRealWorld` (390),
`TestSubjectImplementsAntiFalsePositive` (418) удалить из `test_callback.py` целиком.
Класс `TestMatchSubjectParityWithCallback` (450-490) удалить — паритет двух копий теряет смысл,
когда копия одна; его 7 позитивов и 3 негатива уже присутствуют в `test_gate_logic.py`.
Добавить EC-5: тест, что `monkeypatch.setattr(gate_logic, "find_implementation_commit", fake)`
перехватывает вызов из `callback.verify_status_sync` (по DA-4 — выполнять **первым**).

⚠️ `test_gate_logic.py` уже 720 LOC при лимите 600 для тестов. Переезд 12 кейсов доводит
до ~790. Разбиение файла в scope не входит и `## Allowed Files` его не разрешает — принять
предсуществующее нарушение, не усугублять лишними кейсами.

**4c. `test_claude_runner_timeout.py:191-222` — `TestVariantCNeverIntroduced`:**
- :196 и :218 `(Path(VPS_DIR) / "callback.py")` → `"gate_logic.py"`
- :199 regex `def _is_done_on_develop\(` → `def find_implementation_commit\(`
- :201, :204, :212 тексты ассертов → `find_implementation_commit`
- :220-221 `assert "_fetch_develop(" in source` → `assert "fetch_develop(" in source`;
  `assert "_is_done_on_develop(" in source` → `assert "find_implementation_commit(" in source`

Смысл сохранить дословно: гейт не смеет ходить в голый локальный `develop`. Проверка
`origin/develop` in body и «нет bare `"develop"`» остаётся; сигнатура
`find_implementation_commit` многострочная (gate_logic.py:311-315), regex должен это пережить —
`r"def find_implementation_commit\(.*?\).*?(?=\ndef |\Z)"` с `re.DOTALL` подходит.

**Acceptance:**
- `cd scripts/vps/tests && python -m pytest -q` → 0 failed
- `grep -c "callback\._subject_implements\|callback\._is_done_on_develop\|callback\._fetch_develop" scripts/vps/tests/test_callback.py` = 0
- EC-5 проходит и падает, если вернуть `from gate_logic import ...` в `callback.py`

### Task 5: `gate_logic.py` под 400
**Type:** code
**Files:**
  - modify: `scripts/vps/gate_logic.py`
**Текущий размер:** 402 LOC — недобор ровно **3 строки**.
**Что резать (только docstring'и, ни строки кода):** строки 102 и 141 («Copied verbatim from
callback._parse_allowed_files_v1/_legacy») и 162 («Mirrors callback._parse_allowed_files»)
после Task 2 становятся ссылками на несуществующий код — удалить их. Это ровно 3 строки.
Дополнительно освежить 205 («Renamed from callback._subject_implements») и 283 («Renamed from
callback._fetch_develop») и 317-318 («Renamed from callback._is_done_on_develop») — они
исторически верны, оставить.
**Сохранить дословно:** упоминания TECH-177/L-derived-3 (207-210), BUG-192 (215, 219),
plpilot BUG-338/339/340/346/347 (220, 226-228), 2026-07-02 merge-формы (219-224),
birth-commit ADR-025 (63-68, 347-354), FF-09 invariant (19-20), Devil Attack 2/3/10 (289, 321).
**Acceptance:**
- `wc -l scripts/vps/gate_logic.py` ≤ 400 (EC-7)
- `grep -c "BUG-338\|TECH-177\|BUG-346\|ADR-025\|FF-09" scripts/vps/gate_logic.py` не уменьшился
- `PYTHONPATH=scripts/vps python -c "import gate_logic"` → exit 0, без вывода (AV-S2)

### Coverage-гейт (`.github/workflows/test.yml:64-72`)

Правку делать **только если** прогон реально красный. Проверять до и после:
```bash
PYTHONPATH=scripts/vps pytest tests/unit/test_callback_*.py \
  tests/integration/test_callback_*.py tests/regression/ \
  --cov=callback --cov-report=term-missing --cov-fail-under=54
```
Разрешено менять **чем** измеряется покрытие (например `--cov=callback --cov=gate_logic`).
Понижать `54` — запрещено, порог обязан остаться `--cov-fail-under=54` дословно.

### Execution Order
1 → 2 → 3 → 4 → 5

Порядок не переставлять: Task 1 отдельно от Task 2 — это разделение «перенаправить» и
«удалить» на два коммита, чтобы при регрессии было видно, какой из двух шагов виноват.
Task 3 формально независим (не требует Task 2), но идёт третьим, чтобы порядок коммитов
совпадал с порядком задач.

Если Task 2 остановлен по STOP-условию — Task 3 и Task 5 всё равно выполнимы и полезны
(они не зависят от удаления), Task 4 выполняется частично: 4a и 4c да, 4b нет (пока копии
на месте, ассерты по `callback._subject_implements` продолжают работать и удалять их нечем
обосновать).

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

### 2026-07-27 — BLOCKED at PHASE 1 (planner validation), zero code written

**ACTION REQUIRED — owner decision before this spec can execute.**

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
