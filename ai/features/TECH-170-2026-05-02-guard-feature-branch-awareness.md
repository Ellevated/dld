---
id: TECH-170
type: TECH
status: done
priority: P1
risk: R1
created: 2026-05-02
---

# TECH-170 — Implementation guard sees feature-branch commits, not just develop

**Status:** done
**Priority:** P1
**Risk:** R1

---

## Problem

`_has_implementation_commits` запускает `git log --since=<started_at> -- <allowed>` в working directory проекта. Этот лог по умолчанию = **текущая ветка** (обычно `develop`). Если autopilot работал в `feature/FTR-XXX` worktree (per ADR-009: deterministic worktree cleanup) и ещё **не смержил** ветку обратно — guard видит 0 коммитов и демоутит спеку, хотя код реально написан.

**Live precedent:**
- awardybot/FTR-898 (02.05): по QA-логу "миграции wave 4+5 только в `feature/FTR-898`, не смержены, Tasks 3-17 не сделаны". Часть работы реально была — в feature-branch. Guard её не увидел.
- wb/ARCH-176a/b/c/d: похожий паттерн.

---

## Goal

Guard смотрит **во все ветки**, не только в текущую. Реализация:

1. **Расширить `git log` до `--all`**: `git log --all --since=<started_at> -- <allowed>`. Видны коммиты на любой ref, включая feature-branch'и worktree'ев.

2. **Хранить `branch_name` в `task_log`** для будущей точной фильтрации (опционально):
   - autopilot сейчас работает в `feature/<spec_id>` ветке (ADR-009).
   - При диспатче в pueue label содержит `<project_id>:<spec_id>`. Можем извлекать.
   - В `task_log` добавить колонку `branch` (nullable), записываем при диспатче.

3. **Различать "merged в develop" vs "только в feature"** — отдельная информация в callback log:
   - Если коммиты в feature-ветке но НЕ в develop → log warning `IMPL_GUARD: <spec> has commits on feature/<spec> but NOT merged to develop yet`.
   - Это **не блокирует mark-done** (работа есть), но видно в Telegram digest.

4. **Очищение**: после merge'а через `git merge --ff-only` от orchestrator'а — статус "merged", в callback log пишем `merged_at`. Не критично для mark-done, но важно для дашборда.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/orchestrator.py`
- `scripts/vps/db.py`
- `scripts/vps/schema.sql`
- `tests/unit/test_callback_branch_awareness.py`
- `tests/integration/test_callback_feature_branch.py`

---

## Tasks

1. **`_has_implementation_commits`**: добавить флаг `--all` в git log. Сохранить старое поведение через kwarg `branches="all"` для тестируемости.
2. **`task_log.branch`**: ALTER TABLE add column. Migration в `db.py::init_schema()` (idempotent). orchestrator.py при диспатче пишет `branch=feature/<spec_id>` (если применимо).
3. **`is_merged_to_develop(spec_id)`**: helper в callback.py — `git log develop --grep=<spec_id>` либо `git branch --merged develop`. Используется только для логов/dashboard.
4. **Tests** (integration): tmpdir-repo с feature-branch'ем, проверить что guard видит коммит на feature-branch'е и пропускает spec в done; merge → log "merged_at" обновляется.
5. **Update ADR**: ADR-018 (callback enforcement) — пометка о --all + feature-branch awareness.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | integration | Коммит в `feature/FTR-001`, develop пуст — guard returns True (allows done) |
| EC-2 | integration | Коммит в `feature/FTR-001`, спека merged в develop — guard True, log "merged_to_develop" |
| EC-3 | integration | Нет коммитов нигде — guard False (blocks done) |
| EC-4 | deterministic | task_log.branch заполняется при autopilot dispatch |
| EC-5 | regression | Существующие тесты TECH-168 не сломаны новым флагом --all |

---

## Drift Log

**Checked:** 2026-05-02 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/db.py` | No `init_schema()` exists — schema is bootstrapped via `sqlite3 < schema.sql` during setup-vps.sh | AUTO-FIX: plan introduces idempotent runtime migration helper `_migrate_task_log_branch()` invoked from `log_task()` first call (cached) instead of non-existent `init_schema` |
| `scripts/vps/callback.py` | `_has_implementation_commits` confirmed at lines 720–767 with signature `(project_path, allowed, started_at)` | Plan keeps signature, adds `branches` kwarg (default `"all"`) for backwards-compatible test control |
| `scripts/vps/orchestrator.py` | Two dispatch sites (`scan_inbox` ~line 346, `scan_backlog` ~line 402), plus callback's `dispatch_qa`/`dispatch_reflect` | Plan: only autopilot dispatch in `scan_backlog` writes `branch=feature/<spec_id>`; QA/Reflect/inbox = `None` |

