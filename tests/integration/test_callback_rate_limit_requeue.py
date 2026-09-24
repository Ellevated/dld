"""TECH-225 — rate-limit requeue: DB counter (Task 3) + callback.main() (Task 4).

ADR-013: real sqlite + real git, no mocks. `tmp_db` is module-level so Task 4's
callback.main() tests reuse the same fixture (per the spec's Task 3 steps).

Eval Criteria:
  EC-10: count_requeues_since scopes by (project_id, spec_id, verdict='requeue',
         reason='rate_limited') and windows on `hours`.
  EC-8:  exit_code=5 → lifecycle queued, decision verdict='requeue', demoted=0.
  EC-9:  3rd requeue in 24h → lifecycle blocked repeated_rate_limit:3, verdict='demote'.
  EC-11: spec already done before callback → noop, no requeue row, sys.exit(0).
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
import event_writer  # noqa: E402
import lifecycle  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite DB isolated per test."""
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    db._MIGRATIONS_APPLIED = False
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


# ---------------------------------------------------------------------------
# EC-10: count_requeues_since window and scope
# ---------------------------------------------------------------------------


def test_count_requeues_since_window_and_scope(tmp_db):
    """EC-10: only requeue/rate_limited rows for (proj, TECH-1) within 24h count."""
    with db.get_db() as conn:
        # 2 rows now, matching scope — counted
        conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) VALUES (?, ?, ?, ?, ?)",
            ("proj", "TECH-1", "requeue", "rate_limited", 0),
        )
        conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) VALUES (?, ?, ?, ?, ?)",
            ("proj", "TECH-1", "requeue", "rate_limited", 0),
        )
        # same spec/verdict/reason, but 25h old — outside the 24h window
        conn.execute(
            "INSERT INTO callback_decisions "
            "(ts, project_id, spec_id, verdict, reason, demoted) "
            "VALUES (strftime('%Y-%m-%dT%H:%M:%SZ','now','-25 hours'), ?, ?, ?, ?, ?)",
            ("proj", "TECH-1", "requeue", "rate_limited", 0),
        )
        # different spec, same project
        conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) VALUES (?, ?, ?, ?, ?)",
            ("proj", "TECH-2", "requeue", "rate_limited", 0),
        )
        # different project, same spec id
        conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) VALUES (?, ?, ?, ?, ?)",
            ("other", "TECH-1", "requeue", "rate_limited", 0),
        )
        # same spec/project, but a different requeue reason (TECH-226 fleet_paused)
        conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) VALUES (?, ?, ?, ?, ?)",
            ("proj", "TECH-1", "requeue", "fleet_paused", 0),
        )

    assert db.count_requeues_since("proj", "TECH-1", 24) == 2


