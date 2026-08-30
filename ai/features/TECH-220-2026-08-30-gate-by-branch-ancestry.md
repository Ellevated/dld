# Feature: [TECH-220] Гейт «реализация есть» — по предку ветки, а не по тексту коммита

**Priority:** P0 | **Date:** 2026-08-30 | **Parent:** ARCH-219
**Size:** 4 tasks / 10 files — indivisible: одна функция гейта обязана встать во все четыре точки
вызова одним коммитом, иначе воспроизводится дрейф двух гейтов, который TECH-210 только что удалил.

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

Гейт `gate_logic.find_implementation_commit` решает «спека реализована» по **тексту** заголовка
коммита на `origin/develop`: `match_subject` принимает 12 форм (`feat(FTR-925): …`, `merge FTR-925`,
`… (FTR-925)`) и отвергает всё остальное. Аудит за 16–30.08 (`docs/2026-08-30-orchestrator-failure-audit.md`):
**31 из 61 вердиктов — ложный `no_merged_implementation`** при реальных коммитах в разрешённые файлы.
Причина — шаблон `{type}({scope})` в 9 из 15 даунстримов: коммиты `feat(managed): …` для гейта невидимы.

Контракт «subject обязан нести spec-id» живёт в промпте; промпт — не гейт. Каждая починка добавляла
регексу ещё одну форму (BUG-192, BUG-338..347, TECH-177) — это подпорки под одно решение: identity
работы хранится в тексте, который пишет модель.

В DLD нет человека, который мержит в develop. Мержит только Claude по `finishing.md`: **после зелёного
`./test ci`, `--ff-only`, из ветки `<type>/<ID>`**. Значит «ветка `<type>/<ID>` влита в `origin/develop`»
— это и есть доказательство, что протокол завершения прошёл. Git знает это без регекса.

## Context

Скауты: `ai/.spark/20260830-ARCH-219/research-{web,codebase,devil}.md`.

Четыре реальные точки вызова гейта (codebase §Step 1), все — пара `fetch_develop` → `find_implementation_commit`:

| Точка | Файл:строка | Роль |
|---|---|---|
| `callback_sync._decide_status` | `scripts/vps/callback_sync.py:198-212` | вердикт после прогона (Step 4 + grace-retry TECH-197) |
| `callback_dispatch._merge_confirmed` | `scripts/vps/callback_dispatch.py:172-173` | TECH-207: диспатч QA при потерянном `task_status` |
| `orchestrator_queue.reconcile_if_implemented` | `scripts/vps/orchestrator_queue.py:275-276` | до диспатча: «уже на develop» |
| `gate-daemon._evaluate_project` | `scripts/vps/gate-daemon.py:171,252` | shadow-режим, только JSONL |

Что devil доказал и что входит в дизайн как условия (devil §Arguments 1-4, §Edge Cases):

1. **`feature/` — только для FTR.** `worktree-setup.md:102-108`: BUG → `fix/`, TECH → `tech/`,
   ARCH → `arch/`; **GROWTH — строки нет** (в bash-`case` `autopilot-git.md:52-58` падает в `task/`).
   Карта префиксов существует только в прозе, дважды, и расходится. Буквальный `feature/<ID>` молча
   не сработал бы для ¾ спек, а FTR-тесты были бы зелёными.
2. **Bookkeeping-ветка = не реализация.** Ветка из одних `ai/features/…`, `ai/diary/…` коммитов,
   влитая в develop, не должна давать `done` (ADR-025 инцидент, `strip_bookkeeping_paths`).
3. **Самоблок автопилота перебивает положительный ancestry** ровно так, как перебивает subject.
4. **`task_log.branch` — не источник имени ветки:** `orchestrator_queue.record_dispatch:328` пишет
   `feature/{spec_id}` для всех типов. Имя выводится из префикса spec-id, не читается из БД.
5. **Фетч только `develop` недостаточен** — `fetch_develop` умышленно узкий; ветку фетчим отдельно,
   так же узко (`refs/heads/<type>/<ID>`), 15 с, best-effort.
6. **Squash-merge** ancestry не видит — как не видит и сегодняшний гейт (`finishing.md:298` запрещает).
   Остаётся на subject-фолбэке, документируется как известный случай.

Политический вопрос devil'а («любой merge = done») снят founder'ом 30.08: мержащего человека нет,
ancestry = факт прохождения `finishing.md`. Subject-регекс не удаляется в этой спеке, но получает
дату смерти: каждый вердикт пишет в audit-JSONL `gate_via=ancestry|subject`; когда `subject` не
срабатывает 30 дней — удаление регекса отдельной TECH.

---

