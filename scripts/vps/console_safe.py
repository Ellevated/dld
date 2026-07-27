"""
Module: console_safe
Role: Make operator CLI output survive a non-UTF-8 console.

Uses:
  - sys: stdout/stderr reconfigure

Used by:
  - spec_operator.py, recover_false_reconciliation.py, recover_bootstrap_as_done.py,
    lifecycle_audit.py, migrate_backlog_to_lifecycle.py, spec_verify.py,
    audit_digest.py, openclaw-artifact-scan.py — called first thing in main()

Glossary: docs/orchestrator/

Why this exists (2026-07-27):
    `spec_operator.py force-done <project> <ID> '<reason>'` wrote the lifecycle YAML
    successfully and THEN raised UnicodeEncodeError printing its own success line —
    exiting 1. On Windows `sys.stdout` defaults to the ANSI code page (cp1251 here),
    and both the status arrow and any Cyrillic in the operator-supplied reason are
    unencodable there.

    For a human that is merely ugly: the traceback is visible and the write did land.
    For automation it is a lie — a wrapper reading the exit code sees a failed
    operator action and may retry a mutation that already succeeded.

    Third instance of this class in two days: `lifecycle._run` carried `text=True`
    (CRLF/cp1251 corruption, fixed 2026-07-26) and 17 test modules read/wrote files
    with no explicit `encoding=` (fixed 2026-07-27). Diagnostic output is not worth
    an exit code, so encoding errors are replaced, never raised.

FF invariant: ZERO imports from any other scripts/vps module. Safe to call before
anything else in main(), and safe to import from a module that must stay a pure leaf.
"""

from __future__ import annotations

import sys

__all__ = ["enable"]


def enable(encoding: str = "utf-8", errors: str = "replace") -> None:
    """Reconfigure stdout/stderr so unencodable characters degrade instead of raising.

    Idempotent and never raises. A stream that cannot be reconfigured (already
    detached, replaced by a non-TextIO object under pytest capture, or a Python
    build without `TextIOWrapper.reconfigure`) is skipped silently — the point is
    to remove a failure mode, not to add one.

    Args:
        encoding: Target encoding for both streams.
        errors: Codec error policy. `replace` keeps the process alive and the exit
            code honest; `strict` would reintroduce the bug this module exists for.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding=encoding, errors=errors)
        except (OSError, ValueError):
            # Detached or non-reconfigurable stream — nothing to protect.
            continue
