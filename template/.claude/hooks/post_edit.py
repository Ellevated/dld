#!/usr/bin/env python3
"""Post-Edit hook: auto-formats Python files after Write/Edit.

Actions:
- Runs `ruff format` on Python files
- Shows lint warnings (non-blocking)

Requirements:
- ruff must be installed (pip install ruff)
"""

from __future__ import annotations

import os
import subprocess  # nosec: B404
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import get_tool_input, log_hook_error, post_continue, read_hook_input

# Ruff configuration
RUFF_TIMEOUT_SECONDS = 10  # Max time for format/lint operations
RUFF_LINT_RULES = "E,W,F"  # Error, Warning, Pyflakes (fast, high-value checks)
MAX_LINT_WARNINGS = 5  # Limit output to avoid flooding Claude's context

# Claude Code tools that write files
# - Write: create new file
# - Edit: modify existing file (old_string → new_string)
# - MultiEdit: batch edits (reserved for future Claude Code feature)
FILE_WRITE_TOOLS = ("Write", "Edit", "MultiEdit")


def format_python_file(file_path: str) -> tuple[bool, str]:
    """Format Python file with ruff.

    Returns:
        (success, message)
    """
    try:
        result = subprocess.run(  # nosec: B603, B607
            ["ruff", "format", file_path],
            capture_output=True,
            text=True,
            timeout=RUFF_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            return True, "formatted"
        return False, result.stderr or "format failed"
    except FileNotFoundError:
        return False, "ruff not found"
    except subprocess.TimeoutExpired:
        return False, "format timeout"
    except Exception as e:
        return False, str(e)


def check_lint_warnings(file_path: str) -> list[str]:
    """Check for lint warnings (non-blocking).

    Returns:
        List of warning messages
    """
    try:
        result = subprocess.run(  # nosec: B603, B607
            ["ruff", "check", file_path, f"--select={RUFF_LINT_RULES}"],
            capture_output=True,
            text=True,
            timeout=RUFF_TIMEOUT_SECONDS,
        )
        if result.stdout:
            return result.stdout.strip().split("\n")[:MAX_LINT_WARNINGS]
        return []
    except Exception:  # nosec B110 — fail-safe: lint error = skip linting
        return []


def main() -> None:
    try:
        data = read_hook_input()
        tool_name = data.get("tool_name", "")

        # Only process file-writing tools
        if tool_name not in FILE_WRITE_TOOLS:
            post_continue()
            return

        file_path = get_tool_input(data, "file_path") or ""

        # Only process Python files
        if not file_path.endswith(".py"):
            post_continue()
            return

        # Skip if file doesn't exist
        if not os.path.exists(file_path):
            post_continue()
            return

        messages = []

        # Format the file
        success, msg = format_python_file(file_path)
        if success:
            messages.append(f"ruff format: {os.path.basename(file_path)}")

        # Check for lint warnings (non-blocking)
        warnings = check_lint_warnings(file_path)
        if warnings:
            messages.append(f"lint warnings ({len(warnings)}):")
            messages.extend([f"  {w}" for w in warnings])

        if messages:
            post_continue("\n".join(messages))
        else:
            post_continue()

    except Exception as e:
        log_hook_error("post_edit", e)
        post_continue()  # Fail-safe: don't block on errors


if __name__ == "__main__":
    main()
