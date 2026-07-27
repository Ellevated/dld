#!/usr/bin/env python3
"""
Module: recover_false_reconciliation
Role: One-shot operator helper. Reopens specs the reconciliation gate closed
      against their own birth commit (`lifecycle(BUG-460): queued`).

The gate bug is fixed in `gate_logic.strip_bookkeeping_paths` (2026-07-27), but
`done` is terminal by construction (Rule 7, ADR-025) — so specs already closed
by the bug cannot be reopened by any normal path. This walks every project,
finds the signature, and demotes to `queued` via
`lifecycle.recover_false_reconciliation`, which refuses anything whose cited
commit is real work.

Dry-run by default. `--confirm` executes.

Uses:
  - lifecycle: list_by_status, read_lifecycle, recover_false_reconciliation
  - projects.json: iterate projects

Used by:
  - operator: manual, once per VPS after deploying the gate fix

Glossary: ai/glossary/orchestrator.md
"""

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = str(Path(__file__).resolve().parent)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import lifecycle  # noqa: E402

PROJECTS_JSON = os.environ.get("PROJECTS_JSON", str(Path(SCRIPT_DIR) / "projects.json"))
_REASON = "false reconciliation against own lifecycle commit — gate fix 2026-07-27"


def _projects() -> list[tuple[str, str]]:
    with open(PROJECTS_JSON, encoding="utf-8") as fh:
        data = json.load(fh)
    return [(p.get("id", "?"), p["path"]) for p in data if p.get("path")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true", help="execute (default: dry-run)")
    ap.add_argument("--project", help="limit to one project id")
    args = ap.parse_args(argv)

    recovered, refused, failed = 0, 0, 0

    for project_id, path in _projects():
        if args.project and project_id != args.project:
            continue
        if not Path(path).is_dir():
            print(f"  skip {project_id}: path not found ({path})")
            continue
        try:
            done_specs = lifecycle.list_by_status(path, "done")
        except Exception as exc:  # noqa: BLE001 — operator tool, report and continue
            print(f"  skip {project_id}: {exc}")
            continue

        for spec_id in done_specs:
            row = lifecycle.read_lifecycle(path, spec_id) or {}
            reason = row.get("blocked_reason") or ""
            if not reason.startswith("already_implemented_on_develop:"):
                continue
            if not args.confirm:
                # Validate without writing: the function raises before any CAS write.
                print(f"  WOULD RECOVER {project_id}/{spec_id}  ({reason})")
                recovered += 1
                continue
            try:
                lifecycle.recover_false_reconciliation(path, spec_id, reason=_REASON)
                print(f"  RECOVERED {project_id}/{spec_id}")
                recovered += 1
            except lifecycle.NotFalseReconciliationError as exc:
                print(f"  keep      {project_id}/{spec_id} — {exc.criterion}")
                refused += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED    {project_id}/{spec_id}: {exc}")
                failed += 1

    mode = "EXECUTED" if args.confirm else "DRY-RUN (pass --confirm to execute)"
    print(f"\n{mode}: {recovered} recovered, {refused} kept as done, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
