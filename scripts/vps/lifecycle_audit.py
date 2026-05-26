#!/usr/bin/env python3
"""
Module: lifecycle_audit
Role: READ-ONLY multi-project drift detector. Catches divergence between
      the 5 surfaces that should stay in sync: lifecycle yaml, spec.md,
      backlog.md row, working tree state, and counter files.
Uses: lifecycle (list, read), orchestrator (_parse_backlog), git CLI (ls-tree)
Used by: operator (manual CLI), CI smoke (future).

USAGE
-----
    python3 scripts/vps/lifecycle_audit.py             # all projects, text table
    python3 scripts/vps/lifecycle_audit.py --project=awardybot
    python3 scripts/vps/lifecycle_audit.py --json
    python3 scripts/vps/lifecycle_audit.py --category=bootstrap_as_done
    python3 scripts/vps/lifecycle_audit.py --quiet      # only counts (CI mode)

SAFETY
------
Strictly READ-ONLY. No git writes, no lifecycle mutations, no commits.
Reads from HEAD (yamls), filesystem (counters/WT), and `git status` (drift).

Categories (14):
  orphan_spec_md         — ai/features/{spec}.md exists, yaml absent in HEAD
  orphan_yaml            — yaml in HEAD, no ai/features/ md anywhere
  missing_from_backlog   — yaml exists, no backlog.md row for spec_id
  bootstrap_as_done      — yaml=done with empty signature (TECH-195)
  markdown_status_mismatch — md `**Status:**` != yaml status
  backlog_status_mismatch — backlog row status != yaml status
  backlog_format_unparsed — backlog row matched spec_id but no status extracted
  wt_lifecycle_dirty     — uncommitted in ai/lifecycle/
  wt_features_dirty      — uncommitted in ai/features/
  unauthorized_writer    — transitions contain by=spark|autopilot (ADR-025)
  git_divergence         — develop ahead/behind origin/develop (not just clean)
  push_failures_counter  — ai/.lifecycle-push-failures > 0
  bootstrap_anomaly      — ai/.bootstrap-anomaly-count > 0
  bootstrap_unparsable   — ai/.bootstrap-unparsable-count > 0 (TECH-195 Task 1)

Exit code: 0 if clean, 1 if any findings.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import lifecycle  # noqa: E402

log = logging.getLogger("lifecycle_audit")

CATEGORIES = (
    "orphan_spec_md",
    "orphan_yaml",
    "missing_from_backlog",
    "bootstrap_as_done",
    "markdown_status_mismatch",
    "backlog_status_mismatch",
    "backlog_format_unparsed",
    "wt_lifecycle_dirty",
    "wt_features_dirty",
    "unauthorized_writer",
    "git_divergence",
    "push_failures_counter",
    "bootstrap_anomaly",
    "bootstrap_unparsable",
)

# ──────────────────────────────────────────────────────────────────────
# Git helpers (read-only)
# ──────────────────────────────────────────────────────────────────────


def _git(repo: str, *args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _ls_tree(repo: str, path: str) -> list[str]:
    """Return filenames under `HEAD:<path>` (or [] if path missing in HEAD)."""
    r = _git(repo, "ls-tree", "--name-only", f"HEAD:{path}")
    if r.returncode != 0:
        return []
    return [n for n in r.stdout.splitlines() if n]


def _git_dirty(repo: str, path: str) -> list[str]:
    """Return porcelain lines for <path> (empty if clean)."""
    r = _git(repo, "status", "--porcelain", path)
    if r.returncode != 0:
        return []
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def _git_divergence(repo: str) -> tuple[int, int]:
    """Return (ahead, behind) counts vs origin/develop. (-1, -1) on error."""
    r = _git(repo, "rev-list", "--left-right", "--count", "HEAD...origin/develop")
    if r.returncode != 0:
        return (-1, -1)
    parts = r.stdout.strip().split()
    if len(parts) != 2:
        return (-1, -1)
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return (-1, -1)


# ──────────────────────────────────────────────────────────────────────
# Markdown / backlog parsing (read-only)
# ──────────────────────────────────────────────────────────────────────


_SPEC_ID_RE = re.compile(r"^(BUG|FTR|TECH|ARCH|GROWTH)-\d+$")
_MD_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*([a-z_]+)\s*$", re.MULTILINE)


def _spec_id_from_filename(name: str) -> str | None:
    """ai/features/TECH-195-2026-05-26-foo.md → TECH-195."""
    m = re.match(r"^((?:BUG|FTR|TECH|ARCH|GROWTH)-\d+)", name)
    return m.group(1) if m else None


def _list_feature_specs(repo: str) -> dict[str, str]:
    """Map spec_id → filename for ai/features/*.md (filesystem, not HEAD)."""
    out: dict[str, str] = {}
    features_dir = Path(repo) / "ai" / "features"
    if not features_dir.is_dir():
        return out
    for p in features_dir.glob("*.md"):
        sid = _spec_id_from_filename(p.name)
        if sid and sid not in out:
            out[sid] = p.name
    return out


def _md_status(repo: str, filename: str) -> str | None:
    """Extract `**Status:** xxx` line from spec md. None if missing/unreadable."""
    p = Path(repo) / "ai" / "features" / filename
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _MD_STATUS_RE.search(text)
    return m.group(1) if m else None


def _parse_backlog_columns(text: str) -> dict[str, str | None]:
    """READ-ONLY port of orchestrator._parse_backlog.

    Kept in-module to avoid import cycle and keep audit fully READ-ONLY.
    Maps spec_id → status (or None if row exists but status unparseable).
    """
    valid_statuses = {"queued", "in_progress", "blocked", "resumed", "done", "draft"}
    out: dict[str, str | None] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines):
            divider = lines[i + 1].strip()
            if re.match(r"^\|?\s*:?-{2,}.*\|", divider):
                headers = [c.strip() for c in line.strip().strip("|").split("|")]
                col_map = {h.lower(): idx for idx, h in enumerate(headers)}
                status_col = col_map.get("status")
                i += 2
                while i < len(lines):
                    row = lines[i]
                    if not row.lstrip().startswith("|"):
                        break
                    cells = [c.strip() for c in row.strip().strip("|").split("|")]
                    sid = None
                    for cell in cells[:3]:
                        cell_clean = cell.strip("`*[] ")
                        if _SPEC_ID_RE.match(cell_clean):
                            sid = cell_clean
                            break
                    if sid:
                        status_val: str | None = None
                        if status_col is not None and status_col < len(cells):
                            cand = cells[status_col].strip("`*[] ").lower()
                            if cand in valid_statuses:
                                status_val = cand
                        if status_val is None:
                            for cell in cells:
                                cand = cell.strip("`*[] ").lower()
                                if cand in valid_statuses:
                                    status_val = cand
                                    break
                        out[sid] = status_val
                    i += 1
                continue
        i += 1
    return out


# ──────────────────────────────────────────────────────────────────────
# Per-project audit
# ──────────────────────────────────────────────────────────────────────


def _read_counter(repo: str, name: str) -> int:
    p = Path(repo) / "ai" / name
    if not p.is_file():
        return 0
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return 0


def _is_bootstrap_as_done(data: dict) -> bool:
    return (
        data.get("status") == "done"
        and not data.get("transitions")
        and data.get("pueue_id") is None
        and data.get("finished_at") is None
    )


def _yaml_writers(data: dict) -> set[str]:
    """All `by` values seen in transitions + updated_by field."""
    s = {t.get("by") for t in (data.get("transitions") or []) if t.get("by")}
    if data.get("updated_by"):
        s.add(data["updated_by"])
    return s


def audit_project(repo: str) -> list[dict]:
    """Run all 14 detectors against a single project. Returns list of findings."""
    findings: list[dict] = []
    if not Path(repo).is_dir():
        return findings

    # ── 1. Inventory: yaml from HEAD, md from filesystem, backlog parse
    yaml_names = _ls_tree(repo, lifecycle.LIFECYCLE_DIR)
    yaml_ids = {n[:-5] for n in yaml_names if n.endswith(".yaml")}
    md_map = _list_feature_specs(repo)
    md_ids = set(md_map.keys())
    backlog_path = Path(repo) / "ai" / "backlog.md"
    backlog_text = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    backlog_map = _parse_backlog_columns(backlog_text)
    backlog_ids = set(backlog_map.keys())

    # Pre-load all yamls (single pass)
    yaml_data: dict[str, dict] = {}
    for sid in yaml_ids:
        d = lifecycle.read_lifecycle(repo, sid)
        if d:
            yaml_data[sid] = d

    # ── 2. orphan_spec_md: md exists but yaml absent in HEAD
    for sid in sorted(md_ids - yaml_ids):
        findings.append(
            {"category": "orphan_spec_md", "spec_id": sid, "detail": md_map[sid]}
        )

    # ── 3. orphan_yaml: yaml present, no md
    for sid in sorted(yaml_ids - md_ids):
        findings.append({"category": "orphan_yaml", "spec_id": sid, "detail": "no md"})

    # ── 4. missing_from_backlog: yaml exists, backlog has no row
    for sid in sorted(yaml_ids - backlog_ids):
        findings.append(
            {"category": "missing_from_backlog", "spec_id": sid, "detail": "no row"}
        )

    # ── 5. bootstrap_as_done: TECH-195 signature
    for sid in sorted(yaml_ids):
        if _is_bootstrap_as_done(yaml_data.get(sid, {})):
            findings.append(
                {
                    "category": "bootstrap_as_done",
                    "spec_id": sid,
                    "detail": "status=done, no transitions, no pueue_id, no finished_at",
                }
            )

    # ── 6. markdown_status_mismatch
    for sid in sorted(yaml_ids & md_ids):
        md_st = _md_status(repo, md_map[sid])
        ya_st = yaml_data.get(sid, {}).get("status")
        if md_st and md_st != ya_st:
            findings.append(
                {
                    "category": "markdown_status_mismatch",
                    "spec_id": sid,
                    "detail": f"md={md_st} yaml={ya_st}",
                }
            )

    # ── 7. backlog_status_mismatch (only when backlog has a status)
    for sid in sorted(yaml_ids & backlog_ids):
        b_st = backlog_map.get(sid)
        ya_st = yaml_data.get(sid, {}).get("status")
        if b_st is not None and b_st != ya_st:
            findings.append(
                {
                    "category": "backlog_status_mismatch",
                    "spec_id": sid,
                    "detail": f"backlog={b_st} yaml={ya_st}",
                }
            )

    # ── 8. backlog_format_unparsed: row matched spec_id but status is None
    for sid in sorted(backlog_ids):
        if backlog_map.get(sid) is None:
            findings.append(
                {
                    "category": "backlog_format_unparsed",
                    "spec_id": sid,
                    "detail": "row found but status not extracted",
                }
            )

    # ── 9. wt_lifecycle_dirty
    for line in _git_dirty(repo, lifecycle.LIFECYCLE_DIR):
        findings.append(
            {"category": "wt_lifecycle_dirty", "spec_id": "-", "detail": line}
        )

    # ── 10. wt_features_dirty
    for line in _git_dirty(repo, "ai/features"):
        findings.append(
            {"category": "wt_features_dirty", "spec_id": "-", "detail": line}
        )

    # ── 11. unauthorized_writer (ADR-025: spark, autopilot not in writers)
    for sid in sorted(yaml_ids):
        bad = _yaml_writers(yaml_data.get(sid, {})) & {"spark", "autopilot"}
        if bad:
            findings.append(
                {
                    "category": "unauthorized_writer",
                    "spec_id": sid,
                    "detail": f"by={sorted(bad)}",
                }
            )

    # ── 12. git_divergence
    ahead, behind = _git_divergence(repo)
    if (ahead, behind) != (-1, -1) and (ahead > 0 or behind > 0):
        findings.append(
            {
                "category": "git_divergence",
                "spec_id": "-",
                "detail": f"ahead={ahead} behind={behind}",
            }
        )

    # ── 13. push_failures_counter
    n = _read_counter(repo, ".lifecycle-push-failures")
    if n > 0:
        findings.append(
            {"category": "push_failures_counter", "spec_id": "-", "detail": f"count={n}"}
        )

    # ── 14. bootstrap_anomaly
    n = _read_counter(repo, ".bootstrap-anomaly-count")
    if n > 0:
        findings.append(
            {"category": "bootstrap_anomaly", "spec_id": "-", "detail": f"count={n}"}
        )

    # ── 15. bootstrap_unparsable (TECH-195 Task 1)
    n = _read_counter(repo, ".bootstrap-unparsable-count")
    if n > 0:
        findings.append(
            {"category": "bootstrap_unparsable", "spec_id": "-", "detail": f"count={n}"}
        )

    return findings


# ──────────────────────────────────────────────────────────────────────
# Project iteration / CLI
# ──────────────────────────────────────────────────────────────────────


def _load_projects(projects_json_path: str | None) -> list[dict]:
    path = projects_json_path or os.environ.get("PROJECTS_JSON")
    if not path:
        path = str(SCRIPT_DIR / "projects.json")
    if not Path(path).is_file():
        log.warning("projects.json not found: %s", path)
        return []
    with open(path) as f:
        return json.load(f)


def run(
    project_filter: str | None,
    projects_json: str | None,
    json_output: bool,
    category_filter: str | None,
    quiet: bool,
) -> int:
    if category_filter and category_filter not in CATEGORIES:
        print(
            f"audit: unknown --category={category_filter!r}; valid: {sorted(CATEGORIES)}",
            file=sys.stderr,
        )
        return 2

    projects = _load_projects(projects_json)
    if project_filter:
        projects = [p for p in projects if p.get("project_id") == project_filter]
        if not projects:
            print(f"audit: project_id={project_filter!r} not found", file=sys.stderr)
            return 2

    overall_findings: list[dict] = []
    per_project: list[dict] = []

    for proj in projects:
        project_id = proj.get("project_id", "?")
        repo = proj.get("path")
        if not repo:
            continue
        findings = audit_project(repo)
        if category_filter:
            findings = [f for f in findings if f["category"] == category_filter]
        for f in findings:
            f["project_id"] = project_id
        overall_findings.extend(findings)
        per_project.append(
            {
                "project_id": project_id,
                "path": repo,
                "count": len(findings),
                "findings": findings,
            }
        )

    if json_output:
        print(
            json.dumps(
                {"total": len(overall_findings), "projects": per_project},
                indent=2,
                sort_keys=True,
            )
        )
    elif quiet:
        for p in per_project:
            print(f"{p['project_id']}: {p['count']}")
        print(f"TOTAL: {len(overall_findings)}")
    else:
        _print_text(per_project, overall_findings, category_filter)

    return 1 if overall_findings else 0


def _print_text(per_project: list[dict], overall: list[dict], category_filter: str | None) -> None:
    title = "=== lifecycle_audit ===" + (
        f" [category={category_filter}]" if category_filter else ""
    )
    print(title)
    print()
    for p in per_project:
        if not p["findings"]:
            print(f"  {p['project_id']}: clean")
            continue
        print(f"  {p['project_id']} ({p['count']} finding{'s' if p['count'] != 1 else ''}):")
        # group by category
        by_cat: dict[str, list[dict]] = {}
        for f in p["findings"]:
            by_cat.setdefault(f["category"], []).append(f)
        for cat in CATEGORIES:
            rows = by_cat.get(cat, [])
            if not rows:
                continue
            print(f"    [{cat}] x{len(rows)}")
            for f in rows[:10]:  # cap per-category output
                print(f"      - {f['spec_id']}: {f['detail']}")
            if len(rows) > 10:
                print(f"      ... +{len(rows) - 10} more")
        print()
    print(f"Total findings: {len(overall)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lifecycle_audit",
        description="READ-ONLY multi-project lifecycle drift detector (TECH-195).",
    )
    parser.add_argument(
        "--project", dest="project_filter", help="Only audit this project_id."
    )
    parser.add_argument(
        "--projects-json",
        help="Path to projects.json (default: $PROJECTS_JSON or scripts/vps/projects.json).",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--category", dest="category_filter", help=f"Filter to one category: {sorted(CATEGORIES)}"
    )
    parser.add_argument("--quiet", action="store_true", help="Only print counts.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    return run(
        project_filter=args.project_filter,
        projects_json=args.projects_json,
        json_output=args.json_output,
        category_filter=args.category_filter,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