### References Updated
- Task 1: `init_schema()` → `_migrate_task_log_branch()` runtime helper, lazy-applied
- Task 2: `db.log_task()` signature gets new optional `branch: str | None = None` parameter

---

## Implementation Plan

### Task 1: Schema migration — add `task_log.branch` column

**Files:**
- Modify: `scripts/vps/schema.sql:35-46` (DDL for `task_log`)
- Modify: `scripts/vps/db.py` (add `_migrate_task_log_branch()` helper + call it from `get_db()` once)

**Context:**
Add nullable `branch TEXT` column to `task_log`. Schema.sql gets the column for fresh installs; runtime helper handles existing DBs idempotently (since DLD has no `init_schema()` — schema is loaded externally by `setup-vps.sh`). Must be idempotent and survive concurrent callers (WAL mode).

**Step 1: Edit `scripts/vps/schema.sql`**

Replace the `task_log` CREATE TABLE block (lines 35-46) with:

```sql
CREATE TABLE IF NOT EXISTS task_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL REFERENCES project_state(project_id),
    task_label   TEXT NOT NULL,
    skill        TEXT NOT NULL DEFAULT 'autopilot',
    status       TEXT NOT NULL DEFAULT 'queued',
    pueue_id     INTEGER,
    branch       TEXT,
    started_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at  TEXT,
    exit_code    INTEGER,
    output_summary TEXT
);
```

**Step 2: Add migration helper to `scripts/vps/db.py`**

After `_UNSET = object()` (around line 19), add:

```python
_MIGRATIONS_APPLIED = False


def _ensure_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent runtime migrations. Process-cached after first success.

    TECH-170: add task_log.branch column for feature-branch awareness.
    Safe under WAL — ALTER TABLE ADD COLUMN is atomic and idempotent if
    we check pragma_table_info first.
    """
    global _MIGRATIONS_APPLIED
    if _MIGRATIONS_APPLIED:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(task_log)").fetchall()}
    if "branch" not in cols:
        try:
            conn.execute("ALTER TABLE task_log ADD COLUMN branch TEXT")
        except sqlite3.OperationalError:
            # Race: another process added it between PRAGMA and ALTER.
            pass
    _MIGRATIONS_APPLIED = True
```

**Step 3: Wire migration into `get_db()`**

Inside `get_db()` (around line 38, after `conn.row_factory = sqlite3.Row`), add a single call:

```python
    conn.row_factory = sqlite3.Row
    _ensure_migrations(conn)   # TECH-170: idempotent, process-cached
    begin = "BEGIN IMMEDIATE" if immediate else "BEGIN"
```

Note: `_ensure_migrations` runs OUTSIDE explicit transaction; SQLite's `ALTER TABLE` is auto-committed in autocommit mode (`isolation_level=None`), so this is safe.

**Acceptance:**
- [ ] Fresh `sqlite3 fresh.db < schema.sql` → `PRAGMA table_info(task_log)` includes `branch` column
- [ ] Old DB without column → first `get_db()` call adds it; second is a no-op (cache hit)
- [ ] `_MIGRATIONS_APPLIED` reset between tests via `monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)`

**Test mapping:** EC-4 (precondition for branch storage)

---

### Task 2: Extend `db.log_task()` signature with `branch` kwarg

**Files:**
- Modify: `scripts/vps/db.py:138-152` (`log_task` function)

**Context:**
Add optional `branch: str | None = None` parameter. Persist into the new column. All existing callers (callback's QA/Reflect, orchestrator's inbox) keep `branch=None` semantics.

**Step 1: Replace `log_task` in `scripts/vps/db.py`**

