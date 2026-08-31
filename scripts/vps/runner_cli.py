"""
Module: runner_cli
Role: resolve which Claude Code CLI binary the SDK should drive.
Uses: os, re, shutil, subprocess, pathlib, logging

Used by:
  - claude-runner.py
"""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("claude-runner")

# A CLI older than this does not know the Opus 5 / Sonnet 5 model IDs and will
# silently run its own era's default model instead of the one we pin. 2.1.190 is
# the floor we have verified resolves `claude-opus-5` correctly.
_MIN_CLI_VERSION = (2, 1, 190)

# Distro-style install location, probed last. Named so tests can point it
# somewhere hermetic instead of at whatever the host happens to have.
_SYSTEM_CLI_FALLBACK = "/usr/local/bin/claude"


def _cli_version(path: str) -> tuple[int, int, int] | None:
    """Ask a CLI binary which version it is. None if it won't answer."""
    try:
        p = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", p.stdout or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _resolve_cli_path() -> tuple[str | None, tuple[int, int, int] | None]:
    """Pick the NEWEST Claude Code CLI on the box, not the first one on PATH.

    Ordering by PATH is what broke this for four months (found 2026-07-26). Under
    pueue the daemon inherits systemd's PATH — `/usr/local/sbin:/usr/local/bin:…`
    with no `~/.local/bin` at all — so `shutil.which("claude")` returned a
    root-owned 2.1.72 binary frozen since March, while the installer's
    self-updating launcher at ~/.local/bin/claude sat at 2.1.220 unused. 2.1.72
    predates Opus 5, so `model="claude-opus-5"` silently ran claude-opus-4-6:
    a 200K window instead of 1M, autocompact every ~155K, 34 compactions in one
    90-minute run, and a timeout with nothing merged.

    Version comparison is the only ordering that self-heals — whichever install
    the operator keeps current wins, no matter how PATH is arranged. An explicit
    CLAUDE_CLI_PATH still overrides everything. Candidates that refuse to report
    a version are kept only as a last-resort fallback, and returning (None, None)
    lets the SDK use its bundled CLI rather than crash.
    """
    pinned = os.environ.get("CLAUDE_CLI_PATH")
    if pinned and Path(pinned).exists():
        return pinned, _cli_version(pinned)

    candidates = [
        shutil.which("claude"),
        str(Path.home() / ".local" / "bin" / "claude"),
        _SYSTEM_CLI_FALLBACK,
    ]
    seen: set[str] = set()
    best: tuple[str, tuple[int, int, int]] | None = None
    unversioned: str | None = None

    for candidate in candidates:
        if not candidate:
            continue
        real = str(Path(candidate).resolve()) if Path(candidate).exists() else ""
        if not real or real in seen:
            continue
        seen.add(real)
        version = _cli_version(candidate)
        if version is None:
            unversioned = unversioned or candidate
        elif best is None or version > best[1]:
            best = (candidate, version)

    if best:
        return best
    return unversioned, None


def warn_if_stale(
    cli_path: str | None, cli_version: tuple[int, int, int] | None, model: str
) -> None:
    """A CLI that predates the pinned model does not error — it quietly runs its
    own default instead, and the only visible symptom is a shrunken context
    window and a compaction storm. Say so out loud."""
    if cli_version is not None and cli_version < _MIN_CLI_VERSION:
        logger.warning(
            "CLI %s at %s is older than %s and may not know %s — it will run its "
            "own default model with that model's (smaller) context window. "
            "Point CLAUDE_CLI_PATH at a current install.",
            ".".join(map(str, cli_version)),
            cli_path,
            ".".join(map(str, _MIN_CLI_VERSION)),
            model,
        )


# Every tool a DLD skill may need. Kept next to the CLI resolution rather than in the
# runner: both answer "what can this binary do", and both are read by tests that never
# import the SDK.
ALLOWED_TOOLS = [
    "Skill",
    "Agent",
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "NotebookEdit",
]
