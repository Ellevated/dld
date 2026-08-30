#!/usr/bin/env python3
"""
Module: callback_scope
Role: Implementation-guard telemetry — started_at lookup, commit statistics
      over the spec allowlist, out-of-scope file detection (BUG-199 Fix C),
      and the audit JSONL writer (TECH-171).

Uses:
  - db: get_db (read-only started_at lookup)
  - gate_logic: match_subject
  - subprocess: git log --numstat / --name-only

Used by:
  - callback.verify_status_sync (moves to callback_sync in TECH-216 Task 3)
  - tests/unit/test_audit_log_format.py, tests/integration/test_callback_status_sync.py
    (through callback.* re-exports)

Extracted from callback.py by TECH-216. `_emit_audit` lives here rather than
with the circuit-breaker because it is the audit log's only producer and
`_write_audit` its only sink — splitting them would add the one cross-module
edge the split otherwise avoids.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import gate_logic  # noqa: E402

log = logging.getLogger("callback")


def _get_started_at(pueue_id: int) -> str | None:
    """Read started_at for a pueue task from task_log (read-only db access)."""
    try:
        with db.get_db() as conn:
            row = conn.execute(
                "SELECT started_at FROM task_log WHERE pueue_id = ? ORDER BY id DESC LIMIT 1",
                (pueue_id,),
            ).fetchone()
            if row is None:
                return None
            return row[0] if not hasattr(row, "keys") else row["started_at"]
    except Exception as exc:  # noqa: BLE001 — defensive (callback must not crash)
        log.warning("ALLOWED_FILES: started_at lookup failed for %s: %s", pueue_id, exc)
        return None


def _audit_log_path() -> Path:
    """Return path to callback-audit.jsonl (from CALLBACK_AUDIT_LOG env or default)."""
    env_val = os.environ.get("CALLBACK_AUDIT_LOG", "")
    if env_val:
        return Path(env_val)
    return SCRIPT_DIR / "callback-audit.jsonl"


def _write_audit(record: dict) -> None:
    """Append one JSON line to the audit log. Atomic: write to tmp, then rename."""
    try:
        audit_path = _audit_log_path()
        line = json.dumps(record, ensure_ascii=False) + "\n"
        # Atomic append: open in append mode (kernel-level atomicity for O_APPEND)
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:  # noqa: BLE001 — must not crash callback
        log.warning("AUDIT: write failed: %s", exc)


def _emit_audit(
    project_id: str,
    spec_id: str,
    pueue_id: int | None,
    target_in: str,
    target_out: str,
    reason: str,
    allowed_count: int,
    code_loc: int,
    test_loc: int,
    code_commits: int,
    started_at: str | None,
    start_wall: float,
    **extra: object,
) -> None:
    """Build audit record and write one JSONL line. Called once per verify_status_sync exit."""
    duration_ms = int((time.monotonic() - start_wall) * 1000)
    record = {
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_id": project_id,
        "spec_id": spec_id,
        "pueue_id": pueue_id,
        "target_in": target_in,
        "target_out": target_out,
        "reason": reason,
        "allowed_count": allowed_count,
        "code_loc": code_loc,
        "test_loc": test_loc,
        "code_commits": code_commits,
        "started_at": started_at,
        "duration_ms": duration_ms,
    }
    if extra:
        record.update(extra)
    _write_audit(record)


def _is_test_path(rel_path: str) -> bool:
    """True if rel_path looks like a test file."""
    p = rel_path.lower()
    return (
        p.startswith("tests/")
        or "/tests/" in p
        or "_test." in p
        or p.endswith("_test.py")
        or p.endswith("_test.ts")
        or p.endswith(".test.ts")
        or p.endswith(".test.js")
        or p.endswith(".spec.ts")
        or p.endswith(".spec.js")
    )


def _commit_stats(
    project_path: str,
    allowed: list[str] | None,
    started_at: str | None,
) -> tuple[int, int, int]:
    """Return (code_loc, test_loc, code_commits) via git log --numstat.

    - code_loc:    total lines added in non-test allowed files.
    - test_loc:    total lines added in test files.
    - code_commits: number of commits that touched non-test allowed files.

    Returns (0, 0, 0) on any error or when guard would degrade-open.
    """
    if not allowed or started_at is None:
        return 0, 0, 0
    cmd = [
        "git",
        "-C",
        project_path,
        "log",
        "--all",
        f"--since={started_at}",
        "--pretty=format:COMMIT",
        "--numstat",
        "--",
        *allowed,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return 0, 0, 0
    if r.returncode != 0:
        return 0, 0, 0

    code_loc = 0
    test_loc = 0
    code_commits = 0
    commit_has_code = False

    for line in r.stdout.splitlines():
        if line.strip() == "COMMIT":
            if commit_has_code:
                code_commits += 1
            commit_has_code = False
            continue
        parts = line.split("\t")
        if len(parts) == 3:
            try:
                added = int(parts[0])
            except ValueError:
                added = 0
            rel_path = parts[2]
            if _is_test_path(rel_path):
                test_loc += added
            else:
                code_loc += added
                if added > 0:
                    commit_has_code = True
    # Flush last commit
    if commit_has_code:
        code_commits += 1

    return code_loc, test_loc, code_commits


def _detect_out_of_scope_files(
    project_path: str,
    spec_id: str,
    allowed: list[str] | None,
    started_at: str | None,
) -> list[str]:
    """Return files touched by spec-attributed commits but NOT in the allowlist.

    BUG-199 Fix C: detection-only (WARNING), not enforcement.
    Inspects commits since started_at whose subject implements spec_id,
    and returns any paths they touched that are NOT in the allowed list.
    """
    if not allowed or not started_at or not spec_id:
        return []
    cmd = [
        "git",
        "-C",
        project_path,
        "log",
        "--all",
        f"--since={started_at}",
        "--pretty=format:%h%x00%s",
        "--name-only",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []

    allowed_set = set(allowed)
    out_of_scope: set[str] = set()
    is_spec_commit = False

    for line in r.stdout.splitlines():
        if "\x00" in line:
            # New commit header: hash\x00subject
            _, _, current_subject = line.partition("\x00")
            is_spec_commit = gate_logic.match_subject(current_subject, spec_id)
        elif line.strip() and is_spec_commit:
            # File path from --name-only
            rel_path = line.strip()
            if rel_path not in allowed_set and not rel_path.startswith("ai/"):
                out_of_scope.add(rel_path)

    return sorted(out_of_scope)
