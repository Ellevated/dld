"""Tests for scripts/vps/callback.py — BUG-164 regression tests."""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "vps")
sys.path.insert(0, SCRIPT_DIR)

import db  # noqa: E402
import callback  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path):
    """Create temporary SQLite DB with schema."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    schema_file = Path(SCRIPT_DIR) / "schema.sql"
    conn.executescript(schema_file.read_text())
    conn.close()
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


@pytest.fixture
def tmp_logs(tmp_path):
    """Create temporary logs directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    with patch.object(callback, "SCRIPT_DIR", tmp_path):
        yield log_dir


# --- resolve_label tests ---


def test_resolve_label_from_db(tmp_db):
    """DB returns task_label → correct composite label without pueue CLI."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("myproj", "/home/myproj"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("myproj", "autopilot-BUG-164", "autopilot", "queued", 55),
        )

    label = callback.resolve_label("55")
    assert label == "myproj:autopilot-BUG-164"


def test_resolve_label_fallback_to_pueue(tmp_db):
    """DB returns None → falls back to pueue status → returns label."""
    pueue_response = json.dumps(
        {"tasks": {"77": {"label": "proj2:FTR-100", "status": {"Running": {}}}}}
    )
    mock_result = MagicMock()
    mock_result.stdout = pueue_response

    with patch("subprocess.run", return_value=mock_result):
        label = callback.resolve_label("77")
    assert label == "proj2:FTR-100"


def test_resolve_label_all_fail(tmp_db):
    """DB empty + pueue fails → returns 'unknown'."""
    with patch("subprocess.run", side_effect=Exception("socket")):
        label = callback.resolve_label("999")
    assert label == "unknown"


# --- extract_agent_output tests ---


def test_extract_agent_output_from_logfile(tmp_db, tmp_logs):
    """Log file with JSON → extracts skill and preview correctly."""
    # Setup project in DB
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("testproj", "/home/dld/projects/testproj"),
        )

    # Create log file
    log_data = {
        "exit_code": 0,
        "project": "testproj",
        "skill": "autopilot",
        "task": "/autopilot BUG-164",
        "result_preview": "Fixed callback pueue socket mismatch",
    }
    log_file = tmp_logs / "testproj-20260320-120000.log"
    log_file.write_text(json.dumps(log_data))

    skill, preview = callback.extract_agent_output("42", "testproj")
    assert skill == "autopilot"
    assert "Fixed callback" in preview


def test_extract_agent_output_no_logfile(tmp_db, tmp_logs):
    """No matching log file + no DB skill → falls through to pueue fallback."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("emptyproj", "/home/dld/projects/emptyproj"),
        )

    with patch("subprocess.run", side_effect=Exception("no pueue")):
        skill, preview = callback.extract_agent_output("99", "emptyproj")
    assert skill == ""
    assert preview == ""


def test_extract_agent_output_db_skill_fallback(tmp_db, tmp_logs):
    """No log file but DB has skill → returns skill from DB."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("proj3", "/home/dld/projects/proj3"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("proj3", "autopilot-TECH-100", "autopilot", "queued", 88),
        )

    # No log file for proj3, but DB has the skill
    with patch("subprocess.run", side_effect=Exception("no pueue")):
        skill, preview = callback.extract_agent_output("88", "proj3")
    assert skill == "autopilot"
    assert preview == ""  # no preview from DB


def test_extract_agent_output_no_project_id():
    """No project_id → skips log file, tries DB + pueue fallback."""
    with patch("subprocess.run", side_effect=Exception("no pueue")):
        skill, preview = callback.extract_agent_output("1")
    assert skill == ""
    assert preview == ""


# --- Integration test ---


def test_callback_full_flow_without_pueue(tmp_db, tmp_logs):
    """End-to-end: DB + log file → resolves label + extracts output → QA dispatch attempted."""
    # Setup DB
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path, provider) VALUES (?, ?, ?)",
            ("dld", "/home/dld/projects/dld", "claude"),
        )
        # Acquire slot
        conn.execute(
            "UPDATE compute_slots SET project_id = ?, pueue_id = ? WHERE slot_number = 1",
            ("dld", 100),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dld", "autopilot-BUG-164", "autopilot", "queued", 100),
        )

    # Create log file
    log_data = {
        "exit_code": 0,
        "project": "dld",
        "skill": "autopilot",
        "task": "/autopilot BUG-164",
        "result_preview": "Spec: BUG-164 → done",
    }
    log_file = tmp_logs / "dld-20260320-120000.log"
    log_file.write_text(json.dumps(log_data))

    # Verify resolve_label works from DB
    label = callback.resolve_label("100")
    assert label == "dld:autopilot-BUG-164"

    # Verify extract works from log file
    skill, preview = callback.extract_agent_output("100", "dld")
    assert skill == "autopilot"
    assert "BUG-164" in preview

    # Verify spec_id resolution
    project_id, task_label = callback.parse_label(label)
    spec_id = callback.resolve_spec_id(task_label, preview, "/home/dld/projects/dld")
    assert spec_id == "BUG-164"


# --- verify_status_sync tests ---


def test_verify_status_sync_both_done(tmp_path, caplog):
    """Both spec and backlog marked done → info log, no warning."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    spec = features / "FTR-200-some-feature.md"
    spec.write_text("# Feature\n\n**Status:** done | **Priority:** P1 | **Date:** 2026-03-28\n")

    backlog = tmp_path / "ai" / "backlog.md"
    backlog.write_text(
        "| ID | Task | Status |\n|----|------|--------|\n| FTR-200 | Some feature | done |\n"
    )

    import logging

    with caplog.at_level(logging.INFO):
        callback.verify_status_sync(str(tmp_path), "FTR-200")

    assert any("both spec and backlog are done" in r.message for r in caplog.records)
    assert not any(
        "STATUS_SYNC" in r.message and r.levelno >= logging.WARNING for r in caplog.records
    )


