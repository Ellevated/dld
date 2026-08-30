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

> Validated against the worktree at `.worktrees/TECH-221` (base: `origin/develop` with
> TECH-220 landed). Line numbers below are from THAT tree. Read `### Drift Log` first —
> three assumptions in the sections above are wrong and the tasks work around them.

### Research Sources
- `research-web.md` §Resume, §Pitfalls · `research-devil.md` §Argument 3, DA-5, SA-1, SA-9 ·
  `research-codebase.md` §Extend
- No external crawl performed: nothing here depends on a third-party API. The two facts that
  needed re-checking are local and were checked directly — `git worktree add <path> <branch>`
  gives a DETACHED HEAD unless the local branch already exists (`worktree.guessRemote` is off
  by default), and `claude-runner.py:557-579` passes a CLOSED env whitelist to the SDK.

### Task 1: `gate_ancestry.branch_state`

**Type:** code
**Files:**
- Modify: `scripts/vps/gate_ancestry.py` (212 LOC → ≤265; add after `fetch_branch`, line 111)

**Context:** the gate answers one question today — "is the branch merged". The re-dispatch
decision needs a second — "does the branch exist with work on it". Same module, same
`_git` fail-closed helper, no new dependency (FF-09 invariant holds: still only `gate_logic`).

**Steps:**

1. Add to the import block (after `import subprocess`, line 41):
   ```python
   from dataclasses import dataclass
   ```

2. Insert after `fetch_branch` (i.e. after line 110, before `_base_for_diff`):
   ```python
   @dataclass(frozen=True)
   class BranchState:
       """What origin knows about <type>/<ID> right now (TECH-221).

       ref     — "fix/BUG-9"; "" when the spec id carries no known prefix
       exists  — refs/remotes/origin/<ref> resolves (call fetch_branch first)
       merged  — <ref> is an ancestor of origin/develop
       ahead   — commits on <ref> that origin/develop does not have
       behind  — commits on origin/develop that <ref> does not have
       """

       ref: str
       exists: bool
       merged: bool
       ahead: int
       behind: int


   def branch_state(project_path: str, spec_id: str) -> BranchState:
       """Read-only verdict on origin/<type>/<ID>. Never raises.

       Deliberately does NOT fetch: every caller runs fetch_branch as part of the
       gate a few lines earlier, and a second fetch would double the cost of the
       hot path. Fail-closed by construction — any git failure collapses to
       exists=False, which routes back to the old no_merged_implementation
       verdict rather than to a continuation that has nothing to continue.

       Exact remote ref, never a glob, and never a LOCAL branch: a stale
       refs/heads/<ref> left behind by a swept worktree is precisely the state
       this spec exists to survive, and treating it as evidence would re-create
       the bug (devil DA-8, and the same rule find_merged_branch follows).
       """
       try:
           ref = branch_ref_for(spec_id)
       except ValueError:
           return BranchState(ref="", exists=False, merged=False, ahead=0, behind=0)
       remote = f"refs/remotes/origin/{ref}"
       if not _git(project_path, "rev-parse", "--verify", "--quiet", remote):
           return BranchState(ref=ref, exists=False, merged=False, ahead=0, behind=0)
       # rc 0 = ancestor -> "" (not None); rc 1 / error -> None. Same reading as
       # find_merged_branch: only an explicit rc 0 counts as merged.
       merged = (
           _git(project_path, "merge-base", "--is-ancestor", remote, "origin/develop")
           is not None
       )
       ahead = behind = 0
       counts = _git(
           project_path, "rev-list", "--left-right", "--count", f"origin/develop...{remote}"
       )
       if counts:
           parts = counts.split()
           if len(parts) == 2 and all(p.isdigit() for p in parts):
               behind, ahead = int(parts[0]), int(parts[1])
       return BranchState(ref=ref, exists=True, merged=merged, ahead=ahead, behind=behind)
   ```
   `A...B` (three dots) with `--left-right --count` prints `<only-in-A> <only-in-B>` — left is
   develop-only (behind), right is branch-only (ahead). Two dots would return one number and
   silently mean something else.

3. Update the module docstring's "Used by" list (lines 20-25): add
   `- orchestrator_queue.reconcile (branch_state)` and
   `- callback_sync._decide_status (branch_state)`.

4. Tests for EC-1..EC-3 go in `test_orchestrator_in_progress.py` — see Task 3.
   **Do NOT touch `scripts/vps/tests/test_gate_logic.py`: it is at 598 lines against a
   600-line ceiling** (`scripts/pre-review-check.py:124`), so it has room for two lines and
   no more. Leaving it unmodified is fine for the callback gate — `find_merged_branch`
   requires a non-empty INTERSECTION with Allowed Files, not every file in it.

