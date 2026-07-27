#!/usr/bin/env python3
"""
Module: audit_categories
Role: The 14 drift detector categories for lifecycle_audit, one function per
      category. Extracted from lifecycle_audit.audit_project (TECH-211) —
      each function returns the same findings, in the same order, that the
      original monolithic loop produced for that category.
Uses: audit_probe (git/fs probes), lifecycle (LIFECYCLE_DIR constant), pathlib
Used by: lifecycle_audit.py (audit_project thin orchestration)
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_probe  # noqa: E402
import lifecycle  # noqa: E402

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


def orphan_spec_md(md_ids: set, yaml_ids: set, md_map: dict) -> list[dict]:
    """md exists but yaml absent in HEAD."""
    return [
        {"category": "orphan_spec_md", "spec_id": sid, "detail": md_map[sid]}
        for sid in sorted(md_ids - yaml_ids)
    ]


def orphan_yaml(yaml_ids: set, md_ids: set) -> list[dict]:
    """yaml present, no md."""
    return [
        {"category": "orphan_yaml", "spec_id": sid, "detail": "no md"}
        for sid in sorted(yaml_ids - md_ids)
    ]


def missing_from_backlog(yaml_ids: set, backlog_ids: set) -> list[dict]:
    """yaml exists, backlog has no row."""
    return [
        {"category": "missing_from_backlog", "spec_id": sid, "detail": "no row"}
        for sid in sorted(yaml_ids - backlog_ids)
    ]


def bootstrap_as_done(yaml_ids: set, yaml_data: dict) -> list[dict]:
    """TECH-195 signature."""
    findings = []
    for sid in sorted(yaml_ids):
        if audit_probe._is_bootstrap_as_done(yaml_data.get(sid, {})):
            findings.append(
                {
                    "category": "bootstrap_as_done",
                    "spec_id": sid,
                    "detail": "status=done, no transitions, no pueue_id, no finished_at",
                }
            )
    return findings


def markdown_status_mismatch(
    repo: str, yaml_ids: set, md_ids: set, md_map: dict, yaml_data: dict
) -> list[dict]:
    findings = []
    for sid in sorted(yaml_ids & md_ids):
        md_st = audit_probe._md_status(repo, md_map[sid])
        ya_st = yaml_data.get(sid, {}).get("status")
        if md_st and md_st != ya_st:
            findings.append(
                {
                    "category": "markdown_status_mismatch",
                    "spec_id": sid,
                    "detail": f"md={md_st} yaml={ya_st}",
                }
            )
    return findings


def backlog_status_mismatch(
    yaml_ids: set, backlog_ids: set, backlog_map: dict, yaml_data: dict
) -> list[dict]:
    """Only when backlog has a status."""
    findings = []
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
    return findings


def backlog_format_unparsed(backlog_ids: set, backlog_map: dict) -> list[dict]:
    """Row matched spec_id but status is None."""
    findings = []
    for sid in sorted(backlog_ids):
        if backlog_map.get(sid) is None:
            findings.append(
                {
                    "category": "backlog_format_unparsed",
                    "spec_id": sid,
                    "detail": "row found but status not extracted",
                }
            )
    return findings


def wt_lifecycle_dirty(repo: str) -> list[dict]:
    return [
        {"category": "wt_lifecycle_dirty", "spec_id": "-", "detail": line}
        for line in audit_probe._git_dirty(repo, lifecycle.LIFECYCLE_DIR)
    ]


def wt_features_dirty(repo: str) -> list[dict]:
    return [
        {"category": "wt_features_dirty", "spec_id": "-", "detail": line}
        for line in audit_probe._git_dirty(repo, "ai/features")
    ]


def unauthorized_writer(yaml_ids: set, yaml_data: dict) -> list[dict]:
    """ADR-025: spark, autopilot not in writers."""
    findings = []
    for sid in sorted(yaml_ids):
        bad = audit_probe._yaml_writers(yaml_data.get(sid, {})) & {"spark", "autopilot"}
        if bad:
            findings.append(
                {
                    "category": "unauthorized_writer",
                    "spec_id": sid,
                    "detail": f"by={sorted(bad)}",
                }
            )
    return findings


def git_divergence(repo: str) -> list[dict]:
    ahead, behind = audit_probe._git_divergence(repo)
    if (ahead, behind) != (-1, -1) and (ahead > 0 or behind > 0):
        return [
            {
                "category": "git_divergence",
                "spec_id": "-",
                "detail": f"ahead={ahead} behind={behind}",
            }
        ]
    return []


def push_failures_counter(repo: str) -> list[dict]:
    n = audit_probe._read_counter(repo, ".lifecycle-push-failures")
    if n > 0:
        return [{"category": "push_failures_counter", "spec_id": "-", "detail": f"count={n}"}]
    return []


def bootstrap_anomaly(repo: str) -> list[dict]:
    n = audit_probe._read_counter(repo, ".bootstrap-anomaly-count")
    if n > 0:
        return [{"category": "bootstrap_anomaly", "spec_id": "-", "detail": f"count={n}"}]
    return []


def bootstrap_unparsable(repo: str) -> list[dict]:
    """TECH-195 Task 1."""
    n = audit_probe._read_counter(repo, ".bootstrap-unparsable-count")
    if n > 0:
        return [{"category": "bootstrap_unparsable", "spec_id": "-", "detail": f"count={n}"}]
    return []
