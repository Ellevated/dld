#!/usr/bin/env python3
"""
Module: db
Role: SQLite WAL helpers for orchestrator state management.
Uses: sqlite3 (stdlib)
Used by: orchestrator.py (get_all_projects, seed_projects_from_json, try_acquire_slot, log_task,
             update_project_phase, get_available_slots, get_occupied_slots),
         callback.py (release_slot, finish_task, update_project_phase),
         night-reviewer.sh (via CLI: python3 db.py save-finding / get-new-findings / update-phase)
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "orchestrator.db"))
_UNSET = object()
_MIGRATIONS_APPLIED = False


def _ensure_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent runtime migrations. Process-cached after first success.

    TECH-170: add task_log.branch column for feature-branch awareness.
    Safe under WAL — ALTER TABLE ADD COLUMN is atomic and idempotent if
    we check pragma_table_info first.
    """
    global _MIGRATIONS_APPLIED
    if _MIGRATIONS_APPLIED:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(task_log)").fetchall()}
    if "branch" not in cols:
        try:
            conn.execute("ALTER TABLE task_log ADD COLUMN branch TEXT")
        except sqlite3.OperationalError:
            # Race: another process added it between PRAGMA and ALTER.
            pass
    _MIGRATIONS_APPLIED = True


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
    _ensure_migrations(conn)   # TECH-170: idempotent, process-cached
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


def get_all_projects() -> list[dict]:
    """Get all enabled projects."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM project_state WHERE enabled = 1 ORDER BY project_id"
        ).fetchall()
        return [dict(r) for r in rows]


def update_project_phase(project_id: str, phase: str, current_task=_UNSET) -> None:
    """Update project phase and optionally current_task.

    current_task behavior:
    - omitted     -> preserve existing current_task
    - None        -> explicitly clear current_task
    - str value   -> set current_task to that value
    """
    with get_db() as conn:
        if current_task is _UNSET:
            conn.execute(
                "UPDATE project_state SET phase = ?, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                "WHERE project_id = ?",
                (phase, project_id),
            )
        else:
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
    branch: str | None = None,
) -> int:
    """Create a task_log entry. Returns the row id.

    Args:
        branch: Git branch name (e.g. 'feature/TECH-170'). Used by the
            implementation guard to differentiate work merged to develop
            vs. work still on a feature branch (TECH-170).
    """
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO task_log "
            "(project_id, task_label, skill, status, pueue_id, branch) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, task_label, skill, status, pueue_id, branch),
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


def get_occupied_slots() -> list[dict]:
    """Return all compute_slots with non-NULL pueue_id.

    Used by orphan slot watchdog (BUG-162) to cross-reference
    occupied slots against live pueue tasks.
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT slot_number, provider, project_id, pueue_id, acquired_at "
            "FROM compute_slots WHERE pueue_id IS NOT NULL"
        ).fetchall()
        return [dict(r) for r in rows]


def get_task_by_pueue_id(pueue_id: int) -> Optional[dict]:
    """Get task_log entry by pueue_id. Returns dict with project_id, task_label, skill."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT project_id, task_label, skill FROM task_log "
            "WHERE pueue_id = ? ORDER BY id DESC LIMIT 1",
            (pueue_id,),
        ).fetchone()
        return dict(row) if row else None


def seed_projects_from_json(projects: list[dict]) -> None:
    """Upsert projects from projects.json into project_state table."""
    with get_db() as conn:
        for p in projects:
            conn.execute(
                "INSERT INTO project_state (project_id, path, topic_id, provider, auto_approve_timeout) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "path = excluded.path, "
                "topic_id = COALESCE(excluded.topic_id, project_state.topic_id), "
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


def save_finding(
    project_id: str,
    fingerprint: str,
    severity: str,
    confidence: str,
    file_path: Optional[str],
    line_range: Optional[str],
    summary: str,
    suggestion: Optional[str],
) -> Optional[int]:
    """Insert finding; returns new row id or None if fingerprint already exists."""
    with get_db(immediate=True) as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO night_findings "
            "(project_id, fingerprint, severity, confidence, file_path, line_range, summary, suggestion) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                fingerprint,
                severity,
                confidence,
                file_path,
                line_range,
                summary,
                suggestion,
            ),
        )
        return cursor.lastrowid if cursor.rowcount else None


def get_new_findings(project_id: str) -> list[dict]:
    """Return findings with status='new' for a project."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM night_findings WHERE project_id = ? AND status = 'new' ORDER BY id",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_finding_status(finding_id: int, status: str) -> None:
    """Update finding status and set reviewed_at timestamp."""
    with get_db(immediate=True) as conn:
        conn.execute(
            "UPDATE night_findings SET status = ?, "
            "reviewed_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE id = ?",
            (status, finding_id),
        )