**Acceptance:** EC-1, EC-2, EC-3 (asserted by the tests written in Task 3).
```bash
cd /home/dld/projects/dld/.worktrees/TECH-221
PYTHONPATH=scripts/vps python3 -c "
import gate_ancestry as g
print(g.branch_state('.', 'TECH-221'))
print(g.branch_state('.', 'NOPREFIX-1'))"     # both print a BranchState, no traceback
ruff check scripts/vps/gate_ancestry.py && ruff format --check scripts/vps/gate_ancestry.py
wc -l scripts/vps/gate_ancestry.py            # ≤ 265
```

---

### Task 2: verdict `branch_pushed_not_merged:<N>` + three-way reconcile

**Type:** code
**Files:**
- Modify: `scripts/vps/callback_sync.py:230-238` (368 LOC → ≤380)
- Modify: `scripts/vps/orchestrator_queue.py:256-300` (379 LOC → **must end ≤ 400**)

**Context:** two call sites read the same fact and must not disagree. The callback names the
state for the operator; the orchestrator acts on it. Neither may change the shape the
un-editable caller expects — see the two traps below.

**Steps:**

1. `callback_sync.py` — replace the final `return` of `_decide_status` (lines 230-238) with:
   ```python
       state = gate_ancestry.branch_state(project_path, spec_id)
       if state.exists and state.ahead > 0:
           # TECH-221: the run died before merge and salvage pushed the branch.
           # Nothing is lost and force-done is the WRONG advice here — the next
           # dispatch continues that branch (orchestrator_queue.reconcile).
           return (
               "blocked",
               f"branch_pushed_not_merged:{state.ahead} ahead — "
               f"origin/{state.ref} carries the work; re-dispatch continues that branch",
               via,
           )
       return (
           "blocked",
           (
               f"no_merged_implementation — if implementation IS real, run: "
               f"python3 scripts/vps/spec_operator.py force-done {project_id} {spec_id} "
               f"'gate regex bug, verified manually' --by=operator"
           ),
           via,
       )
   ```
   Leave the `autopilot_signaled` early return (line 214-219) **untouched**: a deliberate
   self-block is not a salvage, and `scripts/vps/tests/test_callback.py:731` pins
   `blocked_reason == "autopilot_signaled_blocked"` exactly.

2. `orchestrator_queue.py` — add `import os` to the stdlib block (after `import json`, line 19).

3. Replace `reconcile_if_implemented` (lines 256-300) with the pair below. The docstring is
   deliberately shorter than the one it replaces: the file has 21 lines of headroom against
   the 400-LOC limit and this edit must fit inside them.
   ```python
   def reconcile(project_dir: str, spec_id: str, spec_file: Path) -> str:
       """Pre-dispatch verdict: "done" | "continue" | "fresh".

       "done"     — already on origin/develop (another window, another node, or a
                    session whose callback never fired). Marked done here; without
                    this we burn a session for the guard to rubber-stamp it after.
       "continue" — origin/<type>/<ID> exists with commits develop lacks: a run
                    killed by timeout whose salvage pushed the branch (TECH-221).
                    Dispatch, but the worktree must be built FROM that branch.
       "fresh"    — nothing found; normal dispatch.

       Fail-closed: "done" only on a positive allowlist AND a positive gate match;
       "continue" only on a remote branch that is provably ahead of develop.
       """
       allowed_files = gate_logic.parse_allowed_files(spec_file)
       if not allowed_files:
           return "fresh"
       gate_logic.fetch_develop(project_dir)
       gate_ancestry.fetch_branch(project_dir, spec_id)
       impl_sha, via = gate_ancestry.find_implementation(project_dir, spec_id, allowed_files)
       if not impl_sha:
           state = gate_ancestry.branch_state(project_dir, spec_id)
           return "continue" if state.exists and state.ahead > 0 else "fresh"
       try:
           lifecycle.write_lifecycle(
               project_dir,
               spec_id,
               "done",
               by="orchestrator",
               reason=f"already_implemented_on_develop:{impl_sha[:12]}",
           )
           log.info(
               "reconciled: %s already implemented on develop (%s, gate_via=%s) — "
               "marked done, no dispatch",
               spec_id,
               impl_sha[:12],
               via,
           )
       except lifecycle.LifecycleAlreadyDoneError:
           log.info("reconcile noop: %s already done (race)", spec_id)
       except lifecycle.LifecycleWriteRaceError:
           log.info("reconcile deferred: %s CAS race, retry next cycle", spec_id)
       return "done"


   def reconcile_if_implemented(project_dir: str, spec_id: str, spec_file: Path) -> bool:
       """Bool facade for scan_queued, plus the CLAUDE_CONTINUE_BRANCH side effect.

       The name and the bool are load-bearing: orchestrator.py:249 reads this as a
       truth value and is NOT editable under this spec. Returning the raw verdict
       string would make "continue" and "fresh" truthy and skip EVERY dispatch.

       The env write is here for the same reason. scan_queued builds its pueue_env
       dict at orchestrator.py:245 and calls this at 249, immediately before
       _pueue_add (252), which submits `{**os.environ, **env}` — so this is the
       only per-dispatch hook this module owns. ALWAYS written, never only set: a
       leftover "1" would label the next, unrelated spec a continuation.
       """
       verdict = reconcile(project_dir, spec_id, spec_file)
       if verdict == "continue":
           os.environ["CLAUDE_CONTINUE_BRANCH"] = "1"
           log.info("continue dispatch: %s — origin branch has unmerged commits", spec_id)
       else:
           os.environ.pop("CLAUDE_CONTINUE_BRANCH", None)
       return verdict == "done"
   ```

