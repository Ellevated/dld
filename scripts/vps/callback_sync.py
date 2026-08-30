#!/usr/bin/env python3
"""
Module: callback_sync
Role: The status gate — decide done | blocked for a finished autopilot run and
      write it through lifecycle (ADR-023: callback is the sole status writer).

Uses:
  - lifecycle: read_lifecycle, write_lifecycle, LifecycleAlreadyDoneError
  - gate_logic: parse_allowed_files, fetch_develop
  - gate_ancestry: fetch_branch, find_implementation (TECH-220 — ancestry primary, subject fallback)
  - callback_scope: _get_started_at, _commit_stats, _detect_out_of_scope_files, _emit_audit
  - callback_circuit: is_circuit_open, _record, note_demote
  - event_writer: notify (Rule 7 structural save)

Used by:
  - callback.main: verify_status_sync (Step 7)
  - callback_dispatch._merge_confirmed reuses the same gate_logic calls (TECH-207)

Extracted from callback.py by TECH-216. verify_status_sync keeps its name,
signature and return; its body is the 2026-05-21 redesign split into named
steps. Every helper binds its collaborators through the owning module
(`callback_scope._commit_stats`, `callback_circuit.is_circuit_open`) so a
monkeypatch on that module is what tests reach for.
"""

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import callback_circuit  # noqa: E402
import callback_scope  # noqa: E402
import event_writer  # noqa: E402
import gate_ancestry  # noqa: E402
import gate_logic  # noqa: E402
import lifecycle  # noqa: E402

log = logging.getLogger("callback")


@dataclass
class _Audit:
    """One verify_status_sync call = one audit line (TECH-171).

    Carries the identifiers fixed at entry plus the scope telemetry filled in
    by step 2, so every exit path emits the same record shape with one call.
    """

    project_id: str
    spec_id: str
    pueue_id: int | None
    target_in: str
    start_wall: float
    allowed_count: int = 0
    code_loc: int = 0
    test_loc: int = 0
    code_commits: int = 0
    started_at: str | None = None
    gate_via: str = "none"

    def emit(self, target_out: str, reason: str, **extra: object) -> None:
        callback_scope._emit_audit(
            self.project_id,
            self.spec_id,
            self.pueue_id,
            self.target_in,
            target_out,
            reason,
            self.allowed_count,
            self.code_loc,
            self.test_loc,
            self.code_commits,
            self.started_at,
            self.start_wall,
            gate_via=self.gate_via,
            **extra,
        )


# --- Step 1: preconditions -----------------------------------------------------


def _read_existing_status(project_path: str, spec_id: str, audit: _Audit) -> str | None:
    """Circuit breaker, project boundary (Rule 3) and terminal done (Rule 7).

    Returns the current lifecycle status when the gate may proceed, or None
    after recording + auditing the reason to stop.
    """
    project_id = audit.project_id
    # Circuit breaker (TECH-169)
    if callback_circuit.is_circuit_open():
        log.warning("CIRCUIT_OPEN: skip verify_status_sync(%s)", spec_id)
        callback_circuit._record(project_id, spec_id, "noop", "circuit_open")
        audit.emit("noop", "circuit_open")
        return None

    # Rule 3: project boundary
    existing = lifecycle.read_lifecycle(project_path, spec_id)
    if not existing:
        log.info("NOOP: %s — no lifecycle.yaml in %s", spec_id, project_id)
        callback_circuit._record(project_id, spec_id, "noop", "not_in_project")
        audit.emit("noop", "not_in_project")
        return None

    existing_status = existing.get("status")

    # Rule 7: done is terminal
    if existing_status == "done":
        log.info("NOOP: %s — already done (terminal)", spec_id)
        callback_circuit._record(project_id, spec_id, "noop", "already_done_terminal")
        audit.emit("done", "already_done_terminal")
        return None

    return existing_status


# --- Step 2: allowlist + scope telemetry ---------------------------------------


