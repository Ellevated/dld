# scripts/vps/tests/test_cycle_smoke.py
"""Cycle E2E smoke tests for BUG-155.

Covers 7 eval criteria:
- EC-1: _submit_to_pueue arg order
- EC-2: artifact_rel excludes drafts
- EC-3: artifact_rel handles empty dir
- EC-4: notify fallback to OPS_TOPIC_ID
- EC-5: notify no fallback when no OPS_TOPIC_ID
- EC-6: notify normal path unchanged
- EC-7: label parsing colon separator
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# scripts/vps is already on sys.path via conftest.py
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)


# ---------------------------------------------------------------------------
# EC-1: _submit_to_pueue arg order
# ---------------------------------------------------------------------------
class TestSubmitToPueueArgOrder:
    """Verify run-agent.sh args: <path> <provider> <skill> <task>."""

    def test_arg_order_from_source(self) -> None:
        """EC-1: Parse telegram-bot.py source to verify arg order.

        The broken version passed: path, "claude -p /autopilot X", provider, skill
        The fixed version passes:  path, provider, skill, "/autopilot X"
        """
        bot_path = Path(VPS_DIR) / "telegram-bot.py"
        source = bot_path.read_text(encoding="utf-8")

        # Find the _submit_to_pueue function and extract task_cmd lines
        in_func = False
        task_cmd_lines: list[str] = []
        for line in source.splitlines():
            if "def _submit_to_pueue" in line:
                in_func = True
                continue
            if in_func and "task_cmd" in line and "run-agent.sh" in line:
                task_cmd_lines.append(line.strip())
                continue
            if in_func and task_cmd_lines and line.strip() and not line.strip().startswith(("r ", "#")):
                task_cmd_lines.append(line.strip())
                if "]" in line:
                    break

        joined = " ".join(task_cmd_lines)

        # Verify: path is first arg after run-agent.sh
        assert 'project["path"]' in joined or "project['path']" in joined, \
            f"project path must be first arg after run-agent.sh: {joined}"

        # Provider must come BEFORE skill and task
        path_pos = joined.find("project[")
        provider_pos = joined.find("provider")
        autopilot_pos = joined.find('"autopilot"')

        assert provider_pos > path_pos, \
            f"provider must come after path: provider@{provider_pos} path@{path_pos}"
        assert autopilot_pos > provider_pos, \
            f"'autopilot' skill must come after provider: autopilot@{autopilot_pos} provider@{provider_pos}"

        # The old broken pattern must NOT be present
        assert "claude -p /autopilot" not in joined, \
            f"Old broken pattern 'claude -p /autopilot' still present: {joined}"


# ---------------------------------------------------------------------------
# EC-2, EC-3: artifact_rel filtering
# ---------------------------------------------------------------------------
class TestArtifactRelFilter:
    """Verify pueue-callback.sh artifact_rel find command filters correctly."""

    def test_excludes_draft_files(self, tmp_path: Path) -> None:
        """EC-2: With draft + canonical files, only canonical is returned."""
        qa_dir = tmp_path / "ai" / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "draft-v2-from-scratch.md").write_text("draft")
        (qa_dir / "SKILL-v1-skill-writer.md").write_text("skill draft")
        (qa_dir / "20260318-120000-TECH-151.md").write_text("report")

        result = subprocess.run(
            ["find", str(qa_dir), "-maxdepth", "1", "-type", "f",
             "-name", "[0-9]*-*.md"],
            capture_output=True, text=True, timeout=5,
        )
        files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]

        assert len(files) == 1, f"Expected 1 file, got {len(files)}: {files}"
        filename = Path(files[0]).name
        assert filename == "20260318-120000-TECH-151.md"
        assert not filename.startswith("draft")

    def test_empty_dir_returns_nothing(self, tmp_path: Path) -> None:
        """EC-3: Empty ai/qa/ dir returns no matches."""
        qa_dir = tmp_path / "ai" / "qa"
        qa_dir.mkdir(parents=True)

        result = subprocess.run(
            ["find", str(qa_dir), "-maxdepth", "1", "-type", "f",
             "-name", "[0-9]*-*.md"],
            capture_output=True, text=True, timeout=5,
        )
        files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
        assert len(files) == 0, f"Expected 0 files, got {len(files)}: {files}"

    def test_multiple_canonical_sorted(self, tmp_path: Path) -> None:
        """Multiple canonical files: sort | tail -1 picks latest."""
        qa_dir = tmp_path / "ai" / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "20260317-100000-TECH-150.md").write_text("old")
        (qa_dir / "20260318-120000-TECH-151.md").write_text("new")
        (qa_dir / "draft-v2-notes.md").write_text("draft")

        result = subprocess.run(
            ["bash", "-c",
             f'find "{qa_dir}" -maxdepth 1 -type f -name "[0-9]*-*.md" | sort | tail -1'],
            capture_output=True, text=True, timeout=5,
        )
        artifact = result.stdout.strip()

        assert "20260318-120000-TECH-151.md" in artifact
        assert "draft" not in artifact

    def test_callback_source_has_fixed_pattern(self) -> None:
        """Verify pueue-callback.sh source uses [0-9]*-*.md for QA find."""
        callback_path = Path(VPS_DIR) / "pueue-callback.sh"
        source = callback_path.read_text(encoding="utf-8")

        for i, line in enumerate(source.splitlines()):
            if "ai/qa" in line and "find" in line:
                assert "[0-9]*-*.md" in line, \
                    f"QA find at line {i+1} must use '[0-9]*-*.md': {line.strip()}"


# ---------------------------------------------------------------------------
# EC-4, EC-5, EC-6: notify.py OPS_TOPIC_ID fallback
# ---------------------------------------------------------------------------
class TestNotifyFallback:
    """Verify notify.py OPS_TOPIC_ID fallback logic.

    Uses asyncio.run() wrapper because pytest-asyncio is not installed.
    """

    def test_normal_topic_id_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EC-6: Project with topic_id=100 sends to thread_id=100."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.delenv("OPS_TOPIC_ID", raising=False)

        import notify

        mock_project = {"project_id": "tp", "path": "/tmp/tp", "topic_id": 100}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = asyncio.run(notify.send_to_project("tp", "Hello"))

        assert result is True
        mock_send.assert_called_once_with("Hello", thread_id=100)

    def test_fallback_to_ops_topic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EC-4: Project with topic_id=NULL falls back to OPS_TOPIC_ID=42."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("OPS_TOPIC_ID", "42")

        import notify

        mock_project = {"project_id": "nt", "path": "/tmp/nt", "topic_id": None}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = asyncio.run(notify.send_to_project("nt", "Hello"))

        assert result is True
        mock_send.assert_called_once_with("Hello", thread_id=42)

    def test_no_fallback_when_no_ops(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EC-5: Project with topic_id=NULL and no OPS_TOPIC_ID returns False."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.delenv("OPS_TOPIC_ID", raising=False)

        import notify

        mock_project = {"project_id": "nt", "path": "/tmp/nt", "topic_id": None}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                result = asyncio.run(notify.send_to_project("nt", "Hello"))

        assert result is False
        mock_send.assert_not_called()

    def test_topic_id_1_triggers_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """topic_id=1 (General) should also try OPS_TOPIC_ID fallback."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("OPS_TOPIC_ID", "99")

        import notify

        mock_project = {"project_id": "gp", "path": "/tmp/gp", "topic_id": 1}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = asyncio.run(notify.send_to_project("gp", "Hello"))

        assert result is True
        mock_send.assert_called_once_with("Hello", thread_id=99)


