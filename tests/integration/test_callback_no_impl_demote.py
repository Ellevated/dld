"""TECH-166 — integration tests for verify_status_sync demotion path.

Real fs + real git + real sqlite (no mocks per ADR-013). Each test sets up:
  - git project with spec file in ai/features/ and backlog.md
  - sqlite task_log entry with started_at predating any test commits
  - invokes callback.verify_status_sync(..., target='done', pueue_id=N)
"""

from __future__ import annotations

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
    _commit(repo, "README.md", "init\n", "init")
    return repo


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
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
    """Don't actually `git push origin develop` from tests (no remote)."""
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)


# --- EC-8 --------------------------------------------------------------------


def test_ec8_demote_when_no_impl_commits(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-998"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=42)
    time.sleep(1.1)
    # Only a doc commit lands — not an allowed file.
    _commit(repo, "docs/note.md", "n\n", "docs: note")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=42)

    spec_text = (repo / "ai" / "features" / f"{spec_id}.md").read_text()
    backlog_text = (repo / "ai" / "backlog.md").read_text()
    assert "**Status:** blocked" in spec_text
    assert "**Blocked Reason:** no_implementation_commits" in spec_text
    assert "| blocked |" in backlog_text
    assert "| done |" not in backlog_text


# --- EC-9 --------------------------------------------------------------------


def test_ec9_happy_path_with_impl_commit(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-997"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=43)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=2\n", "feat: x")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=43)

    spec_text = (repo / "ai" / "features" / f"{spec_id}.md").read_text()
    backlog_text = (repo / "ai" / "backlog.md").read_text()
    assert "**Status:** done" in spec_text
    assert "**Blocked Reason:**" not in spec_text
    assert "| done |" in backlog_text


# --- EC-10 -------------------------------------------------------------------


def test_ec10_blocked_overwrite_protection_compatible(tmp_path, tmp_db, monkeypatch):
    """If autopilot already wrote spec='blocked' (real reason), guard runs and
    flips target to blocked too; existing spec-blocked guard then short-circuits
    to resync. Net result: spec stays blocked, backlog resyncs to blocked.
    """
    spec_id = "TECH-996"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    spec_path = repo / "ai" / "features" / f"{spec_id}.md"
    # Autopilot pre-wrote blocked — and also committed a real file change
    # (so the impl-guard would let target=done through, isolating the
    # blocked-protection branch).
    spec_path.write_text(spec_path.read_text().replace("in_progress", "blocked"))
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=44)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=2\n", "feat: x")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=44)

    spec_text = spec_path.read_text()
    backlog_text = (repo / "ai" / "backlog.md").read_text()
    assert "**Status:** blocked" in spec_text
    assert "**Status:** done" not in spec_text
    assert "| blocked |" in backlog_text
