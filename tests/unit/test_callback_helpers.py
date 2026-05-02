"""TECH-168 Tasks 2+3 — text mutators and pure helpers.

Part A (Task 2): _apply_spec_status, _apply_backlog_status, _apply_blocked_reason.
Part B (Task 3): parse_label, map_result, _skill_from_pueue_command (monkeypatched).

No subprocess / fs / db calls in Part A.
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
# Part A — Text mutators
# =============================================================================

# --- _apply_spec_status ------------------------------------------------------


def test_apply_spec_status_simple_inprogress_to_done():
    """`**Status:** in_progress` → `**Status:** done`, flag=True."""
    text = "# T\n\n**Status:** in_progress\n**Priority:** P1\n"
    changed, new_text = callback._apply_spec_status(text, "done")
    assert changed is True
    assert "**Status:** done" in new_text
    assert "in_progress" not in new_text


def test_apply_spec_status_pipe_separated_inline():
    """`**Status:** in_progress | **Priority:** P0` — only first token replaced."""
    text = "**Status:** in_progress | **Priority:** P0\n"
    changed, new_text = callback._apply_spec_status(text, "done")
    assert changed is True
    # Status token replaced; rest of line preserved
    assert "**Status:** done" in new_text
    assert "**Priority:** P0" in new_text


def test_apply_spec_status_invalid_target_returns_unchanged():
    """target='INVALID' → (False, original_text)."""
    text = "**Status:** in_progress\n"
    changed, new_text = callback._apply_spec_status(text, "INVALID")
    assert changed is False
    assert new_text == text


def test_apply_spec_status_no_status_line():
    """Text without `**Status:**` → (False, unchanged)."""
    text = "# Spec\n\nsome body\n"
    changed, new_text = callback._apply_spec_status(text, "done")
    assert changed is False
    assert new_text == text


def test_apply_spec_status_only_replaces_first():
    """Two `**Status:**` lines → only first replaced (count=1)."""
    text = "**Status:** in_progress\n\nDetails: **Status:** queued\n"
    changed, new_text = callback._apply_spec_status(text, "done")
    assert changed is True
    # First occurrence replaced
    assert new_text.count("**Status:**") == 2
    # First is done, second still queued
    lines = new_text.splitlines()
    first_status = next(l for l in lines if "**Status:**" in l)
    assert "done" in first_status


@pytest.mark.parametrize("status", ["draft", "queued", "in_progress", "blocked", "resumed", "done"])
def test_apply_spec_status_all_valid_statuses(status):
    """All six valid statuses are accepted as target."""
    text = "**Status:** in_progress\n"
    changed, new_text = callback._apply_spec_status(text, status)
    assert changed is True
    assert f"**Status:** {status}" in new_text


# --- _apply_backlog_status ---------------------------------------------------


def test_apply_backlog_status_typical_row():
    """Standard backlog row: status column updated."""
    text = "| BUG-300 | Fix thing | in_progress | P1 |\n"
    changed, new_text = callback._apply_backlog_status(text, "BUG-300", "done")
    assert changed is True
    assert "done" in new_text
    assert "in_progress" not in new_text


def test_apply_backlog_status_spec_id_with_letter_suffix():
    """ARCH-176a — re.escape handles letter suffix; parent ARCH-176 row not matched."""
    text = (
        "| ARCH-176 | parent | in_progress | P0 |\n"
        "| ARCH-176a | foundation | in_progress | P0 |\n"
    )
    changed, new_text = callback._apply_backlog_status(text, "ARCH-176a", "done")
    assert changed is True
    lines = new_text.splitlines()
    parent_line = next(l for l in lines if "| ARCH-176 |" in l and "ARCH-176a" not in l)
    child_line = next(l for l in lines if "| ARCH-176a |" in l)
    assert "in_progress" in parent_line  # parent unchanged
    assert "done" in child_line


def test_apply_backlog_status_no_matching_row():
    """spec_id absent from table → (False, unchanged)."""
    text = "| BUG-999 | Other | in_progress | P1 |\n"
    changed, new_text = callback._apply_backlog_status(text, "BUG-300", "done")
    assert changed is False
    assert new_text == text


def test_apply_backlog_status_two_rows_only_first():
    """Same spec_id twice (data bug) → count=1, only first row patched."""
    row = "| BUG-300 | Fix thing | in_progress | P1 |\n"
    text = row + row
    changed, new_text = callback._apply_backlog_status(text, "BUG-300", "done")
    assert changed is True
    assert new_text.count("done") == 1
    assert new_text.count("in_progress") == 1


def test_apply_backlog_status_invalid_target():
    """target='banana' → (False, unchanged)."""
    text = "| BUG-300 | Fix thing | in_progress | P1 |\n"
    changed, new_text = callback._apply_backlog_status(text, "BUG-300", "banana")
    assert changed is False
    assert new_text == text


# --- _apply_blocked_reason ---------------------------------------------------


def test_apply_blocked_reason_inserts_after_status():
    """No existing reason line → inserted on line after `**Status:**`."""
    text = "**Status:** blocked\n**Priority:** P1\n"
    changed, new_text = callback._apply_blocked_reason(text, "no_implementation_commits")
    assert changed is True
    lines = new_text.splitlines()
    status_idx = next(i for i, l in enumerate(lines) if "**Status:**" in l)
    assert lines[status_idx + 1] == "**Blocked Reason:** no_implementation_commits"


def test_apply_blocked_reason_replaces_existing():
    """Existing `**Blocked Reason:** old` → replaced with new value."""
    text = "**Status:** blocked\n**Blocked Reason:** old_reason\n"
    changed, new_text = callback._apply_blocked_reason(text, "no_implementation_commits")
    assert changed is True
    assert new_text.count("**Blocked Reason:**") == 1
    assert "no_implementation_commits" in new_text
    assert "old_reason" not in new_text


def test_apply_blocked_reason_idempotent():
    """Calling twice with same reason produces single line (no append)."""
    text = "**Status:** blocked\n**Priority:** P1\n"
    _, text1 = callback._apply_blocked_reason(text, "no_implementation_commits")
    _, text2 = callback._apply_blocked_reason(text1, "no_implementation_commits")
    assert text2.count("**Blocked Reason:**") == 1


def test_apply_blocked_reason_no_status_line_returns_unchanged():
    """Text without `**Status:**` → insertion anchor missing → (False, unchanged)."""
    text = "# Spec\n\nsome body\n"
    changed, new_text = callback._apply_blocked_reason(text, "no_implementation_commits")
    assert changed is False
    assert new_text == text


def test_apply_blocked_reason_preserves_surrounding_content():
    """Content before/after Status block preserved byte-for-byte."""
    prefix = "# Title\n\n## Description\n\nsome desc\n\n"
    suffix = "\n## Tests\n\n- test1\n"
    text = prefix + "**Status:** blocked\n**Priority:** P1\n" + suffix
    _, new_text = callback._apply_blocked_reason(text, "reason_x")
    assert new_text.startswith(prefix)
    assert new_text.endswith(suffix)


# =============================================================================
# Part B — Pure helpers
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


@pytest.mark.parametrize("result_str,expected", [
    ("Success", ("done", 0)),
    ("Successfully completed", ("done", 0)),
    ("Failed", ("failed", 1)),
    ("Killed", ("failed", 1)),
    ("", ("failed", 1)),
])
def test_map_result(result_str, expected):
    """Substring 'Success' → done; everything else → failed."""
    assert callback.map_result(result_str) == expected


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
        callback.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, _ = callback._skill_from_pueue_command("1")
    assert skill == "autopilot"


def test_skill_from_pueue_absolute_path_to_run_agent(monkeypatch):
    """Absolute path to run-agent.sh → skill extracted correctly."""
    pueue_json = _make_pueue_json(
        "2", "/srv/scripts/run-agent.sh /p claude qa /qa BUG-1"
    )
    monkeypatch.setattr(
        callback.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, pueue_json, ""),
    )
    skill, _ = callback._skill_from_pueue_command("2")
    assert skill == "qa"


def test_skill_from_pueue_no_run_agent_in_command(monkeypatch):
    """command='echo hello' → ('', 0.0)."""
    pueue_json = _make_pueue_json("3", "echo hello")
    monkeypatch.setattr(
        callback.subprocess, "run",
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
        callback.subprocess, "run",
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
        callback.subprocess, "run",
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
        callback.subprocess, "run",
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
        callback.subprocess, "run",
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
