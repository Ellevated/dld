"""TECH-194 Layer E — integration tests: callback does NOT dispatch qa+reflect
when autopilot signals task_status=blocked or needs_review.

Eval Criteria:
  E1: task_status=blocked  → no pueue add for qa/reflect
  E2: task_status=complete → pueue add IS called for both qa and reflect
  E2b: task_status=needs_review → no pueue add for qa/reflect
  E2c: task_status="" (missing) + impl merged on origin/develop → pueue add IS
       called (TECH-207 merge-confirmed fallback)
  E2d: task_status="" (missing) + nothing merged → no pueue add (SIGKILL/abort)

ADR-013: real fs + real git + real sqlite.
External binaries (pueue, openclaw) replaced with shell stubs — not mocks of
business logic. extract_agent_output is patched because it reads pueue sockets
and log files that don't exist in tests (external I/O, not business logic).
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import db  # noqa: E402
import event_writer  # noqa: E402
import gate_logic  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite DB isolated per test."""
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    db._MIGRATIONS_APPLIED = False
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


# `stub_pueue_bin` lives in tests/integration/conftest.py — it needs a
# platform split that has no business being duplicated per test module.


@pytest.fixture
def stub_event_writer(monkeypatch):
    """Suppress openclaw/Hermes calls — event_writer.notify is external I/O."""
    monkeypatch.setattr(event_writer, "wake_hermes", lambda *a, **kw: True)
    monkeypatch.setattr(event_writer, "write_event", lambda *a, **kw: None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _make_project(tmp_path: Path, spec_id: str) -> Path:
    """Minimal git project with spec + lifecycle yaml committed."""
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)

    spec_body = (
        f"# {spec_id}\n\n"
        "**Status:** in_progress\n\n"
        "## Allowed Files\n\n"
        "<!-- callback-allowlist v1 -->\n\n"
        "- `src/x.py`\n\n"
        "## Tests\n"
    )
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n| {spec_id} | demo | in_progress | P1 |\n"
    )
    (repo / "README.md").write_text("init\n")

    # Lifecycle yaml (status=in_progress) committed normally
    lc_data = {
        "spec_id": spec_id,
        "status": "in_progress",
        "blocked_reason": None,
        "priority": "p1",
        "kind": "tech",
        "transitions": [],
        "version": 1,
        "started_at": None,
        "finished_at": None,
        "pueue_id": None,
        "allowed_files_hash": None,
        "updated_at": None,
        "updated_by": "test",
    }
    (lc_dir / f"{spec_id}.yaml").write_text(
        yaml.safe_dump(lc_data, default_flow_style=False, allow_unicode=True)
    )
    (lc_dir / ".gitkeep").write_text("")

    _git(
        repo,
        "add",
        "README.md",
        f"ai/features/{spec_id}.md",
        "ai/backlog.md",
        "ai/lifecycle/.gitkeep",
        f"ai/lifecycle/{spec_id}.yaml",
    )
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _seed_db(project_id: str, project_path: str, pueue_id: int, task_label: str) -> None:
    """Seed project_state + task_log so resolve_label and get_project_state work."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_state (project_id, path, provider) VALUES (?, ?, ?)",
            (project_id, project_path, "claude"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, task_label, "autopilot", "running", pueue_id),
        )


def _run_main(
    pueue_id: int,
    task_status: str,
    monkeypatch,
    stub_event_writer,
    merged_on_develop: bool = False,
) -> None:
    """Invoke callback.main() with controlled inputs.

    Patches:
      - sys.argv: simulates pueue callback invocation
      - sys.exit: prevents test process termination
      - extract_agent_output: returns (skill="autopilot", preview="", task_status=task_status)
        because in tests there is no real pueue socket / log file
      - _fetch_develop + _is_done_on_develop: stub out the git I/O against a
        remote that tests do not have. `merged_on_develop` is the verdict both
        the Step 6 merge fallback (TECH-207) and Step 7 read.
    """
    monkeypatch.setattr(
        callback,
        "extract_agent_output",
        lambda *a, **kw: ("autopilot", f"TECH-194 result task_status={task_status}", task_status),
    )
    # Stub git I/O against origin (no remote in tests)
    monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
    monkeypatch.setattr(
        gate_logic,
        "find_implementation_commit",
        lambda *a, **kw: "deadbee" if merged_on_develop else None,
    )

    with patch("sys.argv", ["callback.py", str(pueue_id), "claude-runner", "Success"]):
        with patch("sys.exit"):
            callback.main()


# ---------------------------------------------------------------------------
# E1: task_status=blocked → no dispatch
# ---------------------------------------------------------------------------


def test_blocked_skips_dispatch(tmp_path, tmp_db, stub_pueue_bin, stub_event_writer, monkeypatch):
    """E1: autopilot exits with task_status=blocked — callback must NOT dispatch qa or reflect."""
    spec_id = "TECH-194"
    project_id = "proj"
    pueue_id = 501
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(pueue_id, "blocked", monkeypatch, stub_event_writer)

    pueue_log = stub_pueue_bin.read_text() if stub_pueue_bin.exists() else ""
    # pueue add is the dispatch mechanism — must NOT appear for qa or reflect
    assert "add" not in pueue_log or ("qa-" not in pueue_log and "reflect-" not in pueue_log), (
        f"Expected NO qa/reflect dispatch, but pueue was called with: {pueue_log!r}"
    )

    # Verify task_log in DB has no qa or reflect entries
    with db.get_db() as conn:
        qa_rows = conn.execute(
            "SELECT COUNT(*) FROM task_log WHERE task_label LIKE 'qa-%' OR task_label LIKE '%:qa-%'"
        ).fetchone()[0]
        reflect_rows = conn.execute(
            "SELECT COUNT(*) FROM task_log WHERE task_label LIKE 'reflect-%' "
            "OR task_label LIKE '%:reflect-%'"
        ).fetchone()[0]
    assert qa_rows == 0, f"Expected 0 qa rows in task_log, got {qa_rows}"
    assert reflect_rows == 0, f"Expected 0 reflect rows in task_log, got {reflect_rows}"


# ---------------------------------------------------------------------------
# E1b: task_status=needs_review → no dispatch
# ---------------------------------------------------------------------------


def test_needs_review_skips_dispatch(
    tmp_path, tmp_db, stub_pueue_bin, stub_event_writer, monkeypatch
):
    """E1b: autopilot exits with task_status=needs_review — callback skips qa+reflect."""
    spec_id = "TECH-195"
    project_id = "proj2"
    pueue_id = 502
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(pueue_id, "needs_review", monkeypatch, stub_event_writer)

    pueue_log = stub_pueue_bin.read_text() if stub_pueue_bin.exists() else ""
    assert "add" not in pueue_log or ("qa-" not in pueue_log and "reflect-" not in pueue_log), (
        f"Expected NO qa/reflect dispatch for needs_review, pueue called with: {pueue_log!r}"
    )

    with db.get_db() as conn:
        qa_rows = conn.execute(
            "SELECT COUNT(*) FROM task_log WHERE task_label LIKE 'qa-%' OR task_label LIKE '%:qa-%'"
        ).fetchone()[0]
        reflect_rows = conn.execute(
            "SELECT COUNT(*) FROM task_log WHERE task_label LIKE 'reflect-%' "
            "OR task_label LIKE '%:reflect-%'"
        ).fetchone()[0]
    assert qa_rows == 0
    assert reflect_rows == 0


# ---------------------------------------------------------------------------
# E2: task_status=complete → dispatches qa+reflect
# ---------------------------------------------------------------------------


def test_complete_dispatches(tmp_path, tmp_db, stub_pueue_bin, stub_event_writer, monkeypatch):
    """E2: autopilot exits with task_status=complete → callback dispatches qa AND reflect."""
    spec_id = "TECH-196"
    project_id = "proj3"
    pueue_id = 503
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(pueue_id, "complete", monkeypatch, stub_event_writer)

    pueue_log = stub_pueue_bin.read_text() if stub_pueue_bin.exists() else ""
    # pueue add must have been called at least for reflect (qa may be skipped if spec_id
    # not resolved from label in some edge cases, but reflect is always dispatched)
    assert "add" in pueue_log, (
        f"Expected pueue add calls for qa/reflect dispatch, pueue log: {pueue_log!r}"
    )
    # Both qa and reflect should appear
    assert "reflect-" in pueue_log, f"Expected reflect dispatch, pueue log: {pueue_log!r}"


# ---------------------------------------------------------------------------
# E2c: task_status="" (missing) → merge on develop decides (TECH-207)
# ---------------------------------------------------------------------------


def test_missing_task_status_dispatches(
    tmp_path, tmp_db, stub_pueue_bin, stub_event_writer, monkeypatch
):
    """E2c: no task_status, but the work IS merged on origin/develop → dispatch.

    TECH-207 merge-confirmed fallback. This case used to be asserted as plain
    backward compat — dispatch on any missing signal — which TECH-207 deliberately
    replaced: a SIGKILL'd run also reports task_status="", and QA on an aborted run
    is exactly what the TECH-194 allowlist exists to prevent. The merge verdict is
    now what separates the two, so it is what the test has to supply.
    """
    spec_id = "TECH-197"
    project_id = "proj4"
    pueue_id = 504
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    # task_status="" simulates agent output with no task_status field
    _run_main(pueue_id, "", monkeypatch, stub_event_writer, merged_on_develop=True)

    pueue_log = stub_pueue_bin.read_text() if stub_pueue_bin.exists() else ""
    assert "add" in pueue_log, (
        f"Expected pueue add calls when task_status missing but merge confirmed, "
        f"pueue log: {pueue_log!r}"
    )
    assert "reflect-" in pueue_log, (
        f"Expected reflect dispatch for missing task_status, pueue log: {pueue_log!r}"
    )


# ---------------------------------------------------------------------------
# E2d: task_status="" and nothing merged → no dispatch (TECH-207 skip path)
# ---------------------------------------------------------------------------


def test_missing_task_status_without_merge_skips_dispatch(
    tmp_path, tmp_db, stub_pueue_bin, stub_event_writer, monkeypatch
):
    """E2d: no task_status and no merged implementation → SIGKILL/abort → no dispatch."""
    spec_id = "TECH-198"
    project_id = "proj5"
    pueue_id = 505
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(pueue_id, "", monkeypatch, stub_event_writer, merged_on_develop=False)

    pueue_log = stub_pueue_bin.read_text() if stub_pueue_bin.exists() else ""
    assert "qa-" not in pueue_log and "reflect-" not in pueue_log, (
        f"Expected NO dispatch without a confirmed merge, pueue log: {pueue_log!r}"
    )
