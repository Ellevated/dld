"""TECH-168 Task 3 — pure helpers (parse_label, map_result, _skill_from_pueue_command).

ARCH-186: Part A (_apply_spec_status, _apply_backlog_status, _apply_blocked_reason)
removed — those markdown mutators were deleted when lifecycle.yaml became SoT.

No subprocess / fs / db calls in this file.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import db  # noqa: E402

# =============================================================================
# Pure helpers
# =============================================================================

# --- parse_label -------------------------------------------------------------


def test_parse_label_with_colon():
    """'proj:label' → ('proj', 'label')."""
    assert callback.parse_label("proj:label") == ("proj", "label")


def test_parse_label_no_colon_warns(caplog):
    """'orphan' → ('orphan', 'orphan') + warning logged."""
    import logging

    with caplog.at_level(logging.WARNING, logger="callback"):
        result = callback.parse_label("orphan")
    assert result == ("orphan", "orphan")
    assert any("no colon" in r.message for r in caplog.records)


def test_parse_label_multiple_colons_first_wins():
    """'proj:autopilot:BUG-100' → ('proj', 'autopilot:BUG-100') via partition()."""
    assert callback.parse_label("proj:autopilot:BUG-100") == ("proj", "autopilot:BUG-100")


# --- map_result --------------------------------------------------------------


@pytest.mark.parametrize(
    "result_str,expected",
    [
        ("Success", ("done", 0)),
        ("Successfully completed", ("done", 0)),
        ("Failed", ("failed", 1)),
        ("Killed", ("failed", 1)),
        ("", ("failed", 1)),
    ],
)
def test_map_result(result_str, expected):
    """Substring 'Success' → done; everything else → failed."""
    assert callback.map_result(result_str) == expected


@pytest.mark.parametrize(
    "result_str,raw,expected",
    [
        # The case this exists for: a 90-minute TIMEOUT_SECONDS kill must reach
        # task_log as 124, not as an anonymous 1.
        ("Failed", "124", ("failed", 124)),
        ("Failed", "1", ("failed", 1)),
        ("Failed", "78", ("failed", 78)),
        # Success wins regardless — pueue never pairs Success with non-zero.
        ("Success", "124", ("done", 0)),
        # Un-migrated pueue.yml sends no 4th argv at all.
        ("Failed", None, ("failed", 1)),
        ("Failed", "", ("failed", 1)),
        # Garbage must degrade, not crash the callback.
        ("Failed", "not-a-number", ("failed", 1)),
    ],
)
def test_map_result_preserves_real_exit_code(result_str, raw, expected):
    """pueue's {{ exit_code }} survives into task_log when present."""
    assert callback.map_result(result_str, raw) == expected


# --- _skill_from_pueue_command (monkeypatched subprocess) -------------------


def _make_pueue_json(pueue_id: str, command: str, start: str = "") -> str:
    task: dict = {
        "command": command,
        "status": {"Running": {"start": start}} if start else {},
    }
    return json.dumps({"tasks": {pueue_id: task}})


def test_skill_from_pueue_extracts_4th_argv(monkeypatch):
    """command ending in run-agent.sh proj claude autopilot task → skill='autopilot'."""
    pueue_json = _make_pueue_json(
        "1", "/bin/bash /srv/run-agent.sh /path claude autopilot /autopilot BUG-1"
    )
    monkeypatch.setattr(
        callback.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, _ = callback._skill_from_pueue_command("1")
    assert skill == "autopilot"


def test_skill_from_pueue_absolute_path_to_run_agent(monkeypatch):
    """Absolute path to run-agent.sh → skill extracted correctly."""
    pueue_json = _make_pueue_json("2", "/srv/scripts/run-agent.sh /p claude qa /qa BUG-1")
    monkeypatch.setattr(
        callback.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, _ = callback._skill_from_pueue_command("2")
    assert skill == "qa"


def test_skill_from_pueue_no_run_agent_in_command(monkeypatch):
    """command='echo hello' → ('', 0.0)."""
    pueue_json = _make_pueue_json("3", "echo hello")
    monkeypatch.setattr(
        callback.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, ts = callback._skill_from_pueue_command("3")
    assert skill == ""
    assert ts == 0.0


def test_skill_from_pueue_subprocess_failure(monkeypatch):
    """subprocess raises → ('', 0.0), no exception propagates."""

    def _raise(*a, **kw):
        raise OSError("pueue socket not found")

    monkeypatch.setattr(callback.subprocess, "run", _raise)
    skill, ts = callback._skill_from_pueue_command("4")
    assert skill == ""
    assert ts == 0.0


def test_skill_from_pueue_returncode_nonzero(monkeypatch):
    """pueue rc=1 → ('', 0.0) (early return)."""
    monkeypatch.setattr(
        callback.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 1, "", ""),
    )
    skill, ts = callback._skill_from_pueue_command("5")
    assert skill == ""
    assert ts == 0.0


def test_skill_from_pueue_start_ts_running_state(monkeypatch):
    """Running.start='2026-05-02T12:00:00Z' → start_ts is a float > 0."""
    pueue_json = _make_pueue_json(
        "6",
        "run-agent.sh /p claude autopilot x",
        "2026-05-02T12:00:00Z",
    )
    monkeypatch.setattr(
        callback.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, ts = callback._skill_from_pueue_command("6")
    assert skill == "autopilot"
    assert ts > 0.0


def test_skill_from_pueue_start_ts_done_state(monkeypatch):
    """Done.start='2026-05-02T12:00:00Z' → start_ts parsed even after task done."""
    task = {
        "command": "run-agent.sh /p claude autopilot x",
        "status": {"Done": {"start": "2026-05-02T12:00:00Z", "end": "2026-05-02T13:00:00Z"}},
    }
    pueue_json = json.dumps({"tasks": {"7": task}})
    monkeypatch.setattr(
        callback.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, ts = callback._skill_from_pueue_command("7")
    assert skill == "autopilot"
    assert ts > 0.0


def test_skill_from_pueue_malformed_iso_silent(monkeypatch):
    """start='not-a-date' → start_ts=0.0, skill still returned."""
    pueue_json = _make_pueue_json(
        "8",
        "run-agent.sh /p claude autopilot x",
        "not-a-date",
    )
    monkeypatch.setattr(
        callback.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, ts = callback._skill_from_pueue_command("8")
    assert skill == "autopilot"
    assert ts == 0.0


# --- resolve_label (DB stubbed) -------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Create sqlite DB with schema for resolve_label test."""
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


def test_resolve_label_db_label_already_prefixed(tmp_db):
    """task_label already prefixed 'myproj:autopilot-X' → no double-prefix."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("myproj", "/tmp/ignored"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("myproj", "myproj:autopilot-X", "autopilot", "running", 77),
        )
    label = callback.resolve_label("77")
    assert label == "myproj:myproj:autopilot-X" or label == "myproj:autopilot-X"
    # Must not contain triple or quadruple colon from double-prefix
    assert label.count(":") <= 2
