"""verify_status_sync integration tests — 2026-05-21 redesign.

Gate: lifecycle.status = done iff origin/develop has a commit with
`<spec_id>:` in subject AND touching at least one allowed file.

ARCH-186: status lives in lifecycle.yaml (SoT), not markdown.
ADR-013: no mocks except for git I/O helpers (_fetch_develop, _is_done_on_develop).

EC-1: _is_done_on_develop=True  → status becomes done.
EC-2: _is_done_on_develop=False → status becomes blocked (no_merged_implementation).
EC-3: no ## Allowed Files section → blocked (missing_allowed_files).
EC-4: existing status=done (terminal) → noop (Rule 7).
EC-5: done verdict does NOT count as demote (circuit breaker unaffected).
"""

from __future__ import annotations

import logging
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


def _seed_lifecycle_yaml(repo: Path, spec_id: str, status: str = "queued") -> None:
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "spec_id": spec_id,
        "status": status,
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


def _count_decisions(verdict: str, demoted: int | None = None) -> int:
    with db.get_db() as conn:
        if demoted is None:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM callback_decisions WHERE verdict = ?",
                (verdict,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM callback_decisions WHERE verdict = ? AND demoted = ?",
                (verdict, demoted),
            ).fetchone()
        return int(row["c"]) if row else 0


# --- EC-1: gate=True → done --------------------------------------------------


def test_ec1_gate_true_becomes_done(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-871"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=871)
    _seed_lifecycle_yaml(repo, spec_id)

    monkeypatch.setattr(callback, "_fetch_develop", lambda *a: None)
    monkeypatch.setattr(callback, "_is_done_on_develop", lambda *a: True)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=871)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "done"


# --- EC-2: gate=False → blocked (no_merged_implementation) -------------------


def test_ec2_gate_false_becomes_blocked(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-872"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=872)
    _seed_lifecycle_yaml(repo, spec_id)

    monkeypatch.setattr(callback, "_fetch_develop", lambda *a: None)
    monkeypatch.setattr(callback, "_is_done_on_develop", lambda *a: False)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=872)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "blocked"
    assert "no_merged_implementation" in (data.get("blocked_reason") or "")


# --- EC-3: no ## Allowed Files → blocked (missing_allowed_files) -------------


def test_ec3_missing_allowed_files_blocks(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-873"
    repo = _make_project(tmp_path, spec_id, [])
    # Overwrite spec without any Allowed Files section
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(f"# {spec_id}\n\n## Tests\n")
    _git(repo, "add", f"ai/features/{spec_id}.md")
    _git(repo, "commit", "-q", "-m", "no-allowed-files-spec")
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=873)
    _seed_lifecycle_yaml(repo, spec_id)

    monkeypatch.setattr(callback, "_fetch_develop", lambda *a: None)
    monkeypatch.setattr(callback, "_is_done_on_develop", lambda *a: False)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=873)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "blocked"
    assert "missing_allowed_files" in (data.get("blocked_reason") or "")


# --- EC-4: existing=done → noop (Rule 7 terminal) ----------------------------


def test_ec4_done_is_terminal_noop(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-874"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=874)
    _seed_lifecycle_yaml(repo, spec_id, status="done")

    import subprocess as sp

    before = sp.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    monkeypatch.setattr(callback, "_fetch_develop", lambda *a: None)
    monkeypatch.setattr(callback, "_is_done_on_develop", lambda *a: False)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=874)

    after = sp.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    assert before == after, "done is terminal — no new commit expected"

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data["status"] == "done"


# --- EC-5: done does NOT count as demote (circuit breaker clean) -------------


def test_ec5_done_verdict_not_counted_as_demote(tmp_path, tmp_db, monkeypatch):
    spec_id = "TECH-875"
    repo = _make_project(tmp_path, spec_id, ["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=875)
    _seed_lifecycle_yaml(repo, spec_id)

    monkeypatch.setattr(callback, "_fetch_develop", lambda *a: None)
    monkeypatch.setattr(callback, "_is_done_on_develop", lambda *a: True)

    demotes_before = db.count_demotes_since(callback.CIRCUIT_WINDOW_MIN)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=875)

    demotes_after = db.count_demotes_since(callback.CIRCUIT_WINDOW_MIN)
    assert demotes_after == demotes_before, "done must not count toward circuit-breaker threshold"
    assert _count_decisions("demote") == 0
