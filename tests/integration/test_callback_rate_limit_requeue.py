"""TECH-225 — rate-limit requeue: DB counter (Task 3) + callback.main() (Task 4).

ADR-013: real sqlite, no mocks. `tmp_db` is module-level so Task 4's callback.main()
tests reuse the same fixture (per the spec's Task 3 steps).

Eval Criteria:
  EC-10: count_requeues_since scopes by (project_id, spec_id, verdict='requeue',
         reason='rate_limited') and windows on `hours`.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import db  # noqa: E402

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
