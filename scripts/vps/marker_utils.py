"""
Module: marker_utils
Role: Shared DLD-CALLBACK-MARKER regex + block extractor/merger.
Uses: re, dataclasses
Used by: callback.py (allowed-files parser), orchestrator.py (autostash recovery)

ADR-018: callback.py is the sole writer of any content inside
DLD-CALLBACK-MARKER-START/END pairs. Other actors (notably the
orchestrator's autostash recovery in git_pull) MUST treat the HEAD
version of these blocks as authoritative and restore it on top of
any stash-pop result that diverged.

BUG-974: a no-conflict `git stash pop` after `git pull` silently
overwrote a fresh callback Status commit; this module enables the
orchestrator to detect and repair that case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Regex SSOT — keep in sync with callback.py imports.
DLD_MARKER_START_RE = re.compile(
    r"^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$"
)
DLD_MARKER_END_RE = re.compile(r"^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$")
DLD_SUPPORTED_MARKER_VERSIONS: frozenset[str] = frozenset({"1"})


@dataclass(frozen=True)
class MarkerBlock:
    """One DLD-CALLBACK-MARKER-START/END pair.

    Indices are line numbers in the source text (0-based).
    start_line points at the START comment; end_line at the END comment.
    body is the joined inner content (lines between, exclusive),
    with a trailing newline stripped — useful for equality checks.
    """

    start_line: int
    end_line: int
    version: str
    body: str


def extract_marker_blocks(text: str) -> list[MarkerBlock]:
    """Return all well-formed marker blocks in `text`, in source order.

    - Unmatched START (no closing END) is skipped silently — caller
      logs/handles via len() mismatch.
    - Nested STARTs are not supported; the first END wins.
    """
    lines = text.splitlines()
    blocks: list[MarkerBlock] = []
    i = 0
    while i < len(lines):
        m = DLD_MARKER_START_RE.match(lines[i])
        if not m:
            i += 1
            continue
        ver = m.group("ver")
        j = i + 1
        while j < len(lines) and not DLD_MARKER_END_RE.match(lines[j]):
            j += 1
        if j >= len(lines):
            # Unmatched START — bail out; caller will see fewer blocks.
            break
        body = "\n".join(lines[i + 1 : j])
        blocks.append(MarkerBlock(start_line=i, end_line=j, version=ver, body=body))
        i = j + 1
    return blocks


def merge_callback_markers(head_text: str, wt_text: str) -> str:
    """Return wt_text with each DLD-CALLBACK-MARKER block body replaced
    by the corresponding block body from head_text (ADR-018 enforcement).

    Degrade-open contract:
      - If block counts differ between HEAD and working tree, return
        wt_text unchanged. Structural divergence is operator territory.
      - If neither side has marker blocks, return wt_text unchanged.
      - Each pair is matched by source order (1st HEAD block ↔ 1st WT
        block, etc.). Marker version is taken from HEAD (callback wrote it).
    """
    head_blocks = extract_marker_blocks(head_text)
    wt_blocks = extract_marker_blocks(wt_text)
    if not head_blocks and not wt_blocks:
        return wt_text
    if len(head_blocks) != len(wt_blocks):
        return wt_text  # structure differs — bail out (caller logs)

    # Walk wt_text line by line, splicing in HEAD bodies at the wt block
    # boundaries. Operating on lines avoids re-search drift across blocks.
    wt_lines = wt_text.splitlines(keepends=False)
    # Preserve trailing-newline behavior of wt_text.
    had_trailing_newline = wt_text.endswith("\n")

    out: list[str] = []
    cursor = 0
    for hb, wb in zip(head_blocks, wt_blocks):
        # Emit pre-block lines verbatim from wt.
        out.extend(wt_lines[cursor : wb.start_line])
        # Emit START marker from HEAD (carries authoritative version).
        out.append(f"<!-- DLD-CALLBACK-MARKER-START v{hb.version} -->")
        # Emit HEAD body (may span multiple lines).
        if hb.body:
            out.extend(hb.body.split("\n"))
        out.append("<!-- DLD-CALLBACK-MARKER-END -->")
        cursor = wb.end_line + 1
    # Tail after the last block.
    out.extend(wt_lines[cursor:])

    result = "\n".join(out)
    if had_trailing_newline:
        result += "\n"
    return result
