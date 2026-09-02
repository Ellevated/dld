#!/usr/bin/env python3
"""
Module: orchestrator_ci_gate
Role: CI stop-the-line gate for dispatch — hold queued specs while the project's
      local CI watchdog says `fail`.

Why (awardybot reflect R100 §1 / R101 §3, 2026-09-02): six specs were closed `done`
on top of a 60-hour red develop because scan_queued never looked at the CI verdict.
Source of truth is the watchdog's own state file, written by ~/ops/<project>-ci.sh:
~/ops/state/<project>-ci.status = ok | fail. Fails OPEN: no state file → the
project has no local CI watchdog → no gate.

Something has to be allowed to repair the red, so two overrides exist: a spec whose
body carries a line `ci-gate: bypass` (a CI-repair spec) is let through, and the
operator can drop `<project>-ci.gate_off` next to the status file to switch the
gate off for the whole project.

Uses: os, re, pathlib, lifecycle (import), orchestrator_queue.spec_body_files
Used by: orchestrator.scan_queued
"""

import logging
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import lifecycle  # noqa: E402
from orchestrator_queue import spec_body_files  # noqa: E402

log = logging.getLogger("orchestrator")

CI_STATE_DIR = Path(os.environ.get("CI_STATE_DIR", str(Path.home() / "ops" / "state")))
_CI_BYPASS_RE = re.compile(r"^\s*ci[-_]gate:\s*bypass\b", re.IGNORECASE | re.MULTILINE)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def ci_red_skip_reason(project_id: str, project_dir: str, spec_id: str) -> str | None:
    """Reason to HOLD dispatch of spec_id while the project's CI is red, else None."""
    status_file = CI_STATE_DIR / f"{project_id}-ci.status"
    if not status_file.is_file():
        return None
    if (CI_STATE_DIR / f"{project_id}-ci.gate_off").exists():
        return None
    if _read(status_file) != "fail":
        return None
    for spec_file in spec_body_files(project_dir, spec_id):
        body = _read(spec_file)
        if body is not None and _CI_BYPASS_RE.search(body):
            return None
    red_since = _read(CI_STATE_DIR / f"{project_id}-ci.red_since") or "?"
    return (
        f"{project_id} CI red since {red_since} — stop-the-line; "
        f"override: `ci-gate: bypass` in the spec body or {project_id}-ci.gate_off"
    )


def queued_after_ci_gate(project_id: str, project_dir: str) -> list:
    """queued/resumed lifecycle rows minus the ones held by the CI gate.

    Drop-in for `lifecycle.list_by_status(project_dir, {"queued", "resumed"})` in
    scan_queued: same shape, same order, only the held rows removed (each logged).
    """
    rows = lifecycle.list_by_status(project_dir, {"queued", "resumed"})
    kept = []
    for row in rows:
        hold = ci_red_skip_reason(project_id, project_dir, row["spec_id"])
        if hold:
            log.info("CI_GATE: hold %s — %s", row["spec_id"], hold)
            continue
        kept.append(row)
    return kept
