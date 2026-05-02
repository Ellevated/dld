"""TECH-169 — integration tests for callback circuit-breaker.

ADR-013: real fs + real git + real sqlite. External binaries (pueue,
openclaw) are replaced with temp shell stubs that record invocations
to a file — no mocks of business logic.

Covers EC-1..EC-6 plus end-to-end test (Task 8).
"""

from __future__ import annotations

import os
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
import event_writer  # noqa: E402


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite DB seeded from schema.sql, isolated per test."""
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    # Reset migration cache so _ensure_migrations runs against this DB
    db._MIGRATIONS_APPLIED = False
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


@pytest.fixture
def stub_pueue_bin(tmp_path, monkeypatch):
    """Replace `pueue` on PATH with a stub that records argv to a file."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    log_file = tmp_path / "pueue-calls.log"
    stub = stub_dir / "pueue"
    stub.write_text(
        f'#!/usr/bin/env bash\necho "$@" >> "{log_file}"\nexit 0\n'
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_dir}:{os.environ['PATH']}")
    return log_file


@pytest.fixture
def stub_event_writer(tmp_path, monkeypatch):
    """Redirect notify_circuit_event output dir to tmp_path."""
    events_dir = tmp_path / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    # event_writer derives path from __file__; patch write_event to redirect.
    real_write = event_writer.write_event

    def fake_write(project_path, skill, status, message, artifact_rel=""):
        return real_write(str(events_dir), skill, status, message, artifact_rel)

    monkeypatch.setattr(event_writer, "write_event", fake_write)
    monkeypatch.setattr(event_writer, "wake_openclaw", lambda: True)
    return events_dir


def _seed_state(project_id: str = "proj") -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_state (project_id, path) "
            "VALUES (?, ?)",
            (project_id, "/tmp/ignored"),
        )


# --- EC-1: 4-th demote opens circuit ----------------------------------------


