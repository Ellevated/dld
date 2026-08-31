"""Layer B tests: heartbeat_reaper.py (TECH-198).

Tests cover: stale detection, grace-period skip, collision disambiguation
(fail-open), busy-process guard, kill decision. Real files/processes (ADR-013).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import heartbeat_reaper as reaper
import reaper_liveness
import reaper_pueue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_hb(
    log_dir: Path,
    project: str,
    ts_label: str,
    started_at: datetime,
    updated_at: datetime,
    turn: int = 5,
    last_tool: str = "Bash",
) -> Path:
    """Write a heartbeat file in the expected format."""
    hb_path = log_dir / f"{project}-{ts_label}.heartbeat.json"
    data = {
        "turn": turn,
        "elapsed_s": 300,
        "last_tool": last_tool,
        "started_at": started_at.isoformat(),
        "model": "claude-opus-4-8",
        "updated_at": updated_at.isoformat(),
    }
    hb_path.write_text(json.dumps(data), encoding="utf-8")
    return hb_path


def _fake_pueue_tasks(tasks: list[dict]) -> list[dict]:
    """Build task dicts as returned by get_running_claude_tasks."""
    result = []
    for t in tasks:
        start_dt = t.get("start_dt") or datetime.now(tz=timezone.utc)
        result.append(
            {
                "id": t.get("id", 100),
                "label": t.get("label", f"{t.get('project', 'proj')}:SPEC-1"),
                "group": "claude-runner",
                "command": t.get("command", ""),
                "start_iso": start_dt.isoformat(),
                "start_dt": start_dt,
                "project": t.get("project", "proj"),
            }
        )
    return result


# ---------------------------------------------------------------------------
# find_heartbeat_file tests
# ---------------------------------------------------------------------------


class TestFindHeartbeatFile:
    def test_single_match_by_started_at(self, tmp_path: Path) -> None:
        """Single heartbeat file matching started_at is returned."""
        now = datetime.now(tz=timezone.utc)
        started = now - timedelta(minutes=30)
        _write_hb(tmp_path, "myproj", "20260613-120000", started, now - timedelta(minutes=5))

        with patch.object(reaper, "LOG_DIR", tmp_path):
            result = reaper.find_heartbeat_file("myproj", started)
        assert result is not None
        assert result.name == "myproj-20260613-120000.heartbeat.json"

    def test_no_match_wrong_started_at(self, tmp_path: Path) -> None:
        """Heartbeat with different started_at does not match."""
        now = datetime.now(tz=timezone.utc)
        started_actual = now - timedelta(minutes=30)
        started_query = now - timedelta(minutes=60)  # different
        _write_hb(tmp_path, "myproj", "20260613-120000", started_actual, now)

        with patch.object(reaper, "LOG_DIR", tmp_path):
            result = reaper.find_heartbeat_file("myproj", started_query)
        assert result is None

    def test_collision_fail_open(self, tmp_path: Path) -> None:
        """Two heartbeat files with same started_at → fail-open (None)."""
        now = datetime.now(tz=timezone.utc)
        started = now - timedelta(minutes=30)
        _write_hb(tmp_path, "myproj", "20260613-120000", started, now)
        _write_hb(tmp_path, "myproj", "20260613-120001", started, now)

        with patch.object(reaper, "LOG_DIR", tmp_path):
            result = reaper.find_heartbeat_file("myproj", started)
        assert result is None  # fail-open

    def test_no_heartbeat_files(self, tmp_path: Path) -> None:
        """No heartbeat files → None."""
        with patch.object(reaper, "LOG_DIR", tmp_path):
            result = reaper.find_heartbeat_file("myproj", datetime.now(tz=timezone.utc))
        assert result is None

    def test_no_project(self, tmp_path: Path) -> None:
        """Empty project name → None."""
        with patch.object(reaper, "LOG_DIR", tmp_path):
            result = reaper.find_heartbeat_file("", datetime.now(tz=timezone.utc))
        assert result is None


# ---------------------------------------------------------------------------
# read_heartbeat tests
# ---------------------------------------------------------------------------


class TestReadHeartbeat:
    def test_valid_file(self, tmp_path: Path) -> None:
        now = datetime.now(tz=timezone.utc)
        hb = _write_hb(tmp_path, "proj", "20260613-120000", now, now)
        data = reaper.read_heartbeat(hb)
        assert data is not None
        assert data["turn"] == 5

    def test_invalid_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.heartbeat.json"
        bad.write_text("not json{", encoding="utf-8")
        assert reaper.read_heartbeat(bad) is None

    def test_missing_file(self, tmp_path: Path) -> None:
        assert reaper.read_heartbeat(tmp_path / "nope.json") is None


# ---------------------------------------------------------------------------
# reap_stale_sessions integration tests
# ---------------------------------------------------------------------------


class TestReapStaleSessions:
    def test_stale_idle_session_is_killed(self, tmp_path: Path) -> None:
        """Stale + idle session → killed + notified."""
        now = datetime.now(tz=timezone.utc)
        started = now - timedelta(minutes=40)
        updated = now - timedelta(minutes=30)  # 30 min stale > STALE_SECONDS(25min)
        _write_hb(tmp_path, "testproj", "20260613-100000", started, updated)

        tasks = _fake_pueue_tasks(
            [
                {
                    "id": 574,
                    "project": "testproj",
                    "start_dt": started,
                }
            ]
        )

        killed_ids: list[int] = []
        notified: list[dict] = []

        def fake_kill(pid: int) -> bool:
            killed_ids.append(pid)
            return True

        def fake_notify(project: str, pid: int, stale_min: float) -> None:
            notified.append({"project": project, "id": pid, "stale": stale_min})

        with (
            patch.object(reaper, "LOG_DIR", tmp_path),
            patch.object(reaper_pueue, "get_running_claude_tasks", return_value=tasks),
            patch.object(reaper_liveness, "is_process_idle", return_value=True),
            patch.object(reaper, "kill_task", side_effect=fake_kill),
            patch.object(reaper, "notify_reap", side_effect=fake_notify),
        ):
            reaped = reaper.reap_stale_sessions()

        assert reaped == 1
        assert 574 in killed_ids
        assert len(notified) == 1
        assert notified[0]["project"] == "testproj"

    def test_fresh_session_not_killed(self, tmp_path: Path) -> None:
        """Heartbeat updated_at within threshold → NOT killed."""
        now = datetime.now(tz=timezone.utc)
        started = now - timedelta(minutes=10)
        updated = now - timedelta(seconds=30)  # very fresh
        _write_hb(tmp_path, "testproj", "20260613-100000", started, updated)

        tasks = _fake_pueue_tasks(
            [
                {
                    "id": 575,
                    "project": "testproj",
                    "start_dt": started,
                }
            ]
        )

        with (
            patch.object(reaper, "LOG_DIR", tmp_path),
            patch.object(reaper_pueue, "get_running_claude_tasks", return_value=tasks),
            patch.object(reaper, "kill_task") as mock_kill,
        ):
            reaped = reaper.reap_stale_sessions()

        assert reaped == 0
        mock_kill.assert_not_called()

    def test_grace_period_skip(self, tmp_path: Path) -> None:
        """Task younger than GRACE_SECONDS → NOT killed even if no heartbeat."""
        now = datetime.now(tz=timezone.utc)
        started = now - timedelta(seconds=60)  # 1 min < GRACE(5min)

        tasks = _fake_pueue_tasks(
            [
                {
                    "id": 576,
                    "project": "testproj",
                    "start_dt": started,
                }
            ]
        )

        with (
            patch.object(reaper, "LOG_DIR", tmp_path),
            patch.object(reaper_pueue, "get_running_claude_tasks", return_value=tasks),
            patch.object(reaper, "kill_task") as mock_kill,
        ):
            reaped = reaper.reap_stale_sessions()

        assert reaped == 0
        mock_kill.assert_not_called()

    def test_busy_process_not_killed(self, tmp_path: Path) -> None:
        """Stale heartbeat but process is BUSY → NOT killed."""
        now = datetime.now(tz=timezone.utc)
        started = now - timedelta(minutes=40)
        updated = now - timedelta(minutes=30)  # stale
        _write_hb(tmp_path, "testproj", "20260613-100000", started, updated)

        tasks = _fake_pueue_tasks(
            [
                {
                    "id": 577,
                    "project": "testproj",
                    "start_dt": started,
                }
            ]
        )

        with (
            patch.object(reaper, "LOG_DIR", tmp_path),
            patch.object(reaper_pueue, "get_running_claude_tasks", return_value=tasks),
            patch.object(reaper_liveness, "is_process_idle", return_value=False),  # BUSY
            patch.object(reaper, "kill_task") as mock_kill,
        ):
            reaped = reaper.reap_stale_sessions()

        assert reaped == 0
        mock_kill.assert_not_called()

    def test_inconclusive_liveness_fail_open(self, tmp_path: Path) -> None:
        """Liveness check returns None (inconclusive) → fail-open, NOT killed."""
        now = datetime.now(tz=timezone.utc)
        started = now - timedelta(minutes=40)
        updated = now - timedelta(minutes=30)
        _write_hb(tmp_path, "testproj", "20260613-100000", started, updated)

        tasks = _fake_pueue_tasks(
            [
                {
                    "id": 578,
                    "project": "testproj",
                    "start_dt": started,
                }
            ]
        )

        with (
            patch.object(reaper, "LOG_DIR", tmp_path),
            patch.object(reaper_pueue, "get_running_claude_tasks", return_value=tasks),
            patch.object(reaper_liveness, "is_process_idle", return_value=None),  # inconclusive
            patch.object(reaper, "kill_task") as mock_kill,
        ):
            reaped = reaper.reap_stale_sessions()

        assert reaped == 0
        mock_kill.assert_not_called()

    def test_no_running_tasks(self, tmp_path: Path) -> None:
        """No running tasks → 0 reaped, no errors."""
        with (
            patch.object(reaper, "LOG_DIR", tmp_path),
            patch.object(reaper_pueue, "get_running_claude_tasks", return_value=[]),
        ):
            reaped = reaper.reap_stale_sessions()
        assert reaped == 0


# ---------------------------------------------------------------------------
# _parse_iso tests
# ---------------------------------------------------------------------------


class TestParseIso:
    def test_standard_iso(self) -> None:
        dt = reaper_pueue._parse_iso("2026-06-13T12:00:00+00:00")
        assert dt is not None
        assert dt.year == 2026

    def test_z_suffix(self) -> None:
        dt = reaper_pueue._parse_iso("2026-06-13T12:00:00Z")
        assert dt is not None

    def test_empty(self) -> None:
        assert reaper_pueue._parse_iso("") is None

    def test_none(self) -> None:
        assert reaper_pueue._parse_iso(None) is None

    def test_garbage(self) -> None:
        assert reaper_pueue._parse_iso("not-a-date") is None


# ---------------------------------------------------------------------------
# _project_from_command tests
# ---------------------------------------------------------------------------


class TestProjectFromCommand:
    def test_extracts_project_name(self) -> None:
        cmd = "bash run-agent.sh /home/dld/projects/awardybot claude autopilot FTR-1185"
        assert reaper_pueue._project_from_command(cmd) == "awardybot"

    def test_no_match(self) -> None:
        assert reaper_pueue._project_from_command("python3 some_script.py") == ""

    def test_empty(self) -> None:
        assert reaper_pueue._project_from_command("") == ""
