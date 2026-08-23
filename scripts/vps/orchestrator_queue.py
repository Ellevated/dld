#!/usr/bin/env python3
"""
Module: orchestrator_queue
Role: Dependency-aware spec selection (BUG-206) + scan_queued step decomposition.

The scan_queued WRAPPER stays in orchestrator.py (TECH-215) — several
non-editable test files reach it through `orchestrator.<name>` monkeypatches
or by grepping orchestrator.py's source. The steps here have no such
coupling: nothing in this module is a monkeypatch target, so each step is
called by the wrapper as `orchestrator_queue.<name>(...)`, never re-exported
by bare name.

Uses: db (import), lifecycle (import), gate_logic (import),
      orchestrator_slots._pueue_add
Used by: orchestrator (facade re-export of dep helpers; attribute calls into
         the six scan_queued steps from the wrapper)
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import gate_logic  # noqa: E402
import lifecycle  # noqa: E402
from orchestrator_slots import _pueue_add  # noqa: E402,F401

log = logging.getLogger("orchestrator")


# BUG-206: dependency-aware dispatch. Specs declare ordering with an
# "AFTER <SPEC-ID>" marker in their backlog row (the uniform place this
# convention lives — spec prose is too noisy to parse reliably). scan_queued
# must not dispatch a spec whose declared dependency is not yet done, or the
# autopilot burns a full run self-blocking on the unmet prerequisite
# (ARCH-1246/FTR-1245 vs the still-queued TECH-1244, awardybot 2026-06-20).
# Dependency EDGE comes from the backlog; dependency STATUS from the lifecycle SoT.
_AFTER_DEP_RE = re.compile(r"\bafter\s+([A-Z]{2,5}-\d+)", re.IGNORECASE)


def _backlog_deps(project_dir: str, spec_id: str) -> set:
    """Declared 'AFTER <ID>' dependencies for spec_id, read from its backlog row.

    Returns an empty set when the backlog, the row, or the marker is absent —
    conservative by design: a missing marker means no gate, never a stall.
    """
    backlog = Path(project_dir) / "ai" / "backlog.md"
    if not backlog.is_file():
        return set()
    row_re = re.compile(rf"^\s*\|\s*{re.escape(spec_id)}\s*\|")
    try:
        for line in backlog.read_text(errors="replace").splitlines():
            if row_re.match(line):
                deps = {m.group(1).upper() for m in _AFTER_DEP_RE.finditer(line)}
                deps.discard(spec_id)
                return deps
    except OSError:
        pass
    return set()


def _unmet_dependencies(project_dir: str, spec_id: str) -> list:
    """Subset of spec_id's declared deps whose lifecycle status is not 'done'.

    A dependency absent from lifecycle is treated as MET — avoids a permanent
    stall on a stale/archived reference. Prefer a false-negative (dispatch, then
    the autopilot self-blocks and is correctly labeled by callback) over a
    false-positive (a spec that silently never dispatches).
    """
    unmet = []
    for dep in sorted(_backlog_deps(project_dir, spec_id)):
        dep_lc = lifecycle.read_lifecycle(project_dir, dep)
        if dep_lc and dep_lc.get("status") != "done":
            unmet.append(dep)
    return unmet


def recently_processed(audit_log: Path, spec_id: str) -> str | None:
    """Reason this spec must not be re-dispatched yet, or None.

    `audit_log` is a parameter, not SCRIPT_DIR/"callback-audit.jsonl" resolved
    here: test_orchestrator_in_progress.py patches orchestrator.SCRIPT_DIR to a
    tmp repo and cannot be edited (not in Allowed Files). Resolving the path in
    this module would silently read the live daemon's audit log instead.

    - blocked within 30 min: the guard demoted it, a human is needed
    - done within 5 min: callback just wrote done, git pull may still be stale
    """
    if not audit_log.is_file():
        return None
    now = datetime.now(tz=timezone.utc).timestamp()
    cutoff_blocked = now - 30 * 60
    cutoff_done = now - 5 * 60
    try:
        for raw in audit_log.read_text().splitlines()[-200:]:
            entry = json.loads(raw)
            if entry.get("spec_id") != spec_id:
                continue
            ts_str = entry.get("ts", "")
            if not ts_str:
                continue
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
            target_out = entry.get("target_out")
            reason = entry.get("reason", "")
            if target_out == "blocked" and reason != "fixed" and ts > cutoff_blocked:
                return f"demoted recently ({reason})"
            if target_out == "done" and ts > cutoff_done:
                return f"completed recently ({reason})"
    except Exception:  # noqa: BLE001
        pass
    return None


def spec_body_files(project_dir: str, spec_id: str) -> list[Path]:
    """Spec body file(s) matching spec_id under ai/features/, or []."""
    features_dir = Path(project_dir) / "ai" / "features"
    return list(features_dir.glob(f"{spec_id}*"))


def spec_has_allowlist(spec_files: list[Path]) -> bool:
    """True if any spec body carries a parseable `## Allowed Files` section.

    Uses the same parser the callback gate uses, so the two cannot disagree.
    """
    return any(gate_logic.parse_allowed_files(f) for f in spec_files)


def gate_before_pueue_add(
    project_id: str, project_dir: str, spec_id: str, audit_log: Path
) -> tuple[list[Path], str] | None:
    """Bundle of four independent pre-dispatch gates: recency, spec-readiness,
    allowlist-presence, provider/slot availability.

    Extracted as a single step (EC-8, TECH-215 Task 6) rather than three
    separate calls in scan_queued: none of `recently_processed`,
    `spec_body_files`, `resolve_provider` or the `db.*` calls here are
    monkeypatch targets in a non-editable test file, so bundling them costs
    nothing — unlike the candidate-selection loop, which stayed in
    orchestrator.py for exactly that reason.

    Returns (spec_files, provider) if dispatch may proceed, else None.
    """
    skip_reason = recently_processed(audit_log, spec_id)
    if skip_reason:
        log.info("skip dispatch: %s %s", spec_id, skip_reason)
        return None

    # SPEC-READINESS GATE (2026-07-26, ARCH-196 / ADR-027)
    # A lifecycle row can exist before its spec body does: the spec-first ID
    # claim writes ai/lifecycle/<ID>.yaml to reserve the number, and the body
    # lands in ai/features/ only once Spark finishes. Dispatching in that
    # window hands autopilot a spec_id with nothing to read — it burns a whole
    # session and blocks. Skip quietly; if the row is still bodiless after
    # Spark should have finished, it is an orphan, which is a Spark defect and
    # not something dispatch can repair. (awardybot BUG-1410 was this.)
    spec_files = spec_body_files(project_dir, spec_id)
    if not spec_files:
        log.info(
            "skip dispatch: %s queued but no spec body in ai/features/ yet "
            "(spec-first ID claim not finished; orphan if it persists)",
            spec_id,
        )
        return None

    # ALLOWLIST GATE (2026-08-23)
    # The callback gate cannot accept a spec without `## Allowed Files` — it has
    # nothing to check merged commits against, so it writes
    # blocked/missing_allowed_files no matter how well the run went. Dispatching
    # such a spec is therefore guaranteed-futile work: dowry BUG-477 spent 90
    # minutes and 522 turns, produced real code on fix/BUG-477, and was blocked
    # on arrival for a section Spark never wrote.
    #
    # Spark owns this section (skills/spark/feature-mode.md "Allowed Files", and
    # its own Phase 5.5 allowlist linter in completion.md). Until now that was
    # prose an agent was asked to follow, with nothing downstream checking it.
    # A missing allowlist is a Spark defect and, exactly like the bodiless-spec
    # case above, not something dispatch can repair — so skip rather than burn
    # a session, and name the fix in the log.
    if not spec_has_allowlist(spec_files):
        log.warning(
            "skip dispatch: %s has no parseable '## Allowed Files' — the callback "
            "gate would block it on arrival regardless of the run. Fix the spec "
            "(node .claude/scripts/validate-allowlist.mjs ai/features/%s*.md), "
            "then re-queue.",
            spec_id,
            spec_id,
        )
        return None

    state = db.get_project_state(project_id)
    provider = resolve_provider(
        spec_files[0], (state["provider"] if state else None) or "claude", spec_id
    )
    if db.get_available_slots(provider) < 1:
        log.info("no slots for %s provider=%s (busy)", project_id, provider)
        return None

    return spec_files, provider


def resolve_provider(spec_file: Path, default_provider: str, spec_id: str) -> str:
    """Provider named in the spec's `provider:` header, or default_provider.

    Claude runs everything by default; a spec may name a different provider,
    which is treated as a deliberate request rather than a hint — so a busy
    provider makes the spec wait rather than silently running somewhere else.
    A provider with no slots configured at all (typo, or a runner never
    installed) falls back to default_provider with a WARNING, rather than
    stalling the spec forever under a "no slots" log.
    """
    provider = default_provider
    m = re.search(r"^provider:\s+(\w+)", spec_file.read_text(errors="replace"), re.MULTILINE)
    if m:
        requested = m.group(1)
        if db.get_provider_capacity(requested) > 0:
            provider = requested
        else:
            log.warning(
                "spec %s requests provider=%s which has no slots configured — falling back to %s",
                spec_id,
                requested,
                provider,
            )
    return provider


def status_still_dispatchable(project_dir: str, spec_id: str) -> bool:
    """BUG-205: authoritative TOCTOU re-check right before pueue add.

    The list_by_status() snapshot (top of scan_queued) can go stale before we
    actually dispatch: callback runs as a SEPARATE process and may have
    written blocked/done for this spec via git plumbing, and git_pull is
    skipped while an agent is running (stale local HEAD). Re-read the
    lifecycle SoT (HEAD) for THIS spec; return False if it is no longer
    dispatchable.
    """
    fresh = lifecycle.read_lifecycle(project_dir, spec_id)
    fresh_status = fresh.get("status") if fresh else None
    if fresh_status not in ("queued", "resumed"):
        log.info(
            "skip dispatch: %s status changed to %s after scan (TOCTOU re-check)",
            spec_id,
            fresh_status,
        )
        return False
    return True


def reconcile_if_implemented(project_dir: str, spec_id: str, spec_file: Path) -> bool:
    """RECONCILIATION GATE: mark done + skip dispatch if already on develop.

    A queued spec may already be implemented on origin/develop — work landed
    via another developer, another window, another node, or an autopilot
    session whose callback never fired. The single-writer model (ADR-023)
    only updates status through callback on THIS orchestrator's pueue
    completions, so out-of-band work leaves the lifecycle stuck at queued.
    Without this gate we re-dispatch (burn a full session) only for the
    callback guard to rubber-stamp done post-hoc. Run the SAME check the
    callback guard / gate-daemon use (gate_logic), but BEFORE dispatch.
    Fail-closed: only reconcile on a positive allowlist AND a positive commit
    match; otherwise dispatch proceeds as normal (return False).

    Returns True if the spec was reconciled (marked done) — the caller must
    not dispatch.
    """
    allowed_files = gate_logic.parse_allowed_files(spec_file)
    if not allowed_files:
        return False
    gate_logic.fetch_develop(project_dir)
    impl_sha = gate_logic.find_implementation_commit(project_dir, spec_id, allowed_files)
    if not impl_sha:
        return False
    try:
        lifecycle.write_lifecycle(
            project_dir,
            spec_id,
            "done",
            by="orchestrator",
            reason=f"already_implemented_on_develop:{impl_sha[:12]}",
        )
        log.info(
            "reconciled: %s already implemented on develop (%s) — marked done, no dispatch",
            spec_id,
            impl_sha[:12],
        )
    except lifecycle.LifecycleAlreadyDoneError:
        log.info("reconcile noop: %s already done (race)", spec_id)
    except lifecycle.LifecycleWriteRaceError:
        log.info("reconcile deferred: %s CAS race, retry next cycle", spec_id)
    return True


def record_dispatch(
    project_id: str,
    project_dir: str,
    spec_id: str,
    provider: str,
    task_label: str,
    pueue_id: int,
) -> None:
    """DB bookkeeping + lifecycle SoT write for a successful pueue dispatch.

    BUG-218: lifecycle SoT must show the spec is running (ADR-023). Without
    this the documented queued -> in_progress -> done flow never happens:
    started_at stays null forever and reconcile_orphans has nothing to
    reconcile. Called AFTER _pueue_add, never before: the yaml needs the real
    pueue_id, and reconcile_orphans keys crash recovery on it.

    A failed lifecycle write must NEVER unwind the dispatch — the task is
    already queued in pueue and will run regardless. Worst case we degrade to
    the pre-BUG-218 behaviour (status stays queued), which
    pueue_has_active_label already tolerates. So: log and continue, never
    re-raise, never signal failure to the caller.
    """
    db.try_acquire_slot(project_id, provider, pueue_id)
    db.log_task(
        project_id,
        task_label,
        "autopilot",
        "running",
        pueue_id,
        branch=f"feature/{spec_id}",
    )
    db.update_project_phase(project_id, "autopilot", spec_id)
    try:
        lifecycle.write_lifecycle(
            project_dir,
            spec_id,
            "in_progress",
            by="orchestrator",
            pueue_id=pueue_id,
        )
    except lifecycle.LifecycleAlreadyDoneError:
        # Rule 7 (ADR-025): callback closed the spec between the TOCTOU
        # re-check and here. The dispatch cannot be unwound — the pueue task
        # is queued and will start a session against a spec that is now done.
        # How cheaply that session exits is the autopilot skill's early-exit
        # check, not ours.
        log.warning("in_progress skipped: %s already done (race)", spec_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("in_progress write failed for %s (dispatch stands): %s", spec_id, exc)


def dispatch_night_review() -> None:
    """Check .review-trigger and dispatch night reviewer if present.

    Patch target warning (TECH-215): this function reads `SCRIPT_DIR` and
    `_pueue_add` from THIS module's globals, not the orchestrator facade's.
    A future test written as `patch("orchestrator._pueue_add")` would rebind
    a name this body never reads and pass silently while shelling out to the
    live pueue daemon. Patch `orchestrator_queue.*` instead.
    """
    trigger = SCRIPT_DIR / ".review-trigger"
    if not trigger.is_file():
        return
    project_ids = trigger.read_text().strip()
    trigger.unlink(missing_ok=True)
    if not project_ids:
        return
    log.info("dispatching night review: %s", project_ids)
    _pueue_add(
        "night-reviewer",
        "night-review",
        [str(SCRIPT_DIR / "night-reviewer.sh")] + project_ids.split(),
    )
