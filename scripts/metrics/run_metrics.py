#!/usr/bin/env python3
"""Orchestrator run metrics — the measuring instrument for `ai/experiments/`.

Reads the run logs the runner already writes (`scripts/vps/logs/<project>-<ts>.log`,
plus the sibling `.heartbeat.json` for wall-clock) and prints one row per slice:
how many runs, how many timed out, how long, how much.

**Why this lives in the repo.** Every number in `docs/2026-09-02-autopilot-medlenno-i-dorogo.md`
was produced by throwaway scripts in `/tmp/ap/`. They worked, and then they were gone —
so the next question started from zero, comparisons were never quite like-for-like, and a
change shipped in June could sit unmeasured until September. A measurement you cannot
re-run is an anecdote.

Usage:
    run_metrics.py                             # every slice, autopilot
    run_metrics.py --skill qa --since 2026-08-01
    run_metrics.py --split 2026-09-04          # before/after one change
    run_metrics.py --count-since 2026-09-05    # how many runs since — for the gate
    run_metrics.py --json                      # machine-readable

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

DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "vps" / "logs"
_NAME_RE = re.compile(r"(.+)-(\d{8})-(\d{6})$")


def _load_run(path: str) -> dict | None:
    """Parse one run log. Returns None for anything unreadable — logs are appended to."""
    base = os.path.basename(path)[:-4]
    m = _NAME_RE.match(base)
    if not m:
        return None
    project, day, hhmmss = m.groups()
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        # The JSON body is the last top-level object in the file.
        i = text.rfind("\n{")
        start = text.find("{") if i < 0 else i + 1
        data = json.loads(text[start:])
    except (OSError, ValueError):
        return None

    elapsed_s = None
    hb = path[:-4] + ".heartbeat.json"
    if os.path.exists(hb):
        try:
            elapsed_s = json.loads(Path(hb).read_text(encoding="utf-8")).get("elapsed_s")
        except (OSError, ValueError):
            pass

    return {
        "project": project,
        "day": day,
        "time": hhmmss,
        "skill": data.get("skill"),
        "task": data.get("task"),
        "exit_code": data.get("exit_code"),
        "turns": data.get("turns") or 0,
        "cost_usd": data.get("cost_usd") or 0.0,
        # Present only on runs from 2026-09-05 onward; older logs priced a timeout at
        # $0.00 and said nothing about it, which is the bias this field exists to name.
        "cost_source": data.get("cost_source", "legacy_unknown"),
        "cache_read": data.get("cache_read_input_tokens") or 0,
        "cache_write": data.get("cache_creation_input_tokens") or 0,
        "output_tokens": data.get("output_tokens") or 0,
        "elapsed_s": elapsed_s,
        "cli_version": data.get("cli_version"),
        "model": data.get("model"),
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
    return sorted(runs, key=lambda r: (r["day"], r["time"]))


def _pct(values: list, q: float) -> float:
    """Percentile by nearest rank. Empty → 0, so a slice with no data reads as zero."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def summarize(runs: list) -> dict:
    """One slice of runs → the numbers an experiment's hypothesis is checked against."""
    ok = [r for r in runs if r["exit_code"] == 0]
    timeouts = [r for r in runs if r["exit_code"] == 124]
    failures = [r for r in runs if r["exit_code"] not in (0, 124)]
    minutes = [r["elapsed_s"] / 60 for r in ok if r["elapsed_s"]]
    # Timeout minutes are wall-clock too, and they are the ones that hurt.
    timeout_minutes = [r["elapsed_s"] / 60 for r in timeouts if r["elapsed_s"]]
    costs = [r["cost_usd"] for r in ok if r["cost_usd"]]
    timeout_costs = [r["cost_usd"] for r in timeouts if r["cost_usd"]]
    turns = [r["turns"] for r in ok if r["turns"]]

    return {
        "n": len(runs),
        "ok": len(ok),
        "timeout": len(timeouts),
        "fail": len(failures),
        "timeout_rate": round(len(timeouts) / len(runs), 3) if runs else 0.0,
        "p50_min": round(_pct(minutes, 0.5), 1),
        "p75_min": round(_pct(minutes, 0.75), 1),
        "p90_min": round(_pct(minutes, 0.9), 1),
        "p50_timeout_min": round(_pct(timeout_minutes, 0.5), 1),
        "p50_usd": round(_pct(costs, 0.5), 2),
        "sum_usd": round(sum(costs) + sum(timeout_costs), 2),
        "sum_usd_timeouts": round(sum(timeout_costs), 2),
        "p50_turns": int(_pct(turns, 0.5)),
        "p50_cache_read_m": round(
            _pct([r["cache_read"] / 1e6 for r in ok if r["cache_read"]], 0.5), 1
        ),
        # How much of sum_usd is a floor rather than a bill.
        "estimated_runs": len([r for r in runs if r["cost_source"] == "estimated_from_stream"]),
        "unpriced_runs": len(
            [
                r
                for r in runs
                if r["cost_source"] in ("unavailable", "legacy_unknown") and r["exit_code"] != 0
            ]
        ),
    }


