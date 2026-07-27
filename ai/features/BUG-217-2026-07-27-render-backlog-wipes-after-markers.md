# Bug: [BUG-217] render_backlog стирает AFTER-маркеры — зависимости между спеками не живут

**Priority:** P1 | **Date:** 2026-07-27

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

- `scripts/vps/callback.py` — `_render_and_commit_backlog` на неразрушающий путь + устаревший комментарий `:1395-1397` (modify)
- `scripts/vps/render_backlog.py` — только module docstring: `Used by` лжёт про callback + warning про разрушительность `render_backlog()` (modify)
- `scripts/vps/tests/test_render_backlog.py` — e2e-замок: `AFTER` переживает `write_lifecycle` (modify)
- `scripts/vps/tests/test_callback.py` — покрытие обеих веток helper'а + ARCH-196 CQRS-замок (modify)
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

## Drift Log

**Checked:** 2026-07-27 UTC (plan agent, worktree `.worktrees/BUG-217`, branch `develop` @ `9ae31ce`)
**Result:** heavy_drift — **основная посылка спеки не воспроизводится на текущем коде**

### Changes Detected

| Файл | Что утверждала спека | Что в коде сейчас | Действие |
|------|----------------------|-------------------|----------|
| `scripts/vps/callback.py:1095-1120` | `_render_and_commit_backlog` зовёт полную пересборку на каждом цикле | Функция существует, но **не вызывается ниоткуда**. Единственный call-site удалён в ARCH-196 (CHANGELOG 3.17, 2026-05-28: «removed inline `_render_and_commit_backlog` call»). На его месте комментарий `callback.py:1395-1397` | ПОСЫЛКА СНЯТА |
| `scripts/vps/lifecycle.py:318-353` | (не упомянут) | **Живой писатель backlog** — `_atomic_write` читает `HEAD:ai/backlog.md`, гонит `render_backlog.sync_status(..., overrides={spec: new_status})` и вкладывает результат в **тот же** plumbing-коммит, что и yaml. WT синкается на `:396`. `AFTER` этот путь не трогает | ДОБАВЛЕНО В ПЛАН |
| `ai/backlog.md` | «grep "AFTER " → 0 попаданий, ни одна зависимость не пережила первый callback» | **Маркеры на месте:** `:29` `TECH-216 … AFTER TECH-210`, `:30` `ARCH-209 … AFTER TECH-210, …TECH-216` (7 штук). Написаны в `9ae31ce`, спека читала файл до этого коммита | ДОКАЗАТЕЛЬСТВО СНЯТО |
| `scripts/vps/tests/test_render_backlog.py:284-302` | «регрессия на выживание `AFTER` отсутствует» | Тест `test_sync_status_updates_only_status_preserving_content` **уже** проверяет `⛔ AFTER FTR-2` дословно (`:292`, `:302`) | ПЕРЕЦЕЛЕНО НА E2E |
| `scripts/vps/tests/test_orchestrator.py:732-800` | (не упомянут) | Читатель покрыт: `TestDependencyGate` — 6 кейсов на `_backlog_deps` / `_unmet_dependencies`. Файл **не** в Allowed Files → EC-6/7/8 новых тестов не требуют | EC ПЕРЕКЛАССИФИЦИРОВАНЫ |

### Точные строки (сверены чтением, спека была права)

| Ссылка в спеке | Факт |
|----------------|------|
| `callback.py:1095-1120` — `_render_and_commit_backlog` | ✅ точно 1095-1120 |
| `callback.py:1105` — вызов `render_backlog.render_backlog` | ✅ точно |
| `render_backlog.py:246-273` — `sync_status` | ✅ точно; сигнатура `sync_status(repo_dir, backlog_text: str, overrides: Optional[dict] = None) -> str` |
| `render_backlog.py:140-220` — `render_backlog()` | ⚠️ `def` на `:146`, тело 160-220 |
| `orchestrator.py:734` `_AFTER_DEP_RE`, `:737-755` `_backlog_deps`, `:758-771` `_unmet_dependencies`, `:728-733` комментарий | ✅ все точно |
| `lifecycle.py:332` — `sync_status` как безопасный образец | ✅ точно |

### Что осталось настоящим дефектом

Механизм `AFTER` сегодня **работает**. Но он работает **случайно**, и три вещи это не закрепляют:

