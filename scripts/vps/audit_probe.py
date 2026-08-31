#!/usr/bin/env python3
"""
Module: audit_probe
Role: READ-ONLY git/filesystem probes and markdown/backlog parsing helpers for
      lifecycle_audit. Extracted from lifecycle_audit (TECH-211).
Uses: subprocess (git CLI), re, pathlib
Used by: lifecycle_audit.py (audit_project orchestration), audit_categories.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

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
# Counters / yaml introspection (read-only)
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
