# scripts/vps/tests/test_orchestrator_git_pull.py
"""Unit tests for orchestrator.git_pull (post-ARCH-186 ff-only-or-skip).

Guarantees (post-ARCH-186):
  - On any working tree state: exactly one `pull --ff-only origin develop` runs
    (no dirty check, no stash, no pop, no autostash).
  - On pull failure: warning logged, no exception raised.
  - No `autostash`, no `rebase`, no `fetch`, no `stash` ever invoked.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import orchestrator  # noqa: E402


def _mk_run(returncode: int = 0):
    """Return a fake subprocess.run that always returns given returncode."""

    def _run(argv, *args, **kwargs):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = ""
        result.stderr = ""
        return result

    return _run


class TestGitPullFfOnly:
    """Post-ARCH-186: git_pull always runs ff-only, no dirty-tree check."""

    def test_runs_ff_only_pull(self, tmp_path):
        """Always runs exactly one `pull --ff-only origin develop`."""
        (tmp_path / ".git").mkdir()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_mk_run(0)) as run_mock,
            patch("orchestrator.log"),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        invocations = [
            " ".join(str(x) for x in c.args[0])
            for c in run_mock.call_args_list
            if c.args and isinstance(c.args[0], list)
        ]

        # Exactly one pull, with --ff-only
        pulls = [inv for inv in invocations if " pull " in f" {inv} "]
        assert len(pulls) == 1, f"expected 1 pull, got {pulls}"
        assert "--ff-only" in pulls[0]
        assert "origin develop" in pulls[0]

        # Forbidden under any branch
        for inv in invocations:
            assert "autostash" not in inv, f"autostash leaked: {inv}"
            assert "rebase" not in inv, f"rebase leaked: {inv}"
            assert "fetch" not in inv, f"fetch leaked: {inv}"
            assert "stash" not in inv, f"stash leaked: {inv}"

    def test_pull_failure_logs_warning_no_raise(self, tmp_path):
        """If ff-only pull fails (non-zero exit), warning is logged, no exception."""
        (tmp_path / ".git").mkdir()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_mk_run(1)),
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))  # must not raise

        assert log_mock.warning.called

    def test_no_dirty_check_no_diff_calls(self, tmp_path):
        """Post-ARCH-186: no `git diff` calls — dirty check removed."""
        (tmp_path / ".git").mkdir()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_mk_run(0)) as run_mock,
            patch("orchestrator.log"),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        invocations = [
            " ".join(str(x) for x in c.args[0])
            for c in run_mock.call_args_list
            if c.args and isinstance(c.args[0], list)
        ]

        # No diff probes
        for inv in invocations:
            assert " diff " not in f" {inv} ", f"unexpected diff call: {inv}"


class TestGitPullSkipped:
    """Pre-conditions short-circuit before subprocess is touched."""

    def test_no_git_dir_returns_early(self, tmp_path):
        """No .git/ directory → return without touching subprocess."""
        with (
            patch("orchestrator.subprocess.run") as run_mock,
            patch("orchestrator.is_agent_running", return_value=False),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))
        run_mock.assert_not_called()

    def test_agent_running_returns_early(self, tmp_path):
        """Agent already running → log info + return."""
        (tmp_path / ".git").mkdir()
        with (
            patch("orchestrator.is_agent_running", return_value=True),
            patch("orchestrator.subprocess.run") as run_mock,
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))
        run_mock.assert_not_called()
        assert log_mock.info.called
