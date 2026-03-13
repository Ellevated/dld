# scripts/vps/tests/test_approve_handler.py
"""Unit tests for scripts/vps/approve_handler.py.

Covers: _update_spec_status regex replace, handle_spec_approve (draft -> queued),
handle_spec_rework (MAX_REWORK_ITERATIONS guard), handle_spec_reject,
_write_finding_to_inbox.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import approve_handler
from approve_handler import (
    MAX_REWORK_ITERATIONS,
    _update_spec_status,
    _write_finding_to_inbox,
    handle_spec_approve,
    handle_spec_rework,
    handle_spec_reject,
)


def _create_spec_file(project_dir: Path, spec_id: str, status: str = "draft") -> Path:
    """Helper: create a minimal spec file in ai/features/."""
    features = project_dir / "ai" / "features"
    features.mkdir(parents=True, exist_ok=True)
    spec_file = features / f"{spec_id}-2026-03-12-test-spec.md"
    spec_file.write_text(
        f"# Feature: [{spec_id}] Test Spec\n"
        f"**Status:** {status} | **Priority:** P1 | **Date:** 2026-03-12\n"
        f"\n## Scope\nTest scope\n",
        encoding="utf-8",
    )
    return spec_file


def _create_backlog(project_dir: Path, spec_id: str, status: str = "draft") -> Path:
    """Helper: create a minimal backlog file."""
    ai_dir = project_dir / "ai"
    ai_dir.mkdir(parents=True, exist_ok=True)
    backlog = ai_dir / "backlog.md"
    backlog.write_text(
        f"| {spec_id} | Test Spec | {status} |\n",
        encoding="utf-8",
    )
    return backlog


def _make_callback_query(callback_data: str, message_thread_id: int = 5) -> MagicMock:
    """Helper: build a mock Update with CallbackQuery."""
    query = MagicMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.message_thread_id = message_thread_id

    update = MagicMock()
    update.callback_query = query
    return update


def _make_context(bot_data: dict | None = None) -> MagicMock:
    """Helper: build a mock Context with bot_data."""
    context = MagicMock()
    context.bot_data = bot_data if bot_data is not None else {}
    return context


# --- EC-11: _update_spec_status regex replace ---

class TestUpdateSpecStatus:
    def test_updates_spec_status(self, tmp_path):
        """EC-11: _update_spec_status changes Status in spec file."""
        spec_file = _create_spec_file(tmp_path, "FTR-200", "draft")
        _create_backlog(tmp_path, "FTR-200", "draft")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = _update_spec_status(str(tmp_path), "FTR-200", "queued")

        assert result is True

        content = spec_file.read_text(encoding="utf-8")
        assert "**Status:** queued" in content
        assert "**Status:** draft" not in content

    def test_updates_backlog_status(self, tmp_path):
        """EC-11: _update_spec_status also changes Status in backlog."""
        _create_spec_file(tmp_path, "FTR-201", "draft")
        backlog = _create_backlog(tmp_path, "FTR-201", "draft")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _update_spec_status(str(tmp_path), "FTR-201", "queued")

        bl_content = backlog.read_text(encoding="utf-8")
        assert "queued" in bl_content

    def test_calls_git_add_commit_push(self, tmp_path):
        """_update_spec_status runs git add, commit, push."""
        _create_spec_file(tmp_path, "FTR-202", "draft")
        _create_backlog(tmp_path, "FTR-202", "draft")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            _update_spec_status(str(tmp_path), "FTR-202", "queued")

        assert mock_run.call_count == 3
        git_cmds = [call.args[0][1] for call in mock_run.call_args_list]
        assert git_cmds == ["add", "commit", "push"]

    def test_spec_not_found_returns_false(self, tmp_path):
        """_update_spec_status returns False if spec file not found."""
        (tmp_path / "ai" / "features").mkdir(parents=True, exist_ok=True)
        result = _update_spec_status(str(tmp_path), "NONEXIST-999", "queued")
        assert result is False


# --- EC-9: handle_spec_rework iteration limit ---

class TestSpecRework:
    @pytest.mark.asyncio
    async def test_rework_within_limit(self, seed_project):
        """First rework attempt asks for comment (within MAX_REWORK_ITERATIONS)."""
        update = _make_callback_query("spec_rework:testproject:FTR-300")
        context = _make_context()

        await handle_spec_rework(update, context)

        query = update.callback_query
        query.answer.assert_awaited_once()
        call_text = query.edit_message_text.call_args[0][0]
        assert "напиши что доработать" in call_text
        assert context.bot_data["rework_count:testproject:FTR-300"] == 1

    @pytest.mark.asyncio
    async def test_rework_exceeds_limit_blocks(self, seed_project):
        """EC-9: 4th rework attempt (count > MAX_REWORK_ITERATIONS=3) blocks spec."""
        update = _make_callback_query("spec_rework:testproject:FTR-301")
        context = _make_context({"rework_count:testproject:FTR-301": 3})

        with patch("approve_handler._update_spec_status") as mock_update:
            mock_update.return_value = True
            await handle_spec_rework(update, context)

        query = update.callback_query
        call_text = query.edit_message_text.call_args[0][0]
        assert "лимит доработок" in call_text
        assert str(MAX_REWORK_ITERATIONS) in call_text
        assert "заблокирована" in call_text
        assert context.bot_data["rework_count:testproject:FTR-301"] == 4


# --- Finding inbox ---

class TestWriteFindingToInbox:
    def test_write_finding_creates_file(self, tmp_path):
        """_write_finding_to_inbox creates inbox file with correct content."""
        project = {"path": str(tmp_path)}
        finding = {
            "id": 42,
            "summary": "Unused import in db.py",
            "severity": "low",
            "confidence": "high",
            "file_path": "scripts/vps/db.py",
            "line_range": "10-12",
            "suggestion": "Remove unused import os",
        }

        _write_finding_to_inbox(project, finding)

        inbox = tmp_path / "ai" / "inbox"
        files = list(inbox.glob("*-night-finding-42.md"))
        assert len(files) == 1

        content = files[0].read_text(encoding="utf-8")
        assert "Finding: Unused import in db.py" in content
        assert "Route: spark_bug" in content
        assert "Status: new" in content
        assert "Severity: low" in content
        assert "File: scripts/vps/db.py" in content
        assert "Lines: 10-12" in content
        assert "Remove unused import os" in content