4. Update the module docstring "Uses" line (13-14) — no new import beyond `os`, so only add
   `os` if you list stdlib there; do not restructure the header.

**Acceptance:** EC-4, EC-5, EC-6 (tests in Task 3).
```bash
cd /home/dld/projects/dld/.worktrees/TECH-221
PYTHONPATH=scripts/vps python3 -c "import gate_ancestry, gate_logic, callback_sync, orchestrator_queue"
wc -l scripts/vps/callback_sync.py scripts/vps/orchestrator_queue.py   # ≤380, ≤400
ruff check scripts/vps && ruff format --check scripts/vps
DB_PATH=/tmp/tech221.db python3 -m pytest scripts/vps/tests/test_callback.py -q   # 0 failed
DB_PATH=/tmp/tech221.db python3 -m pytest tests/integration/test_callback_feature_branch.py \
  tests/integration/test_callback_no_impl_demote.py tests/integration/test_callback_already_merged.py -q
```
The last command is the regression that matters: those three files assert
`no_merged_implementation` and are NOT editable. They stay green because their fixtures have
no `origin` remote at all, so `branch_state` returns `exists=False`. If one of them turns
red, the new branch is being read from `refs/heads/` instead of `refs/remotes/origin/`.

---

### Task 3: tests for EC-1..EC-6

**Type:** test
**Files:**
- Modify: `scripts/vps/tests/test_orchestrator_in_progress.py` (236 LOC → ≤400; ceiling 600)

**Context:** this file is the only editable test file with room (see Task 1 step 4). Extend its
module docstring with a second line: `TECH-221 — branch_state, three-way reconcile and the
continue-dispatch env flag live here because test_gate_logic.py sits at 598/600 lines.`

**Steps:**

1. Add imports next to the existing ones (line 20-21): `import os`, `import gate_ancestry`,
   `import callback_sync`, `import orchestrator_queue`.

2. Add a fixture that gives a real bare remote (ADR-013 — no mocks for git):
   ```python
   @pytest.fixture()
   def repo_with_origin(tmp_path):
       """local repo + bare origin, develop pushed. Mirrors test_gate_logic.py:72-100."""
       remote, local = tmp_path / "remote", tmp_path / "local"
       subprocess.run(["git", "init", "--bare", "-q", "-b", "develop", str(remote)], check=True)

       def git(*args):
           subprocess.run(["git", *args], cwd=str(local), check=True, capture_output=True)

       local.mkdir()
       git("init", "-q", "-b", "develop")
       git("config", "user.email", "t@t")
       git("config", "user.name", "t")
       git("remote", "add", "origin", str(remote))
       (local / "README.md").write_text("init\n", encoding="utf-8")
       git("add", "README.md")
       git("commit", "-q", "-m", "init")
       git("push", "-q", "origin", "develop")
       return local, git
   ```