def test_verify_status_sync_fixes_spec(tmp_path, caplog):
    """Spec in_progress → auto-fixed to done, file content updated."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    spec = features / "BUG-300-fix-thing.md"
    spec.write_text("# Bug\n\n**Status:** in_progress | **Priority:** P0\n")

    backlog = tmp_path / "ai" / "backlog.md"
    backlog.write_text("| ID | Task | Status |\n| BUG-300 | Fix thing | done |\n")

    import logging

    with patch("callback.subprocess.run"):
        with caplog.at_level(logging.INFO):
            callback.verify_status_sync(str(tmp_path), "BUG-300")

    assert "**Status:** done" in spec.read_text()
    assert any("STATUS_FIX: spec BUG-300" in r.message for r in caplog.records)


def test_verify_status_sync_fixes_backlog(tmp_path, caplog):
    """Backlog in_progress → auto-fixed to done, file content updated."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    spec = features / "TECH-400-refactor.md"
    spec.write_text("# Tech\n\n**Status:** done | **Priority:** P1\n")

    backlog = tmp_path / "ai" / "backlog.md"
    backlog.write_text("| ID | Task | Status |\n| TECH-400 | Refactor | in_progress |\n")

    import logging

    with patch("callback.subprocess.run"):
        with caplog.at_level(logging.INFO):
            callback.verify_status_sync(str(tmp_path), "TECH-400")

    assert "done" in backlog.read_text().split("TECH-400")[1].split("\n")[0]
    assert any("STATUS_FIX: backlog TECH-400" in r.message for r in caplog.records)


def test_verify_status_sync_fixes_both(tmp_path, caplog):
    """Neither done → both auto-fixed, git commit attempted."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    spec = features / "FTR-500-new-thing.md"
    spec.write_text("# Feature\n\n**Status:** in_progress\n")

    backlog = tmp_path / "ai" / "backlog.md"
    backlog.write_text("| ID | Task | Status |\n| FTR-500 | New thing | in_progress |\n")

    import logging

    with patch("callback.subprocess.run") as mock_run:
        with caplog.at_level(logging.INFO):
            callback.verify_status_sync(str(tmp_path), "FTR-500")

    # Files fixed
    assert "**Status:** done" in spec.read_text()
    assert "done" in backlog.read_text().split("FTR-500")[1].split("\n")[0]
    # Git commit+push attempted (3 calls: add, commit, push)
    assert mock_run.call_count == 3
    assert any("auto-fixed 2 file(s)" in r.message for r in caplog.records)


def test_verify_status_sync_failed_sets_blocked(tmp_path, caplog):
    """Failed autopilot → spec and backlog set to blocked."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    spec = features / "BUG-600-crash.md"
    spec.write_text("# Bug\n\n**Status:** in_progress | **Priority:** P0\n")

    backlog = tmp_path / "ai" / "backlog.md"
    backlog.write_text("| ID | Task | Status |\n| BUG-600 | Crash | in_progress |\n")

    import logging

    with patch("callback.subprocess.run"):
        with caplog.at_level(logging.INFO):
            callback.verify_status_sync(str(tmp_path), "BUG-600", target="blocked")

    assert "**Status:** blocked" in spec.read_text()
    assert "blocked" in backlog.read_text().split("BUG-600")[1].split("\n")[0]
    assert any("auto-fixed 2 file(s)" in r.message for r in caplog.records)
