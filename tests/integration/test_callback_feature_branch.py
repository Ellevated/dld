"""BUG-1039 regression — feature-branch commits no longer trigger done.

2026-05-21 redesign: gate reads only origin/develop. Feature-branch commits
(not merged) must NOT produce done.

EC-1: commit only on feature/SPEC branch → blocked (BUG-1039 regression guard)
EC-2: commit on origin/develop with spec_id → done
EC-3: no commits anywhere → blocked
EC-4: db.log_task with branch kwarg → row persisted (orchestrator integration)
EC-5: db.log_task without branch → branch column NULL
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import db  # noqa: E402
import gate_logic  # noqa: E402
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
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "spec_id": spec_id,
        "status": "queued",
        "blocked_reason": None,
        "priority": "p1",
        "kind": "tech",
        "transitions": [],
        "version": 1,
        "started_at": None,
        "finished_at": None,
        "pueue_id": None,
        "allowed_files_hash": None,
        "updated_at": None,
        "updated_by": "test",
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
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md", f"ai/features/{spec_id}.md", "ai/lifecycle/.gitkeep")
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


# --- EC-1: feature-branch commit → blocked (BUG-1039 regression) -------------


def test_ec1_feature_branch_only_is_blocked(tmp_path, tmp_db, monkeypatch):
    """BUG-1039 regression: commit only on feature branch, not on origin/develop → blocked.

    Old --all gate produced false-done here. New gate reads origin/develop only.
    """
    spec_id = "TECH-901"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=901, branch=f"feature/{spec_id}")
    _seed_lifecycle_yaml(repo, spec_id)

    # feature-branch commit — does NOT reach origin/develop
    _git(repo, "checkout", "-q", "-b", f"feature/{spec_id}")
    _commit(repo, "src/x.py", "y=1\n", f"feat({spec_id}): work")
    _git(repo, "checkout", "-q", "develop")

    # find_implementation_commit sees only origin/develop → None
    monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
    monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a: None)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=901)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "blocked", (
        "feature-branch-only commit must NOT produce done (BUG-1039 regression)"
    )


# --- EC-2: commit on origin/develop → done -----------------------------------


def test_ec2_commit_on_origin_develop_is_done(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-902"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=902, branch=f"feature/{spec_id}")
    _seed_lifecycle_yaml(repo, spec_id)

    # Gate finds implementation on origin/develop
    monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
    monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a: "deadbee")

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=902)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "done"


# --- EC-3: no commits anywhere → blocked ------------------------------------


def test_ec3_no_commits_demotes(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-903"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=903, branch=f"feature/{spec_id}")
    _seed_lifecycle_yaml(repo, spec_id)

    monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
    monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a: None)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=903)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "blocked"
    assert "no_merged_implementation" in (data.get("blocked_reason") or "")


# --- EC-4, EC-5: db.log_task branch persistence ------------------------------


def test_ec4_log_task_persists_branch(tmp_db):
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("proj", "/tmp/ignored"),
        )
    db.log_task(
        "proj",
        "autopilot-TECH-904",
        "autopilot",
        "running",
        pueue_id=904,
        branch="feature/TECH-904",
    )
    with db.get_db() as conn:
        row = conn.execute("SELECT branch FROM task_log WHERE pueue_id = ?", (904,)).fetchone()
    assert row is not None
    assert row["branch"] == "feature/TECH-904"


def test_ec5_log_task_default_branch_is_null(tmp_db):
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("proj", "/tmp/ignored"),
        )
    db.log_task("proj", "qa-TECH-905", "qa", "running", pueue_id=905)
    with db.get_db() as conn:
        row = conn.execute("SELECT branch FROM task_log WHERE pueue_id = ?", (905,)).fetchone()
    assert row is not None
    assert row["branch"] is None
