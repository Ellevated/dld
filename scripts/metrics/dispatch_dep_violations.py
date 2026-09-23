#!/usr/bin/env python3
"""Dispatches that started before a declared dependency was done — the EXP-012 metric.

For every spec of every orchestrated project, each `→ in_progress` transition written
by the orchestrator (the built-in path and `dispatch_one` both sign as `orchestrator`;
a spec an operator takes over by hand runs in an order chosen on purpose, and is not
counted) on or
after `--since` is checked against the spec's declared edges (`spec_deps.declared`:
lifecycle `depends_on` ∪ spec-header `AFTER` ∪ backlog `AFTER`). A dependency is late
when its first `→ done` transition comes after the dispatch, or it has none. Edges to
ids absent from the repo's lifecycle (cross-repo, typos) are skipped: nothing here can
tell when they were done.

Edges are read as declared TODAY, so a dependency added to a header after its spec ran
counts against that run — the error is small and the same on both sides of the split.

Usage:
    dispatch_dep_violations.py                     # since the LLM dispatcher (2026-09-07)
    dispatch_dep_violations.py --since 2026-09-23  # after EXP-012

Exit codes: 0 always (a reporting tool, never a gate).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vps"))
import db  # noqa: E402
import lifecycle  # noqa: E402
import spec_deps  # noqa: E402

ALL_STATUSES = {"queued", "in_progress", "blocked", "done", "resumed", "draft", "stale"}


def _ts(value) -> str:
    return str(value or "").replace(" ", "T")


def _done_at(row: dict) -> str | None:
    """When the spec first became done; "" = done before any transition was recorded."""
    for t in row.get("transitions") or []:
        if t.get("to") == "done":
            return _ts(t.get("at"))
    return "" if row.get("status") == "done" else None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default="2026-09-07")
    args = ap.parse_args(argv[1:])
    dispatches = late_runs = 0
    for project in db.get_all_projects():
        pdir = project["path"]
        if not Path(pdir, "ai", "lifecycle").is_dir():
            continue
        for row in lifecycle.list_by_status(pdir, ALL_STATUSES):
            trs = row.get("transitions") or []
            starts = [
                i
                for i, t in enumerate(trs)
                if t.get("to") == "in_progress"
                and t.get("by") == "orchestrator"
                and _ts(t.get("at")) >= args.since
            ]
            if not starts:
                continue
            deps = spec_deps.declared(pdir, row["spec_id"])
            for i in starts:
                dispatches += 1
                at = _ts(trs[i].get("at"))
                late = []
                for dep in sorted(deps):
                    drow = lifecycle.read_lifecycle(pdir, dep)
                    if drow is None:
                        continue
                    done = _done_at(drow)
                    if done is None or done > at:
                        late.append(f"{dep} (done {done[:16] if done else 'never'})")
                if late:
                    late_runs += 1
                    outcome = trs[i + 1].get("to") if i + 1 < len(trs) else row.get("status")
                    print(
                        f"{project['project_id']}:{row['spec_id']} dispatched {at[:16]} "
                        f"before {', '.join(late)} → {outcome}"
                    )
    print(
        f"dispatches since {args.since}: {dispatches}; "
        f"before a declared dependency was done: {late_runs}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
