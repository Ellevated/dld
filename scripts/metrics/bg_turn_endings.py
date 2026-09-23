#!/usr/bin/env python3
"""Headless turn-ending measure — did the run end waiting on background work?

TECH-223: headless has nobody to notify when a background task or a polling
loop finishes, so a turn ending on either is lost work. Reads the same run
logs as `run_metrics.py` (`<project>-<ts>.log` + sibling `.stderr.txt`) and
reports, per skill, `bg_killed` (runner killed a still-running background
task) and `ended_on_wait` (last turn looks like a wait). Groups split on
`headless_guards` (TECH-223 Task 2) — sliced by field, not date (EXP-009).

Usage:
    bg_turn_endings.py                            # every slice
    bg_turn_endings.py --skill qa --since 2026-09-23
    bg_turn_endings.py --json

Exit codes: 0 always (a reporting tool, never a gate — see check-experiments.py).
"""

import argparse
import collections
import glob
import json
import os
import re
import sys
from pathlib import Path

from run_metrics import _NAME_RE, DEFAULT_LOG_DIR

_BG_KILLED_MARKER = "Background tasks still running after"
_WAIT_START_RE = re.compile(
    r"^(until |while |for |sleep |export |cd |uv run|python|\.venv/|bash |tail |grep |Wait until)"
)
_PROMISE_RE = re.compile(r"пришлю|вернусь|I'll send|will report", re.IGNORECASE)


def _load_run(path: str) -> dict | None:
    """Parse one run log — same tail-JSON parse as run_metrics._load_run."""
    base = os.path.basename(path)[:-4]
    m = _NAME_RE.match(base)
    if not m:
        return None
    _project, day, _hhmmss = m.groups()
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        i = text.rfind("\n{")
        start = text.find("{") if i < 0 else i + 1
        data = json.loads(text[start:])
    except (OSError, ValueError):
        return None

    stderr_path = path[:-4] + ".stderr.txt"
    bg_killed = False
    if os.path.exists(stderr_path):
        try:
            bg_killed = _BG_KILLED_MARKER in Path(stderr_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            pass

    preview = data.get("result_preview") or ""
    stripped = preview.lstrip()
    first_line = stripped.splitlines()[0] if stripped else ""
    ended_on_wait = bool(_WAIT_START_RE.match(first_line)) or bool(_PROMISE_RE.search(preview))

    return {
        "name": os.path.basename(path),
        "day": day,
        "skill": data.get("skill"),
        "guards": "headless_guards" in data,
        "bg_killed": bg_killed,
        "ended_on_wait": ended_on_wait,
    }


def load_runs(log_dir: Path, skill: str | None, since: str | None, until: str | None) -> list:
    runs = []
    for path in glob.glob(str(log_dir / "*.log")):
        run = _load_run(path)
        if run is None:
            continue
        if skill and run["skill"] != skill:
            continue
        if since and run["day"] < since.replace("-", ""):
            continue
        if until and run["day"] > until.replace("-", ""):
            continue
        runs.append(run)
    return runs


def group(runs: list) -> dict:
    """One row per (skill, guards) slice — the field an experiment cuts on."""
    grouped = collections.defaultdict(list)
    for r in runs:
        label = f"{r['skill']}+guards" if r["guards"] else str(r["skill"])
        grouped[label].append(r)
    return {
        label: {
            "runs": len(rs),
            "bg_killed": sum(1 for r in rs if r["bg_killed"]),
            "ended_on_wait": sum(1 for r in rs if r["ended_on_wait"]),
            "bg_killed_names": [r["name"] for r in rs if r["bg_killed"]],
            "ended_on_wait_names": [r["name"] for r in rs if r["ended_on_wait"]],
        }
        for label, rs in sorted(grouped.items())
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    ap.add_argument("--skill", default="all", help="autopilot | qa | reflect | all")
    ap.add_argument("--since", help="YYYY-MM-DD inclusive")
    ap.add_argument("--until", help="YYYY-MM-DD inclusive")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    log_dir = Path(args.log_dir)
    if not log_dir.is_dir():
        print(f"no log dir: {log_dir} (this machine may not run the orchestrator)", file=sys.stderr)
        return 0

    skill = None if args.skill == "all" else args.skill
    slices = group(load_runs(log_dir, skill, args.since, args.until))

    if args.json:
        print(json.dumps(slices, indent=2))
        return 0

    print(f"skill={args.skill}  logs={log_dir}")
    print(f"{'skill':<22} {'runs':>4} {'bg_killed':>9} {'ended_on_wait':>13}")
    for label, s in slices.items():
        print(f"{label:<22} {s['runs']:4d} {s['bg_killed']:9d} {s['ended_on_wait']:13d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