3. `class TestBranchState` — three tests, all against `repo_with_origin`:
   - **EC-1** `test_pushed_branch_is_ahead`: `git("checkout","-q","-b","fix/BUG-9")`, three
     commits, `git("push","-q","origin","fix/BUG-9")`, `git("checkout","-q","develop")`, then
     `st = gate_ancestry.branch_state(str(local), "BUG-9")` →
     `st.exists is True and st.merged is False and st.ahead == 3 and st.behind == 0 and st.ref == "fix/BUG-9"`.
   - **EC-2** `test_missing_branch_is_absent`: on the bare fixture,
     `gate_ancestry.branch_state(str(local), "BUG-404")` → `exists is False`, no exception.
     Second assertion in the same test: an unknown prefix (`"NOPE-1"`) also returns
     `exists is False` with `ref == ""` — that is the `ValueError` path.
   - **EC-3** `test_merged_branch_is_ancestor`: after EC-1's setup,
     `git("merge","--ff-only","fix/BUG-9")` on develop, `git("push","-q","origin","develop")`,
     re-read → `merged is True and ahead == 0`.
   Every test must call `gate_ancestry.fetch_branch(str(local), spec_id)` first if it pushed
   from the same clone — pushing updates `refs/remotes/origin/*` automatically here, so this is
   belt-and-suspenders; state the reason in a comment rather than dropping it.

4. `class TestDecideStatusNamesTheBranch` — **EC-4**:
   ```python
   def test_reason_is_branch_pushed_not_merged(self, repo_with_origin, monkeypatch):
       local, git = repo_with_origin
       # 3 commits on fix/BUG-9, pushed, develop unchanged (EC-1 setup)
       ...
       monkeypatch.setattr(callback_sync.time, "sleep", lambda *_: None)  # 3×5s grace retry
       status, reason, _via = callback_sync._decide_status(
           str(local), "BUG-9", "proj", ["src/x.py"], autopilot_signaled=False
       )
       assert status == "blocked"
       assert reason.startswith("branch_pushed_not_merged:3")
       assert "force-done" not in reason
   ```
   The `sleep` patch is not optional: without it `_decide_status` sleeps 15 s per call
   (`callback_sync.py:221-228`).

5. `class TestReconcileThreeWay` — **EC-5**. `reconcile` needs a spec file with a v1
   allowlist; reuse the literal from `_dispatch` (line 67-70). Three cases on
   `repo_with_origin`: branch pushed and ahead → `"continue"`; branch merged ff-only into
   develop AND the diff touches an allowed file → `"done"`; nothing pushed → `"fresh"`.
   For the `"done"` case make the commit touch `src/dummy.py` (the allowlisted path), or
   `find_merged_branch`'s diff-intersection rejects it and you get `"fresh"`.

6. **EC-6**, two tests:
   - `test_env_flag_set_and_cleared`: call `orchestrator_queue.reconcile_if_implemented`
     directly on a continue-state repo → `os.environ["CLAUDE_CONTINUE_BRANCH"] == "1"`; call
     it again on a fresh-state repo → `"CLAUDE_CONTINUE_BRANCH" not in os.environ`.
   - `test_flag_is_live_at_pueue_add`: reuse `_dispatch` but with a capturing mock —
     ```python
     seen = {}
     def _capture(*a, **kw):
         seen["flag"] = os.environ.get("CLAUDE_CONTINUE_BRANCH")
         return 42
     ```
     patched over `orchestrator._pueue_add`, plus
     `patch("orchestrator_queue.gate_ancestry.branch_state", return_value=gate_ancestry.BranchState("tech/TECH-911", True, False, 3, 0))`.
     Assert `seen["flag"] == "1"`. This proves the var is live in `os.environ` at the moment
     `_pueue_add` builds `{**os.environ, **env}`, which is the only thing the un-editable
     caller lets us prove.
   Add a module-level autouse fixture that pops `CLAUDE_CONTINUE_BRANCH` in `finally` —
   production code writes `os.environ` directly, so `monkeypatch` cannot undo it and the flag
   would leak into the next test.

**Acceptance:** EC-1..EC-6 green, whole orchestrator suite still green.
```bash
cd /home/dld/projects/dld/.worktrees/TECH-221
DB_PATH=/tmp/tech221.db python3 -m pytest scripts/vps/tests/test_orchestrator_in_progress.py -q
DB_PATH=/tmp/tech221.db python3 -m pytest scripts/vps/tests/ -q      # 0 failed
DB_PATH=/tmp/tech221.db python3 -m pytest tests/ -q                  # 0 failed
wc -l scripts/vps/tests/test_orchestrator_in_progress.py             # < 600
```

---

### Task 4: prompts — reuse-aware PHASE 0, both trees

