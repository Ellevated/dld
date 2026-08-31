"""TECH-168 Task 5 — Integration: verify_status_sync scenarios EC-11..EC-17.

ARCH-186: assertions rewritten to read from lifecycle.yaml (SoT) instead of
markdown files. EC-16 removed (tests _resync_backlog_to_spec which is gone).

Real fs + real git + real sqlite (no mocks per ADR-013).
EC-11: no allowed files section → missing_allowed_files_section degrade.
EC-12: v1 empty section → no_implementation_commits demote.
EC-13: done-overwrite protection (spec already done, target=blocked).
EC-14: HEAD already synced → idempotent, no new commit.
EC-15: operator uncommitted edits in spec survive callback.
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

import yaml  # noqa: E402

import callback  # noqa: E402
import db  # noqa: E402
import gate_logic  # noqa: E402
import lifecycle  # noqa: E402


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


def _head_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


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
    """Create a minimal git project with spec + backlog + lifecycle dir committed."""
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    # lifecycle dir must exist in HEAD so git read-tree works for lifecycle writes
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("")

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
        spec_body = f"# {spec_id}\n\n**Status:** {spec_status}\n{extra_spec_lines}\n## Tests\n"

    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status | P |\n|---|---|---|---|\n"
        f"| {spec_id} | demo | {spec_status} | P1 |\n"
    )
    # Commit everything: README + spec + backlog + lifecycle in one init commit
    (repo / "README.md").write_text("init\n")
    _git(
        repo,
        "add",
        "README.md",
        f"ai/features/{spec_id}.md",
        "ai/backlog.md",
        "ai/lifecycle/.gitkeep",
    )
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


def _seed_lifecycle_yaml(repo: Path, spec_id: str) -> None:
    """Write minimal lifecycle.yaml (status=queued) via normal git add+commit."""
    _seed_lifecycle_yaml_with_status(repo, spec_id, "queued")


def _seed_lifecycle_yaml_with_status(repo: Path, spec_id: str, status: str) -> None:
    """Write minimal lifecycle.yaml with given status via normal git add+commit.

    Using normal git add+commit (not lifecycle plumbing) ensures the YAML
    survives subsequent normal commits — plumbing writes exist only in the
    object store and are lost when the next normal commit rebuilds the tree
    from the working directory index.
    """
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "spec_id": spec_id,
        "status": status,
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
    yaml_path = lc_dir / f"{spec_id}.yaml"
    yaml_path.write_text(yaml.safe_dump(data, default_flow_style=False, allow_unicode=True))
    _git(repo, "add", f"ai/lifecycle/{spec_id}.yaml")
    _git(repo, "commit", "-q", "-m", "chore: lifecycle test-seed")


# --- EC-11: missing-section degrade-open → done ----------------------------


def test_ec11_no_allowed_files_section_blocks(tmp_path, tmp_db, monkeypatch):
    """No ## Allowed Files section → blocked with missing_allowed_files.

    2026-05-21 redesign: missing Allowed Files is no longer degrade-open.
    Gate cannot evaluate without a file list → fail-closed → blocked.
    """
    spec_id = "TECH-1011"
    repo = _make_project(tmp_path, spec_id, allowed_files=None)
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=111)
    _seed_lifecycle_yaml(repo, spec_id)
    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=111)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None, "lifecycle.yaml must be written"
    assert data["status"] == "blocked"
    assert "missing_allowed_files" in (data.get("blocked_reason") or "")


# --- EC-12: empty-section degrade-closed (v1 marker, no bullets) -----------


def test_ec12_v1_empty_section_demotes(tmp_path, tmp_db, monkeypatch):
    """Spec with v1 marker but zero bullets → degrade-closed → blocked."""
    spec_id = "TECH-1012"
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("")

    spec_body = (
        f"# {spec_id}\n\n"
        "**Status:** in_progress\n\n"
        "## Allowed Files\n\n"
        "<!-- callback-allowlist v1 -->\n\n"
        "## Tests\n"
    )
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(spec_body)
    (repo / "ai" / "backlog.md").write_text(f"| {spec_id} | demo | in_progress | P1 |\n")
    (repo / "README.md").write_text("init\n")
    _git(
        repo,
        "add",
        "README.md",
        f"ai/features/{spec_id}.md",
        "ai/backlog.md",
        "ai/lifecycle/.gitkeep",
    )
    _git(repo, "commit", "-q", "-m", "init")
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=112)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=1\n", "feat: x")
    _suppress_push(monkeypatch)

    # Pre-seed lifecycle so write_lifecycle(existing=...) path stores blocked_reason
    _seed_lifecycle_yaml(repo, spec_id)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=112)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None, "lifecycle.yaml must be written"
    assert data["status"] == "blocked"
    assert data.get("blocked_reason") == "empty_allowed_files"


# --- EC-13: done-overwrite protection ----------------------------------------


def test_ec13_done_overwrite_protection(tmp_path, tmp_db, monkeypatch):
    """Lifecycle already at done + target='blocked' → skipped, stays done."""
    spec_id = "TECH-1013"
    repo = _make_project(tmp_path, spec_id, allowed_files=["src/x.py"], spec_status="done")
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=113)

    # Pre-seed lifecycle.yaml as done via normal commit so it survives later writes
    _seed_lifecycle_yaml_with_status(repo, spec_id, "done")

    _suppress_push(monkeypatch)

    callback.verify_status_sync(str(repo), spec_id, target="blocked", pueue_id=113)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "done"


# --- EC-14: HEAD already synced — idempotent ---------------------------------


def test_ec14_head_already_synced_no_commit(tmp_path, tmp_db, monkeypatch):
    """lifecycle=done, target=done, impl-commit present → no new commit (idempotent)."""
    spec_id = "TECH-1014"
    repo = _make_project(tmp_path, spec_id, allowed_files=["src/x.py"], spec_status="done")
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=114)
    time.sleep(1.1)
    _commit(repo, "src/x.py", "y=2\n", "feat: x")

    # Pre-seed lifecycle.yaml as done via normal commit
    _seed_lifecycle_yaml_with_status(repo, spec_id, "done")

    _suppress_push(monkeypatch)
    before_count = _head_count(repo)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=114)

    assert _head_count(repo) == before_count


# --- EC-15: operator uncommitted edits survive --------------------------------


def test_ec15_operator_uncommitted_edits_in_spec_survive(tmp_path, tmp_db, monkeypatch):
    """Operator added ## Notes to spec workdir AFTER autopilot finished.
    callback writes ONLY to lifecycle.yaml (no markdown edits).
    Spec workdir content remains untouched.
    """
    spec_id = "TECH-1015"
    repo = _make_project(tmp_path, spec_id, allowed_files=["src/x.py"])
    _seed_task("proj", f"autopilot-{spec_id}", pueue_id=115)
    _seed_lifecycle_yaml(repo, spec_id)
    _suppress_push(monkeypatch)

    # Gate stubs: gate=True so lifecycle becomes done
    monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
    monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a: "deadbee")

    # Operator adds notes to working tree (not committed)
    spec_workdir = repo / "ai" / "features" / f"{spec_id}.md"
    original_content = spec_workdir.read_text()
    operator_note = "\n## Notes by operator\n\noperator note here\n"
    spec_workdir.write_text(original_content + operator_note)

    before_head = _head_sha(repo)

    callback.verify_status_sync(str(repo), spec_id, target="done", pueue_id=115)

    # lifecycle.yaml must say done
    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "done"

    # spec.md workdir must still contain operator's note (callback never touches it)
    workdir_content = spec_workdir.read_text()
    assert "operator note here" in workdir_content

    # spec.md in HEAD must be unchanged from before callback ran (no markdown edits)
    head_content = _head_file(repo, f"ai/features/{spec_id}.md")
    assert head_content is not None
    assert "operator note here" not in head_content

    # Everything callback committed touches ai/lifecycle/ (plus the folded
    # ai/backlog.md status render) and never ai/features/. Anchored on the SHA
    # captured above: a fixed `HEAD~3` outlived the extra commit it counted on
    # — ARCH-196 dropped the separate backlog-render commit, leaving only three
    # in the repo, so the range named a revision that does not exist and git
    # answered with empty stdout the assertion below then read as a pass.
    new_commit_files = subprocess.run(
        ["git", "-C", str(repo), "log", "--name-only", "--format=", f"{before_head}..HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert new_commit_files, "callback must have committed something"
    assert "ai/lifecycle/" in new_commit_files
    assert "ai/features/" not in new_commit_files


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
