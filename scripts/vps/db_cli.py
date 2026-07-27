#!/usr/bin/env python3
"""
Module: db_cli
Role: argv dispatcher for `python3 db.py <cmd>` (night-reviewer.sh calls it 7 times).
Uses: json, sys (stdlib).
Used by: db.py `if __name__ == "__main__":` only.

Pure leaf (TECH-212): must never import db. Under `python3 db.py` that module is
__main__, so an `import db` here would create a SECOND module object with its own
DB_PATH and _MIGRATIONS_APPLIED. The caller passes itself in as `api` instead.

Command set and output are frozen — night-reviewer.sh parses stdout with jq and
compares get-new-findings against the literal "[]".
"""

import json
import sys

_USAGE = (
    "Usage: python3 db.py <seed|save-finding|get-new-findings"
    "|update-finding-status|update-phase> [args...]"
)


def main(argv: list[str], api) -> int:
    """Dispatch argv. `api` is the db module. Returns the process exit code."""
    cmd = argv[1] if len(argv) > 1 else ""

    if cmd == "seed":
        if len(argv) != 3:
            print("Usage: python3 db.py seed <path/to/projects.json>", file=sys.stderr)
            return 1
        with open(argv[2], encoding="utf-8") as f:
            projects = json.load(f)
        api.seed_projects_from_json(projects)
        print(f"seeded {len(projects)} projects")
        return 0

    if cmd == "save-finding":
        # Args: project_id fingerprint severity confidence file_path line_range summary suggestion
        if len(argv) != 10:
            print(
                "Usage: python3 db.py save-finding <project_id> <fingerprint> <severity>"
                " <confidence> <file_path> <line_range> <summary> <suggestion>",
                file=sys.stderr,
            )
            return 1
        fid = api.save_finding(
            argv[2],
            argv[3],
            argv[4],
            argv[5],
            argv[6],
            argv[7],
            argv[8],
            argv[9],
        )
        print(fid if fid is not None else "duplicate")
        return 0

    if cmd == "get-new-findings":
        if len(argv) != 3:
            print("Usage: python3 db.py get-new-findings <project_id>", file=sys.stderr)
            return 1
        print(json.dumps(api.get_new_findings(argv[2])))
        return 0

    if cmd == "update-finding-status":
        if len(argv) != 4:
            print(
                "Usage: python3 db.py update-finding-status <finding_id> <status>",
                file=sys.stderr,
            )
            return 1
        api.update_finding_status(int(argv[2]), argv[3])
        print(f"updated finding {argv[2]} -> {argv[3]}")
        return 0

    if cmd == "update-phase":
        if len(argv) != 4:
            print("Usage: python3 db.py update-phase <project_id> <phase>", file=sys.stderr)
            return 1
        api.update_project_phase(argv[2], argv[3])
        print(f"phase: {argv[2]} -> {argv[3]}")
        return 0

    print(_USAGE, file=sys.stderr)
    return 1
