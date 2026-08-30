#!/usr/bin/env python3
"""
Module: callback_dispatch
Role: Post-autopilot tail — resolve the spec id, decide whether completion is
      confirmed (Step 6 of callback.main) and dispatch QA / Reflect into pueue.

Uses:
  - db: get_project_state, try_acquire_slot, log_task
  - gate_logic: parse_allowed_files, fetch_develop, find_implementation_commit
  - subprocess: `pueue status --json`, `pueue add`

Used by:
  - callback.main: _step6_dispatch_qa_reflect (Step 6), resolve_spec_id (Step 7)

Extracted from callback.py by TECH-216. Callers reach these names through the
module attribute (`callback_dispatch.dispatch_qa`) so that
`monkeypatch.setattr(callback_dispatch, ...)` intercepts them.
"""

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import gate_logic  # noqa: E402

log = logging.getLogger("callback")

# Spec-id regex (TECH-182). `[a-z]*` captures sub-spec suffixes (ARCH-176a/b/c).
# Single source is gate_logic (TECH-210); mirrors orchestrator.scan_backlog.
_SPEC_ID_RE = gate_logic._SPEC_ID_RE


def resolve_spec_id(task_label: str, preview: str, project_path: str) -> str | None:
    """Multi-layer spec_id resolution."""
    # Layer 1: from task label
    m = _SPEC_ID_RE.search(task_label)
    if m:
        return m.group(0)

    # Layer 2: from preview text
    if preview:
        m = _SPEC_ID_RE.search(preview)
        if m:
            return m.group(0)

    # Layer 3: from inbox done files
    if task_label.startswith("inbox-") and project_path:
        done_dir = Path(project_path) / "ai" / "inbox" / "done"
        if done_dir.is_dir():
            for f in sorted(done_dir.glob("*.md"), reverse=True):
                text = f.read_text(errors="replace")
                m = re.search(r"\*\*SpecID:\*\*\s*(\S+)", text)
                if m:
                    sm = _SPEC_ID_RE.search(m.group(1))
                    if sm:
                        return sm.group(0)
    return None


def is_already_queued(label: str) -> bool:
    """Check if a task with this label is Running or Queued."""
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        for task in data.get("tasks", {}).values():
            if task.get("label") == label:
                status = task.get("status", {})
                if isinstance(status, dict) and ("Running" in status or "Queued" in status):
                    return True
        return False
    except Exception:
        return False


def _pueue_add(group: str, label: str, cmd: list) -> int | None:
    """Submit task to pueue. Returns task ID or None."""
    try:
        pueue_cmd = [
            "pueue",
            "add",
            "--group",
            group,
            "--label",
            label,
            "--print-task-id",
            "--",
        ] + cmd
        result = subprocess.run(
            pueue_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stdout.strip().splitlines():
            m = re.search(r"(\d+)", line.strip())
            if m:
                return int(m.group(1))
        return None
    except Exception:
        return None


def dispatch_qa(project_id: str, project_path: str, spec_id: str, provider: str) -> None:
    """Dispatch QA task via pueue."""
    qa_label = f"{project_id}:qa-{spec_id}"
    if is_already_queued(qa_label):
        log.info("skip duplicate QA: %s", qa_label)
        return
    runner_group = f"{provider}-runner"
    pueue_id = _pueue_add(
        runner_group,
        qa_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_path, provider, "qa", f"/qa {spec_id}"],
    )
    if pueue_id:
        db.try_acquire_slot(project_id, provider, pueue_id)
        db.log_task(project_id, qa_label, "qa", "running", pueue_id)
        log.info("QA dispatched: %s pueue_id=%d", qa_label, pueue_id)
    else:
        log.warning("QA dispatch failed: %s", qa_label)


def dispatch_reflect(project_id: str, project_path: str, task_label: str, provider: str) -> None:
    """Dispatch reflect task via pueue."""
    reflect_label = f"{project_id}:reflect-{task_label}"
    if is_already_queued(reflect_label):
        log.info("skip duplicate reflect: %s", reflect_label)
        return
    runner_group = f"{provider}-runner"
    pueue_id = _pueue_add(
        runner_group,
        reflect_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_path, provider, "reflect", "/reflect"],
    )
    if pueue_id:
        db.try_acquire_slot(project_id, provider, pueue_id)
        db.log_task(project_id, reflect_label, "reflect", "running", pueue_id)
        log.info("reflect dispatched: %s pueue_id=%d", reflect_label, pueue_id)
    else:
        log.warning("reflect dispatch failed: %s", reflect_label)