## Scope

**In scope:** новая чистая функция ancestry-гейта в `gate_logic`; карта префиксов ветки одной функцией
с явной строкой для GROWTH; подключение во все четыре точки вызова; `gate_via` в audit; обновление
`docs/orchestrator/status-model.md` §7; тесты на throwaway git-репо.

**Out of scope:** продолжение salvage-ветки при повторном диспатче и вердикт `branch_pushed_not_merged`
(TECH-221); удаление `match_subject` (после 30 дней метрики); хук на subject (отвергнут как костыль).

---

## Impact Tree Analysis

### Step 1: UP — who uses?
_Source: grep + `codebase-memory-mcp cli trace_path` (граф устарел после TECH-216, каждая ссылка
перепроверена grep — codebase §Step 1)._
- [x] `grep -rn "gate_logic.find_implementation_commit" scripts/vps/*.py` → 4 вызова: `callback_sync.py:199,212`,
      `callback_dispatch.py:173`, `orchestrator_queue.py:276`, `gate-daemon.py:171,252`
- [x] Тесты, мокающие интерфейс: `scripts/vps/tests/test_orchestrator*.py` (`patch.object(orchestrator.gate_logic, "find_implementation_commit")`) — контракт `str | None` сохраняется

### Step 2: DOWN — what depends on?
- [x] `gate_logic` → только stdlib (FF-09: без callback/lifecycle/db). Новая функция — тот же класс: `subprocess` внутри тела
- [x] Карта префиксов — новая, в Python её нет (codebase §Step 2)

### Step 3: BY TERM — grep entire project
- [x] `grep -rn "merge-base\|is-ancestor" scripts/vps/*.py` → 0 (greenfield)
- [x] `grep -rn "find_implementation_commit" --include="*.py" --include="*.md" .` → 37 файлов; источник — 4 вызова + реэкспорты

| File | Line | Status | Action |
|------|------|--------|--------|
| `scripts/vps/callback_sync.py` | 198-212 | subject-гейт + grace-retry | ancestry первым, subject фолбэком, `gate_via` в `_Audit` |
| `scripts/vps/callback_dispatch.py` | 172-173 | subject-гейт | тот же общий вызов |
| `scripts/vps/orchestrator_queue.py` | 275-276 | subject-гейт | тот же общий вызов; `record_dispatch:328` — `branch` из карты префиксов |
| `scripts/vps/gate-daemon.py` | 171, 252 | shadow | новый вердикт отдельным полем JSONL |
| `docs/orchestrator/status-model.md` | 182-211 | описывает subject-гейт | переписать §7 guard |

### Step 4: CHECKLIST — mandatory folders
- [x] `tests/**` — `tests/unit/test_callback_branch_awareness.py` (по имени — дом для ancestry-серии),
      `tests/unit/test_callback_implementation_guard.py`, `scripts/vps/tests/test_gate_logic.py`.
      `tests/regression/` и `tests/contracts/` **не редактируются** — `test_callback_spec_corpus.py`
      тестирует парсер allowlist, к subject-вердиктам отношения не имеет (codebase, Verified References)
- [x] `db/migrations/**` — нет
- [x] `template/` — `gate_logic.py`, `gate-daemon.py` в template отсутствуют (`grep -rl gate_logic template/` → 0); синхронизировать нечего

