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
    pueue_response = json.dumps({
        "tasks": {
            "77": {"label": "proj2:FTR-100", "status": {"Running": {}}}
        }
    })
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