1. **Заряженное ружьё.** `_render_and_commit_backlog` — мёртвый код, который зовёт разрушительную
   пересборку. Комментарий `callback.py:1396-1397` называет его «operator emergency CLI tool», но
   CLI-пути нет: `main()` (`:1562-1576`) знает только `--reset-circuit`. Строка «retained at line ~975»
   тоже устарела (реально 1095). `TECH-216` (раскол callback) перечисляет его как модуль `render`
   на 28 LOC — то есть его перенесут в новую структуру как живой компонент.
2. **Нет e2e-регрессии.** Юнит-тест проверяет `sync_status` изолированно. Что `AFTER` переживает
   **полный** цикл `lifecycle.write_lifecycle` (fold в plumbing-коммит + WT-checkout `:396`) — не
   проверяет никто. Именно этот путь единственный живой.
3. **Нет документации.** `docs/orchestrator/components.md` не описывает, кто пишет `ai/backlog.md`.
   Про `AFTER` там одна строка на стороне читателя (`:32-33`).

### Изменения объёма относительно исходного плана

| Было в спеке | Стало | Почему |
|--------------|-------|--------|
| Task 1 — «падающий» тест | Тест-**замок** (зелёный сразу) | Дефект не воспроизводится; тест фиксирует поведение, а не чинит |
| Task 2 — переключить callback на `sync_status` в hot path | Обезвредить мёртвый helper, hot path не трогать | Вернуть вызов в `verify_status_sync` = откатить ARCH-196 CQRS single-writer |
| `render_backlog.py` — «fallback на полную сборку, если строки ещё нет» | **Не менять** (только docstring) | Строки в backlog пишет Spark (`.claude/skills/spark/completion.md:80`), не машина. Append-путь — второй писатель, ровно то, что ARCH-196 убрал |
| EC-4 (новая спека дописывается) | **DROP** | см. выше — придуманная работа |
| EC-5 (fallback при отсутствии backlog) | Оставлен, но как одна ветка `if` в Task 2 | Дёшево и честно: новый проект |
| EC-6/EC-7/EC-8 | **Уже покрыты**, новых тестов нет | `test_orchestrator.py:732-800`, файл вне Allowed Files |

---

## Implementation Plan

> ⚠️ **Читать Drift Log выше перед началом.** Разделы `## Механизм` и `## Доказательство` в теле
> спеки описывают состояние кода **до ARCH-196** и фактически неверны. Источник истины по задаче —
> этот план.

### Research Sources
- `scripts/vps/lifecycle.py:318-353` — единственный живой писатель `ai/backlog.md` (`sync_status`, fold в тот же коммит)
- `scripts/vps/lifecycle.py:393-396` — WT-синк `ai/backlog.md` после plumbing-коммита
- `scripts/vps/render_backlog.py:227` `_BACKLOG_ROW_RE`, `:246-273` `sync_status`
- `scripts/vps/orchestrator.py:727-771` — читатель `AFTER` + инцидент ARCH-1246/FTR-1245
- `CHANGELOG.md:26` (v3.17) — ARCH-196 удалил inline-вызов рендера; backlog = single-writer
- `.claude/skills/spark/completion.md:77-83` — строку в backlog пишет Spark

---

### Task 1: E2E-замок — `AFTER` переживает полный цикл `write_lifecycle`

**Type:** test
**Files:**
- Modify: `scripts/vps/tests/test_render_backlog.py` (дописать в конец, после `test_sync_status_byte_identical_when_already_synced` на `:334-342`)

**Context:** сейчас проверено только, что чистая функция `sync_status` не трогает маркер.
Живой путь — `lifecycle.write_lifecycle` → `_atomic_write` (`lifecycle.py:318-353`) → fold backlog в
plumbing-коммит → WT-checkout (`:396`). Ни один тест не доказывает, что маркер переживает **его**.
Тест зелёный на текущем коде — это замок, а не воспроизведение (см. Drift Log).

**Step 1: дописать тест**