### Verification
- [x] Все найденные файлы в Allowed Files
- [x] `match_subject` / `_SPEC_ID_RE` не трогаются (36 кейсов `test_gate_logic_subject.py` без правок)

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/gate_ancestry.py` — `branch_ref_for`, `fetch_branch`, `find_merged_branch` — stdlib-only, FF-09 (NEW)
- `scripts/vps/gate_logic.py` — `find_implementation` = ancestry → subject; импорт `gate_ancestry` (modify)
- `scripts/vps/callback_sync.py` — `_decide_status` через `find_implementation`; `gate_via` в `_Audit` (modify)
- `scripts/vps/callback_dispatch.py` — `_merge_confirmed` через `find_implementation` (modify)
- `scripts/vps/orchestrator_queue.py` — `reconcile_if_implemented` через `find_implementation`; `record_dispatch` пишет реальный префикс (modify)
- `scripts/vps/gate-daemon.py` — shadow-вердикт с `gate_via` (modify)
- `scripts/vps/tests/test_gate_logic.py` — ancestry-серия на throwaway-репо (modify)
- `tests/unit/test_callback_branch_awareness.py` — EC-серия ancestry через публичный callback.verify_status_sync (modify)
- `tests/unit/test_callback_implementation_guard.py` — самоблок перебивает ancestry (modify)
- `docs/orchestrator/status-model.md` — §7 Implementation guard (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** orchestrator — единственный writer статусов (ADR-023)
**Cross-cutting:** Errors — fail-closed: любая ошибка git/фетча → `None` → `blocked`, никогда не `done`;
callback «Always exit 0»
**Data model:** `ai/lifecycle/*.yaml` только через `lifecycle.write_lifecycle`; audit-JSONL получает поле `gate_via`

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

`ai/lessons/` содержит только `.gitkeep`. Gate 7 auto-pass (no lessons bank).

След из git-истории (codebase §Git Context): `cefaa55` — «origin/develop-only» закон, тест
`test_no_local_develop_gate_path` проверяет исходник; `6df9807` — спека закрывалась собственным
birth-коммитом (→ `strip_bookkeeping_paths`); `176d824`/`c1068f5` — каждая волна ложных blocked
добавляла регексу форму; `774977a` — TECH-210 удалил второй экземпляр гейта; `1be55b4` —
`wip(TECH-210): salvaged after timeout` — сама TECH-210 попала в сценарий, который чинит ARCH-219.

---

## Approaches

### Approach 1: ancestry primary, subject deprecated fallback (выбран)
**Source:** `research-web.md` §Approach 1 (git-scm: `merge-base --is-ancestor` — примитив, на котором
построен `git branch --merged`); `research-codebase.md` §Recommendation
**Summary:** `find_implementation(project, spec_id, allowed) -> (sha|None, via)`: (1) фетч ветки
`<type>/<ID>`; (2) `merge-base --is-ancestor origin/<type>/<ID> origin/develop`; (3) дифф
`merge-base..tip` пересекается с `strip_bookkeeping_paths(allowed)`; (4) иначе — старый
`find_implementation_commit` с `via="subject"`
**Pros:** identity работы — в git, не в тексте; закрывает причину №1 аудита без правки 9 даунстримов;
фолбэк сохраняет все 36 subject-вердиктов; одна функция во всех 4 точках
**Cons:** карта префиксов — третья копия (две прозы + Python); squash остаётся на фолбэке

### Approach 2: salvage мержит сам на зелёном, гейт не трогать
**Source:** `research-devil.md` §Alternative 1; аудит п.3c
**Summary:** `salvage.py` после смерти прогона делает `--ff-only` в develop, если `./test ci` зелёный
**Pros:** R1, один файл, Rule 1/7 не тронуты
**Cons:** причина №1 (`{scope}`) не закрыта вообще; красная ветка сгорает; identity остаётся в регексе

### Approach 3: Gerrit `Change-Id` трейлер
**Source:** `research-web.md` §Approach 3
**Cons:** хук на все машины, дублирует ID, который уже несёт имя ветки; отвергнут

### Selected: 1
**Rationale:** единственный, где гейт перестаёт читать текст, написанный моделью. Approach 2 — ровно
тот класс подпорки, о котором founder сказал «сколько можно»; берётся его полезная половина
(salvage-ветка видна гейту) в TECH-221.

---

## Design

### `gate_ancestry` (новый, stdlib-only) + `gate_logic.find_implementation`

`gate_logic.py` — 398 LOC, лимит 400: ancestry-функции живут в новом `gate_ancestry.py` (тот же
FF-09 контракт), `gate_logic` получает только `find_implementation` и импорт.

```python
_BRANCH_PREFIX = {"FTR": "feature", "BUG": "fix", "TECH": "tech", "ARCH": "arch", "GROWTH": "growth"}
# L-derived-4: worktree-setup.md:102-108 и autopilot-git.md:52-58 обязаны совпадать с этой картой.
# GROWTH раньше не имел строки нигде и в bash падал в `task/` — здесь решено: growth/.

def branch_ref_for(spec_id: str) -> str:            # "feature/FTR-925"; ValueError на неизвестный префикс
def fetch_branch(project_path, spec_id, timeout=15) -> bool   # git fetch origin refs/heads/<b>:refs/remotes/origin/<b>; best-effort
def find_merged_branch(project_path, spec_id, allowed) -> str | None
    # 1. ref = refs/remotes/origin/<branch>; нет → None
    # 2. git merge-base --is-ancestor <ref> origin/develop; rc≠0 → None
    # 3. base = git merge-base <ref> origin/develop
    #    files = git diff --name-only base <ref>; ∩ strip_bookkeeping_paths(allowed) == ∅ → None
    # 4. return tip sha
def find_implementation(project_path, spec_id, allowed) -> tuple[str | None, str]
    # ("<sha>", "ancestry") | ("<sha>", "subject") | (None, "none")
    # subject = существующий find_implementation_commit, без изменений
```

Точное имя ref, никаких glob (`ARCH-176` ≠ `ARCH-176a`, devil DA-8). Все subprocess-ошибки → `None`.
`find_implementation_commit` и `match_subject` не меняются ни на байт.

### Точки вызова

Все четыре заменяют пару `fetch_develop` + `find_implementation_commit` на
`fetch_develop` + `fetch_branch` + `find_implementation`. `callback_sync._decide_status` сохраняет
порядок: `_push_local_develop` (TECH-197) **до** гейта; grace-retry ×3 — тем же `find_implementation`;
самоблок (`autopilot_signaled and target == "blocked"`) перебивает любой `via`.
`_Audit` получает поле `gate_via`, `_emit_audit` пишет его как `extra`.
`record_dispatch` пишет `branch=branch_ref_for(spec_id)`.

### Squash / удалённая ветка

Ветка удалена после merge (§0a sweep) → шаг 1 даёт `None` → фолбэк subject. Squash-merge → ancestry
`False` → фолбэк subject. Оба случая — `gate_via=subject`, видны в метрике.

---

## Implementation Plan

### Research Sources
- `research-web.md` §Approach 1, §Pitfalls (stale refs, shallow clone, `merge-tree` trap)
- `research-codebase.md` §Reusable Modules, §Verified References
- `research-devil.md` DA-1..DA-12, SA-2..SA-7

### Task 1: gate_logic — ancestry-функции + карта префиксов
**Type:** code
**Files:**
  - create: `scripts/vps/gate_ancestry.py`
  - modify: `scripts/vps/gate_logic.py`
  - modify: `scripts/vps/tests/test_gate_logic.py`
**Pattern:** существующие тесты `find_implementation_commit` на throwaway-репо (`git init`, ветка, merge)
**Acceptance:** EC-1..EC-6 зелёные; `match_subject`-тесты без правок зелёные; FF-09 (`grep -nE "^import (callback|lifecycle|db)" scripts/vps/gate_ancestry.py scripts/vps/gate_logic.py` — пусто); оба файла ≤ 400 LOC

### Task 2: четыре точки вызова + gate_via
**Type:** code
**Files:**
  - modify: `scripts/vps/callback_sync.py`
  - modify: `scripts/vps/callback_dispatch.py`
  - modify: `scripts/vps/orchestrator_queue.py`
  - modify: `scripts/vps/gate-daemon.py`
**Pattern:** TECH-210 `6e8db68` — перенацеливание всех точек одним коммитом
**Acceptance:** `grep -rn "find_implementation_commit(" scripts/vps/*.py` → только внутри `gate_logic.find_implementation`; audit-строка содержит `gate_via`

### Task 3: EC-серия через публичный контракт
**Type:** test
**Files:**
  - modify: `tests/unit/test_callback_branch_awareness.py`
  - modify: `tests/unit/test_callback_implementation_guard.py`
**Pattern:** `tests/integration/test_callback_feature_branch.py` (реальный git-репо, без моков)
**Acceptance:** EC-7..EC-11 зелёные; `tests/regression/` без правок зелёные

### Task 4: status-model.md §7
**Type:** docs
**Files:**
  - modify: `docs/orchestrator/status-model.md`
**Acceptance:** §7 описывает ancestry как primary, subject как deprecated с метрикой `gate_via`

### Execution Order
1 → 2 → 3 → 4

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Автопилот мержит `<type>/<ID>` `--ff-only` в develop и пушит | — | existing (`finishing.md`) |
| 2 | Callback фетчит develop и ветку | Task 1, 2 | ✓ |
| 3 | Ancestry + пересечение с allowlist без bookkeeping | Task 1 | ✓ |
| 4 | Фолбэк subject при отсутствии ветки / squash | Task 1 | ✓ |
| 5 | Самоблок перебивает | Task 2, 3 | ✓ |
| 6 | Вердикт и `gate_via` в lifecycle + audit | Task 2 | ✓ |
| 7 | Pre-dispatch reconcile и QA-фолбэк — тот же вердикт | Task 2 | ✓ |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Ветка влита, трогает allowed | `fix/BUG-9` merged ff-only, коммит `feat(managed): x` в `src/x.py` | `("<sha>", "ancestry")` | deterministic | audit причина №1 | P0 |
| EC-2 | Bookkeeping-only ветка | ветка меняет только `ai/features/…`, `ai/diary/…` | `(None, "none")` | deterministic | devil DA-1, ADR-025 | P0 |
| EC-3 | Префикс по типу | `BUG-9` → `fix/`, `TECH-9` → `tech/`, `ARCH-9` → `arch/`, `GROWTH-9` → `growth/`; `XXX-9` → `ValueError` | ref точный | deterministic | devil DA-2/DA-3 | P0 |
| EC-4 | Ветка запушена, не влита | `origin/fix/BUG-9` есть, не предок | ancestry `None` → фолбэк subject | deterministic | devil | P0 |
| EC-5 | Squash-merge | новый коммит на develop с subject `feat(FTR-9): …`, ветка не предок | `("<sha>", "subject")` | deterministic | devil DA-4 | P1 |
| EC-6 | Суффикс сабспеки | ветки `arch/ARCH-176` и `arch/ARCH-176a` | `ARCH-176` никогда не матчит `ARCH-176a` | deterministic | devil DA-8 | P1 |
| EC-7 | Самоблок перебивает ancestry | ветка влита, `autopilot_signaled=True, target=blocked` | lifecycle `blocked / autopilot_signaled_blocked` | deterministic | devil DA-11 | P0 |
| EC-8 | Ошибка git → fail-closed | `origin` недоступен / `merge-base` rc=128 | `(None, "none")`, исключение не выходит из callback | deterministic | FF-09 | P0 |
| EC-9 | Порядок push-local → гейт | локальный merge не запушен, `target=blocked`, `autopilot_signaled=False` | `_push_local_develop` до `find_implementation`; итог `done` | deterministic | devil DA-9 | P1 |
| EC-10 | `record_dispatch` пишет реальный префикс | `TECH-9` | `task_log.branch == "tech/TECH-9"` | deterministic | devil DA-10 | P1 |
| EC-11 | Регрессия subject-вердиктов | `test_gate_logic_subject.py` (36), `test_callback_implementation_guard.py` EC-4..9 | без правок зелёные | deterministic | devil DA-12 | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-12 | Четыре точки вызова на одном (spec, git-state) | `_decide_status`, `_merge_confirmed`, `reconcile_if_implemented`, `_evaluate_project` | одинаковый вердикт и `via` | integration | devil SA-5 | P0 |
| EC-13 | Живой callback на VPS на реальной done-спеке с существующей веткой | `python3 callback.py <id> claude-runner Success` | audit-строка с `gate_via=ancestry` | integration | TECH-216 EC-12 | P0 |

### Coverage Summary
Deterministic: 11 | Integration: 2 | LLM-Judge: 0 | Total: 13 (min 3 ✓)

### TDD Order
1. EC-1, EC-2, EC-3 — красные на пустом `gate_logic` → Task 1
2. EC-4..EC-6, EC-8 — граничные ancestry
3. EC-7, EC-9, EC-12 — точки вызова
4. EC-10, EC-11, EC-13 — регрессия и живой прогон

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Модули импортируются | `PYTHONPATH=scripts/vps python -c "import gate_ancestry, gate_logic, callback, callback_sync, callback_dispatch, orchestrator_queue"` | exit 0 | 15s |
| AV-S2 | FF-09 | `grep -nE "^import (callback|lifecycle|db)" scripts/vps/gate_ancestry.py scripts/vps/gate_logic.py` | пусто | 5s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Гейт-тесты | — | `cd scripts/vps/tests && python -m pytest -q -k "gate_logic or callback or orchestrator"` | 0 failed |
| AV-F2 | Корневые | — | `python -m pytest -q tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/` | 0 failed |
| AV-F3 | Coverage-гейт | — | команда из `.github/workflows/test.yml` | ≥54 % |
| AV-F4 | Живой callback на VPS | VPS, спека со влитой веткой | EC-13 | `gate_via=ancestry` в `callback-audit.jsonl` |

### Verify Command

```bash
PYTHONPATH=scripts/vps python -c "import gate_ancestry, gate_logic, callback, callback_sync, callback_dispatch, orchestrator_queue"
cd scripts/vps/tests && python -m pytest -q -k "gate_logic or callback or orchestrator" && cd ../../..
python -m pytest -q tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `find_implementation` — единственный вход гейта во всех четырёх точках
- [ ] Карта префиксов одной функцией, GROWTH определён
- [ ] `gate_via` в каждой audit-строке

### Tests
- [ ] EC-1..EC-13 проходят
- [ ] `tests/regression/`, `test_gate_logic_subject.py` зелёные **без правок**

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1..F3 локально; AV-F4 на VPS

### Technical
- [ ] `match_subject`, `find_implementation_commit`, `_SPEC_ID_RE` не изменены
- [ ] Все файлы ≤ 400 LOC
- [ ] Rule 7 и «origin/develop-only» (`test_no_local_develop_gate_path`) соблюдены

---

## Autopilot Log