**Type:** code + sync
**Files:**
- Modify: `.claude/skills/autopilot/worktree-setup.md` (§0a sweep 15-44; step 5 at 88-91; type map 102-108)
- Modify: `template/.claude/skills/autopilot/worktree-setup.md` (same anchors, same text)
- Modify: `.claude/skills/autopilot/autopilot-git.md` (`case` 51-59; §2.4 106-126; §5.3 256-260)
- Modify: `template/.claude/skills/autopilot/autopilot-git.md` (same anchors, same text)

**Context:** three edits per tree, and they are one change: the sweep must stop deleting the
worktree, step 5 must reuse the branch, and §5.3 must be able to push a rebased branch. Any
one alone reproduces the collision devil described (§Argument 3).

**Steps:**

1. **Sweep guard** — `worktree-setup.md` §0a, insert immediately after the uncommitted-changes
   check (after line 27, before the `# Remove when the work is safe` comment):
   ```bash
     # TECH-221: a spec whose branch was pushed but never merged is WAITING to be
     # continued. `pushed=yes` is true for exactly that state, so the test below
     # would delete the worktree and then fail to delete the branch (`git branch -d`
     # refuses an unmerged branch), leaving the dangling local ref the next
     # `worktree add -b` trips over.
     wt_spec="$(basename "$wt")"
     if grep -q 'branch_pushed_not_merged' "ai/lifecycle/${wt_spec}.yaml" 2>/dev/null; then
       echo "SWEEP SKIP: $wt — branch pushed, not merged (re-dispatch continues it)"
       continue
     fi
   ```

2. **Step 5** — replace `worktree-setup.md` lines 88-91 with the block below. Keep the existing
   `# WHY origin/develop explicit` comment (lines 93-100) exactly where it is; it still governs
   the else-branch.
   ```
   5. Create worktree — CONTINUE an existing pushed branch, else branch fresh from origin/develop:
      # Refresh remote first — base MUST be fresh origin/develop, not stale local ref
      git fetch origin develop

      if git ls-remote --exit-code --heads origin "{type}/{ID}" >/dev/null 2>&1; then
        # CONTINUATION: a previous run was killed by timeout and its salvage pushed
        # the commits. Starting fresh here burns them and makes the next salvage
        # push non-fast-forward.
        git fetch origin "{type}/{ID}"

        # A local ref may survive from a swept worktree. Drop it only when origin
        # already has everything it holds; otherwise STOP — never discard commits.
        if git show-ref --verify --quiet "refs/heads/{type}/{ID}"; then
          if [[ -z "$(git log --oneline "origin/{type}/{ID}..{type}/{ID}" 2>/dev/null)" ]]; then
            git branch -D "{type}/{ID}"
          else
            echo "LOCAL_BRANCH_AHEAD: {type}/{ID} has commits origin lacks — needs_review"
            exit 2
          fi
        fi

        # -b <branch> <start-point> is the only non-detached form: plain
        # `worktree add <path> <branch>` detaches HEAD unless the local branch
        # already exists (worktree.guessRemote is off by default).
        git worktree add ".worktrees/{ID}" -b "{type}/{ID}" "origin/{type}/{ID}"

        git -C ".worktrees/{ID}" rebase origin/develop || {
          git -C ".worktrees/{ID}" rebase --abort
          echo "REBASE_CONFLICT: {type}/{ID} vs origin/develop"
          # STOP. Emit task_status="needs_review". NEVER reset --hard: those
          # commits are the work this spec exists to save.
          exit 2
        }

        # Re-sync origin immediately: the rebase rewrote the salvaged commits, so
        # until this lands origin and local have diverged and the NEXT salvage
        # push would be rejected non-fast-forward — the exact loss this fixes.
        git -C ".worktrees/{ID}" push --force-with-lease origin "{type}/{ID}"

        echo "CONTINUING {type}/{ID} — commits already done:"
        git -C ".worktrees/{ID}" log --oneline origin/develop..HEAD
        # Read that list before planning. Those tasks are DONE — do not redo them.
      else
        git worktree add ".worktrees/{ID}" -b "{type}/{ID}" origin/develop
      fi
   ```

3. **Type map** — add one row to `worktree-setup.md` lines 102-108:
   ```
   | GROWTH- | growth/     |
   ```
   Value must equal `gate_ancestry._BRANCH_PREFIX["GROWTH"]` (`growth`), see that map's comment
   (L-derived-4, TECH-220).

4. **`autopilot-git.md`**: add `GROWTH) BRANCH_PREFIX="growth" ;;` to the `case` (after the
   `ARCH)` line, 56) and the matching `| GROWTH-XXX | growth/GROWTH-XXX | .worktrees/GROWTH-XXX/ |`
   row to the §1 table.

