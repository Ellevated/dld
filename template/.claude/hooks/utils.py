#!/usr/bin/env python3
"""Shared utilities for Claude Code hooks.

This module provides helper functions for:
- PreToolUse hooks (pre_bash.py, pre_edit.py)
- PostToolUse hooks (post_edit.py)
- UserPromptSubmit hooks (prompt_guard.py)
- Stop hooks (session-end.sh)

Usage:
    from utils import allow_tool, deny_tool, read_hook_input
"""

from __future__ import annotations

import fnmatch
import glob as glob_module
import json
import os
import re
import subprocess  # nosec: B404
import sys
from pathlib import Path


def get_error_log_path() -> Path:
    """Get safe path for hook error log.

    Uses ~/.cache/dld/ instead of /tmp to prevent symlink attacks
    on multi-user systems.
    """
    cache_dir = Path.home() / ".cache" / "dld"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "hook-errors.log"


def read_hook_input() -> dict:
    """Read JSON from stdin (Claude Code passes context here)."""
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _output_json(data: dict) -> None:
    """Output JSON to stdout and exit.

    Uses sys.stdout.write + flush to avoid buffering issues
    that can cause "hook error" in Claude Code.
    """
    try:
        sys.stdout.write(json.dumps(data) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        pass  # Claude Code closed pipe early - OK
    sys.exit(0)


# PreToolUse hook helpers (pre_bash.py, pre_edit.py, etc.)


def allow_tool() -> None:
    """Allow tool execution (PreToolUse hooks).

    Example:
        # In pre_bash.py
        if is_safe_command(cmd):
            allow_tool()
    """
    sys.exit(0)  # Silent exit = allow


def deny_tool(reason: str) -> None:
    """Block tool execution (PreToolUse hooks).

    Args:
        reason: Explanation why the tool is blocked

    Example:
        # In pre_bash.py
        if "rm -rf /" in cmd:
            deny_tool("Destructive command blocked")
    """
    _output_json(
        {
            "hookSpecificOutput": {
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def ask_tool(reason: str) -> None:
    """Ask user confirmation for tool execution (PreToolUse hooks).

    Args:
        reason: Explanation why confirmation is needed

    Example:
        # In pre_bash.py
        if "git push --force" in cmd:
            ask_tool("Force push requires confirmation")
    """
    _output_json(
        {
            "hookSpecificOutput": {
                "permissionDecision": "ask",
                "permissionDecisionReason": reason,
            }
        }
    )


# UserPromptSubmit hook helpers (prompt_guard.py, etc.)


def approve_prompt() -> None:
    """Approve prompt submission (UserPromptSubmit hooks).

    Example:
        # In prompt_guard.py
        if is_safe_prompt(prompt):
            approve_prompt()
    """
    _output_json({"decision": "approve"})


def block_prompt(reason: str) -> None:
    """Block prompt submission (UserPromptSubmit hooks).

    Args:
        reason: Explanation why the prompt is blocked

    Example:
        # In prompt_guard.py
        if contains_secrets(prompt):
            block_prompt("Prompt contains sensitive data")
    """
    _output_json({"decision": "block", "reason": reason})


# Backward compatibility (deprecated)


def allow() -> None:
    """Deprecated: use allow_tool() or approve_prompt() for clarity."""
    allow_tool()


def block(reason: str) -> None:
    """Deprecated: use deny_tool() or block_prompt() for clarity."""
    deny_tool(reason)


def ask(reason: str) -> None:
    """Deprecated: use ask_tool() for clarity."""
    ask_tool(reason)


def get_tool_input(data: dict, key: str) -> str | None:
    """Extract value from tool_input."""
    return data.get("tool_input", {}).get(key)


def get_user_prompt(data: dict) -> str:
    """Extract user prompt from hook data."""
    return data.get("user_prompt", "") or ""


# PostToolUse hook helpers (post_edit.py, etc.)


def post_continue(message: str = "") -> None:
    """Continue after tool execution (PostToolUse hooks).

    Args:
        message: Optional context message for Claude

    Example:
        # In post_edit.py
        post_continue("Formatted with ruff")
    """
    if message:
        output: dict = {"decision": "continue"}
        output["hookSpecificOutput"] = {"additionalContext": message}
        _output_json(output)
    else:
        sys.exit(0)  # Silent exit = continue


def post_block(reason: str) -> None:
    """Block/revert tool execution (PostToolUse hooks).

    Args:
        reason: Explanation why the tool result is blocked

    Example:
        # In post_edit.py
        if has_syntax_error(file):
            post_block("File has syntax errors")
    """
    _output_json(
        {
            "decision": "block",
            "hookSpecificOutput": {"additionalContext": reason},
        }
    )


# Allowed Files enforcement

# Files always allowed to edit (regardless of spec)
ALWAYS_ALLOWED_PATTERNS = [
    "ai/features/*.md",
    "ai/backlog.md",
    "ai/diary/**",
    ".gitignore",
    "pyproject.toml",
    ".claude/**",  # Hooks, settings, agents, etc.
]


def extract_allowed_files(spec_path: str) -> list[str]:
    """Extract allowed files from spec's ## Allowed Files section.

    Args:
        spec_path: Path to feature spec file

    Returns:
        List of allowed file paths/patterns
    """
    try:
        with open(spec_path) as f:
            content = f.read()
    except Exception:
        return []

    # Find ## Allowed Files section
    match = re.search(r"## Allowed Files\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    section = match.group(1)
    allowed = []

    # Parse various formats:
    # 1. `path/to/file.py` - description
    # - path/to/file.py - description
    # | path/to/file.py | description |
    for line in section.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Extract path from markdown formats
        # Format: `path` or **path** or path - description
        path_match = re.search(
            r"[`*]*([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+(?::\d+(?:-\d+)?)?)[`*]*", line
        )
        if path_match:
            path = path_match.group(1)
            # Remove line number suffix if present (file.py:45-60 -> file.py)
            path = re.sub(r":\d+(-\d+)?$", "", path)
            if path and not path.startswith("|"):
                allowed.append(path)

    return allowed


def infer_spec_from_branch() -> str | None:
    """Infer spec path from current git branch name.

    Branch patterns:
    - feature/FTR-100 -> ai/features/FTR-100-*.md
    - fix/BUG-200 -> ai/features/BUG-200-*.md
    - tech/TECH-300 -> ai/features/TECH-300-*.md

    Returns:
        Path to spec file if found, None otherwise
    """
    try:
        result = subprocess.run(  # nosec: B603, B607
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        branch = result.stdout.strip()
        if not branch:
            return None

        # Extract task ID from branch name
        # feature/FTR-100 -> FTR-100
        # fix/BUG-200 -> BUG-200
        match = re.search(r"(FTR|BUG|TECH|ARCH|SEC)-\d+", branch, re.IGNORECASE)
        if not match:
            return None

        task_id = match.group(0).upper()

        # Find spec file
        pattern = f"ai/features/{task_id}-*.md"
        matches = glob_module.glob(pattern)
        if matches:
            return matches[0]

        return None
    except Exception:
        return None


def is_file_allowed(file_path: str, spec_path: str | None) -> tuple[bool, list[str]]:
    """Check if file is in Allowed Files list.

    Args:
        file_path: Path to file being edited
        spec_path: Path to spec file (or None)

    Returns:
        (is_allowed, allowed_files)
    """
    # Normalize path
    file_path = os.path.normpath(file_path)
    if file_path.startswith("./"):
        file_path = file_path[2:]

    # Always-allowed files
    for pattern in ALWAYS_ALLOWED_PATTERNS:
        if fnmatch.fnmatch(file_path, pattern):
            return True, []

    # No spec = allow all (graceful degradation)
    if not spec_path:
        return True, []

    # Get allowed files from spec
    allowed_files = extract_allowed_files(spec_path)
    if not allowed_files:
        return True, []  # No Allowed Files section = allow all

    # Check if file matches any allowed pattern
    for allowed in allowed_files:
        allowed = os.path.normpath(allowed)
        # Direct match
        if file_path == allowed:
            return True, allowed_files
        # Glob pattern match
        if fnmatch.fnmatch(file_path, allowed):
            return True, allowed_files
        # Prefix match (allow subdirs)
        if file_path.startswith(allowed.rstrip("/*") + "/"):
            return True, allowed_files

    return False, allowed_files
