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

# Slot count lives in test_db, next to the schema check that pins it.
from test_db import CLAUDE_SLOTS


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
    """Verify dedup guard used in dispatch_one/scan_inbox."""

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
        with patch("orchestrator_slots.get_live_pueue_ids", return_value=None):
            released = orchestrator.release_orphan_slots()
        assert released == 0
        assert len(db.get_occupied_slots()) == 1  # slot still occupied

    def test_all_running_no_release(self, seed_project):
        """EC-2: All tasks running → 0 released."""
        db.try_acquire_slot("testproject", "claude", pueue_id=5)
        db.try_acquire_slot("testproject", "claude", pueue_id=6)
        with patch("orchestrator_slots.get_live_pueue_ids", return_value={5, 6}):
            released = orchestrator.release_orphan_slots()
        assert released == 0
        assert len(db.get_occupied_slots()) == 2

    def test_genuine_orphan_released(self, seed_project):
        """EC-3: Orphan slot (pueue_id=99 not in pueue) → released."""
        db.try_acquire_slot("testproject", "claude", pueue_id=99)
        with patch("orchestrator_slots.get_live_pueue_ids", return_value=set()):
            released = orchestrator.release_orphan_slots()
        assert released == 1
        assert db.get_occupied_slots() == []
        assert db.get_available_slots("claude") == CLAUDE_SLOTS

    def test_empty_pueue_releases_all_orphans(self, seed_project):
        """EC-4: pueue has no tasks, DB has occupied slot → release it."""
        db.try_acquire_slot("testproject", "claude", pueue_id=42)
        with patch("orchestrator_slots.get_live_pueue_ids", return_value=set()):
            released = orchestrator.release_orphan_slots()
        assert released == 1

    def test_no_occupied_slots_noop(self, seed_project):
        """EC-5: No occupied slots → fast no-op."""
        with patch("orchestrator_slots.get_live_pueue_ids", return_value={1, 2, 3}):
            released = orchestrator.release_orphan_slots()
        assert released == 0

    def test_mixed_orphan_and_live(self, seed_project):
        """Mix of live and orphan slots — only orphan released."""
        db.try_acquire_slot("testproject", "claude", pueue_id=10)  # live
        db.try_acquire_slot("testproject", "claude", pueue_id=99)  # orphan
        with patch("orchestrator_slots.get_live_pueue_ids", return_value={10}):
            released = orchestrator.release_orphan_slots()
        assert released == 1
        occupied = db.get_occupied_slots()
        assert len(occupied) == 1
        assert occupied[0]["pueue_id"] == 10

    def test_release_idempotent(self, seed_project):
        """Double release of same orphan — second call is no-op."""
        db.try_acquire_slot("testproject", "claude", pueue_id=77)
        with patch("orchestrator_slots.get_live_pueue_ids", return_value=set()):
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
        with patch("orchestrator_slots.get_live_pueue_ids", return_value=set()):
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
    f.write_text("\n".join(parts), encoding="utf-8")
    return f