5. **`autopilot-git.md` §2.4** (lines 106-126): same continuation logic as step 2, written with
   the file's variables (`$WORKTREE_PATH`, `${BRANCH_PREFIX}/${TASK_ID}`, `cd "$WORKTREE_PATH"`
   at the end of both branches). Keep the existing WHY comment on the else-branch.

6. **`autopilot-git.md` §5.3** (lines 256-260) — a continued branch was rebased, so the plain
   push is non-fast-forward by construction:
   ```bash
   # A continued branch (PHASE 0) was rebased onto develop, so its first push is
   # non-fast-forward by construction. --force-with-lease refuses if origin moved
   # under us; never plain --force.
   git push -u origin ${BRANCH_PREFIX}/${TASK_ID} ||
     git push --force-with-lease origin ${BRANCH_PREFIX}/${TASK_ID}
   ```

7. **Sync both trees.** Apply byte-identical text to the `template/` copies — but **do not
   `cp`**: the two files differ today by exactly one line each and must keep differing
   (`rules/template-sync.md`, "Template prompts carry no DLD spec ids"):
   - `worktree-setup.md:100` — root `#   merge-backs). ... Reference: awardybot TECH-1063 incident, commit 833e5994.`
     vs template `#   merge-backs). ... This has bitten a real run — do not skip the check.`
   - `autopilot-git.md:123` — the same pair.
   Nothing added in this task may name a spec id in the template copy.

**Acceptance:** EC-7, plus tree parity.
```bash
cd /home/dld/projects/dld/.worktrees/TECH-221
# Exactly one hunk per file, and it is the pre-existing spec-id line:
diff .claude/skills/autopilot/worktree-setup.md template/.claude/skills/autopilot/worktree-setup.md
diff .claude/skills/autopilot/autopilot-git.md   template/.claude/skills/autopilot/autopilot-git.md
grep -c 'GROWTH' .claude/skills/autopilot/worktree-setup.md \
  template/.claude/skills/autopilot/worktree-setup.md \
  .claude/skills/autopilot/autopilot-git.md \
  template/.claude/skills/autopilot/autopilot-git.md      # every file ≥ 1
node .claude/scripts/check-prompt-integrity.mjs --tree .claude        # exit 0
python3 scripts/check-tree-sync.py                                    # 0 (see Drift Log D4)
```
EC-7, executed by hand once in a throwaway repo (10 lines, no CI needed):
```bash
d=$(mktemp -d); git init --bare -q -b develop "$d/origin"
git clone -q "$d/origin" "$d/wk"; cd "$d/wk"
git commit -q --allow-empty -m init && git push -q origin develop
git checkout -q -b tech/TECH-999 && git commit -q --allow-empty -m "wip(TECH-999): salvaged"
git push -q -u origin tech/TECH-999 && git checkout -q develop && git branch -D tech/TECH-999
# now run step 5's continuation branch verbatim with {type}/{ID}=tech/TECH-999:
test "$(git -C .worktrees/TECH-999 rev-parse HEAD)" = "$(git rev-parse origin/tech/TECH-999)"
```
The pass condition is HEAD identity with the remote branch tip (and a non-empty
`log --oneline origin/develop..HEAD`), **not** the absence of the `-b` token — EC-7's wording
predates the detached-HEAD finding, see Drift Log D3.

---

### Task 5: live verification note (EC-8) — NOT executable in this run

**Type:** doc
**Files:**
- Modify: `ai/features/TECH-221-2026-08-30-continue-salvaged-branch.md` (this file, `## Autopilot Log`)

**Context:** EC-8 needs a real spec killed by a real timeout on the live orchestrator, then a
real re-dispatch. Autopilot cannot manufacture that inside its own session — it would have to
kill itself, wait for `callback.py` to fire, and observe the next orchestrator cycle. **Do not
attempt it, and do not fake it with a hand-built lifecycle yaml.**

**Steps:** append to `## Autopilot Log`, verbatim:
```markdown
### EC-8 — deferred to operator (manual)

Not runnable from an autopilot session: it needs a timeout-killed run on the live VPS.
Operator protocol, first spec that salvages after this lands:

1. `python3 scripts/vps/db.py ...` / `grep salvage scripts/vps/logs/<run>.log` — confirm
   `pushed: true` for `origin/<type>/<ID>`.
2. `cat ai/lifecycle/<ID>.yaml` → `blocked_reason` starts with `branch_pushed_not_merged:`
   (NOT `no_merged_implementation`).
3. `spec_operator.py` demote to `queued`, wait one orchestrator cycle, then
   `git -C .worktrees/<ID> log --oneline origin/develop..HEAD` — the salvaged commits are
   there and the run did not start from zero.
4. `grep 'continue dispatch' scripts/vps/logs/orchestrator.log` — one line for that spec.
5. If that run also dies: its salvage push must succeed (fast-forward), because PHASE 0
   force-with-lease-pushed the rebased branch before any work started.
```

