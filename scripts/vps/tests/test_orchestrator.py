# scripts/vps/tests/test_orchestrator.py
"""Unit tests for orchestrator watchdog functions (BUG-162).

Covers: get_live_pueue_ids, release_orphan_slots, get_occupied_slots (db.py).
"""

import json
import subprocess
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

    def test_dict_queued_status_in_live_set(self, seed_project):
        """Regression 2026-04-24: modern pueue wraps Queued in a dict.

        Before the fix, `status: {"Queued": {...}}` fell through to the
        string-match branch (`st in ("Queued", ...)`), which is always false
        because st is a dict. Result: all Queued tasks flagged as orphans
        and released, causing duplicate dispatch.
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "tasks": {
                    "30": {"status": {"Queued": {"enqueued_at": "t"}}, "label": "proj:T1"},
                    "31": {"status": {"Stashed": {"enqueue_at": None}}, "label": "proj:T2"},
                    "32": {"status": {"Paused": {}}, "label": "proj:T3"},
                    "33": {"status": {"Running": {"start": "t"}}, "label": "proj:T4"},
                    "34": {"status": {"Done": {"result": "Success"}}, "label": "proj:T5"},
                }
            }
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            result = orchestrator.get_live_pueue_ids()
        # 34 is Done → not live; all others → live
        assert result == {30, 31, 32, 33}


class TestSpecIdRegex:
    """v3.15.8: spec id regex must capture letter suffixes (ARCH-176a/b/c/d).

    Reproduces wb infinite-dispatch loop: a `queued` row for ARCH-176a in
    the backlog kept being matched as `ARCH-176` by the old `\\d+` regex,
    and orchestrator dispatched the parent (status=split) on every cycle.
    """

    def test_captures_simple_id(self):
        import re

        m = re.search(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*", "| BUG-865 | foo |")
        assert m and m.group(0) == "BUG-865"

    def test_captures_letter_suffix(self):
        import re

        m = re.search(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*", "| ARCH-176a | foo |")
        assert m and m.group(0) == "ARCH-176a"

    def test_captures_multi_letter_suffix(self):
        import re

        m = re.search(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*", "ARCH-176abc rest")
        assert m and m.group(0) == "ARCH-176abc"

    def test_does_not_eat_uppercase_after_id(self):
        import re

        m = re.search(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*", "ARCH-176 META-SPEC")
        # Uppercase 'M' is not captured (regex only consumes lowercase a-z)
        assert m and m.group(0) == "ARCH-176"


class TestPueueHasActiveLabel:
    """Verify dedup guard used in scan_queued/scan_inbox."""

    def test_returns_true_for_running_duplicate(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {"tasks": {"7": {"status": {"Running": {}}, "label": "proj:BUG-1"}}}
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            assert orchestrator.pueue_has_active_label("proj:BUG-1") is True

    def test_returns_true_for_queued_duplicate(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {"tasks": {"8": {"status": {"Queued": {}}, "label": "proj:BUG-2"}}}
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            assert orchestrator.pueue_has_active_label("proj:BUG-2") is True

    def test_returns_false_for_done_task(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "tasks": {
                    "9": {
                        "status": {"Done": {"result": "Success"}},
                        "label": "proj:BUG-3",
                    }
                }
            }
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            assert orchestrator.pueue_has_active_label("proj:BUG-3") is False

    def test_returns_false_when_label_absent(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {"tasks": {"10": {"status": {"Running": {}}, "label": "other:spec"}}}
        )
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            assert orchestrator.pueue_has_active_label("proj:BUG-4") is False

    def test_fail_open_on_pueue_error(self):
        """If pueue is unreachable, return False (allow dispatch)."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "daemon not running"
        with patch("orchestrator.subprocess.run", return_value=mock_result):
            assert orchestrator.pueue_has_active_label("proj:BUG-5") is False

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


# --- TECH-181: Hermes intake status gate ---


import pytest


