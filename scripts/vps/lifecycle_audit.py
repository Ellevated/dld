#!/usr/bin/env python3
"""
Module: lifecycle_audit
Role: READ-ONLY multi-project drift detector. Catches divergence between
      the 5 surfaces that should stay in sync: lifecycle yaml, spec.md,
      backlog.md row, working tree state, and counter files.
Uses: lifecycle (list, read), audit_probe (git/fs probes, backlog parsing),
      audit_categories (14 detector functions) — TECH-211 split
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
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_categories  # noqa: E402
import audit_probe  # noqa: E402
import console_safe  # noqa: E402
import lifecycle  # noqa: E402

log = logging.getLogger("lifecycle_audit")

# Assignment aliases (NOT from-imports — see TECH-211 DA-4): preserved for
# test_orchestrator_bootstrap.py:513-519, which imports these two names
# directly from this module.
CATEGORIES = audit_categories.CATEGORIES
_parse_backlog_columns = audit_probe._parse_backlog_columns


# ──────────────────────────────────────────────────────────────────────
# Per-project audit
# ──────────────────────────────────────────────────────────────────────


def audit_project(repo: str) -> list[dict]:
    """Run all 14 detectors against a single project. Returns list of findings."""
    findings: list[dict] = []
    if not Path(repo).is_dir():
        return findings

    # ── Inventory: yaml from HEAD, md from filesystem, backlog parse
    yaml_names = audit_probe._ls_tree(repo, lifecycle.LIFECYCLE_DIR)
    yaml_ids = {n[:-5] for n in yaml_names if n.endswith(".yaml")}
    md_map = audit_probe._list_feature_specs(repo)
    md_ids = set(md_map.keys())
    backlog_path = Path(repo) / "ai" / "backlog.md"
    backlog_text = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    backlog_map = audit_probe._parse_backlog_columns(backlog_text)
    backlog_ids = set(backlog_map.keys())

    # Pre-load all yamls (single pass)
    yaml_data: dict[str, dict] = {}
    for sid in yaml_ids:
        d = lifecycle.read_lifecycle(repo, sid)
        if d:
            yaml_data[sid] = d

    findings.extend(audit_categories.orphan_spec_md(md_ids, yaml_ids, md_map))
    findings.extend(audit_categories.orphan_yaml(yaml_ids, md_ids))
    findings.extend(audit_categories.missing_from_backlog(yaml_ids, backlog_ids))
    findings.extend(audit_categories.bootstrap_as_done(yaml_ids, yaml_data))
    findings.extend(
        audit_categories.markdown_status_mismatch(repo, yaml_ids, md_ids, md_map, yaml_data)
    )
    findings.extend(
        audit_categories.backlog_status_mismatch(yaml_ids, backlog_ids, backlog_map, yaml_data)
    )
    findings.extend(audit_categories.backlog_format_unparsed(backlog_ids, backlog_map))
    findings.extend(audit_categories.wt_lifecycle_dirty(repo))
    findings.extend(audit_categories.wt_features_dirty(repo))
    findings.extend(audit_categories.unauthorized_writer(yaml_ids, yaml_data))
    findings.extend(audit_categories.git_divergence(repo))
    findings.extend(audit_categories.push_failures_counter(repo))
    findings.extend(audit_categories.bootstrap_anomaly(repo))
    findings.extend(audit_categories.bootstrap_unparsable(repo))

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
    console_safe.enable()
    parser = argparse.ArgumentParser(
        prog="lifecycle_audit",
        description="READ-ONLY multi-project lifecycle drift detector (TECH-195).",
    )
    parser.add_argument("--project", dest="project_filter", help="Only audit this project_id.")
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