```python
# scripts/vps/tests/test_render_backlog.py — в КОНЕЦ файла


# ---------------------------------------------------------------------------
# BUG-217: AFTER-маркер переживает полный цикл lifecycle.write_lifecycle
# ---------------------------------------------------------------------------


def test_after_marker_survives_full_lifecycle_write(tmp_git_repo):
    """Живой путь записи backlog — lifecycle._atomic_write, а не render_backlog().

    Он читает HEAD:ai/backlog.md, гонит sync_status и вкладывает результат в тот же
    plumbing-коммит, что и yaml. Замок на то, что 'AFTER <ID>' (единственное место,
    где живёт зависимость между спеками — orchestrator._backlog_deps читает ТОЛЬКО
    строку backlog) не исчезает ни в HEAD, ни в WT.
    """
    import lifecycle
    import orchestrator

    repo = tmp_git_repo

    backlog = (
        "# DLD Backlog\n\n"
        "Проза, которую написал founder — не трогать.\n\n"
        "## P1 — High impact (default)\n\n"
        "| ID | Status | Kind | Updated | Spec |\n"
        "|----|--------|------|---------|------|\n"
        "| TECH-210 | queued | tech | 2026-07-27 | [spec](features/a.md) |\n"
        "| TECH-216 | queued | tech | 2026-07-27 | [spec](features/b.md) — AFTER TECH-210 |\n"
    )
    (repo / "ai" / "backlog.md").write_text(backlog, encoding="utf-8")
    subprocess.run(["git", "add", "ai/backlog.md"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "docs: backlog"], cwd=str(repo), check=True)

    lifecycle.create_initial(repo, "TECH-210", "p1", "tech", by="orchestrator")
    lifecycle.create_initial(repo, "TECH-216", "p1", "tech", by="orchestrator")

    # Полный цикл: статус TECH-210 едет queued -> in_progress -> done
    lifecycle.write_lifecycle(repo, "TECH-210", "in_progress", by="callback")
    lifecycle.write_lifecycle(repo, "TECH-210", "done", by="callback")

    head = subprocess.run(
        ["git", "show", "HEAD:ai/backlog.md"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    wt = (repo / "ai" / "backlog.md").read_text(encoding="utf-8")

    # EC-1: маркер жив в HEAD и в WT, ровно один раз
    assert head.count("AFTER TECH-210") == 1, f"AFTER стёрт в HEAD:\n{head}"
    assert wt.count("AFTER TECH-210") == 1, f"AFTER стёрт в WT:\n{wt}"

    # EC-2: статус всё-таки синхронизирован
    assert "| TECH-210 | done |" in head

    # EC-3: проза и структура целы
    assert "Проза, которую написал founder — не трогать." in head
    assert "## P1 — High impact (default)" in head

    # EC-6: читатель зависимостей видит маркер после цикла (читает WT)
    assert orchestrator._backlog_deps(str(repo), "TECH-216") == {"TECH-210"}
```

**Step 2: запустить**

```bash
cd /home/dld/projects/dld/.worktrees/BUG-217/scripts/vps/tests
python -m pytest test_render_backlog.py::test_after_marker_survives_full_lifecycle_write -v
```

Ожидается: `PASSED`. **Если FAILED — остановиться и доложить:** значит найден настоящий, ещё не
описанный дефект в `lifecycle._atomic_write`, и план надо пересобрать (`lifecycle.py` не в Allowed Files).

**Возможные подводные камни (проверить, если тест не зелёный):**
- `orchestrator` тянет `db` и `gate_logic` на импорте — если импорт падает, вынести проверку EC-6
  в отдельный тест и пометить `pytest.importorskip("orchestrator")`.
- `lifecycle._push_best_effort` в репозитории без `origin` уходит в best-effort ветку и только пишет
  WARNING — исключения быть не должно (см. `test_lifecycle_push_rebase.py`).
- Фикстура `tmp_git_repo` (`:29-62`) создаёт ветку `main` — `_current_branch` это переваривает.

**Acceptance Criteria:**
- [ ] Тест зелёный
- [ ] `python -m pytest test_render_backlog.py -q` — 0 failed (8 кейсов было, стало 9)

---

### Task 2: Обезвредить `_render_and_commit_backlog` (мёртвый разрушительный путь)

**Type:** code
**Files:**
- Modify: `scripts/vps/callback.py:1095-1120` (тело функции) и `:1395-1397` (устаревший комментарий)
- Modify: `scripts/vps/render_backlog.py:1-20` (module docstring — секция `Used by` лжёт)

