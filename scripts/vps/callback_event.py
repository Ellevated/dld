#!/usr/bin/env python3
"""
Module: callback_event
Role: Hermes events — artifact selection for qa/reflect, and the one autopilot
      event per run, built from the Step 7 verdict rather than the pueue exit code.

Uses:
  - event_writer: notify (TECH-224)

Used by:
  - callback.main: write_event_for_skill (Step 5, qa/reflect/spark), autopilot_event
    (Step 7b)

Extracted from callback.py by TECH-224 (callback.py had no LOC headroom left).
`event_writer.notify` is called as a module attribute so a monkeypatch on
`event_writer.wake_hermes` still intercepts the fire-and-forget Hermes spawn.
"""

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import event_writer  # noqa: E402  — Hermes events (TECH-224)


def pick_artifact(project_path: str, skill: str, task_label: str) -> str:
    """Pick the artifact to attach to a Hermes event, relative to project_path.

    qa: prefer the file naming this run's own spec id (case-insensitive, not
    followed by a digit so a shorter id can't match a longer one), else the
    newest file by mtime. reflect: always newest by mtime. Anything else, or
    no candidate file, returns "".
    """
    p = Path(project_path)
    if skill == "qa":
        candidates = list(p.glob("ai/qa/[0-9]*-*.md"))
        if not candidates:
            return ""
        spec_id = task_label.removeprefix("qa-")
        own_re = re.compile(re.escape(spec_id) + r"(?!\d)", re.IGNORECASE)
        own = [f for f in candidates if own_re.search(f.name)]
        pool = own or candidates
        return str(max(pool, key=lambda f: f.stat().st_mtime).relative_to(p))
    if skill == "reflect":
        candidates = list(p.glob("ai/reflect/findings-*.md"))
        if not candidates:
            return ""
        return str(max(candidates, key=lambda f: f.stat().st_mtime).relative_to(p))
    return ""


def write_event_for_skill(project_path: str, skill: str, status: str, task_label: str) -> None:
    """Write the Hermes event for qa / reflect / spark. Autopilot's event is
    `autopilot_event`, built after the Step 7 verdict.
    """
    if skill not in ("qa", "reflect", "spark"):
        return
    if status != "done" and not (status == "failed" and skill == "qa"):
        return

    artifact_rel = pick_artifact(project_path, skill, task_label)
    event_writer.notify(
        project_path,
        skill,
        status,
        f"{skill} {status} for {task_label}",
        artifact_rel,
    )


def autopilot_event(
    project_path: str,
    task_label: str,
    pueue_status: str,
    verdict: tuple[str, str] | None,
    why: str,
) -> None:
    """Write the one Hermes event for an autopilot run, carrying the Step 7 verdict.

    `verdict` is `(status, reason)` from `verify_status_sync`, or None when Step 7
    reached no decision — the event still fires, noting `why` instead of silence.
    """
    if verdict is not None:
        status, reason = verdict
        event_writer.notify(
            project_path,
            "autopilot",
            status,
            f"autopilot {status} for {task_label}: {reason}",
        )
        return
    event_writer.notify(
        project_path,
        "autopilot",
        pueue_status,
        f"autopilot {pueue_status} for {task_label} — вердикт lifecycle недоступен: {why}",
    )
