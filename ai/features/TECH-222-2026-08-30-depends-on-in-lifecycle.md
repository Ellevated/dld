# Feature: [TECH-222] Зависимости задач — в lifecycle YAML, а не в генерируемой таблице

**Priority:** P1 | **Date:** 2026-08-30 | **AFTER TECH-220, AFTER TECH-221**
**Size:** 9 tasks / 12 files — reader и producer идут одним коммитом: схема без того, кто её
заполняет, — это инфраструктура, которую никто не пишет (devil §Argument 1).
(Изначально «6 tasks»: план разбил их на 9 bite-sized, набор файлов не изменился.)

> **Почему AFTER:** TECH-220, TECH-221 и эта спека правят один и тот же
> `scripts/vps/orchestrator_queue.py` (371 из 400 LOC) — параллельный запуск даёт конфликт мержа
> и пробитый потолок файла. Зависимость объявлена и строкой в `ai/backlog.md` — единственным
> механизмом, который сегодня работает. То, что спека про зависимости вынуждена объявлять свою
> зависимость вручную, и есть её обоснование.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Планировщик решает «можно ли диспатчить спеку» по маркерам `AFTER <ID>` в строке
`ai/backlog.md` — файла, который сам же объявлен авто-генерируемым видом
(`AUTO-GENERATED from ai/lifecycle/*.yaml — do not edit manually`). Носителя нет:

| Кто должен был писать строку | Что на самом деле |
|---|---|
| Spark | `.claude/skills/spark/completion.md` §«The backlog is a render» прямо запрещает — кроме случая, когда CAS-claim не удался |
| `callback._render_and_commit_backlog` → `render_backlog.render_backlog()` | **мёртвый код**: `grep -rn "_render_and_commit_backlog" scripts/vps/` → одно определение, ноль вызовов |
| живой путь `lifecycle_cas._atomic_write` → `render_backlog.sync_status` | правит **только ячейку Status у уже существующих строк**, новых не добавляет |

Последний коммит `render(backlog): auto-sync from lifecycle` — **26.05.2026**. Значит
`_backlog_deps` возвращает пустое множество для **каждой** спеки, созданной после мая:
DEP_GATE мёртв, и это не заметно, потому что его молчание неотличимо от «зависимостей нет».

Живой инцидент 30.08: TECH-221 объявляет `**AFTER TECH-220**` в прозе спеки; строки в backlog
нет вовсе, `depends_on` некуда положить, и планировщик собирался отправить его во второй слот
параллельно с TECH-220 — обе правят `scripts/vps/gate_logic.py` и промпты автопилота в двух
деревьях. Удержано вручную: `spec_operator.py demote --blocked` + сторож на VPS
(`~/ops/unblock-tech221-when-220-done.sh`). Это ровно тот класс, что чинит ARCH-219: **контракт
живёт в генерируемом тексте вместо факта в git.**

Перекос уже был записан месяц назад — `ai/reflect/upstream-signals.md`,
`SIGNAL-2026-07-27-spark-ARCH-209` («correct direction, wrong size for a bug fix»), и остался без
решения. TECH-222 — это решение.

## Context

Скауты: `ai/.spark/20260830-TECH-222/research-{web,codebase,devil}.md`.

**Внешняя практика единогласна** (research-web §Approaches): GitHub Actions `needs:`, GitLab CI
`needs:`, Dagster `deps=`, Tekton `runAfter` — ребро хранится **на зависимом объекте**, плоским
списком ID, никогда на родителе и никогда в отдельном реестре. Для DLD это ещё и единственное
направление, бесплатное при per-file CAS: `depends_on` пишется в тот же файл и в тот же коммит,
что создаёт спеку. «Родитель объявляет детей» потребовал бы мутировать чужой — возможно уже
`done`, то есть терминальный по Rule 7 — YAML.

**Fleet-аудит проведён до написания спеки** (devil §Argument 3, SA-9 — закрыт фактом). Грепом по
`ai/backlog.md` всех 11 проектов из живого `projects.json` на VPS:

| Проект | Строк с `AFTER` |
|---|---|
| **dld** | 3 — `TECH-215 → BUG-218` (done), `TECH-216 → TECH-210` (done), **`ARCH-209 → TECH-210…TECH-216` (queued)** |
| awardybot, dowry, dowry-mc, nexus, plpilot, gipotenuza, memyselfandi, mishkinlyap, wb | 0 |

Мигрировать нужно ровно одну живую строку. Флоту терять нечего.

**Гейт держит работу прямо сейчас** (devil §Argument 4, DA-1): `TECH-213.status = blocked` с
07.08, ARCH-209 зависит от него, `_unmet_dependencies("ARCH-209") == ["TECH-213"]`, и
`_select_dispatchable_spec` пропускает ARCH-209 каждый цикл. Утверждение обратного в
`research-codebase.md` («no live spec is currently blocked by a backlog-only AFTER») — **ошибка
скаута**, пойманная devil'ом и перепроверенная по обоим файлам-источникам. Миграция обязана
сохранить этот гейт; ошибка в ней = ARCH-209 уезжает в работу поверх незавершённого раскола
`claude-runner.py`.

## Scope

**In scope:** поле `depends_on` в lifecycle YAML; чтение его планировщиком; заполнение при
создании спеки (Spark); одноразовая миграция ARCH-209; удаление мёртвой
`_render_and_commit_backlog`; доки и промпты, описывающие механизм.

**Out of scope:**
- Удаление `ai/backlog.md` — `orchestrator_backlog.bootstrap_new_specs:195` пропускает спеку,
  которой нет в бэклоге (`if spec_id not in backlog_ids: continue`). Бэклог остаётся частью
  handshake для проектов, где Spark не может заклеймить ID сам.
- Воскрешение полного `render_backlog.render_backlog()` — по собственному комментарию
  `sync_status` он «destroys founder descriptions / section structure / AFTER markers». Это
  регрессия, которую текущий дизайн уже однажды обошёл (devil §Alternative 1).
- Транзитивное разрешение: проверяем только прямых родителей, как Airflow и GH Actions. A→B→C
  работает само.
- Приоритеты, порядок диспатча, `AFTER` в даунстримах (их нет — см. аудит).

## Impact Tree Analysis

### Step 1: UP — кто зовёт
`_backlog_deps` ← `_unmet_dependencies` ← `_select_dispatchable_spec` (`orchestrator.py:188`) ←
`scan_queued` ← главный цикл демона. Один путь, ветвлений нет.

### Step 2: DOWN — от чего зависит
`lifecycle.read_lifecycle` (уже отдаёт весь словарь YAML — новое поле доступно без нового
чтения), `Path`, `re`.

### Step 3: BY TERM
```
grep -rn "_backlog_deps\|_unmet_dependencies\|_AFTER_DEP_RE" scripts/vps/   → orchestrator_queue.py, orchestrator.py (re-export), tests
grep -rn "_render_and_commit_backlog" .                                     → callback.py:187 (только определение)
grep -rn "AFTER" ai/backlog.md docs/orchestrator/*.md .claude/skills/spark/ → backlog 3 строки, README:104,181, components:32-33,215
```

### Step 4: CHECKLIST
- [x] `scripts/vps/tests/` — `TestDependencyGate` (**8** тестов, `test_orchestrator.py:753-886`)
- [x] `scripts/vps/tests/test_lifecycle.py` для `create_initial`/`set_depends_on`
      (корневого `tests/test_lifecycle.py` не существует — путь в Allowed Files верный)
- [x] `template/` — копии `spark/completion.md` и `spark/feature-mode.md` (обе правятся);
      `scripts/vps/` в `template/` отсутствует — проверено
- [x] `docs/orchestrator/README.md`, `components.md` — описывают гейт как чтение backlog-строки

