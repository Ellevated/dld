# Tech: [TECH-182] Orchestrator git rebase --autostash теряет uncommitted файлы
<!-- DLD-CALLBACK-MARKER-START v1 -->
**Status:** done | **Priority:** P1 | **Date:** 2026-05-10

## ACTION REQUIRED (autopilot 2026-05-10)

Спека лежит в репо `awardybot`, но `Allowed Files` указывают на `scripts/vps/orchestrator.py` и `scripts/vps/callback.py` — это файлы из **другого репозитория** (`/home/dld/projects/dld`, remote `Ellevated/dld`). В `awardybot` `scripts/vps/` отсутствует, autopilot не может закоммитить фикс в текущий репо.

**Что нужно от человека (выбрать один путь):**
1. Перенести спеку в репо `dld` (`/home/dld/projects/dld/ai/features/`) и запустить autopilot оттуда; либо
2. Подтвердить, что фикс делается вручную в репо `dld`, а в backlog awardybot спеку закрыть как «moved».

Plan уже сгенерирован планером (см. ниже) и валиден против `/home/dld/projects/dld/scripts/vps/*` — после перемещения спеки можно сразу запускать coder.
<!-- DLD-CALLBACK-MARKER-END -->

## Why

`orchestrator.py` при `git_pull` использует `git rebase --autostash`. Если в рабочем дереве есть uncommitted изменения (например, callback только что записал строки в `ai/backlog.md` через `write_text`), `--autostash` прячет их в stash, применяет rebase, затем делает `stash pop`. При конфликте `stash pop` не применяется — данные остаются в stash, рабочее дерево возвращается к состоянию remote.

**Задокументированный инцидент (2026-05-10):** BUG-972 и BUG-973 были созданы коммитом `66d97b89`, но после нескольких циклов rebase пропали из HEAD develop. Потребовалось ручное `git cherry-pick` для восстановления.

## Root Causes

**BUG-1 (критический):** `orchestrator.py` строки 232–233:
```python
_git("fetch", "origin", "develop", ...)
_git("rebase", "--autostash", "origin/develop", ...)
```
При конфликте stash pop → `rebase --abort` в except откатывает rebase, но **не восстанавливает stash**. Данные теряются.

**BUG-2 (высокий):** `callback.py` функция `_append_blocked_reason` пишет в working tree через `spec_path.write_text()` — uncommitted изменение, уязвимое к BUG-1.

**BUG-3 (средний):** `_git_commit_push` в callback.py не логирует ошибку `git push` — локальный коммит без remote push + следующий rebase = потенциальный конфликт.

## Scope

1. **`scripts/vps/orchestrator.py`** — заменить `rebase --autostash` на безопасный pull:
   - Если `git diff --quiet` == 0 (чистое дерево): `git pull --ff-only origin develop`
   - Если грязное дерево: логировать warning, пропустить pull в этом цикле (не пытаться autostash)
   - Удалить ветку с `rebase --autostash`

2. **`scripts/vps/callback.py`** — функция `_append_blocked_reason`:
   - Заменить `spec_path.write_text()` → запись через `_git_commit_push` plumbing путь (как остальные операции в callback)

3. **`scripts/vps/callback.py`** — функция `_git_commit_push`:
   - Добавить логирование ошибки `git push` (сейчас `subprocess.run` без check и без log)

4. **Тест:** unit-тест для orchestrator `git_pull` — имитировать грязное дерево, убедиться что данные не теряются.

## Allowed Files
<!-- callback-allowlist v1 -->
- `scripts/vps/orchestrator.py`
- `scripts/vps/callback.py`
- `scripts/vps/tests/test_orchestrator_git_pull.py`

## Drift Log

