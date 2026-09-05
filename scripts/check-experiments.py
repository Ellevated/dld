#!/usr/bin/env python3
"""Gate: every shipped change has a due verdict, and no verdict is overdue.

The failure this closes is not a bug, it is a silence. A prompt change ships, everyone
agrees it should help, and nothing ever asks whether it did. Four months later the fleet
turns out to have been running an older model than the config named, and a code graph
nobody ever called was loaded into twelve agents per run. Both were found by accident.

So: a change to how the fleet runs gets a file in `ai/experiments/`, stating what should
move, by how much, and when to look. This gate fails when a stated deadline passes with
no verdict written. It cannot check whether the hypothesis was right — only that somebody
was made to look.

    python3 scripts/check-experiments.py            # 0 = nothing overdue, 1 = look now
    python3 scripts/check-experiments.py --json

Front matter is deliberately flat key/value — parsed with stdlib, so the gate runs in CI
with no dependency to install and cannot fail open because pyyaml was missing.
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = REPO / "ai" / "experiments"
METRICS = REPO / "scripts" / "metrics" / "run_metrics.py"

REQUIRED = ("id", "title", "opened", "status", "metric", "baseline", "expected")
OPEN_STATES = ("open",)
CLOSED_STATES = ("confirmed", "refuted", "inconclusive", "abandoned")


def parse_front_matter(path: Path) -> dict | None:
    """Read the leading `---` block as flat key: value pairs. None if there is none."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    _, _, rest = text.partition("---\n")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return None
    data = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        if not _:
            continue
        data[key.strip()] = value.strip()
    # Repo-relative when it is under the repo (the normal case, and what a reader wants
    # to paste), absolute otherwise — `--dir` accepts any path, and a crash there would
    # take the gate down over a cosmetic detail.
    try:
        data["_path"] = str(path.relative_to(REPO))
    except ValueError:
        data["_path"] = str(path)
    return data


def runs_since(date: str) -> int | None:
    """How many autopilot runs finished since `date`. None when logs are unavailable.

    CI has no orchestrator logs, and that is fine: the date deadline still applies there.
    Silently treating "cannot count" as "not due yet" is what a gate must never do, so
    the two cases stay distinct in the output.
    """
    if not METRICS.exists():
        return None
    try:
        out = subprocess.run(
            [sys.executable, str(METRICS), "--count-since", date, "--skill", "autopilot"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def check(experiments: list, today: datetime.date) -> list:
    """Return one problem dict per experiment that needs a human. Empty = clean."""
    problems = []
    for exp in experiments:
        eid = exp.get("id", exp["_path"])
        missing = [k for k in REQUIRED if not exp.get(k)]
        if missing:
            problems.append(
                {
                    "id": eid,
                    "path": exp["_path"],
                    "kind": "incomplete",
                    "detail": f"missing: {', '.join(missing)}",
                }
            )
            continue

        status = exp["status"]
        if status in CLOSED_STATES:
            if not exp.get("verdict"):
                problems.append(
                    {
                        "id": eid,
                        "path": exp["_path"],
                        "kind": "closed_without_verdict",
                        "detail": f"status={status} but no `verdict:` line — say what the numbers showed",
                    }
                )
            continue
        if status not in OPEN_STATES:
            problems.append(
                {
                    "id": eid,
                    "path": exp["_path"],
                    "kind": "bad_status",
                    "detail": f"unknown status: {status}",
                }
            )
            continue

        due_date = exp.get("check_after_date")
        due_runs = exp.get("check_after_runs")
        if not due_date and not due_runs:
            problems.append(
                {
                    "id": eid,
                    "path": exp["_path"],
                    "kind": "no_deadline",
                    "detail": "an open experiment needs `check_after_date:` or `check_after_runs:`",
                }
            )
            continue

        if due_date:
            try:
                if datetime.date.fromisoformat(due_date) <= today:
                    problems.append(
                        {
                            "id": eid,
                            "path": exp["_path"],
                            "kind": "overdue",
                            "detail": f"due {due_date} — measure it and write the verdict",
                        }
                    )
                    continue
            except ValueError:
                problems.append(
                    {
                        "id": eid,
                        "path": exp["_path"],
                        "kind": "bad_date",
                        "detail": f"check_after_date: {due_date}",
                    }
                )
                continue

        if due_runs:
            try:
                threshold = int(due_runs)
            except ValueError:
                problems.append(
                    {
                        "id": eid,
                        "path": exp["_path"],
                        "kind": "bad_runs",
                        "detail": f"check_after_runs: {due_runs}",
                    }
                )
                continue
            seen = runs_since(exp["opened"])
            if seen is not None and seen >= threshold:
                problems.append(
                    {
                        "id": eid,
                        "path": exp["_path"],
                        "kind": "enough_runs",
                        "detail": f"{seen} autopilot runs since {exp['opened']} (threshold {threshold}) — measure it",
                    }
                )
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dir", default=str(EXPERIMENTS_DIR))
    args = ap.parse_args(argv)

    exp_dir = Path(args.dir)
    if not exp_dir.is_dir():
        print(f"no experiments dir ({exp_dir}) — nothing to check")
        return 0

    experiments = []
    for path in sorted(exp_dir.glob("*.md")):
        if path.name.upper() in ("README.MD", "INDEX.MD"):
            continue
        fm = parse_front_matter(path)
        if fm is None:
            print(f"WARN: {path.name} has no front matter — skipped", file=sys.stderr)
            continue
        experiments.append(fm)

    problems = check(experiments, datetime.date.today())
    openn = len([e for e in experiments if e.get("status") in OPEN_STATES])

    if args.json:
        print(
            json.dumps({"total": len(experiments), "open": openn, "problems": problems}, indent=2)
        )
        return 1 if problems else 0

    print(f"experiments: {len(experiments)} total, {openn} open")
    if not problems:
        print("OK — nothing due.")
        return 0
    print(f"\n{len(problems)} need attention:\n")
    for p in problems:
        print(f"  [{p['kind']}] {p['id']} — {p['detail']}")
        print(f"      {p['path']}")
    print("\nMeasure with: python3 scripts/metrics/run_metrics.py --split <opened date>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
