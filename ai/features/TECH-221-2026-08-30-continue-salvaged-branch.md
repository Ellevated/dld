# Feature: [TECH-221] Повторный диспатч продолжает salvage-ветку, а не стартует с нуля

**Priority:** P0 | **Date:** 2026-08-30 | **Parent:** ARCH-219 | **AFTER TECH-220**
**Size:** 4 tasks / 9 files — indivisible: чистка worktree (PHASE 0), создание worktree (шаг 5) и
вердикт гейта описывают одно состояние — «ветка есть, не влита»; починка одного без других
воспроизводит коллизию, которую devil разобрал (§Argument 3).

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.
> Do not add a `Status:` field to the spec body — it's no longer authoritative.

## Why

13 из ~50 прогонов за две недели убиты таймаутом до merge (аудит §2). `salvage.py` честно пушит
ветку (`pushed: true`, 5–6 коммитов), но дальше:

1. гейт смотрит только `origin/develop` → `blocked / no_merged_implementation`;
2. следующий диспатч делает `git worktree add -b <type>/<ID> origin/develop` — **свежую** ветку с
   тем же именем; salvage второго прогона отвергается `non-fast-forward`;
3. PHASE 0 чистка любого прогона считает salvage-ветку «запушена → можно удалять», `git worktree
   remove --force`, а `git branch -d` молча падает (`|| true`, ветка не влита) — остаётся висячий
   локальный ref, о который спотыкается следующий `-b`.

Итог: 90–180 минут и $20–30 на прогон сгорают повторно, а работа лежит в `origin/<type>/<ID>`.

## Context

Скауты: `ai/.spark/20260830-ARCH-219/research-{web,codebase,devil}.md`. Опирается на TECH-220:
`gate_ancestry.branch_ref_for`, `fetch_branch`, `find_merged_branch`.

Механика (codebase §Verified References): `worktree-setup.md:91` и `autopilot-git.md:124` — оба
безусловный `-b`; `worktree-setup.md:34-43` — sweep по `merged || pushed`; `salvage.py:227` —
`git push -u origin <branch>` без force; `salvage.find_worktree` уже prefix-agnostic.

Research §Resume: production-паттерн (`ai-sdlc`, `git-ai resume`, Syncropel dispatch-recovery) —
переиспользовать worktree из запушенной ветки, сказать агенту, какие коммиты уже есть, проверить,
не ушёл ли develop вперёд базы ветки.

---

## Scope

**In scope:** состояние ветки как чистая функция (`gate_ancestry.branch_state`); вердикт
`branch_pushed_not_merged` с числом коммитов впереди; worktree-setup PHASE 0 не удаляет worktree спеки
в этом статусе; шаг 5 переиспользует существующую ветку (`git worktree add <path> <branch>` без `-b`,
`rebase origin/develop`); диспатч передаёт автопилоту факт продолжения; обе копии промптов.

**Out of scope:** salvage сам мержит на зелёном (отдельно, если после этой спеки останутся потери);
`--ff-only` в `finishing.md` не трогается — он теперь несущий для ancestry-гейта.

---

## Impact Tree Analysis

### Step 1: UP — who uses?
_Source: grep (codebase §Step 1, §Affected Files)._
- [x] `grep -n "git worktree add" .claude/skills/autopilot/*.md template/.claude/skills/autopilot/*.md` → 4 места (worktree-setup:91, autopilot-git:124 × 2 дерева)
- [x] `grep -n "pushed=yes\|git branch -d" .claude/skills/autopilot/worktree-setup.md` → §0a sweep 34-43
- [x] `orchestrator_queue.reconcile_if_implemented` — boolean; нужен третий исход «продолжить ветку»

### Step 2: DOWN — what depends on?
- [x] `gate_ancestry` (TECH-220): `branch_ref_for`, `fetch_branch`
- [x] `salvage.find_worktree` — переиспользуется как есть

### Step 3: BY TERM — grep entire project
- [x] `grep -rn "no_merged_implementation" scripts/vps/*.py docs/ .claude/` — подсказка force-done в `callback_sync._decide_status`; новый reason рядом

