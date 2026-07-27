#!/usr/bin/env python3
"""
Module: db_decisions
Role: circuit-breaker decisions (TECH-169) + SDK/gate telemetry (BUG-188, ARCH-190).
Uses: sqlite3 (stdlib) — receives an open connection, never opens one.
Used by: db.py only, through thin delegates that keep the public names
         db.record_decision / db.count_demotes_since / db.clear_decisions /
         db.log_sdk_post_result_error / db.log_gate_cycle / db.get_gate_health.

Pure leaf (TECH-212): must never import db. The caller owns the connection and the
transaction; db.get_db() stays the single place migrations run.
"""

import sqlite3
from typing import Optional


def record_decision(
    conn: sqlite3.Connection,
    project_id: str,
    spec_id: Optional[str],
    verdict: str,
    reason: Optional[str],
    demoted: bool,
) -> int:
    """Insert one callback decision row. Returns row id.

    TECH-169: Used by callback.verify_status_sync to feed the circuit-breaker.
    `verdict` is one of: 'demote', 'sync', 'noop', 'circuit_open'.
    """
    cursor = conn.execute(
        "INSERT INTO callback_decisions "
        "(project_id, spec_id, verdict, reason, demoted) "
        "VALUES (?, ?, ?, ?, ?)",
        (project_id, spec_id, verdict, reason, 1 if demoted else 0),
    )
    return cursor.lastrowid


def count_demotes_since(conn: sqlite3.Connection, min_ago: int) -> int:
    """Count callback_decisions rows with demoted=1 in the last `min_ago` minutes.

    TECH-169: Window query for circuit-breaker threshold check.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM callback_decisions "
        "WHERE demoted = 1 "
        "AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
        (f"-{int(min_ago)} minutes",),
    ).fetchone()
    return int(row["cnt"]) if row else 0


def clear_decisions(conn: sqlite3.Connection, min_ago: int) -> int:
    """Delete callback_decisions rows newer than `min_ago` minutes. Returns deleted count.

    TECH-169: Used by --reset-circuit to flush the recent window.
    """
    cursor = conn.execute(
        "DELETE FROM callback_decisions WHERE ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
        (f"-{int(min_ago)} minutes",),
    )
    return cursor.rowcount or 0


def log_sdk_post_result_error(
    conn: sqlite3.Connection,
    project_id: str,
    task: str,
    turns: int,
    cost_usd: float,
    error_msg: str,
    stderr: Optional[str],
) -> int:
    """Record a post-ResultMessage SDK exception (BUG-188).

    Called by claude-runner.py when the `result_received and not result_is_error`
    branch fires (SDK threw AFTER successful ResultMessage). The runner does not
    fail the task, but we still want telemetry so operators can spot drift.

    Threshold-based alerting (>5/day) is a downstream concern.
    """
    cursor = conn.execute(
        "INSERT INTO sdk_post_result_errors "
        "(project_id, task, turns, cost_usd, error_msg, stderr) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, task, turns, float(cost_usd or 0.0), error_msg, stderr),
    )
    return cursor.lastrowid or 0


def log_gate_cycle(
    conn: sqlite3.Connection,
    cycle_count: int,
    last_poll_at: str,
    in_progress_specs: int,
    decisions_this_cycle: int,
    error_msg: Optional[str] = None,
) -> int:
    """Record gate-daemon per-cycle health metrics (ARCH-190).

    Called by gate-daemon.py at the end of each polling cycle.
    Returns the new row id.

    Args:
        cycle_count: Monotonically increasing cycle counter.
        last_poll_at: ISO timestamp of when the poll was initiated.
        in_progress_specs: Total in_progress specs evaluated across all projects.
        decisions_this_cycle: Number of shadow verdicts written this cycle.
        error_msg: Non-fatal error summary if any project fetch failed; None otherwise.
    """
    cursor = conn.execute(
        "INSERT INTO gate_health "
        "(cycle_count, last_poll_at, in_progress_specs, decisions_this_cycle, error_msg) "
        "VALUES (?, ?, ?, ?, ?)",
        (cycle_count, last_poll_at, in_progress_specs, decisions_this_cycle, error_msg),
    )
    return cursor.lastrowid or 0


def get_gate_health(conn: sqlite3.Connection) -> Optional[dict]:
    """Return the latest gate_health row as dict, or None if table is empty (ARCH-190).

    Used by operators and future vps-orch CLI (MP-014) to inspect daemon liveness.
    """
    row = conn.execute("SELECT * FROM gate_health ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None
