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
- [x] Тесты, мокающие интерфейс — **8 файлов, 24 патч-сайта** (planner 2026-08-30, было указано «test_orchestrator*.py»):
      `tests/integration/test_callback_{feature_branch,already_merged,no_impl_demote,blocked_no_dispatch,status_sync}.py`,
      `scripts/vps/tests/test_{callback,gate_daemon,orchestrator}.py`. **Ни один не в Allowed Files.**
      Все патчат атрибут модуля `gate_logic.find_implementation_commit` лямбдой на 3 позиционных аргумента
      (`lambda *a: "deadbee"`, `def spy_find(project_path, spec_id, allowed)`, `def _delayed_is_done(pp, sid, af)`).
      Патчи остаются рабочими ровно потому, что subject-фолбэк зовёт `gate_logic.find_implementation_commit`
      как **атрибут модуля**, позиционно, тремя аргументами — см. Task 1 «Не сломать 24 патч-сайта»

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

- `scripts/vps/gate_ancestry.py` — `branch_ref_for`, `fetch_branch`, `_base_for_diff`, `find_merged_branch`, `find_implementation` — stdlib + `gate_logic`, FF-09 (NEW)
- `scripts/vps/callback_sync.py` — `_decide_status` через `find_implementation`; `gate_via` в `_Audit` (modify)
- `scripts/vps/callback_dispatch.py` — `_merge_confirmed` через `find_implementation` (modify)
- `scripts/vps/orchestrator_queue.py` — `reconcile_if_implemented` через `find_implementation`; `record_dispatch` пишет реальный префикс (modify)
- `scripts/vps/gate-daemon.py` — shadow-вердикт с `gate_via` (modify)
- `scripts/vps/tests/test_gate_ancestry.py` — ancestry-серия EC-1..EC-6, EC-8 на throwaway-репо (NEW)
- `tests/unit/test_callback_branch_awareness.py` — EC-серия ancestry через публичный callback.verify_status_sync (modify)
- `tests/unit/test_callback_implementation_guard.py` — самоблок перебивает ancestry (modify)
- `scripts/vps/tests/test_claude_runner_timeout.py` — `test_push_local_is_best_effort_not_gate`: имя точки входа гейта (modify)
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

### `gate_ancestry` (новый, stdlib + `gate_logic`)

**Правка planner 2026-08-30 к исходному дизайну (две штуки, обе обязательные — см. Drift Log):**

1. **`find_implementation` живёт в `gate_ancestry`, не в `gate_logic`.** `gate_logic.py` = 398 LOC при
   лимите 400; добавить туда функцию с докстрингом = 418 LOC, т.е. ровно тот лимит, ради которого
   и заводился отдельный модуль. Направление импорта одностороннее: `gate_ancestry → gate_logic`,
   обратного импорта нет (был бы цикл). **`gate_logic.py` в этой спеке не меняется вообще.**
2. **Шаг 3 (диапазон диффа) в исходном виде не работает.** `finishing.md:53-54` мержит
   `git pull --rebase origin develop` + `git merge --ff-only {type}/{ID}` → после ff-мержа
   `merge-base(<ref>, origin/develop) == <ref>`, и `git diff base <ref>` **всегда пуст** → ancestry
   никогда бы не срабатывала, гейт молча остался бы на subject. Нижняя граница для ff-случая —
   birth-коммит спеки (`ai/features/<ID>-*.md`), он гарантированно на develop до создания ветки.

```python
_BRANCH_PREFIX = {"FTR": "feature", "BUG": "fix", "TECH": "tech", "ARCH": "arch", "GROWTH": "growth"}
# L-derived-4: worktree-setup.md:102-108 и autopilot-git.md:52-58 обязаны совпадать с этой картой.
# GROWTH раньше не имел строки нигде и в bash падал в `task/` — здесь решено: growth/.

def branch_ref_for(spec_id: str) -> str            # "feature/FTR-925"; ValueError на неизвестный префикс
def fetch_branch(project_path, spec_id, timeout=15) -> bool   # git fetch origin refs/heads/<b>:refs/remotes/origin/<b>; best-effort
def find_merged_branch(project_path, spec_id, allowed) -> str | None
    # 1. ref = refs/remotes/origin/<branch>; git rev-parse --verify --quiet → нет → None
    # 2. git merge-base --is-ancestor <ref> origin/develop; rc≠0 → None
    # 3. base = _base_for_diff(...)  ← ff-случай: birth-коммит спеки, no-ff: merge-base
    #    files = git diff --name-only base <tip>; ∩ strip_bookkeeping_paths(allowed) == ∅ → None
    # 4. return tip sha
def find_implementation(project_path, spec_id, allowed) -> tuple[str | None, str]
    # ("<sha>", "ancestry") | ("<sha>", "subject") | (None, "none")
    # subject = gate_logic.find_implementation_commit, атрибутом модуля, позиционно, 3 аргумента
```

Точное имя ref, никаких glob (`ARCH-176` ≠ `ARCH-176a`, devil DA-8). Все subprocess-ошибки → `None`.
`find_implementation_commit`, `match_subject`, `_SPEC_ID_RE` не меняются ни на байт.

**Ветка на origin переживает merge.** `worktree-setup.md:41,55,179` удаляют только **локальную**
ветку (`git branch -d`); `git push origin --delete` в дереве промптов нет ни разу. Значит
`refs/remotes/origin/<type>/<ID>` доступна гейту и после свипа — исходное «ветка удалена → фолбэк»
остаётся теоретическим случаем, а не основным.

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

## Detailed Implementation Plan

_Планировщик перепроверил каждую ссылку Impact Tree против рабочего дерева `tech/TECH-220`
2026-08-30: `callback_sync.py:198-212`, `callback_dispatch.py:172-173`,
`orchestrator_queue.py:275-276` и `:328`, `gate-daemon.py:171,252`,
`status-model.md:182-211`, `gate_logic.py` = 398 LOC — **все точны, правок не потребовалось**.
Изменены две вещи: строка Impact Tree Step 1 про мокающие тесты (было «test_orchestrator*.py»,
на деле 8 файлов / 24 сайта) и Design (см. Drift Log)._

### Research Sources

Внешний поиск не проводился и не требовался: `merge-base --is-ancestor` (rc 0/1/иное),
refspec `refs/heads/X:refs/remotes/origin/X` и `git diff --name-only A B` — примитивы,
стабильные задолго до cutoff. Всё, что нуждалось в проверке, проверено по репозиторию:
`.claude/skills/autopilot/finishing.md:51-61,295-300` (ff-only merge, push ветки до мержа),
`worktree-setup.md:41,53-57,102-108,179` (карта префиксов, свип удаляет только локальные ветки),
`autopilot-git.md:44-59,259` (вторая копия карты, `task/` фолбэк).

### Задача 5 задач, а не 4

Исходная Task 2 держала 4 файла при потолке 3 файла/задача. Разнесена на две (callback-контур
и orchestrator-контур). Атомарность, ради которой в Size написано «одним коммитом», сохраняется:
обе задачи идут подряд в одном прогоне, ни один прогон не завершается с частично перенацеленными
точками вызова.

---

### Task 1: `gate_ancestry.py` — ancestry-гейт + единая точка входа

**Type:** code
**Files:**
- Create: `scripts/vps/gate_ancestry.py` (~195 LOC)
- Test: `scripts/vps/tests/test_gate_logic.py` (append ancestry-серию в конец)

