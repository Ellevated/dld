"""TECH-176 — integration tests for verify_status_sync auto-close path.

Auto-close fires when:
  - the activity-window guard (`_has_implementation_commits`) sees zero
    commits since `started_at`, AND
  - `_spec_has_merged_implementation` finds historical commits in the
    repo whose subject mentions the spec_id and that touch the spec's
    Allowed Files.

Real fs + real git + real sqlite (no mocks per ADR-013).
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
    r = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
        capture_output=True, text=True,
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
    monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False, raising=False)
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


def _seed_task(project_id: str, label: str, pueue_id: int) -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            (project_id, "/tmp/ignored"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, label, "autopilot", "running", pueue_id),
        )


def _suppress_push(monkeypatch):
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)


def _count_decisions(verdict: str, demoted: int | None = None) -> int:
    with db.get_db() as conn:
        if demoted is None:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM callback_decisions WHERE verdict = ?",
                (verdict,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM callback_decisions "
                "WHERE verdict = ? AND demoted = ?",
                (verdict, demoted),
            ).fetchone()
        return int(row["c"]) if row else 0


# --- EC-1 -------------------------------------------------------------------
# Pre-existing commit with spec_id in subject + zero activity since started_at
# → auto-close to done.

def test_ec1_already_merged_before_started_at_auto_close(tmp_path, tmp_db, monkeypatch, caplog):
    spec_id = "TECH-871"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    # Historical commit with spec_id in subject touching Allowed Files.
    _commit(repo, "src/x.py", "y=1\n", f"feat({spec_id}): real work")
    time.sleep(1.1)
    # Now seed the task — started_at is AFTER the commit above.
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=871)
    # No further commits — activity window is empty.
    _suppress_push(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="callback"):
        callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=871)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    backlog_text = _head_file(repo, "ai/backlog.md")
    assert spec_text is not None
    assert "**Status:** done" in spec_text, "auto-close should flip to done"
    assert "**Blocked Reason:**" not in spec_text
    assert "**Status:** blocked" not in spec_text
    assert backlog_text is not None
    assert "| done |" in backlog_text
    assert any("already merged" in rec.message and "auto-close" in rec.message
               for rec in caplog.records), "auto-close log line must fire"


# --- EC-2 -------------------------------------------------------------------
# Merge commit (`Merge TECH-XXX: ...`) on an Allowed File, no other activity
# → auto-close to done. Confirms `--grep` matches merge subjects too.

def test_ec2_merge_commit_subject_auto_close(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-872"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    # Simulate a squash-merge: commit on develop with "Merge TECH-XXX" subject
    # touching an Allowed File.
    _commit(repo, "src/x.py", "y=2\n", f"Merge {spec_id}: feature branch into develop")
    time.sleep(1.1)
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=872)
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=872)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    assert spec_text is not None
    assert "**Status:** done" in spec_text


# --- EC-3 -------------------------------------------------------------------
# Regression: zero commits anywhere (even historically) → still demotes.

def test_ec3_no_commits_anywhere_still_demotes(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-873"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=873)
    time.sleep(1.1)
    # Only a docs commit; nothing matches grep+allowed.
    _commit(repo, "docs/note.md", "n\n", f"docs: {spec_id} note only")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=873)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    backlog_text = _head_file(repo, "ai/backlog.md")
    assert spec_text is not None
    assert "**Status:** blocked" in spec_text
    assert "**Blocked Reason:** no_implementation_commits" in spec_text
    assert backlog_text is not None
    assert "| blocked |" in backlog_text


# --- EC-4 -------------------------------------------------------------------
# Subject mentions spec_id but commit touches only an UNALLOWED path → does
# NOT trigger auto-close (proves the `-- *allowed` filter actually filters).

def test_ec4_grep_matches_but_path_unallowed_demotes(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-874"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=874)
    time.sleep(1.1)
    # Subject mentions spec_id but file is NOT in Allowed Files.
    _commit(repo, "docs/random.md", "n\n", f"docs({spec_id}): outside allowlist")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=874)

    spec_text = _head_file(repo, f"ai/features/{spec_id}.md")
    assert spec_text is not None
    assert "**Status:** blocked" in spec_text, \
        "grep-only match without Allowed Files touch must demote, not auto-close"
    assert "**Blocked Reason:** no_implementation_commits" in spec_text


# --- EC-5 -------------------------------------------------------------------
# Deterministic: auto-close writes verdict='auto_close', demoted=0, NOT counted
# by count_demotes_since (so circuit-breaker is unaffected).

def test_ec5_auto_close_decision_not_counted_by_circuit(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-875"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _commit(repo, "src/x.py", "y=1\n", f"feat({spec_id}): historical work")
    time.sleep(1.1)
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=875)
    _suppress_push(monkeypatch)

    # Snapshot demote count before.
    demotes_before = db.count_demotes_since(callback.CIRCUIT_WINDOW_MIN)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=875)

    # 1. auto_close row exists, demoted=0.
    assert _count_decisions("auto_close", demoted=0) == 1, \
        "auto_close decision row missing"
    # 2. No demote row written.
    assert _count_decisions("demote") == 0, \
        "auto_close path must not record demote"
    # 3. count_demotes_since unchanged → circuit threshold not advanced.
    demotes_after = db.count_demotes_since(callback.CIRCUIT_WINDOW_MIN)
    assert demotes_after == demotes_before, \
        "auto_close must not count toward circuit-breaker threshold"
