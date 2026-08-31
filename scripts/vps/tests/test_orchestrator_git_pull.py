# scripts/vps/tests/test_orchestrator_git_pull.py
"""Unit tests for orchestrator.git_pull (fetch + ff-only-merge, FETCH_HEAD-race safe).

Guarantees:
  - On any working tree state: exactly one `fetch origin develop` followed by
    exactly one `merge --ff-only origin/develop` (no dirty check, no stash,
    no pop, no autostash, no plain `pull`).
  - Merge target is the tracking ref `origin/develop`, NEVER FETCH_HEAD — this
    is the fix for the gate-daemon/orchestrator FETCH_HEAD race that produced
    "Cannot fast-forward to multiple branches".
  - On fetch failure: warning logged, merge NOT attempted, no exception.
  - On merge failure: warning logged, no exception raised.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import orchestrator  # noqa: E402
import orchestrator_git  # noqa: E402


def _mk_run(returncode: int = 0):
    """Return a fake subprocess.run that always returns given returncode."""

    def _run(argv, *args, **kwargs):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = ""
        result.stderr = ""
        return result

    return _run


def _mk_run_by_cmd(rc_fetch: int = 0, rc_merge: int = 0):
    """Fake subprocess.run with per-subcommand return codes (fetch vs merge)."""

    def _run(argv, *args, **kwargs):
        result = MagicMock()
        result.stdout = ""
        result.stderr = ""
        if "fetch" in argv:
            result.returncode = rc_fetch
        elif "merge" in argv:
            result.returncode = rc_merge
        else:
            result.returncode = 0
        return result

    return _run


def _invocations(run_mock):
    return [
        " ".join(str(x) for x in c.args[0])
        for c in run_mock.call_args_list
        if c.args and isinstance(c.args[0], list)
    ]


class TestGitPullFetchThenMerge:
    """git_pull runs fetch + ff-only merge from the tracking ref."""

    def test_runs_fetch_then_ff_only_merge(self, tmp_path):
        """Exactly one `fetch origin develop` then one `merge --ff-only origin/develop`."""
        (tmp_path / ".git").mkdir()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_mk_run(0)) as run_mock,
            patch("orchestrator.log"),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        invocations = _invocations(run_mock)

        fetches = [inv for inv in invocations if " fetch " in f" {inv} "]
        merges = [inv for inv in invocations if " merge " in f" {inv} "]
        assert len(fetches) == 1, f"expected 1 fetch, got {fetches}"
        assert "origin develop" in fetches[0]
        assert len(merges) == 1, f"expected 1 merge, got {merges}"
        assert "--ff-only" in merges[0]

        # fetch must precede merge
        assert invocations.index(fetches[0]) < invocations.index(merges[0])

        # Forbidden under any branch
        for inv in invocations:
            assert "autostash" not in inv, f"autostash leaked: {inv}"
            assert "rebase" not in inv, f"rebase leaked: {inv}"
            assert "stash" not in inv, f"stash leaked: {inv}"
            assert " pull " not in f" {inv} ", f"plain pull leaked: {inv}"

    def test_merge_target_is_tracking_ref_not_fetch_head(self, tmp_path):
        """Regression (FETCH_HEAD race): merge targets origin/develop, not FETCH_HEAD."""
        (tmp_path / ".git").mkdir()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_mk_run(0)) as run_mock,
            patch("orchestrator.log"),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        invocations = _invocations(run_mock)
        merges = [inv for inv in invocations if " merge " in f" {inv} "]
        assert len(merges) == 1
        assert "origin/develop" in merges[0], f"merge must target tracking ref: {merges[0]}"
        for inv in invocations:
            assert "FETCH_HEAD" not in inv, f"FETCH_HEAD must never be a merge target: {inv}"

    def test_fetch_failure_skips_merge_logs_warning(self, tmp_path):
        """Fetch non-zero → warning logged, merge NOT attempted, no raise."""
        (tmp_path / ".git").mkdir()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch(
                "orchestrator.subprocess.run",
                side_effect=_mk_run_by_cmd(rc_fetch=1, rc_merge=0),
            ) as run_mock,
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))  # must not raise

        invocations = _invocations(run_mock)
        assert log_mock.warning.called
        merges = [inv for inv in invocations if " merge " in f" {inv} "]
        assert merges == [], f"merge must be skipped after fetch failure: {merges}"

    def test_merge_failure_logs_warning_no_raise(self, tmp_path):
        """Fetch ok, merge non-zero (divergence) → warning logged, no exception.

        The merge-failure branch logs through orchestrator_git, which owns the
        consecutive-failure bookkeeping; fetch failures still log from here.
        """
        (tmp_path / ".git").mkdir()
        orchestrator_git._GIT_ADVANCE_FAILURES.clear()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch(
                "orchestrator.subprocess.run",
                side_effect=_mk_run_by_cmd(rc_fetch=0, rc_merge=1),
            ),
            patch("orchestrator.log"),
            patch("orchestrator_git.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))  # must not raise

        assert log_mock.warning.called

    def test_no_dirty_check_no_diff_calls(self, tmp_path):
        """No `git diff` calls — dirty check removed (post-ARCH-186)."""
        (tmp_path / ".git").mkdir()

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_mk_run(0)) as run_mock,
            patch("orchestrator.log"),
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        for inv in _invocations(run_mock):
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


class TestStuckProjectEscalates:
    """A project that cannot fast-forward for several cycles must say so at ERROR.

    dowry stopped receiving prompts and specs on 2026-08-31 because a job kept
    rewriting a tracked generated file; the only signal was one WARNING per
    five-minute cycle, which reads exactly like a healthy log.
    """

    def _run_cycles(self, tmp_path, n, project="stuckproject"):
        (tmp_path / ".git").mkdir(exist_ok=True)
        stderr = (
            "error: Your local changes to the following files would be overwritten by merge:\n"
            "\t.claude/rules/generated/schema.md\nAborting\n"
        )

        def _run(argv, *args, **kwargs):
            result = MagicMock()
            result.stdout = ""
            result.stderr = "" if "fetch" in argv else stderr
            result.returncode = 0 if "fetch" in argv else 1
            return result

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_run),
            patch("orchestrator.log"),
            patch("orchestrator_git.log") as log_mock,
        ):
            for _ in range(n):
                orchestrator.git_pull(project, str(tmp_path))
        return log_mock

    def setup_method(self):
        orchestrator_git._GIT_ADVANCE_FAILURES.clear()

    def test_first_failures_are_warnings(self, tmp_path):
        log_mock = self._run_cycles(tmp_path, 2)
        assert log_mock.error.call_count == 0
        assert log_mock.warning.call_count == 2

    def test_third_consecutive_failure_escalates_to_error(self, tmp_path):
        log_mock = self._run_cycles(tmp_path, 3)
        assert log_mock.error.call_count == 1
        message = log_mock.error.call_args.args[0] % log_mock.error.call_args.args[1:]
        assert "NO updates" in message
        assert "schema.md" in message, "the blocking file must survive into the log line"

    def test_success_resets_the_counter(self, tmp_path):
        self._run_cycles(tmp_path, 2)
        (tmp_path / ".git").mkdir(exist_ok=True)
        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=_mk_run(0)),
            patch("orchestrator.log"),
        ):
            orchestrator.git_pull("stuckproject", str(tmp_path))
        assert "stuckproject" not in orchestrator_git._GIT_ADVANCE_FAILURES

    def test_stderr_is_collapsed_to_one_line(self):
        assert orchestrator_git._one_line("a\nb\n\nc") == "a | b | c"
        assert orchestrator_git._one_line(None) == ""
