"""Tests for .claude/hooks/pre_bash.py"""

import json
import sys
from pathlib import Path

# Import after adding hooks to path
sys.path.insert(0, str(Path(__file__).parent.parent / "template" / ".claude" / "hooks"))
from pre_bash import main


class TestBlockedPatterns:
    """Tests for hard-blocked commands."""

    def test_blocks_push_to_main(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git push origin main'."""
        mock_stdin({"tool_input": {"command": "git push origin main"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Push to main blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "PR workflow" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_push_main_different_format(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git push main' without origin."""
        mock_stdin({"tool_input": {"command": "git push main"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Push to main blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_git_clean_fd(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git clean -fd' (destructive)."""
        mock_stdin({"tool_input": {"command": "git clean -fd"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "git clean -fd blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert (
            "Destroys untracked files" in result["hookSpecificOutput"]["permissionDecisionReason"]
        )

    def test_blocks_git_clean_df(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git clean -df' (alternate order)."""
        mock_stdin({"tool_input": {"command": "git clean -df"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "git clean -fd blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_git_clean_dry_run(self, mock_stdin, mock_exit):
        """Should allow 'git clean -fdn' (dry-run with -n)."""
        mock_stdin({"tool_input": {"command": "git clean -fdn"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_allows_git_clean_dfn(self, mock_stdin, mock_exit):
        """Should allow 'git clean -dfn' (alternate order)."""
        mock_stdin({"tool_input": {"command": "git clean -dfn"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_blocks_git_reset_hard(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git reset --hard'."""
        mock_stdin({"tool_input": {"command": "git reset --hard HEAD~1"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert (
            "git reset --hard blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]
        )
        assert "Wipes uncommitted work" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_blocks_force_push_to_develop(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git push -f origin develop'."""
        mock_stdin({"tool_input": {"command": "git push -f origin develop"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert (
            "Force push to protected branch blocked"
            in result["hookSpecificOutput"]["permissionDecisionReason"]
        )
        assert (
            "Protected: develop, main" in result["hookSpecificOutput"]["permissionDecisionReason"]
        )

    def test_blocks_force_push_to_main(self, mock_stdin, capture_stdout, mock_exit):
        """Should block 'git push --force origin main' (caught by push to main rule)."""
        mock_stdin({"tool_input": {"command": "git push --force origin main"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        # Note: This is caught by "push to main" pattern (checked first)
        assert "Push to main blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_force_push_to_feature_branch(self, mock_stdin, mock_exit):
        """Should allow 'git push -f origin feature/FTR-100'."""
        mock_stdin({"tool_input": {"command": "git push -f origin feature/FTR-100"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)


class TestMergePatterns:
    """Tests for merge workflow enforcement."""

    def test_asks_confirmation_for_merge_without_ff_only(
        self, mock_stdin, capture_stdout, mock_exit
    ):
        """Should ask confirmation for 'git merge feature/branch' without --ff-only."""
        mock_stdin({"tool_input": {"command": "git merge feature/FTR-100"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert (
            "Use --ff-only for merges" in result["hookSpecificOutput"]["permissionDecisionReason"]
        )
        assert "Rebase-first workflow" in result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_allows_merge_with_ff_only(self, mock_stdin, mock_exit):
        """Should allow 'git merge --ff-only feature/branch'."""
        mock_stdin({"tool_input": {"command": "git merge --ff-only feature/FTR-100"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)


class TestAllowedCommands:
    """Tests for commands that should pass through."""

    def test_allows_git_status(self, mock_stdin, mock_exit):
        """Should allow 'git status'."""
        mock_stdin({"tool_input": {"command": "git status"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_allows_git_diff(self, mock_stdin, mock_exit):
        """Should allow 'git diff'."""
        mock_stdin({"tool_input": {"command": "git diff HEAD~1"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_allows_git_push_to_develop(self, mock_stdin, mock_exit):
        """Should allow normal push to develop."""
        mock_stdin({"tool_input": {"command": "git push origin develop"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_allows_git_checkout(self, mock_stdin, mock_exit):
        """Should allow 'git checkout -b feature/FTR-100'."""
        mock_stdin({"tool_input": {"command": "git checkout -b feature/FTR-100"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_allows_non_git_commands(self, mock_stdin, mock_exit):
        """Should allow non-git commands like 'ls -la'."""
        mock_stdin({"tool_input": {"command": "ls -la"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_allows_pytest(self, mock_stdin, mock_exit):
        """Should allow 'pytest' command."""
        mock_stdin({"tool_input": {"command": "pytest tests/"}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_command(self, mock_stdin, mock_exit):
        """Should allow empty command."""
        mock_stdin({"tool_input": {"command": ""}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_handles_missing_command(self, mock_stdin, mock_exit):
        """Should allow when command key is missing."""
        mock_stdin({"tool_input": {}})

        with mock_exit() as exit_mock:
            main()

        exit_mock.assert_called_once_with(0)

    def test_case_insensitive_matching(self, mock_stdin, capture_stdout, mock_exit):
        """Should match patterns case-insensitively."""
        # Uppercase GIT should still be blocked
        mock_stdin({"tool_input": {"command": "GIT PUSH ORIGIN MAIN"}})

        with mock_exit():
            with capture_stdout() as output:
                main()

        result = json.loads(output.getvalue())
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Push to main blocked" in result["hookSpecificOutput"]["permissionDecisionReason"]