def _write_inbox_file(inbox_dir: Path, name: str, status: str | None) -> Path:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    parts = ["# Test inbox item"]
    if status is not None:
        parts.append(f"**Status:** {status}")
    parts += [
        "**Route:** spark",
        "**Source:** test",
        "",
        "---",
        "",
        "Idea body text.",
    ]
    f = inbox_dir / name
    f.write_text("\n".join(parts))
    return f


class TestScanInboxStatusGate:
    """TECH-181: orchestrator dispatches only Status: queued, ignores all others."""

    def test_scan_inbox_dispatches_queued(self, tmp_path, seed_project):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-queued.md", "queued")

        with (
            patch("orchestrator._pueue_add", return_value=42) as mock_add,
            patch("orchestrator.pueue_has_active_label", return_value=False),
            patch("orchestrator.db.try_acquire_slot"),
            patch("orchestrator.db.log_task"),
            patch("orchestrator.db.update_project_phase"),
            patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
        ):
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 1
        assert mock_add.called
        # File moved to inbox/done/
        assert not f.exists()
        done_file = inbox_dir / "done" / "20260507-queued.md"
        assert done_file.exists()
        text = done_file.read_text()
        assert "**Status:** processing" in text
        assert "**Status:** queued" not in text

    def test_scan_inbox_ignores_draft(self, tmp_path, seed_project):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-draft.md", "draft")
        original = f.read_text()

        with patch("orchestrator._pueue_add") as mock_add:
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 0
        assert not mock_add.called
        assert f.exists()
        assert f.read_text() == original

    @pytest.mark.parametrize("status", ["clarifying", "stale", "rejected"])
    def test_scan_inbox_ignores_clarifying_stale_rejected(self, tmp_path, seed_project, status):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, f"20260507-{status}.md", status)

        with patch("orchestrator._pueue_add") as mock_add:
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 0
        assert not mock_add.called
        assert f.exists()

    def test_scan_inbox_ignores_legacy_new(self, tmp_path, seed_project):
        """Regression guard for clean break: legacy `Status: new` MUST NOT dispatch."""
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-legacy.md", "new")
        original = f.read_text()

        with patch("orchestrator._pueue_add") as mock_add:
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 0
        assert not mock_add.called
        assert f.exists()
        assert f.read_text() == original

    def test_scan_inbox_no_status_field(self, tmp_path, seed_project):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-nostatus.md", None)

        with patch("orchestrator._pueue_add") as mock_add:
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 0
        assert not mock_add.called
        assert f.exists()


