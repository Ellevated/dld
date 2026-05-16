"""Regression test for BUG-974: autostash silently overwrites callback Status.

End-to-end on a real temp git repo:
  1. Initial commit has spec with Status: queued.
  2. Working tree edits the same Status line locally (simulates stale local).
  3. "remote" advance commits Status: done; we fetch & expose as origin/develop.
  4. orchestrator.git_pull → stash, pull (fast-forward to done), pop.
  5. Post-recovery: working tree MUST contain Status: done (HEAD wins).
  6. AUTOSTASH_CALLBACK_RESTORE warning MUST have been logged.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ARCH-186: autostash + marker restore eliminated by lifecycle.py per-spec YAML.
# Whole module skipped — file is DELETED in Task 6 (final retirement step).
pytestmark = pytest.mark.skip(
    reason="ARCH-186: autostash + marker restore removed; file deleted in Task 6"
)

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import orchestrator  # noqa: E402

M_START = "<!-- DLD-CALLBACK-MARKER-START v1 -->"
M_END = "<!-- DLD-CALLBACK-MARKER-END -->"


def _run(cwd, *argv, check=True):
    r = subprocess.run(
        list(argv), cwd=str(cwd), capture_output=True, text=True
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"{argv} failed: {r.stderr}")
    return r


def _git_init_local_at_done(tmp_path):
    """Build remote+local both at HEAD with Status: done.

    Reproduces the incident geometry: local HEAD has the freshly-written
    callback commit (Status: done). The working tree, however, contains
    a stale Status: queued for the marker block (e.g. a manual operator
    revert, or a backlog regenerator that re-wrote the file). The next
    autostash cycle MUST detect and restore HEAD on pop.
    """
    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    _run(remote, "git", "init", "-q", "-b", "develop")
    _run(remote, "git", "config", "user.email", "t@t")
    _run(remote, "git", "config", "user.name", "t")
    spec = remote / "spec.md"
    spec.write_text(f"# Spec\n{M_START}\n**Status:** queued\n{M_END}\n")
    _run(remote, "git", "add", "spec.md")
    _run(remote, "git", "commit", "-q", "-m", "initial: queued")
    spec.write_text(f"# Spec\n{M_START}\n**Status:** done\n{M_END}\n")
    _run(remote, "git", "add", "spec.md")
    _run(remote, "git", "commit", "-q", "-m", "callback: Status -> done")
    _run(tmp_path, "git", "clone", "-q", "-b", "develop", str(remote), str(local))
    _run(local, "git", "config", "user.email", "t@t")
    _run(local, "git", "config", "user.name", "t")
    return local


def test_git_pull_restores_callback_marker_after_clean_pop(tmp_path):
    local = _git_init_local_at_done(tmp_path)
    spec = local / "spec.md"
    # Working tree reverts Status to queued (the incident's dirty state).
    spec.write_text(
        f"# Spec EDITED\n{M_START}\n**Status:** queued\n{M_END}\n"
    )

    with patch.object(orchestrator, "is_agent_running", return_value=False):
        with patch.object(orchestrator, "log") as log_mock:
            orchestrator.git_pull("testproject", str(local))

    # Working tree must reflect HEAD's authoritative Status: done.
    final = spec.read_text()
    assert "**Status:** done" in final, f"Status not restored: {final!r}"
    assert "**Status:** queued" not in final, f"Stale Status leaked: {final!r}"

    # User-owned prose outside markers must be preserved.
    assert "# Spec EDITED" in final

    # Recovery warning emitted.
    warned_msgs = [
        (c.args[0] if c.args else "") for c in log_mock.warning.call_args_list
    ]
    assert any(
        "AUTOSTASH_CALLBACK_RESTORE" in str(m) for m in warned_msgs
    ), f"missing AUTOSTASH_CALLBACK_RESTORE warning; got: {warned_msgs}"


def test_git_pull_no_op_when_no_markers(tmp_path):
    """File without DLD-CALLBACK-MARKER blocks must not be rewritten,
    even if it has diff vs HEAD after pop."""
    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    _run(remote, "git", "init", "-q", "-b", "develop")
    _run(remote, "git", "config", "user.email", "t@t")
    _run(remote, "git", "config", "user.name", "t")
    plain = remote / "notes.md"
    plain.write_text("hello\n")
    _run(remote, "git", "add", "notes.md")
    _run(remote, "git", "commit", "-q", "-m", "init")
    _run(tmp_path, "git", "clone", "-q", "-b", "develop", str(remote), str(local))
    _run(local, "git", "config", "user.email", "t@t")
    _run(local, "git", "config", "user.name", "t")
    # Advance remote.
    plain.write_text("hello from remote\n")
    _run(remote, "git", "add", "notes.md")
    _run(remote, "git", "commit", "-q", "-m", "remote edit")
    # Local dirty edit, no markers anywhere.
    (local / "notes.md").write_text("hello local\n")

    with patch.object(orchestrator, "is_agent_running", return_value=False):
        with patch.object(orchestrator, "log") as log_mock:
            orchestrator.git_pull("testproject", str(local))

    # No AUTOSTASH_CALLBACK_RESTORE warning for plain files.
    msgs = [str(c.args[0] if c.args else "") for c in log_mock.warning.call_args_list]
    assert not any("AUTOSTASH_CALLBACK_RESTORE" in m for m in msgs), (
        f"unexpected restore on plain file: {msgs}"
    )


@pytest.fixture(autouse=True)
def _require_git():
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
    except Exception:
        pytest.skip("git not available")