def _collect_scope(
    project_path: str, spec_id: str, audit: _Audit
) -> tuple[list[str] | None, list[str]]:
    """Parse the spec allowlist and fill the audit with commit telemetry.

    Returns (allowed, out_of_scope_files). BUG-199 Fix C: out-of-scope
    detection is WARNING-only — it never feeds the status decision.
    """
    spec_file = next(iter(Path(project_path).glob(f"ai/features/{spec_id}*.md")), None)
    allowed = gate_logic.parse_allowed_files(spec_file) if spec_file else None
    started_at = callback_scope._get_started_at(int(audit.pueue_id)) if audit.pueue_id else None
    code_loc, test_loc, code_commits = callback_scope._commit_stats(
        project_path, allowed, started_at
    )
    audit.allowed_count = len(allowed) if allowed else 0
    audit.code_loc, audit.test_loc, audit.code_commits = code_loc, test_loc, code_commits
    audit.started_at = started_at

    out_of_scope_files = callback_scope._detect_out_of_scope_files(
        project_path, spec_id, allowed, started_at
    )
    if out_of_scope_files:
        log.warning(
            "OUT_OF_SCOPE: %s — commits attributed to %s touched %d file(s) outside allowlist: %s",
            audit.project_id,
            spec_id,
            len(out_of_scope_files),
            ", ".join(out_of_scope_files[:10]),
        )
    return allowed, out_of_scope_files


# --- Step 3: flush a timeout-interrupted merge ---------------------------------