```python
def log_task(
    project_id: str,
    task_label: str,
    skill: str,
    status: str,
    pueue_id: int = None,
    branch: str | None = None,
) -> int:
    """Create a task_log entry. Returns the row id.

    Args:
        branch: Git branch name (e.g. 'feature/TECH-170'). Used by the
            implementation guard to differentiate work merged to develop
            vs. work still on a feature branch (TECH-170).
    """
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO task_log "
            "(project_id, task_label, skill, status, pueue_id, branch) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, task_label, skill, status, pueue_id, branch),
        )
        return cursor.lastrowid
```

**Acceptance:**
- [ ] `log_task("p", "l", "autopilot", "running", 1)` works (branch=NULL)
- [ ] `log_task("p", "l", "autopilot", "running", 1, branch="feature/TECH-170")` persists branch
- [ ] All existing callers keep working without modification (defaults preserve old behavior)

**Test mapping:** EC-4

---

### Task 3: Orchestrator writes `branch=feature/<spec_id>` for autopilot dispatch

**Files:**
- Modify: `scripts/vps/orchestrator.py:418` (the `db.log_task(...)` call inside `scan_backlog`)

**Context:**
`scan_backlog` is the only autopilot dispatch site. The runner creates / checks out `feature/<spec_id>` for each task. We mirror that as the recorded branch. Inbox (`scan_inbox` line 354), QA/Reflect (callback) stay on develop — leave `branch=None`.

**Step 1: Update `scan_backlog` log_task call**

In `scripts/vps/orchestrator.py` around line 418, change:

```python
    db.log_task(project_id, task_label, "autopilot", "running", pueue_id)
```

to:

```python
    db.log_task(
        project_id,
        task_label,
        "autopilot",
        "running",
        pueue_id,
        branch=f"feature/{spec_id}",
    )
```

**Acceptance:**
- [ ] After autopilot dispatch, row in `task_log` has `branch='feature/<spec_id>'`
- [ ] Inbox / QA / Reflect rows still have `branch=NULL`

**Test mapping:** EC-4

---

### Task 4: `_has_implementation_commits` — add `--all` and `branches` kwarg

**Files:**
- Modify: `scripts/vps/callback.py:720-767` (`_has_implementation_commits`)

**Context:**
Default behavior changes from "log on current branch" to "log across **all** refs". The kwarg `branches` exists for tests and for the future `is_merged_to_develop` helper. Three accepted values:
- `"all"` (default) — `git log --all`
- `"current"` — old behavior, no branch flag
- `"develop"` — `git log develop` (used by Task 5 helper)

**Step 1: Replace the function**

