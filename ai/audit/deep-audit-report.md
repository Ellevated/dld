# Deep Audit — callback / lifecycle / orchestrator contour

**Date:** 2026-05-23
**Trigger:** Incident — 15 fake-done lifecycle flips + 4 связанных бага одной волны (5-я итерация фиксов в этом контуре за месяц)
**Scope:** `scripts/vps/callback.py` (1374 LOC), `lifecycle.py` (602), `orchestrator.py` (667), `db.py` (531), `event_writer.py`, `render_backlog.py`, `claude-runner.py`, `migrate_backlog_to_lifecycle.py`, `spec_operator.py`, hooks, тесты
**Method:** 6 параллельных персон (Cartographer, Archaeologist, Accountant, Geologist, Scout, Coroner)
**Total findings:** 85 (Cartographer 15 + Archaeologist 14 + Accountant 13 + Geologist 13 + Scout 12 + Coroner 18)

---

## Executive Summary

**Этот контур ломается раз за разом не из-за плохих фиксов — из-за фундаментального несоответствия дизайна.** Каждое «правило» (TECH-166, 176, 177, ARCH-186, ARCH-187, BUG-188, cefaa55 8-rule) — попытка вывести *намерение* («работа сделана?») из *артефактов* (exit code, subject string, file path, markdown text). Каждое такое выведение ошибается на каком-то edge case. Каждый фикс добавляет новое правило вместо упрощения. Сложность нарастает; новые правила открывают новые failure modes. 5-я итерация — следствие, не аномалия.

ARCH-186 spec сам это прогнозировал в своём rationale (`За 2.5 месяца — 10+ фиксов вокруг одного контракта, каждый закрывал одну race и открывал другую`). ARCH-186 пытался решить проблему через миграцию SoT из markdown в git-YAML — но **переместил** проблему, не **устранил** её, потому что:
1. **Markdown продолжает быть entry point** для bootstrap_new_specs
2. **Спека ARCH-187** (которая должна была закрыть identity-enforcement gap, найденный сразу после ARCH-186) — сама была force-done оператором в обход своего же гарда
3. **Защиты, добавленные ARCH-187** (pre-commit hook, identity enforcement), **не задеплоены** в managed-проекты, где живут писатели lifecycle

Сегодняшние 5 багов — не «пять разных проблем», а **5 проявлений одной структурной болезни**: split brain между декларированным SoT и реальными writers.

---

## 5 структурных корней (синтез из 6 персон)

### Root 1 — Split brain: «status» живёт в 3-х несинхронных хранилищах

| Store | Medium | Writer (декларированный) | Reader |
|---|---|---|---|
| `ai/lifecycle/{spec_id}.yaml` HEAD | git object store | callback (ADR-023) | callback.verify_status_sync, orchestrator.scan_queued, render_backlog |
| `ai/backlog.md` WT | working tree | render_backlog (best-effort через WT-sync) | **orchestrator.bootstrap_new_specs (читает WT, не HEAD)** |
| spec body `## Status:` (+ зомби-маркеры DLD-CALLBACK-MARKER в 23 файлах) | working tree markdown | Spark (создаёт), никто не апдейтит | spec_lint.py (валидирует мёртвый формат), migrate_backlog_to_lifecycle.py |

