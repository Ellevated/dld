#!/usr/bin/env python3
"""
Module: db_findings
Role: night-review findings CRUD (FTR-147) — night_findings table.
Uses: sqlite3 (stdlib) — receives an open connection, never opens one.
Used by: db.py only, through thin delegates that keep the public names
         db.save_finding / db.get_new_findings / db.update_finding_status /
         db.get_finding_by_id / db.get_all_findings / db.get_projects_for_night_scan.
         The live consumer is night-reviewer.sh via `python3 db.py <cmd>` (db_cli.py).

Pure leaf (TECH-212): must never import db.
"""

import sqlite3
from typing import Optional


def save_finding(
    conn: sqlite3.Connection,
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


def get_new_findings(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """Return findings with status='new' for a project."""
    rows = conn.execute(
        "SELECT * FROM night_findings WHERE project_id = ? AND status = 'new' ORDER BY id",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_finding_status(conn: sqlite3.Connection, finding_id: int, status: str) -> None:
    """Update finding status and set reviewed_at timestamp."""
    conn.execute(
        "UPDATE night_findings SET status = ?, "
        "reviewed_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE id = ?",
        (status, finding_id),
    )


def get_finding_by_id(conn: sqlite3.Connection, finding_id: int) -> Optional[dict]:
    """Return a single finding by id, or None if not found."""
    row = conn.execute(
        "SELECT * FROM night_findings WHERE id = ?",
        (finding_id,),
    ).fetchone()
    return dict(row) if row else None


def get_all_findings(
    conn: sqlite3.Connection, project_id: str, status: Optional[str] = None
) -> list[dict]:
    """Return all findings for project, optionally filtered by status."""
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


def get_projects_for_night_scan(conn: sqlite3.Connection, project_ids: list[str]) -> list[dict]:
    """Return enabled projects whose project_id is in the given list."""
    if not project_ids:
        return []
    # Only the "?,?,?" placeholder list is interpolated — every value stays a
    # bound parameter (ADR-017).
    placeholders = ",".join("?" * len(project_ids))
    sql = (
        "SELECT * FROM project_state WHERE enabled = 1 "
        f"AND project_id IN ({placeholders}) ORDER BY project_id"
    )
    rows = conn.execute(sql, project_ids).fetchall()
    return [dict(r) for r in rows]
