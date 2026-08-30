# Feature: [TECH-222] Зависимости задач — в lifecycle YAML, а не в генерируемой таблице

**Priority:** P1 | **Date:** 2026-08-30 | **AFTER TECH-220, AFTER TECH-221**
**Size:** 6 tasks / 12 files — reader и producer идут одним коммитом: схема без того, кто её
заполняет, — это инфраструктура, которую никто не пишет (devil §Argument 1).

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
grep -rn "AFTER" ai/backlog.md docs/orchestrator/*.md .claude/skills/spark/ → backlog 3 строки, README:104,180, components:32-33,202
```

### Step 4: CHECKLIST
- [x] `scripts/vps/tests/` — `TestDependencyGate` (7 тестов, `test_orchestrator.py:753-870`)
- [x] `tests/` — `test_lifecycle.py` для `create_initial`/`set_depends_on`
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
блокирует staged-правку. Миграция ARCH-209 — Task 6, выполняется оператором после мержа.

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

**Task 1 — схема.** `create_initial(..., depends_on=None)` → нормализация в список строк, дефолт
`[]`; `_build_yaml_content` пишет поле в create- и update-ветках. Существующие вызовы
(`migrate_backlog_to_lifecycle.py`, `orchestrator_backlog.bootstrap_new_specs`) не меняются и
получают `[]` (SA-2). EC-5, EC-6.

**Task 2 — чтение.** `_spec_deps` по дизайну выше; `_unmet_dependencies` зовёт её; имена и
re-export не трогать. Проверить `orchestrator_queue.py` ≤400 LOC после правки (371 сейчас).
EC-1..EC-4, EC-11.

**Task 3 — запись в существующую.** `lifecycle.set_depends_on(repo_dir, spec_id, deps, by)` через
`_cas_loop`; `by` обязателен (ADR-024). EC-7.

**Task 4 — producer.** `.claude/skills/spark/completion.md` + `feature-mode.md` и обе копии в
`template/`: (a) конвенция `**AFTER <ID>**` в шапке спеки, (b) `depends_on=` в примере
`create_initial`, (c) требование проверить, что каждый ID существует в `ai/lifecycle/` — опечатка
ловится здесь, (d) исправить `completion.md:132`, где живым продюсером бэклога назван мёртвый
`_render_and_commit_backlog`. EC-8.

**Task 5 — уборка и доки.** Удалить `callback._render_and_commit_backlog` (26 строк, ноль
вызовов — `callback.py` ровно 400 LOC, это ещё и запас). `docs/orchestrator/README.md:104,180` и
`components.md:32-33,202` — гейт читает `depends_on`, backlog-строка названа deprecated-фолбэком
с датой смерти. EC-9.

**Task 6 — миграция (оператор, ПОСЛЕ мержа).** На VPS и локально:

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
| EC-9 | Мёртвый код удалён | `grep -rn "_render_and_commit_backlog" .` | 0 совпадений; `pytest scripts/vps/tests/ -v` зелёный | deterministic | Task 5 | P1 |
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
1. EC-5, EC-6, EC-4 — схема на пустом месте → Task 1
2. EC-1, EC-2, EC-3, EC-12 — чтение и фолбэк → Task 2
3. EC-7 — гонка записи → Task 3
4. EC-10, EC-11, EC-13 — регрессия гейта
5. EC-8, EC-9, EC-14 — producer, уборка, живой прогон

---

## Acceptance Verification

```bash
ruff check . && ruff format --check .
pytest scripts/vps/tests/ -v
pytest tests/ -v
python scripts/check-tree-sync.py                  # .claude/ vs template/.claude/
node .claude/scripts/check-prompt-integrity.mjs --tree .claude
grep -rn "_render_and_commit_backlog" . | wc -l     # → 0
wc -l scripts/vps/orchestrator_queue.py scripts/vps/lifecycle.py   # оба ≤400
```

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
- [ ] Обе копии промптов (`.claude/` и `template/`) синхронны — `check-tree-sync.py` зелёный
- [ ] Все команды из Acceptance Verification зелёные

## Autopilot Log

_(заполняется автопилотом)_