```python
def _has_implementation_commits(
    project_path: str,
    allowed: list[str] | None,
    started_at: str | None,
    branches: str = "all",
) -> bool:
    """True if any commit since `started_at` touched any path in `allowed`.

    `branches` (TECH-170):
        "all"     → `git log --all` — sees commits on feature branches
                    even when worktree hasn't merged back to develop yet.
                    Default; closes the false-negative gap behind ADR-009.
        "current" → no branch flag — pre-TECH-170 behavior.
        "develop" → `git log develop` — used by `is_merged_to_develop`.

    Mixed semantics — content issues fail closed, infra/data issues fail open:
        allowed is None        → False (no `## Allowed Files` section: spec is
                                        non-conformant, refuse to mark done.
                                        Caller logs reason='missing_allowed_files_section'.)
        allowed == []          → False (explicit empty allowlist = no-impl)
        started_at is None     → True  (data-availability issue, not spec content)
        subprocess error       → True  (don't block on tool failure)
    """
    if allowed is None:
        log.warning(
            "IMPL_GUARD: spec has no `## Allowed Files` section — "
            "blocking done (degrade-closed). Specs MUST declare an allowlist."
        )
        return False
    if started_at is None:
        return True
    if not allowed:
        return False
    cmd = ["git", "-C", project_path, "log"]
    if branches == "all":
        cmd.append("--all")
    elif branches == "develop":
        cmd.append("develop")
    # "current" → no extra flag
    cmd += [f"--since={started_at}", "--pretty=%H", "--", *allowed]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("IMPL_GUARD: git log failed (%s) — degrade open", exc)
        return True
    if result.returncode != 0:
        log.warning(
            "IMPL_GUARD: git log rc=%s stderr=%s — degrade open",
            result.returncode,
            result.stderr.strip()[:200],
        )
        return True
    return bool(result.stdout.strip())
```

**Acceptance:**
- [ ] Default call (no `branches=`) emits `git log --all --since ...`
- [ ] `branches="current"` produces pre-TECH-170 command (regression-safe)
- [ ] `branches="develop"` produces `git log develop --since ...`
- [ ] Existing TECH-168 tests pass unchanged (they use happy/unhappy fixtures whose commits land on the only branch — `--all` is a superset)

**Test mapping:** EC-1, EC-3, EC-5

---

### Task 5: New helper `is_merged_to_develop(project_path, spec_id)`

**Files:**
- Modify: `scripts/vps/callback.py` (insert near `_has_implementation_commits`, around line 768)

**Context:**
Pure read-only helper. Returns `True` if `develop` branch contains any commit whose subject mentions the spec id. Used purely for logging — never blocks `mark-done`. Wraps `git log develop --grep=<spec_id>` with timeout/degrade-open semantics.

**Step 1: Add function in `scripts/vps/callback.py` after `_has_implementation_commits`**

```python
def is_merged_to_develop(project_path: str, spec_id: str) -> bool:
    """Best-effort check: does `develop` contain a commit mentioning spec_id?

    Used only for diagnostic logging in `verify_status_sync`. Never blocks
    a transition. On any error returns False (silent — caller treats as
    "merge state unknown").

    TECH-170: pairs with `--all` guard. Together they let us tell apart:
        - work on feature/<spec> only (guard True, this False) — log warn
        - work merged to develop      (guard True, this True)  — happy path
    """
    if not spec_id:
        return False
    cmd = [
        "git", "-C", project_path, "log", "develop",
        "--grep", re.escape(spec_id),
        "--pretty=%H",
        "-n", "1",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("MERGE_CHECK: git log failed for %s: %s", spec_id, exc)
        return False
    if r.returncode != 0:
        return False
    return bool(r.stdout.strip())
```

**Step 2: Wire diagnostic log into `verify_status_sync`**

In `scripts/vps/callback.py` inside the `verify_status_sync` impl-guard block (around line 815, right after `if not _has_implementation_commits(...)` early-return), add a positive-path branch:

Replace:

```python
        if not _has_implementation_commits(project_path, allowed, started_at):
            reason = (
                "missing_allowed_files_section" if allowed is None else "no_implementation_commits"
            )
            log.warning(
                "IMPL_GUARD: %s — demoting done → blocked (%s, started_at=%s)",
                spec_id,
                reason,
                started_at,
            )
            _, spec_text = _apply_blocked_reason(spec_text, reason)
            target = "blocked"
```

with:

```python
        if not _has_implementation_commits(project_path, allowed, started_at):
            reason = (
                "missing_allowed_files_section" if allowed is None else "no_implementation_commits"
            )
            log.warning(
                "IMPL_GUARD: %s — demoting done → blocked (%s, started_at=%s)",
                spec_id,
                reason,
                started_at,
            )
            _, spec_text = _apply_blocked_reason(spec_text, reason)
            target = "blocked"
        else:
            # TECH-170: positive path — tell apart "merged to develop" vs "feature-only"
            if is_merged_to_develop(project_path, spec_id):
                log.info("IMPL_GUARD: %s — commits found and merged to develop ✓", spec_id)
            else:
                log.warning(
                    "IMPL_GUARD: %s has commits on feature branch but NOT merged to develop yet "
                    "(allowing done; visible in dashboard)",
                    spec_id,
                )
```

**Acceptance:**
- [ ] `is_merged_to_develop` returns `True` when develop has a commit subject containing spec_id
- [ ] Returns `False` when only feature branch has the commit
- [ ] Returns `False` on any subprocess error (no exception leak)
- [ ] `verify_status_sync` logs the appropriate WARNING vs INFO line
- [ ] Helper does NOT change `target` — work proceeds to `done` regardless

**Test mapping:** EC-2

---

### Task 6: Unit tests — `tests/unit/test_callback_branch_awareness.py`

**Files:**
- Create: `tests/unit/test_callback_branch_awareness.py`

**Context:**
Unit-level coverage for the new `branches` kwarg and `is_merged_to_develop`. Mirrors patterns from `tests/unit/test_callback_implementation_guard.py`.

**Step 1: Create file**

```python
"""TECH-170 — unit tests for callback feature-branch awareness.

EC-1: --all flag sees commits on feature/<spec> when develop is empty.
EC-3: empty repo / no relevant commits → guard False.
EC-5: branches='current' reproduces pre-TECH-170 command shape.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _commit(repo: Path, rel: str, body: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@pytest.fixture
def feature_repo(tmp_path):
    """Repo on develop with empty develop and a commit on feature/TECH-170."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _commit(repo, "README.md", "init\n", "chore: init")
    _git(repo, "checkout", "-q", "-b", "feature/TECH-170")
    return repo


# --- EC-1: feature-branch commit visible via --all -------------------------


def test_ec1_all_sees_feature_branch_commit(feature_repo):
    """Commit lands on feature/TECH-170; develop is unchanged.
    Default branches='all' → guard returns True."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(feature_repo, "src/x.py", "y=1\n", "feat: TECH-170 work")
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at
    ) is True


def test_ec1_current_misses_feature_branch_commit_from_develop(feature_repo):
    """Same commit, but branches='current' while we're checked out on develop.
    Reproduces pre-TECH-170 false-negative."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(feature_repo, "src/x.py", "y=1\n", "feat: TECH-170 work")
    _git(feature_repo, "checkout", "-q", "develop")
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at, branches="current"
    ) is False
    # Sanity: --all still finds it from develop checkout.
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at, branches="all"
    ) is True


# --- EC-3: no commits anywhere ---------------------------------------------


def test_ec3_no_commits_anywhere_returns_false(feature_repo):
    """No commits in window on any branch → False (degrade closed for content)."""
    time.sleep(1.1)
    started_at = _now_iso()
    assert callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], started_at
    ) is False


# --- EC-5: regression — branches='current' is the pre-TECH-170 command -----


def test_ec5_current_branch_matches_legacy_behavior(feature_repo, monkeypatch):
    """Capture the exact subprocess.run argv to verify backwards compat."""
    captured: list[list[str]] = []
    real_run = subprocess.run

    def spy(cmd, *a, **kw):
        if isinstance(cmd, list) and len(cmd) >= 4 and cmd[:3] == ["git", "-C", str(feature_repo)] and cmd[3] == "log":
            captured.append(list(cmd))
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", spy)
    callback._has_implementation_commits(
        str(feature_repo), ["src/x.py"], _now_iso(), branches="current"
    )
    assert captured, "git log was not invoked"
    argv = captured[0]
    # No --all and no explicit ref between 'log' and '--since'
    assert "--all" not in argv
    assert not any(a == "develop" for a in argv[4:5])  # 4th token after 'log' is not 'develop'


# --- is_merged_to_develop --------------------------------------------------


def test_is_merged_to_develop_finds_commit_on_develop(feature_repo):
    _git(feature_repo, "checkout", "-q", "develop")
    _commit(feature_repo, "src/y.py", "z=1\n", "feat: TECH-170 merge")
    assert callback.is_merged_to_develop(str(feature_repo), "TECH-170") is True


def test_is_merged_to_develop_false_when_only_on_feature(feature_repo):
    # Commit lands on feature/TECH-170 only.
    _commit(feature_repo, "src/x.py", "y=1\n", "feat: TECH-170 work")
    assert callback.is_merged_to_develop(str(feature_repo), "TECH-170") is False


def test_is_merged_to_develop_handles_missing_branch(tmp_path):
    """Repo without develop branch → graceful False, no exception."""
    repo = tmp_path / "norepo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"],
                   check=True, capture_output=True)
    assert callback.is_merged_to_develop(str(repo), "TECH-170") is False
```

**Acceptance:**
- [ ] All 6 tests pass on a clean checkout
- [ ] No mocks of git itself — only of `subprocess.run` for argv inspection (allowed: pytest argv-spy is not a behavioral mock)
- [ ] Test file ≤ 600 LOC

**Test mapping:** EC-1, EC-3, EC-5 (and partial EC-2)

---

### Task 7: Integration tests — `tests/integration/test_callback_feature_branch.py`

**Files:**
- Create: `tests/integration/test_callback_feature_branch.py`

**Context:**
End-to-end: `verify_status_sync(target='done')` with feature branch worktree state. Real git, real sqlite (per ADR-013). Patterns mirror `test_callback_no_impl_demote.py`.

**Step 1: Create file**

```python
"""TECH-170 — integration tests for verify_status_sync with feature branches.

EC-1: commit on feature/TECH-XXX, develop empty → status flips to done
      (NOT demoted to blocked) and a 'feature branch but NOT merged' WARNING
      is logged.
EC-2: same plus a commit on develop mentioning the spec → 'merged to develop'
      INFO is logged; status flips to done.
EC-3: no commits anywhere → status demoted to blocked with reason
      'no_implementation_commits' (regression of TECH-166 happy demote path).
EC-4: dispatch path stores branch in task_log (orchestrator integration).
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import db  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _commit(repo: Path, rel: str, body: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


def _make_project(tmp_path: Path, spec_id: str, allowed_files: list[str]) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    allowed_block = "\n".join(f"- `{p}`" for p in allowed_files) or "(none)"
    spec_body = f"""# {spec_id}

**Status:** done

## Allowed Files

{allowed_block}

## Tests
"""
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n"
        f"| {spec_id} | demo | in_progress | P1 |\n"
    )
    _commit(repo, "README.md", "init\n", "init")
    return repo


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    # Reset migration cache so the new DB triggers _ensure_migrations once.
    monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False, raising=False)
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