_HEADER = (
    f"{'slice':<22} {'n':>4} {'ok':>4} {'t/o':>4} {'fail':>4} {'t/o%':>5} | "
    f"{'p50m':>5} {'p90m':>5} {'t/o p50m':>8} | {'$p50':>6} {'$sum':>8} {'$t/o':>7} | "
    f"{'turns':>5} {'crM':>5} {'est':>4} {'unpr':>5}"
)


def _row(label: str, s: dict) -> str:
    return (
        f"{label:<22} {s['n']:4d} {s['ok']:4d} {s['timeout']:4d} {s['fail']:4d} "
        f"{s['timeout_rate'] * 100:4.0f}% | {s['p50_min']:5.0f} {s['p90_min']:5.0f} "
        f"{s['p50_timeout_min']:8.0f} | {s['p50_usd']:6.1f} {s['sum_usd']:8.0f} "
        f"{s['sum_usd_timeouts']:7.0f} | {s['p50_turns']:5d} {s['p50_cache_read_m']:5.1f} "
        f"{s['estimated_runs']:4d} {s['unpriced_runs']:5d}"
    )


def _by_week(day: str) -> str:
    import datetime

    d = datetime.date(int(day[:4]), int(day[4:6]), int(day[6:8]))
    monday = d - datetime.timedelta(days=d.weekday())
    return f"week of {monday.isoformat()}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    ap.add_argument("--skill", default="autopilot", help="autopilot | qa | reflect | all")
    ap.add_argument("--project", help="only this project id")
    ap.add_argument("--since", help="YYYY-MM-DD inclusive")
    ap.add_argument("--until", help="YYYY-MM-DD inclusive")
    ap.add_argument(
        "--split",
        metavar="DATE",
        help="one before/after pair around DATE — for an experiment verdict",
    )
    ap.add_argument(
        "--count-since",
        metavar="DATE",
        help="print how many runs finished since DATE, nothing else",
    )
    ap.add_argument("--by", choices=["week", "day", "project", "none"], default="week")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    skill = None if args.skill == "all" else args.skill
    log_dir = Path(args.log_dir)
    if not log_dir.is_dir():
        print(f"no log dir: {log_dir} (this machine may not run the orchestrator)", file=sys.stderr)
        return 0

    since = args.count_since or args.since
    runs = load_runs(log_dir, skill, since, args.until)
    if args.project:
        runs = [r for r in runs if r["project"] == args.project]

    if args.count_since:
        print(len(runs))
        return 0

    if args.split:
        cut = args.split.replace("-", "")
        before = [r for r in runs if r["day"] < cut]
        after = [r for r in runs if r["day"] >= cut]
        slices = [
            (f"before {args.split}", summarize(before)),
            (f"since {args.split}", summarize(after)),
        ]
    elif args.by == "none":
        slices = [("all", summarize(runs))]
    else:
        key = {
            "week": lambda r: _by_week(r["day"]),
            "day": lambda r: r["day"],
            "project": lambda r: r["project"],
        }[args.by]
        grouped = collections.defaultdict(list)
        for r in runs:
            grouped[key(r)].append(r)
        slices = [(k, summarize(v)) for k, v in sorted(grouped.items())]

    if args.json:
        print(json.dumps({"skill": args.skill, "slices": dict(slices)}, indent=2))
        return 0

    print(f"skill={args.skill}  runs={len(runs)}  logs={log_dir}")
    print(_HEADER)
    for label, s in slices:
        print(_row(label, s))
    print(
        "\nest = runs priced from streamed usage (a floor, not a bill); "
        "unpr = failed runs with no cost at all — before 2026-09-05 every timeout was one."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
