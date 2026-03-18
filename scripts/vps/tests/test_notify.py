# scripts/vps/tests/test_notify.py
"""Unit tests for scripts/vps/notify.py.

Covers: send_to_project fail-closed topic routing and missing token behavior.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import notify


class TestMissingToken:
    @pytest.mark.asyncio
    async def test_send_to_project_missing_token_returns_false(self, seed_project, monkeypatch):
        """send_to_project with empty token returns False."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        result = await notify.send_to_project("testproject", "Hello")
        assert result is False


class TestTopicRouting:
    @pytest.mark.asyncio
    async def test_send_to_project_uses_explicit_topic_id(self, seed_project, monkeypatch):
        """Project with explicit topic_id routes to that topic."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        with patch("notify._send_message") as mock_send:
            mock_send.return_value = True
            result = await notify.send_to_project("testproject", "Hello")

        assert result is True
        mock_send.assert_called_once_with("Hello", thread_id=5)

    @pytest.mark.asyncio
    async def test_topic_id_1_refuses_to_send(self, isolated_db, monkeypatch):
        """topic_id=1 (General) must fail closed, not silently route there."""
        import db

        db.seed_projects_from_json([
            {"project_id": "general_proj", "path": "/tmp/gp", "topic_id": 1, "provider": "claude"},
        ])

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        with patch("notify._send_message") as mock_send:
            result = await notify.send_to_project("general_proj", "Hello")

        assert result is False
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_topic_id_refuses_to_send(self, isolated_db, monkeypatch):
        """Project without topic binding must fail closed."""
        import db

        db.seed_projects_from_json([
            {"project_id": "no_topic", "path": "/tmp/nt", "provider": "claude"},
        ])

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

        with patch("notify._send_message") as mock_send:
            result = await notify.send_to_project("no_topic", "Hello")

        assert result is False
        mock_send.assert_not_called()