| File | Line | Status | Action |
|------|------|--------|--------|
| `.claude/skills/autopilot/worktree-setup.md` | 34-43, 91 | sweep + `-b` | sweep по статусу; шаг 5 reuse-aware |
| `template/.claude/skills/autopilot/worktree-setup.md` | те же | — | тот же текст (template-sync) |
| `.claude/skills/autopilot/autopilot-git.md` | 124 | `-b` | reuse-aware |
| `template/.claude/skills/autopilot/autopilot-git.md` | те же | — | тот же текст |
| `scripts/vps/callback_sync.py` | `_decide_status` | reason `no_merged_implementation` | `branch_pushed_not_merged:N_ahead` когда ветка есть |
| `scripts/vps/orchestrator_queue.py` | 255-296, 299-348 | reconcile boolean; dispatch | трёхзначный исход; `CLAUDE_CONTINUE_BRANCH=1` в env диспатча |

### Step 4: CHECKLIST — mandatory folders
- [x] `tests/**` — `scripts/vps/tests/test_gate_logic.py` (branch_state), `scripts/vps/tests/test_orchestrator_in_progress.py` (диспатч продолжения)
- [x] `template/` — **да, оба промпта в обоих деревьях** (devil SA-9); `check-tree-sync.py` подтверждает
- [x] `db/migrations/**` — нет

