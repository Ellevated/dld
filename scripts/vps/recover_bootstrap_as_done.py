#!/usr/bin/env python3
"""
Module: recover_bootstrap_as_done
Role: One-shot operator helper — find and demote lifecycle yamls that look
      like "bootstrap-as-done" artifacts (status=done, no transitions, no
      pueue_id, no finished_at — classic signature of the TECH-195 bug).
Uses: lifecycle (read/list/recover_bootstrap_artifact)
Used by: operator (manual CLI, post-TECH-195 deploy)

USAGE
-----
    python3 scripts/vps/recover_bootstrap_as_done.py             # dry-run all projects
    python3 scripts/vps/recover_bootstrap_as_done.py --project=awardybot
    python3 scripts/vps/recover_bootstrap_as_done.py --confirm   # really do it
    python3 scripts/vps/recover_bootstrap_as_done.py --json      # machine output

SAFETY
------
- Default mode is dry-run; nothing changes without --confirm.
- Only specs matching ALL four criteria are touched:
    * status == "done"
    * transitions == [] (or absent)
    * pueue_id is None (never ran)
    * finished_at is None (never closed by callback)
- Demote goes through lifecycle.recover_bootstrap_artifact — the narrow
  Rule 7 escape that validates the signature in the primitive itself
  (NotBootstrapArtifactError if criteria mismatch). by="operator" so the
  transition is auditable.
- Specs with even one transition are left alone (legitimate dones).

Exit code: 0 if clean / dry-run / all-success, 1 if any recovery fails.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import lifecycle  # noqa: E402

log = logging.getLogger("recover_bootstrap_as_done")


# ──────────────────────────────────────────────────────────────────────
# Detection
# ──────────────────────────────────────────────────────────────────────


def _is_bootstrap_as_done(data: dict) -> bool:
    """Return True iff yaml looks like a silent-bootstrap artifact.

    Criteria (ALL must hold):
      status == "done"
      transitions empty
      pueue_id is None (never dispatched)
      finished_at is None (callback never closed it)
    """
    if data.get("status") != "done":
        return False
    if data.get("transitions"):
        return False
    if data.get("pueue_id") is not None:
        return False
    if data.get("finished_at") is not None:
        return False
    return True


def find_bootstrap_as_done(project_dir: str) -> list[str]:
    """Return sorted list of spec_ids that look like bootstrap-as-done."""
    if not Path(project_dir).is_dir():
        return []
    try:
        candidates = lifecycle.list_by_status(project_dir, "done")
    except Exception as exc:  # noqa: BLE001
        log.warning("lifecycle.list_by_status failed for %s: %s", project_dir, exc)
        return []
    return sorted(d["spec_id"] for d in candidates if _is_bootstrap_as_done(d))


# ──────────────────────────────────────────────────────────────────────
# Recovery
# ──────────────────────────────────────────────────────────────────────


def recover_one(project_dir: str, spec_id: str, reason: str) -> int:
    """Demote a single bootstrap-as-done via lifecycle.recover_bootstrap_artifact.

    Returns:
        0 on success.
        4 if the signature no longer matches (legitimate done — refused).
        5 on any other lifecycle error (race, missing HEAD yaml, etc).
    """
    try:
        lifecycle.recover_bootstrap_artifact(
            project_dir, spec_id, reason=reason, by="operator"
        )
        return 0
    except lifecycle.NotBootstrapArtifactError as exc:
        log.warning("REFUSED: %s/%s: %s", project_dir, spec_id, exc)
        return 4
    except (lifecycle.LifecycleWriteRaceError, FileNotFoundError, ValueError) as exc:
        log.warning("FAILED: %s/%s: %s", project_dir, spec_id, exc)
        return 5


# ──────────────────────────────────────────────────────────────────────
# Project iteration
# ──────────────────────────────────────────────────────────────────────


def _load_projects(projects_json_path: str | None) -> list[dict]:
    """Load projects from projects.json. Returns list of {project_id, path, ...}."""
    path = projects_json_path or os.environ.get("PROJECTS_JSON")
    if not path:
        path = str(SCRIPT_DIR / "projects.json")
    if not Path(path).is_file():
        log.warning("projects.json not found: %s", path)
        return []
    with open(path) as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def run(
    dry_run: bool,
    project_filter: str | None,
    projects_json: str | None,
    json_output: bool,
    reason: str,
) -> int:
    projects = _load_projects(projects_json)
    if project_filter:
        projects = [p for p in projects if p.get("project_id") == project_filter]
        if not projects:
            print(f"recover: project_id={project_filter!r} not found", file=sys.stderr)
            return 2

    overall_rc = 0
    summary: list[dict] = []

    for proj in projects:
        project_id = proj.get("project_id", "?")
        project_dir = proj.get("path")
        if not project_dir:
            continue
        candidates = find_bootstrap_as_done(project_dir)
        proj_summary = {
            "project_id": project_id,
            "path": project_dir,
            "candidates": candidates,
            "count": len(candidates),
            "demoted": [],
            "failed": [],
        }
        if candidates and not dry_run:
            for spec_id in candidates:
                rc = recover_one(project_dir, spec_id, reason)
                if rc == 0:
                    proj_summary["demoted"].append(spec_id)
                else:
                    proj_summary["failed"].append({"spec_id": spec_id, "rc": rc})
                    overall_rc = 1
        summary.append(proj_summary)

    if json_output:
        print(
            json.dumps(
                {"dry_run": dry_run, "projects": summary},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _print_text(summary, dry_run)
    return overall_rc


def _print_text(summary: list[dict], dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    total_candidates = sum(p["count"] for p in summary)
    total_demoted = sum(len(p["demoted"]) for p in summary)
    total_failed = sum(len(p["failed"]) for p in summary)
    print(f"=== recover_bootstrap_as_done [{mode}] ===")
    print()
    for proj in summary:
        if not proj["candidates"]:
            continue
        print(f"  {proj['project_id']} ({proj['path']}):")
        for spec_id in proj["candidates"]:
            mark = "  "
            if spec_id in proj["demoted"]:
                mark = "OK "
            elif any(f["spec_id"] == spec_id for f in proj["failed"]):
                mark = "X  "
            print(f"    {mark}{spec_id}")
        print()
    print(
        f"Summary: {total_candidates} candidates"
        + (f", {total_demoted} demoted, {total_failed} failed" if not dry_run else "")
    )
    if dry_run and total_candidates:
        print()
        print("Re-run with --confirm to actually demote.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="recover_bootstrap_as_done",
        description="Find/demote bootstrap-as-done lifecycle artifacts (TECH-195).",
    )
    parser.add_argument(
        "--project",
        dest="project_filter",
        help="Only process this project_id (default: all from projects.json).",
    )
    parser.add_argument(
        "--projects-json",
        help="Path to projects.json (default: $PROJECTS_JSON or scripts/vps/projects.json).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually demote (default: dry-run, no changes).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON instead of text.",
    )
    parser.add_argument(
        "--reason",
        default="TECH-195 bootstrap-as-done recovery",
        help="Reason recorded in lifecycle transitions.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    return run(
        dry_run=not args.confirm,
        project_filter=args.project_filter,
        projects_json=args.projects_json,
        json_output=args.json_output,
        reason=args.reason,
    )


if __name__ == "__main__":
    sys.exit(main())
