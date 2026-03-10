#!/usr/bin/env python3
"""
Module: db
Role: SQLite WAL helpers for orchestrator state management.
Uses: sqlite3 (stdlib)
Used by: telegram-bot.py, notify.py
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "orchestrator.db"))


@contextmanager
def get_db(immediate: bool = False):
    """Context manager for SQLite connection with WAL mode.

    Uses isolation_level=None (manual transaction control) so callers
    can safely issue BEGIN IMMEDIATE without conflicting with implicit
    transactions that autocommit=False would start.

    Args:
        immediate: If True, opens with BEGIN IMMEDIATE (prevents writer
                   starvation; use in try_acquire_slot / release_slot).
    """
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    begin = "BEGIN IMMEDIATE" if immediate else "BEGIN"
    conn.execute(begin)
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def try_acquire_slot(project_id: str, provider: str, pueue_id: int) -> Optional[int]:
    """Acquire a compute slot for a project. Returns slot_number or None.

    Uses BEGIN IMMEDIATE to prevent race conditions between
    orchestrator and callback scripts.
    """
    with get_db(immediate=True) as conn:
        row = conn.execute(
            "SELECT slot_number FROM compute_slots "
            "WHERE provider = ? AND project_id IS NULL "
            "ORDER BY slot_number LIMIT 1",
            (provider,),
        ).fetchone()
        if row is None:
            return None
        slot = row["slot_number"]
        conn.execute(
            "UPDATE compute_slots SET project_id = ?, pueue_id = ?, "
            "acquired_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE slot_number = ?",
            (project_id, pueue_id, slot),
        )
        return slot


def release_slot(pueue_id: int) -> Optional[str]:
    """Release a compute slot by pueue task id. Returns project_id or None."""
    with get_db(immediate=True) as conn:
        row = conn.execute(
            "SELECT slot_number, project_id FROM compute_slots WHERE pueue_id = ?",
            (pueue_id,),
        ).fetchone()
        if row is None:
            return None
        project_id = row["project_id"]
        conn.execute(
            "UPDATE compute_slots SET project_id = NULL, pid = NULL, "
            "pueue_id = NULL, acquired_at = NULL WHERE pueue_id = ?",
            (pueue_id,),
        )
        return project_id


def get_project_state(project_id: str) -> Optional[dict]:
    """Get project state as dict. Returns None if not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM project_state WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return dict(row) if row else None


def get_project_by_topic(topic_id: int) -> Optional[dict]:
    """Look up project by Telegram topic_id. Returns None if not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM project_state WHERE topic_id = ?",
            (topic_id,),
        ).fetchone()
        return dict(row) if row else None


def get_all_projects() -> list[dict]:
    """Get all enabled projects."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM project_state WHERE enabled = 1 ORDER BY project_id"
        ).fetchall()
        return [dict(r) for r in rows]


def update_project_phase(project_id: str, phase: str, current_task: str = None) -> None:
    """Update project phase and optional current_task."""
    with get_db() as conn:
        conn.execute(
            "UPDATE project_state SET phase = ?, current_task = ?, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE project_id = ?",
            (phase, current_task, project_id),
        )


def log_task(
    project_id: str,
    task_label: str,
    skill: str,
    status: str,
    pueue_id: int = None,
) -> int:
    """Create a task_log entry. Returns the row id."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, task_label, skill, status, pueue_id),
        )
        return cursor.lastrowid


def finish_task(pueue_id: int, status: str, exit_code: int, summary: str = None) -> None:
    """Mark a task as finished in task_log."""
    with get_db() as conn:
        conn.execute(
            "UPDATE task_log SET status = ?, exit_code = ?, output_summary = ?, "
            "finished_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE pueue_id = ? AND finished_at IS NULL",
            (status, exit_code, summary, pueue_id),
        )


def get_available_slots(provider: str) -> int:
    """Count available slots for a provider."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM compute_slots WHERE provider = ? AND project_id IS NULL",
            (provider,),
        ).fetchone()
        return row["cnt"]


def seed_projects_from_json(projects: list[dict]) -> None:
    """Upsert projects from projects.json into project_state table."""
    with get_db() as conn:
        for p in projects:
            conn.execute(
                "INSERT INTO project_state (project_id, path, topic_id, provider, auto_approve_timeout) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "path = excluded.path, topic_id = excluded.topic_id, "
                "provider = excluded.provider, "
                "auto_approve_timeout = excluded.auto_approve_timeout",
                (
                    p["project_id"],
                    p["path"],
                    p.get("topic_id"),
                    p.get("provider", "claude"),
                    p.get("auto_approve_timeout", 30),
                ),
            )