def _push_local_develop(project_path: str, spec_id: str, project_id: str) -> None:
    """TECH-197 push-local-before-gate.

    When timeout kills autopilot between "git merge" and "git push develop",
    implementation sits in local develop but NOT origin. Push it now, best-effort.
    """
    try:
        subprocess.run(
            ["git", "-C", project_path, "push", "origin", "develop"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        log.info("PUSH_LOCAL: %s — best-effort push develop for %s", spec_id, project_id)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("PUSH_LOCAL: %s — failed: %s", spec_id, exc)


# --- Step 4: THE gate ----------------------------------------------------------


def _decide_status(
    project_path: str,
    spec_id: str,
    project_id: str,
    allowed: list[str] | None,
    *,
    autopilot_signaled: bool,
) -> tuple[str, str, str]:
    """Rule 1: done iff origin/develop carries the implementation — via branch
    ancestry (TECH-220 primary) or, failing that, a subject-matching commit
    (deprecated fallback).

    Returns (new_status, reason, gate_via). `gate_via` is `"ancestry"` |
    `"subject"` | `"none"` — the caller records it on every audit line
    regardless of the final status, so a self-block that overrides a positive
    verdict still leaves a trace of what the gate found. Grace-retry
    (TECH-197) covers the network race where the push landed but origin has
    not caught up yet; it runs only when the autopilot did NOT deliberately
    hold the spec.
    """
    if not allowed:
        # Cannot evaluate the gate → block with explicit reason.
        reason = "missing_allowed_files" if allowed is None else "empty_allowed_files"
        log.warning("GATE: %s — %s, blocking", spec_id, reason)
        return "blocked", reason, "none"

    # Rule 4: fetch before evaluating the gate
    gate_logic.fetch_develop(project_path)
    gate_ancestry.fetch_branch(project_path, spec_id)
    sha, via = gate_ancestry.find_implementation(project_path, spec_id, allowed)
    if sha:
        return "done", "", via

    if autopilot_signaled:
        # Autopilot EXPLICITLY signaled blocked/needs_review and the gate finds
        # no merged implementation — the expected outcome of a deliberate
        # self-block (e.g. unmet dependency), NOT a gate anomaly. Surface the
        # real cause instead of the misleading force-done hint.
        return "blocked", "autopilot_signaled_blocked", via

    for attempt in range(1, 4):  # up to 3 retries
        time.sleep(5)
        gate_logic.fetch_develop(project_path)
        gate_ancestry.fetch_branch(project_path, spec_id)
        sha, via = gate_ancestry.find_implementation(project_path, spec_id, allowed)
        if sha:
            log.info("GRACE_RETRY: %s — resolved on attempt %d (via=%s)", spec_id, attempt, via)
            return "done", "", via

    state = gate_ancestry.branch_state(project_path, spec_id)
    if state.exists and state.ahead > 0:
        # TECH-221: the run died before merge and salvage pushed the branch.
        # Nothing is lost and force-done is the WRONG advice here — the next
        # dispatch continues that branch (orchestrator_queue.reconcile).
        return (
            "blocked",
            f"branch_pushed_not_merged:{state.ahead} ahead — "
            f"origin/{state.ref} carries the work; re-dispatch continues that branch",
            via,
        )
    return (
        "blocked",
        (
            f"no_merged_implementation — if implementation IS real, run: "
            f"python3 scripts/vps/spec_operator.py force-done {project_id} {spec_id} "
            f"'gate regex bug, verified manually' --by=operator"
        ),
        via,
    )


# --- Step 5: write through lifecycle -------------------------------------------


def _write_status(
    project_path: str,
    spec_id: str,
    new_status: str,
    reason: str,
    audit: _Audit,
) -> bool:
    """lifecycle.write_lifecycle with the two failure paths audited.

    Returns True when the write landed; False after emitting the audit line
    for a Rule 7 structural save (ADR-025) or a write error.
    """
    try:
        lifecycle.write_lifecycle(
            project_path,
            spec_id,
            new_status,
            reason=reason or None,
            by="callback",
            pueue_id=audit.pueue_id,
        )
        return True
    except lifecycle.LifecycleAlreadyDoneError as exc:
        # Rule 7 structural guard (ADR-025): race between the Rule 7 fast-path
        # read in step 1 and this write — another writer flipped to done in
        # between. Benign NOOP — emit warning for investigation.
        log.warning("STATUS_SYNC: %s — Rule 7 structural save (%s)", spec_id, exc)
        callback_circuit._record(audit.project_id, spec_id, "noop", "rule_7_saved")
        try:
            event_writer.notify(
                project_path,
                "callback",
                "failed",
                f"rule_7_saved: {spec_id} — callback attempted '{new_status}', "
                f"spec already done. Investigate who wrote lifecycle({spec_id}): done.",
            )
        except Exception:  # noqa: BLE001
            pass  # notify is best-effort
        audit.emit("done", "rule_7_saved")
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("STATUS_SYNC: lifecycle.write failed for %s: %s", spec_id, exc)
        audit.emit("error", f"write_failed:{exc}")
        return False


# --- The gate: steps 1-7 -------------------------------------------------------


def verify_status_sync(
    project_path: str,
    spec_id: str,
    target: str = "done",
    pueue_id: int | None = None,
    autopilot_signaled: bool = False,
) -> None:
    """Single gate: lifecycle.status = done iff origin/develop contains a commit
    with `<spec_id>:` in its subject AND touching at least one allowed file.

    Implements the 2026-05-21 redesign (8 rules). The decision is a pure
    function of (origin/develop after fetch, allowed_files, existing lifecycle).
    Pueue exit code and activity windows do NOT factor into done/blocked.

    Rules enforced here:
      1. done iff commit on origin/develop with `<spec_id>:` subject + allowed_files
      3. noop if no ai/lifecycle/<spec_id>.yaml in this project
      4. fetch origin/develop before evaluating
      7. done is terminal — never demote done

    Preserves:
      - Circuit breaker (TECH-169) on mass-demote
      - Audit log (TECH-171) exactly one JSONL line per call
    """
    project_id = Path(project_path).name
    audit = _Audit(project_id, spec_id, pueue_id, target, time.monotonic())

    # Step 1: circuit / project boundary / terminal done
    existing_status = _read_existing_status(project_path, spec_id, audit)
    if existing_status is None:
        return

    # Step 2: allowlist + telemetry (out-of-scope is WARNING only, BUG-199)
    allowed, out_of_scope_files = _collect_scope(project_path, spec_id, audit)

    # Step 3: TECH-197 — flush a timeout-interrupted local merge
    if not autopilot_signaled and target == "blocked":
        _push_local_develop(project_path, spec_id, project_id)

    # Step 4: THE gate
    new_status, reason, gate_via = _decide_status(
        project_path, spec_id, project_id, allowed, autopilot_signaled=autopilot_signaled
    )
    audit.gate_via = gate_via
    # Autopilot explicitly signaled blocked/needs_review → honor over gate=done
    # (autopilot saw something the gate can't infer: tests failed, need human).
    if autopilot_signaled and target == "blocked" and new_status == "done":
        new_status, reason = "blocked", "autopilot_signaled_blocked"

    # No-op if state already matches
    if existing_status == new_status:
        log.info("NOOP: %s — already %s", spec_id, new_status)
        callback_circuit._record(project_id, spec_id, "noop", "already_correct")
        audit.emit(new_status, "already_correct")
        return

    # Step 5: demote accounting feeds the circuit breaker (TECH-169)
    if new_status == "blocked":
        callback_circuit.note_demote(project_id, spec_id, reason)
    else:
        callback_circuit._record(project_id, spec_id, "sync", "fixed")

    # Step 6: write (ADR-023 — the only status writer)
    log.warning(
        "STATUS_SYNC: %s — %s → %s (%s)", spec_id, existing_status, new_status, reason or "ok"
    )
    if not _write_status(project_path, spec_id, new_status, reason, audit):
        return

    # Step 7: audit (TECH-171). Rule 5 inline backlog render was removed in
    # ARCH-196 — backlog.md is single-writer (spark/autopilot Edit).
    audit.emit(
        new_status,
        reason or "ok",
        out_of_scope_files=out_of_scope_files if out_of_scope_files else None,
    )