### Verification
- [x] Все файлы в Allowed Files
- [x] `salvage.py` не меняется

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts.
     Format is parsed by scripts/vps/callback.py — see TECH-167/175/ARCH-186. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/gate_ancestry.py` — `branch_state(project_path, spec_id) -> BranchState` (modify)
- `scripts/vps/callback_sync.py` — reason `branch_pushed_not_merged:<N>` (modify)
- `scripts/vps/orchestrator_queue.py` — трёхзначный reconcile; диспатч с `CLAUDE_CONTINUE_BRANCH` (modify)
- `.claude/skills/autopilot/worktree-setup.md` — sweep по статусу, шаг 5 reuse (modify)
- `template/.claude/skills/autopilot/worktree-setup.md` — то же (modify)
- `.claude/skills/autopilot/autopilot-git.md` — §2.4 reuse (modify)
- `template/.claude/skills/autopilot/autopilot-git.md` — то же (modify)
- `scripts/vps/tests/test_gate_logic.py` — `branch_state` (modify)
- `scripts/vps/tests/test_orchestrator_in_progress.py` — диспатч продолжения (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: true

---

## Blueprint Reference

**Domain:** orchestrator
**Cross-cutting:** Errors — fail-closed; продолжение ветки не должно уметь тихо потерять коммиты
(rebase с конфликтом → `needs_review`, не `reset --hard`)
**Data model:** `ai/lifecycle/*.yaml` — новый `blocked_reason`; `task_log.branch`

---

## Historical Risks

<!-- lessons-binding v1 -->

| ID | Class | Rule | Sources |
|----|-------|------|---------|
| none | — | — | — |

Gate 7 auto-pass (no lessons bank). Из git: `1be55b4 wip(TECH-210): salvaged after timeout` — TECH-210
сама прошла этот сценарий и была доведена руками; TECH-197 (`_push_local_develop`) — прошлая попытка
спасти «между merge и push»; BUG-1063 (awardybot) — почему база worktree пиннится к `origin/develop`.

---

## Approaches

### Approach 1: продолжить ветку — worktree из существующего ref + rebase (выбран)
**Source:** `research-web.md` §Resume (ai-sdlc, git-ai resume); `research-devil.md` §Argument 3, DA-5, SA-1
**Summary:** до создания worktree — `branch_state`; если `origin/<type>/<ID>` есть и не влита:
`git worktree add .worktrees/<ID> <branch>` (без `-b`), `git rebase origin/develop`, конфликт →
`needs_review`; планировщик получает список уже сделанных коммитов
**Pros:** работа не сгорает; salvage-push перестаёт быть non-fast-forward
**Cons:** rebase может конфликтовать — тогда честный `needs_review`, а не тихий старт с нуля

### Approach 2: salvage мержит сам на зелёном `./test ci`
**Source:** devil §Alternative 1
**Pros:** ничего в промптах
**Cons:** красная ветка сгорает целиком; при 400+ ходах до таймаута ветка почти всегда красная —
именно эти прогоны и умирают

### Selected: 1
**Rationale:** цель — не потерять работу, а не «иногда повезёт с зелёным». Approach 2 можно добавить
поверх позже, если метрика покажет, что зелёные salvage-ветки — заметная доля.

---

## Design

### `gate_ancestry.branch_state`

```python
@dataclass(frozen=True)
class BranchState:
    ref: str               # "fix/BUG-9"
    exists: bool           # origin/<ref> есть после fetch_branch
    merged: bool           # is-ancestor origin/develop
    ahead: int             # rev-list --count origin/develop..origin/<ref>
    behind: int            # rev-list --count origin/<ref>..origin/develop
```

Чистая, fail-closed: ошибка git → `exists=False`.

### Вердикт

`callback_sync._decide_status`: после `find_implementation` дал `(None, _)` — если
`branch_state.exists and ahead > 0` → `blocked`, reason
`branch_pushed_not_merged:<ahead> ahead — re-dispatch continues the branch`. Иначе прежний
`no_merged_implementation` с force-done подсказкой.

### Диспатч

`orchestrator_queue.reconcile_if_implemented` → `reconcile(...) -> "done" | "continue" | "fresh"`.
`"continue"` → `pueue add` с `CLAUDE_CONTINUE_BRANCH=1` в env (как `CLAUDE_CURRENT_SPEC_PATH`).

### Промпты (обе копии)

PHASE 0 sweep: **не** удалять worktree, если `ai/lifecycle/<ID>.yaml` → `blocked` c
`branch_pushed_not_merged`. Шаг 5:

```bash
if git ls-remote --exit-code origin "{type}/{ID}" >/dev/null 2>&1; then
  git fetch origin "{type}/{ID}"
  git worktree add ".worktrees/{ID}" "{type}/{ID}"        # без -b
  git -C ".worktrees/{ID}" rebase origin/develop || { echo REBASE_CONFLICT; exit 2; }  # → needs_review
  git -C ".worktrees/{ID}" log --oneline origin/develop..HEAD   # планировщику: что уже сделано
else
  git worktree add ".worktrees/{ID}" -b "{type}/{ID}" origin/develop
fi
```

Карта префиксов в обоих промптах получает строку `GROWTH- | growth/` (L-derived-4 с TECH-220).

---

## Implementation Plan

### Research Sources
- `research-web.md` §Resume, §Pitfalls
- `research-devil.md` §Argument 3, DA-5, SA-1, SA-9
- `research-codebase.md` §Extend

### Task 1: `branch_state`
**Type:** code
**Files:**
  - modify: `scripts/vps/gate_ancestry.py`
  - modify: `scripts/vps/tests/test_gate_logic.py`
**Acceptance:** EC-1..EC-3 на throwaway-репо

### Task 2: вердикт и трёхзначный reconcile
**Type:** code
**Files:**
  - modify: `scripts/vps/callback_sync.py`
  - modify: `scripts/vps/orchestrator_queue.py`
  - modify: `scripts/vps/tests/test_orchestrator_in_progress.py`
**Acceptance:** EC-4..EC-6

### Task 3: промпты в обоих деревьях
**Type:** code
**Files:**
  - modify: `.claude/skills/autopilot/worktree-setup.md`
  - modify: `template/.claude/skills/autopilot/worktree-setup.md`
  - modify: `.claude/skills/autopilot/autopilot-git.md`
  - modify: `template/.claude/skills/autopilot/autopilot-git.md`
**Acceptance:** `python scripts/check-tree-sync.py` clean; EC-7 (сценарий по шагам на throwaway-репо)

### Task 4: живая проверка
**Type:** test
**Acceptance:** EC-8 на VPS: спека с salvage-веткой → callback даёт `branch_pushed_not_merged`, следующий диспатч создаёт worktree из ветки, salvage-push проходит

### Execution Order
1 → 2 → 3 → 4

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Прогон убит таймаутом, salvage пушит ветку | — | existing |
| 2 | Callback: ветка есть, не влита → `branch_pushed_not_merged:N` | Task 1, 2 | ✓ |
| 3 | PHASE 0 другого прогона не удаляет worktree этой спеки | Task 3 | ✓ |
| 4 | Оркестратор: `continue`, env-флаг | Task 2 | ✓ |
| 5 | Шаг 5: worktree из ветки, rebase, список сделанного | Task 3 | ✓ |
| 6 | Конфликт rebase → `needs_review` | Task 3 | ✓ |
| 7 | Merge ff-only → гейт TECH-220 видит ancestry | — | TECH-220 |

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Ветка запушена, 3 впереди | `origin/fix/BUG-9` +3 над develop | `exists=True, merged=False, ahead=3` | deterministic | devil | P0 |
| EC-2 | Ветки нет | — | `exists=False`, без исключения | deterministic | FF-09 | P0 |
| EC-3 | Ветка влита | ff-only merged | `merged=True, ahead=0` | deterministic | — | P0 |
| EC-4 | Вердикт | EC-1 + `target=blocked` | reason начинается с `branch_pushed_not_merged:3` | deterministic | — | P0 |
| EC-5 | Reconcile трёхзначный | EC-1 / EC-3 / ничего | `"continue"` / `"done"` / `"fresh"` | deterministic | devil SA-5 | P0 |
| EC-6 | Диспатч передаёт флаг | `"continue"` | `pueue add` env содержит `CLAUDE_CONTINUE_BRANCH=1` | deterministic | — | P1 |
| EC-7 | Шаг 5 по скрипту из спеки | throwaway-репо с запушенной веткой | worktree на ветке, `-b` не вызывался, лог коммитов выведен | deterministic | devil DA-5 | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-8 | VPS, спека с salvage-веткой | callback → диспатч → salvage | reason `branch_pushed_not_merged`; второй salvage-push не non-fast-forward | integration | аудит §2 | P0 |

### Coverage Summary
Deterministic: 7 | Integration: 1 | LLM-Judge: 0 | Total: 8 (min 3 ✓)

### TDD Order
1. EC-1..EC-3 → Task 1
2. EC-4..EC-6 → Task 2
3. EC-7 → Task 3
4. EC-8 → Task 4

---

## Acceptance Verification

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Импорт | `PYTHONPATH=scripts/vps python -c "import gate_ancestry, gate_logic, callback_sync, orchestrator_queue"` | exit 0 | 15s |
| AV-S2 | Два дерева | `python scripts/check-tree-sync.py` | clean | 60s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Тесты | — | `cd scripts/vps/tests && python -m pytest -q -k "gate_logic or orchestrator or callback"` | 0 failed |
| AV-F2 | Живой сценарий | VPS | EC-8 | reason + успешный второй push |

### Verify Command

```bash
PYTHONPATH=scripts/vps python -c "import gate_ancestry, gate_logic, callback_sync, orchestrator_queue"
python scripts/check-tree-sync.py
cd scripts/vps/tests && python -m pytest -q -k "gate_logic or orchestrator or callback"
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `branch_pushed_not_merged:<N>` вместо `no_merged_implementation`, когда ветка есть
- [ ] Повторный диспатч работает на существующей ветке; sweep её не трогает
- [ ] Оба дерева промптов идентичны

### Tests
- [ ] EC-1..EC-8 проходят

### Acceptance Verification
- [ ] AV-S1, AV-S2, AV-F1 локально; AV-F2 на VPS

### Technical
- [ ] `salvage.py`, `finishing.md` (`--ff-only`) не изменены
- [ ] Все файлы ≤ 400 LOC

---

## Autopilot Log
