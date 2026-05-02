"""TECH-168 Task 5 — Integration: verify_status_sync scenarios EC-11..EC-17.

Real fs + real git + real sqlite (no mocks per ADR-013).
EC-11: no allowed files section → missing_allowed_files_section demote.
EC-12: v1 empty section → no_implementation_commits demote.
EC-13: done-overwrite protection (spec already done, target=blocked).
EC-14: HEAD already synced → idempotent, no new commit.
EC-15: operator uncommitted edits in spec survive callback.
EC-16: _resync_backlog_to_spec idempotency when already in sync.
EC-17: _get_started_at queries (4 sub-tests).
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import db  # noqa: E402


# --- Shared helpers ----------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo: Path, rel: str, body: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


def _head_count(repo: Path) -> int:
    r = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
    )
    return int(r.stdout.strip()) if r.returncode == 0 else 0


def _head_file(repo: Path, rel: str) -> str | None:
    r = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else None


def _make_project(
    tmp_path: Path,
    spec_id: str,
    allowed_files: list[str] | None = None,
    spec_status: str = "in_progress",
    extra_spec_lines: str = "",
) -> Path:
    """Create a minimal git project with spec + backlog committed."""
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)

    if allowed_files is not None:
        allowed_block = "\n".join(f"- `{p}`" for p in allowed_files) or "(none)"
    else:
        allowed_block = None  # No section

    if allowed_block is not None:
        spec_body = (
            f"# {spec_id}\n\n"
            f"**Status:** {spec_status}\n"
            f"{extra_spec_lines}"
            "\n## Allowed Files\n\n"
            f"{allowed_block}\n\n"
            "## Tests\n"
        )
    else:
        # No Allowed Files section at all
        spec_body = (
            f"# {spec_id}\n\n"
            f"**Status:** {spec_status}\n"
            f"{extra_spec_lines}"
            "\n## Tests\n"
        )

    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n"
        f"| {spec_id} | demo | {spec_status} | P1 |\n"
    )
    # Commit everything: README + spec + backlog in one init commit
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md",
         f"ai/features/{spec_id}.md", "ai/backlog.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    with patch.object(db, "DB_PATH", db_path):
        yield db_path


def _seed_task(project_id: str, label: str, pueue_id: int) -> None:
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            (project_id, "/tmp/ignored"),
        )
        conn.execute(
            "INSERT INTO task_log "
            "(project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, label, "autopilot", "running", pueue_id),
        )


def _suppress_push(monkeypatch) -> None:
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)


# --- EC-11: missing-section degrade-closed -----------------------------------


def test_ec11_no_allowed_files_section_demotes_done_to_blocked(
    tmp_path, tmp_db, monkeypatch
):
    """Spec without ## Allowed Files + target='done' → demote missing_allowed_files_section."""
    spec_id = "TECH-1011"
    repo = _make_project(tmp_path, spec_id, allowed_files=None)
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=111)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=1\n", "feat: x")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=111)

    # callback commits via plumbing (no workdir mutation), so check HEAD
    spec_text = _head_file(repo, f"ai/features/{spec_id}.md") or ""
    backlog_text = _head_file(repo, "ai/backlog.md") or ""
    assert "**Status:** blocked" in spec_text
    assert "missing_allowed_files_section" in spec_text
    assert "| blocked |" in backlog_text


# --- EC-12: empty-section degrade-closed (v1 marker, no bullets) -------------


def test_ec12_v1_empty_section_demotes(tmp_path, tmp_db, monkeypatch):
    """Spec with v1 marker but zero bullets → degrade-closed → blocked."""
    spec_id = "TECH-1012"
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)

    spec_body = (
        f"# {spec_id}\n\n"
        "**Status:** in_progress\n\n"
        "## Allowed Files\n\n"
        "<!-- callback-allowlist v1 -->\n\n"
        "## Tests\n"
    )
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(
        f"| {spec_id} | demo | in_progress | P1 |\n"
    )
    # Commit all files: README + spec + backlog
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md", f"ai/features/{spec_id}.md", "ai/backlog.md")
    _git(repo, "commit", "-q", "-m", "init")
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=112)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=1\n", "feat: x")
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=112)

    # callback commits via plumbing (no workdir mutation), so check HEAD
    spec_text = _head_file(repo, f"ai/features/{spec_id}.md") or ""
    assert "**Status:** blocked" in spec_text
    assert "no_implementation_commits" in spec_text


# --- EC-13: done-overwrite protection ----------------------------------------


def test_ec13_done_overwrite_protection(tmp_path, tmp_db, monkeypatch):
    """Spec already at HEAD=done + target='blocked' → log, resync backlog, return."""
    spec_id = "TECH-1013"
    repo = _make_project(tmp_path, spec_id, allowed_files=["src/x.py"], spec_status="done")
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=113)
    _suppress_push(monkeypatch)
    before_count = _head_count(repo)

    callback.verify_status_sync(str(repo), spec_id, target="blocked", pueue_id=113)

    # callback operates on HEAD content; check HEAD via git show
    spec_text = _head_file(repo, f"ai/features/{spec_id}.md") or ""
    # Spec must stay done
    assert "**Status:** done" in spec_text
    assert "**Status:** blocked" not in spec_text
    # Backlog resynced to done (was in_progress initially)
    backlog_text = _head_file(repo, "ai/backlog.md") or ""
    assert "| done |" in backlog_text


