#!/usr/bin/env python3
"""
Module: orchestrator_queue
Role: The mechanics of starting one run — find the spec body, record the dispatch
      (slot, task_log, lifecycle `in_progress`) — plus the night-review trigger.

What this module no longer holds (removed 2026-09-27): the built-in gate chain
that decided WHICH spec runs — `gate_before_pueue_add`, `recently_processed`,
`spec_has_allowlist`, `resolve_provider`, `status_still_dispatchable`,
`reconcile`/`reconcile_if_implemented`, `_unmet_dependencies`. Since 2026-09-07
that decision belongs to the dispatcher skill, and the chain ran only under
`DISPATCH_MODE=builtin`, which nothing set. Every new rule had to be written
twice — once here, once in `dispatch_one.py`. See
docs/2026-09-27-snyatie-relsov-dispetchera.md.

Uses: db (import), gate_ancestry (import), lifecycle (import),
      orchestrator_slots._pueue_add
Used by: dispatch_one (spec_body_files, record_dispatch — attribute calls),
         orchestrator (facade re-export of dispatch_night_review)
"""

import logging
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import gate_ancestry  # noqa: E402
import lifecycle  # noqa: E402
from orchestrator_slots import _pueue_add  # noqa: E402,F401

log = logging.getLogger("orchestrator")


def spec_body_files(project_dir: str, spec_id: str) -> list[Path]:
    """Spec body file(s) matching spec_id under ai/features/, or []."""
    features_dir = Path(project_dir) / "ai" / "features"
    return list(features_dir.glob(f"{spec_id}*"))


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
    try:
        branch = gate_ancestry.branch_ref_for(spec_id)
    except ValueError:
        branch = f"task/{spec_id}"  # mirrors the bash fallback in autopilot-git.md:57
    db.try_acquire_slot(project_id, provider, pueue_id)
    db.log_task(
        project_id,
        task_label,
        "autopilot",
        "running",
        pueue_id,
        branch=branch,
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
        # Rule 7 (ADR-025): callback closed the spec between the dispatcher's
        # briefing and here. The dispatch cannot be unwound — the pueue task
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
