#!/usr/bin/env python3
"""
Module: orchestrator_git
Role: notice when a project checkout stops being able to fast-forward.
Uses: logging
Used by: orchestrator.git_pull (via the TECH-215 facade re-export)

`git_pull` itself deliberately stays in orchestrator.py — a test asserts that,
because patching `orchestrator.is_agent_running` has to be visible to it. What
lives here is the bookkeeping that pushed that file past the 400-LOC ceiling:
pure functions plus one counter, nothing that touches git.
"""

import logging

# Same logger name as orchestrator: operators grep one journald stream, and a
# split module is not a reason to split the log.
log = logging.getLogger("orchestrator")


# A project whose merge keeps failing is not receiving anything the fleet
# pushes — not prompts, not specs, not gate fixes. Three cycles is ~15 min.
_GIT_ADVANCE_STUCK_AFTER = 3
_GIT_ADVANCE_FAILURES: dict[str, int] = {}


def _one_line(text: str | None) -> str:
    """Collapse git's multi-line stderr so the whole reason survives one log line.

    journald splits on the newline: the message that mattered — the list of
    files blocking the merge — was cut off after "would be overwritten by
    merge:" for as long as this ran.
    """
    parts = (text or "").splitlines()
    return " | ".join(part.strip() for part in parts if part.strip())[:400]


def _note_git_advance_failure(project_id: str, project_dir: str, stderr: str) -> None:
    """Log a failed ff-only merge, escalating once the project is demonstrably stuck."""
    count = _GIT_ADVANCE_FAILURES.get(project_id, 0) + 1
    _GIT_ADVANCE_FAILURES[project_id] = count
    if count >= _GIT_ADVANCE_STUCK_AFTER:
        log.error(
            "git merge --ff-only origin/develop failed for %s on %d consecutive cycles — "
            "the project is receiving NO updates (prompts, specs, gate fixes) until this "
            "is cleared: %s",
            project_dir,
            count,
            stderr,
        )
    else:
        log.warning(
            "git merge --ff-only origin/develop failed for %s: %s — skip cycle",
            project_dir,
            stderr,
        )
