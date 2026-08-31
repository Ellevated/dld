#!/usr/bin/env python3
"""
Module: callback_circuit
Role: Circuit-breaker (TECH-169) — trips on a burst of demotes, pauses the
      pueue runner group, and exposes the operator reset; plus the
      decision-log wrapper that feeds it.

Uses:
  - db: count_demotes_since, record_decision, clear_decisions
  - event_writer: notify_circuit_event
  - subprocess: `pueue pause` / `pueue start`

Used by:
  - callback.verify_status_sync (moves to callback_sync in TECH-216 Task 3)
  - callback.main (--reset-circuit CLI) and spec_operator.py (reset-circuit),
    both through the `callback._reset_circuit_cli` re-export
  - tests/integration/test_callback_circuit_breaker.py (through callback.*)

Extracted from callback.py by TECH-216.
"""

import logging
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import event_writer  # noqa: E402

log = logging.getLogger("callback")

# Threshold: more than this many demotes within WINDOW_MIN → circuit OPEN.
CIRCUIT_THRESHOLD = 3
CIRCUIT_WINDOW_MIN = 10
# Healing: if there were no demotes in the last HEAL_MIN minutes, circuit
# auto-closes (lazy check inside is_circuit_open).
CIRCUIT_HEAL_MIN = 30
# Reset CLI clears decisions newer than this (matches HEAL_MIN by design).
CIRCUIT_RESET_CLEAR_MIN = 30
# Pueue group paused on OPEN / resumed on RESET.
CIRCUIT_PUEUE_GROUP = "claude-runner"


def is_circuit_open() -> bool:
    """Return True if circuit-breaker is currently OPEN.

    Logic:
      1. Count demotes in last CIRCUIT_WINDOW_MIN minutes.
      2. If count > CIRCUIT_THRESHOLD → OPEN.
      3. Auto-heal: if count == 0 over CIRCUIT_HEAL_MIN window → CLOSED
         (cheap because we just compared to 0 above; no extra query).

    Pure function over DB state — no in-memory flag (callback is short-lived
    per pueue completion).
    """
    try:
        recent = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
    except Exception as exc:  # noqa: BLE001 — callback must not crash
        log.warning("CIRCUIT: count_demotes_since failed: %s", exc)
        return False
    if recent > CIRCUIT_THRESHOLD:
        # Lazy auto-heal: if last 30 min were quiet, ignore stale window.
        try:
            heal = db.count_demotes_since(CIRCUIT_HEAL_MIN)
        except Exception:
            heal = recent
        if heal == 0:
            log.info("CIRCUIT: auto-heal — no demotes in %d min", CIRCUIT_HEAL_MIN)
            return False
        return True
    return False


def _pueue_pause(group: str = CIRCUIT_PUEUE_GROUP) -> bool:
    """Best-effort pause of a pueue group. Returns True on success.

    Never raises — pueue might be missing, socket mismatch, etc.
    """
    try:
        r = subprocess.run(
            ["pueue", "pause", "--group", group],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            log.warning("CIRCUIT: paused pueue group=%s", group)
            return True
        log.warning(
            "CIRCUIT: pause failed (rc=%s) stderr=%s",
            r.returncode,
            r.stderr.strip()[:200],
        )
        return False
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("CIRCUIT: pause subprocess error: %s", exc)
        return False


def _pueue_resume(group: str = CIRCUIT_PUEUE_GROUP) -> bool:
    """Best-effort resume of a pueue group. Returns True on success."""
    try:
        r = subprocess.run(
            ["pueue", "start", "--group", group],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            log.warning("CIRCUIT: resumed pueue group=%s", group)
            return True
        log.warning(
            "CIRCUIT: resume failed (rc=%s) stderr=%s",
            r.returncode,
            r.stderr.strip()[:200],
        )
        return False
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("CIRCUIT: resume subprocess error: %s", exc)
        return False


def _trip_circuit(project_id: str, spec_id: str | None, count: int) -> None:
    """Side-effects fired exactly once when circuit transitions to OPEN.

    1. Log structured warning.
    2. Record an explicit 'circuit_open' decision (NOT counted as demote).
    3. Notify via event_writer (Telegram-equivalent).
    4. Pause claude-runner pueue group (best-effort).
    """
    log.error(
        "CIRCUIT_OPEN: %d demotes in %d min, refusing further status mutations until reset",
        count,
        CIRCUIT_WINDOW_MIN,
    )
    try:
        db.record_decision(
            project_id,
            spec_id,
            "circuit_open",
            f"threshold_exceeded:{count}/{CIRCUIT_WINDOW_MIN}min",
            demoted=False,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record_decision(circuit_open) failed: %s", exc)
    try:
        event_writer.notify_circuit_event(
            action="open",
            count=count,
            window_min=CIRCUIT_WINDOW_MIN,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: notify_circuit_event(open) failed: %s", exc)
    _pueue_pause()


def _reset_circuit_cli() -> None:
    """Operator-triggered circuit reset.

    Steps:
      1. Clear callback_decisions newer than CIRCUIT_RESET_CLEAR_MIN.
      2. Resume claude-runner pueue group.
      3. Send reset event (Telegram-equivalent).
    """
    try:
        deleted = db.clear_decisions(CIRCUIT_RESET_CLEAR_MIN)
        log.warning("CIRCUIT_RESET: cleared %d decision row(s)", deleted)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT_RESET: clear_decisions failed: %s", exc)
    _pueue_resume()
    try:
        event_writer.notify_circuit_event(action="reset", count=0, window_min=CIRCUIT_WINDOW_MIN)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT_RESET: notify failed: %s", exc)
    print(f"circuit reset: cleared decisions, resumed {CIRCUIT_PUEUE_GROUP}")


def _record(project_id, spec_id, action, reason, *, demoted=False):
    """db.record_decision, never raises (BLE001)."""
    try:
        db.record_decision(project_id, spec_id, action, reason, demoted=demoted)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: record_decision failed: %s", exc)


def note_demote(project_id: str, spec_id: str, reason: str) -> None:
    """Record one demote and trip the circuit when the window overflows.

    The threshold (>CIRCUIT_THRESHOLD demotes within CIRCUIT_WINDOW_MIN) is
    the TECH-169 contract; verify_status_sync used to inline this.
    """
    _record(project_id, spec_id, "demote", reason, demoted=True)
    try:
        count = db.count_demotes_since(CIRCUIT_WINDOW_MIN)
        if count > CIRCUIT_THRESHOLD:
            _trip_circuit(project_id, spec_id, count)
    except Exception as exc:  # noqa: BLE001
        log.warning("CIRCUIT: count/trip failed: %s", exc)
