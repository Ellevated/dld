"""Shared fixtures for tests/integration.

ADR-013: real fs + real git + real sqlite. Only external binaries get
replaced, and only at the process boundary — never business logic.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


def _record(log_file: Path, args: list[str]) -> None:
    """Append one invocation to the call log, exactly as `echo "$@"` would."""
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(" ".join(str(a) for a in args) + "\n")


@pytest.fixture
def stub_pueue_bin(tmp_path, monkeypatch):
    """Replace the external `pueue` binary with a recorder of its argv.

    Returns the path of the call log. One line per invocation, arguments
    space-joined, `pueue` itself omitted. `pueue add --print-task-id` also
    answers with a task id so callback can parse a successful dispatch;
    every other subcommand exits 0 with empty stdout (callback's pueue
    readers are all wrapped in try/except and treat that as "no data").

    POSIX gets a real shell stub first on PATH, so callback resolves and
    execs it for real. Windows cannot: CreateProcess only ever appends
    `.exe` to a bare name, so a PATH stub called `pueue` — or `pueue.cmd` —
    is unreachable and every dispatch dies with FileNotFoundError. There
    the boundary is intercepted one level up, at `subprocess.run`, for
    argv[0] == "pueue" only; everything else runs for real.
    """
    log_file = tmp_path / "pueue-calls.log"

    if os.name != "nt":
        stub_dir = tmp_path / "bin"
        stub_dir.mkdir()
        stub = stub_dir / "pueue"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$@" >> "{log_file}"\n'
            "if echo \"$@\" | grep -q 'print-task-id'; then echo 42; fi\n"
            "exit 0\n"
        )
        stub.chmod(0o755)
        monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ['PATH']}")
        return log_file

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and str(cmd[0]) == "pueue":
            argv = [str(c) for c in cmd[1:]]
            _record(log_file, argv)
            stdout = "42\n" if "--print-task-id" in argv else ""
            return subprocess.CompletedProcess(cmd, 0, stdout, "")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)
    return log_file