**Context:** гейт перестаёт читать текст, написанный моделью. Модуль отдельный, потому что
`gate_logic.py` = 398 LOC при лимите 400. Импорт строго односторонний
(`gate_ancestry → gate_logic`); `gate_logic.py` не трогается.

**Не сломать 24 патч-сайта (load-bearing, читать до написания кода).**
8 тестовых файлов вне Allowed Files делают
`monkeypatch.setattr(gate_logic, "find_implementation_commit", …)` и ожидают, что подмена
доедет до вердикта. Она доедет **только если** subject-фолбэк зовёт
`gate_logic.find_implementation_commit(project_path, spec_id, allowed_files)` —
атрибутом модуля, позиционно, ровно тремя аргументами. Запрещено:
`from gate_logic import find_implementation_commit` (имя связывается на импорте — патч промахнётся),
именованные аргументы (`spy_find(project_path, spec_id, allowed)` в
`test_gate_daemon.py:410` и `_delayed_is_done(pp, sid, af)` в `test_callback.py:603`
принимают только позиционные).

**Steps:**

1. Красный тест — дописать в конец `scripts/vps/tests/test_gate_logic.py`
   (переиспользуя тамошние `_git`, `git_repo_with_remote`, `_add_commit`, `_push_to_remote`):

```python
# --- TECH-220: ancestry gate ------------------------------------------------

from gate_ancestry import (  # noqa: E402
    branch_ref_for,
    find_implementation,
    find_merged_branch,
)


def _spec_birth(repo: Path, spec_id: str) -> None:
    """Spark-коммит спеки на develop — он же нижняя граница ff-диффа."""
    _add_commit(repo, f"ai/features/{spec_id}-2026-08-30-x.md", f"docs({spec_id}): spec")


def _ff_merge_branch(repo: Path, branch: str, files: list[str], subject: str) -> str:
    """Ветка от develop, коммит, ff-only merge, push ветки И develop."""
    _git(repo, "checkout", "-q", "-b", branch)
    for f in files:
        _add_commit(repo, f, subject)
    _git(repo, "push", "-q", "-u", "origin", branch)
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "--ff-only", "-q", branch)
    _git(repo, "push", "-q", "origin", "develop")
    _git(repo, "fetch", "-q", "origin")
    return _git(repo, "rev-parse", branch).strip()


class TestAncestryGate:
    def test_ec1_merged_branch_touching_allowed_file(self, git_repo_with_remote):
        """EC-1: ветка влита ff-only, subject гейту непонятен → ancestry."""
        repo = git_repo_with_remote
        _spec_birth(repo, "BUG-9")
        _push_to_remote(repo)
        tip = _ff_merge_branch(repo, "fix/BUG-9", ["src/x.py"], "feat(managed): x")

        assert find_merged_branch(str(repo), "BUG-9", ["src/x.py"]) == tip
        assert find_implementation(str(repo), "BUG-9", ["src/x.py"]) == (tip, "ancestry")

    def test_ec2_bookkeeping_only_branch_is_not_evidence(self, git_repo_with_remote):
        """EC-2: ветка из одних ai/-коммитов влита → не done (devil DA-1, ADR-025)."""
        repo = git_repo_with_remote
        _spec_birth(repo, "BUG-10")
        _push_to_remote(repo)
        _ff_merge_branch(
            repo, "fix/BUG-10", ["ai/diary/2026-08-30.md"], "docs(BUG-10): diary"
        )

        assert find_merged_branch(str(repo), "BUG-10", ["src/x.py", "ai/diary/x.md"]) is None
        assert find_implementation(str(repo), "BUG-10", ["src/x.py"]) == (None, "none")

    def test_ec3_branch_prefix_map(self):
        """EC-3: карта префиксов, включая GROWTH; неизвестный тип → ValueError."""
        assert branch_ref_for("FTR-9") == "feature/FTR-9"
        assert branch_ref_for("BUG-9") == "fix/BUG-9"
        assert branch_ref_for("TECH-9") == "tech/TECH-9"
        assert branch_ref_for("ARCH-9") == "arch/ARCH-9"
        assert branch_ref_for("GROWTH-9") == "growth/GROWTH-9"
        with pytest.raises(ValueError):
            branch_ref_for("XXX-9")

    def test_ec4_pushed_but_not_merged_falls_back(self, git_repo_with_remote):
        """EC-4: ветка на origin, но не предок develop → ancestry None, subject решает."""
        repo = git_repo_with_remote
        _spec_birth(repo, "BUG-11")
        _push_to_remote(repo)
        _git(repo, "checkout", "-q", "-b", "fix/BUG-11")
        _add_commit(repo, "src/y.py", "feat(managed): y")
        _git(repo, "push", "-q", "-u", "origin", "fix/BUG-11")
        _git(repo, "checkout", "-q", "develop")
        _git(repo, "fetch", "-q", "origin")

        assert find_merged_branch(str(repo), "BUG-11", ["src/y.py"]) is None
        assert find_implementation(str(repo), "BUG-11", ["src/y.py"]) == (None, "none")

    def test_ec5_squash_merge_falls_back_to_subject(self, git_repo_with_remote):
        """EC-5: ветки нет, но subject несёт id → ("<sha>", "subject")."""
        repo = git_repo_with_remote
        sha = _add_commit(repo, "src/z.py", "feat(FTR-9): squashed work")
        _push_to_remote(repo)
        _git(repo, "fetch", "-q", "origin")

        assert find_implementation(str(repo), "FTR-9", ["src/z.py"]) == (sha, "subject")

    def test_ec6_subspec_suffix_never_cross_matches(self, git_repo_with_remote):
        """EC-6: arch/ARCH-176a влита — ARCH-176 не должна засчитаться (devil DA-8)."""
        repo = git_repo_with_remote
        _spec_birth(repo, "ARCH-176a")
        _push_to_remote(repo)
        _ff_merge_branch(repo, "arch/ARCH-176a", ["src/sub.py"], "feat(managed): sub")

        assert branch_ref_for("ARCH-176a") == "arch/ARCH-176a"
        assert find_merged_branch(str(repo), "ARCH-176", ["src/sub.py"]) is None

    def test_ec8_git_failure_is_fail_closed(self, tmp_path):
        """EC-8: не-репозиторий → (None, "none"), исключение не выходит наружу."""
        broken = tmp_path / "notarepo"
        broken.mkdir()
        assert find_merged_branch(str(broken), "TECH-9", ["src/x.py"]) is None
        assert find_implementation(str(broken), "TECH-9", ["src/x.py"]) == (None, "none")
        assert fetch_branch(str(broken), "TECH-9") is False
```

   (`fetch_branch` добавить в тот же `from gate_ancestry import …`.)

2. Красный прогон — модуля ещё нет:

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220/scripts/vps/tests && \
  python3 -m pytest -q test_gate_logic.py -k Ancestry
