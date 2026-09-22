"""Spec kind for lifecycle bootstrap — the **Kind:** header, else the ID prefix.

awardybot and dowry specs carry no **Kind:** line, and bootstrap recorded every one of them
as a flat "tech": 39 FTR, 17 BUG and 3 ARCH showed up as tech in backlog.md. The ID prefix
is the fallback; an explicit header still wins. Only the backlog render reads kind.

Split out of test_orchestrator_bootstrap.py, which sits at its LOC baseline.
"""

import sys
from pathlib import Path

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

from orchestrator import _parse_priority_kind  # noqa: E402


def test_parse_priority_kind_falls_back_to_id_prefix(tmp_path):
    """No **Kind:** header -> kind from the ID prefix, not a flat 'tech'."""
    cases = {
        "FTR-9001-x.md": "ftr",
        "BUG-9002-x.md": "bug",
        "ARCH-9003-x.md": "arch",
        "TECH-9004-x.md": "tech",
        "GROWTH-9005-x.md": "tech",
    }
    for name, expected in cases.items():
        spec = tmp_path / name
        spec.write_text("# Title\n\n**Priority:** P0 | **Date:** 2026-09-23\n")
        assert _parse_priority_kind(spec) == ("p0", expected), name


def test_parse_priority_kind_explicit_header_wins(tmp_path):
    spec = tmp_path / "FTR-9006-x.md"
    spec.write_text("**Priority:** P2\n**Kind:** bug\n")
    assert _parse_priority_kind(spec) == ("p2", "bug")