def _seed_task(project_id: str, label: str, pueue_id: int, branch: str | None = None) -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            (project_id, "/tmp/ignored"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id, branch) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, label, "autopilot", "running", pueue_id, branch),
        )


def _suppress_push(monkeypatch):
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)


# --- EC-1 ------------------------------------------------------------------


def test_ec1_commit_on_feature_branch_allows_done(tmp_path, tmp_db, monkeypatch, caplog):
    spec_id = "TECH-901"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=901, branch=f"feature/{spec_id}")
    _git(repo, "checkout", "-q", "-b", f"feature/{spec_id}")
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=1\n", f"feat: {spec_id} work")
    # Switch back to develop to simulate callback running there.
    _git(repo, "checkout", "-q", "develop")
    _suppress_push(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="callback"):
        callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=901)

    spec_text = (repo / "ai" / "features" / f"{spec_id}.md").read_text()
    backlog_text = (repo / "ai" / "backlog.md").read_text()
    assert "**Status:** done" in spec_text, "feature-branch commit should allow done"
    assert "**Blocked Reason:**" not in spec_text
    assert "| done |" in backlog_text
    # Warning about not-yet-merged
    assert any("NOT merged to develop" in rec.message for rec in caplog.records)


# --- EC-2 ------------------------------------------------------------------