**Acceptance:** the section exists. No code, no test, no `## Status` line, no lifecycle edit.

---

### Execution Order

```
Task 1 (branch_state)
  └─> Task 2 (callback_sync verdict + orchestrator_queue reconcile)   [imports BranchState]
        └─> Task 3 (tests EC-1..EC-6)                                 [tests 1 and 2 together]
Task 4 (prompts, both trees)   — independent of 1-3, may run in parallel or last
Task 5 (EC-8 note)             — last; it records what the run could NOT verify
```
Task 2 cannot start before Task 1 (it calls `branch_state`). Task 3 covers both and is written
after them rather than before only because `_decide_status` and `reconcile` change shape in
Task 2; write the assertions first inside Task 3 and watch them fail on a stash if you want
the TDD signal. Task 4 touches no Python and shares no file with 1-3.

**One commit per task**, subject `tech(TECH-221): <what>`. Never `git add ai/lifecycle/`.

### Drift Log

Spec is **light-drifted**: it was written against a mental model of the post-TECH-215/216 split
that does not match the files. Fixed here, no council escalation needed — every fix stays
inside `## Allowed Files`.

| # | Spec says | Reality (verified in this worktree) | Resolution |
|---|---|---|---|
| D1 | Impact Tree: `orchestrator_queue.py 299-348 — dispatch; CLAUDE_CONTINUE_BRANCH=1 в env диспатча` | The dispatch and its `pueue_env` dict live in **`orchestrator.py:245-263`** (`scan_queued`), which TECH-215 deliberately kept out of `orchestrator_queue.py` and which is **not** in Allowed Files. `orchestrator_queue.py:303-356` is `record_dispatch`, which runs AFTER `_pueue_add` — too late to affect env. | Env is set/cleared in `reconcile_if_implemented` (Task 2), the one function inside the allowlist that runs immediately before `_pueue_add`. `_pueue_add` submits `{**os.environ, **env}` (`orchestrator_slots.py:197`), so the flag lands on the task. Documented in the docstring; always cleared, never only set. |
| D2 | Design: `reconcile_if_implemented → reconcile(...) -> "done"\|"continue"\|"fresh"` | `orchestrator.py:249` reads the return as a **bool** (`if ...: return False`). All three strings are truthy — changing the return type in place would skip **every** dispatch, fleet-wide. | Two functions: `reconcile` (three-way, EC-5) + `reconcile_if_implemented` (bool facade, unchanged signature). Named in Task 2 step 3 with the reason in the docstring so nobody "simplifies" it back. |
| D3 | Design step 5: `git worktree add ".worktrees/{ID}" "{type}/{ID}"  # без -b`; EC-7: "`-b` не вызывался" | With no local branch of that name, that form gives a **detached HEAD** (`worktree.guessRemote` defaults to false) — commits would land on no branch and PHASE 3 push would fail. A stale local branch of that name is also exactly what the sweep leaves behind. | Step 5 uses `-b "{type}/{ID}" "origin/{type}/{ID}"` after an explicit, fail-closed cleanup of the local ref. EC-7's pass condition is restated as HEAD identity with the remote tip; the "-b not called" wording is superseded. |
| D4 | AV-S2 / Task 3 acceptance: `python scripts/check-tree-sync.py` proves the prompt trees match | That script compares **function bodies in `.mjs/.js/.py/.sh`** only (`scripts/check-tree-sync.py:63`, and its own docstring: "compares function bodies only"). It cannot see a markdown prompt, and on this box it most likely reports `TREE_SYNC_UNAVAILABLE` + exit 0. | Keep running it (it must not regress), but the real gate for Task 4 is a two-file `diff` whose only hunk is the pre-existing spec-id line. Both commands are in Task 4's acceptance. |
| D5 | Allowed Files: `scripts/vps/tests/test_gate_logic.py — branch_state (modify)` | That file is **598 lines** against the 600-line test ceiling enforced by `scripts/pre-review-check.py:124`, which `task-loop.md` Step 3a runs. Adding EC-1..EC-3 there trips the gate. | `branch_state` tests go to `test_orchestrator_in_progress.py` (236 lines, same allowlist). `test_gate_logic.py` is left untouched — permitted, since the callback gate needs a non-empty intersection with Allowed Files, not every entry. |
| D6 | Task 4 (now Task 5) "живая проверка" as a `test` task | EC-8 requires a real salvage-timeout on the live orchestrator + a subsequent dispatch cycle. Unreachable from inside the session under test. | Re-typed as a documented operator protocol appended to `## Autopilot Log`. Flagged in the return contract as `solution_verified: partial`. |

