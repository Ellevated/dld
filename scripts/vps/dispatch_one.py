#!/usr/bin/env python3
"""
Module: dispatch_one
Role: run exactly one spec, on explicit instruction. The dispatcher's only verb.

The split this file exists to enforce (2026-09-07): a model decides WHAT runs,
code performs the run. Everything here is mechanism that must not be re-invented
per decision — take a compute slot, submit to pueue under a label, write the
lifecycle row, log the task. Nothing here judges whether the spec deserves to
run: that judgement now lives in the dispatcher prompt, which can also repair a
spec instead of refusing it.

Three refusals remain, and all three are physics rather than policy:
  * no free slot for the provider — there is nowhere to run;
  * this spec is already live in pueue — a second run would fight the first over
    the same branch and worktree;
  * the spec body does not exist — there is nothing to hand the agent.
Each prints a one-line reason and exits 2, so the caller can say why in words.

Usage:
    python3 dispatch_one.py <project_id> <SPEC-ID> [--skill autopilot]
                            [--provider claude] [--reason "why now"]

Uses: argparse, json, os, sys, pathlib, db, lifecycle, orchestrator_queue,
      orchestrator_slots
Used by: skills/dispatcher (via ~/ops/dispatcher.sh), operators on the VPS
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import db  # noqa: E402
import orchestrator_queue  # noqa: E402
import orchestrator_slots  # noqa: E402


def _fail(reason: str) -> int:
    print(json.dumps({"dispatched": False, "reason": reason}, ensure_ascii=False))
    return 2


def dispatch(project_id: str, spec_id: str, skill: str, provider: str | None, reason: str) -> int:
    state = db.get_project_state(project_id)
    if not state:
        return _fail(f"unknown project {project_id!r} — not in project_state")
    project_dir = state["path"]
    if not os.path.isdir(project_dir):
        return _fail(f"project path missing on disk: {project_dir}")

    spec_files = orchestrator_queue.spec_body_files(project_dir, spec_id)
    if not spec_files:
        return _fail(f"{spec_id}: no spec body in {project_dir}/ai/features/")

    provider = provider or (state.get("provider") or "claude")
    if db.get_available_slots(provider) < 1:
        return _fail(f"no free {provider} slot")

    task_label = f"{project_id}:{spec_id}"
    if orchestrator_slots.pueue_has_active_label(task_label):
        return _fail(f"{task_label} is already live in pueue")
    if orchestrator_slots.pueue_has_active_spec(spec_id):
        return _fail(f"{spec_id} is live in pueue under another project")

    task = f"/{skill} {spec_id}" if skill != "autopilot" else f"/autopilot {spec_id}"
    pueue_id = orchestrator_slots._pueue_add(
        f"{provider}-runner",
        task_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_dir, provider, skill, task],
        env={
            "CLAUDE_PROJECT_DIR": project_dir,
            "CLAUDE_CURRENT_SPEC_PATH": str(spec_files[0]),
        },
    )
    if pueue_id is None:
        return _fail(f"pueue rejected {task_label}")

    orchestrator_queue.record_dispatch(
        project_id, project_dir, spec_id, provider, task_label, pueue_id
    )
    print(
        json.dumps(
            {
                "dispatched": True,
                "project": project_id,
                "spec_id": spec_id,
                "skill": skill,
                "provider": provider,
                "pueue_id": pueue_id,
                "reason": reason,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Dispatch one spec on explicit instruction.")
    ap.add_argument("project_id")
    ap.add_argument("spec_id")
    ap.add_argument("--skill", default="autopilot")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--reason", default="", help="one line: why this spec, now")
    args = ap.parse_args(argv[1:])
    return dispatch(args.project_id, args.spec_id, args.skill, args.provider, args.reason)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