# ---------------------------------------------------------------------------
# Task 4: callback.main() with exit_code=5 — helpers
# (copied from test_callback_blocked_no_dispatch.py:60-148, per the spec)
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_event_writer(monkeypatch):
    """Suppress openclaw/Hermes calls — event_writer.notify is external I/O."""
    monkeypatch.setattr(event_writer, "wake_hermes", lambda *a, **kw: True)
    monkeypatch.setattr(event_writer, "write_event", lambda *a, **kw: None)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _make_project(tmp_path: Path, spec_id: str, *, status: str = "in_progress") -> Path:
    """Minimal git project with spec + lifecycle yaml committed."""
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)

    spec_body = (
        f"# {spec_id}\n\n"
        "**Status:** in_progress\n\n"
        "## Allowed Files\n\n"
        "<!-- callback-allowlist v1 -->\n\n"
        "- `src/x.py`\n\n"
        "## Tests\n"
    )
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "README.md").write_text("init\n")

    lc_data = {
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
    (lc_dir / f"{spec_id}.yaml").write_text(
        yaml.safe_dump(lc_data, default_flow_style=False, allow_unicode=True)
    )
    (lc_dir / ".gitkeep").write_text("")

    _git(
        repo,
        "add",
        "README.md",
        f"ai/features/{spec_id}.md",
        "ai/lifecycle/.gitkeep",
        f"ai/lifecycle/{spec_id}.yaml",
    )
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _seed_db(project_id: str, project_path: str, pueue_id: int, task_label: str) -> None:
    """Seed project_state + task_log so resolve_label and get_project_state work."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_state (project_id, path, provider) VALUES (?, ?, ?)",
            (project_id, project_path, "claude"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, task_label, "autopilot", "running", pueue_id),
        )


def _run_main_exit5(pueue_id: int, monkeypatch):
    """Invoke callback.main() simulating a pueue callback for exit_code=5.

    autopilot's own task_status is irrelevant here — exit_code=5 is decided
    by the runner before any task_status JSON is produced. Returns the
    `sys.exit` mock so callers can assert the exit code.
    """
    monkeypatch.setattr(callback, "extract_agent_output", lambda *a, **kw: ("autopilot", "", ""))
    with patch("sys.argv", ["callback.py", str(pueue_id), "claude-runner", "Failed", "5"]):
        with patch("sys.exit") as fake_exit:
            callback.main()
    return fake_exit


# ---------------------------------------------------------------------------
# EC-8: exit_code=5 requeues the spec
# ---------------------------------------------------------------------------


def test_exit5_requeues_spec(tmp_path, tmp_db, stub_event_writer, monkeypatch):
    spec_id = "TECH-1"
    project_id = "proj"
    pueue_id = 601
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)
    monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    events = []
    monkeypatch.setattr(event_writer, "notify", lambda *a, **kw: events.append((a, kw)))

    _run_main_exit5(pueue_id, monkeypatch)

    lc = lifecycle.read_lifecycle(str(repo), spec_id)
    assert lc["status"] == "queued"
    assert lc["updated_by"] == "callback"
    assert lc["blocked_reason"] == "rate_limited"
    assert lc["transitions"][-1]["from"] == "in_progress"
    assert lc["transitions"][-1]["to"] == "queued"
    assert lc["transitions"][-1]["by"] == "callback"

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT verdict, reason, demoted FROM callback_decisions WHERE spec_id = ?",
            (spec_id,),
        ).fetchall()
    requeue_rows = [r for r in rows if r["verdict"] == "requeue"]
    assert len(requeue_rows) == 1
    assert requeue_rows[0]["reason"] == "rate_limited"
    assert requeue_rows[0]["demoted"] == 0
    assert db.count_demotes_since(10) == 0

    assert events, "expected one Hermes event for the autopilot run"
    message = events[-1][0][3]
    assert "queued" in message
    assert "rate_limited" in message


# ---------------------------------------------------------------------------
# EC-9: third requeue in 24h escalates to blocked
# ---------------------------------------------------------------------------


def test_third_requeue_in_24h_blocks(tmp_path, tmp_db, stub_event_writer, monkeypatch):
    spec_id = "TECH-2"
    project_id = "proj"
    pueue_id = 602
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)
    monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(event_writer, "notify", lambda *a, **kw: None)

    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) VALUES (?, ?, ?, ?, ?)",
            (project_id, spec_id, "requeue", "rate_limited", 0),
        )
        conn.execute(
            "INSERT INTO callback_decisions "
            "(project_id, spec_id, verdict, reason, demoted) VALUES (?, ?, ?, ?, ?)",
            (project_id, spec_id, "requeue", "rate_limited", 0),
        )

    _run_main_exit5(pueue_id, monkeypatch)

    lc = lifecycle.read_lifecycle(str(repo), spec_id)
    assert lc["status"] == "blocked"
    assert lc["blocked_reason"] == "repeated_rate_limit:3"

    with db.get_db() as conn:
        last = conn.execute(
            "SELECT verdict, demoted FROM callback_decisions "
            "WHERE spec_id = ? ORDER BY id DESC LIMIT 1",
            (spec_id,),
        ).fetchone()
    assert last["verdict"] == "demote"
    assert last["demoted"] == 1


# ---------------------------------------------------------------------------
# EC-11: spec already done before callback → noop
# ---------------------------------------------------------------------------


def test_already_done_is_noop(tmp_path, tmp_db, stub_event_writer, monkeypatch):
    spec_id = "TECH-3"
    project_id = "proj"
    pueue_id = 603
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id, status="in_progress")
    _seed_db(project_id, str(repo), pueue_id, task_label)
    monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(event_writer, "notify", lambda *a, **kw: None)

    lifecycle.write_lifecycle(str(repo), spec_id, "done", by="callback")

    fake_exit = _run_main_exit5(pueue_id, monkeypatch)

    lc = lifecycle.read_lifecycle(str(repo), spec_id)
    assert lc["status"] == "done"

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT verdict, reason FROM callback_decisions WHERE spec_id = ?",
            (spec_id,),
        ).fetchall()
    assert any(r["verdict"] == "noop" for r in rows)
    assert not any(r["verdict"] == "requeue" for r in rows)

    fake_exit.assert_called_with(0)
