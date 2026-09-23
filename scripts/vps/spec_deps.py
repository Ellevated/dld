#!/usr/bin/env python3
"""
Module: spec_deps
Role: one answer to "which specs does this spec wait for?" — shared by the
      built-in dispatch gate (orchestrator_queue) and the LLM dispatcher's
      briefing (dispatch_summary), so the two cannot disagree again.

An edge is declared in any of three places, and the fleet uses all three:
  * `depends_on` in the lifecycle yaml — the SoT since TECH-222, written by
    Spark's `create_initial` claim;
  * `**AFTER <ID>**` in the first 15 lines of the spec body — what Spark writes,
    and where it reads `depends_on` from (skills/spark/completion.md step 2,
    same regex, same window);
  * `AFTER <ID>` in the backlog row — the deprecated BUG-206 marker.

Measured 2026-09-23 over 1758 lifecycle entries on the VPS: 44 carry
`depends_on`, 58 a backlog AFTER, 85 a header AFTER — and 25 declare a header
edge neither of the other two holds, nine of them queued in dowry at that
moment (BUG-521 → BUG-522 → BUG-523 → BUG-524 looked like four ready specs).
The briefing read `depends_on` alone, the gate `depends_on` ∪ backlog. It had
already cost a run: awardybot FTR-1531 was dispatched on 2026-09-11 before
FTR-1530 merged and died two minutes in without code.

Only the edges live here, never STATUS: whether a dependency counts as met is
the caller's policy — fail-open on an unknown id in the gate, reported as
`missing` in the briefing.

Uses: itertools, logging, re, pathlib, lifecycle
Used by: orchestrator_queue (re-exported under the TECH-222 names),
         dispatch_summary
"""

import itertools
import logging
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import lifecycle  # noqa: E402

log = logging.getLogger("orchestrator")

# Backlog prose: "after FTR-1530", "⛔ AFTER TECH-1244" — any case.
AFTER_ROW_RE = re.compile(r"\bafter\s+([A-Z]{2,5}-\d+)", re.IGNORECASE)
# Spec header: Spark's own grep, uppercase only. A lowercase "after" in the first
# lines is prose ("Status update — after BUG-355 shipped"), not a declaration.
AFTER_HEADER_RE = re.compile(r"\bAFTER +([A-Z]{2,5}-\d+)")
HEADER_LINES = 15


def backlog_deps(project_dir: str, spec_id: str) -> set:
    """Deprecated 'AFTER <ID>' deps from spec_id's backlog row; empty when absent."""
    backlog = Path(project_dir) / "ai" / "backlog.md"
    if not backlog.is_file():
        return set()
    row_re = re.compile(rf"^\s*\|\s*{re.escape(spec_id)}\s*\|")
    try:
        for line in backlog.read_text(errors="replace").splitlines():
            if row_re.match(line):
                deps = {m.group(1).upper() for m in AFTER_ROW_RE.finditer(line)}
                deps.discard(spec_id)
                return deps
    except OSError:
        pass
    return set()


def header_deps(project_dir: str, spec_id: str) -> set:
    """`AFTER <ID>` in the first HEADER_LINES lines of the spec body; empty when absent."""
    features = Path(project_dir) / "ai" / "features"
    deps: set = set()
    for body in features.glob(f"{spec_id}*.md"):
        # FTR-43* also matches FTR-435-….md — only "<ID>-…" and "<ID>.md" are this spec.
        if body.name[len(spec_id)] not in "-.":
            continue
        try:
            with body.open(encoding="utf-8", errors="replace") as fh:
                head = list(itertools.islice(fh, HEADER_LINES))
        except OSError:
            continue
        deps |= {m.group(1) for line in head for m in AFTER_HEADER_RE.finditer(line)}
    deps.discard(spec_id)
    return deps


def declared(project_dir: str, spec_id: str) -> set:
    """Every declared dep: lifecycle `depends_on` ∪ spec header ∪ backlog row.

    An edge found outside `depends_on` is logged as DEP_VIA with its source —
    the count that says whether Spark copies the header into the yaml.
    """
    raw = (lifecycle.read_lifecycle(project_dir, spec_id) or {}).get("depends_on") or []
    if not isinstance(raw, list):
        log.warning("DEP_SHAPE: %s depends_on is not a list — ignored", spec_id)
        raw = []
    yaml_deps = {d.upper() for d in raw if isinstance(d, str)}
    header = header_deps(project_dir, spec_id) - yaml_deps
    legacy = backlog_deps(project_dir, spec_id) - yaml_deps - header
    if header:
        log.info("DEP_VIA: %s deps_via=header %s", spec_id, sorted(header))
    if legacy:
        log.info("DEP_VIA: %s deps_via=backlog (legacy) %s", spec_id, sorted(legacy))
    return yaml_deps | header | legacy
