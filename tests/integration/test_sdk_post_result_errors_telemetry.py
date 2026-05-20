"""BUG-188 — integration tests for sdk_post_result_errors telemetry table.

ADR-013: real SQLite, no mocks of business logic.

Three tests:
1. log_sdk_post_result_error inserts a row with correct values.
2. Table is auto-created by _ensure_migrations on a fresh empty DB (no schema.sql).
3. stderr column is nullable.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))


def _fresh_db_module(tmp_path, schema=True):
    """Return a reloaded db module pointing at tmp_path/orchestrator.db."""
    db_path = tmp_path / "orchestrator.db"
    os.environ["DB_PATH"] = str(db_path)
    if schema:
        schema_sql = (SCRIPT_DIR / "schema.sql").read_text()
        conn = sqlite3.connect(db_path)
        conn.executescript(schema_sql)
        conn.close()
    # Force re-init in case the module was imported by another test
    if "db" in sys.modules:
        del sys.modules["db"]
    import db  # noqa: PLC0415
    db._MIGRATIONS_APPLIED = False
    return db


def test_log_sdk_post_result_error_inserts_row(tmp_path):
    db = _fresh_db_module(tmp_path, schema=True)
    row_id = db.log_sdk_post_result_error(
        project_id="testproj",
        task="TECH-999",
        turns=43,
        cost_usd=6.32,
        error_msg="post-result exception",
        stderr="cli: rate limited",
    )
    assert row_id > 0
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT * FROM sdk_post_result_errors WHERE id = ?", (row_id,)
        ).fetchone()
    assert row["project_id"] == "testproj"
    assert row["task"] == "TECH-999"
    assert row["turns"] == 43
    assert row["cost_usd"] == 6.32
    assert row["error_msg"] == "post-result exception"
    assert row["stderr"] == "cli: rate limited"


def test_table_auto_created_on_first_call(tmp_path):
    # Fresh empty .db file, NO schema loaded — _ensure_migrations must create it.
    db = _fresh_db_module(tmp_path, schema=False)
    # Sanity: the table does not exist yet
    db_path = tmp_path / "orchestrator.db"
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "sdk_post_result_errors" not in tables

    # First call should auto-create the table via _ensure_migrations
    row_id = db.log_sdk_post_result_error(
        project_id="p", task="T-1", turns=1, cost_usd=0.0,
        error_msg="x", stderr=None,
    )
    assert row_id > 0
    # Verify table now exists
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "sdk_post_result_errors" in tables


def test_stderr_column_nullable(tmp_path):
    db = _fresh_db_module(tmp_path, schema=True)
    row_id = db.log_sdk_post_result_error(
        project_id="p", task="T-2", turns=0, cost_usd=0.0,
        error_msg="x", stderr=None,
    )
    with db.get_db() as conn:
        row = conn.execute(
            "SELECT stderr FROM sdk_post_result_errors WHERE id = ?", (row_id,)
        ).fetchone()
    assert row["stderr"] is None
