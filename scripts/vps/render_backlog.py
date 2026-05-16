"""
Module: render_backlog
Role: Pure function that renders ai/backlog.md from ai/lifecycle/*.yaml files.
      Produces a read-only markdown view grouped by priority then kind.
      Never raises on bad data — logs warnings and skips malformed entries.

Uses:
  - pathlib: Path, glob
  - yaml: safe_load
  - datetime: now, timezone
  - logging: getLogger
  - lifecycle: LIFECYCLE_DIR constant; read via HEAD git object store (fallback to WT)

Used by:
  - lifecycle.py: _atomic_write() hook (TASK 4 stub — wired in Task 5)
  - migrate_backlog_to_lifecycle.py: render after migration
  - callback.py: optional post-write render

Glossary: ai/glossary/orchestrator.md
"""

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from lifecycle import LIFECYCLE_DIR

log = logging.getLogger(__name__)

FEATURES_DIR = "ai/features"

# Priority order: p0 first, then p1, then p2, then unknown
PRIORITY_ORDER = ["p0", "p1", "p2"]
PRIORITY_LABELS = {
    "p0": "P0 — Blocks revenue, users, or security",
    "p1": "P1 — High impact (default)",
    "p2": "P2 — Nice-to-have",
}

# Kind sort order within priority group
KIND_ORDER = ["tech", "ftr", "bug", "arch"]

HEADER = """\
# DLD Backlog

<!-- AUTO-GENERATED from ai/lifecycle/*.yaml — do not edit manually.
     callback.py + lifecycle.py write per-spec YAML; render_backlog
     produces this view on every lifecycle write (ARCH-186 / ADR-023). -->
"""

TABLE_HEADER = "| ID | Status | Kind | Updated | Spec |\n|----|--------|------|---------|------|\n"
DONE_TABLE_HEADER = "| ID | Status | Kind | Finished | Spec |\n|----|--------|------|----------|------|\n"


def _load_all_yamls(repo_dir: Path) -> list[dict]:
    """Load all lifecycle YAMLs from HEAD or working tree.

    Returns list of parsed dicts. Skips malformed entries with a warning.
    """
    results = []
    repo_str = str(repo_dir)

    # Try HEAD first via git ls-tree
    r = subprocess.run(
        ["git", "ls-tree", "--name-only", f"HEAD:{LIFECYCLE_DIR}"],
        cwd=repo_str, capture_output=True, text=True, check=False,
    )
    if r.returncode == 0:
        names = sorted(n for n in r.stdout.splitlines() if n.endswith(".yaml"))
        for name in names:
            spec_id = name[:-5]
            show = subprocess.run(
                ["git", "show", f"HEAD:{LIFECYCLE_DIR}/{name}"],
                cwd=repo_str, capture_output=True, text=True, check=False,
            )
            if show.returncode != 0:
                log.warning("render_backlog: cannot read %s from HEAD", name)
                continue
            try:
                data = yaml.safe_load(show.stdout)
                if not isinstance(data, dict):
                    raise ValueError("not a mapping")
                results.append(data)
            except Exception as exc:
                log.warning("render_backlog: skipping malformed %s: %s", name, exc)
        return results

    # Fallback: working tree glob
    pattern = repo_dir / LIFECYCLE_DIR / "*.yaml"
    for yaml_path in sorted(pattern.parent.glob("*.yaml")):
        try:
            raw = yaml_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            if not isinstance(data, dict):
                raise ValueError("not a mapping")
            results.append(data)
        except Exception as exc:
            log.warning("render_backlog: skipping malformed %s: %s", yaml_path.name, exc)
    return results


def _find_spec_link(repo_dir: Path, spec_id: str) -> str:
    """Return markdown link to spec file, or plain spec_id if not found."""
    features = repo_dir / FEATURES_DIR
    if features.is_dir():
        matches = sorted(features.glob(f"{spec_id}*.md"))
        if matches:
            rel = matches[0].relative_to(repo_dir / "ai")
            return f"[spec]({rel})"
    return spec_id


def _truncate_date(iso: Optional[str]) -> str:
    """Truncate ISO datetime to YYYY-MM-DD. Returns '' on None/invalid."""
    if not iso:
        return ""
    return str(iso)[:10]


def _render_table_row(data: dict, repo_dir: Path, date_field: str) -> str:
    spec_id = data.get("spec_id", "?")
    status = data.get("status", "?")
    kind = data.get("kind", "?")
    date_val = _truncate_date(data.get(date_field))
    spec_link = _find_spec_link(repo_dir, spec_id)
    return f"| {spec_id} | {status} | {kind} | {date_val} | {spec_link} |\n"


def _sort_key(data: dict) -> tuple:
    kind = data.get("kind", "z")
    kind_idx = KIND_ORDER.index(kind) if kind in KIND_ORDER else len(KIND_ORDER)
    return (kind_idx, data.get("spec_id", ""))


def render_backlog(repo_dir) -> str:
    """Render ai/backlog.md content from ai/lifecycle/*.yaml.

    Groups specs by priority (p0 -> p1 -> p2) then by kind (tech, ftr, bug, arch).
    Returns markdown string with a clear "auto-generated, do not edit" header.

    Skips malformed yamls with a logged warning — never raises on bad data.

    Args:
        repo_dir: Path or str to the git repository root.

    Returns:
        Markdown string ready to be written to ai/backlog.md.
    """
    repo_dir = Path(repo_dir)
    all_data = _load_all_yamls(repo_dir)

    now = datetime.now(tz=timezone.utc)
    cutoff_days = 30

    # Separate done from active
    active: list[dict] = []
    done_recent: list[dict] = []
    done_older_count = 0

    for data in all_data:
        status = data.get("status", "")
        if status == "done":
            finished_raw = data.get("finished_at") or data.get("updated_at", "")
            finished_str = _truncate_date(finished_raw)
            try:
                finished_dt = datetime.fromisoformat(finished_str)
                age_days = (now.date() - finished_dt.date()).days
            except (ValueError, TypeError):
                age_days = 999
            if age_days <= cutoff_days:
                done_recent.append(data)
            else:
                done_older_count += 1
        else:
            active.append(data)

    # Build output
    lines = [HEADER]

    # Active specs grouped by priority
    for prio in PRIORITY_ORDER:
        label = PRIORITY_LABELS[prio]
        lines.append(f"## {label}\n\n")
        group = sorted(
            [d for d in active if d.get("priority", "p1") == prio],
            key=_sort_key,
        )
        if group:
            lines.append(TABLE_HEADER)
            for data in group:
                lines.append(_render_table_row(data, repo_dir, "updated_at"))
        else:
            lines.append("_no specs_\n")
        lines.append("\n")

    # Done section
    lines.append("## Done (last 30 days)\n\n")
    done_recent_sorted = sorted(done_recent, key=_sort_key)
    if done_recent_sorted:
        lines.append(DONE_TABLE_HEADER)
        for data in done_recent_sorted:
            lines.append(_render_table_row(data, repo_dir, "finished_at"))
    else:
        lines.append("_no specs_\n")
    if done_older_count > 0:
        lines.append(f"\n| Older than 30 days: {done_older_count} specs |\n")
    lines.append("\n")

    return "".join(lines)
