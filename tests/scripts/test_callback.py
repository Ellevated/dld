"""Tests for scripts/vps/callback.py — BUG-164 regression tests."""

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "vps")
sys.path.insert(0, SCRIPT_DIR)

import db  # noqa: E402
import callback  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path):
    """Create temporary SQLite DB with schema."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    schema_file = Path(SCRIPT_DIR) / "schema.sql"
    conn.executescript(schema_file.read_text())
    conn.close()
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


@pytest.fixture
def tmp_logs(tmp_path):
    """Create temporary logs directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    with patch.object(callback, "SCRIPT_DIR", tmp_path):
        yield log_dir


# --- resolve_label tests ---


def test_resolve_label_from_db(tmp_db):
    """DB returns task_label → correct composite label without pueue CLI."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("myproj", "/home/myproj"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("myproj", "autopilot-BUG-164", "autopilot", "queued", 55),
        )

    label = callback.resolve_label("55")
    assert label == "myproj:autopilot-BUG-164"


def test_resolve_label_fallback_to_pueue(tmp_db):
    """DB returns None → falls back to pueue status → returns label."""
    pueue_response = json.dumps(
        {"tasks": {"77": {"label": "proj2:FTR-100", "status": {"Running": {}}}}}
    )
    mock_result = MagicMock()
    mock_result.stdout = pueue_response

    with patch("subprocess.run", return_value=mock_result):
        label = callback.resolve_label("77")
    assert label == "proj2:FTR-100"


def test_resolve_label_all_fail(tmp_db):
    """DB empty + pueue fails → returns 'unknown'."""
    with patch("subprocess.run", side_effect=Exception("socket")):
        label = callback.resolve_label("999")
    assert label == "unknown"


# --- extract_agent_output tests ---


def test_extract_agent_output_from_logfile(tmp_db, tmp_logs):
    """Log file with JSON → extracts skill and preview correctly."""
    # Setup project in DB
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("testproj", "/home/dld/projects/testproj"),
        )

    # Create log file
    log_data = {
        "exit_code": 0,
        "project": "testproj",
        "skill": "autopilot",
        "task": "/autopilot BUG-164",
        "result_preview": "Fixed callback pueue socket mismatch",
    }
    log_file = tmp_logs / "testproj-20260320-120000.log"
    log_file.write_text(json.dumps(log_data))

    skill, preview, _ = callback.extract_agent_output("42", "testproj")
    assert skill == "autopilot"
    assert "Fixed callback" in preview


def test_extract_agent_output_no_logfile(tmp_db, tmp_logs):
    """No matching log file + no DB skill → falls through to pueue fallback."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("emptyproj", "/home/dld/projects/emptyproj"),
        )

    with patch("subprocess.run", side_effect=Exception("no pueue")):
        skill, preview, _ = callback.extract_agent_output("99", "emptyproj")
    assert skill == ""
    assert preview == ""


def test_extract_agent_output_db_skill_fallback(tmp_db, tmp_logs):
    """No log file but DB has skill → returns skill from DB."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("proj3", "/home/dld/projects/proj3"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("proj3", "autopilot-TECH-100", "autopilot", "queued", 88),
        )

    # No log file for proj3, but DB has the skill
    with patch("subprocess.run", side_effect=Exception("no pueue")):
        skill, preview, _ = callback.extract_agent_output("88", "proj3")
    assert skill == "autopilot"
    assert preview == ""  # no preview from DB


def test_extract_agent_output_no_project_id():
    """No project_id → skips log file, tries DB + pueue fallback."""
    with patch("subprocess.run", side_effect=Exception("no pueue")):
        skill, preview, _ = callback.extract_agent_output("1")
    assert skill == ""
    assert preview == ""


# --- Integration test ---


def test_callback_full_flow_without_pueue(tmp_db, tmp_logs):
    """End-to-end: DB + log file → resolves label + extracts output → QA dispatch attempted."""
    # Setup DB
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path, provider) VALUES (?, ?, ?)",
            ("dld", "/home/dld/projects/dld", "claude"),
        )
        # Acquire slot
        conn.execute(
            "UPDATE compute_slots SET project_id = ?, pueue_id = ? WHERE slot_number = 1",
            ("dld", 100),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dld", "autopilot-BUG-164", "autopilot", "queued", 100),
        )

    # Create log file
    log_data = {
        "exit_code": 0,
        "project": "dld",
        "skill": "autopilot",
        "task": "/autopilot BUG-164",
        "result_preview": "Spec: BUG-164 → done",
    }
    log_file = tmp_logs / "dld-20260320-120000.log"
    log_file.write_text(json.dumps(log_data))

    # Verify resolve_label works from DB
    label = callback.resolve_label("100")
    assert label == "dld:autopilot-BUG-164"

    # Verify extract works from log file
    skill, preview, _ = callback.extract_agent_output("100", "dld")
    assert skill == "autopilot"
    assert "BUG-164" in preview

    # Verify spec_id resolution
    project_id, task_label = callback.parse_label(label)
    spec_id = callback.resolve_spec_id(task_label, preview, "/home/dld/projects/dld")
    assert spec_id == "BUG-164"


# --- verify_status_sync tests ---

# Helpers shared by git-plumbing verify_status_sync tests.
# verify_status_sync reads/writes via git HEAD (not disk), so tests need a real
# git repo. Equivalent integration tests: tests/integration/test_callback_status_sync.py

import subprocess as _subprocess


def _git(repo: Path, *args: str) -> None:
    _subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _make_git_repo(
    tmp_path: Path, spec_id: str, spec_filename: str, spec_status: str, backlog_status: str
) -> tuple:
    """Init git repo with committed spec + backlog. Returns (repo, spec_path, backlog_path)."""
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    spec = repo / "ai" / "features" / spec_filename
    spec.write_text(f"# Spec\n\n**Status:** {spec_status}\n")
    backlog = repo / "ai" / "backlog.md"
    backlog.write_text(f"| ID | Task | Status |\n| {spec_id} | task | {backlog_status} |\n")
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md", f"ai/features/{spec_filename}", "ai/backlog.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo, spec, backlog


def _head(repo: Path, rel: str) -> str:
    """Read a path from git HEAD (not working tree)."""
    r = _subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else ""


def _suppress_push_sync(monkeypatch) -> None:
    real_run = _subprocess.run

    def _fake(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return _subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", _fake)


def test_verify_status_sync_both_done(tmp_path, caplog):
    """Both spec and backlog marked done → info log, no warning."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    spec = features / "FTR-200-some-feature.md"
    spec.write_text("# Feature\n\n**Status:** done | **Priority:** P1 | **Date:** 2026-03-28\n")

    backlog = tmp_path / "ai" / "backlog.md"
    backlog.write_text(
        "| ID | Task | Status |\n|----|------|--------|\n| FTR-200 | Some feature | done |\n"
    )

    import logging

    with caplog.at_level(logging.INFO):
        callback.verify_status_sync(str(tmp_path), "FTR-200")

    assert any("both spec and backlog are done" in r.message for r in caplog.records)
    assert not any(
        "STATUS_SYNC" in r.message and r.levelno >= logging.WARNING for r in caplog.records
    )