**Context:** функция не вызывается ниоткуда (Drift Log), но зовёт полную пересборку, которая стирает
`AFTER`, описания founder'а и структуру секций. TECH-216 планирует перенести её в модуль `render` как
живой компонент. Делаем её неразрушающей **на месте** и в hot path НЕ возвращаем — иначе откатим
ARCH-196 (single-writer / CQRS).

**Step 1: заменить тело `_render_and_commit_backlog`**

`scripts/vps/callback.py` — заменить строки 1095-1108 (docstring + первый `try`), блок
`lifecycle.write_file_atomic` (`:1109-1120`) остаётся как есть:

```python
def _render_and_commit_backlog(project_path: str, project_id: str) -> None:
    """Operator-only backlog refresh. NOT wired into verify_status_sync.

    ARCH-196 removed the inline call site: ai/backlog.md is single-writer
    (spark/autopilot Edit), and lifecycle._atomic_write already folds a
    status-only `render_backlog.sync_status` pass into the same plumbing
    commit as the yaml (lifecycle.py:318-353). Do NOT re-wire this into the
    callback hot path.

    This helper must stay NON-DESTRUCTIVE (BUG-217). `render_backlog.render_backlog()`
    rebuilds the file from lifecycle yaml alone and destroys founder descriptions,
    section structure and `AFTER <ID>` markers. Those markers are the ONLY place a
    dependency between specs lives — `orchestrator._backlog_deps` (orchestrator.py:737)
    reads nothing else, and it fails silently: no marker -> empty dep set -> dispatch.
    So: sync statuses into the backlog that is already in HEAD; fall back to the full
    rebuild only when HEAD has no ai/backlog.md at all (new project).

    Best-effort: logged, never raises.
    """
    try:
        import render_backlog

        head = lifecycle.run_git(["git", "show", "HEAD:ai/backlog.md"], cwd=project_path)
        if head.returncode == 0:
            content = render_backlog.sync_status(project_path, head.stdout)
        else:
            log.info("RENDER: no ai/backlog.md in HEAD for %s — full rebuild", project_id)
            content = render_backlog.render_backlog(project_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("RENDER: backlog render failed for %s: %s", project_id, exc)
        return
    try:
        ok = lifecycle.write_file_atomic(
            project_path,
            "ai/backlog.md",
            content,
            "render(backlog): status sync from lifecycle",
            by="callback",
        )
        if not ok:
            log.warning("RENDER: write_file_atomic returned False for %s", project_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("RENDER: write_file_atomic raised for %s: %s", project_id, exc)
```

Заметки для coder'а:
- `lifecycle` уже импортирован (`callback.py:39`); `lifecycle.run_git` — публичный алиас байтового
  `_run` (`lifecycle.py:184-187`), использовать его, а **не** `subprocess.run(..., text=True)`:
  `text=True` ломается на кириллице в backlog (cp1251) — тот же класс, что и в `lifecycle._run`.
- `write_file_atomic` при совпадении с HEAD сам делает no-op и возвращает `True` (`lifecycle.py:788-790`).
- Сообщение коммита меняем с `auto-sync from lifecycle` на `status sync from lifecycle` — теперь оно
  описывает то, что действительно происходит.

**Step 2: поправить устаревший комментарий `callback.py:1395-1397`**

```python
    # Rule 5 (ARCH-196): inline backlog render REMOVED — backlog.md is now
    # single-writer (spark/autopilot Edit); lifecycle._atomic_write folds a
    # status-only sync_status pass into the same commit as the yaml.
    # _render_and_commit_backlog (:1095) is an operator-only helper with no
    # live caller. Re-wiring it here reverts ARCH-196 — do not.
```

(старый текст говорил «retained at line ~975» — функция давно на 1095.)

**Step 3: поправить module docstring `render_backlog.py:14-18`**

Секция `Used by` утверждает `callback.py: optional post-write render` — call-site нет с ARCH-196.
Заменить блок `Used by:` на:

```
Used by:
  - lifecycle.py: _atomic_write() folds sync_status() into the lifecycle commit
    (the ONLY live writer of ai/backlog.md — status cells only)
  - migrate_backlog_to_lifecycle.py: full render after migration (one-shot)
  - callback.py: _render_and_commit_backlog — operator-only, no live caller

WARNING: render_backlog() rebuilds the file from lifecycle yaml alone. It destroys
founder descriptions, section structure and `AFTER <ID>` dependency markers (BUG-217).
Use sync_status() unless the file genuinely does not exist yet.
```