```
   Ожидаемо: `ModuleNotFoundError: No module named 'gate_ancestry'` (collection error).

3. Создать `scripts/vps/gate_ancestry.py`:

```python
#!/usr/bin/env python3
"""
Module: gate_ancestry
Role: Branch-ancestry implementation gate (TECH-220) plus `find_implementation`,
      the single entry point all four gate call sites use.

The gate used to decide "this spec is implemented" from the *text* of a commit
subject on origin/develop. Nine of fifteen downstream projects write
`feat(managed): ...`, so 31 of 61 verdicts between 16-30.08 were false
`no_merged_implementation`. Git already knows the answer: autopilot is the only
thing that merges, it merges only from `<type>/<ID>`, only `--ff-only`, and only
after a green run (`.claude/skills/autopilot/finishing.md:51-61`). So
"origin/<type>/<ID> is an ancestor of origin/develop" IS the proof that the
finishing protocol ran.

Uses:
  - subprocess, logging, pathlib, sys: stdlib; every subprocess call is inside a
    function body (same discipline as gate_logic)
  - gate_logic: strip_bookkeeping_paths, find_implementation_commit

Used by:
  - callback_sync._decide_status
  - callback_dispatch._merge_confirmed
  - orchestrator_queue.reconcile_if_implemented / record_dispatch
  - gate-daemon._evaluate_project

FF-09 invariant: ZERO imports from callback, lifecycle, db, orchestrator.
gate_logic is the single exception and is itself stdlib-only and import-safe.

Import direction is one-way: gate_ancestry -> gate_logic, never the reverse.
gate_logic must NOT import this module: it sits at 398 of its 400 LOC budget and
a back-import would be a cycle.

The subject fallback calls `gate_logic.find_implementation_commit(...)` as a
module ATTRIBUTE, positionally, with exactly three arguments. Two dozen tests in
files this spec may not edit monkeypatch that attribute; binding the name at
import time or passing keywords turns every one of them into a silent no-op.
"""

import logging
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import gate_logic  # noqa: E402

log = logging.getLogger(__name__)

# L-derived-4: the same map lives as prose twice — the "Type mapping" table in
# .claude/skills/autopilot/worktree-setup.md:102-108 and the bash `case` in
# autopilot-git.md:52-58 — and the two disagree. Neither has a GROWTH row; the
# bash falls through to `task/`. GROWTH is decided here as `growth/`; if either
# prose copy ever grows a GROWTH row it must match this value.
_BRANCH_PREFIX = {
    "FTR": "feature",
    "BUG": "fix",
    "TECH": "tech",
    "ARCH": "arch",
    "GROWTH": "growth",
}

_GIT_TIMEOUT = 15