class TestScanInboxStatusGate:
    """TECH-181: orchestrator dispatches only Status: queued, ignores all others."""

    def test_scan_inbox_dispatches_queued(self, tmp_path, seed_project):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-queued.md", "queued")

        with (
            patch("orchestrator_inbox._pueue_add", return_value=42) as mock_add,
            patch("orchestrator_inbox.pueue_has_active_label", return_value=False),
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
        text = done_file.read_text(encoding="utf-8")
        assert "**Status:** processing" in text
        assert "**Status:** queued" not in text

    def test_scan_inbox_ignores_draft(self, tmp_path, seed_project):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-draft.md", "draft")
        original = f.read_text(encoding="utf-8")

        with patch("orchestrator_inbox._pueue_add") as mock_add:
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 0
        assert not mock_add.called
        assert f.exists()
        assert f.read_text(encoding="utf-8") == original

    @pytest.mark.parametrize("status", ["clarifying", "stale", "rejected"])
    def test_scan_inbox_ignores_clarifying_stale_rejected(self, tmp_path, seed_project, status):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, f"20260507-{status}.md", status)

        with patch("orchestrator_inbox._pueue_add") as mock_add:
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 0
        assert not mock_add.called
        assert f.exists()

    def test_scan_inbox_ignores_legacy_new(self, tmp_path, seed_project):
        """Regression guard for clean break: legacy `Status: new` MUST NOT dispatch."""
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-legacy.md", "new")
        original = f.read_text(encoding="utf-8")

        with patch("orchestrator_inbox._pueue_add") as mock_add:
            count = orchestrator.scan_inbox("testproject", str(tmp_path))

        assert count == 0
        assert not mock_add.called
        assert f.exists()
        assert f.read_text(encoding="utf-8") == original

    def test_scan_inbox_no_status_field(self, tmp_path, seed_project):
        inbox_dir = tmp_path / "ai" / "inbox"
        f = _write_inbox_file(inbox_dir, "20260507-nostatus.md", None)

        with patch("orchestrator_inbox._pueue_add") as mock_add:
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
        backlog.write_text(rows, encoding="utf-8")
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
        assert counter.read_text(encoding="utf-8").strip() == "1"


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
        hb.write_text(stale_ts.strftime("%Y-%m-%dT%H:%M:%SZ"), encoding="utf-8")
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
        args, _ = mock_module.notify.call_args  # real signature: path, skill, status, message
        assert (len(args), args[0], args[2]) == (4, str(heartbeat_monitor.SCRIPT_DIR), "failed")
        assert "ORCHESTRATOR_STALE" in args[3]

    def test_missing_heartbeat_file_no_crash(self, tmp_path, monkeypatch, capsys):
        """Missing file = WARN to stderr, no crash."""
        import heartbeat_monitor

        monkeypatch.setattr(heartbeat_monitor, "HEARTBEAT_FILE", tmp_path / "nope")
        heartbeat_monitor.main()
        captured = capsys.readouterr()
        assert "WARN: no heartbeat file" in captured.err


# --- Cycle pacing: honest 5-min period (_next_sleep) ---


class TestNextSleep:
    """Sleep the REMAINDER of the poll window, so the cycle period == poll_interval
    instead of poll_interval + pass_duration (the old flat-sleep behaviour pushed
    the real period to ~7-8 min)."""

    def test_subtracts_pass_duration(self):
        # 3-min pass within a 5-min window → sleep the remaining 2 min.
        assert orchestrator._next_sleep(300, 180) == 120

    def test_fast_pass_sleeps_almost_full_window(self):
        assert orchestrator._next_sleep(300, 5) == 295

    def test_overlong_pass_floored_not_negative(self):
        # Pass longer than the window must floor, never go negative (busy-loop).
        assert orchestrator._next_sleep(300, 600) == orchestrator.MIN_CYCLE_SLEEP

    def test_pass_equal_to_window_floored(self):
        assert orchestrator._next_sleep(300, 300) == orchestrator.MIN_CYCLE_SLEEP

    def test_just_under_floor_clamped(self):
        # Remainder smaller than the floor → clamp up to MIN_CYCLE_SLEEP.
        assert orchestrator._next_sleep(300, 290) == orchestrator.MIN_CYCLE_SLEEP


# ---------------------------------------------------------------------------
# TECH-215: compatibility surface of the orchestrator facade.
#
# Every name below is either imported by a bound `from orchestrator import ...`,
# or is a monkeypatch target in a test file that is NOT in this spec's Allowed
# Files. Losing one is not a red test somewhere else — it is a SILENT pass:
# `patch("orchestrator.X")` on a name the split moved away rebinds an attribute
# nothing reads, and the test then runs against unpatched production code.
# ---------------------------------------------------------------------------