def test_ec1_circuit_opens_after_threshold(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    # 3 demotes — circuit closed (threshold is > 3, so 3 == not yet open)
    for i in range(3):
        db.record_decision("proj", f"TECH-{i}", "demote", "no_impl", demoted=True)
    assert callback.is_circuit_open() is False

    # 4th demote — pushes count to 4 > 3 → OPEN
    db.record_decision("proj", "TECH-3", "demote", "no_impl", demoted=True)
    assert callback.is_circuit_open() is True


# --- EC-2: reset re-enables -------------------------------------------------


def test_ec2_reset_closes_circuit(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    for i in range(5):
        db.record_decision("proj", f"TECH-{i}", "demote", "no_impl", demoted=True)
    assert callback.is_circuit_open() is True

    callback._reset_circuit_cli()
    assert callback.is_circuit_open() is False
    # Pueue resume invoked
    log_text = stub_pueue_bin.read_text() if stub_pueue_bin.exists() else ""
    assert "start --group claude-runner" in log_text


# --- EC-3: 30-min idle auto-heals -------------------------------------------


def test_ec3_auto_heal_after_idle(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    # Insert 5 demotes with ts older than HEAL_MIN (31 min ago)
    with db.get_db() as conn:
        for i in range(5):
            conn.execute(
                "INSERT INTO callback_decisions "
                "(ts, project_id, spec_id, verdict, reason, demoted) "
                "VALUES (strftime('%Y-%m-%dT%H:%M:%SZ','now','-31 minutes'),"
                " ?, ?, ?, ?, ?)",
                ("proj", f"TECH-{i}", "demote", "no_impl", 1),
            )
    # Window query for 10 min → 0 → not OPEN
    assert callback.is_circuit_open() is False


# --- EC-4: events emitted on open + reset -----------------------------------


def test_ec4_events_emitted(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    callback._trip_circuit("proj", "TECH-99", 4)
    # Sleep 1s so reset event gets a distinct filename (ts resolution = 1s).
    time.sleep(1)
    callback._reset_circuit_cli()

    files = sorted(stub_event_writer.rglob("*.json"))
    assert len(files) >= 2
    bodies = "\n".join(f.read_text() for f in files)
    assert '"skill": "circuit_breaker"' in bodies
    assert "CIRCUIT_OPEN" in bodies
    assert "CIRCUIT_RESET" in bodies


# --- EC-5: pueue pause/resume invoked ---------------------------------------


def test_ec5_pueue_pause_on_open_resume_on_reset(tmp_db, stub_pueue_bin, stub_event_writer):
    _seed_state("proj")
    callback._trip_circuit("proj", "TECH-99", 4)
    callback._reset_circuit_cli()

    log_text = stub_pueue_bin.read_text()
    assert "pause --group claude-runner" in log_text
    assert "start --group claude-runner" in log_text


# --- EC-6: callback_decisions table grows + indexed ------------------------


def test_ec6_decisions_table_shape(tmp_db):
    _seed_state("proj")
    for i in range(10):
        db.record_decision("proj", f"TECH-{i}", "demote", "no_impl", demoted=True)
    with db.get_db() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM callback_decisions").fetchone()[0]
        idx_rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='callback_decisions'"
        ).fetchall()
    assert cnt == 10
    idx_names = {r[0] for r in idx_rows}
    assert "idx_callback_decisions_ts" in idx_names
    assert "idx_callback_decisions_demoted_ts" in idx_names


# --- Task 8: End-to-end via verify_status_sync ------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _make_project(tmp_path: Path, idx: int, spec_id: str) -> Path:
    repo = tmp_path / f"proj{idx}"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(
        f"# {spec_id}\n\n**Status:** in_progress\n\n"
        f"## Allowed Files\n\n<!-- callback-allowlist v1 -->\n\n- `src/x.py`\n\n## Tests\n"
    )
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n"
        f"| {spec_id} | demo | in_progress | P1 |\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_e2e_5th_call_is_noop_circuit_open(
    tmp_path, tmp_db, stub_pueue_bin, stub_event_writer, monkeypatch
):
    # Suppress real `git push` (no remote in tests)
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)

    # Build 4 separate projects, each triggers a demote (no-impl).
    repos = []
    for i in range(4):
        spec_id = f"TECH-{900 + i}"
        repo = _make_project(tmp_path, i, spec_id)
        with db.get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_state (project_id, path) "
                "VALUES (?, ?)",
                (f"proj{i}", str(repo)),
            )
            conn.execute(
                "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"proj{i}", f"autopilot-{spec_id}", "autopilot", "running", 100 + i),
            )
        time.sleep(1.1)
        repos.append((repo, spec_id, 100 + i))

    # Calls 1-4: demote each (count climbs 1..4). After call 4, circuit OPEN.
    for repo, spec_id, pid in repos:
        callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=pid)

    def _head_content(repo: Path, rel: str) -> str:
        """Read file content from git HEAD (callback writes via plumbing, not working tree)."""
        r = subprocess.run(
            ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
            capture_output=True, text=True, check=False,
        )
        return r.stdout

    # All 4 specs demoted — verify at HEAD (callback uses plumbing, not working tree).
    for repo, spec_id, _ in repos:
        spec_text = _head_content(repo, f"ai/features/{spec_id}.md")
        assert "**Status:** blocked" in spec_text, f"{spec_id} should be blocked at HEAD"

    # Now circuit is OPEN. 5th call (any project) should no-op.
    repo5 = _make_project(tmp_path, 99, "TECH-905")
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_state (project_id, path) "
            "VALUES (?, ?)",
            ("proj99", str(repo5)),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("proj99", "autopilot-TECH-905", "autopilot", "running", 199),
        )
    time.sleep(1.1)
    # No impl commit on this repo either — would demote, except circuit OPEN.
    callback.verify_status_sync(str(repo5), "TECH-905", target="done", pueue_id=199)

    # Circuit blocked the mutation — HEAD should still have in_progress.
    spec_text = _head_content(repo5, "ai/features/TECH-905.md")
    assert "**Status:** in_progress" in spec_text, "Circuit should have blocked the demote"
    assert "**Status:** blocked" not in spec_text

    # Decision recorded as noop:circuit_open
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT verdict, reason FROM callback_decisions "
            "WHERE spec_id = 'TECH-905'"
        ).fetchall()
    assert any(r[0] == "noop" and r[1] == "circuit_open" for r in rows)