# --- main Step 6: QA + Reflect dispatch decision (TECH-194 Layer E / TECH-207) ---

# Status values the autopilot may signal to hold a spec deliberately.
_HOLD_SIGNALS = ("blocked", "needs_review")


def _merge_confirmed(project_path: str, spec_id: str, task_label: str, task_status: str) -> bool:
    """TECH-207 fallback: is the implementation already on origin/develop?

    Reuses the same gate logic as Step 7. Any error → False (never dispatch on
    doubt; a QA run against nothing burned $2.50 in TECH-194).
    """
    try:
        spec_file = next(iter(Path(project_path).glob(f"ai/features/{spec_id}*.md")), None)
        allowed = gate_logic.parse_allowed_files(spec_file) if spec_file else None
        if not allowed:
            log.info("skip QA+reflect merge fallback: no allowed_files for %s", spec_id)
            return False
        gate_logic.fetch_develop(project_path)
        if gate_logic.find_implementation_commit(project_path, spec_id, allowed):
            log.info(
                "QA_DISPATCH_MERGE_FALLBACK: task_status=%r but impl confirmed "
                "merged on origin/develop for %s — dispatching QA+Reflect",
                task_status,
                spec_id,
            )
            return True
        log.info(
            "skip QA+reflect dispatch: task_status=%r, no merge confirmed "
            "for %s (SIGKILL/abort/incomplete)",
            task_status,
            spec_id,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("QA_DISPATCH_MERGE_FALLBACK: error checking merge for %s: %s", task_label, exc)
        return False


def _step6_dispatch_qa_reflect(
    skill: str,
    status: str,
    task_status: str,
    project_id: str,
    task_label: str,
    preview: str,
) -> None:
    """Step 6: Post-autopilot tail — dispatch QA + Reflect.

    TECH-194 Layer E: allowlist gate — only dispatch when completion is confirmed.
    TECH-207: merge-confirmed fallback — when task_status is missing/displaced
    but the implementation IS confirmed merged on origin/develop, dispatch anyway.

    Dispatch conditions (any of):
      1. task_status == "complete" (explicit signal — original path)
      2. task_status not in ("blocked", "needs_review") AND implementation
         confirmed merged on origin/develop (merge fallback)

    Skip conditions:
      - skill != "autopilot" or status != "done"
      - task_status in ("blocked", "needs_review") — deliberate hold
      - No merge confirmed and task_status != "complete" — SIGKILL/abort
    """
    if skill != "autopilot" or status != "done":
        return

    # Explicit block signals — never dispatch (TECH-194 Layer E preserved)
    if task_status in _HOLD_SIGNALS:
        log.info("skip QA+reflect dispatch: task_status=%r (explicit block signal)", task_status)
        return

    # Resolve state once — reused by both explicit_complete and merge fallback paths.
    try:
        state = db.get_project_state(project_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("skip QA+reflect: get_project_state failed for %s: %s", project_id, exc)
        return
    if not state:
        log.info("skip QA+reflect: no project_state for %s", project_id)
        return
    project_path = state.get("path", "")
    provider = state.get("provider", "claude") or "claude"
    if not project_path:
        log.info("skip QA+reflect: empty project_path for %s", project_id)
        return

    spec_id = resolve_spec_id(task_label, preview, project_path)

    if task_status == "complete":
        dispatch_via = "explicit_complete"
    else:
        if not spec_id:
            log.info("skip QA+reflect merge fallback: no spec_id for %s", task_label)
            return
        if not _merge_confirmed(project_path, spec_id, task_label, task_status):
            return
        dispatch_via = "QA_DISPATCH_MERGE_FALLBACK"

    # Dispatch QA + Reflect (shared path for both explicit_complete and merge fallback)
    try:
        if spec_id:
            dispatch_qa(project_id, project_path, spec_id, provider)
        else:
            log.info("skip QA: no spec_id resolved for %s", task_label)
        dispatch_reflect(project_id, project_path, task_label, provider)
    except Exception as exc:  # noqa: BLE001
        log.warning("post-autopilot dispatch failed (%s): %s", dispatch_via, exc)