### Step 5: DUAL SYSTEM
Два источника зависимостей на переходный период — намеренно: YAML (новый) ∪ backlog (старый,
фолбэк с метрикой `deps_via` и датой смерти). Тот же паттерн, что `gate_via` в TECH-220.
Удаление backlog-пути — отдельная TECH, когда `deps_via=backlog` не срабатывает 30 дней.

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/lifecycle.py` — `create_initial(..., depends_on=None)`, новая `set_depends_on` через callable-CAS (modify)
- `scripts/vps/lifecycle_git.py` — `_build_yaml_content`: `depends_on` в обеих ветках create/update (modify)
- `scripts/vps/orchestrator_queue.py` — `_spec_deps` = YAML ∪ backlog + метрика `deps_via`; `_unmet_dependencies` зовёт её (modify)
- `scripts/vps/callback.py` — удалить мёртвую `_render_and_commit_backlog` (modify)
- `scripts/vps/tests/test_orchestrator.py` — `TestDependencyGate` переписать на YAML-фикстуры (modify)
- `scripts/vps/tests/test_lifecycle.py` — `depends_on` в `create_initial`, `set_depends_on`, гонка (modify)
- `.claude/skills/spark/completion.md` — конвенция `**AFTER <ID>**` → `depends_on=`; исправить враньё про мёртвый рендер (modify)
- `.claude/skills/spark/feature-mode.md` — тот же kwarg в примере `create_initial` (modify)
- `template/.claude/skills/spark/completion.md` — зеркало (modify)
- `template/.claude/skills/spark/feature-mode.md` — зеркало (modify)
- `docs/orchestrator/README.md` — DEP_GATE читает YAML (modify)
- `docs/orchestrator/components.md` — то же в описании `orchestrator_queue` (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

⛔ `ai/lifecycle/*.yaml` НЕ в списке намеренно: запись только через плумбинг, pre-commit hook
блокирует staged-правку. Миграция ARCH-209 — операторский шаг после мержа, см. одноимённую
секцию в конце `## Implementation Plan`; в задачи автопилота (Task 1-9) она не входит.

---

## Environment

nodejs: false
docker: false
database: false

## Blueprint Reference

ADR-023 (lifecycle YAML = SoT статуса, backlog = вид) — спека доводит его до конца: зависимость
такой же факт о задаче, как её статус, и должна лежать там же. ADR-024 (`by` обязателен при
записи lifecycle) — `set_depends_on` принимает `by`.

## Historical Risks

| Урок | Источник | Как учтён |
|---|---|---|
| Переименование функции ломает `monkeypatch` по голому имени молча | `orchestrator.py:190-195` (собственный докстринг), devil DA-8 | `_unmet_dependencies`, `_backlog_deps` и re-export `orchestrator.py:389-394` сохраняют имена и место байт-в-байт; меняется только тело |
| Полный рендер бэклога уничтожает ручные строки | `render_backlog.py:250-253` | Полный рендер не воскрешаем; мёртвую обёртку удаляем |
| Фикстура вместо живого состояния прячет ошибку | ошибка `research-codebase.md`, пойманная devil'ом | EC-1 проверяется на **живом** репо, а не только на synthetic-фикстуре |
| Фолбэк без сигнала = тихая деградация | ARCH-219/TECH-220 (`gate_via`) | `deps_via` в лог при каждом непустом множестве legacy-зависимостей |

## Approaches

| # | Подход | Вердикт |
|---|---|---|
| 1 | `depends_on: [ID]` в lifecycle YAML зависимой спеки | **выбран** — совпадает с практикой (`needs:`), бесплатен при per-file CAS, переживает удаление бэклога |
| 2 | Воскресить полный `render_backlog()` и оставить чтение из строки | отклонён — уничтожает founder-прозу и сами `AFTER`-маркеры, то есть ломает то, на что опирается |
| 3 | Парсить `**AFTER <ID>**` из прозы спеки демоном | отклонён как основной (`_AFTER_DEP_RE` docstring: проза «too noisy to parse reliably»), но именно эта строка становится **источником для Spark** при создании — парсит промпт, а не демон |
| 4 | Dual-read как временный режим | принят **как способ выката**, а не как цель: YAML ∪ backlog с метрикой и датой смерти |

## Design

### Схема

```yaml
depends_on: []            # список spec_id; отсутствие ключа ≡ []
```

Пишется в двух местах и только там: `create_initial` (новая спека) и `set_depends_on`
(ретрофит существующей). Валидатора схемы у lifecycle нет (`lifecycle_git._build_yaml_content`
— обычный dict + `yaml.safe_dump`, неизвестные ключи и так проходят), поэтому поле добавляется
явно в обе ветки, а не «доедет round-trip'ом».

### Чтение

```python
def _spec_deps(project_dir: str, spec_id: str) -> set:
    """Объявленные зависимости: lifecycle YAML (новое) ∪ backlog-строка (deprecated)."""
    lc = lifecycle.read_lifecycle(project_dir, spec_id) or {}
    raw = lc.get("depends_on") or []
    if not isinstance(raw, list):
        log.warning("DEP_SHAPE: %s depends_on is %s, not list — ignored", spec_id, type(raw).__name__)
        raw = []
    yaml_deps = {d.upper() for d in raw if isinstance(d, str)}
    legacy = _backlog_deps(project_dir, spec_id)
    if legacy - yaml_deps:
        log.info("DEP_VIA: %s deps_via=backlog (legacy) %s", spec_id, sorted(legacy - yaml_deps))
    return yaml_deps | legacy
```

`_unmet_dependencies` меняет ровно одну строку — `_backlog_deps(...)` → `_spec_deps(...)`.
Fail-open («зависимость без lifecycle-записи считается выполненной») **сохраняется без
изменений**: это ответ на вопрос devil №5 — опечатка и архивная ссылка неотличимы по данным,
а тихий вечный стоп хуже лишнего диспатча. Опечатка ловится раньше, на записи (Task 4).

### Запись в существующую спеку

`write_file_atomic` для этого не годится: её retry передаёт **статически вычисленный** `content`
на каждую попытку (`lifecycle.py:255-301`), поэтому параллельная смена статуса в окне
чтение→коммит молча откатится (devil §Argument 2, DA-6). `set_depends_on` строится на
`lifecycle_cas._cas_loop(repo_dir, spec_id, branch, yaml_fn)` — том же callable-контракте, что
уже используют `write_lifecycle` и `create_initial`: на каждом retry запись пересобирается из
свежей записи, статус сохраняется.

### Producer (Spark)

Конвенция уже существует де-факто — TECH-221 объявляет `**AFTER TECH-220**` в шапке. Она
становится машиночитаемой: Spark извлекает `AFTER <ID>` из шапки спеки и передаёт
`depends_on=[...]` в `create_initial`. Демон прозу не парсит — парсит промпт, один раз, в момент
создания.

## Implementation Plan

> **Три жёстких потолка, найденных при планировании — читать до первой правки.**
>
> | Файл | Сейчас | Потолок | Кто ловит |
> |---|---|---|---|
> | `scripts/vps/orchestrator_queue.py` | **400** (не 371, как написано выше — TECH-220/221 съели запас) | 400 | `test_orchestrator.py::TestSplitStructuralInvariants::test_file_under_loc_limit` |
> | `scripts/vps/lifecycle.py` | 372 | 400 | `test_lifecycle.py::TestSplitContract::test_every_module_under_the_loc_limit` |
> | `scripts/vps/callback.py` | 400 | 400 | ревью / CLAUDE.md |
>
> Task 2 обязан быть **LOC-нейтральным** (45 строк на входе, 45 на выходе). Task 1+3 имеют
> ровно 28 строк бюджета на `lifecycle.py`. Ослаблять сами LOC-тесты запрещено.
>
> Окружение: `export PATH=/home/dld/.local/bin:$PATH` (там `pytest` и `ruff`).
> Работать ТОЛЬКО в `/home/dld/projects/dld/.worktrees/TECH-222`.

---

### Task 1: Схема — `depends_on` в create-ветке

**Type:** code
**Files:**
- Modify: `scripts/vps/lifecycle_git.py:94-154` (`_build_yaml_content`)
- Modify: `scripts/vps/lifecycle.py:141-202` (`create_initial`)
- Test: `scripts/vps/tests/test_lifecycle.py`

**Context:** У lifecycle нет валидатора схемы — `_build_yaml_content` это обычный dict +
`yaml.safe_dump`. Поле нужно добавить явно в обе ветки: create пишет `[]` по умолчанию
(EC-6), update сохраняет уже записанное (иначе первый же `write_lifecycle` его сотрёт).
Заодно `reason`/`pueue_id`/`allowed_files_hash` получают дефолты `None` — без этого вызов
из Task 3 не помещается в бюджет `lifecycle.py`. Все текущие вызовы передают их явно,
поведение не меняется.

**Steps:**

1. Failing test. Дописать в конец `scripts/vps/tests/test_lifecycle.py`:

```python
def test_create_initial_writes_depends_on(tmp_git_repo):
    """EC-5: depends_on лежит в HEAD, статус остаётся queued."""
    lifecycle.create_initial(tmp_git_repo, "TECH-570", "p1", "tech", depends_on=["TECH-220"])
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-570")
    assert data["depends_on"] == ["TECH-220"]
    assert data["status"] == "queued"


def test_create_initial_defaults_depends_on_to_empty(tmp_git_repo):
    """EC-6: bootstrap/migrate зовут без kwarg — получают [] и ничего больше не меняется."""
    lifecycle.create_initial(tmp_git_repo, "TECH-571", "p1", "tech")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-571")
    assert data["depends_on"] == []
    assert data["priority"] == "p1"
    assert data["kind"] == "tech"
    assert data["version"] == 1
    assert data["transitions"] == []


def test_write_lifecycle_preserves_depends_on(tmp_git_repo):
    """Смена статуса не должна ронять поле — иначе гейт умрёт на первом же диспатче."""
    lifecycle.create_initial(tmp_git_repo, "TECH-572", "p1", "tech", depends_on=["TECH-220"])
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-572", "in_progress", by="orchestrator")
    assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-572")["depends_on"] == ["TECH-220"]
```

2. Показать красное:
```bash
export PATH=/home/dld/.local/bin:$PATH
pytest scripts/vps/tests/test_lifecycle.py -k depends_on -x -q
# → TypeError: create_initial() got an unexpected keyword argument 'depends_on'
```

3. `scripts/vps/lifecycle_git.py` — сигнатура `_build_yaml_content` (строки 94-105) становится:

```python
def _build_yaml_content(
    spec_id: str,
    status: str,
    *,
    existing: Optional[dict],
    reason: Optional[str] = None,
    by: str,
    pueue_id: Optional[int] = None,
    allowed_files_hash: Optional[str] = None,
    priority: Optional[str] = None,
    kind: Optional[str] = None,
    depends_on: Optional[list] = None,
) -> str:
```

   В create-ветке (`if existing is None:`) после строки `"kind": kind or "tech",` добавить:
```python
            "depends_on": [str(d) for d in depends_on or []],
```

   В update-ветке сразу после `data = dict(existing)` добавить:
```python
    if depends_on is not None:
        data["depends_on"] = [str(d) for d in depends_on]
```

4. `scripts/vps/lifecycle.py` — в `create_initial` добавить параметр после `by: str = "orchestrator",`:
```python
    depends_on: Optional[list] = None,
```
   в докстринг — одну строку:
```
    `depends_on` is the list of spec_ids this spec waits for (TECH-222); absent ≡ [].
```
   и в `make_yaml()` дописать последним аргументом `_build_yaml_content(...)`:
```python
            depends_on=depends_on,
```

5. Зелёное + бюджет:
```bash
pytest scripts/vps/tests/test_lifecycle.py -q
ruff check scripts/vps && ruff format --check scripts/vps
wc -l scripts/vps/lifecycle.py            # ≤ 375 (было 372, +3)
wc -l scripts/vps/lifecycle_git.py        # ≈ 158
```

**Acceptance:** EC-5, EC-6. Три новых теста зелёные; `pytest scripts/vps/tests/test_lifecycle_create_initial.py scripts/vps/tests/test_lifecycle_done_terminal.py -q` (не в Allowed Files — только прогнать) остаются зелёными; `lifecycle.py` ≤ 375 LOC.

---

### Task 2: Чтение — `_spec_deps`, строго LOC-нейтрально

**Type:** code
**Files:**
- Modify: `scripts/vps/orchestrator_queue.py:39-83` (блок целиком)
- Test: `scripts/vps/tests/test_orchestrator.py` (новый класс `TestSpecDeps`)

**Context:** `_unmet_dependencies` меняет ровно одну строку — источник рёбер. Имена
`_backlog_deps`, `_unmet_dependencies`, `_AFTER_DEP_RE` и re-export `orchestrator.py:389-394`
не трогать: 13 тестов патчат `orchestrator._unmet_dependencies` по голому имени. Файл ровно
на потолке (400/400), поэтому старый комментарий BUG-206 и два докстринга ужимаются на столько
же строк, сколько добавляет `_spec_deps`. Комментарий переписывать надо в любом случае — он
утверждает «Dependency EDGE comes from the backlog», что после этой задачи ложь.

**Steps:**

1. Failing test — дописать в `scripts/vps/tests/test_orchestrator.py` **после строки 332**
   (`import pytest`; практически — сразу перед `class TestDependencyGate`, строка 753):

```python
@pytest.fixture()
def dep_repo(tmp_path):
    """Реальный git-репо: read_lifecycle читает HEAD, фикстура-словарь тут не годится."""

    def git(*args):
        subprocess.run(["git", *args], cwd=str(tmp_path), check=True, capture_output=True)

    git("init", "-b", "develop")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "ai" / "lifecycle").mkdir(parents=True)
    (tmp_path / "ai" / "lifecycle" / ".gitkeep").write_text("", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "init")
    return tmp_path


def _commit_raw_yaml(repo, spec_id, body):
    """Записать lifecycle-yaml произвольной формы (плумбинг такое не напишет)."""
    (repo / "ai" / "lifecycle" / f"{spec_id}.yaml").write_text(body, encoding="utf-8")
    subprocess.run(
        ["git", "add", f"ai/lifecycle/{spec_id}.yaml"], cwd=str(repo), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", f"raw({spec_id})"], cwd=str(repo), check=True, capture_output=True
    )


class TestSpecDeps:
    """TECH-222: рёбра из lifecycle YAML ∪ backlog-строка (deprecated)."""

    def _backlog(self, repo, rows):
        backlog = repo / "ai" / "backlog.md"
        backlog.parent.mkdir(parents=True, exist_ok=True)
        header = "| ID | status | kind | date | desc |\n| --- | --- | --- | --- | --- |\n"
        backlog.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")

    def test_reads_depends_on_from_yaml(self, dep_repo):
        """Главный новый путь: строки в бэклоге нет вовсе."""
        import lifecycle

        lifecycle.create_initial(dep_repo, "ARCH-1246", "p1", "arch", depends_on=["TECH-1244"])
        assert orchestrator_queue._spec_deps(str(dep_repo), "ARCH-1246") == {"TECH-1244"}

    def test_missing_key_is_empty(self, dep_repo):
        """EC-4: запись, созданная до миграции, ведёт себя как сегодня."""
        _commit_raw_yaml(dep_repo, "TECH-800", "spec_id: TECH-800\nstatus: queued\n")
        assert orchestrator_queue._spec_deps(str(dep_repo), "TECH-800") == set()

    def test_broken_shape_warns_and_is_ignored(self, dep_repo, caplog):
        """EC-3: depends_on строкой, а не списком → WARNING DEP_SHAPE, трактуем как []."""
        import logging

        _commit_raw_yaml(
            dep_repo, "TECH-801", 'spec_id: TECH-801\nstatus: queued\ndepends_on: "TECH-210"\n'
        )
        with caplog.at_level(logging.WARNING, logger="orchestrator"):
            assert orchestrator_queue._spec_deps(str(dep_repo), "TECH-801") == set()
        assert any("DEP_SHAPE" in r.message for r in caplog.records)

    def test_legacy_backlog_still_read_and_logged(self, dep_repo, caplog):
        """EC-12: ARCH-209 до миграции — ребро только в бэклоге, в лог идёт deps_via=backlog."""
        import logging

        lifecycle_mod = __import__("lifecycle")
        lifecycle_mod.create_initial(dep_repo, "ARCH-209", "p1", "arch")
        self._backlog(dep_repo, ["| ARCH-209 | queued | arch | 2026-07-27 | x AFTER TECH-213 |"])
        with caplog.at_level(logging.INFO, logger="orchestrator"):
            assert orchestrator_queue._spec_deps(str(dep_repo), "ARCH-209") == {"TECH-213"}
        assert any("deps_via=backlog" in r.message for r in caplog.records)

    def test_union_does_not_double_log(self, dep_repo, caplog):
        """YAML ∪ backlog: пересечение не считается legacy-находкой."""
        import logging

        lifecycle_mod = __import__("lifecycle")
        lifecycle_mod.create_initial(dep_repo, "ARCH-210", "p1", "arch", depends_on=["TECH-213"])
        self._backlog(dep_repo, ["| ARCH-210 | queued | arch | 2026-07-27 | x AFTER TECH-213 |"])
        with caplog.at_level(logging.INFO, logger="orchestrator"):
            assert orchestrator_queue._spec_deps(str(dep_repo), "ARCH-210") == {"TECH-213"}
        assert not [r for r in caplog.records if "deps_via=backlog" in r.message]

    def test_dangling_reference_is_met(self, dep_repo):
        """EC-2: fail-open сохранён — ссылки нет в lifecycle, исключения тоже нет."""
        import lifecycle

        lifecycle.create_initial(dep_repo, "ARCH-211", "p1", "arch", depends_on=["TECH-9999"])
        assert orchestrator_queue._unmet_dependencies(str(dep_repo), "ARCH-211") == []
```

2. Показать красное:
```bash
pytest scripts/vps/tests/test_orchestrator.py -k SpecDeps -x -q
# → AttributeError: module 'orchestrator_queue' has no attribute '_spec_deps'
```

3. Заменить в `scripts/vps/orchestrator_queue.py` строки **39-83 целиком** (45 строк) на
   ровно эти 45 строк:

```python
# BUG-206 / TECH-222: dependency-aware dispatch. The edge lives on the dependent spec
# (`depends_on: [ID]` in its lifecycle yaml, written by Spark); the `AFTER <ID>` backlog
# marker is a deprecated fallback (deps_via=backlog). STATUS always from the lifecycle SoT.
_AFTER_DEP_RE = re.compile(r"\bafter\s+([A-Z]{2,5}-\d+)", re.IGNORECASE)


def _backlog_deps(project_dir: str, spec_id: str) -> set:
    """Deprecated 'AFTER <ID>' deps from spec_id's backlog row; empty when absent."""
    backlog = Path(project_dir) / "ai" / "backlog.md"
    if not backlog.is_file():
        return set()
    row_re = re.compile(rf"^\s*\|\s*{re.escape(spec_id)}\s*\|")
    try:
        for line in backlog.read_text(errors="replace").splitlines():
            if row_re.match(line):
                deps = {m.group(1).upper() for m in _AFTER_DEP_RE.finditer(line)}
                deps.discard(spec_id)
                return deps
    except OSError:
        pass
    return set()


def _spec_deps(project_dir: str, spec_id: str) -> set:
    """Declared deps: lifecycle `depends_on` (SoT) ∪ backlog `AFTER` row (legacy)."""
    raw = (lifecycle.read_lifecycle(project_dir, spec_id) or {}).get("depends_on") or []
    if not isinstance(raw, list):
        log.warning("DEP_SHAPE: %s depends_on is not a list — ignored", spec_id)
        raw = []
    yaml_deps = {d.upper() for d in raw if isinstance(d, str)}
    legacy = _backlog_deps(project_dir, spec_id) - yaml_deps
    if legacy:
        log.info("DEP_VIA: %s deps_via=backlog (legacy) %s", spec_id, sorted(legacy))
    return yaml_deps | legacy


def _unmet_dependencies(project_dir: str, spec_id: str) -> list:
    """Declared deps of spec_id not yet 'done'. Absent from lifecycle ≡ met (fail-open:
    a stale/archived reference must not stall dispatch forever). Unchanged by TECH-222."""
    unmet = []
    for dep in sorted(_spec_deps(project_dir, spec_id)):
        dep_lc = lifecycle.read_lifecycle(project_dir, dep)
        if dep_lc and dep_lc.get("status") != "done":
            unmet.append(dep)
    return unmet
```

4. Зелёное + потолок (это, а не «выглядит нормально», — критерий):
```bash
ruff format scripts/vps/orchestrator_queue.py && ruff check scripts/vps
wc -l scripts/vps/orchestrator_queue.py   # ДОЛЖНО быть ровно 400
pytest scripts/vps/tests/test_orchestrator.py -q
pytest scripts/vps/tests/ -q -x --deselect scripts/vps/tests/test_lifecycle_push_rebase.py::test_dirty_wt_blocks_rebase
```
   Если `ruff format` разложил какую-то строку и вышло >400 — ужимать комментарий
   BUG-206/TECH-222 до 2 строк, **не** трогая `test_file_under_loc_limit`.

5. Живая проверка (EC-12, ещё ДО миграции — ребро только в бэклоге):
```bash
cd /home/dld/projects/dld/.worktrees/TECH-222
python3 -c "
import sys, logging; sys.path.insert(0,'scripts/vps'); logging.basicConfig(level=logging.INFO)
import orchestrator
print(orchestrator._unmet_dependencies('.', 'ARCH-209'))"
# → INFO ... DEP_VIA: ARCH-209 deps_via=backlog (legacy) ['TECH-210', ... 'TECH-216']
# → ['TECH-213']
```

**Acceptance:** EC-2, EC-3, EC-4, EC-12. `orchestrator_queue.py` ровно 400 LOC.
`grep -n "_backlog_deps\|_unmet_dependencies\|_AFTER_DEP_RE" scripts/vps/orchestrator.py` →
строки 390-392 не изменились. Живой прогон печатает `['TECH-213']` и логирует `DEP_VIA`.

---

### Task 3: `set_depends_on` — запись в существующую запись через callable-CAS

**Type:** code
**Files:**
- Modify: `scripts/vps/lifecycle.py` (новая публичная функция после `create_initial`)
- Test: `scripts/vps/tests/test_lifecycle.py`

**Context:** `write_file_atomic` не годится: её retry шлёт статически вычисленный `content`,
поэтому параллельная смена статуса в окне чтение→коммит молча откатится (devil DA-6).
`_cas_loop(repo_dir, spec_id, branch, yaml_fn)` пересобирает запись из свежего HEAD на каждой
попытке. Бюджет `lifecycle.py` — 23 строки (375 → 398).

**Steps:**

1. Failing test — дописать в конец `scripts/vps/tests/test_lifecycle.py` (хелпер `_git`
   уже определён в этом файле, строка 621):

```python
def test_set_depends_on_preserves_concurrent_status_write(tmp_git_repo):
    """EC-7 (devil DA-6): статус, записанный между чтением и коммитом, обязан выжить.

    Инжектим сырым git-коммитом, а НЕ через write_lifecycle: _write_lock —
    обычный threading.Lock, вызов публичного writer'а изнутри CAS-петли = дедлок.
    """
    lifecycle.create_initial(tmp_git_repo, "TECH-580", "p1", "tech")
    yaml_path = tmp_git_repo / "ai" / "lifecycle" / "TECH-580.yaml"
    state = {"injected": False}
    real_run = lifecycle_git._run

    def injecting_run(cmd, **kwargs):
        if not state["injected"] and cmd[:2] == ["git", "write-tree"]:
            state["injected"] = True
            yaml_path.write_text(
                yaml_path.read_text(encoding="utf-8").replace(
                    "status: queued", "status: in_progress"
                ),
                encoding="utf-8",
            )
            _git(tmp_git_repo, "add", "ai/lifecycle/TECH-580.yaml")
            _git(tmp_git_repo, "commit", "-m", "lifecycle(TECH-580): in_progress")
        return real_run(cmd, **kwargs)

    with patch.object(lifecycle_git, "_run", injecting_run):
        lifecycle.set_depends_on(tmp_git_repo, "TECH-580", ["TECH-220"], by="operator")

    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-580")
    assert data["status"] == "in_progress", "параллельная смена статуса откатилась"
    assert data["depends_on"] == ["TECH-220"]


def test_set_depends_on_rejects_unknown_writer(tmp_git_repo):
    """ADR-024: by обязателен и проверяется по _ALLOWED_WRITERS."""
    lifecycle.create_initial(tmp_git_repo, "TECH-581", "p1", "tech")
    with pytest.raises(ValueError, match="invalid by='autopilot'"):
        lifecycle.set_depends_on(tmp_git_repo, "TECH-581", ["TECH-220"], by="autopilot")
```

2. Показать красное:
```bash
pytest scripts/vps/tests/test_lifecycle.py -k set_depends_on -x -q
# → AttributeError: module 'lifecycle' has no attribute 'set_depends_on'
```

3. `scripts/vps/lifecycle.py` — вставить сразу после `create_initial` (перед `list_by_status`):

```python
def set_depends_on(repo_dir, spec_id: str, deps: list, *, by: str) -> None:
    """Rewrite `depends_on` on an existing entry without losing a concurrent status write.

    Callable-CAS, not write_file_atomic: the latter re-sends a statically computed
    body on every retry, so a status written between read and commit is reverted.
    `by` is required (ADR-024) and gated by _ALLOWED_WRITERS.
    """
    if by not in _ALLOWED_WRITERS:
        raise ValueError(f"set_depends_on: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}")
    repo_dir = str(repo_dir)
    branch = lifecycle_git._current_branch(repo_dir)

    def make_yaml():
        existing = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
        if existing is None:
            raise KeyError(f"set_depends_on: no lifecycle entry for {spec_id}")
        return lifecycle_git._build_yaml_content(
            spec_id, existing.get("status", "queued"), existing=existing, by=by, depends_on=deps
        )

    lifecycle_cas._cas_loop(repo_dir, spec_id, branch, make_yaml)
```

   В шапке модуля добавить `set_depends_on` в перечисление публичного API (строки 4-7),
   **не увеличивая число строк** — вписать в существующую строку.

4. Зелёное + бюджет:
```bash
ruff format scripts/vps/lifecycle.py && ruff check scripts/vps
wc -l scripts/vps/lifecycle.py     # ДОЛЖНО быть ≤400 (ожидаемо 398)
pytest scripts/vps/tests/test_lifecycle.py -q
```
   Если >400 — сократить докстринг `set_depends_on` до одной строки, ничего больше.

**Acceptance:** EC-7. Оба новых теста зелёные; `lifecycle.py` ≤400 LOC;
`test_lifecycle.py::TestSplitContract::test_every_module_under_the_loc_limit` зелёный.

---

### Task 4: `TestDependencyGate` переписан на YAML — и цикл, и голые патчи

**Type:** test
**Files:**
- Modify: `scripts/vps/tests/test_orchestrator.py:753-886` (`class TestDependencyGate`)

**Context:** Три теста `test_unmet_*` патчат `orchestrator.lifecycle.read_lifecycle` целиком
и **останутся зелёными на мёртвом пути** после Task 2: `{"status": "queued"}.get("depends_on")`
→ `None` → фолбэк в бэклог. Это ровно то, что devil SA-3 запрещает. Их надо перевести на
`dep_repo` + `create_initial(depends_on=...)`. Три теста `test_backlog_deps_*` остаются
как есть — это юнит-тесты legacy-парсера (EC-12). Два `test_scan_queued_*` остаются
байт-в-байт: они патчат `orchestrator._unmet_dependencies` по голому имени и **являются**
проверкой EC-11.

**Steps:**

1. В `class TestDependencyGate` заменить три теста (строки 801-825) на:

```python
    # --- _unmet_dependencies поверх YAML (TECH-222) ---

    def test_unmet_when_yaml_dep_not_done(self, dep_repo):
        import lifecycle

        lifecycle.create_initial(dep_repo, "TECH-1244", "p1", "tech")
        lifecycle.create_initial(dep_repo, "ARCH-1246", "p1", "arch", depends_on=["TECH-1244"])
        assert orchestrator._unmet_dependencies(str(dep_repo), "ARCH-1246") == ["TECH-1244"]

    def test_met_when_yaml_dep_done(self, dep_repo):
        import lifecycle

        lifecycle.create_initial(dep_repo, "TECH-1244", "p1", "tech")
        lifecycle.write_lifecycle(dep_repo, "TECH-1244", "done", by="callback")
        lifecycle.create_initial(dep_repo, "ARCH-1246", "p1", "arch", depends_on=["TECH-1244"])
        assert orchestrator._unmet_dependencies(str(dep_repo), "ARCH-1246") == []

    def test_met_when_dep_absent_from_lifecycle(self, dep_repo):
        """Висячая/архивная ссылка → считается выполненной (анти-stall, EC-2)."""
        import lifecycle

        lifecycle.create_initial(dep_repo, "ARCH-1246", "p1", "arch", depends_on=["TECH-999"])
        assert orchestrator._unmet_dependencies(str(dep_repo), "ARCH-1246") == []

    def test_dependency_cycle_skips_both_without_raising(self, dep_repo):
        """EC-10: A↔B, обе queued → кандидата нет, исключения нет, диспатч не виснет."""
        import lifecycle

        lifecycle.create_initial(dep_repo, "TECH-810", "p1", "tech", depends_on=["TECH-811"])
        lifecycle.create_initial(dep_repo, "TECH-811", "p1", "tech", depends_on=["TECH-810"])
        assert orchestrator._unmet_dependencies(str(dep_repo), "TECH-810") == ["TECH-811"]
        assert orchestrator._unmet_dependencies(str(dep_repo), "TECH-811") == ["TECH-810"]
        queued = [{"spec_id": "TECH-810"}, {"spec_id": "TECH-811"}]
        assert orchestrator._select_dispatchable_spec(str(dep_repo), queued) is None
```

2. Докстринг класса (строки 754-761) — дописать одну строку:
   `TECH-222: ребро теперь в lifecycle YAML; backlog-строка проверяется отдельно выше.`

3. Прогон:
```bash
pytest scripts/vps/tests/test_orchestrator.py -k "DependencyGate or SpecDeps" -v
# 3 backlog_deps + 4 unmet/cycle + 2 scan_queued + 6 SpecDeps = 15 зелёных
```

4. Доказать, что EC-11 жив (патч по голому имени всё ещё перехватывает):
```bash
pytest scripts/vps/tests/test_orchestrator.py::TestDependencyGate::test_scan_queued_skips_dep_unmet_dispatches_next -v
```

**Acceptance:** EC-10, EC-11, EC-13. Ни один тест в `TestDependencyGate`, проверяющий
`_unmet_dependencies`, не остаётся на патче `read_lifecycle` целиком. Полный
`pytest scripts/vps/tests/ -q` зелёный (кроме известного pre-existing FAIL в
`test_lifecycle_push_rebase.py`).

---

### Task 5: Producer — промпты Spark в корневом дереве

**Type:** code
**Files:**
- Modify: `.claude/skills/spark/completion.md` (строки 28-31, 124-157)
- Modify: `.claude/skills/spark/feature-mode.md` (строки 396-406)

**Context:** Конвенция `**AFTER <ID>**` в шапке спеки уже существует де-факто (TECH-221),
но её никто не машинно-читает — инцидент 30.08 ровно об этом. Spark парсит шапку сам, в
момент создания, и кладёт результат в `create_initial`. Демон прозу по-прежнему не парсит.
Плюс `completion.md:132` и `:153` называют живым продюсером бэклога мёртвую
`callback._render_and_commit_backlog` — это надо исправить в том же коммите, иначе Task 7
удалит функцию, а промпт продолжит на неё ссылаться.

**Steps:**

1. `completion.md`, блок claim (строки 25-32) — добавить `depends_on` и правило перед ним:

```markdown
2. **Собрать зависимости из шапки спеки.** Каждый `**AFTER <ID>**` в заголовочном блоке —
   это ребро. Проверить, что запись существует, ПЕРЕД claim'ом (опечатка ловится здесь,
   демон её не увидит — он fail-open):
   ```bash
   for D in $DEPS; do git cat-file -e "HEAD:ai/lifecycle/$D.yaml" 2>/dev/null \
     || echo "UNKNOWN DEPENDENCY: $D — исправить шапку спеки, не класть в depends_on"; done
   ```
3. **Claim the ID via CAS — where the module exists:**
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, 'scripts/vps')
   import lifecycle
   lifecycle.create_initial('\$REPO_DIR', '\$CANDIDATE',
                            priority='\$PRIORITY', kind='\$KIND',
                            status='queued', by='spark',
                            depends_on=['TECH-220'])   # [] если AFTER в шапке нет
   "
   ```
```
   (нумерацию последующих шагов сдвинуть; экранирование `\$` в спеке — в самом промпте
   остаются обычные `$REPO_DIR`.)

2. `completion.md:129-132` — таблица «что производит бэклог». Заменить строку

```markdown
| What produces the backlog | `callback._render_and_commit_backlog` → `render_backlog.render_backlog()`, from those same YAMLs, after every lifecycle write |
```
   на

```markdown
| What produces the backlog | `lifecycle_cas._atomic_write` → `render_backlog.sync_status`, folded into the same commit as the YAML. It rewrites **only the Status cell of rows that already exist** — it does not add rows, and it does not touch prose. The full renderer has had no caller since 2026-05 and was deleted in TECH-222 |
```

3. `completion.md:153-157` — абзац про «known race». Заменить на:

```markdown
There is no renderer race under that exception: the only live writer is
`render_backlog.sync_status`, which rewrites the Status cell of existing rows and adds
none. A hand-written row survives until the record exists. (This paragraph used to
describe a full re-render after every lifecycle write; that path had no caller.)
```

4. `completion.md` — в «Status on Spark exit» дописать одну строку после таблицы:

```markdown
**Зависимости живут в `depends_on`, не в прозе.** Если спека объявляет `**AFTER <ID>**` в
шапке, тот же список обязан уехать в `create_initial(depends_on=[...])` — иначе планировщик
её не увидит и задиспатчит спеку параллельно с её же предусловием (инцидент TECH-221, 30.08).
```

5. `feature-mode.md:396-406` — в примере claim'а:

```bash
       create_initial('<REPO_DIR>', '<CANDIDATE_ID>', priority='<P0|P1|P2>', kind='<TECH|FTR|BUG|ARCH>', by='spark', status='queued', depends_on=[<'AFTER' ids from the spec header, or empty>])
```
   и сразу под блоком — одну строку:
```markdown
   `depends_on` — плоский список spec_id из `**AFTER <ID>**` в шапке спеки. Проверить каждый
   через `git cat-file -e HEAD:ai/lifecycle/<ID>.yaml` до claim'а; несуществующий ID не класть.
```

6. Проверка:
```bash
node .claude/scripts/check-prompt-integrity.mjs --tree .claude
grep -n "_render_and_commit_backlog" .claude/skills/spark/completion.md   # → пусто
grep -n "depends_on" .claude/skills/spark/completion.md .claude/skills/spark/feature-mode.md
```

**Acceptance:** EC-8 (корневое дерево). `check-prompt-integrity.mjs` exit 0; в
`completion.md` ноль упоминаний `_render_and_commit_backlog`; обе правки про `depends_on`
на месте.

---

### Task 6: Зеркало в `template/` — по смыслу, не `cp`

**Type:** sync
**Files:**
- Modify: `template/.claude/skills/spark/completion.md` (строки 44-53, 111-136)
- Modify: `template/.claude/skills/spark/feature-mode.md` (строки 396-406)

**Context:** **`cp` здесь запрещён.** Файлы намеренно расходятся: root — 393 строки с
именами `callback.py` / ADR-номерами, template — 346 строк, где те же правила изложены без
DLD-внутренностей (`rules/template-sync.md`, «Template prompts carry no DLD spec ids»).
`cp` протащил бы в шаблон `scripts/vps/*` и номера спек. `feature-mode.md:401` в двух
деревьях байт-в-байт — там правка идентичная. Ложное утверждение про рендер в шаблоне тоже
есть, просто своими словами (строки 113-116 и 134-136).

**Steps:**

1. `template/.../completion.md:113-116` — заменить

```markdown
Where an orchestrator dispatches specs, it reads the lifecycle records, and `ai/backlog.md`
is rendered from those same records after every lifecycle write. A spec **that has a
lifecycle record** and no backlog row is dispatched normally, and its row appears on the
next render.
```
   на

```markdown
Where an orchestrator dispatches specs, it reads the lifecycle records. `ai/backlog.md` is a
view over them: a status sync folds the new status into the same commit as the record, and it
rewrites **only the Status cell of rows that already exist** — it adds no rows and touches no
prose. A spec **that has a lifecycle record** and no backlog row is dispatched normally.
```

2. `template/.../completion.md:134-136` — заменить абзац про race на:

```markdown
Under the exception there is no renderer race: the status sync rewrites existing rows and
adds none, so a hand-written row survives until the record exists.
```

3. `template/.../completion.md`, блок claim (строки 25-32 в шаблонной нумерации) — та же
   правка, что в Task 5 шаг 1, **без** ссылок на `scripts/vps` и без номеров спек:
   зависимости из `**AFTER <ID>**` в шапке → `depends_on=[...]`, каждый ID проверить через
   `git cat-file -e HEAD:ai/lifecycle/<ID>.yaml` до claim'а.

4. `template/.../feature-mode.md:401` — та же строка, что в Task 5 шаг 5 (файлы в этом месте
   идентичны), плюс тот же однострочный комментарий под блоком.

5. Проверка:
```bash
python scripts/check-tree-sync.py                 # 0 = clean или UNAVAILABLE
node .claude/scripts/check-prompt-integrity.mjs --tree template/.claude
grep -c "depends_on" .claude/skills/spark/completion.md template/.claude/skills/spark/completion.md
grep -rn "scripts/vps\|TECH-2\|ADR-0" template/.claude/skills/spark/completion.md   # → 0 новых
diff <(grep -c depends_on .claude/skills/spark/feature-mode.md) \
     <(grep -c depends_on template/.claude/skills/spark/feature-mode.md)   # пусто
```

**Acceptance:** EC-8 (оба дерева). `check-tree-sync.py` не красный; обе копии несут
конвенцию `depends_on`; в `template/` не появилось ни одного нового `scripts/vps`,
`TECH-NNN`, `ADR-NNN`.

---

### Task 7: Удалить мёртвую `_render_and_commit_backlog`

**Type:** code
**Files:**
- Modify: `scripts/vps/callback.py` (строки 14, 46, 186-213)

**Context:** Ноль call-site'ов — проверено грепом по всем `*.py`. Последний вызов снят в
ARCH-196, функция оставлена «для оператора» и с тех пор не звалась ни разу. **Побочный
эффект, которого нет в спеке:** после удаления `import lifecycle` (строка 46) становится
единственным неиспользуемым импортом в файле → `ruff` F401. Патчей `callback.lifecycle`
в репозитории нет (проверено), поэтому импорт удаляется вместе с функцией.

**Steps:**

1. Проверить предпосылку перед удалением:
```bash
grep -rn "_render_and_commit_backlog" --include="*.py" .          # → 1 (только def)
grep -rn "callback\.lifecycle\|from callback import lifecycle" .  # → 0
grep -n "lifecycle" scripts/vps/callback.py                       # → только 14, 46, 188-212
```

2. Удалить строки 186-213 (пустая строка + `def _render_and_commit_backlog` … до строки
   перед `verify_status_sync = callback_sync.verify_status_sync`), оставив ровно две пустых
   строки перед `verify_status_sync`.

3. Удалить строку 46 `import lifecycle  # noqa: E402  — atomic YAML writer (ADR-023)`.

4. В шапке модуля удалить строку 14
   `  - lifecycle: read_lifecycle, write_lifecycle  (ADR-023 — sole status writer)`
   и заменить строку 25 на:
```
ARCH-186: verify_status_sync (callback_sync) writes only to lifecycle.yaml — callback.py
itself no longer imports lifecycle; the dead backlog renderer was removed in TECH-222.
```

5. Прогон:
```bash
ruff check scripts/vps && ruff format --check scripts/vps
python3 -c "import sys; sys.path.insert(0,'scripts/vps'); import callback; print('ok')"
pytest scripts/vps/tests/ -q --deselect scripts/vps/tests/test_lifecycle_push_rebase.py::test_dirty_wt_blocks_rebase
pytest tests/ -q
wc -l scripts/vps/callback.py     # ≈ 371
```

**Acceptance:** EC-9. `grep -rn "_render_and_commit_backlog" scripts/ .claude/skills/
template/.claude/skills/` → 0. `callback.py` импортируется, обе pytest-сюиты зелёные,
`ruff check` без F401.

---

### Task 8: Доки оркестратора

**Type:** code
**Files:**
- Modify: `docs/orchestrator/README.md:104,181`
- Modify: `docs/orchestrator/components.md:32-33,215`

**Context:** Оба файла описывают DEP_GATE как чтение backlog-строки. После Task 2 это
фолбэк, а не механизм. Строки проверены: README **181** (не 180), components **215**
(не 202).

**Steps:**

1. `README.md:104` — заменить
```
    dependency gate: все `AFTER <ID>` зависимости должны быть done
```
   на
```
    dependency gate: все `depends_on: [ID]` из lifecycle YAML должны быть done
                     (legacy-фолбэк: `AFTER <ID>` в backlog-строке, метрика DEP_VIA)
```

2. `README.md:181` — заменить
```
4. **Dependency gate** — не диспатчить spec с незакрытой `AFTER <ID>` (BUG-206).
```
   на
```
4. **Dependency gate** — не диспатчить spec с незакрытой зависимостью из `depends_on`
   (BUG-206 + TECH-222; backlog-`AFTER` — deprecated-фолбэк, снимается после 30 дней без DEP_VIA).
```

3. `components.md:32-33` — заменить
```
- **Dependency gate (BUG-206, `:782-795`):** spec с `AFTER <ID>` в backlog-строке диспатчится только
  когда все зависимости `done` (status из lifecycle SoT). Отсутствующая зависимость = MET (анти-stall).
```
   на
```
- **Dependency gate (BUG-206 + TECH-222, `orchestrator_queue._spec_deps`):** ребро живёт в
  `depends_on: [ID]` в lifecycle YAML зависимой спеки (пишет Spark в `create_initial`, ретрофит —
  `lifecycle.set_depends_on`). Диспатч только когда все зависимости `done` (status из lifecycle SoT).
  Отсутствующая зависимость = MET (fail-open, анти-stall). Backlog-`AFTER` читается как
  deprecated-фолбэк и логируется как `DEP_VIA: … deps_via=backlog` — удалить, когда метрика
  молчит 30 дней.
```

4. `components.md:215` — заменить
```
5. **Dependency gate** — не диспатчить spec с незакрытой `AFTER <ID>` (BUG-206).
```
   на
```
5. **Dependency gate** — не диспатчить spec с незакрытым `depends_on` (BUG-206, TECH-222).
```

5. Проверка:
```bash
grep -rn "AFTER <ID>" docs/orchestrator/    # только строки, помеченные deprecated
grep -rn "depends_on" docs/orchestrator/    # 4 попадания
```

**Acceptance:** DoD «доки описывают механизм, который действительно работает». Ни одна
строка в `docs/orchestrator/` больше не называет backlog-`AFTER` основным источником.

---

### Task 9: Финальный гейт

**Type:** test
**Files:** нет правок — только прогон

**Steps:**
```bash
cd /home/dld/projects/dld/.worktrees/TECH-222
export PATH=/home/dld/.local/bin:$PATH
ruff check . && ruff format --check .
pytest scripts/vps/tests/ -v
pytest tests/ -v
python scripts/check-tree-sync.py
node .claude/scripts/check-prompt-integrity.mjs --tree .claude
grep -rn "_render_and_commit_backlog" scripts/ .claude/skills/ template/.claude/skills/ | wc -l  # 0
wc -l scripts/vps/orchestrator_queue.py scripts/vps/lifecycle.py scripts/vps/callback.py
# EC-12 на живом состоянии (до операторской миграции):
python3 -c "
import sys, logging; sys.path.insert(0,'scripts/vps'); logging.basicConfig(level=logging.INFO)
import orchestrator; print(orchestrator._unmet_dependencies('.', 'ARCH-209'))"
# → ['TECH-213'] + DEP_VIA в логе
```

**Acceptance:** всё зелёное, кроме известного pre-existing
`test_lifecycle_push_rebase.py::test_dirty_wt_blocks_rebase`. Три файла ≤400 LOC.
`_unmet_dependencies('.', 'ARCH-209') == ['TECH-213']` — гейт держит ARCH-209 и после правки.

---

### Execution Order

```
Task 1 (схема: lifecycle_git + create_initial)
  ├─→ Task 3 (set_depends_on — нужен depends_on-kwarg в _build_yaml_content и его дефолты)
  └─→ Task 2 (_spec_deps — тесты зовут create_initial(depends_on=...))
        └─→ Task 4 (TestDependencyGate — нужен и _spec_deps, и dep_repo-фикстура из Task 2)
Task 5 (промпты root) ─→ Task 6 (зеркало template) ─→ (Task 7 удаляет функцию, на которую
                                                       Task 5 больше не ссылается)
Task 7 (уборка callback) — независим от 1-4, но ПОСЛЕ Task 5 (иначе промпт неделю ссылается
                           на удалённую функцию)
Task 8 (доки) — независим, но по смыслу ПОСЛЕ Task 2
Task 9 — последним, всегда
```

Жёсткие рёбра: **1 → 3**, **1 → 2 → 4**, **5 → 6**, **5 → 7**, **всё → 9**.
Task 8 можно делать в любой момент после Task 2.

---

### Операторский шаг (НЕ задача автопилота): миграция ARCH-209

`ai/lifecycle/*.yaml` намеренно нет в Allowed Files — pre-commit hook блокирует staged-правку,
запись идёт только через плумбинг. Выполняется **после мержа**, на VPS и локально:

```bash
python3 -c "
import sys; sys.path.insert(0,'scripts/vps'); import lifecycle
lifecycle.set_depends_on('.', 'ARCH-209',
  ['TECH-210','TECH-211','TECH-212','TECH-213','TECH-214','TECH-215','TECH-216'], by='operator')"
```

затем немедленно EC-1 на живом состоянии. Порядок выката жёсткий (ответ на вопрос devil №4):
**код → данные**, `AFTER`-текст из `ai/backlog.md` не удалять вовсе — фолбэк читает его и держит
гейт, пока метрика не покажет, что он не нужен. Окна, где зависимость объявлена там, куда никто
не смотрит, не возникает ни на секунду.

## Drift Log

Спека сверена с рабочим деревом `.worktrees/TECH-222` (ветка `tech/TECH-222`) 2026-08-30.
**Вердикт: light drift, исправлено на месте, эскалация в `/council` не требуется.**

| # | Что в спеке | Что в коде | Действие |
|---|---|---|---|
| 1 | `orchestrator_queue.py` «371 из 400 LOC» | **ровно 400** — TECH-220/221 съели весь запас; потолок держит `test_orchestrator.py::TestSplitStructuralInvariants::test_file_under_loc_limit` | Task 2 переписан как **LOC-нейтральный** (45 строк на входе, 45 на выходе), с точным блоком-заменой и `wc -l` в acceptance |
| 2 | — | `lifecycle.py` = 372 LOC, потолок 400 (`test_lifecycle.py::TestSplitContract`) → на Task 1+3 остаётся 28 строк | Задан бюджет: Task 1 = +3, Task 3 = +23 (398). Для этого `_build_yaml_content` получает дефолты `reason/pueue_id/allowed_files_hash=None` — все текущие вызовы передают их явно |
| 3 | `TestDependencyGate` — «7 тестов, `:753-870`» | **8 тестов**, `:753-886` | Шапка Impact Tree поправлена; Task 4 перечисляет их поимённо |
| 4 | Impact Tree: «`tests/` — `test_lifecycle.py`» | корневого `tests/test_lifecycle.py` не существует; настоящий путь — `scripts/vps/tests/test_lifecycle.py` (он же в Allowed Files) | Impact Tree поправлен |
| 5 | `README:104,180`, `components:32-33,202` | `README:104,**181**`, `components:32-33,**215**` | Поправлено в Impact Tree и в Task 8 |
| 6 | EC-9: `grep -rn "_render_and_commit_backlog" .` → 0 | невозможно: ~40 исторических упоминаний в `ai/features/*`, `ai/architect/*`, `CHANGELOG.md`, `docs/opus5-skills-review.md`, `.claude/rules/dependencies.md` — ни один файл не в Allowed Files | Грep сужен до `scripts/ .claude/skills/ template/.claude/skills/` в EC-9 и в Acceptance Verification |
| 7 | «удалить мёртвую `_render_and_commit_backlog`» | после удаления `import lifecycle` (`callback.py:46`) остаётся единственным неиспользуемым импортом → **ruff F401**, `ruff check` красный. Патчей `callback.lifecycle` в репо нет (проверено грепом) | Task 7 удаляет импорт и строку 14 шапки вместе с функцией |
| 8 | «`template/` — копии `spark/completion.md` и `feature-mode.md`» | это **не** копии: root 393 строки с именами `callback.py`/ADR, template 346 строк без DLD-внутренностей (`rules/template-sync.md`). `_render_and_commit_backlog` в шаблоне вообще не упоминается — то же ложное утверждение изложено своими словами (`:113-116`, `:134-136`) | Task 6 — **семантическое** зеркало, `cp` явно запрещён; acceptance проверяет, что в `template/` не появилось `scripts/vps`/`TECH-NNN`/`ADR-NNN` |
| 9 | EC-7 «параллельный `write_lifecycle` в полёте» | `_write_lock` — обычный `threading.Lock` (`lifecycle_const.py:45`), нереентрантный: вызов `write_lifecycle` изнутри `_cas_loop` = **дедлок**, тест повис бы навсегда | Тест EC-7 инжектит статус сырым `git commit` (тот же приём, что в живом `test_concurrent_commit_during_write_not_reverted`) — семантика та же, дедлока нет |
| 10 | три теста `test_unmet_*` «переписать на YAML» | они патчат `orchestrator.lifecycle.read_lifecycle` целиком и **остались бы зелёными на мёртвом пути** после Task 2 (`{"status":"queued"}.get("depends_on")` → `None` → фолбэк в бэклог) | Task 4 переводит их на реальный git-репо + `create_initial(depends_on=...)`; два `test_scan_queued_*` оставлены байт-в-байт — они и есть проверка EC-11 |
| 11 | — | живой гейт подтверждён: `ARCH-209.status=queued`, `TECH-213.status=blocked`, `TECH-210/211/212/214/215/216 = done`, строка `AFTER ×7` в `ai/backlog.md:32` | EC-12 вынесен в шаги Task 2 и Task 9 как исполняемая команда против самого worktree |
| 12 | — | `.claude/rules/dependencies.md` называет `orchestrator_queue.py` 338 LOC и `callback.py` 397 (реально 400/400), и упоминает `_render_and_commit_backlog` | **Не трогаем** — файла нет в Allowed Files. Запись оставлена здесь для следующего `/reflect` |
| 13 | — | `scripts/vps/tests/test_lifecycle.py` уже 730 LOC при гайдлайне 600 для тестов (никакой тест это не проверяет); Task 1+3 добавляют ~55 | Принято: разносить тесты некуда — `test_lifecycle_create_initial.py` не в Allowed Files. Кандидат на отдельный TECH |
| 14 | — | после Task 7 `render_backlog.render_backlog()` (полный рендер) остаётся без единого вызова; живёт только `sync_status` | Вне scope (файла нет в Allowed Files), спека это и так объявляет в Out of scope. Записано |

Не потребовалось: внешний research (`## Research Sources` в спеке нет; вопрос — про
внутренний контракт репозитория, не про внешний API).

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Живой гейт переживает миграцию | реальный репо: `ARCH-209.depends_on=[TECH-210..216]`, `TECH-213.status=blocked` | `_unmet_dependencies(repo,"ARCH-209") == ["TECH-213"]`, `scan_queued` логирует `DEP_GATE: skip ARCH-209` | deterministic | devil DA-1 | P0 |
| EC-2 | Висячая ссылка | `depends_on: ["TECH-9999"]`, записи нет | считается выполненной (fail-open сохранён), исключения нет | deterministic | devil DA-2 | P0 |
| EC-3 | Битая форма поля | `depends_on: "TECH-210"` (строка) | `WARNING DEP_SHAPE`, трактуется как `[]`, не падает | deterministic | devil DA-4 | P1 |
| EC-4 | Старый YAML без ключа | любая запись до миграции | `[]`, поведение как сегодня при отсутствии строки в бэклоге | deterministic | devil DA-5 | P1 |
| EC-5 | `create_initial` пишет поле | `create_initial(..., depends_on=["TECH-220"])` | в HEAD `depends_on: [TECH-220]`, `status: queued` | deterministic | Task 1 | P0 |
| EC-6 | Back-compat вызовов | `create_initial` без kwarg (bootstrap, migrate) | `depends_on: []`, прочие поля не изменились | deterministic | devil SA-2 | P0 |
| EC-7 | Гонка миграции со сменой статуса | `set_depends_on` в полёте, параллельный `write_lifecycle` меняет статус той же спеки | итог содержит **и** новый статус, **и** `depends_on`; отката статуса нет | deterministic | devil DA-6 | P0 |
| EC-8 | Spark объявляет зависимость | спека с `**AFTER TECH-220**` в шапке | `create_initial` вызван с `depends_on=["TECH-220"]`; кейс TECH-221 не воспроизводится | deterministic | devil Argument 1 | P0 |
| EC-9 | Мёртвый код удалён | `grep -rn "_render_and_commit_backlog" scripts/ .claude/skills/ template/.claude/skills/` | 0 совпадений; `pytest scripts/vps/tests/ -v` зелёный | deterministic | Task 5 | P1 |
| EC-10 | Цикл не вешает диспатч | `A.depends_on=[B]`, `B.depends_on=[A]`, обе `queued` | обе пропускаются каждый цикл, исключения нет, в логе `DEP_GATE: skip` на обе | deterministic | devil DA-3 | P1 |
| EC-11 | Патчи по голому имени живы | `monkeypatch.setattr(orchestrator, "_unmet_dependencies", fake)` как в текущем `test_scan_queued_skips_dep_unmet_dispatches_next` | патч перехватывает вызов из `_select_dispatchable_spec` | deterministic | devil DA-8 | P0 |
| EC-12 | Legacy-путь ещё работает | спека без `depends_on`, но со строкой `AFTER` в бэклоге (ARCH-209 до Task 6) | зависимости найдены, в логе `DEP_VIA: … deps_via=backlog` | deterministic | devil Alt 4 | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-13 | Переписанный `TestDependencyGate` на YAML-фикстурах | `pytest scripts/vps/tests/test_orchestrator.py -k Dependency -v` | 7 тестов зелёные и реально трогают новый путь (фикстуры пишут YAML, не строки бэклога) | integration | devil SA-3 | P0 |
| EC-14 | Демон на VPS после выката | цикл `scan_queued` для dld | ARCH-209 по-прежнему пропущен; TECH-221 диспатчится ровно после `done` у TECH-220 | integration | инцидент 30.08 | P0 |

### Coverage Summary
Deterministic: 12 | Integration: 2 | LLM-Judge: 0 | Total: 14 (min 3 ✓)

### TDD Order
1. EC-5, EC-6 — схема на пустом месте → **Task 1**
2. EC-2, EC-3, EC-4, EC-12 — чтение, битая форма, фолбэк → **Task 2**
3. EC-7 — гонка записи → **Task 3**
4. EC-10, EC-11, EC-13 — регрессия гейта → **Task 4**
5. EC-8 — producer в обоих деревьях → **Task 5, Task 6**
6. EC-9 — уборка мёртвого кода → **Task 7**; доки → **Task 8**
7. EC-1, EC-14 — живой прогон: EC-1 в форме «до миграции» проверяется в **Task 9**
   (`_unmet_dependencies('.', 'ARCH-209') == ['TECH-213']` через legacy-фолбэк), в форме
   «после миграции» — операторским шагом после мержа. EC-14 — на VPS после выката.

---

## Acceptance Verification

```bash
export PATH=/home/dld/.local/bin:$PATH
ruff check . && ruff format --check .
pytest scripts/vps/tests/ -v
pytest tests/ -v
python scripts/check-tree-sync.py                  # .claude/ vs template/.claude/
node .claude/scripts/check-prompt-integrity.mjs --tree .claude
grep -rn "_render_and_commit_backlog" scripts/ .claude/skills/ template/.claude/skills/ | wc -l   # → 0
wc -l scripts/vps/orchestrator_queue.py scripts/vps/lifecycle.py scripts/vps/callback.py   # все ≤400
```

> `grep` намеренно не по всему репо: ~40 исторических упоминаний живут в `ai/features/*`,
> `ai/architect/*`, `CHANGELOG.md`, `docs/opus5-skills-review.md` и
> `.claude/rules/dependencies.md` — ни один из этих файлов не в Allowed Files, и переписывать
> историю спека не просит.
>
> **Известный pre-existing FAIL, не регрессия:**
> `scripts/vps/tests/test_lifecycle_push_rebase.py::test_dirty_wt_blocks_rebase` падает и на
> чистом `origin/develop`. Всё остальное в `scripts/vps/tests/` должно быть зелёным.

## Definition of Done

- [ ] `depends_on` читается планировщиком из lifecycle YAML; backlog остаётся фолбэком с
      метрикой `deps_via` и названной датой смерти (30 дней без `deps_via=backlog`)
- [ ] Spark кладёт зависимость в `depends_on` при создании спеки — кейс TECH-221 («объявлено
      только в прозе») больше не возникает
- [ ] ARCH-209 после миграции по-прежнему заблокирован TECH-213 — проверено на живом репо
- [ ] `set_depends_on` не теряет параллельную смену статуса (callable-CAS, не статический content)
- [ ] `_unmet_dependencies`, `_backlog_deps` и re-export в `orchestrator.py` не переименованы
- [ ] `TestDependencyGate` переписан на YAML-фикстуры, а не оставлен зеленеть на мёртвом пути
- [ ] `_render_and_commit_backlog` удалена; `completion.md` больше не называет её живым продюсером
- [ ] `docs/orchestrator/{README,components}.md` описывают механизм, который действительно работает
- [ ] Обе копии промптов несут одну конвенцию `depends_on` — **по смыслу, не байт-в-байт**:
      `completion.md` в двух деревьях намеренно расходится (root называет `callback.py` и
      номера ADR, template — нет; `rules/template-sync.md`). `cp` запрещён,
      `check-tree-sync.py` не красный
- [ ] Все команды из Acceptance Verification зелёные

## Autopilot Log

_(заполняется автопилотом)_
