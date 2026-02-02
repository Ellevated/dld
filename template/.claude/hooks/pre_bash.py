#!/usr/bin/env python3
"""Pre-Bash hook: blocks dangerous commands.

Hard blocks:
- Push to main branch (protected workflow)
- Destructive git operations (git clean -fd, git reset --hard)
- Force push to protected branches (develop, main)

Soft blocks (ask confirmation):
- Merge without --ff-only (rebase-first workflow)

Customize BLOCKED_PATTERNS for project-specific rules.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import allow_tool, ask_tool, deny_tool, get_tool_input, read_hook_input

# Blocked patterns - hard deny (no confirmation)
# Note: git push -f to feature branches is ALLOWED (rebase workflow)
# Only develop/main are protected from force push
BLOCKED_PATTERNS = [
    # Push to main (Hard Block)
    (
        r"git\s+push[^|]*\bmain\b",
        "Push to main blocked!\n\n"
        "Use PR workflow: develop -> PR -> main\n"
        "Direct push to main is forbidden.\n\n"
        "See: CLAUDE.md -> Git Autonomous Mode",
    ),
    # Destructive git operations (Multi-Agent Safety)
    # Negative lookahead (?!-\w*n) excludes dry-run variants (-fdn, -dfn)
    (
        r"git\s+clean\s+(?!-\w*n)-[a-z]*f[a-z]*d|git\s+clean\s+(?!-\w*n)-[a-z]*d[a-z]*f",
        "git clean -fd blocked!\n\n"
        "Destroys untracked files from other agents.\n"
        "Safe alternatives:\n"
        "  git checkout -- .     # reset tracked only\n"
        "  git stash -u          # stash with recovery\n"
        "  git clean -fdn        # dry-run first\n\n"
        "See: CLAUDE.md -> Multi-Agent Safety",
    ),
    (
        r"git\s+reset\s+--hard",
        "git reset --hard blocked!\n\n"
        "Wipes uncommitted work from all agents.\n"
        "Safe alternatives:\n"
        "  git checkout -- .     # reset tracked only\n"
        "  git stash             # save work first\n\n"
        "See: CLAUDE.md -> Multi-Agent Safety",
    ),
    # Force push safety (allow feature branches only)
    (
        r"git\s+push\s+(-f|--force)[^|]*\b(develop|main)\b",
        "Force push to protected branch blocked!\n\n"
        "Force push allowed only on feature branches.\n"
        "Protected: develop, main\n\n"
        "If rebasing feature branch, use:\n"
        "  git push -f origin feature/{ID}\n\n"
        "See: CLAUDE.md -> Git Autonomous Mode",
    ),
    (
        r"git\s+push[^|]*\b(develop|main)\b[^|]*(-f|--force)",
        "Force push to protected branch blocked!\n\n"
        "Force push allowed only on feature branches.\n"
        "Protected: develop, main\n\n"
        "If rebasing feature branch, use:\n"
        "  git push -f origin feature/{ID}\n\n"
        "See: CLAUDE.md -> Git Autonomous Mode",
    ),
]

# Merge without rebase verification (Parallel Safety)
MERGE_PATTERNS = [
    (
        r"git\s+merge",  # Match any merge, Python filters --ff-only
        "Use --ff-only for merges!\n\n"
        "Rebase-first workflow required:\n"
        "  1. git rebase origin/develop  # in worktree\n"
        "  2. git push -f origin {branch}  # force push feature\n"
        "  3. git merge --ff-only {branch}  # in main repo\n\n"
        "See: CLAUDE.md -> Rebase Workflow",
    ),
]


def _log_error(error: Exception) -> None:
    """Log hook error for diagnostics."""
    try:
        import datetime

        with open("/tmp/claude-hook-errors.log", "a") as f:  # nosec B108
            f.write(f"{datetime.datetime.now()} [pre_bash]: {error}\n")
    except Exception:
        pass  # nosec B110 - intentional fail-safe


def main() -> None:
    try:
        data = read_hook_input()
        command = get_tool_input(data, "command") or ""

        # Hard blocks (deny immediately)
        for pattern, message in BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                deny_tool(message)
                return

        # Soft blocks (ask confirmation)
        for pattern, message in MERGE_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                # Allow --ff-only explicitly (per spec)
                if "--ff-only" in command:
                    continue
                ask_tool(message)
                return

        allow_tool()
    except Exception as e:
        _log_error(e)
        allow_tool()


if __name__ == "__main__":
    main()