**Checked:** 2026-05-10 UTC
**Result:** no_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/orchestrator.py` | none — `git_pull` lives at lines 215–236, `rebase --autostash` exactly at line 233 (matches spec's "around 232–233") | none |
| `scripts/vps/callback.py` | none — `_append_blocked_reason` at lines 755–768 (uses `spec_path.write_text`); `_git_commit_push` at lines 469–528 (line 522 `git push` lacks log on failure) | none |
| `scripts/vps/tests/test_orchestrator_git_pull.py` | file does not yet exist (Task 4 creates it); sibling `tests/test_orchestrator.py` provides import-style precedent | none |

### References Updated
- (none — spec line numbers verified against current code)

> **Note:** `scripts/vps/` lives in the **DLD framework repo** (`/home/dld/projects/dld/`), not in the awardybot project tree. The TECH-182 worktree was created at `/home/dld/projects/awardybot-tech-974/` because that's where the spec was filed and triaged, but the implementation must be performed against `/home/dld/projects/dld/scripts/vps/*.py`. Coder MUST run all Edit/Read calls against `/home/dld/projects/dld/scripts/vps/` and commit there.

## Implementation Plan

### Task 1: orchestrator.py `git_pull` — replace `rebase --autostash` with safe pull

**Files:**
- Modify: `scripts/vps/orchestrator.py:215-236` (the entire `git_pull` function body)

**Context:**
The autostash branch (lines 232–233) silently destroys uncommitted work when `stash pop` conflicts. Replacement policy: pull only on a clean tree; on a dirty tree, log a warning and skip — let the operator (or a callback commit) clean it up next cycle. The `rebase --abort` cleanup in the except clause is no longer reachable once `rebase` is gone, so it must also be removed.

**Step 1: Read the current function**

Confirm exact current source (no edits in this step):

```python
# scripts/vps/orchestrator.py:215-236 (current)
def git_pull(project_id: str, project_dir: str) -> None:
    """Pull develop branch. Skip if agent running or not a git repo."""
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return
    if is_agent_running(project_id):
        log.info("skip git pull — agent running: %s", project_id)
        return

    def _git(*a, **kw):
        return subprocess.run(["git", "-C", project_dir] + list(a), capture_output=True, **kw)

    try:
        clean = _git("diff", "--quiet", timeout=30).returncode == 0
        staged = _git("diff", "--cached", "--quiet", timeout=30).returncode == 0
        if clean and staged:
            _git("pull", "--rebase", "origin", "develop", text=True, timeout=120, check=True)
        else:
            _git("fetch", "origin", "develop", timeout=60, check=True)
            _git("rebase", "--autostash", "origin/develop", text=True, timeout=120, check=True)
    except subprocess.CalledProcessError as exc:
        _git("rebase", "--abort", timeout=30)
        log.warning("git pull failed: %s — %s", project_dir, (exc.stderr or "")[:200])
```

**Step 2: Apply the edit**

Replace the body of `git_pull` (the part after the `_git` inner-helper definition, i.e. lines 226–236) with:

```python
    try:
        clean = _git("diff", "--quiet", timeout=30).returncode == 0
        staged = _git("diff", "--cached", "--quiet", timeout=30).returncode == 0
        if clean and staged:
            _git("pull", "--ff-only", "origin", "develop", text=True, timeout=120, check=True)
        else:
            log.warning(
                "git pull skipped — working tree dirty (clean=%s staged=%s) for %s; "
                "no autostash, data preserved",
                clean,
                staged,
                project_dir,
            )
    except subprocess.CalledProcessError as exc:
        log.warning("git pull failed: %s — %s", project_dir, (exc.stderr or "")[:200])
```

Final shape of the whole function after the edit:

```python
def git_pull(project_id: str, project_dir: str) -> None:
    """Pull develop branch. Skip if agent running, not a git repo, or working tree dirty.

    TECH-182: removed `rebase --autostash` — stash pop conflicts silently
    discarded uncommitted callback writes (BUG-972/BUG-973). Now pull is
    fast-forward-only on a clean tree, otherwise we log a warning and skip
    this cycle. No working-tree mutation under any failure mode.
    """
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return
    if is_agent_running(project_id):
        log.info("skip git pull — agent running: %s", project_id)
        return

    def _git(*a, **kw):
        return subprocess.run(["git", "-C", project_dir] + list(a), capture_output=True, **kw)

    try:
        clean = _git("diff", "--quiet", timeout=30).returncode == 0
        staged = _git("diff", "--cached", "--quiet", timeout=30).returncode == 0
        if clean and staged:
            _git("pull", "--ff-only", "origin", "develop", text=True, timeout=120, check=True)
        else:
            log.warning(
                "git pull skipped — working tree dirty (clean=%s staged=%s) for %s; "
                "no autostash, data preserved",
                clean,
                staged,
                project_dir,
            )
    except subprocess.CalledProcessError as exc:
        log.warning("git pull failed: %s — %s", project_dir, (exc.stderr or "")[:200])
```

Diff summary:
- `pull --rebase` → `pull --ff-only` on the clean-tree branch.
- `else` branch: removed both `_git("fetch", ...)` and `_git("rebase", "--autostash", ...)`; replaced with a single `log.warning(...)`.
- Removed `_git("rebase", "--abort", ...)` from the except clause (no rebase is in flight anymore).
- Updated the docstring to mention TECH-182.

**Step 3: Verify**

```bash
cd /home/dld/projects/dld
grep -n "autostash\|rebase --abort" scripts/vps/orchestrator.py
# Expected: no matches.

python3 -c "import ast; ast.parse(open('scripts/vps/orchestrator.py').read()); print('SYNTAX OK')"
# Expected: SYNTAX OK

ruff check scripts/vps/orchestrator.py
# Expected: no errors.
```

**Acceptance Criteria:**
- [ ] No `--autostash` token anywhere in `scripts/vps/orchestrator.py`.
- [ ] No `rebase --abort` token in `git_pull`.
- [ ] Clean-tree path uses `pull --ff-only origin develop`.
- [ ] Dirty-tree path emits `log.warning(...)` with both `clean` and `staged` flags and project_dir; does NOT call any state-mutating git command.
- [ ] `python3 -c "import ast; ast.parse(open('scripts/vps/orchestrator.py').read())"` exits 0.
- [ ] `ruff check scripts/vps/orchestrator.py` exits 0.

---

### Task 2: callback.py `_append_blocked_reason` — write via `_git_commit_push` plumbing instead of `write_text`

**Files:**
- Modify: `scripts/vps/callback.py:755-768` (entire `_append_blocked_reason` function)

**Context:**
`_append_blocked_reason` currently mutates the working tree via `spec_path.write_text(new_text)` (line 767). On the next orchestrator cycle, that uncommitted change becomes vulnerable to BUG-1 (stash-pop loss in autostash). Even though Task 1 removes the autostash, the callback path should still align with the established pattern in `_git_commit_push` / `_resync_backlog_to_spec` — read HEAD, compute new content, commit via plumbing (`hash-object` + `update-index --cacheinfo`), never touch the working tree. This makes the helper consistent with the rest of callback.py (TECH-167+) and immune to future regressions.

**Step 1: Read the current function**

```python
# scripts/vps/callback.py:755-768 (current)
def _append_blocked_reason(spec_path: Path, reason: str) -> bool:
    """Path-taking wrapper around _apply_blocked_reason — preserves the
    pre-TECH-167 helper signature used by existing unit tests.

    Reads spec_path, applies _apply_blocked_reason, writes back if changed.
    Idempotent: calling twice with the same reason produces only one
    `**Blocked Reason:**` line (re.subn count=1 ensures replacement, not
    append).
    """
    text = spec_path.read_text(errors="replace")
    changed, new_text = _apply_blocked_reason(text, reason)
    if changed and new_text != text:
        spec_path.write_text(new_text)
    return changed
```

**Step 2: Apply the edit**

Replace the function body with a HEAD-read + plumbing-commit flow that mirrors `_resync_backlog_to_spec` (lines 531–566):

```python
def _append_blocked_reason(spec_path: Path, reason: str) -> bool:
    """Append/replace **Blocked Reason:** line on a spec via git plumbing.

    TECH-182: switched from `spec_path.write_text(new_text)` (working-tree
    mutation, vulnerable to upstream rebase/stash data-loss) to the same
    HEAD-read + plumbing-commit path used by `_resync_backlog_to_spec` and
    `verify_status_sync`. Operator's uncommitted edits in the working tree
    are preserved; callback never touches them.

    Resolves spec_path against its enclosing project (walks up to find the
    `ai/features/` parent), reads the file at HEAD, applies
    `_apply_blocked_reason`, and commits + pushes via `_git_commit_push`.

    Returns True iff a commit was made (idempotent — calling twice with
    the same reason yields no second commit because HEAD content already
    matches).
    """
    # Walk up from spec_path to the project root (parent of ai/features/).
    project_root: Path | None = None
    for parent in spec_path.resolve().parents:
        if (parent / "ai" / "features").is_dir() and (parent / ".git").exists():
            project_root = parent
            break
    if project_root is None:
        log.warning(
            "BLOCKED_REASON: could not resolve project root for %s — skip",
            spec_path,
        )
        return False

    rel_path = str(spec_path.resolve().relative_to(project_root))
    head_text = _read_head_blob(str(project_root), rel_path)
    if head_text is None:
        log.warning(
            "BLOCKED_REASON: HEAD read failed for %s in %s — skip",
            rel_path,
            project_root,
        )
        return False

    changed, new_text = _apply_blocked_reason(head_text, reason)
    if not changed or new_text == head_text:
        return False

    # Best-effort spec_id for commit message — falls back to filename stem.
    spec_re = re.compile(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*")
    m = spec_re.search(spec_path.name)
    spec_id = m.group(0) if m else spec_path.stem

    _git_commit_push(str(project_root), spec_id, "blocked", [(rel_path, new_text)])
    return True
```

Diff summary vs. current (lines 755–768):
- Removed `spec_path.write_text(new_text)`.
- Added project-root resolution via `parents` walk (looks for sibling `ai/features/` + `.git`).
- Added HEAD read via `_read_head_blob` (already imported / defined above at line 421).
- Routed the write through `_git_commit_push` with a single `(rel_path, new_text)` tuple.
- Best-effort spec_id extraction for commit subject.

**Step 3: Verify**

```bash
cd /home/dld/projects/dld
grep -n "spec_path.write_text" scripts/vps/callback.py
# Expected: no matches (this was the only call site).

python3 -c "import ast; ast.parse(open('scripts/vps/callback.py').read()); print('SYNTAX OK')"
# Expected: SYNTAX OK.

ruff check scripts/vps/callback.py
# Expected: no errors.

# Existing test for _append_blocked_reason (if any) may need updating —
# the function signature is unchanged but the side-effect path is different.
# Run the callback test suite to surface any breakage:
cd /home/dld/projects/dld/scripts/vps
python3 -m pytest tests/test_callback.py -k blocked_reason -v
# Expected: tests pass OR fail with a clear "needs HEAD blob" message that
# we then patch in the same task.
```

**Acceptance Criteria:**
- [ ] `_append_blocked_reason` no longer calls `spec_path.write_text(...)`.
- [ ] `_append_blocked_reason` uses `_read_head_blob` and `_git_commit_push`.
- [ ] Function signature unchanged: `(spec_path: Path, reason: str) -> bool`.
- [ ] `grep -n "spec_path.write_text" scripts/vps/callback.py` returns 0 matches.
- [ ] `python3 -c "import ast; ast.parse(open('scripts/vps/callback.py').read())"` exits 0.
- [ ] `ruff check scripts/vps/callback.py` exits 0.
- [ ] Existing `tests/test_callback.py` either passes unchanged or is updated in a follow-up task with operator approval.

---

### Task 3: callback.py `_git_commit_push` — log error when `git push` fails

**Files:**
- Modify: `scripts/vps/callback.py:469-528` (specifically the trailing `subprocess.run(... push ...)` call at line 522)

**Context:**
`_git_commit_push` already logs failures of `hash-object` (lines 503–512) and `commit` (lines 514–521), but the final `git push` (line 522) is fire-and-forget. When push fails (network, stale ref, branch protection), the local `develop` accumulates an extra commit ahead of `origin/develop`; the next orchestrator cycle's `pull --ff-only` (Task 1) refuses to fast-forward, triggering the dirty-tree skip and stalling auto-fixes silently. Logging makes the failure visible in `callback-debug.log`.

**Step 1: Read the current tail**

```python
# scripts/vps/callback.py:521-528 (current)
        return
    subprocess.run(git + ["push", "origin", "develop"], capture_output=True, timeout=60)
    log.info(
        "STATUS_FIX: committed and pushed %s → %s (%d file(s), no working-tree mutation)",
        spec_id,
        target,
        len(fixes),
    )
```

**Step 2: Apply the edit**

Replace the unchecked `subprocess.run` + bare `log.info` with a return-code check that logs explicitly on failure:

```python
        return
    push = subprocess.run(
        git + ["push", "origin", "develop"],
        capture_output=True,
        timeout=60,
    )
    if push.returncode != 0:
        stderr = push.stderr or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        log.warning(
            "STATUS_FIX: push failed for %s (rc=%d): %s",
            spec_id,
            push.returncode,
            stderr.strip()[:200],
        )
        return
    log.info(
        "STATUS_FIX: committed and pushed %s → %s (%d file(s), no working-tree mutation)",
        spec_id,
        target,
        len(fixes),
    )
```

Diff summary:
- Captured `subprocess.run(...)` result into `push`.
- Added `if push.returncode != 0` branch that decodes stderr and logs `log.warning` (consistent with the commit-failure log shape on lines 516–520).
- Wrapped the success `log.info` so it only fires when push actually succeeded.
- No new imports needed (`subprocess`, `log` already at module top).

**Step 3: Verify**

```bash
cd /home/dld/projects/dld
grep -n "git + \[\"push\"" scripts/vps/callback.py
# Expected: 1 match — and line above it must be `push = subprocess.run(`.

grep -n "STATUS_FIX: push failed" scripts/vps/callback.py
# Expected: 1 match.

python3 -c "import ast; ast.parse(open('scripts/vps/callback.py').read()); print('SYNTAX OK')"
# Expected: SYNTAX OK.

ruff check scripts/vps/callback.py
# Expected: no errors.
```

**Acceptance Criteria:**
- [ ] `git push` return code is captured and checked.
- [ ] Failure path logs `STATUS_FIX: push failed for {spec_id} (rc={rc}): {stderr}` via `log.warning`.
- [ ] Success path `STATUS_FIX: committed and pushed ...` only fires on `rc == 0`.
- [ ] Existing logger `log` (defined at module level on line 29) is reused — no new logger instantiation.
- [ ] `python3 -c "import ast; ast.parse(open('scripts/vps/callback.py').read())"` exits 0.
- [ ] `ruff check scripts/vps/callback.py` exits 0.

---

### Task 4: Unit test — `tests/test_orchestrator_git_pull.py`

**Files:**
- Create: `scripts/vps/tests/test_orchestrator_git_pull.py`

**Context:**
Cement the safety contract introduced in Task 1: with a dirty working tree, `git_pull` MUST NOT issue any rebase/fetch/pull and MUST emit a warning. Tests stub `subprocess.run` (mirrors `tests/test_orchestrator.py` style) and assert (a) call sequence does not include `rebase`/`autostash`/`fetch`, (b) `log.warning` is called, (c) on a clean tree, exactly one `pull --ff-only origin develop` is issued.

**Step 1: Write the failing test**

Create `scripts/vps/tests/test_orchestrator_git_pull.py` with the following content:

```python
# scripts/vps/tests/test_orchestrator_git_pull.py
"""Unit tests for orchestrator.git_pull (TECH-182).

Guarantees:
  - On dirty working tree: pull is SKIPPED (no fetch, no rebase, no autostash).
  - On clean working tree: exactly one `pull --ff-only origin develop` runs.
  - No `rebase --autostash` is ever invoked under any branch.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import orchestrator  # noqa: E402


def _mk_run(returncodes_by_args):
    """Return a fake subprocess.run that picks return code by argv signature.

    `returncodes_by_args` is a list of (substring_marker, returncode) tuples
    matched against ' '.join(argv). First substring hit wins.
    """

    def _run(argv, *args, **kwargs):
        argv_str = " ".join(str(x) for x in argv)
        rc = 0
        for marker, ret in returncodes_by_args:
            if marker in argv_str:
                rc = ret
                break
        result = MagicMock()
        result.returncode = rc
        result.stdout = ""
        result.stderr = ""
        return result

    return _run


class TestGitPullDirtyTree:
    """When working tree has uncommitted changes: pull MUST be skipped."""

    def test_dirty_unstaged_skips_pull(self, tmp_path):
        """`diff` returns 1 (dirty unstaged) → no fetch, no rebase, log warning."""
        # Make project_dir look like a git repo
        (tmp_path / ".git").mkdir()

        # diff non-zero → dirty; diff --cached zero → no staged
        fake_run = _mk_run(
            [
                ("diff --cached", 0),  # staged clean
                ("diff", 1),  # unstaged dirty (must come AFTER --cached marker)
            ]
        )

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=fake_run) as run_mock,
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        # Collect every git invocation
        invocations = [
            " ".join(str(x) for x in c.args[0])
            for c in run_mock.call_args_list
            if c.args and isinstance(c.args[0], list)
        ]

        # Sanity: at minimum the two `diff` checks ran
        assert any("diff --quiet" in inv and "--cached" not in inv for inv in invocations)
        assert any("diff --cached" in inv for inv in invocations)

        # Forbidden tokens — these MUST NOT appear in any subprocess call
        for inv in invocations:
            assert "autostash" not in inv, f"autostash leaked into call: {inv}"
            assert "rebase" not in inv, f"rebase leaked into call: {inv}"
            assert "fetch" not in inv, f"fetch leaked into call: {inv}"
            assert "pull" not in inv, f"pull leaked into call (dirty tree): {inv}"

        # And the warning MUST have been emitted
        assert log_mock.warning.called, "expected log.warning on dirty tree"
        warning_args = log_mock.warning.call_args
        # First positional arg is the format string
        fmt = warning_args.args[0] if warning_args.args else ""
        assert "dirty" in fmt or "skipped" in fmt, f"unexpected warning fmt: {fmt}"

    def test_dirty_staged_only_skips_pull(self, tmp_path):
        """`diff --cached` returns 1 (dirty staged) → still skipped."""
        (tmp_path / ".git").mkdir()
        fake_run = _mk_run(
            [
                ("diff --cached", 1),  # staged dirty
                ("diff", 0),  # unstaged clean
            ]
        )
        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=fake_run) as run_mock,
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        invocations = [
            " ".join(str(x) for x in c.args[0])
            for c in run_mock.call_args_list
            if c.args and isinstance(c.args[0], list)
        ]
        for inv in invocations:
            assert "autostash" not in inv
            assert "rebase" not in inv
            assert "fetch" not in inv
            assert "pull" not in inv

        assert log_mock.warning.called


class TestGitPullCleanTree:
    """When working tree is clean: exactly one `pull --ff-only` runs."""

    def test_clean_tree_runs_ff_only(self, tmp_path):
        (tmp_path / ".git").mkdir()
        # Both diff probes return 0 → clean
        fake_run = _mk_run([("diff", 0)])

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=fake_run) as run_mock,
            patch("orchestrator.log"),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        invocations = [
            " ".join(str(x) for x in c.args[0])
            for c in run_mock.call_args_list
            if c.args and isinstance(c.args[0], list)
        ]

        # Exactly one pull, with --ff-only
        pulls = [inv for inv in invocations if " pull " in f" {inv} "]
        assert len(pulls) == 1, f"expected 1 pull, got {pulls}"
        assert "--ff-only" in pulls[0]
        assert "origin develop" in pulls[0]

        # Forbidden under any branch
        for inv in invocations:
            assert "autostash" not in inv
            assert "--rebase" not in inv  # we no longer use --rebase variant


class TestGitPullSkipped:
    """Pre-conditions short-circuit before subprocess is touched."""

    def test_no_git_dir_returns_early(self, tmp_path):
        """No .git/ directory → return without touching subprocess."""
        with (
            patch("orchestrator.subprocess.run") as run_mock,
            patch("orchestrator.is_agent_running", return_value=False),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))
        run_mock.assert_not_called()

    def test_agent_running_returns_early(self, tmp_path):
        """Agent already running → log info + return."""
        (tmp_path / ".git").mkdir()
        with (
            patch("orchestrator.is_agent_running", return_value=True),
            patch("orchestrator.subprocess.run") as run_mock,
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))
        run_mock.assert_not_called()
        assert log_mock.info.called
```

**Step 2: Verify test fails before Task 1 is applied**

(If Tasks 1 is already in place, skip this step — Task 4 may be implemented after Tasks 1–3.)

```bash
cd /home/dld/projects/dld/scripts/vps
python3 -m pytest tests/test_orchestrator_git_pull.py -v
# Expected (PRE-TASK-1): TestGitPullDirtyTree.* FAIL — current code calls
# `fetch` + `rebase --autostash` even on dirty tree, so the "fetch leaked"
# / "rebase leaked" / "autostash leaked" assertions fire.
```

**Step 3: Verify test passes after Task 1**

```bash
cd /home/dld/projects/dld/scripts/vps
python3 -m pytest tests/test_orchestrator_git_pull.py -v
# Expected:
#   PASSED test_dirty_unstaged_skips_pull
#   PASSED test_dirty_staged_only_skips_pull
#   PASSED test_clean_tree_runs_ff_only
#   PASSED test_no_git_dir_returns_early
#   PASSED test_agent_running_returns_early
```

**Step 4: Lint**

```bash
ruff check scripts/vps/tests/test_orchestrator_git_pull.py
# Expected: no errors.
```

**Acceptance Criteria:**
- [ ] File `scripts/vps/tests/test_orchestrator_git_pull.py` exists.
- [ ] All 5 test cases pass against the post-Task-1 `git_pull`.
- [ ] Tests stub `subprocess.run` via `unittest.mock.patch` (no real git invocations).
- [ ] Dirty-tree tests assert NO `autostash`, NO `rebase`, NO `fetch`, NO `pull` token in any subprocess call.
- [ ] Dirty-tree tests assert `log.warning` was called and the format string mentions "dirty" or "skipped".
- [ ] Clean-tree test asserts exactly one `git pull --ff-only origin develop` invocation.
- [ ] `ruff check scripts/vps/tests/test_orchestrator_git_pull.py` exits 0.
- [ ] No mocks of internal logic beyond `subprocess.run`, `is_agent_running`, and `log` — keeps the test focused on the safety contract.

---

### Execution Order

```
Task 1 (orchestrator.git_pull) ─┐
                                ├─→ Task 4 (test_orchestrator_git_pull.py)
Task 3 (callback._git_commit_push push logging) ─┘ (independent, parallel-safe)

Task 2 (callback._append_blocked_reason) — depends on nothing in this scope
```

Recommended sequencing for one commit per task:

1. **Task 1** — orchestrator.py git_pull rewrite. Commit: `fix(TECH-182): replace rebase --autostash with safe ff-only pull (orchestrator.py)`.
2. **Task 4** — test_orchestrator_git_pull.py. Commit: `test(TECH-182): unit tests for orchestrator.git_pull dirty-tree safety`.
3. **Task 3** — callback.py push logging. Commit: `fix(TECH-182): log git push failures in _git_commit_push (callback.py)`.
4. **Task 2** — callback.py _append_blocked_reason via plumbing. Commit: `fix(TECH-182): route _append_blocked_reason through git plumbing (callback.py)`.

### Dependencies

- **Task 4 → Task 1**: tests assert the new behaviour; without Task 1 the dirty-tree assertions fail (this is the TDD red→green checkpoint).
- **Task 2** is independent of the others — it can ship before or after Task 1, but landing it after Task 1 means the safety net is in place by the time the new write path is exercised in production.
- **Task 3** is independent — adds observability only.
- All four tasks live in the **DLD framework repo** (`/home/dld/projects/dld/`). Coder must `cd /home/dld/projects/dld` before applying edits and committing. The commit branch in that repo is whatever the operator has checked out (typically `develop`); do NOT push to `main`.

### Research Sources

- Git docs — `git pull --ff-only` semantics (refuses non-fast-forward merges; safe default for poll-loop daemons).
- Internal pattern reference: `_resync_backlog_to_spec` (callback.py:531–566) — canonical HEAD-read + plumbing-commit flow that Task 2 mirrors.
- Internal pattern reference: `_git_commit_push` commit-failure log (callback.py:516–520) — shape Task 3's push-failure log copies.
- Test scaffolding reference: `tests/test_orchestrator.py` (`unittest.mock.patch` pattern with `orchestrator.subprocess.run`) — Task 4 follows the same import/patching style.
