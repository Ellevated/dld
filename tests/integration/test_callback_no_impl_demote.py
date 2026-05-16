"""TECH-166 — integration tests for verify_status_sync demotion path.

ARCH-186: assertions rewritten to read from lifecycle.yaml (SoT).

Real fs + real git + real sqlite (no mocks per ADR-013). Each test sets up:
  - git project with spec file in ai/features/, backlog.md, ai/lifecycle/.gitkeep
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

import yaml  # noqa: E402

import yaml  # noqa: E402

import callback  # noqa: E402
import db  # noqa: E402
import lifecycle  # noqa: E402


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


def _seed_lifecycle_yaml(repo: Path, spec_id: str) -> None:
    """Write minimal lifecycle.yaml (status=queued) via normal git add+commit."""
    _seed_lifecycle_yaml_with_status(repo, spec_id, "queued")


def _seed_lifecycle_yaml_with_status(repo: Path, spec_id: str, status: str) -> None:
    """Write minimal lifecycle.yaml with given status via normal git add+commit."""
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "spec_id": spec_id, "status": status, "blocked_reason": None,
        "priority": "p1", "kind": "tech", "transitions": [], "version": 1,
        "started_at": None, "finished_at": None, "pueue_id": None,
        "allowed_files_hash": None, "updated_at": None, "updated_by": "test",
    }
    yaml_path = lc_dir / f"{spec_id}.yaml"
    yaml_path.write_text(yaml.safe_dump(data, default_flow_style=False, allow_unicode=True))
    _git(repo, "add", f"ai/lifecycle/{spec_id}.yaml")
    _git(repo, "commit", "-q", "-m", "chore: lifecycle test-seed")


def _make_project(tmp_path: Path, spec_id: str, allowed_files: list[str]) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("")
    allowed_block = "\n".join(f"- `{p}`" for p in allowed_files) or "(none)"
    spec_body = f"""# {spec_id}

**Status:** in_progress

## Allowed Files

{allowed_block}

## Tests
"""
    spec_rel = f"ai/features/{spec_id}.md"
    backlog_rel = "ai/backlog.md"
    (repo / spec_rel).write_text(spec_body)
    (repo / backlog_rel).write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n| {spec_id} | demo | in_progress | P1 |\n"
    )
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md", spec_rel, backlog_rel, "ai/lifecycle/.gitkeep")
    _git(repo, "commit", "-q", "-m", "init")
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

    # Pre-seed lifecycle so write_lifecycle(existing=...) path stores blocked_reason
    _seed_lifecycle_yaml(repo, spec_id)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=42)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None, "lifecycle.yaml must be written"
    assert data["status"] == "blocked"
    assert "no_implementation_commits" in (data.get("blocked_reason") or "")


# --- EC-9 --------------------------------------------------------------------


def test_ec9_happy_path_with_impl_commit(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-997"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=43)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=2\n", "feat: x")
    _suppress_push(monkeypatch)

    _seed_lifecycle_yaml(repo, spec_id)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=43)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None, "lifecycle.yaml must be written"
    assert data["status"] == "done"


# --- EC-10 -------------------------------------------------------------------


def test_ec10_blocked_overwrite_protection_compatible(tmp_path, tmp_db, monkeypatch):
    """lifecycle pre-seeded as blocked → verify_status_sync(target=done) keeps it blocked.

    Guard A in verify_status_sync: if existing_status == 'blocked' and target == 'done',
    skip mutation. Net result: lifecycle stays blocked.
    """
    spec_id = "TECH-996"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=44)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=2\n", "feat: x")
    _suppress_push(monkeypatch)

    # Pre-seed lifecycle.yaml as blocked via normal commit so it survives later writes
    _seed_lifecycle_yaml_with_status(repo, spec_id, "blocked")

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=44)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "blocked"