_FACADE_NAMES = [
    # module-level state
    "SCRIPT_DIR",
    "log",
    "MIN_CYCLE_SLEEP",
    "BOOTSTRAP_ANOMALY_THRESHOLD",
    # slots / pueue
    "sync_projects",
    "get_live_pueue_ids",
    "pueue_has_active_label",
    "pueue_has_active_spec",
    "release_orphan_slots",
    "is_agent_running",
    "git_pull",
    "_pueue_add",
    # backlog / bootstrap
    "_parse_backlog",
    "_bump_unparsable_counter",
    "_parse_priority_kind",
    "bootstrap_new_specs",
    "cleanup_stale_stashes",
    "startup_reconcile",
    # inbox
    "scan_inbox",
    # queue — the built-in dispatch names (scan_queued, _unmet_dependencies,
    # _backlog_deps, _AFTER_DEP_RE) and the gate_logic import left 2026-09-27
    # with the builtin path itself; nothing patches them any more.
    "dispatch_night_review",
    # main loop
    "process_project",
    "_next_sleep",
    "main",
]


class TestFacadeCompatSurface:
    """EC-7/EC-13: names the untouchable test files reach through `orchestrator`."""

    @pytest.mark.parametrize("name", _FACADE_NAMES)
    def test_name_resolves_from_orchestrator(self, name):
        assert hasattr(orchestrator, name), (
            f"orchestrator.{name} disappeared — a monkeypatch or bound import "
            f"in a non-editable test file now silently misses"
        )

    def test_bound_import_of_adr_026_names(self):
        """test_orchestrator_bootstrap.py:28 binds both at import time."""
        from orchestrator import _bump_unparsable_counter, _parse_backlog  # noqa: F401

    def test_patched_facade_name_is_seen_by_its_caller(self, tmp_path):
        """The whole point: patching the facade must still reach the callee.

        git_pull stays in orchestrator.py precisely so that
        patch("orchestrator.is_agent_running") is observed by it.
        """
        # git_pull's first gate is `os.path.isdir(project_dir/.git)`. A real repo
        # root won't do here: this repo is checked out as a worktree, where
        # `.git` is a FILE (gitdir pointer), not a directory — isdir() is False
        # and git_pull would short-circuit before is_agent_running is ever
        # called, silently passing this test for the wrong reason. A bare
        # `.git/` directory is the minimal fixture that satisfies the gate.
        (tmp_path / ".git").mkdir()
        with (
            patch("orchestrator.is_agent_running", return_value=True) as spy,
            patch("orchestrator.subprocess.run") as run_mock,
        ):
            orchestrator.git_pull("p", str(tmp_path))
        spy.assert_called_once()
        run_mock.assert_not_called()


class TestSplitStructuralInvariants:
    """EC-8, EC-9, EC-12: the shape the split exists to produce."""

    _MODULES = [
        "orchestrator.py",
        "orchestrator_slots.py",
        "orchestrator_backlog.py",
        "orchestrator_inbox.py",
        "orchestrator_queue.py",
    ]

    # Per-file ceilings above 400. Empty since 2026-09-27: orchestrator.py carried
    # 412 for the builtin dispatch loop, which left with the builtin path.
    _LOC_CEILING: dict[str, int] = {}

    @pytest.mark.parametrize("name", _MODULES)
    def test_file_under_loc_limit(self, name):
        path = Path(orchestrator.__file__).parent / name
        loc = len(path.read_text(encoding="utf-8").splitlines())
        limit = self._LOC_CEILING.get(name, 400)
        assert loc <= limit, f"{name}: {loc} LOC > {limit}"

    @pytest.mark.parametrize("name", _MODULES[1:])
    def test_sibling_never_imports_the_facade(self, name):
        """The invariant TECH-214 states for lifecycle: no cycle, ever."""
        src = (Path(orchestrator.__file__).parent / name).read_text(encoding="utf-8")
        for line in src.splitlines():
            s = line.strip()
            assert s != "import orchestrator", f"{name}: cycle via `import orchestrator`"
            assert not s.startswith("from orchestrator import"), f"{name}: cycle"

    def test_no_function_body_over_80_lines(self):
        """EC-8: the reason the split exists — scan_queued hid a bug at 226 lines."""
        import ast

        offenders = []
        for name in self._MODULES:
            path = Path(orchestrator.__file__).parent / name
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    span = node.end_lineno - node.lineno
                    if span > 80:
                        offenders.append(f"{name}:{node.name} ({span})")
        assert not offenders, f"functions over 80 lines: {offenders}"