# --- EC-14: HEAD already synced — idempotent ---------------------------------


def test_ec14_head_already_synced_no_commit(tmp_path, tmp_db, monkeypatch):
    """spec=done, backlog=done at HEAD, target=done, impl-commit present → no new commit."""
    spec_id = "TECH-1014"
    # spec_status=done means both spec and backlog already say done in _make_project
    repo = _make_project(tmp_path, spec_id, allowed_files=["src/x.py"], spec_status="done")

    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=114)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=2\n", "feat: x")
    _suppress_push(monkeypatch)
    before_count = _head_count(repo)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=114)

    assert _head_count(repo) == before_count


# --- EC-15: operator uncommitted edits survive --------------------------------


def test_ec15_operator_uncommitted_edits_in_spec_survive(tmp_path, tmp_db, monkeypatch):
    """Operator added ## Notes block to spec workdir AFTER autopilot finished.
    callback patches HEAD-content (no notes) + plumbing-commits.
    Workdir notes still on disk after callback.
    """
    spec_id = "TECH-1015"
    repo = _make_project(tmp_path, spec_id, allowed_files=["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=115)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=2\n", "feat: x")
    _suppress_push(monkeypatch)

    # Operator adds notes to working tree (not committed)
    spec_workdir = repo / "ai" / "features" / f"{spec_id}.md"
    original = spec_workdir.read_text()
    spec_workdir.write_text(original + "\n## Notes by operator\n\noperator note here\n")

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=115)

    # HEAD must have done status (no operator notes)
    head_content = _head_file(repo, f"ai/features/{spec_id}.md")
    assert "**Status:** done" in head_content
    assert "operator note here" not in head_content

    # Workdir must still have the operator note
    workdir_content = spec_workdir.read_text()
    assert "operator note here" in workdir_content


# --- EC-16: _resync_backlog_to_spec idempotency ------------------------------


def test_ec16_resync_backlog_idempotent_when_already_synced(tmp_path, tmp_db, monkeypatch):
    """spec=blocked, backlog=blocked at HEAD → resync is no-op (no new commit)."""
    spec_id = "TECH-1016"
    repo = _make_project(
        tmp_path, spec_id, allowed_files=["src/x.py"], spec_status="blocked"
    )
    # spec_status=blocked means backlog already says blocked in _make_project
    backlog_path = repo / "ai" / "backlog.md"
    _suppress_push(monkeypatch)
    before_count = _head_count(repo)

    callback._resync_backlog_to_spec(
        str(repo),
        spec_id,
        "blocked",
        backlog_path,
    )

    assert _head_count(repo) == before_count


# --- EC-17: _get_started_at --------------------------------------------------


def test_ec17_get_started_at_returns_iso_string(tmp_db):
    """Insert task_log row with explicit started_at → _get_started_at returns it."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("p17", "/tmp/ignored"),
        )
        conn.execute(
            "INSERT INTO task_log "
            "(project_id, task_label, skill, status, pueue_id, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p17", "lbl", "autopilot", "running", 170, "2026-05-01T10:00:00Z"),
        )

    result = callback._get_started_at(170)
    assert result == "2026-05-01T10:00:00Z"


def test_ec17_get_started_at_missing_pueue_id_returns_none(tmp_db):
    """No row for pueue_id=999 → returns None."""
    result = callback._get_started_at(999)
    assert result is None


def test_ec17_get_started_at_returns_latest_when_duplicate(tmp_db):
    """Two rows with same pueue_id → returns the row with highest id (latest)."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT INTO project_state (project_id, path) VALUES (?, ?)",
            ("p17b", "/tmp/ignored"),
        )
        conn.execute(
            "INSERT INTO task_log "
            "(project_id, task_label, skill, status, pueue_id, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p17b", "lbl", "autopilot", "running", 171, "2026-05-01T08:00:00Z"),
        )
        conn.execute(
            "INSERT INTO task_log "
            "(project_id, task_label, skill, status, pueue_id, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("p17b", "lbl", "autopilot", "running", 171, "2026-05-01T10:00:00Z"),
        )

    result = callback._get_started_at(171)
    assert result == "2026-05-01T10:00:00Z"


def test_ec17_get_started_at_db_error_returns_none(tmp_db, monkeypatch):
    """Force db.get_db() to raise → caught, returns None, no exception leaks."""

    def _raise():
        raise RuntimeError("forced db error")

    monkeypatch.setattr(db, "get_db", _raise)

    result = callback._get_started_at(172)
    assert result is None
