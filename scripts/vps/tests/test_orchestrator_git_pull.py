# scripts/vps/tests/test_orchestrator_git_pull.py
"""Unit tests for orchestrator.git_pull (TECH-182).

Guarantees:
  - On dirty working tree: pull is SKIPPED (no fetch, no rebase, no autostash).
  - On clean working tree: exactly one `pull --ff-only origin develop` runs.
  - No `rebase --autostash` is ever invoked under any branch.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import orchestrator  # noqa: E402


def _mk_run(returncodes_by_args):
    """Return a fake subprocess.run that picks return code by argv signature.

    `returncodes_by_args` is a list of (substring_marker, returncode) tuples
    matched against ' '.join(argv). First substring hit wins.
    """

    def _run(argv, *args, **kwargs):
        argv_str = " ".join(str(x) for x in argv)
        rc = 0
        for marker, ret in returncodes_by_args:
            if marker in argv_str:
                rc = ret
                break
        result = MagicMock()
        result.returncode = rc
        result.stdout = ""
        result.stderr = ""
        return result

    return _run


class TestGitPullDirtyTree:
    """When working tree has uncommitted changes: pull MUST be skipped."""

    def test_dirty_unstaged_skips_pull(self, tmp_path):
        """`diff` returns 1 (dirty unstaged) → no fetch, no rebase, log warning."""
        # Make project_dir look like a git repo
        (tmp_path / ".git").mkdir()

        # diff non-zero → dirty; diff --cached zero → no staged
        fake_run = _mk_run(
            [
                ("diff --cached", 0),  # staged clean
                ("diff", 1),  # unstaged dirty (must come AFTER --cached marker)
            ]
        )

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=fake_run) as run_mock,
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        # Collect every git invocation
        invocations = [
            " ".join(str(x) for x in c.args[0])
            for c in run_mock.call_args_list
            if c.args and isinstance(c.args[0], list)
        ]

        # Sanity: at minimum the two `diff` checks ran
        assert any("diff --quiet" in inv and "--cached" not in inv for inv in invocations)
        assert any("diff --cached" in inv for inv in invocations)

        # Forbidden tokens — these MUST NOT appear as git subcommands
        # Use word-boundary pattern to avoid matching path components.
        for inv in invocations:
            assert "autostash" not in inv, f"autostash leaked into call: {inv}"
            assert "rebase" not in inv, f"rebase leaked into call: {inv}"
            assert "fetch" not in inv, f"fetch leaked into call: {inv}"
            assert " pull " not in f" {inv} ", f"pull leaked into call (dirty tree): {inv}"

        # And the warning MUST have been emitted
        assert log_mock.warning.called, "expected log.warning on dirty tree"
        warning_args = log_mock.warning.call_args
        # First positional arg is the format string
        fmt = warning_args.args[0] if warning_args.args else ""
        assert "dirty" in fmt or "skipped" in fmt, f"unexpected warning fmt: {fmt}"

    def test_dirty_staged_only_skips_pull(self, tmp_path):
        """`diff --cached` returns 1 (dirty staged) → still skipped."""
        (tmp_path / ".git").mkdir()
        fake_run = _mk_run(
            [
                ("diff --cached", 1),  # staged dirty
                ("diff", 0),  # unstaged clean
            ]
        )
        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=fake_run) as run_mock,
            patch("orchestrator.log") as log_mock,
        ):
            orchestrator.git_pull("testproject", str(tmp_path))

        invocations = [
            " ".join(str(x) for x in c.args[0])
            for c in run_mock.call_args_list
            if c.args and isinstance(c.args[0], list)
        ]
        for inv in invocations:
            assert "autostash" not in inv
            assert "rebase" not in inv
            assert "fetch" not in inv
            assert " pull " not in f" {inv} "

        assert log_mock.warning.called


class TestGitPullCleanTree:
    """When working tree is clean: exactly one `pull --ff-only` runs."""

    def test_clean_tree_runs_ff_only(self, tmp_path):
        (tmp_path / ".git").mkdir()
        # Both diff probes return 0 → clean
        fake_run = _mk_run([("diff", 0)])

        with (
            patch("orchestrator.is_agent_running", return_value=False),
            patch("orchestrator.subprocess.run", side_effect=fake_run) as run_mock,
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
            assert "autostash" not in inv
            assert "--rebase" not in inv  # we no longer use --rebase variant


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