def _git(project_path: str, *args: str, timeout: int = _GIT_TIMEOUT) -> str | None:
    """Run one git command. Return stripped stdout, or None on ANY failure.

    Fail-closed by construction: every caller treats None as "no evidence",
    which routes to blocked, never to done.
    """
    try:
        r = subprocess.run(
            ["git", "-C", project_path, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("ANCESTRY: git %s failed in %s: %s", args[0], project_path, exc)
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def branch_ref_for(spec_id: str) -> str:
    """`BUG-9` -> `fix/BUG-9`. Raises ValueError on an unknown prefix."""
    prefix = spec_id.split("-")[0].upper()
    if prefix not in _BRANCH_PREFIX:
        raise ValueError(f"no branch prefix for spec id {spec_id!r}")
    return f"{_BRANCH_PREFIX[prefix]}/{spec_id}"


def fetch_branch(project_path: str, spec_id: str, timeout: int = 15) -> bool:
    """Refresh refs/remotes/origin/<type>/<ID>. Best-effort, like fetch_develop.

    Deliberately as narrow as gate_logic.fetch_develop: one exact refspec, never
    `--all`. A branch that does not exist on origin is a normal outcome, not an
    error — the caller falls back to the subject gate.
    """
    try:
        branch = branch_ref_for(spec_id)
    except ValueError:
        return False
    refspec = f"refs/heads/{branch}:refs/remotes/origin/{branch}"
    return _git(project_path, "fetch", "origin", refspec, "--quiet", timeout=timeout) is not None


def _base_for_diff(project_path: str, ref: str, tip: str, spec_id: str) -> str | None:
    """Lower bound for "what this branch introduced".

    Two shapes reach us. A `--no-ff` merge leaves develop with commits the branch
    never had, so `merge-base` IS the fork point. A `--ff-only` merge — what
    finishing.md:51-54 actually does, after rebasing develop — replays develop
    onto the branch tip, so `merge-base(ref, origin/develop) == ref` and a diff
    against it is always empty. For that case the spec's own birth commit is the
    usable bound: Spark commits `ai/features/<ID>-*.md` to develop before the
    branch is ever cut, so the oldest commit reachable from the tip that ADDS the
    spec file always sits on the develop side of the fork.

    ponytail: the ff bound is wider than the true fork point — another spec
    landing on develop inside that window and touching one of THIS spec's allowed
    files would count as evidence. Ceiling accepted because a branch literally
    named <type>/<ID> still has to have been merged to get here. Upgrade path: a
    merge trailer recording the fork sha.
    """
    base = _git(project_path, "merge-base", ref, "origin/develop")
    if base is None:
        return None
    if base != tip:
        return base
    birth = _git(
        project_path,
        "log",
        tip,
        "--reverse",
        "--diff-filter=A",
        "--pretty=%H",
        "--",
        f"ai/features/{spec_id}-*.md",
    )
    if not birth:
        log.info("ANCESTRY: %s — ff-merged branch but no spec birth commit; failing closed", spec_id)
        return None
    return birth.splitlines()[0].strip()


def find_merged_branch(project_path: str, spec_id: str, allowed_files: list[str]) -> str | None:
    """Tip sha of origin/<type>/<ID> iff that branch is merged into
    origin/develop AND carried at least one non-bookkeeping allowed file.

    Exact ref name, never a glob: ARCH-176 must not match ARCH-176a (devil DA-8).
    """
    if not spec_id or not allowed_files:
        return None
    impl_files = gate_logic.strip_bookkeeping_paths(allowed_files)
    if not impl_files:
        return None
    try:
        branch = branch_ref_for(spec_id)
    except ValueError:
        return None
    ref = f"refs/remotes/origin/{branch}"
    tip = _git(project_path, "rev-parse", "--verify", "--quiet", ref)
    if not tip:
        return None
    # rc 0 = ancestor, rc 1 = not, anything else = error. _git collapses the
    # last two into None, which is exactly the fail-closed reading we want.
    if _git(project_path, "merge-base", "--is-ancestor", ref, "origin/develop") is None:
        return None
    base = _base_for_diff(project_path, ref, tip, spec_id)
    if base is None:
        return None
    changed = _git(project_path, "diff", "--name-only", base, tip)
    if changed is None:
        return None
    # Same normalisation gate_logic.strip_bookkeeping_paths applies (backslash → slash,
    # leading ./ dropped), so the two sides of the intersection are comparable.
    touched = {ln.strip().replace("\\", "/") for ln in changed.splitlines() if ln.strip()}
    wanted = {p.strip().lstrip("./").replace("\\", "/") for p in impl_files}
    if not touched & wanted:
        log.info("ANCESTRY: %s — %s is merged but touched no impl file", spec_id, branch)
        return None
    log.info("ANCESTRY: %s — %s merged into origin/develop at %s", spec_id, branch, tip[:12])
    return tip


def find_implementation(
    project_path: str,
    spec_id: str,
    allowed_files: list[str],
) -> tuple[str | None, str]:
    """THE gate. ("<sha>", "ancestry") | ("<sha>", "subject") | (None, "none").

    Ancestry first — git knows who merged what. The subject regex is the
    deprecated second pass, kept until 30 days of `gate_via` telemetry show it
    never fires; then it and match_subject go in their own TECH.
    """
    sha = find_merged_branch(project_path, spec_id, allowed_files)
    if sha:
        return sha, "ancestry"
    # Module attribute, positional, three args — see the module docstring.
    sha = gate_logic.find_implementation_commit(project_path, spec_id, allowed_files)
    if sha:
        return sha, "subject"
    return None, "none"
```

4. Зелёный прогон + инварианты:

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220/scripts/vps/tests && \
  python3 -m pytest -q test_gate_logic.py test_gate_logic_subject.py
```
   Ожидаемо: `0 failed`, 36 subject-кейсов зелёные без единой правки.

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220 && \
  grep -nE "^(import|from) (callback|lifecycle|db|orchestrator)" scripts/vps/gate_ancestry.py ; \
  grep -c "" scripts/vps/gate_ancestry.py ; \
  git diff --stat scripts/vps/gate_logic.py
```
   Ожидаемо: grep пуст (rc 1), счётчик < 300, diff по `gate_logic.py` пуст.

**Acceptance:** EC-1..EC-6, EC-8 зелёные (AV-F1 подмножество) · EC-11-половина:
`test_gate_logic_subject.py` без правок зелёный · FF-09 (AV-S2) · `gate_ancestry.py` ≤ 300 LOC ·
`gate_logic.py` не изменён (DoD Technical).

---

### Task 2: callback-контур — `_decide_status` и `_merge_confirmed` через `find_implementation`

**Type:** code
**Files:**
- Modify: `scripts/vps/callback_sync.py:34-38, 43-77, 177-220, 275-349`
- Modify: `scripts/vps/callback_dispatch.py:160-190` (+ импорт)

**Context:** вердикт после прогона (Step 4 + grace-retry TECH-197) и QA-фолбэк при потерянном
`task_status` (TECH-207) обязаны давать один и тот же вердикт из одного источника, иначе
возвращается дрейф двух гейтов, который убрала TECH-210. Здесь же рождается метрика `gate_via` —
дата смерти subject-регекса.

**Steps:**

1. `callback_sync.py`, блок импортов (после `import gate_logic  # noqa: E402`, строка 37):
   добавить `import gate_ancestry  # noqa: E402` (алфавитный порядок: перед `gate_logic`).

2. `_Audit` (строки 43-77) — новое поле + протаскивание в каждую строку аудита:

```python
    started_at: str | None = None
    gate_via: str = "none"

    def emit(self, target_out: str, reason: str, **extra: object) -> None:
        callback_scope._emit_audit(
            self.project_id,
            self.spec_id,
            self.pueue_id,
            self.target_in,
            target_out,
            reason,
            self.allowed_count,
            self.code_loc,
            self.test_loc,
            self.code_commits,
            self.started_at,
            self.start_wall,
            gate_via=self.gate_via,
            **extra,
        )
```
   `_emit_audit` уже принимает `**extra` и кладёт его в запись (`callback_scope.py:90,109-110`) —
   менять его не нужно и нельзя (файла нет в Allowed Files).

3. `_decide_status` (строки 177-220) — возвращает тройку, ancestry первой:

```python
def _decide_status(
    project_path: str,
    spec_id: str,
    project_id: str,
    allowed: list[str] | None,
    *,
    autopilot_signaled: bool,
) -> tuple[str, str, str]:
    """Rule 1: done iff origin/develop carries this spec's implementation.

    Returns (new_status, reason, gate_via). TECH-220: the branch
    `<type>/<ID>` being an ancestor of origin/develop is the primary evidence;
    the subject regex is the deprecated fallback. Grace-retry (TECH-197) covers
    the network race where the push landed but origin has not caught up yet; it
    runs only when the autopilot did NOT deliberately hold the spec.
    """
    if not allowed:
        reason = "missing_allowed_files" if allowed is None else "empty_allowed_files"
        log.warning("GATE: %s — %s, blocking", spec_id, reason)
        return "blocked", reason, "none"

    # Rule 4: fetch before evaluating the gate. Both refs, both best-effort.
    gate_logic.fetch_develop(project_path)
    gate_ancestry.fetch_branch(project_path, spec_id)
    sha, via = gate_ancestry.find_implementation(project_path, spec_id, allowed)
    if sha:
        return "done", "", via

    if autopilot_signaled:
        # Autopilot EXPLICITLY signaled blocked/needs_review and the gate finds
        # no merged implementation — the expected outcome of a deliberate
        # self-block (e.g. unmet dependency), NOT a gate anomaly. Surface the
        # real cause instead of the misleading force-done hint.
        return "blocked", "autopilot_signaled_blocked", "none"

    for attempt in range(1, 4):  # up to 3 retries
        time.sleep(5)
        gate_logic.fetch_develop(project_path)
        gate_ancestry.fetch_branch(project_path, spec_id)
        sha, via = gate_ancestry.find_implementation(project_path, spec_id, allowed)
        if sha:
            log.info("GRACE_RETRY: %s — resolved on attempt %d via %s", spec_id, attempt, via)
            return "done", "", via

    return (
        "blocked",
        (
            f"no_merged_implementation — if implementation IS real, run: "
            f"python3 scripts/vps/spec_operator.py force-done {project_id} {spec_id} "
            f"'gate regex bug, verified manually' --by=operator"
        ),
        "none",
    )
```

4. `verify_status_sync` (строка 315) — распаковка тройки, порядок шагов НЕ меняется
   (`_push_local_develop` остаётся Step 3, до гейта — EC-9):

```python
    new_status, reason, audit.gate_via = _decide_status(
        project_path, spec_id, project_id, allowed, autopilot_signaled=autopilot_signaled
    )
```
   Блок ниже (строки 318-321, `autopilot_signaled and target == "blocked" and new_status == "done"`
   → `blocked`/`autopilot_signaled_blocked`) остаётся дословно: самоблок перебивает любой `via`
   (EC-7, devil DA-11).

5. `callback_dispatch.py`: добавить `import gate_ancestry  # noqa: E402` рядом с `gate_logic`;
   в `_merge_confirmed` заменить строки 172-173:

```python
        gate_logic.fetch_develop(project_path)
        gate_ancestry.fetch_branch(project_path, spec_id)
        sha, via = gate_ancestry.find_implementation(project_path, spec_id, allowed)
        if sha:
            log.info(
                "QA_DISPATCH_MERGE_FALLBACK: task_status=%r but impl confirmed "
                "merged on origin/develop for %s (gate_via=%s) — dispatching QA+Reflect",
                task_status,
                spec_id,
                via,
            )
            return True
```
   `except Exception → False` внизу не трогать: «никогда не диспатчить на сомнении».

6. Прогон:

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220 && \
  python3 -m pytest -q scripts/vps/tests/test_callback.py \
    tests/integration/test_callback_already_merged.py \
    tests/integration/test_callback_feature_branch.py \
    tests/integration/test_callback_blocked_no_dispatch.py \
    tests/integration/test_callback_status_sync.py \
    tests/integration/test_callback_no_impl_demote.py
```
   Ожидаемо: `0 failed`. Красное здесь = патч `gate_logic.find_implementation_commit`
   перестал доезжать → вернуться к разделу «Не сломать 24 патч-сайта» Task 1.

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220 && \
  CALLBACK_AUDIT_LOG=/tmp/tech220-audit.jsonl python3 - <<'PY'
import sys; sys.path.insert(0, "scripts/vps")
import callback_sync
a = callback_sync._Audit("p", "TECH-1", None, "done", 0.0)
a.gate_via = "ancestry"; a.emit("done", "ok")
PY
  grep -c '"gate_via": "ancestry"' /tmp/tech220-audit.jsonl
```
   Ожидаемо: `1`.

**Acceptance:** EC-7 (самоблок перебивает — покрывается Task 4) · EC-9 (порядок
`_push_local_develop` → гейт не изменён; проверяется чтением диффа: строки 310-317 сохраняют
последовательность) · EC-12-половина · `gate_via` в каждой audit-строке (DoD Functional) ·
`grep -rn "gate_logic.find_implementation_commit(" scripts/vps/*.py` → только
`gate_ancestry.py`.

---

### Task 3: orchestrator-контур — reconcile, `record_dispatch`, shadow-вердикт

**Type:** code
**Files:**
- Modify: `scripts/vps/orchestrator_queue.py:29-32, 255-296, 299-330`
- Modify: `scripts/vps/gate-daemon.py:42-44, 160-275`

**Context:** pre-dispatch «уже на develop» и shadow-метрика обязаны читать тот же вердикт
(EC-12). Плюс devil DA-10: `record_dispatch` пишет в `task_log.branch` литерал
`feature/{spec_id}` для ВСЕХ типов — для ¾ спек это выдумка.

**Steps:**

1. `orchestrator_queue.py` импорты (строки 29-32): добавить `import gate_ancestry  # noqa: E402`
   перед `import gate_logic`.

2. `reconcile_if_implemented`, строки 275-276 и лог ниже:

```python
    gate_logic.fetch_develop(project_dir)
    gate_ancestry.fetch_branch(project_dir, spec_id)
    impl_sha, via = gate_ancestry.find_implementation(project_dir, spec_id, allowed_files)
    if not impl_sha:
        return False
```
   и в `log.info` добавить `gate_via`:

```python
        log.info(
            "reconciled: %s already implemented on develop (%s, gate_via=%s) — "
            "marked done, no dispatch",
            spec_id,
            impl_sha[:12],
            via,
        )
```
   **`reason=f"already_implemented_on_develop:{impl_sha[:12]}"` не менять** —
   `test_orchestrator.py:955` ассертит подстроку, файл не редактируется.
   Ранний `if not allowed_files: return False` (строки 272-274) остаётся ПЕРЕД фетчем:
   `test_orchestrator.py:1042` требует `mock_find.assert_not_called()`.

3. `record_dispatch`, строка 328 — реальный префикс вместо литерала:

```python
    try:
        branch = gate_ancestry.branch_ref_for(spec_id)
    except ValueError:
        branch = f"task/{spec_id}"  # mirrors the bash fallback in autopilot-git.md:57
    db.try_acquire_slot(project_id, provider, pueue_id)
    db.log_task(
        project_id,
        task_label,
        "autopilot",
        "running",
        pueue_id,
        branch=branch,
    )
```

4. `gate-daemon.py` импорты (строки 42-44): добавить `import gate_ancestry  # noqa: E402`
   перед `import gate_logic`. Строку 171 (`gate_logic.fetch_develop(project_path, timeout=15)`)
   не трогать — она про develop и остаётся до цикла по спекам.

5. `_evaluate_project`, строки 252-272 — вердикт + новое поле JSONL:

```python
        gate_ancestry.fetch_branch(project_path, spec_id)
        sha, via = gate_ancestry.find_implementation(project_path, spec_id, allowed)
        if sha:
            verdict = "done"
            reason = f"{via}_matched:{sha[:12]}"
        else:
            verdict = "in_progress"
            reason = "no_matching_commit"

        _write_shadow(
            {
                "cycle_start_ts": cycle_start_ts,
                "as_of_ts": as_of_ts,
                "project": project_id,
                "spec_id": spec_id,
                "gate_verdict": verdict,
                "gate_reason": reason,
                "gate_via": via,
                "matching_commit_sha": sha,
                "allowed_files_count": len(allowed),
                "shadow_only": True,
            }
        )
```
   `fetch_branch` ставить ПОСЛЕ ветки `if sha_unchanged: … continue` (строки 199-214), иначе
   SHA-кеш перестанет экономить сеть и `test_gate_daemon.py::T05` покажет лишние вызовы.
   Три ранних `_write_shadow` (skipped / spec_file_not_found / missing_allowed_files) получают
   `"gate_via": "none"` — форма записи одна на все выходы.

6. Прогон:

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220 && \
  python3 -m pytest -q scripts/vps/tests/test_orchestrator.py \
    scripts/vps/tests/test_orchestrator_in_progress.py \
    scripts/vps/tests/test_gate_daemon.py
```
   Ожидаемо: `0 failed` (в частности T05 sha-cache и `mock_find.assert_not_called()`).

**Acceptance:** EC-10 (`task_log.branch == "tech/TECH-9"`, проверяется тестом Task 4) ·
EC-12-половина: все четыре точки читают `gate_ancestry.find_implementation` —
`grep -rn "find_implementation(" scripts/vps/*.py` даёт ровно 5 строк (определение +
4 вызова) · shadow-JSONL несёт `gate_via`.

---

### Task 4: EC-серия через публичный контракт callback

**Type:** test
**Files:**
- Modify: `tests/unit/test_callback_branch_awareness.py` (append; существующие EC-1..EC-6 не трогать)
- Modify: `tests/unit/test_callback_implementation_guard.py` (append; EC-1..EC-9 не трогать)

**Context:** Task 1 проверяет чистую функцию. Здесь проверяется, что вердикт доезжает до
`ai/lifecycle/*.yaml` через публичный `callback.verify_status_sync`, и что самоблок его
перебивает. Оба файла уже нумеруют свои тесты `ec1..ec9` в собственной шкале — новые
называть `test_tech220_*`, чтобы не путать со шкалой спеки.

**Steps:**

1. `tests/unit/test_callback_branch_awareness.py` — дописать в конец
   (переиспользуя `repo_with_remote`, `_git`, `_commit_on`):

```python
# --- TECH-220: ancestry verdict reaches lifecycle ----------------------------

import gate_ancestry  # noqa: E402


def _merge_ff(repo, branch: str, rel: str, msg: str) -> str:
    _git(repo, "checkout", "-q", "-b", branch)
    _commit_on(repo, rel, "y=1\n", msg)
    _git(repo, "push", "-q", "-u", "origin", branch)
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "--ff-only", "-q", branch)
    _git(repo, "push", "-q", "origin", "develop")
    _git(repo, "fetch", "-q", "origin")
    return _git(repo, "rev-parse", branch).stdout.strip()


def test_tech220_ancestry_beats_unreadable_subject(repo_with_remote):
    """EC-1 через публичный контракт: subject `feat(managed): …` невидим
    старому гейту, ancestry находит ветку."""
    repo = repo_with_remote
    _commit_on(repo, "ai/features/TECH-170-2026-08-30-x.md", "s\n", "docs(TECH-170): spec")
    _git(repo, "push", "-q", "origin", "develop")
    tip = _merge_ff(repo, "tech/TECH-170", "src/x.py", "feat(managed): real work")

    assert gate_logic.find_implementation_commit(str(repo), "TECH-170", ["src/x.py"]) is None
    assert gate_ancestry.find_implementation(str(repo), "TECH-170", ["src/x.py"]) == (
        tip,
        "ancestry",
    )


def test_tech220_record_dispatch_branch_uses_real_prefix():
    """EC-10 (devil DA-10): task_log.branch перестаёт быть литералом feature/."""
    assert gate_ancestry.branch_ref_for("TECH-9") == "tech/TECH-9"
    assert gate_ancestry.branch_ref_for("BUG-9") == "fix/BUG-9"
    assert gate_ancestry.branch_ref_for("ARCH-9") == "arch/ARCH-9"
    assert gate_ancestry.branch_ref_for("GROWTH-9") == "growth/GROWTH-9"
```

2. `tests/unit/test_callback_implementation_guard.py` — дописать в конец
   (переиспользуя `dev_repo`, `_git`, `_commit_to`):

```python
# --- TECH-220: self-block outranks a positive ancestry verdict ---------------

import gate_ancestry  # noqa: E402
import lifecycle  # noqa: E402


def test_tech220_self_block_overrides_ancestry(dev_repo, monkeypatch):
    """EC-7 (devil DA-11): ветка влита, но автопилот сам сказал blocked."""
    spec_id = "TECH-220T"
    _commit_to(dev_repo, f"ai/features/{spec_id}-2026-08-30-x.md", "s\n", f"docs({spec_id}): spec")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "checkout", "-q", "-b", f"tech/{spec_id}")
    _commit_to(dev_repo, "src/foo.py", "x=1\n", "feat(managed): impl")
    _git(dev_repo, "push", "-q", "-u", "origin", f"tech/{spec_id}")
    _git(dev_repo, "checkout", "-q", "develop")
    _git(dev_repo, "merge", "--ff-only", "-q", f"tech/{spec_id}")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin")
    lifecycle.write_lifecycle(str(dev_repo), spec_id, "in_progress")

    # Ancestry сама по себе положительна
    assert gate_ancestry.find_merged_branch(str(dev_repo), spec_id, ["src/foo.py"]) is not None

    callback.verify_status_sync(
        str(dev_repo), spec_id, target="blocked", autopilot_signaled=True
    )
    data = lifecycle.read_lifecycle(str(dev_repo), spec_id)
    assert data["status"] == "blocked"
    assert data.get("blocked_reason") == "autopilot_signaled_blocked"
```
   (спека `ai/features/{spec_id}-…md` должна содержать `## Allowed Files` с `` - `src/foo.py` ``,
   иначе гейт уйдёт в `missing_allowed_files` и тест проверит не то — записать её тем же
   `_commit_to` с телом
   `"# TECH-220T\n\n## Allowed Files\n\n- `src/foo.py`\n"`.)

3. Прогон полного корневого набора (AV-F2):

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220 && \
  python3 -m pytest -q tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/
```
   Ожидаемо: `0 failed`, `tests/regression/` и `tests/contracts/` без единой правки.

**Acceptance:** EC-7, EC-10 зелёные · EC-11 полностью (`tests/regression/`,
`test_gate_logic_subject.py`, `test_callback_implementation_guard.py::test_ec4..ec9` зелёные
без правок) · EC-12 (один вердикт на всех точках).

---

### Task 5: `status-model.md` §7 — гейт по предку ветки

**Type:** docs
**Files:**
- Modify: `docs/orchestrator/status-model.md:182-211` (подраздел
  «Implementation guard (`_is_done_on_develop`)» внутри `## 7. Контракт callback`)

**Context:** подраздел описывает гейт именем функции, удалённой в TECH-210
(`_is_done_on_develop`), и по строкам `callback.py:797-838`, которых нет после
TECH-216-сплита. Переписывается целиком.

**Steps:**

1. Заменить заголовок и первый абзац:

```markdown
### <a name="guard"></a>Implementation guard (`gate_ancestry.find_implementation`)

**Текущий гейт (Rule 1, TECH-220):** `done` ⟺ ветка `<type>/<ID>` — предок
`origin/develop` И принесла ≥1 не-bookkeeping allowed-файл. Одна функция,
`gate_ancestry.find_implementation`, во всех четырёх точках вызова:
`callback_sync._decide_status`, `callback_dispatch._merge_confirmed`,
`orchestrator_queue.reconcile_if_implemented`, `gate-daemon._evaluate_project`.
**Нет activity-окна, нет `--all`, нет auto-close.** Fail-closed: любая ошибка git → `None`
→ `blocked`, никогда не `done`.
```

2. Добавить блок про две ступени и метрику (после первого абзаца):

```markdown
- **Ступень 1 — ancestry (primary).** `git merge-base --is-ancestor
  refs/remotes/origin/<type>/<ID> origin/develop`. Мержит в develop только автопилот,
  только из ветки `<type>/<ID>`, только `--ff-only` после зелёного прогона
  (`skills/autopilot/finishing.md`) — значит предок = протокол завершения прошёл.
  Карта префиксов: FTR→`feature/`, BUG→`fix/`, TECH→`tech/`, ARCH→`arch/`,
  GROWTH→`growth/` (`gate_ancestry._BRANCH_PREFIX` — единственная машинная копия;
  две прозаические живут в `worktree-setup.md` и `autopilot-git.md` и между собой расходятся).
  Имя ref точное, без glob: `ARCH-176` никогда не матчит `ARCH-176a`.
- **Bookkeeping-фильтр.** Диапазон, который принесла ветка, пересекается с
  `strip_bookkeeping_paths(allowed)`; пусто → не evidence. Нижняя граница диапазона:
  `merge-base` при no-ff мерже, birth-коммит спеки (`ai/features/<ID>-*.md`) при ff-only,
  где `merge-base == tip` и диффа иначе просто нет.
- **Ступень 2 — subject (deprecated).** Старый `gate_logic.find_implementation_commit` +
  `match_subject` без изменений: 12 форм, два прохода `git log` (обычный + `--first-parent`).
  Срабатывает на squash-мерже и на ветке, которой нет на origin.
- **Метрика и дата смерти.** Каждый вердикт пишет `gate_via` = `ancestry` | `subject` |
  `none`: в `callback-audit.jsonl` (`_Audit.gate_via`, поле есть в КАЖДОЙ строке) и в
  shadow-JSONL gate-daemon. Когда `subject` не срабатывает 30 дней — регекс удаляется
  отдельной TECH.
```

3. Сохранить без изменений врезку `> ⚠️ Это редизайн поверх TECH-170/TECH-176 …`,
   буллет `_parse_allowed_files` и буллет `degrade-closed → blocked` (они по-прежнему верны);
   в буллете `_subject_implements` заменить имя на `gate_logic.match_subject` и добавить
   «— deprecated, ступень 2».

4. Проверка:

```bash
cd /home/dld/projects/dld/.worktrees/TECH-220 && \
  grep -n "_is_done_on_develop\|callback.py:797-838" docs/orchestrator/status-model.md
```
   Ожидаемо: пусто (rc 1) в границах §7.

**Acceptance:** §7 описывает ancestry как primary и subject как deprecated с метрикой
`gate_via` · имя удалённой функции `_is_done_on_develop` из §7 исчезло.

---

### Execution Order

```
Task 1 ──► Task 2 ──► Task 4 ──► Task 5
       └─► Task 3 ──┘
```

- **Task 1 блокирует всё:** ни одна точка вызова не может импортировать модуль, которого нет.
- **Task 2 и Task 3 независимы друг от друга** (разные файлы, общая зависимость — только Task 1),
  но обе обязаны попасть в один прогон: Size спеки требует, чтобы прогон не завершался с
  частично перенацеленными точками.
- **Task 4 после 2 и 3:** проверяет вердикт через публичный `verify_status_sync` (Task 2) и
  `branch_ref_for` в `record_dispatch` (Task 3).
- **Task 5 последняя:** документирует то, что уже работает.

### Что осталось за пределами Allowed Files (для follow-up, не для этого прогона)

- `.github/workflows/test.yml` перечисляет `--cov=` шесть callback-модулей; `gate_ancestry`
  туда не попадёт. Порога 54 % это не роняет (модуль не в знаменателе), но покрытие нового
  кода CI не измерит.
- `.claude/skills/autopilot/{worktree-setup,autopilot-git}.md` — две прозаические копии карты
  префиксов без строки GROWTH и с `task/` фолбэком в bash. `gate_ancestry._BRANCH_PREFIX`
  становится третьей копией и единственной машинной; свести их — отдельная TECH.

---

## Drift Log

**Итог: `light` — исправлено планировщиком, эскалация не требуется.**

| # | Что проверялось | Состояние | Действие |
|---|---|---|---|
| 1 | `callback_sync.py:198-212` (`fetch_develop` + 2× `find_implementation_commit`) | точно | — |
| 2 | `callback_dispatch.py:172-173` (`_merge_confirmed`) | точно | — |
| 3 | `orchestrator_queue.py:275-276` (`reconcile_if_implemented`) | точно | — |
| 4 | `orchestrator_queue.py:328` (`branch=f"feature/{spec_id}"`) | точно | — |
| 5 | `gate-daemon.py:171,252` | точно | — |
| 6 | `docs/orchestrator/status-model.md:182-211` = §7 guard | точно | — |
| 7 | `gate_logic.py` = 398 LOC; `match_subject`/`_SPEC_ID_RE`/`find_implementation_commit` на месте | точно | — |
| 8 | `template/scripts/vps/` | не существует | sync-задача не нужна (подтверждает Step 4 спеки) |
| 9 | Тесты, мокающие гейт | **дрейф: 8 файлов / 24 сайта вместо «test_orchestrator*.py»** | строка Impact Tree Step 1 исправлена; контракт вызова фолбэка вынесен в Task 1 отдельным разделом |
| 10 | Дизайн: `find_implementation` в `gate_logic` | **не влезает: 398 + ~20 > 400 LOC** | функция переехала в `gate_ancestry`; `gate_logic.py` в этой спеке не меняется |
| 11 | Дизайн: `base = git merge-base <ref> origin/develop` для диффа | **неработоспособно при ff-only мерже (`merge-base == ref` → дифф всегда пуст)** | добавлен `_base_for_diff`: birth-коммит спеки как нижняя граница для ff-случая, `merge-base` для no-ff |
| 12 | «Ветка удалена после merge (§0a sweep)» | **неточно: свип делает только `git branch -d`, `push origin --delete` в дереве промптов отсутствует** | Design дополнен: `origin/<type>/<ID>` переживает merge, фолбэк по удалённой ветке — редкий случай, а не основной |
| 13 | `scripts/vps/tests/test_gate_logic.py` = 598 LOC при лимите 600 | **ancestry-серия (101 строка) даёт 700 — hard-block `pre-review-check.py`** | ancestry-тесты вынесены в новый `scripts/vps/tests/test_gate_ancestry.py`; существующий файл не трогается вовсе |
| 14 | Allowed Files: `gate_logic.py` (modify), `test_gate_logic.py` (modify) | **оба стали лишними после п.10 и п.13** | заменены на `scripts/vps/tests/test_gate_ancestry.py` (NEW); allowlist сужен, а не расширен по существу |
| 15 | `test_claude_runner_timeout.py::test_push_local_is_best_effort_not_gate` | **красный: ассертит строку `gate_logic.find_implementation_commit(` в исходнике `callback_sync.py`** | инвариант (push-local — не гейт, гейт бьёт по origin) сохранён, переехало только имя точки входа — ровно как при TECH-216 (комментарий на строке 221). Ассерт обновлён на `gate_ancestry.find_implementation(` + добавлена проверка, что ancestry тоже ходит в `origin/develop`; файл добавлен в Allowed Files |

Пункты 10-12 — дефекты дизайна спеки, найденные при сверке с кодом, а не дрейф кода под спекой.
Ни один не меняет выбранный Approach 1 и ни один не выходит за Allowed Files, поэтому
исправлены здесь, а не через `/council`. Пункт 11 — единственный блокирующий: без него
ancestry не сработала бы ни разу, а гейт молча остался бы subject-only при зелёных тестах,
если бы тесты EC-1/EC-2 писали ветку через `--no-ff`.

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Автопилот мержит `<type>/<ID>` `--ff-only` в develop и пушит | — | existing (`finishing.md:51-61`) |
| 2 | Callback фетчит develop и ветку | Task 1 (`fetch_branch`), Task 2, Task 3 | ✓ |
| 3 | Ancestry + пересечение с allowlist без bookkeeping | Task 1 (`find_merged_branch`, `_base_for_diff`) | ✓ |
| 4 | Фолбэк subject при отсутствии ветки / squash | Task 1 (`find_implementation`) | ✓ |
| 5 | Самоблок перебивает | Task 2 (порядок сохранён), Task 4 (EC-7) | ✓ |
| 6 | Вердикт и `gate_via` в lifecycle + audit | Task 2 (`_Audit.gate_via`), Task 3 (shadow JSONL) | ✓ |
| 7 | Pre-dispatch reconcile и QA-фолбэк — тот же вердикт | Task 2 (`_merge_confirmed`), Task 3 (`reconcile_if_implemented`) | ✓ |
| 8 | `task_log.branch` = реальный префикс | Task 3 (`record_dispatch`), Task 4 (EC-10) | ✓ |

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
1. EC-1, EC-2, EC-3 — красные (`ModuleNotFoundError: gate_ancestry`) → Task 1
2. EC-4..EC-6, EC-8 — граничные ancestry → Task 1
3. EC-9, EC-12 — точки вызова → Task 2, Task 3
4. EC-7, EC-10, EC-11 — самоблок, префикс ветки, регрессия → Task 4
5. EC-13 — живой прогон на VPS (AV-F4), после мержа

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Модули импортируются | `PYTHONPATH=scripts/vps python3 -c "import gate_ancestry, gate_logic, callback, callback_sync, callback_dispatch, orchestrator_queue"` | exit 0 | 15s |
| AV-S2 | FF-09 | `grep -nE "^(import\|from) (callback\|lifecycle\|db\|orchestrator)" scripts/vps/gate_ancestry.py` | пусто (rc 1) | 5s |
| AV-S3 | `gate_logic.py` не тронут | `git diff --stat scripts/vps/gate_logic.py` | пусто | 5s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Гейт-тесты | — | `cd scripts/vps/tests && python3 -m pytest -q -k "gate_logic or callback or orchestrator"` | 0 failed |
| AV-F2 | Корневые | — | `python3 -m pytest -q tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/` | 0 failed |
| AV-F3 | Coverage-гейт | — | команда из `.github/workflows/test.yml` | ≥54 % |
| AV-F4 | Живой callback на VPS | VPS, спека со влитой веткой | EC-13 | `gate_via=ancestry` в `callback-audit.jsonl` |

### Verify Command

```bash
PYTHONPATH=scripts/vps python3 -c "import gate_ancestry, gate_logic, callback, callback_sync, callback_dispatch, orchestrator_queue"
cd scripts/vps/tests && python3 -m pytest -q -k "gate_logic or callback or orchestrator" && cd ../../..
python3 -m pytest -q tests/unit/test_callback_*.py tests/integration/test_callback_*.py tests/regression/
git diff --stat scripts/vps/gate_logic.py   # must be empty — gate_logic is untouched
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `gate_ancestry.find_implementation` — единственный вход гейта во всех четырёх точках
      (`grep -rn "find_implementation(" scripts/vps/*.py` → 5 строк: 1 определение + 4 вызова)
- [ ] Карта префиксов одной функцией (`branch_ref_for`), GROWTH определён как `growth/`
- [ ] `gate_via` в каждой audit-строке callback и в каждой строке shadow-JSONL
- [ ] `record_dispatch` пишет реальный префикс ветки, а не литерал `feature/`

### Tests
- [ ] EC-1..EC-13 проходят
- [ ] `tests/regression/`, `test_gate_logic_subject.py` зелёные **без правок**

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-S3, AV-F1..F3 локально; AV-F4 на VPS

### Technical
- [ ] `scripts/vps/gate_logic.py` не изменён ни на байт (следствие: `match_subject`,
      `find_implementation_commit`, `_SPEC_ID_RE` целы)
- [ ] Subject-фолбэк зовётся как `gate_logic.find_implementation_commit(a, b, c)` —
      атрибут модуля, позиционно, 3 аргумента (24 патч-сайта вне Allowed Files)
- [ ] `gate_ancestry.py` ≤ 300 LOC, все прочие файлы ≤ 400 LOC
- [ ] Rule 7 и «origin/develop-only» (`test_no_local_develop_gate_path`) соблюдены

---

## Autopilot Log

### Task 1/5: gate_ancestry.py — ancestry-гейт + единая точка входа — 2026-08-30 14:40
- Coder: completed (2 files: scripts/vps/gate_ancestry.py NEW 212 LOC, scripts/vps/tests/test_gate_ancestry.py NEW 197 LOC)
- Tester: passed (7/7 ancestry + 59 существующих gate_logic зелёные; ruff format поправлен)
- Deploy: skipped (no migrations)
- Spec compliance: matches — `_BRANCH_PREFIX` с GROWTH :57-63, `branch_ref_for` ValueError :90-95, `fetch_branch` :98-110, `_base_for_diff` :113-151, `find_merged_branch` :154-192, `find_implementation` :194-212; `gate_logic.py` diff = 0 строк
- Code Quality Reviewer: approved (0 blocking, 1 advisory — dependencies.md без записи о новом модуле)
- Local Verify: pass (AV-S2 FF-09 пусто, LOC 212 ≤ 400)
- Commit: dd90d02c
- **Отклонение от плана:** ancestry-серия ушла в новый `test_gate_ancestry.py`, а не в `test_gate_logic.py` — тот 598 LOC из 600, дописать 101 строку было некуда (Drift Log п. 13-14). Кодер отказался сам и эскалировал, allowlist сужен.

### Task 2/5 + 3/5: четыре точки вызова + gate_via — 2026-08-30 15:10
- Coder: completed (5 files: callback_sync.py, callback_dispatch.py, orchestrator_queue.py, gate-daemon.py, tests/test_claude_runner_timeout.py) — два кодера параллельно по непересекающимся контурам
- Tester: passed (scripts/vps/tests 636 passed / 1 known pre-existing fail; tests/ 259 passed 1 skipped)
- Deploy: skipped (no migrations)
- Spec compliance: matches — все 4 точки через `gate_ancestry.find_implementation`; `fetch_develop` сохранён на каждой; `_push_local_develop` до гейта (verify_status_sync:330 → _decide_status:334); самоблок перебивает (:339-340); `_Audit.gate_via` (:63,:79,:336); `record_dispatch` через `branch_ref_for` (:326); `already_implemented_on_develop` сохранён
- Code Quality Reviewer: approved (0 blocking, 2 advisory — gate-daemon.py 398/400 LOC; 4 pre-existing bare-except, идентичны на merge-base)
- Local Verify: pass (grep `find_implementation_commit(` → единственный вызов = фолбэк в gate_ancestry.py:209)
- Commit: 18831c93
- **Отклонение от плана:** `test_claude_runner_timeout.py::test_push_local_is_best_effort_not_gate` ассертил имя точки входа строкой в исходнике → красный. Инвариант сохранён, обновлено имя (как при TECH-216), добавлен `test_ancestry_gate_resolves_against_origin`. Файл внесён в allowlist (Drift Log п. 15).

### Task 4/5: EC-серия через публичный контракт — 2026-08-30 15:35
- Coder: completed (2 files: tests/unit/test_callback_branch_awareness.py 189 LOC, tests/unit/test_callback_implementation_guard.py 332 LOC)
- Tester: passed (140 passed — было 136 + 4 новых; tests/regression и tests/contracts не тронуты)
- Spec compliance: matches — EC-7 самоблок поверх ancestry, EC-10 префикс, EC-11 регрессия, EC-12 один вердикт на всех четырёх точках через реальный git-репо, gate_via в audit-JSONL
- Code Quality Reviewer: approved (pre-review-check PASSED, LOC 189/332 ≤ 600, ruff clean)
- Commit: abce7693

### Task 5/5: status-model.md §7 — 2026-08-30 15:45
- Coder: completed (1 file: docs/orchestrator/status-model.md)
- Tester: skipped (docs) · check-prompt-integrity rc=0
- Spec compliance: matches — §7 = ancestry primary / subject deprecated с метрикой `gate_via`; якорь `#guard` сохранён; §9 инвариант 6 приведён в соответствие
- Code Quality Reviewer: approved
- Commit: 3f20db7b

### PHASE 3 — 2026-08-30 15:55
- Final test: scripts/vps/tests 636 passed / 1 failed (`test_lifecycle_push_rebase.py::test_dirty_wt_blocks_rebase` — **pre-existing**, воспроизводится на develop до этой ветки); tests/ 259 passed, 1 skipped
- Exa Verify: no critical issues. Подтверждено, что `merge-base --is-ancestor` — канонический скриптовый тест, и что squash/rebase его ломают — ровно тот случай, который у нас уходит на subject-фолбэк и задокументирован. Отмечено на будущее: `git merge-tree --write-tree` (git ≥ 2.38) даёт content-containment и закрыл бы squash без регекса — кандидат в ту же TECH, что удалит `match_subject`.
- Reflect: 2 сигнала записаны (SIGNAL-2026-08-30-1115 ff-дифф, -1116 allowlist pre-flight), commit d9dfb2c3
- Documenter: completed — 5 файлов (`.claude/rules/dependencies.md` + новая секция gate_ancestry, `docs/orchestrator/{README,runbook,components}.md`, `docs/dependencies-changelog.md`), 8 устаревших ссылок на удалённый `_is_done_on_develop` починены, commit f8a8470b
- Template sync: нечего синхронизировать — `template/scripts/vps/` не существует (подтверждает Step 4 спеки); `validate-allowlist.mjs` затрагивает только `strip_bookkeeping_paths`-регексы, которые не менялись, `test_allowlist_parity.py` зелёный
- AV-S1 (импорты) pass · AV-S2 (FF-09) pass · AV-F1 (308 passed) pass · AV-F2 (140 passed) pass
- AV-F3 (coverage ≥54%): **не прогнан локально** — `pytest-cov` не установлен на этой машине; гейт остаётся за CI
- Post-Deploy Verify: DEPLOY_URL=local-only → AV-F4/EC-13 выполнен read-only на реальном репозитории после мержа (см. ниже)