**Residual risks, accepted and named** (no code owed by this spec):
- `salvage.py:227` pushes without `--force-with-lease` and is **out of scope** (spec §Scope).
  The PHASE 0 re-sync push (Task 4 step 2) is what keeps origin and the rebased branch
  identical, so a second timeout still salvages fast-forward. Remove that push and the
  residual risk comes back.
- `claude-runner.py:557-579` passes a **closed env whitelist** to the SDK, and it is not in
  Allowed Files — so `CLAUDE_CONTINUE_BRANCH` may not reach the agent's own session env even
  though it reaches the pueue task process. The prompt therefore must not depend on it: step 5
  detects continuation itself with `git ls-remote`. The flag is telemetry and a future hook,
  not the mechanism.

---

## Flow Coverage Matrix

| # | Шаг | Covered by Task | Status |
|---|---|---|---|
| 1 | Прогон убит таймаутом, salvage пушит ветку | — | existing |
| 2 | Callback: ветка есть, не влита → `branch_pushed_not_merged:N` | Task 1, 2 | ✓ |
| 3 | PHASE 0 другого прогона не удаляет worktree этой спеки | Task 4 | ✓ |
| 4 | Оркестратор: `continue`, env-флаг | Task 2 | ✓ |
| 5 | Шаг 5: worktree из ветки, rebase, список сделанного | Task 4 | ✓ |
| 6 | Конфликт rebase → `needs_review` | Task 4 | ✓ |
| 6a | Rebase переписал коммиты → push ветки force-with-lease, salvage снова ff | Task 4 | ✓ |
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
1. EC-1..EC-3 → Task 1 (код) + Task 3 (тесты)
2. EC-4..EC-6 → Task 2 (код) + Task 3 (тесты)
3. EC-7 → Task 4 (промпты; ручной прогон на throwaway-репо, pass = HEAD == origin/<type>/<ID>)
4. EC-8 → Task 5 (не исполняется автопилотом — операторский протокол, см. Drift Log D6)

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
- [ ] EC-1..EC-6 проходят (`scripts/vps/tests/test_orchestrator_in_progress.py`)
- [ ] EC-7 прогнан вручную на throwaway-репо (Task 4)
- [ ] EC-8 задокументирован как операторский протокол в `## Autopilot Log` (Task 5, Drift Log D6)

### Acceptance Verification
- [ ] AV-S1, AV-F1 локально; AV-S2 не регрессирует (что он реально проверяет — Drift Log D4)
- [ ] AV-F2 (= EC-8) — за оператором, не в этом прогоне

### Technical
- [ ] `salvage.py`, `finishing.md` (`--ff-only`), `orchestrator.py`, `claude-runner.py` не изменены
- [ ] `gate_ancestry.py` ≤ 265, `callback_sync.py` ≤ 380, `orchestrator_queue.py` ≤ 400 LOC;
      тестовый файл < 600 (ceiling для тестов)

---

## Autopilot Log

### EC-8 — deferred to operator (manual)

Not runnable from an autopilot session: it needs a timeout-killed run on the live VPS.
Operator protocol, first spec that salvages after this lands:

1. `python3 scripts/vps/db.py ...` / `grep salvage scripts/vps/logs/<run>.log` — confirm
   `pushed: true` for `origin/<type>/<ID>`.
2. `cat ai/lifecycle/<ID>.yaml` → `blocked_reason` starts with `branch_pushed_not_merged:`
   (NOT `no_merged_implementation`).
3. `spec_operator.py` demote to `queued`, wait one orchestrator cycle, then
   `git -C .worktrees/<ID> log --oneline origin/develop..HEAD` — the salvaged commits are
   there and the run did not start from zero.
4. `grep 'continue dispatch' scripts/vps/logs/orchestrator.log` — one line for that spec.
5. If that run also dies: its salvage push must succeed (fast-forward), because PHASE 0
   force-with-lease-pushed the rebased branch before any work started.
