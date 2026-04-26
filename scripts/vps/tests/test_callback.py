# scripts/vps/tests/test_callback.py
"""Tests for callback.verify_status_sync (status auto-fix guards).

The two guards are symmetric:
  * target=done + spec=blocked  → skip (autopilot says blocked, respect it).
  * target=blocked + spec=done  → skip (final push/merge failed but work is
    on a feature branch — wiping done loses the signal).
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import callback  # noqa: E402


@pytest.fixture
def project(tmp_path):
    """Create a fake project with ai/features/<spec>.md and ai/backlog.md."""
    p = tmp_path / "proj"
    (p / "ai" / "features").mkdir(parents=True)
    return p


def _write_spec(project: Path, spec_id: str, status: str) -> Path:
    f = project / "ai" / "features" / f"{spec_id}-test.md"
    f.write_text(f"# {spec_id}\n\n**Status:** {status}\n")
    return f


def _write_backlog(project: Path, spec_id: str, status: str) -> None:
    (project / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status |\n|---|---|---|\n| {spec_id} | t | {status} |\n"
    )


# --- Guard 1: target=done + spec=blocked → skip ---


class TestDoneOverBlockedGuard:
    def test_done_target_respects_blocked_spec(self, project):
        spec = _write_spec(project, "BUG-1", "blocked")
        _write_backlog(project, "BUG-1", "blocked")
        callback.verify_status_sync(str(project), "BUG-1", target="done")
        # Spec untouched
        assert "**Status:** blocked" in spec.read_text()
        # Backlog untouched
        assert "| blocked |" in (project / "ai" / "backlog.md").read_text()


# --- Guard 2 (NEW 2026-04-25): target=blocked + spec=done → skip ---


class TestBlockedOverDoneGuard:
    def test_blocked_target_respects_done_spec(self, project):
        """Reproduces the BUG-376 / BUG-374 / BUG-865 scenario.

        Autopilot finished all per-task code, marked spec done, then the
        final merge-to-develop step failed. Pueue exit=1 → callback called
        with target=blocked. Without this guard, done was wiped and the
        feature branch was orphaned.
        """
        spec = _write_spec(project, "BUG-2", "done")
        _write_backlog(project, "BUG-2", "done")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-2", target="blocked")
        assert "**Status:** done" in spec.read_text(), "spec done preserved"
        assert "| done |" in (project / "ai" / "backlog.md").read_text(), "backlog done preserved"
        mock_push.assert_not_called(), "no auto-fix commit when guard fires"

    def test_blocked_target_still_writes_when_spec_not_done(self, project):
        """Sanity: guard only fires for done spec; other states get blocked."""
        _write_spec(project, "BUG-3", "in_progress")
        _write_backlog(project, "BUG-3", "in_progress")
        with patch("callback._git_commit_push"):
            callback.verify_status_sync(str(project), "BUG-3", target="blocked")
        assert "**Status:** blocked" in (project / "ai" / "features" / "BUG-3-test.md").read_text()


# --- Both guards: idempotent (target already matches) ---


class TestIdempotent:
    def test_already_done_no_op(self, project):
        _write_spec(project, "BUG-4", "done")
        _write_backlog(project, "BUG-4", "done")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-4", target="done")
        mock_push.assert_not_called()

    def test_already_blocked_no_op(self, project):
        _write_spec(project, "BUG-5", "blocked")
        _write_backlog(project, "BUG-5", "blocked")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-5", target="blocked")
        mock_push.assert_not_called()


# --- v3.15.6: backlog resync to spec authority on guard fire ---


class TestBacklogResyncToSpec:
    """Stop dispatch loops by syncing backlog → spec when guards fire.

    Scenario: backlog says queued/resumed, spec says blocked. Orchestrator
    sees queued, dispatches autopilot, autopilot SKIPs (inconsistency),
    callback target=done, Guard A fires. Without resync, backlog stays
    queued → next cycle dispatches again → loop ($0.30/cycle waste).
    Real case 2026-04-25: FTR-853 looped 11 times.
    """

    def test_guard_a_resyncs_backlog_when_spec_blocked(self, project):
        """target=done + spec=blocked + backlog=queued → backlog → blocked."""
        _write_spec(project, "BUG-10", "blocked")
        _write_backlog(project, "BUG-10", "queued")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-10", target="done")
        assert "| blocked |" in (project / "ai" / "backlog.md").read_text(), (
            "backlog resynced to spec's blocked"
        )
        # spec untouched
        assert "**Status:** blocked" in (project / "ai" / "features" / "BUG-10-test.md").read_text()
        mock_push.assert_called_once(), "resync should commit"

    def test_guard_a_resyncs_backlog_when_resumed(self, project):
        """Same shape with backlog=resumed (after operator resume)."""
        _write_spec(project, "BUG-11", "blocked")
        _write_backlog(project, "BUG-11", "resumed")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-11", target="done")
        assert "| blocked |" in (project / "ai" / "backlog.md").read_text()
        mock_push.assert_called_once()

    def test_guard_b_resyncs_backlog_when_spec_done(self, project):
        """target=blocked + spec=done + backlog=in_progress → backlog → done."""
        _write_spec(project, "BUG-12", "done")
        _write_backlog(project, "BUG-12", "in_progress")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-12", target="blocked")
        assert "| done |" in (project / "ai" / "backlog.md").read_text(), (
            "backlog resynced to spec's done"
        )
        # spec untouched
        assert "**Status:** done" in (project / "ai" / "features" / "BUG-12-test.md").read_text()
        mock_push.assert_called_once()

    def test_guard_a_no_commit_when_backlog_already_blocked(self, project):
        """Idempotency: guard fires but backlog already in sync → no commit."""
        _write_spec(project, "BUG-13", "blocked")
        _write_backlog(project, "BUG-13", "blocked")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-13", target="done")
        mock_push.assert_not_called()

    def test_guard_b_no_commit_when_backlog_already_done(self, project):
        """Idempotency: guard fires but backlog already in sync → no commit."""
        _write_spec(project, "BUG-14", "done")
        _write_backlog(project, "BUG-14", "done")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-14", target="blocked")
        mock_push.assert_not_called()


# --- v3.15.7: skill detection from pueue command (survives SIGKILL'd runners) ---


def _mock_pueue_status(task_id: str, command: str, start_iso: str = ""):
    """Build a MagicMock subprocess.run result for `pueue status --json`."""
    status = {"Running": {"start": start_iso}} if start_iso else {"Queued": {}}
    payload = {
        "tasks": {
            task_id: {
                "command": command,
                "original_command": command,
                "status": status,
                "label": "proj:SPEC-1",
            }
        }
    }
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps(payload)
    return m


class TestSkillFromPueueCommand:
    """Reproduce TECH-869 case: SIGKILL'd autopilot — log file is stale,
    pueue command is the only deterministic skill source."""

    def test_extracts_autopilot_from_run_agent_invocation(self):
        cmd = (
            "/home/dld/projects/dld/scripts/vps/run-agent.sh "
            "/home/dld/projects/awardybot claude autopilot /autopilot TECH-869"
        )
        with patch(
            "callback.subprocess.run",
            return_value=_mock_pueue_status("1120", cmd, "2026-04-26T17:26:08+03:00"),
        ):
            skill, start_ts = callback._skill_from_pueue_command("1120")
        assert skill == "autopilot"
        assert start_ts > 0

    def test_extracts_qa_skill(self):
        cmd = "/path/run-agent.sh /proj claude qa /qa TECH-869"
        with patch("callback.subprocess.run", return_value=_mock_pueue_status("5", cmd)):
            skill, _ = callback._skill_from_pueue_command("5")
        assert skill == "qa"

    def test_extracts_spark_skill(self):
        cmd = "/x/run-agent.sh /p claude spark /tmp/.task-cmd-X.txt"
        with patch("callback.subprocess.run", return_value=_mock_pueue_status("9", cmd)):
            skill, _ = callback._skill_from_pueue_command("9")
        assert skill == "spark"

    def test_returns_empty_on_pueue_failure(self):
        m = MagicMock()
        m.returncode = 1
        m.stderr = "daemon down"
        with patch("callback.subprocess.run", return_value=m):
            skill, ts = callback._skill_from_pueue_command("1")
        assert skill == ""
        assert ts == 0.0

    def test_returns_empty_when_command_unknown(self):
        cmd = "/some/other/script foo bar baz"
        with patch("callback.subprocess.run", return_value=_mock_pueue_status("2", cmd)):
            skill, _ = callback._skill_from_pueue_command("2")
        assert skill == ""


class TestFindLogFileFiltersStale:
    """Verify _find_log_file refuses logs older than the task's own start_ts.

    This is the actual TECH-869 fix: previously _find_log_file returned the
    latest mtime in logs/ regardless of when the current task started, so
    a SIGKILL'd run with no fresh log got the previous (qa) run's log
    mistakenly classified as autopilot's output.
    """

    def test_skips_old_logs(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        # Stale log (mtime in the past)
        old = log_dir / "proj-old.log"
        old.write_text("{}")
        import os

        os.utime(old, (1000, 1000))
        # Patch SCRIPT_DIR
        monkeypatch.setattr(callback, "SCRIPT_DIR", tmp_path)
        # Task started after mtime — old log must be skipped
        result = callback._find_log_file("proj", after_ts=2000.0)
        assert result is None

    def test_returns_log_newer_than_after_ts(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        new = log_dir / "proj-new.log"
        new.write_text("{}")
        import os

        os.utime(new, (5000, 5000))
        monkeypatch.setattr(callback, "SCRIPT_DIR", tmp_path)
        result = callback._find_log_file("proj", after_ts=2000.0)
        assert result == new

    def test_default_after_ts_zero_returns_any_log(self, tmp_path, monkeypatch):
        """Backward-compat: callers that don't pass after_ts get original behavior."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        f = log_dir / "proj-x.log"
        f.write_text("{}")
        monkeypatch.setattr(callback, "SCRIPT_DIR", tmp_path)
        result = callback._find_log_file("proj")
        assert result == f
