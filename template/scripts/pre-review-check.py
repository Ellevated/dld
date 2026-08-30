#!/usr/bin/env python3
"""
Deterministic pre-review checks.

Run BEFORE AI review to save tokens on obvious issues.
Exit 0 = PASS, Exit 1 = FAIL with issues list.

Usage:
    python scripts/pre-review-check.py file1.py file2.py ...
    python scripts/pre-review-check.py  # reads from stdin (newline-separated)
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple


class Issue(NamedTuple):
    """A detected issue."""

    file: str
    line: int
    check: str
    message: str


def check_todo_fixme(file_path: Path) -> list[Issue]:
    """Check for TODO/FIXME comments in Python files."""
    issues: list[Issue] = []
    if not file_path.suffix == ".py":
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues

    pattern = re.compile(r"#\s*(TODO|FIXME)[\s:](.*)", re.IGNORECASE)
    for line_num, line in enumerate(content.splitlines(), start=1):
        match = pattern.search(line)
        if match:
            tag, text = match.groups()
            issues.append(
                Issue(
                    file=str(file_path),
                    line=line_num,
                    check="TODO/FIXME",
                    message=f"# {tag.upper()}: {text.strip()[:50]}",
                )
            )
    return issues


def check_bare_exceptions(file_path: Path) -> list[Issue]:
    """Check for bare except: or except Exception: without re-raise."""
    issues: list[Issue] = []
    if not file_path.suffix == ".py":
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues

    lines = content.splitlines()
    # Pattern: except: or except Exception: (without specific exception type)
    bare_except_pattern = re.compile(r"^\s*except\s*:\s*(#.*)?$")
    generic_except_pattern = re.compile(r"^\s*except\s+Exception\s*:\s*(#.*)?$")

    for line_num, line in enumerate(lines, start=1):
        if bare_except_pattern.match(line):
            # Check if next non-empty line has 'raise'
            has_reraise = _check_reraise(lines, line_num)
            if not has_reraise:
                issues.append(
                    Issue(
                        file=str(file_path),
                        line=line_num,
                        check="BARE_EXCEPT",
                        message="Bare `except:` without re-raise",
                    )
                )
        elif generic_except_pattern.match(line):
            has_reraise = _check_reraise(lines, line_num)
            if not has_reraise:
                issues.append(
                    Issue(
                        file=str(file_path),
                        line=line_num,
                        check="BARE_EXCEPT",
                        message="`except Exception:` without re-raise",
                    )
                )
    return issues


def _check_reraise(lines: list[str], except_line: int) -> bool:
    """Check if except block contains a raise statement."""
    # Look at next 5 lines for a raise statement
    for i in range(except_line, min(except_line + 5, len(lines))):
        line = lines[i].strip()
        if line.startswith("raise"):
            return True
        # If we hit another except/else/finally/def/class, stop looking
        if re.match(r"^(except|else|finally|def |class |@)", line):
            break
    return False


def check_loc_limits(file_path: Path) -> list[Issue]:
    """Check file line count against limits (400 code, 600 tests)."""
    issues: list[Issue] = []
    if not file_path.suffix == ".py":
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues

    line_count = len(content.splitlines())
    is_test = "test" in file_path.name.lower() or "/tests/" in str(file_path)
    limit = 600 if is_test else 400

    if line_count > limit:
        issues.append(
            Issue(
                file=str(file_path),
                line=line_count,
                check="LOC_LIMIT",
                message=f"{line_count} lines (max {limit})",
            )
        )
    return issues


def main() -> int:
    """Run all checks on provided files."""
    # Get files from args or stdin
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:]]
    else:
        # Read from stdin (newline-separated)
        files = [Path(line.strip()) for line in sys.stdin if line.strip()]

    if not files:
        print("PRE-REVIEW PASSED (no files to check)")
        return 0

    all_issues: list[Issue] = []

    for file_path in files:
        if not file_path.exists():
            continue
        all_issues.extend(check_todo_fixme(file_path))
        all_issues.extend(check_bare_exceptions(file_path))
        all_issues.extend(check_loc_limits(file_path))

    if not all_issues:
        print("PRE-REVIEW PASSED")
        return 0

    print("PRE-REVIEW FAILED:")
    for issue in all_issues:
        print(f"  - {issue.file}:{issue.line}: [{issue.check}] {issue.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
