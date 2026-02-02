"""Tests for prompt_guard.py hook.

Tests complexity detection, skill indicators, and prompt approval logic.
"""

import json
import sys
from pathlib import Path

# Add hooks to path
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "template" / ".claude" / "hooks"),
)

from prompt_guard import main


class TestComplexityDetection:
    """Test detection of complex tasks requiring spark."""

    def test_detects_implement_feature(self, mock_stdin, capture_stdout, mock_exit):
        """Detects 'implement feature' pattern."""
        mock_stdin({"user_prompt": "implement a new authentication feature"})

        with capture_stdout() as output:
            with mock_exit():
                main()

        output_val = output.getvalue()
        assert "Complex task detected" in output_val
        assert "spark" in output_val

    def test_detects_create_endpoint(self, mock_stdin, capture_stdout, mock_exit):
        """Detects 'create endpoint' pattern."""
        mock_stdin({"user_prompt": "create a new API endpoint for users"})

        with capture_stdout() as output:
            with mock_exit():
                main()

        output_val = output.getvalue()
        assert "Complex task detected" in output_val

    def test_detects_write_function(self, mock_stdin, capture_stdout, mock_exit):
        """Detects 'write function' pattern."""
        mock_stdin({"user_prompt": "write a function to process payments"})

        with capture_stdout() as output:
            with mock_exit():
                main()

        output_val = output.getvalue()
        assert "Complex task detected" in output_val

    def test_detects_add_api(self, mock_stdin, capture_stdout, mock_exit):
        """Detects 'add api' pattern."""
        mock_stdin({"user_prompt": "add a REST API for billing"})

        with capture_stdout() as output:
            with mock_exit():
                main()

        output_val = output.getvalue()
        assert "Complex task detected" in output_val


class TestSkillIndicators:
    """Test that skill indicators bypass the complexity check."""

    def test_skips_when_spark_mentioned(self, mock_stdin, capture_stdout, mock_exit):
        """Skip check when /spark is mentioned."""
        mock_stdin({"user_prompt": "/spark implement new feature"})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1

    def test_skips_when_autopilot_mentioned(self, mock_stdin, capture_stdout, mock_exit):
        """Skip check when /autopilot is mentioned."""
        mock_stdin({"user_prompt": "/autopilot create endpoint"})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1

    def test_skips_when_audit_mentioned(self, mock_stdin, capture_stdout, mock_exit):
        """Skip check when /audit is mentioned."""
        mock_stdin({"user_prompt": "/audit write new code"})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1


class TestSimplePrompts:
    """Test that simple prompts are approved without warning."""

    def test_approves_simple_question(self, mock_stdin, capture_stdout, mock_exit):
        """Simple questions are approved."""
        mock_stdin({"user_prompt": "what does this function do?"})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1
        assert "Complex task" not in output_val

    def test_approves_fix_request(self, mock_stdin, capture_stdout, mock_exit):
        """Fix requests without 'write/create' are approved."""
        mock_stdin({"user_prompt": "fix the bug in user.py line 45"})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1
        assert "Complex task" not in output_val

    def test_approves_read_request(self, mock_stdin, capture_stdout, mock_exit):
        """Read/analyze requests are approved."""
        mock_stdin({"user_prompt": "show me the contents of config.py"})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1
        assert "Complex task" not in output_val


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_empty_prompt(self, mock_stdin, capture_stdout, mock_exit):
        """Empty prompt is approved (fail-safe)."""
        mock_stdin({"user_prompt": ""})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1

    def test_handles_missing_prompt(self, mock_stdin, capture_stdout, mock_exit):
        """Missing user_prompt key is handled gracefully."""
        mock_stdin({"some_other_key": "value"})

        with capture_stdout() as output:
            with mock_exit() as exit_mock:
                main()

        output_val = output.getvalue()
        data = json.loads(output_val) if output_val else {}
        assert data.get("decision") == "approve" or exit_mock.call_count == 1
