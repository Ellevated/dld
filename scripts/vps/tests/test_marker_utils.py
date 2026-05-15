"""Unit tests for marker_utils (BUG-974).

Covers:
- extract_marker_blocks: counts, bodies, line ranges.
- merge_callback_markers: replaces bodies, degrades open on structure mismatch.
"""

import sys
from pathlib import Path

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

from marker_utils import (  # noqa: E402
    extract_marker_blocks,
    merge_callback_markers,
)


M_START = "<!-- DLD-CALLBACK-MARKER-START v1 -->"
M_END = "<!-- DLD-CALLBACK-MARKER-END -->"


def test_extract_marker_blocks_two_blocks():
    text = (
        "# Spec\n"
        f"{M_START}\n"
        "**Status:** done\n"
        f"{M_END}\n"
        "\n"
        "## Allowed Files\n"
        f"{M_START}\n"
        "- `file.py`\n"
        f"{M_END}\n"
    )
    blocks = extract_marker_blocks(text)
    assert len(blocks) == 2
    assert blocks[0].body == "**Status:** done"
    assert blocks[1].body == "- `file.py`"
    assert blocks[0].version == "1"


def test_extract_marker_blocks_no_markers_returns_empty():
    assert extract_marker_blocks("# just text\nno markers here\n") == []


def test_extract_marker_blocks_unmatched_start_skipped():
    text = f"{M_START}\nbody without end\n"
    assert extract_marker_blocks(text) == []


def test_merge_replaces_block_bodies():
    head = (
        "# Spec\n"
        f"{M_START}\n"
        "**Status:** done\n"
        f"{M_END}\n"
    )
    wt = head.replace("done", "queued")
    merged = merge_callback_markers(head, wt)
    assert "**Status:** done" in merged
    assert "**Status:** queued" not in merged
    # Trailing newline preserved.
    assert merged.endswith("\n")


def test_merge_replaces_only_marker_bodies_preserves_surrounding_text():
    head = (
        "intro\n"
        f"{M_START}\n"
        "callback-owned: A\n"
        f"{M_END}\n"
        "user prose\n"
    )
    wt = (
        "intro CHANGED BY USER\n"
        f"{M_START}\n"
        "callback-owned: STALE\n"
        f"{M_END}\n"
        "user prose CHANGED BY USER\n"
    )
    merged = merge_callback_markers(head, wt)
    assert "callback-owned: A" in merged
    assert "callback-owned: STALE" not in merged
    # User-owned prose outside markers must be retained from wt.
    assert "intro CHANGED BY USER" in merged
    assert "user prose CHANGED BY USER" in merged


def test_merge_mismatched_counts_returns_wt_unchanged():
    head = "no markers\n"
    wt = f"{M_START}\n**Status:** queued\n{M_END}\n"
    assert merge_callback_markers(head, wt) == wt


def test_merge_no_markers_either_side_noop():
    head = "plain head\n"
    wt = "plain wt with edits\n"
    assert merge_callback_markers(head, wt) == wt


def test_merge_handles_multiline_bodies():
    head = (
        f"{M_START}\n"
        "- `a.py`\n"
        "- `b.py`\n"
        "- `c.py`\n"
        f"{M_END}\n"
    )
    wt = (
        f"{M_START}\n"
        "- `a.py`\n"
        f"{M_END}\n"
    )
    merged = merge_callback_markers(head, wt)
    assert "- `b.py`" in merged
    assert "- `c.py`" in merged
