#!/usr/bin/env python3
"""
Module: spec_lint
Role: CLI linter for DLD spec files -- validates DLD-CALLBACK-MARKER pairing,
      version support, and inner content.
Uses: re, argparse, subprocess, pathlib, sys
Used by: .git-hooks/pre-commit, CI smoke, tests/unit/test_spec_lint.py

TECH-175 marker SSOT:
  START = ^<!-- DLD-CALLBACK-MARKER-START v<N> -->
  END   = ^<!-- DLD-CALLBACK-MARKER-END -->
  SUPPORTED_VERSIONS = {"1"}
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# --- Regex SSOT (TECH-175) ---------------------------------------------------
START_RE = re.compile(
    r"^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$"
)
END_RE = re.compile(r"^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$")
SUPPORTED_VERSIONS: frozenset[str] = frozenset({"1"})
ALLOWED_HEAD_RE = re.compile(r"^##[ \t]+Allowed Files[ \t]*$")
TECH167_INNER_RE = re.compile(r"<!--\s*callback-allowlist\s+v1\b[^>]*-->")


class LintError(NamedTuple):
    code: str
    line_idx: int  # 0-based
    msg: str


def _is_inside_any_block(idx: int, blocks: list[tuple[int, int, str]]) -> bool:
    return any(s < idx < e for s, e, _ in blocks)


def lint_spec(text: str) -> list[LintError]:
    """Validate marker pairing, versions, and inner content.

    Returns list of LintError. Empty list = no issues.
    """
    lines = text.splitlines()
    blocks: list[tuple[int, int, str]] = []
    open_start: int | None = None
    open_ver: str | None = None
    errs: list[LintError] = []

    for i, ln in enumerate(lines):
        m = START_RE.match(ln)
        if m:
            if open_start is not None:
                errs.append(LintError("LINT_E004_NESTED", i, "marker inside open block"))
            open_start = i
            open_ver = m.group("ver")
            if open_ver not in SUPPORTED_VERSIONS:
                errs.append(LintError("LINT_E005_UNKNOWN_VERSION", i, f"v{open_ver}"))
            continue
        if END_RE.match(ln):
            if open_start is None:
                errs.append(LintError("LINT_E003_UNMATCHED_END", i, ""))
            else:
                blocks.append((open_start, i, open_ver or "?"))
                open_start = None
                open_ver = None
            continue

    if open_start is not None:
        errs.append(LintError("LINT_E002_UNMATCHED_START", open_start, ""))

    # ## Allowed Files coverage check
    af_idx = next((i for i, ln in enumerate(lines) if ALLOWED_HEAD_RE.match(ln)), None)
    if af_idx is not None and not _is_inside_any_block(af_idx, blocks):
        errs.append(LintError("LINT_E006_ALLOWED_FILES_OUTSIDE_BLOCK", af_idx, ""))

    # Inner TECH-167 marker required in each Allowed Files block
    for s, e, _ in blocks:
        block_lines = lines[s + 1:e]
        has_af = any(ALLOWED_HEAD_RE.match(ln) for ln in block_lines)
        if has_af and not TECH167_INNER_RE.search("\n".join(block_lines)):
            errs.append(LintError("LINT_E008_INNER_TECH167_MISSING", s, ""))

    if not blocks:
        errs.append(LintError("LINT_E001_NO_MARKERS", 0, ""))

    return errs


def lint_spec_blocks(path: str | Path) -> list[tuple[int, int, str]]:
    """Return (start_idx, end_idx, ver) marker blocks for a file.

    Used by --diff-warn to check diff hunk intersection.
    """
    lines = Path(path).read_text(errors="replace").splitlines()
    blocks: list[tuple[int, int, str]] = []
    open_start: int | None = None
    open_ver: str | None = None
    for i, ln in enumerate(lines):
        m = START_RE.match(ln)
        if m:
            open_start, open_ver = i, m.group("ver")
            continue
        if END_RE.match(ln) and open_start is not None:
            blocks.append((open_start, i, open_ver or "?"))
            open_start = None
    return blocks


def _diff_intersects_marker_block(
    diff_text: str, blocks: list[tuple[int, int, str]]
) -> bool:
    """Return True if any +/- diff line falls inside a marker block.

    Parses unified diff hunk headers: @@ -old +new,count @@
    """
    if not blocks:
        return False
    new_line = 0
    for raw in diff_text.splitlines():
        hunk = re.match(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", raw)
        if hunk:
            new_line = int(hunk.group(1)) - 1
            continue
        if raw.startswith(("+", "-")) and _is_inside_any_block(new_line, blocks):
            return True
        if not raw.startswith("-"):
            new_line += 1
    return False


def main(argv: list[str]) -> int:
    """CLI entry. Exit 0=ok, 1=lint errors, 2=diff-warn hit."""
    parser = argparse.ArgumentParser(description="DLD spec marker linter (TECH-175)")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--legacy-ok", action="store_true",
                        help="downgrade LINT_E001_NO_MARKERS to warning")
    parser.add_argument("--diff-warn", action="store_true",
                        help="exit 2 if staged diff touches a marker block")
    args = parser.parse_args(argv)

    rc = 0
    for p in args.paths:
        if args.diff_warn:
            blocks = lint_spec_blocks(p)
            try:
                diff = subprocess.check_output(
                    ["git", "diff", "--cached", "-U0", "--", str(p)],
                    stderr=subprocess.DEVNULL,
                ).decode(errors="replace")
            except subprocess.CalledProcessError:
                diff = ""
            if _diff_intersects_marker_block(diff, blocks):
                return 2
            return 0

        errs = lint_spec(Path(p).read_text(errors="replace"))
        for code, line_idx, msg in errs:
            is_warn = args.legacy_ok and code == "LINT_E001_NO_MARKERS"
            stream = sys.stdout if is_warn else sys.stderr
            print(f"{code} {p}:{line_idx + 1} {msg}".rstrip(), file=stream)
            if not is_warn:
                rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