def test_verify_status_sync_fixes_spec(tmp_path, monkeypatch, caplog):
    """Spec in_progress → auto-fixed to done in git HEAD."""
    import logging

    repo, _, _ = _make_git_repo(tmp_path, "BUG-300", "BUG-300-fix-thing.md", "in_progress", "done")
    _suppress_push_sync(monkeypatch)

    with caplog.at_level(logging.INFO):
        callback.verify_status_sync(str(repo), "BUG-300")

    assert "**Status:** done" in _head(repo, "ai/features/BUG-300-fix-thing.md")
    assert any("auto-fixed" in r.message for r in caplog.records)


def test_verify_status_sync_fixes_backlog(tmp_path, monkeypatch, caplog):
    """Backlog in_progress → auto-fixed to done in git HEAD."""
    import logging

    repo, _, _ = _make_git_repo(tmp_path, "TECH-400", "TECH-400-refactor.md", "done", "in_progress")
    _suppress_push_sync(monkeypatch)

    with caplog.at_level(logging.INFO):
        callback.verify_status_sync(str(repo), "TECH-400")

    assert "done" in _head(repo, "ai/backlog.md").split("TECH-400")[1].split("\n")[0]
    assert any("auto-fixed" in r.message for r in caplog.records)


def test_verify_status_sync_fixes_both(tmp_path, monkeypatch, caplog):
    """Both in_progress → both auto-fixed to done, git plumbing commit runs."""
    import logging

    repo, _, _ = _make_git_repo(
        tmp_path, "FTR-500", "FTR-500-new-thing.md", "in_progress", "in_progress"
    )
    _suppress_push_sync(monkeypatch)

    with caplog.at_level(logging.INFO):
        callback.verify_status_sync(str(repo), "FTR-500")

    assert "**Status:** done" in _head(repo, "ai/features/FTR-500-new-thing.md")
    assert "done" in _head(repo, "ai/backlog.md").split("FTR-500")[1].split("\n")[0]
    assert any("auto-fixed 2 file(s)" in r.message for r in caplog.records)


def test_verify_status_sync_failed_sets_blocked(tmp_path, monkeypatch, caplog):
    """target=blocked → spec and backlog set to blocked in git HEAD."""
    import logging

    repo, _, _ = _make_git_repo(
        tmp_path, "BUG-600", "BUG-600-crash.md", "in_progress", "in_progress"
    )
    _suppress_push_sync(monkeypatch)

    with caplog.at_level(logging.INFO):
        callback.verify_status_sync(str(repo), "BUG-600", target="blocked")

    assert "**Status:** blocked" in _head(repo, "ai/features/BUG-600-crash.md")
    assert "blocked" in _head(repo, "ai/backlog.md").split("BUG-600")[1].split("\n")[0]


def test_verify_status_sync_respects_blocked(tmp_path, monkeypatch, caplog):
    """Spec blocked at HEAD, target=done → stays blocked (spec-authority guard)."""
    import logging

    repo, _, _ = _make_git_repo(
        tmp_path, "FTR-700", "FTR-700-blocked-task.md", "blocked", "blocked"
    )
    _suppress_push_sync(monkeypatch)

    with caplog.at_level(logging.INFO):
        callback.verify_status_sync(str(repo), "FTR-700", target="done")

    assert "**Status:** blocked" in _head(repo, "ai/features/FTR-700-blocked-task.md")
    assert any("spec is blocked at HEAD" in r.message for r in caplog.records)


def test_apply_spec_status_rejects_invalid_status():
    """Invalid target → _apply_spec_status returns (False, unchanged text)."""
    text = "# Bug\n\n**Status:** in_progress\n"
    ok, result = callback._apply_spec_status(text, "INVALID")
    assert ok is False
    assert result == text
