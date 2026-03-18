# scripts/vps/tests/test_approve_handler.py
"""Unit tests for scripts/vps/approve_handler.py.

Covers: finding approve/reject callbacks and evening review toggles.
Legacy spec approval path was removed in north-star flow.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import approve_handler
from approve_handler import (
    handle_approve_all,
    handle_finding_approve,
    handle_finding_reject,
    handle_launch_review,
    handle_project_toggle,
    handle_reject_all,
)


def _make_callback_query(callback_data: str) -> MagicMock:
    query = MagicMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()

    update = MagicMock()
    update.callback_query = query
    return update


def _make_context(bot_data: dict | None = None) -> MagicMock:
    context = MagicMock()
    context.bot_data = bot_data if bot_data is not None else {}
    return context


class TestFindingCallbacks:
    @pytest.mark.asyncio
    async def test_handle_finding_approve_updates_db(self, monkeypatch):
        update = _make_callback_query("approve_finding:42")
        context = _make_context()

        called = {}
        monkeypatch.setattr(approve_handler.db, "update_finding_status", lambda fid, status: called.update(fid=fid, status=status))

        await handle_finding_approve(update, context)

        update.callback_query.answer.assert_awaited_once()
        assert called == {"fid": 42, "status": "approved"}
        update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_finding_reject_updates_db(self, monkeypatch):
        update = _make_callback_query("reject_finding:7")
        context = _make_context()

        called = {}
        monkeypatch.setattr(approve_handler.db, "update_finding_status", lambda fid, status: called.update(fid=fid, status=status))

        await handle_finding_reject(update, context)

        assert called == {"fid": 7, "status": "rejected"}
        update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_approve_all_approves_all_sent_findings(self, monkeypatch):
        update = _make_callback_query("approve_all:testproject")
        context = _make_context()

        monkeypatch.setattr(approve_handler.db, "get_all_findings", lambda pid, status=None: [{"id": 1}, {"id": 2}])
        seen = []
        monkeypatch.setattr(approve_handler.db, "update_finding_status", lambda fid, status: seen.append((fid, status)))

        await handle_approve_all(update, context)

        assert seen == [(1, "approved"), (2, "approved")]
        update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_reject_all_rejects_all_sent_findings(self, monkeypatch):
        update = _make_callback_query("reject_all:testproject")
        context = _make_context()

        monkeypatch.setattr(approve_handler.db, "get_all_findings", lambda pid, status=None: [{"id": 3}, {"id": 4}])
        seen = []
        monkeypatch.setattr(approve_handler.db, "update_finding_status", lambda fid, status: seen.append((fid, status)))

        await handle_reject_all(update, context)

        assert seen == [(3, "rejected"), (4, "rejected")]
        update.callback_query.edit_message_text.assert_awaited_once()


class TestEveningReviewCallbacks:
    @pytest.mark.asyncio
    async def test_toggle_project_updates_selection(self, monkeypatch):
        update = _make_callback_query("toggle:alpha")
        context = _make_context({"night_selected": set()})
        monkeypatch.setattr(approve_handler.db, "get_all_projects", lambda: [{"project_id": "alpha"}])

        await handle_project_toggle(update, context)

        assert context.bot_data["night_selected"] == {"alpha"}
        update.callback_query.edit_message_reply_markup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_launch_review_writes_trigger_file(self, tmp_path, monkeypatch):
        update = _make_callback_query("launch_review")
        context = _make_context({"night_selected": {"alpha", "beta"}})
        monkeypatch.setattr(approve_handler, "SCRIPT_DIR", tmp_path)

        await handle_launch_review(update, context)

        trigger = tmp_path / ".review-trigger"
        assert trigger.exists()
        assert trigger.read_text(encoding="utf-8") == "alpha\nbeta\n"
        assert context.bot_data["night_selected"] == set()
