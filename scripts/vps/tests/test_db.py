# scripts/vps/tests/test_db.py
"""Unit tests for scripts/vps/db.py.

Covers: seed_projects_from_json, log_task, finish_task, try_acquire_slot,
release_slot, get_available_slots, get_project_state, update_project_phase,
callback CLI mode, save_finding, get_new_findings.
"""

import sqlite3
import sys
from pathlib import Path


VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import db


# --- EC-1: seed_projects upsert idempotency ---


class TestSeedProjects:
    def test_seed_upsert_idempotency(self, isolated_db):
        """EC-1: Seeding same project_id twice updates path, no duplicate row."""
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/old/path", "topic_id": 5, "provider": "claude"},
            ]
        )
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/new/path", "topic_id": 5, "provider": "claude"},
            ]
        )

        conn = sqlite3.connect(str(isolated_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM project_state WHERE project_id = 'proj1'").fetchall()
        conn.close()

        assert len(rows) == 1, "Should have exactly 1 row after double-seed"
        assert rows[0]["path"] == "/new/path", "Path should be updated on conflict"

    def test_seed_multiple_projects(self, isolated_db):
        """Seeding multiple projects creates all rows."""
        db.seed_projects_from_json(
            [
                {"project_id": "a", "path": "/a", "topic_id": 1, "provider": "claude"},
                {"project_id": "b", "path": "/b", "topic_id": 2, "provider": "codex"},
            ]
        )
        assert db.get_project_state("a") is not None
        assert db.get_project_state("b") is not None
        assert db.get_project_state("a")["provider"] == "claude"
        assert db.get_project_state("b")["provider"] == "codex"

    def test_seed_preserves_existing_topic_binding_when_json_omits_it(self, isolated_db):
        """Reseed must not erase topic binding if projects.json omits it."""
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/old/path", "topic_id": 42, "provider": "claude"},
            ]
        )
        db.seed_projects_from_json(
            [
                {"project_id": "proj1", "path": "/new/path", "provider": "claude"},
            ]
        )

        state = db.get_project_state("proj1")
        assert state is not None
        assert state["path"] == "/new/path"
        assert state["topic_id"] == 42


# --- EC-12: log_task creates DB entry ---


class TestLogTask:
    def test_log_task_creates_entry(self, seed_project):
        """EC-12: log_task creates a row with correct values."""
        row_id = db.log_task(
            project_id="testproject",
            task_label="testproject:inbox-20260312",
            skill="spark",
            status="queued",
            pueue_id=42,
        )
        assert row_id is not None
        assert row_id > 0

        conn = sqlite3.connect(str(Path(db.DB_PATH)))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_log WHERE id = ?", (row_id,)).fetchone()
        conn.close()

        assert row["project_id"] == "testproject"
        assert row["task_label"] == "testproject:inbox-20260312"
        assert row["skill"] == "spark"
        assert row["status"] == "queued"
        assert row["pueue_id"] == 42

    def test_finish_task(self, seed_project):
        """finish_task marks the task with status, exit_code, finished_at."""
        row_id = db.log_task("testproject", "label", "spark", "queued", pueue_id=99)
        db.finish_task(pueue_id=99, status="done", exit_code=0, summary="ok")

        conn = sqlite3.connect(str(Path(db.DB_PATH)))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM task_log WHERE id = ?", (row_id,)).fetchone()
        conn.close()

        assert row["status"] == "done"
        assert row["exit_code"] == 0
        assert row["output_summary"] == "ok"
        assert row["finished_at"] is not None


# --- EC-2 + EC-3: try_acquire_slot ---


class TestSlotAcquisition:
    def test_acquire_slot_success(self, seed_project):
        """Acquire a free claude slot returns slot_number."""
        slot = db.try_acquire_slot("testproject", "claude", pueue_id=10)
        assert slot is not None
        assert slot in (1, 2), "Should get one of the two claude slots"

    def test_acquire_slot_no_free_slots(self, seed_project):
        """EC-2: All slots occupied returns None, no crash."""
        # Occupy both claude slots
        db.try_acquire_slot("testproject", "claude", pueue_id=10)
        db.try_acquire_slot("testproject", "claude", pueue_id=11)

        result = db.try_acquire_slot("testproject", "claude", pueue_id=12)
        assert result is None

    def test_acquire_slot_concurrent_one_slot(self, isolated_db):
        """EC-3: Two calls for 1 slot -- exactly one gets it."""
        # Seed project first
        db.seed_projects_from_json(
            [
                {"project_id": "p1", "path": "/p1", "topic_id": 1, "provider": "codex"},
            ]
        )
        # codex has exactly 1 slot (slot_number=3)
        slot_a = db.try_acquire_slot("p1", "codex", pueue_id=20)
        slot_b = db.try_acquire_slot("p1", "codex", pueue_id=21)

        results = [slot_a, slot_b]
        assert results.count(None) == 1, "Exactly one call should get None"
        assert results.count(3) == 1, "Exactly one call should get slot 3"

    def test_release_slot(self, seed_project):
        """release_slot frees the slot, returns project_id."""
        db.try_acquire_slot("testproject", "claude", pueue_id=30)
        project_id = db.release_slot(pueue_id=30)
        assert project_id == "testproject"
        # Slot is free again
        assert db.get_available_slots("claude") == 2

    def test_release_nonexistent_slot(self, seed_project):
        """release_slot with unknown pueue_id returns None."""
        assert db.release_slot(pueue_id=999) is None

    def test_get_available_slots(self, seed_project):
        """get_available_slots counts free slots per provider."""
        assert db.get_available_slots("claude") == 2
        assert db.get_available_slots("codex") == 1
        assert db.get_available_slots("gemini") == 1

        db.try_acquire_slot("testproject", "claude", pueue_id=40)
        assert db.get_available_slots("claude") == 1


# --- project state + phase ---


class TestProjectState:
    def test_get_project_state(self, seed_project):
        """get_project_state returns dict with all columns."""
        state = db.get_project_state("testproject")
        assert state is not None
        assert state["project_id"] == "testproject"
        assert state["path"] == "/tmp/test-project"
        assert state["topic_id"] == 5
        assert state["phase"] == "idle"

    def test_get_project_state_not_found(self, isolated_db):
        """get_project_state returns None for missing project."""
        assert db.get_project_state("nonexistent") is None

    def test_update_project_phase(self, seed_project):
        """update_project_phase changes phase and current_task."""
        db.update_project_phase("testproject", "processing_inbox", "task-label-1")
        state = db.get_project_state("testproject")
        assert state["phase"] == "processing_inbox"
        assert state["current_task"] == "task-label-1"


# --- Note: callback CLI removed in ARCH-161 (moved to standalone callback.py) ---
