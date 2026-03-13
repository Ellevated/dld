# scripts/vps/tests/test_notify.py
"""Unit tests for scripts/vps/notify.py.

Covers: send_to_project (topic routing), send_spec_approval (keyboard structure,
callback_data format, title dedup), missing token returns False.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import notify


# --- EC-7: send_spec_approval keyboard structure ---

class TestSendSpecApproval:
    @pytest.mark.asyncio
    async def test_keyboard_has_three_buttons(self, seed_project, monkeypatch):
        """EC-7: send_spec_approval creates keyboard with 3 buttons, correct callback_data."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        captured_kwargs = {}

        async def mock_send_message(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = mock_send_message
        mock_bot_instance.shutdown = AsyncMock()

        with patch("telegram.Bot", return_value=mock_bot_instance):
            result = await notify.send_spec_approval(
                project_id="testproject",
                spec_id="FTR-100",
                title="Test Feature",
                problem="Fix the bug",
                tasks_count=3,
            )

        assert result is True
        assert "reply_markup" in captured_kwargs

        keyboard = captured_kwargs["reply_markup"]
        rows = keyboard.inline_keyboard
        assert len(rows) == 1, "Should have exactly 1 row"

        buttons = rows[0]
        assert len(buttons) == 3, "Should have exactly 3 buttons"

        assert buttons[0].callback_data == "spec_approve:testproject:FTR-100"
        assert buttons[1].callback_data == "spec_rework:testproject:FTR-100"
        assert buttons[2].callback_data == "spec_reject:testproject:FTR-100"

    @pytest.mark.asyncio
    async def test_title_dedup_removes_spec_prefix(self, seed_project, monkeypatch):
        """Title dedup: removes 'Feature: [FTR-100] ' prefix from title."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        captured_kwargs = {}

        async def mock_send_message(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = mock_send_message
        mock_bot_instance.shutdown = AsyncMock()

        with patch("telegram.Bot", return_value=mock_bot_instance):
            await notify.send_spec_approval(
                project_id="testproject",
                spec_id="FTR-100",
                title="Feature: [FTR-100] Great Feature",
                problem="Details here",
                tasks_count=2,
            )

        text = captured_kwargs["text"]
        assert "Feature: [FTR-100]" not in text
        assert "FTR-100" in text
        assert "Great Feature" in text


# --- EC-8: send_spec_approval missing token ---

class TestMissingToken:
    @pytest.mark.asyncio
    async def test_missing_token_returns_false(self, seed_project, monkeypatch):
        """EC-8: Empty TELEGRAM_BOT_TOKEN returns False, no crash."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        result = await notify.send_spec_approval(
            project_id="testproject",
            spec_id="FTR-100",
            title="Test",
            problem="Details",
            tasks_count=1,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_to_project_missing_token_returns_false(self, seed_project, monkeypatch):
        """send_to_project with empty token returns False."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        result = await notify.send_to_project("testproject", "Hello")
        assert result is False


# --- Topic routing ---

class TestTopicRouting:
    @pytest.mark.asyncio
    async def test_topic_id_1_sends_to_general(self, isolated_db, monkeypatch):
        """topic_id=1 is General topic bug -- should pass thread_id=None."""
        import db

        db.seed_projects_from_json([
            {"project_id": "general_proj", "path": "/tmp/gp", "topic_id": 1, "provider": "claude"},
        ])

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        captured_kwargs = {}

        async def mock_send_message(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = mock_send_message
        mock_bot_instance.shutdown = AsyncMock()

        with patch("telegram.Bot", return_value=mock_bot_instance):
            result = await notify.send_to_project("general_proj", "Hello")

        assert result is True
        assert captured_kwargs.get("message_thread_id") is None