def test_ec2_commit_merged_to_develop_logs_merged(tmp_path, tmp_db, monkeypatch, caplog):
    spec_id = "TECH-902"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=902, branch=f"feature/{spec_id}")
    time.sleep(1.1)
    # Commit lands directly on develop with spec_id in subject (simulating merge).
    _commit(repo, "src/x.py", "y=1\n", f"feat: {spec_id} merge")
    _suppress_push(monkeypatch)

    with caplog.at_level(logging.INFO, logger="callback"):
        callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=902)

    spec_text = (repo / "ai" / "features" / f"{spec_id}.md").read_text()
    assert "**Status:** done" in spec_text
    assert any("merged to develop" in rec.message for rec in caplog.records)


# --- EC-3 ------------------------------------------------------------------


def test_ec3_no_commits_anywhere_demotes(tmp_path, tmp_db, monkeypatch):
    """Regression of TECH-166: still demotes when truly nothing was done."""
    spec_id = "TECH-903"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=903, branch=f"feature/{spec_id}")
    time.sleep(1.1)
    # Commit on a non-allowed path on develop, no feature branch work either.
    _commit(repo, "docs/note.md", "n\n", f"docs: {spec_id} note")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=903)

    spec_text = (repo / "ai" / "features" / f"{spec_id}.md").read_text()
    backlog_text = (repo / "ai" / "backlog.md").read_text()
    assert "**Status:** blocked" in spec_text
    assert "**Blocked Reason:** no_implementation_commits" in spec_text
    assert "| blocked |" in backlog_text