**Step 4: проверить**

```bash
cd /home/dld/projects/dld/.worktrees/BUG-217
python -m py_compile scripts/vps/callback.py scripts/vps/render_backlog.py
cd scripts/vps/tests && python -m pytest test_render_backlog.py test_callback.py -q
```

**Acceptance Criteria:**
- [ ] `py_compile` exit 0
- [ ] `grep -c "render_backlog.render_backlog" scripts/vps/callback.py` = 1 (только fallback-ветка)
- [ ] `grep -n "_render_and_commit_backlog(" scripts/vps/callback.py` — 0 вызовов (только `def`)
- [ ] Тест Task 1 всё ещё зелёный
- [ ] `render_backlog()` не удалена

---

### Task 3: Покрытие helper'а + документация

**Type:** test + docs
**Files:**
- Modify: `scripts/vps/tests/test_callback.py` (дописать класс в конец файла)
- Modify: `docs/orchestrator/components.md` (новая секция перед `## Side monitors`, `:152`)

**Context:** закрепить обе ветки нового `_render_and_commit_backlog` и записать в доки, кто на самом
деле пишет `ai/backlog.md` — сейчас там про это ничего, из-за чего спека BUG-217 и была написана
против несуществующего механизма.

**Step 1: тесты в `scripts/vps/tests/test_callback.py`** (в конец файла; фикстура `git_repo` — `:67-78`)

```python
# ---------------------------------------------------------------------------
# BUG-217: _render_and_commit_backlog must not destroy the backlog
# ---------------------------------------------------------------------------


class TestRenderAndCommitBacklog:
    """Operator-only helper. Non-destructive by contract — it is the one place
    left in the codebase that can still call the full rebuild."""

    _BACKLOG = (
        "# DLD Backlog\n\nfounder prose — keep\n\n"
        "## P1 — High impact (default)\n\n"
        "| ID | Status | Kind | Updated | Spec |\n"
        "|----|--------|------|---------|------|\n"
        "| TECH-210 | queued | tech | 2026-07-27 | [spec](features/a.md) |\n"
        "| TECH-216 | queued | tech | 2026-07-27 | [spec](features/b.md) — AFTER TECH-210 |\n"
    )

    def test_no_live_caller_in_verify_status_sync(self):
        """ARCH-196 CQRS lock: the helper must stay unwired from the hot path."""
        src = (Path(callback.__file__)).read_text(encoding="utf-8")
        calls = [ln for ln in src.splitlines() if "_render_and_commit_backlog(" in ln]
        assert len(calls) == 1, f"expected def only, found call sites: {calls}"
        assert calls[0].lstrip().startswith("def "), calls[0]

    def test_preserves_after_marker_and_prose(self, git_repo):
        """EC-1/EC-2/EC-3: statuses sync, everything else is byte-preserved."""
        (git_repo / "ai").mkdir(exist_ok=True)
        (git_repo / "ai" / "backlog.md").write_text(self._BACKLOG, encoding="utf-8")
        _git(git_repo, "add", "ai/backlog.md")
        _git(git_repo, "commit", "-q", "-m", "docs: backlog")

        lifecycle.create_initial(git_repo, "TECH-210", "p1", "tech", by="orchestrator")
        lifecycle.write_lifecycle(str(git_repo), "TECH-210", "in_progress", by="callback")

        callback._render_and_commit_backlog(str(git_repo), "testproj")

        out = _git(git_repo, "show", "HEAD:ai/backlog.md")
        assert out.count("AFTER TECH-210") == 1
        assert "founder prose — keep" in out
        assert "## P1 — High impact (default)" in out
        assert "| TECH-210 | in_progress |" in out

    def test_falls_back_to_full_render_when_backlog_absent(self, git_repo):
        """EC-5: new project — HEAD has no ai/backlog.md, full rebuild is correct."""
        lifecycle.create_initial(git_repo, "TECH-210", "p1", "tech", by="orchestrator")

        callback._render_and_commit_backlog(str(git_repo), "testproj")

        out = _git(git_repo, "show", "HEAD:ai/backlog.md")
        assert "# DLD Backlog" in out
        assert "TECH-210" in out
```

