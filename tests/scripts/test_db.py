"""Tests for scripts/vps/db.py — get_task_by_pueue_id (BUG-164)."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "vps")
sys.path.insert(0, SCRIPT_DIR)

import db  # noqa: E402


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


def test_get_task_by_pueue_id_found(tmp_db):
    """Insert task_log row → query by pueue_id → returns correct dict."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("testproj", "/tmp/testproj"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("testproj", "autopilot-BUG-164", "autopilot", "queued", 42),
        )

    result = db.get_task_by_pueue_id(42)
    assert result is not None
    assert result["project_id"] == "testproj"
    assert result["task_label"] == "autopilot-BUG-164"
    assert result["skill"] == "autopilot"


def test_get_task_by_pueue_id_not_found(tmp_db):
    """Query non-existent pueue_id → returns None."""
    result = db.get_task_by_pueue_id(9999)
    assert result is None


def test_get_task_by_pueue_id_returns_latest(tmp_db):
    """Multiple rows for same pueue_id → returns latest (highest id)."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("proj1", "/tmp/proj1"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("proj1", "old-task", "spark", "done", 10),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("proj1", "new-task", "autopilot", "queued", 10),
        )

    result = db.get_task_by_pueue_id(10)
    assert result is not None
    assert result["task_label"] == "new-task"
    assert result["skill"] == "autopilot"