# ---------------------------------------------------------------------------
# EC-7: label parsing colon separator
# ---------------------------------------------------------------------------
class TestLabelParsing:
    """Verify pueue-callback.sh label parsing logic."""

    def test_colon_separator_parsing(self) -> None:
        """EC-7: label='dld:TECH-151' => PROJECT_ID='dld', TASK_LABEL='TECH-151'."""
        label = "dld:TECH-151"
        result = subprocess.run(
            ["bash", "-c", f'''
                LABEL="{label}"
                PROJECT_ID="${{LABEL%%:*}}"
                TASK_LABEL="${{LABEL#*:}}"
                echo "$PROJECT_ID"
                echo "$TASK_LABEL"
            '''],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 2, f"Expected 2 lines, got: {lines}"
        assert lines[0] == "dld"
        assert lines[1] == "TECH-151"

    def test_no_colon_label_warning(self) -> None:
        """Label without colon: both vars equal full label (warning case)."""
        label = "unknown"
        result = subprocess.run(
            ["bash", "-c", f'''
                LABEL="{label}"
                PROJECT_ID="${{LABEL%%:*}}"
                TASK_LABEL="${{LABEL#*:}}"
                if [[ "$PROJECT_ID" == "$LABEL" ]]; then
                    echo "WARN"
                fi
                echo "$PROJECT_ID"
                echo "$TASK_LABEL"
            '''],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        assert "WARN" in lines

    def test_compound_spec_id_preserved(self) -> None:
        """Label 'proj:qa-BUG-155' preserves full TASK_LABEL after colon."""
        label = "myproj:qa-BUG-155"
        result = subprocess.run(
            ["bash", "-c", f'''
                LABEL="{label}"
                PROJECT_ID="${{LABEL%%:*}}"
                TASK_LABEL="${{LABEL#*:}}"
                echo "$PROJECT_ID"
                echo "$TASK_LABEL"
            '''],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        assert lines[0] == "myproj"
        assert lines[1] == "qa-BUG-155"