Заметки для coder'а:
- `Path`, `callback`, `lifecycle`, `_git`, `git_repo` уже есть в файле (`:15`, `:24-26`, `:34-51`, `:67-78`).
- Фикстура `git_repo` НЕ создаёт `ai/` — в первом тесте каталог создаётся явно;
  `lifecycle.create_initial` каталог `ai/lifecycle` создаёт сам через plumbing.
- Если `_render_and_commit_backlog` в первом тесте не поменял ничего (статусы уже совпали) —
  `write_file_atomic` вернёт `True` без коммита; ассерты всё равно проходят, файл читается из HEAD.

**Step 2: секция в `docs/orchestrator/components.md`** — вставить **перед** `## Side monitors` (`:152`):

```markdown
## <a name="backlog"></a>ai/backlog.md — кто пишет и почему это важно

`ai/backlog.md` — **не** SoT (ADR-023), но и не чистый рендер: часть данных живёт **только** там.

| Писатель | Что пишет | Разрушает ли соседние байты |
|----------|-----------|------------------------------|
| Spark / autopilot (Edit) | Новую строку спеки, описание, `AFTER <ID>` | нет (ручная правка) |
| `lifecycle._atomic_write` (`:318-353`) | **Только ячейку Status** существующих строк, через `render_backlog.sync_status`. Вкладывается в тот же plumbing-коммит, что и yaml; WT синкается на `:396` | нет — по построению |
| `callback._render_and_commit_backlog` (`:1095`) | Operator-only, **живых вызовов нет** (ARCH-196). После BUG-217 тоже идёт через `sync_status`; полная пересборка — только когда файла нет в HEAD | нет |
| `render_backlog.render_backlog()` (`:146`) | Полная пересборка из lifecycle-yaml | **ДА** — стирает описания founder'а, структуру секций и `AFTER`-маркеры |

**Противоречие, которое надо помнить:** зависимость между спеками (`AFTER <ID>`) существует
**только** в строке backlog. `orchestrator._backlog_deps` (`:737-755`) не читает ничего другого,
а `_unmet_dependencies` (`:758-771`) на этом основании не даёт `scan_queued` диспатчить спеку.
Отказ молчаливый: маркера нет → пустое множество → диспатч. То есть для одного поля backlog
де-факто и есть SoT. Пока это так — `render_backlog()` нельзя ставить ни в один автоматический путь.
Правильное решение (`after:` в lifecycle-yaml) — смена SoT, требует ADR; см. upstream-сигнал BUG-217.

**Инвариант:** `grep -n "_render_and_commit_backlog(" scripts/vps/callback.py` → только `def`.
Возврат вызова в `verify_status_sync` откатывает ARCH-196 (single-writer backlog).
```

**Step 3: проверить**

```bash
cd /home/dld/projects/dld/.worktrees/BUG-217/scripts/vps/tests
python -m pytest test_callback.py test_render_backlog.py -q
```

**Acceptance Criteria:**
- [ ] 3 новых кейса зелёные
- [ ] В `components.md` есть секция `ai/backlog.md — кто пишет`
- [ ] `python -m pytest -q` в `scripts/vps/tests` — 0 failed

---

### Execution Order

```
Task 1 (замок, зелёный) → Task 2 (обезвредить) → Task 3 (покрытие + доки)
```

Строго последовательно. Task 1 — гейт: если он **падает**, дефект глубже описанного, остановиться
и доложить (правка ушла бы в `lifecycle.py`, которого нет в Allowed Files).

### Dependencies

- Task 2 зависит от Task 1 (Task 1 фиксирует поведение, которое Task 2 не должен сломать)
- Task 3 зависит от Task 2 (тестирует новое тело функции)
- Параллелить нечего — 3 задачи, ~120 LOC суммарно

### Sync Zone Check

Ни один файл из Allowed Files не лежит в `.claude/` или `scripts/` (шаблонных) — `scripts/vps/`
в `template/` не зеркалится. **Sync-задача не нужна.**

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

> Пересобрано после Drift Check. EC-4 снят (append-путь — придуманная работа, строки пишет Spark);
> EC-7/EC-8 уже покрыты `test_orchestrator.py:732-800`, файл вне Allowed Files.

