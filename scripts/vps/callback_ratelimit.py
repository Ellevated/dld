#!/usr/bin/env python3
"""
Module: callback_ratelimit
Role: exit 5 (rate_limited) — return the spec to `queued` instead of demoting
      it to `blocked`. A 3rd requeue for the same spec within 24h escalates to
      `blocked` through the ordinary circuit-breaker demote path (TECH-225).

Uses:
  - callback_sync: _Audit, _read_existing_status, _write_status
  - callback_circuit: note_demote, _record
  - db: count_requeues_since

Used by:
  - callback.main: Step 7, autopilot exit_code == 5

A narrower sibling of callback_sync.verify_status_sync: exit 5 never runs the
ancestry gate (_decide_status) — it always writes queued or escalates on the
requeue ceiling alone. Reuses verify_status_sync's Rule 3/7/circuit read and
Rule 7 race-safe write so every noop case it already covers (no lifecycle.yaml,
open circuit, already done) is covered here too.
"""

import logging
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import callback_circuit  # noqa: E402
import callback_sync  # noqa: E402
import db  # noqa: E402

log = logging.getLogger("callback")

REQUEUE_CEILING = 3
REQUEUE_WINDOW_HOURS = 24
REQUEUE_REASON = "rate_limited"


def requeue(project_path: str, spec_id: str, pueue_id: int | None) -> tuple[str, str] | None:
    """Requeue a spec after a rate-limit exit, or escalate on the 3rd/24h.

    Returns `(status, reason)` written, or None on a noop (circuit open, no
    lifecycle.yaml, already done — see `callback_sync._read_existing_status`).
    """
    project_id = Path(project_path).name
    audit = callback_sync._Audit(project_id, spec_id, pueue_id, "queued", time.monotonic())

    if callback_sync._read_existing_status(project_path, spec_id, audit) is None:
        return None

    try:
        prior = db.count_requeues_since(project_id, spec_id, REQUEUE_WINDOW_HOURS)
    except Exception as exc:  # noqa: BLE001 — counter failure must not block the requeue
        log.warning("REQUEUE_RATE_LIMIT: count_requeues_since failed: %s", exc)
        prior = 0

    if prior >= REQUEUE_CEILING - 1:
        status, reason = "blocked", f"repeated_rate_limit:{prior + 1}"
        callback_circuit.note_demote(project_id, spec_id, reason)
    else:
        status, reason = "queued", REQUEUE_REASON
        callback_circuit._record(project_id, spec_id, "requeue", reason)

    log.warning("REQUEUE_RATE_LIMIT %s → %s (%s)", spec_id, status, reason)

    if not callback_sync._write_status(project_path, spec_id, status, reason, audit):
        return None
    audit.emit(status, reason)
    return status, reason
