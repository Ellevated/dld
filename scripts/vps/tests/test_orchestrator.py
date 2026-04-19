# scripts/vps/tests/test_orchestrator.py
"""Unit tests for orchestrator watchdog functions (BUG-162).

Covers: get_live_pueue_ids, release_orphan_slots, get_occupied_slots (db.py).
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock


VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import db
import orchestrator


# --- EC-7: get_occupied_slots returns correct data ---


class TestGetOccupiedSlots:
    def test_returns_occupied_only(self, seed_project):
        """EC-7: Returns exactly the occupied slots with correct fields."""
        db.try_acquire_slot("testproject", "claude", pueue_id=10)
        db.try_acquire_slot("testproject", "claude", pueue_id=11)
        result = db.get_occupied_slots()
        assert len(result) == 2
        for slot in result:
            assert "slot_number" in slot
            assert "pueue_id" in slot
            assert "project_id" in slot
            assert "acquired_at" in slot
            assert slot["project_id"] == "testproject"

    def test_returns_empty_when_none_occupied(self, seed_project):
        """EC-5: No occupied slots → empty list."""
        result = db.get_occupied_slots()
        assert result == []


# --- EC-1: pueue failure → no release ---


class TestGetLivePueueIds:
    def test_pueue_failure_returns_none(self, seed_project):
        """EC-1: When pueue status fails, return None (not empty set)."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "daemon not running"
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            result = orchestrator.get_live_pueue_ids()
        assert result is None

    def test_pueue_exception_returns_none(self, seed_project):
        """EC-1: When subprocess raises, return None."""
        with patch("orchestrator.subprocess.run", side_effect=OSError("no pueue")):
            result = orchestrator.get_live_pueue_ids()
        assert result is None

    def test_running_tasks_detected(self, seed_project):
        """EC-2: Running tasks appear in live set."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "tasks": {
                    "5": {
                        "status": {"Running": {"start": "2026-03-19T00:00:00Z"}},
                        "label": "proj:T1",
                    },
                    "6": {
                        "status": {"Running": {"start": "2026-03-19T00:00:00Z"}},
                        "label": "proj:T2",
                    },
                }
            }
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            result = orchestrator.get_live_pueue_ids()
        assert result == {5, 6}

    def test_queued_tasks_in_live_set(self, seed_project):
        """EC-6: Queued tasks are included in live set (not released)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "tasks": {
                    "10": {"status": "Queued", "label": "proj:T1"},
                }
            }
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            result = orchestrator.get_live_pueue_ids()
        assert 10 in result

    def test_stashed_paused_in_live_set(self, seed_project):
        """Stashed and Paused tasks stay in live set."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "tasks": {
                    "20": {"status": "Stashed", "label": "proj:T1"},
                    "21": {"status": "Paused", "label": "proj:T2"},
                }
            }
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            result = orchestrator.get_live_pueue_ids()
        assert result == {20, 21}

    def test_empty_tasks_returns_empty_set(self, seed_project):
        """EC-4: pueue returns empty tasks (valid response) → empty set (not None)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"tasks": {}})
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            result = orchestrator.get_live_pueue_ids()
        assert result == set()  # empty set, NOT None


# --- EC-3, EC-4: release_orphan_slots ---


class TestReleaseOrphanSlots:
    def test_pueue_unreachable_no_release(self, seed_project):
        """EC-1: Pueue failure → 0 released, DB unchanged."""
        db.try_acquire_slot("testproject", "claude", pueue_id=50)
        with patch("orchestrator.get_live_pueue_ids", return_value=None):
            released = orchestrator.release_orphan_slots()
        assert released == 0
        assert len(db.get_occupied_slots()) == 1  # slot still occupied

    def test_all_running_no_release(self, seed_project):
        """EC-2: All tasks running → 0 released."""
        db.try_acquire_slot("testproject", "claude", pueue_id=5)
        db.try_acquire_slot("testproject", "claude", pueue_id=6)
        with patch("orchestrator.get_live_pueue_ids", return_value={5, 6}):
            released = orchestrator.release_orphan_slots()
        assert released == 0
        assert len(db.get_occupied_slots()) == 2

    def test_genuine_orphan_released(self, seed_project):
        """EC-3: Orphan slot (pueue_id=99 not in pueue) → released."""
        db.try_acquire_slot("testproject", "claude", pueue_id=99)
        with patch("orchestrator.get_live_pueue_ids", return_value=set()):
            released = orchestrator.release_orphan_slots()
        assert released == 1
        assert db.get_occupied_slots() == []
        assert db.get_available_slots("claude") == 2

    def test_empty_pueue_releases_all_orphans(self, seed_project):
        """EC-4: pueue has no tasks, DB has occupied slot → release it."""
        db.try_acquire_slot("testproject", "claude", pueue_id=42)
        with patch("orchestrator.get_live_pueue_ids", return_value=set()):
            released = orchestrator.release_orphan_slots()
        assert released == 1

    def test_no_occupied_slots_noop(self, seed_project):
        """EC-5: No occupied slots → fast no-op."""
        with patch("orchestrator.get_live_pueue_ids", return_value={1, 2, 3}):
            released = orchestrator.release_orphan_slots()
        assert released == 0

    def test_mixed_orphan_and_live(self, seed_project):
        """Mix of live and orphan slots — only orphan released."""
        db.try_acquire_slot("testproject", "claude", pueue_id=10)  # live
        db.try_acquire_slot("testproject", "claude", pueue_id=99)  # orphan
        with patch("orchestrator.get_live_pueue_ids", return_value={10}):
            released = orchestrator.release_orphan_slots()
        assert released == 1
        occupied = db.get_occupied_slots()
        assert len(occupied) == 1
        assert occupied[0]["pueue_id"] == 10

    def test_release_idempotent(self, seed_project):
        """Double release of same orphan — second call is no-op."""
        db.try_acquire_slot("testproject", "claude", pueue_id=77)
        with patch("orchestrator.get_live_pueue_ids", return_value=set()):
            orchestrator.release_orphan_slots()
            released = orchestrator.release_orphan_slots()
        assert released == 0


# --- EC-8: Integration test (no mocks for DB) ---


class TestWatchdogIntegration:
    def test_acquire_then_watchdog_frees_slot(self, seed_project):
        """EC-8: Slot acquired, pueue task gone → watchdog frees it, available increases."""
        initial_available = db.get_available_slots("claude")
        db.try_acquire_slot("testproject", "claude", pueue_id=555)
        assert db.get_available_slots("claude") == initial_available - 1

        # Simulate pueue returning no tasks (task 555 is gone)
        with patch("orchestrator.get_live_pueue_ids", return_value=set()):
            released = orchestrator.release_orphan_slots()
        assert released == 1
        assert db.get_available_slots("claude") == initial_available