def get_finding_by_id(finding_id: int) -> Optional[dict]:
    """Return a single finding by id, or None if not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM night_findings WHERE id = ?",
            (finding_id,),
        ).fetchone()
        return dict(row) if row else None


def get_all_findings(project_id: str, status: Optional[str] = None) -> list[dict]:
    """Return all findings for project, optionally filtered by status."""
    with get_db() as conn:
        if status is not None:
            rows = conn.execute(
                "SELECT * FROM night_findings WHERE project_id = ? AND status = ? ORDER BY id",
                (project_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM night_findings WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_projects_for_night_scan(project_ids: list[str]) -> list[dict]:
    """Return enabled projects whose project_id is in the given list."""
    if not project_ids:
        return []
    placeholders = ",".join("?" * len(project_ids))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM project_state WHERE enabled = 1 AND project_id IN ({placeholders}) ORDER BY project_id",
            project_ids,
        ).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    if cmd == "seed":
        import json

        if len(sys.argv) != 3:
            print("Usage: python3 db.py seed <path/to/projects.json>", file=sys.stderr)
            sys.exit(1)
        path = sys.argv[2]
        with open(path) as f:
            projects = json.load(f)
        seed_projects_from_json(projects)
        print(f"seeded {len(projects)} projects")

    elif cmd == "save-finding":
        # Args: project_id fingerprint severity confidence file_path line_range summary suggestion
        if len(sys.argv) != 10:
            print(
                "Usage: python3 db.py save-finding <project_id> <fingerprint> <severity>"
                " <confidence> <file_path> <line_range> <summary> <suggestion>",
                file=sys.stderr,
            )
            sys.exit(1)
        fid = save_finding(
            sys.argv[2],
            sys.argv[3],
            sys.argv[4],
            sys.argv[5],
            sys.argv[6],
            sys.argv[7],
            sys.argv[8],
            sys.argv[9],
        )
        print(fid if fid is not None else "duplicate")

    elif cmd == "get-new-findings":
        import json

        if len(sys.argv) != 3:
            print("Usage: python3 db.py get-new-findings <project_id>", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(get_new_findings(sys.argv[2])))

    elif cmd == "update-finding-status":
        if len(sys.argv) != 4:
            print(
                "Usage: python3 db.py update-finding-status <finding_id> <status>",
                file=sys.stderr,
            )
            sys.exit(1)
        update_finding_status(int(sys.argv[2]), sys.argv[3])
        print(f"updated finding {sys.argv[2]} -> {sys.argv[3]}")

    elif cmd == "update-phase":
        if len(sys.argv) != 4:
            print("Usage: python3 db.py update-phase <project_id> <phase>", file=sys.stderr)
            sys.exit(1)
        update_project_phase(sys.argv[2], sys.argv[3])
        print(f"phase: {sys.argv[2]} -> {sys.argv[3]}")

    else:
        print(
            "Usage: python3 db.py <seed|save-finding|get-new-findings"
            "|update-finding-status|update-phase> [args...]",
            file=sys.stderr,
        )
        sys.exit(1)
