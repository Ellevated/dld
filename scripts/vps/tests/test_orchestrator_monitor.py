"""Monitor reads a healthy host correctly under cron's stripped environment.

cron gives no XDG_RUNTIME_DIR and PATH=/usr/bin:/bin. Both `systemctl --user`
and `pueue` then fail to reach the user session, write to stderr and leave
stdout EMPTY — which the monitor used to read as "orchestrator dead" and
"circuit breaker tripped". 3910 false alerts between 2026-05-28 and 2026-08-18.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import orchestrator_monitor as mon  # noqa: E402


def _completed(stdout: str = "", stderr: str = "", code: int = 0):
    return subprocess.CompletedProcess(args=["x"], returncode=code, stdout=stdout, stderr=stderr)


# --- _runtime_env -------------------------------------------------------


def test_runtime_env_fills_xdg_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(mon.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(
        mon.Path, "is_dir", lambda self: str(self).replace("\\", "/") == "/run/user/1000"
    )

    env = mon._runtime_env()

    # str(Path(...)) so the assertion holds on the Windows dev box too
    assert env["XDG_RUNTIME_DIR"] == str(Path("/run/user/1000"))


def test_runtime_env_keeps_existing_xdg(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/4242")

    assert mon._runtime_env()["XDG_RUNTIME_DIR"] == "/run/user/4242"


def test_runtime_env_adds_usr_local_bin(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    assert "/usr/local/bin" in mon._runtime_env()["PATH"].split(os.pathsep)


def test_runtime_env_does_not_duplicate_path_entry(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")

    assert mon._runtime_env()["PATH"].split(os.pathsep).count("/usr/local/bin") == 1


# --- systemctl ----------------------------------------------------------


def test_service_check_reports_bus_failure_not_empty_detail(monkeypatch):
    monkeypatch.setattr(
        mon,
        "_run",
        lambda cmd: _completed(stderr="Failed to connect to bus: No medium found", code=1),
    )

    ok, detail = mon.check_orchestrator_service()

    assert ok is False
    assert "unreachable" in detail
    assert detail.strip() != ""  # the old bug: ORCHESTRATOR_DOWN with a blank reason


def test_service_check_active(monkeypatch):
    monkeypatch.setattr(mon, "_run", lambda cmd: _completed(stdout="active\n"))

    assert mon.check_orchestrator_service() == (True, "active")


def test_service_check_inactive(monkeypatch):
    monkeypatch.setattr(mon, "_run", lambda cmd: _completed(stdout="inactive\n", code=3))

    ok, detail = mon.check_orchestrator_service()

    assert (ok, detail) == (False, "inactive")


# --- pueue --------------------------------------------------------------


PUEUE_JSON = (
    '{"tasks":{"1":{"status":"Running"},"2":{"status":{"Queued":{}}},'
    '"3":{"status":"Success"}},"groups":{"claude-runner":{"status":"Running"}}}'
)


def test_pueue_status_raises_with_stderr_when_stdout_empty(monkeypatch):
    monkeypatch.setattr(
        mon,
        "_run",
        lambda cmd: _completed(
            stderr='I/O error at path ".../pueue_dld.socket" while connecting to daemon', code=1
        ),
    )

    with pytest.raises(RuntimeError, match="pueue_dld.socket"):
        mon._pueue_status()


def test_group_check_not_paused(monkeypatch):
    monkeypatch.setattr(mon, "_run", lambda cmd: _completed(stdout=PUEUE_JSON))

    ok, detail, reachable = mon.check_pueue_group()

    assert ok is True
    assert "claude-runner=Running" == detail
    assert reachable is True


def test_group_check_reports_daemon_down_not_paused_group(monkeypatch):
    """A dead daemon must NOT be reported as a tripped circuit breaker.

    Different incident, different fix (`systemctl --user start pueued` vs
    `pueue start --group`). Conflating them is what hid the 2026-08-23 outage
    behind the same string as 3910 earlier false alarms.
    """
    monkeypatch.setattr(
        mon,
        "_run",
        lambda cmd: _completed(
            stderr=(
                'I/O error at path "/run/user/1000/pueue_dld.socket" while '
                "connecting to daemon. Did you start it?\n"
                "Backtrace omitted. Run with RUST_BACKTRACE=1 ...\n"
                "Run with RUST_BACKTRACE=full to include source snippets."
            ),
            code=1,
        ),
    )

    ok, detail, reachable = mon.check_pueue_group()

    assert ok is False
    assert reachable is False
    # The detail must name the actual failure, not the RUST_BACKTRACE boilerplate.
    assert "pueue_dld.socket" in detail
    assert "RUST_BACKTRACE" not in detail


def test_meaningful_stderr_skips_backtrace_boilerplate():
    noisy = (
        "Error:\n"
        '   2: I/O error at path "/run/user/1000/pueue_dld.socket"\n'
        "Location:\n"
        "   client.rs:85\n"
        "Backtrace omitted. Run with RUST_BACKTRACE=1 environment variable.\n"
        "Run with RUST_BACKTRACE=full to include source snippets."
    )

    assert "pueue_dld.socket" in mon._meaningful_stderr(noisy)


def test_meaningful_stderr_falls_back_when_all_noise():
    """All-boilerplate stderr still yields something rather than crashing."""
    assert mon._meaningful_stderr("Run with RUST_BACKTRACE=full") != ""
    assert mon._meaningful_stderr("") == "empty output"


def test_group_check_paused(monkeypatch):
    monkeypatch.setattr(
        mon,
        "_run",
        lambda cmd: _completed(
            stdout='{"groups":{"claude-runner":{"status":"Paused"}},"tasks":{}}'
        ),
    )

    assert mon.check_pueue_group()[0] is False


def test_task_counts_parse(monkeypatch):
    monkeypatch.setattr(mon, "_run", lambda cmd: _completed(stdout=PUEUE_JSON))

    assert mon.count_active_tasks() == (1, 1)


def test_task_counts_minus_one_when_unreadable(monkeypatch):
    monkeypatch.setattr(mon, "_run", lambda cmd: _completed(stderr="boom", code=1))

    assert mon.count_active_tasks() == (-1, -1)