class TestBootstrapAnomaly:
    """TECH-189 Task 4: bootstrap_new_specs anomaly detector."""

    def _make_project(self, tmp_path: Path, spec_ids: list[str]) -> Path:
        features = tmp_path / "ai" / "features"
        features.mkdir(parents=True)
        backlog = tmp_path / "ai" / "backlog.md"
        # Build backlog with each spec ID + status=queued, plus one filler col so
        # the regex sees `| ID | desc | queued | P0 | spec |`.
        rows = "\n".join(f"| {sid} | desc | queued | P0 | [spec]({sid}.md) |" for sid in spec_ids)
        backlog.write_text(rows)
        # Each spec.md file in features/ with the spec ID in the filename
        for sid in spec_ids:
            (features / f"{sid}-2026-05-23-anomaly-test.md").write_text(
                "# test\n\n**Status:** queued\n**Priority:** P0\n**Kind:** tech\n"
            )
        # CR-5 (ARCH-196): bootstrap_new_specs reads backlog from HEAD via git.
        # Init a real git repo and commit backlog.md so HEAD contains the data.
        subprocess.check_call(
            ["git", "init", "-b", "main", str(tmp_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            ["git", "add", "ai/backlog.md"],
            cwd=str(tmp_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            ["git", "commit", "-m", "test: add backlog"],
            cwd=str(tmp_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return tmp_path

    def test_no_anomaly_for_normal_count(self, tmp_path, caplog):
        """1 new spec = normal, no anomaly warning, no counter file."""
        import logging

        self._make_project(tmp_path, ["TECH-991"])
        with (
            patch.object(orchestrator.lifecycle, "create_initial") as mock_init,
            patch.object(orchestrator.lifecycle, "read_lifecycle", return_value=None),
        ):
            with caplog.at_level(logging.WARNING):
                orchestrator.bootstrap_new_specs(str(tmp_path))
        assert mock_init.call_count == 1
        assert not any("BOOTSTRAP_ANOMALY" in r.message for r in caplog.records)
        assert not (tmp_path / "ai" / ".bootstrap-anomaly-count").exists()

    def test_anomaly_fires_above_threshold(self, tmp_path, caplog):
        """5 new specs in one cycle (>3) fires BOOTSTRAP_ANOMALY warning + counter."""
        import logging

        ids = [f"TECH-9{i:02d}" for i in range(80, 85)]  # 5 ids
        self._make_project(tmp_path, ids)
        with (
            patch.object(orchestrator.lifecycle, "create_initial"),
            patch.object(orchestrator.lifecycle, "read_lifecycle", return_value=None),
        ):
            with caplog.at_level(logging.WARNING):
                orchestrator.bootstrap_new_specs(str(tmp_path))

        anomaly_logs = [r for r in caplog.records if "BOOTSTRAP_ANOMALY" in r.message]
        assert len(anomaly_logs) == 1
        assert "created 5 lifecycle yamls" in anomaly_logs[0].message
        counter = tmp_path / "ai" / ".bootstrap-anomaly-count"
        assert counter.is_file()
        assert counter.read_text().strip() == "1"


class TestHeartbeatMonitor:
    """TECH-189 Task 8: heartbeat_monitor.py — external liveness check."""

    def test_fresh_heartbeat_no_alert(self, tmp_path, monkeypatch, capsys):
        """Fresh timestamp = no Hermes event, no ALERT to stderr."""
        from datetime import datetime, timezone

        import heartbeat_monitor

        hb = tmp_path / ".orchestrator-heartbeat"
        hb.write_text(datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        monkeypatch.setattr(heartbeat_monitor, "HEARTBEAT_FILE", hb)
        with patch.object(heartbeat_monitor, "STALE_THRESHOLD_MINUTES", 10):
            heartbeat_monitor.main()
        captured = capsys.readouterr()
        assert "ALERT" not in captured.err

    def test_stale_heartbeat_fires_notify(self, tmp_path, monkeypatch, capsys):
        """Stale timestamp (>10min) = ALERT to stderr + event_writer.notify called."""
        from datetime import datetime, timedelta, timezone

        import heartbeat_monitor

        hb = tmp_path / ".orchestrator-heartbeat"
        stale_ts = datetime.now(tz=timezone.utc) - timedelta(minutes=15)
        hb.write_text(stale_ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
        monkeypatch.setattr(heartbeat_monitor, "HEARTBEAT_FILE", hb)

        # event_writer.notify is imported lazily inside main() — patch via sys.modules
        from unittest.mock import MagicMock as _MM

        mock_module = _MM()
        mock_module.notify = _MM()
        monkeypatch.setitem(sys.modules, "event_writer", mock_module)

        heartbeat_monitor.main()
        captured = capsys.readouterr()
        assert "ALERT: orchestrator heartbeat stale" in captured.err
        mock_module.notify.assert_called_once()
        args, _ = mock_module.notify.call_args
        assert args[0] == "dld"
        assert "ORCHESTRATOR_STALE" in args[1]

    def test_missing_heartbeat_file_no_crash(self, tmp_path, monkeypatch, capsys):
        """Missing file = WARN to stderr, no crash."""
        import heartbeat_monitor

        monkeypatch.setattr(heartbeat_monitor, "HEARTBEAT_FILE", tmp_path / "nope")
        heartbeat_monitor.main()
        captured = capsys.readouterr()
        assert "WARN: no heartbeat file" in captured.err
