# scripts/vps/tests/conftest.py
"""Shared pytest fixtures for orchestrator tests."""

import sqlite3
import sys
from pathlib import Path

import pytest

# Make scripts/vps importable
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

SCHEMA_SQL = Path(__file__).resolve().parent.parent / "schema.sql"


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Create an isolated SQLite DB with the production schema applied.

    Patches db.DB_PATH so every db.py function uses this temp DB.
    Returns the path to the temp database file.
    """
    db_path = tmp_path / "test_orchestrator.db"
    monkeypatch.setenv("DB_PATH", str(db_path))

    import db as db_mod

    monkeypatch.setattr(db_mod, "DB_PATH", str(db_path))

    # Apply schema
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.close()

    return db_path


@pytest.fixture()
def seed_project(isolated_db):
    """Seed a single test project and return its project_id."""
    import db

    db.seed_projects_from_json(
        [
            {
                "project_id": "testproject",
                "path": "/tmp/test-project",
                "topic_id": 5,
                "provider": "claude",
                "auto_approve_timeout": 30,
            }
        ]
    )
    return "testproject"