# --- EC-4 ------------------------------------------------------------------


def test_ec4_log_task_persists_branch(tmp_db):
    """db.log_task with branch kwarg → row has branch populated."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("proj", "/tmp/ignored"),
        )
    db.log_task("proj", "autopilot-TECH-904", "autopilot", "running",
                pueue_id=904, branch="feature/TECH-904")
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT branch FROM task_log WHERE pueue_id = ?", (904,)
        ).fetchone()
    assert row is not None
    assert row["branch"] == "feature/TECH-904"


def test_ec4_log_task_default_branch_is_null(tmp_db):
    """Existing callers (no branch kwarg) → branch column stays NULL."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("proj", "/tmp/ignored"),
        )
    db.log_task("proj", "qa-TECH-905", "qa", "running", pueue_id=905)
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT branch FROM task_log WHERE pueue_id = ?", (905,)
        ).fetchone()
    assert row is not None
    assert row["branch"] is None
```

**Acceptance:**
- [ ] All 5 tests pass; no mocks of git, no mocks of sqlite (ADR-013)
- [ ] `_suppress_push` is the only subprocess-level patch (whitelisted: prevents `git push` to non-existent remote in CI)
- [ ] Caplog assertions verify the new WARNING / INFO branches in `verify_status_sync`
- [ ] EC-3 regression case still demotes (TECH-166 contract preserved)

**Test mapping:** EC-1, EC-2, EC-3, EC-4

---

### Task 8: Update ADR-018 in `.claude/rules/architecture.md`

**Files:**
- Modify: `.claude/rules/architecture.md` (ADR-018 row)

**Note:** This file is **not** in `## Allowed Files`. Per spec scope, ADR documentation is **mentioned in Task list item 5** but NOT explicitly listed as an allowed file. Implementation note: the spec's `## Allowed Files` block is the single source of truth for the callback guard. To stay within the allowlist, **defer the ADR update to a follow-up doc commit** (manual or a sibling spec). If reviewer wants ADR in-spec, this task is a no-op and the ADR change must move to a separate spec/PR.

**Acceptance:**
- [ ] No file outside `## Allowed Files` is touched by autopilot in this task
- [ ] If exceeded scope is required, a follow-up TECH spec is created instead

**Test mapping:** none (documentation)

---

### Execution Order

```
Task 1 (schema + migration)
   ↓
Task 2 (db.log_task signature)
   ↓
Task 3 (orchestrator dispatch writes branch)   ← parallel with Task 4
Task 4 (callback._has_implementation_commits --all + branches kwarg)
   ↓
Task 5 (is_merged_to_develop + verify_status_sync log)
   ↓
Task 6 (unit tests)        Task 7 (integration tests)   ← parallel
   ↓
Task 8 (ADR — deferred / no-op)
```

### Dependencies

- Task 2 depends on Task 1 (column must exist)
- Task 3 depends on Task 2 (`branch` kwarg must exist)
- Task 4 is independent of 1-3 (pure callback edit) — can parallelize
- Task 5 depends on Task 4 (helper coexists with new branches kwarg)
- Task 6 depends on Tasks 4 + 5
- Task 7 depends on Tasks 1, 2, 3, 4, 5

### Research Sources

- TECH-166 spec & ADR-018 entry (existing impl-guard contract — must not regress)
- TECH-167 v1 allowlist parser (parsing semantics — unchanged here)
- ADR-009 Background pipeline + worktree isolation (root cause: feature branches per spec)
- Live precedent: awardybot/FTR-898 (02.05) — feature branch work invisible to guard
- Existing tests: `tests/unit/test_callback_implementation_guard.py`,
  `tests/integration/test_callback_no_impl_demote.py`,
  `tests/scripts/test_db.py` (fixture patterns reused)