| ID | Scenario | Input | Expected | Type | Task | Priority |
|----|----------|-------|----------|------|------|----------|
| EC-1 | `AFTER` переживает полный цикл `write_lifecycle` | backlog со строкой `\| TECH-216 \| queued \| tech \| ... AFTER TECH-210 \|`, затем `write_lifecycle(TECH-210, in_progress→done)` | маркер на месте в HEAD **и** в WT, ровно 1 раз | deterministic | Task 1 | P0 |
| EC-2 | Статус всё ещё синхронизируется | lifecycle `done`, backlog `queued` | ячейка стала `done` | deterministic | Task 1, 3 | P0 |
| EC-3 | Проза и структура секций целы | backlog с заголовками и текстом founder'а | сохранены дословно | deterministic | Task 1, 3 | P0 |
| EC-5 | Отсутствующий backlog | `ai/backlog.md` нет в HEAD | `_render_and_commit_backlog` → полная сборка, файл создан | deterministic | Task 3 | P1 |
| EC-6 | `_backlog_deps` видит маркер после цикла | backlog после `write_lifecycle` | `{"TECH-210"}` | deterministic | Task 1 | P0 |
| EC-9 | Helper не возвращён в hot path | исходник `callback.py` | `_render_and_commit_backlog(` встречается 1 раз, и это `def` | deterministic | Task 3 | P0 |
| EC-10 | Helper не разрушает backlog | backlog в HEAD + вызов helper'а напрямую | `AFTER` + проза целы, статус синхронизирован | deterministic | Task 3 | P0 |

### Уже покрыто — новых тестов не пишем

| ID | Что | Где покрыто |
|----|-----|-------------|
| EC-7 | `AFTER` с незакрытой зависимостью блокирует диспатч | `test_orchestrator.py` `TestDependencyGate` (`:732-800`) |
| EC-8 | Зависимость `done` → диспатч разрешён | там же |
| — | `sync_status` сохраняет `AFTER` изолированно | `test_render_backlog.py:284-302` |

### Coverage Summary
Deterministic: 7 новых | Integration: 0 новых (2 существующих) | LLM-Judge: 0 | Total: 7 (min 3 ✓)

### TDD Order
1. EC-1, EC-2, EC-3, EC-6 — Task 1, один e2e-тест. **Замок, не воспроизведение** — зелёный сразу
2. EC-9, EC-10, EC-5 — Task 3, после правки Task 2

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
- [ ] `AFTER`-маркер переживает полный цикл `lifecycle.write_lifecycle` — в HEAD и в WT
- [ ] Статусы синхронизируются как раньше
- [ ] `_render_and_commit_backlog` при вызове больше не разрушает backlog

### Tests
- [ ] EC-1, EC-2, EC-3, EC-5, EC-6, EC-9, EC-10 проходят
- [ ] EC-7/EC-8 подтверждены как уже покрытые (`test_orchestrator.py:732-800`), новых тестов нет
- [ ] ⚠️ EC-1 **зелёный сразу** — это замок, а не воспроизведение. Если он падает — остановиться
      и доложить: дефект в `lifecycle.py`, которого нет в Allowed Files

### Acceptance Verification
- [ ] AV-S1, AV-F1, AV-F2 локально
- [ ] AV-F3 — `grep -c "AFTER " ai/backlog.md` ≥ 1 (сейчас 2, деградации быть не должно)
- [ ] AV-F4 на VPS

### Technical
- [ ] `render_backlog()` не удалена и по-прежнему не вызывается ни из одного автоматического пути
- [ ] `_render_and_commit_backlog` не имеет живых вызовов (ARCH-196 CQRS сохранён)
- [ ] Устаревший комментарий `callback.py:1395-1397` («line ~975») исправлен
- [ ] `render_backlog.py` module docstring больше не утверждает, что callback его зовёт
- [ ] В `docs/orchestrator/components.md` есть секция «`ai/backlog.md` — кто пишет»

### Не делаем (зафиксировано Drift Check)
- [ ] Append-путь «строки ещё нет» — **не реализуем** (второй писатель, откат ARCH-196)
- [ ] `_render_and_commit_backlog` **не** возвращаем в `verify_status_sync`
- [ ] `lifecycle.py` не трогаем — он уже делает правильную вещь

---

## Autopilot Log
