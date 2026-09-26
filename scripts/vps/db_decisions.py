#!/usr/bin/env python3
"""
Module: db_decisions
Role: circuit-breaker decisions (TECH-169) + SDK telemetry (BUG-188).
Uses: sqlite3 (stdlib) — receives an open connection, never opens one.
Used by: db.py only, through thin delegates that keep the public names
         db.record_decision / db.count_demotes_since / db.count_requeues_since /
         db.clear_decisions / db.log_sdk_post_result_error / db.log_classifier_refusal.

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
    `verdict` is one of: 'demote', 'sync', 'noop', 'circuit_open', 'requeue'.
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


def count_requeues_since(
    conn: sqlite3.Connection, project_id: str, spec_id: str, hours: int
) -> int:
    """Count 'requeue'/'rate_limited' rows for a spec in the last `hours` (TECH-225).

    Feeds the repeated-rate-limit ceiling. Scoped by project_id — spec ids are
    only unique within a project.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM callback_decisions "
        "WHERE project_id = ? AND spec_id = ? AND verdict = 'requeue' "
        "AND reason = 'rate_limited' "
        "AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
        (project_id, spec_id, f"-{int(hours)} hours"),
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


def log_classifier_refusal(
    conn: sqlite3.Connection,
    project_id: str,
    task: str,
    skill: Optional[str],
    model: Optional[str],
    category: Optional[str],
    declines: int,
    fallbacks_served: int,
    unrecovered: int,
    exit_code: Optional[int],
    detail: Optional[str],
) -> int:
    """Record a safety-classifier decline seen by claude-runner.

    A decline is `stop_reason: "refusal"` inside a normal HTTP 200, so it shows
    up in no error rate and no exception counter. `unrecovered` is the number
    of declines the CLI could not re-run on a fallback model — those are the
    ones that produced no report at all, and the runner exits 4 for them.
    """
    cursor = conn.execute(
        "INSERT INTO classifier_refusals "
        "(project_id, task, skill, model, category, declines, fallbacks_served, "
        "unrecovered, exit_code, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            task,
            skill,
            model,
            category,
            int(declines),
            int(fallbacks_served),
            int(unrecovered),
            exit_code,
            detail,
        ),
    )
    return cursor.lastrowid or 0
