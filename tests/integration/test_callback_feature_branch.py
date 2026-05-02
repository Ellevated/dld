"""TECH-170 — integration tests for verify_status_sync with feature branches.

EC-1: commit on feature/TECH-XXX, develop empty → status flips to done
      (NOT demoted to blocked) and a 'feature branch but NOT merged' WARNING
      is logged.
EC-2: same plus a commit on develop mentioning the spec → 'merged to develop'
      INFO is logged; status flips to done.
EC-3: no commits anywhere → status demoted to blocked with reason
      'no_implementation_commits' (regression of TECH-166 happy demote path).
EC-4: dispatch path stores branch in task_log (orchestrator integration).

Adaptation note (vs spec verbatim):
  _make_project now commits spec+backlog+README in one initial commit so that
  git show HEAD: resolves them. verify_status_sync reads exclusively from HEAD
  (not working tree); without this the guard condition `spec_text is not None`
  is never satisfied and no status flip occurs. Assertions read from HEAD too
  (via _head_file). Same pattern as test_callback_status_sync.py (TECH-168
  Task 5) which discovered this requirement first.
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


def _head_file(repo: Path, rel: str) -> str | None:
    """Read file content from git HEAD. None if not found."""
    r = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else None


def _make_project(tmp_path: Path, spec_id: str, allowed_files: list[str]) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    allowed_block = "\n".join(f"- `{p}`" for p in allowed_files) or "(none)"
    spec_body = f"""# {spec_id}

**Status:** in_progress

## Allowed Files

{allowed_block}

## Tests
"""
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n"
        f"| {spec_id} | demo | in_progress | P1 |\n"
    )
    # Commit README + spec + backlog so git show HEAD: resolves all three.
    # verify_status_sync reads spec/backlog from HEAD (not working tree) —
    # files not in HEAD are invisible to it (spec_head=None → guard skipped).
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md",
         f"ai/features/{spec_id}.md", "ai/backlog.md")
    _git(repo, "commit", "-q", "-m", "init")
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

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    backlog_text = _head_file(repo, "ai/backlog.md")
    assert spec_text is not None
    assert "**Status:** done" in spec_text, "feature-branch commit should allow done"
    assert "**Blocked Reason:**" not in spec_text
    assert backlog_text is not None
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

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    assert spec_text is not None
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

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    backlog_text = _head_file(repo, "ai/backlog.md")
    assert spec_text is not None
    assert "**Status:** blocked" in spec_text
    assert "**Blocked Reason:** no_implementation_commits" in spec_text
    assert backlog_text is not None
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