**Конкретный inconsistency contract:**
- ADR-023 декларирует «callback — единственный writer статуса»
- `lifecycle.py:208` отключает auto-render backlog.md как фикс пост-merge ARCH-186 (стрипает founder's rich sections)
- `callback.py:1187` всё равно вызывает `_render_and_commit_backlog` (контракт нарушен в комментарии, не в коде)
- `orchestrator.py:295` читает backlog.md из **dirty WT** (а не HEAD) для bootstrap → читает то, что человек только что отредактировал, а не то что закоммичено

**Сегодняшний bug 1** (15 fake-done flips) — прямое следствие: `bootstrap_new_specs` прочёл backlog.md, где спеки висели как `done` (рендер из старого callback написал так), без gate-check скопировал в lifecycle yaml.

**Evidence:** Cartographer #13, Archaeologist #1/#11, Geologist #2 (Three Representations and Their Drift), Coroner #14 (NOTE/disabled).

---

### Root 2 — Identity gates вокруг ОДНОГО writer, но writer-ов много

ADR-023 говорит «callback — единственный writer». На самом деле:

| # | Writer | Тип | Identity | Соблюдает контракт? |
|---|---|---|---|---|
| 1 | `callback.verify_status_sync → lifecycle.write_lifecycle` | atomic CAS | `by="callback"` | ✓ |
| 2 | `orchestrator.bootstrap_new_specs → lifecycle.create_initial` | atomic CAS | `by="orchestrator"` (hardcoded) | технически да |
| 3 | `orchestrator.startup_reconcile → lifecycle.reconcile_orphans → write_lifecycle` | atomic CAS | `by="callback"` (hardcoded в lifecycle.py:551) — **ложь** | identity misattributed |
| 4 | `spec_operator.py → write_lifecycle` | atomic CAS | `by="operator"` (всегда, кто бы ни вызвал) | identity не аутентифицирована |
| 5 | `migrate_backlog_to_lifecycle.py:224-225` | **`Path.write_text()` напрямую в WT** | без identity, **полностью в обход git plumbing и CAS** | **violates ADR-023 entirely** |
| 6 | Pre-commit hook `pre-commit-lifecycle-guard.mjs` | должен ловить «чужие» writes | — | **не задеплоен ни в одном репо**: `core.hooksPath` указывает на `.git/hooks/`, guard живёт в `.git-hooks/` (Coroner #1, Cartographer #4) |

**ARCH-187** (identity enforcement) — фикс был реализован в коде, но защитный механизм (pre-commit hook) не работает **даже в DLD-репо**, не говоря о managed-проектах. ARCH-187 сама была force-done оператором в обход своего же гарда (Archaeologist #4).

**Evidence:** Archaeologist #3/#4, Cartographer #4/#15, Coroner #5, Geologist (writer table).

---

### Root 3 — Конвенция коммитов в managed-проектах **не та**, что ожидает gate

`_subject_implements` (callback.py:699-711, переписан в cefaa55) принимает:
- `feat(SPEC-123): ...` — canonical scope
- `merge SPEC-123: ...`
- `SPEC-123: ...` — legacy bare (требует space после колона)

Доминирующая конвенция в **awardybot** (460 коммитов с этим паттерном против 176 canonical) и **dowry**:
```
feat(seller-batch): cancel-while-scheduled endpoint (FTR-1053 Task 4)
feat(billing): batch worker — claim (TECH-1052 Task 3)
fix(billing): re-assert SECURITY INVOKER (BUG-1054 Task 1)
```
→ scope = домен, SPEC-ID в хвосте subject. `_subject_implements` возвращает `False` для всех таких → спеки остаются `blocked` → autopilot перезапускает → если успеет до circuit-breaker, повторно делает работу.

**Это не «баг конвенции» — это конфликт двух конвенций**:
- Конвенция DLD-репо (cefaa55 design): SPEC-ID = scope
- Конвенция awardybot/dowry: SPEC-ID = trailer
Обе валидны. cefaa55 ужесточил под одну, не уведомив другую.

**Дополнительно** (Cartographer #10, Coroner #4): `_SPEC_ID_RE` в callback.py не включает `GROWTH` префикс, а orchestrator включает. 6 живых `GROWTH-NNN` спецификаций bootstrap'ятся orchestrator'ом, но `resolve_spec_id` в callback не находит их → post-completion цепочка (QA, reflect, verify_status_sync) **молча скипается**.

---

### Root 4 — Невидимая инфраструктура: best-effort + missing CI

**Best-effort failure swallowing** (Coroner #1-3, Scout #5/#6):
- `_atomic_write` WT-sync — `log.warning`, не falls back
- `_atomic_write_file` (backlog.md) — `log.warning`
- `_push_best_effort` — `log.debug` (т.е. **в INFO логах невидимо вообще**)
- `_atomic_write` стек: 8 git plumbing вызовов **без timeout**; любой может зависнуть под `_write_lock`, заблокировав весь callback

**`scripts/vps/tests/` (~100 функций) НЕ В CI** (Accountant #1):
- `pyproject.toml:19` имеет `testpaths = ["tests"]`
- В `tests/` лежат только callback-тесты
- В `scripts/vps/tests/` — все тесты lifecycle.py, orchestrator.py, db.py, render_backlog.py — запускаются только вручную через `run-tests.sh`
- Любая регрессия в lifecycle/orchestrator **уходит в прод без сигнала**
- Coverage gate (`.github/workflows/test.yml`) только на callback.py ≥65%; lifecycle (602 LOC) и orchestrator (667 LOC) — **никакого gate**

**Тесты не покрывают сегодняшние баги:**

| Сегодняшний bug | Тест который должен был ловить | Статус |
|---|---|---|
| 1. bootstrap_new_specs archive→done без gate | — | **отсутствует** |
| 2. _subject_implements конвенция | `chore(area, FTR-X)` documented but untested | PARTIAL |
| 3. _atomic_write WT-sync stale-index | — | **отсутствует** |
| 4. pre-commit-guard не задеплоен | — | **отсутствует** |
| 5. local tests poisoning prod-DB | `tmp_db` fixture есть, но не autouse в `tests/conftest.py` | PARTIAL |

**Integration тесты на already-merged мокают `_is_done_on_develop`** (Accountant #8) — то есть **сам gate в реальном end-to-end не проверяется ни одним тестом**.

---

### Root 5 — God module + duplicated logic

**callback.py = 1374 LOC, 36 функций, 6+ ответственностей** (Coroner «God Object», Cartographer #1, Archaeologist #13):
1. Pueue integration
2. Spec parsing (2 parser'a: v1 + legacy)
3. Git guard (Rule 1 + circuit-breaker + commit stats)
4. Audit JSONL
5. Backlog render trigger
6. Downstream dispatch (QA, reflect, события)
7. `verify_status_sync` — 202 LOC одна функция (более половины CLAUDE.md лимита)

**Duplicated logic:**
- `_atomic_write` / `_atomic_write_file` — две почти идентичные 80-LOC функции с одинаковым 8-step git plumbing (Coroner Finding 1). Баг в WT-sync есть **в обеих**.
- `_pueue_add` в callback и orchestrator с разными сигнатурами (Cartographer #8, Archaeologist #12)
- `is_already_queued` (callback) ловит только Running/Queued, `pueue_has_active_label` (orchestrator) ловит ещё Locked/Stashed/Paused → возможен **double-dispatch QA/Reflect** (Coroner #10)
- `_load_env` / `_setup_logging` дословно скопированы в 3 модуля (Cartographer #9, Coroner #13)
- Backlog row regex — 2 копии (orchestrator.py + migrate.py)
- `_SPEC_ID_RE` — расходящиеся версии (с/без GROWTH)
- `_subject_implements` ничего не логирует при rejection — спека остаётся `blocked` без диагностики, оператор не знает что искать (Coroner #15)

---

## Top-30 Findings (consolidated, severity-sorted)

| # | Source | Finding | Severity | File:Line |
|---|---|---|---|---|
| 1 | Carto/Coro/Arch | callback.py 1374 LOC = 3.4× лимита, 6+ ответственностей в одном модуле — структурный долг, делающий все следующие фиксы дороже | critical | callback.py:1-1374 |
| 2 | Carto/Coro | `_subject_implements` отвергает доминирующую awardybot/dowry конвенцию (460 vs 176 коммитов) → систематические false-blocked | critical | callback.py:699-711 |
| 3 | Geo/Arch/Carto | bootstrap_new_specs читает WT `ai/backlog.md` без Rule 1 gate → 15 fake-done flips сегодня | critical | orchestrator.py:295,323 |
| 4 | Carto/Scout/Coro | `pre-commit-lifecycle-guard.mjs` мёртв — `core.hooksPath=.git/hooks` во всех 3+ репо, guard в `.git-hooks/`. Не работает **нигде**, не только в managed | critical | `.git-hooks/pre-commit`, `git config core.hookspath` |
| 5 | Scout/Carto | guard не задеплоен в 10 managed-проектов (awardybot/wb/dowry/...) — даже если починить #4, защиты в managed не будет | critical | filesystem audit: 0/10 проектов имеют hook |
| 6 | Coro/Arch | `template/.claude/skills/spark/completion.md:46` требует `DLD-CALLBACK-MARKER-START v1` который ARCH-186 удалил — каждый новый Spark-spec будет malformed | critical | template/completion.md:46 vs feature-mode.md:653 |
| 7 | Scout | TELEGRAM_BOT_TOKEN коммитнут в открытом виде в git-tracked `.env` | critical | scripts/vps/.env |
| 8 | Acct | `scripts/vps/tests/` (~100 тестов lifecycle/orchestrator/bootstrap) **не в CI** — `pyproject.toml:19 testpaths=["tests"]` | critical | pyproject.toml:19 |
| 9 | Acct | На все 5 сегодняшних багов — 0 регрессионных тестов (или PARTIAL) | critical | tests/* gap matrix |
| 10 | Geo/Coro/Carto | `_atomic_write` WT-sync читает из main index (private GIT_INDEX_FILE уже удалён в finally), → стейл-blob → 13 D файлов в awardybot WT | high | lifecycle.py:243-258 |
| 11 | Coro | `_atomic_write` и `_atomic_write_file` — две копии 80-LOC git plumbing. Stale-index bug в обеих | high | lifecycle.py:171, lifecycle.py:469 |
| 12 | Scout | lifecycle.py `_run()` **без timeout** на 8 git plumbing вызовах; любой может зависнуть под `_write_lock` → весь callback заблокирован | high | lifecycle.py:77-88 |
| 13 | Scout | `_push_best_effort` логирует на DEBUG — push failures **не видны в INFO логах**, multi-machine convergence ADR-023 ломается молча | high | lifecycle.py:263-266 |
| 14 | Geo | `started_at` в lifecycle yaml **всегда null** — verify_status_sync делает `queued → done` минуя `in_progress`, поле никогда не записывается → структурно сломано | high | lifecycle.py:155-158, BUG-188.yaml:8 |
| 15 | Geo | `migrate_backlog_to_lifecycle.py` не идемпотентна — `--commit` повторно затрёт `version`, `transitions`, `status` к migration-time | high | migrate.py:224-225 (write_text без CAS) |
| 16 | Scout | awardybot + wb имеют дёрти `ai/lifecycle/` WT vs HEAD — orchestrator restart упадёт через `assert_clean_lifecycle_tree` FATAL | high | git status в обоих репо |
| 17 | Arch | callback.py 19 bare `except Exception` (ADR-004 разрешает только в hooks/) — silent error swallowing в gate-логике | high | callback.py grep `except Exception` |
| 18 | Arch | ARCH-187 (identity enforcement spec) **сама** была force-done оператором, в обход своего же гарда | high | ai/lifecycle/ARCH-187.yaml:17-21 |
| 19 | Acct | Integration тесты для already-merged мокают `_is_done_on_develop` — основной gate в реальном end-to-end **не тестируется** | high | tests/integration/test_callback_already_merged.py:151 |
| 20 | Acct | Coverage gate только на callback.py ≥65%; lifecycle/orchestrator (1269 LOC прод) — никакого gate | high | .github/workflows/test.yml |
| 21 | Carto/Coro | `_SPEC_ID_RE` в callback не включает GROWTH (orchestrator включает) → GROWTH-NNN спеки молча скипают QA/reflect | high | callback.py:43 vs orchestrator.py:299 |
| 22 | Coro/Arch | spec_lint.py — зомби: валидирует DLD-CALLBACK-MARKER который ARCH-186 удалил; pre-commit hook всё ещё вызывает → ложная уверенность в compliance | medium | spec_lint.py:25-26, .git-hooks/pre-commit:29 |
| 23 | Coro | `reconcile_orphans` пишет lifecycle с `by="callback"` хотя вызывается из orchestrator — audit trail врёт | medium | lifecycle.py:551, orchestrator.py:364 |
| 24 | Coro | `scan_queued` читает hardcoded `SCRIPT_DIR/callback-audit.jsonl`, callback пишет в `CALLBACK_AUDIT_LOG` env — пути расходятся при кастомном env | medium | orchestrator.py:520 vs callback.py:574 |
| 25 | Carto/Arch/Coro | `_pueue_add` дублирован в callback и orchestrator с разными сигнатурами + `is_already_queued` пропускает Stashed/Locked/Paused (orchestrator ловит) → возможен double-dispatch | medium | callback.py:352, orchestrator.py:157-160 |
| 26 | Geo | `allowed_files_hash` есть в каждом yaml но **всегда null** — мёртвое поле, нет writers | medium | lifecycle.py:599, все 190+ yaml |
| 27 | Geo | 4 lifecycle yaml имеют `priority: p3` — `render_backlog.py:37 PRIORITY_ORDER` знает только p0/p1/p2 → молча исчезают из render | medium | TECH-057.yaml + 3 других |
| 28 | Geo | Нет DB schema versioning; `_MIGRATIONS_APPLIED` — process-global флаг, ресет на рестарт | medium | db.py:21,31-83 |
| 29 | Geo | `task_log.pueue_id`, `night_findings.(project_id,status)` — нет индексов на hot queries, full scan при росте | medium | schema.sql, db.py:264,560 |
| 30 | Arch | `verify_status_sync` docstring референсит Rules 1/3/4/5/7 из 8-rule, опускает Rules 2 и 6 — design split между callback и orchestrator без документированной карты | medium | callback.py:1014-1019 |

---

## Архитектурный вердикт

**Этот контур не выдерживает своего scope.** Один callback.py владеет 7-ю ответственностями, написан под допущение единого writer'а, который реально не единственный, защищается хуком, который не работает, против конвенции, которой managed-проекты не следуют, с тестами, которые не запускаются в CI, и с best-effort failure modes, которые молча пропускают сбои в multi-machine convergence guarantee.

**Каждое следующее «правило» в этом контуре будет иметь негативный ROI**, потому что:
1. Добавление к 1374 LOC сделает callback ещё хуже maintainable
2. Новое правило не сможет покрыть split-brain между `bootstrap_new_specs` и `verify_status_sync` иначе как дублированием
3. Без CI-видимых тестов lifecycle/orchestrator любое новое правило не имеет регрессионной защиты — следующая итерация рефакторинга снова сломает уже починенное
4. Pre-commit guard не работает → identity enforcement из ARCH-187 декларативен, не операционен

---

## Рекомендации

**НЕ делать:**
- Очередную «8-rule redesign» в callback.py
- Очередную spec-к «фиксим 4 бага одной волны»
- Лезть в `_subject_implements` без понимания обеих конвенций (DLD vs awardybot)
- Накатывать новые ADR (018→023→024→...) поверх существующих

**Делать в порядке стоимости-impact:**

### P0 (структурные, до следующего merge в этот контур)

1. **`pyproject.toml: testpaths` расширить до `["tests", "scripts/vps/tests"]`** — самый дешёвый фикс с самым большим эффектом. Сразу ~100 тестов в CI, регрессионная сетка для lifecycle/orchestrator включена. 1 LOC изменение.
2. **`tests/conftest.py: autouse fixture` для DB_PATH isolation** — глобально подменять DB_PATH на tmp, чтобы новые тесты не могли отравить prod. 10 LOC.
3. **Починить pre-commit guard в DLD** — установить `core.hooksPath=.git-hooks` (или переместить guard в `.git/hooks/pre-commit`). Без этого ARCH-187 — декорация. 1 команда git config.
4. **TELEGRAM_BOT_TOKEN** — переместить в Nexus, удалить из .env, добавить .env в .gitignore, ротировать токен (он скомпрометирован — лежит в публичном git history).

### P1 (regression bank — pre-commit для каждого incident)

5. Для каждого incident'а (BUG-185, BUG-188, TECH-166/176/177, ARCH-186/187, сегодняшние 5) написать **один** integration test, который падает без фикса. ADR-013 compliance: НЕ мокать `_is_done_on_develop` / `_fetch_develop`. 5-10 тестов.
6. Coverage gate расширить на lifecycle.py и orchestrator.py (≥60% хотя бы).
7. Удалить мёртвый код: spec_lint.py, DLD-CALLBACK-MARKER из template/spark/completion.md, marker-related регрессионные тесты, `.worktrees/ARCH-186`, `.worktrees/ARCH-187`.

### P2 (архитектурный пересмотр — спросить «правильна ли архитектура?»)

8. **`/architect` или `/retrofit` сессия именно по этому контуру.** Не «фиксим 4 бага», а «можно ли callback разнести на 3 модуля: gate (read-only) + writer (single responsibility) + dispatcher». Без этого расщепления будет 6-я, 7-я, 8-я итерация.
9. **bootstrap_new_specs должен использовать тот же gate** (`_is_done_on_develop`), что и `verify_status_sync`. ИЛИ — bootstrap отменить и оставить только Spark как single creator of lifecycle yaml. Не должно быть «параллельный writer без gate».
10. **`_subject_implements` принять ОБЕ конвенции** (scope + trailer), задокументировать как ADR, добавить тесты для каждой. ИЛИ — стандартизировать managed-проекты под одну конвенцию (это требует операционной работы по проектам).
11. **WT-sync переписать** — `git checkout HEAD -- <file>` вместо `checkout-index --force --` (последнее читает из stale main index, как нашли Geologist + Coroner). И добавить timeout на все `_run()` вызовы в lifecycle.py.
12. **Deployment механизм для managed-проектов** — скрипт `register-project.sh` устанавливает `.git-hooks/`, делает `git config core.hooksPath`, валидирует. Без этого `ARCH-187` навсегда останется декоративной защитой.

### P3 (нюансы)

13. Удалить `allowed_files_hash` (мёртвое поле) или реализовать его.
14. `priority: p3` либо добавить в PRIORITY_ORDER, либо валидировать на write.
15. DB retention для `task_log`, `callback_decisions`, `sdk_post_result_errors`.
16. Индексы на hot queries.
17. Schema versioning через `PRAGMA user_version`.
18. Унифицировать `_load_env`, `_pueue_add`, `_SPEC_ID_RE` в общий `scripts/vps/common.py`.

---

## Handoff

- **`/architect` mode** — этот отчёт как primary input для архитектурного пересмотра callback/lifecycle/orchestrator.
- **`/spark` на P0 #1-#4** — это однострочные/однофайловые фиксы с измеримым эффектом, можно делать прямо.
- **`/spark` на P1 regression bank** — отдельной spec'кой, систематический подход к incident-driven testing.

---

## Operations Log

- Personas dispatched: 6 (parallel, background)
- Reports compiled: 6 (Cartographer 15 findings, Archaeologist 14, Accountant 13, Geologist 13, Scout 12, Coroner 18) = 85 findings total
- Synthesis: inline (caller-writes, ADR-007 — subagents не пишут файлы надёжно)
- Coverage: 100% core contour files
- Wall time: ~8 минут параллельно
