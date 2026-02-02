#!/usr/bin/env python3
"""Pre-Edit hook: protects files and enforces LOC limits.

Hard blocks:
- Files outside Allowed Files in spec (when spec exists)
- Protected test files (contracts/, regression/)

Soft blocks:
- Files exceeding LOC limits (400 code, 600 tests)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    allow_tool,
    ask_tool,
    deny_tool,
    get_tool_input,
    infer_spec_from_branch,
    is_file_allowed,
    read_hook_input,
)

# Protected paths (Hard Block)
PROTECTED_PATHS = [
    "tests/contracts/",
    "tests/regression/",
]

# LOC limits (Soft Block)
MAX_LOC_CODE = 400
MAX_LOC_TEST = 600
# 7/8 = 0.875 -> gives round thresholds: 350 LOC (code), 525 LOC (tests)
WARN_THRESHOLD = 0.875

# Sync zones (files that should stay in sync with template/)
SYNC_ZONES = [
    ".claude/",
    "scripts/",
]

# Excluded from sync reminders (DLD-specific customizations)
EXCLUDE_FROM_SYNC = [
    ".claude/rules/localization.md",
    ".claude/rules/template-sync.md",
    ".claude/rules/git-local-folders.md",
    ".claude/CUSTOMIZATIONS.md",
    ".claude/settings.local.json",
]


def count_lines(file_path: str) -> int:
    """Count lines in file."""
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def is_test_file(file_path: str) -> bool:
    """Check if file is a test file."""
    return "_test.py" in file_path or "/tests/" in file_path


def normalize_path(file_path: str) -> str:
    """Convert absolute path to relative."""
    if not file_path:
        return ""

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    if file_path.startswith(project_dir):
        return file_path[len(project_dir) :].lstrip("/")
    return file_path


def check_sync_zone(rel_path: str) -> "str | None":
    """Returns reminder message if file is in sync zone."""
    if not rel_path:
        return None

    # Check if file is in a sync zone
    in_sync_zone = False
    for zone in SYNC_ZONES:
        if rel_path.startswith(zone):
            in_sync_zone = True
            break

    if not in_sync_zone:
        return None

    # Check if file is excluded from sync
    if rel_path in EXCLUDE_FROM_SYNC:
        return None

    # Check if template version exists
    template_path = f"template/{rel_path}"
    if os.path.exists(template_path):
        return (
            f"SYNC ZONE: {rel_path}\n\n"
            f"This file exists in template/{rel_path}\n"
            f"Remember to sync changes bidirectionally.\n\n"
            f"See: .claude/rules/template-sync.md"
        )

    return None


def _log_error(error: Exception) -> None:
    """Log hook error for diagnostics."""
    try:
        import datetime

        with open("/tmp/claude-hook-errors.log", "a") as f:  # nosec B108
            f.write(f"{datetime.datetime.now()} [pre_edit]: {error}\n")
    except Exception:
        pass  # nosec B110 - intentional fail-safe


def main():
    try:
        data = read_hook_input()
        file_path = get_tool_input(data, "file_path") or ""

        rel_path = normalize_path(file_path)

        # Check Allowed Files (Hard Block) - only when spec exists
        spec_path = os.environ.get("CLAUDE_CURRENT_SPEC_PATH") or infer_spec_from_branch()
        allowed, allowed_files = is_file_allowed(rel_path, spec_path)
        if not allowed:
            allowed_list = "\n".join(f"  - {f}" for f in allowed_files[:10])
            deny_tool(
                f"File not in Allowed Files!\n\n"
                f"{rel_path}\n\n"
                f"Spec: {spec_path or '(not found)'}\n\n"
                f"Allowed files:\n{allowed_list}\n\n"
                f"Add file to spec's ## Allowed Files or change approach."
            )
            return

        # Check protected paths (Hard Block)
        for protected in PROTECTED_PATHS:
            if protected in rel_path:
                deny_tool(
                    f"Protected test file!\n\n"
                    f"{rel_path}\n\n"
                    f"tests/contracts/ and tests/regression/ cannot be modified.\n"
                    f"Fix the code, not the test.\n\n"
                    f"See: CLAUDE.md -> Test Safety"
                )
                return

        # Check LOC limits (Soft Block)
        # Use absolute path for file operations
        abs_path = file_path if file_path.startswith("/") else os.path.join(os.getcwd(), file_path)

        if os.path.exists(abs_path):
            loc = count_lines(abs_path)
            max_loc = MAX_LOC_TEST if is_test_file(rel_path) else MAX_LOC_CODE
            warn_loc = int(max_loc * WARN_THRESHOLD)

            if loc >= max_loc:
                ask_tool(
                    f"File exceeds LOC limit!\n\n"
                    f"{rel_path}: {loc} lines (limit: {max_loc})\n\n"
                    f"Consider splitting the file.\n"
                    f"See: CLAUDE.md -> File Limits\n\n"
                    f"Proceed anyway?"
                )
                return
            elif loc >= warn_loc:
                ask_tool(
                    f"File approaching LOC limit\n\n"
                    f"{rel_path}: {loc} lines (limit: {max_loc})\n\n"
                    f"Proceed?"
                )
                return

        # Check sync zone (Soft reminder - just info, doesn't block)
        sync_reminder = check_sync_zone(rel_path)
        if sync_reminder:
            # Use ask_tool to show reminder but allow proceeding
            ask_tool(sync_reminder)
            return

        allow_tool()
    except Exception as e:
        _log_error(e)
        allow_tool()


if __name__ == "__main__":
    main()
