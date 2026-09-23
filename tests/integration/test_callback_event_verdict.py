"""TECH-224 — end-to-end tests: Hermes wakes on the lifecycle *verdict*, not on
pueue's exit code.

Eval Criteria (spec §Eval Criteria):
  EC-1: autopilot signals blocked, gate would say done  -> one event, status=blocked,
        message names autopilot_signaled_blocked. Red today (event says done).
  EC-2: ordinary done                                    -> one event, status=done.
        Regression guard, green today.
  EC-3: autopilot crashed (exit!=0), branch pushed but not merged -> one event,
        status=blocked, message names branch_pushed_not_merged. Red today (0 events
        — Step 5 only fires for skill in ("autopilot","qa","reflect","spark") AND
        status=="done" or (status=="failed" and skill=="qa"); a failed autopilot run
        gets none).
  EC-4: Step 7 (verify_status_sync) raises -> callback still exits 0 and wakes once,
        with a "вердикт lifecycle недоступен" note. Red today (no such note).
  EC-5: no lifecycle record for the spec -> one event noting no_decision. Red today.
  EC-8: qa/reflect skills are unaffected — their event is Step 5, Step 7 never runs
        for them. Regression guard, green today.

ADR-013: real fs + real git + real sqlite. `event_writer.wake_hermes` is the one
external boundary replaced (fire-and-forget hermes CLI spawn) — `write_event` runs
for real, so assertions read the JSON it actually wrote.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import callback_sync  # noqa: E402
import db  # noqa: E402
import event_writer  # noqa: E402
import gate_logic  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Fresh SQLite DB isolated per test. No unittest.mock (D2) — monkeypatch only."""
    import sqlite3

    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (SCRIPT_DIR / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_MIGRATIONS_APPLIED", False)
    return db_path


@pytest.fixture
def wakes(monkeypatch):
    """Recorder for event_writer.wake_hermes — the one external boundary (Hermes
    CLI spawn). event_writer.write_event runs for real; assertions read its JSON.
    """
    calls: list[tuple[str, str, Path | None]] = []

    def _recorder(project_path, skill, status, event_file=None):
        calls.append((skill, status, event_file))
        return True

    monkeypatch.setattr(event_writer, "wake_hermes", _recorder)
    return calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _make_project(tmp_path: Path, spec_id: str, with_lifecycle: bool = True) -> Path:
    """Minimal git project with spec (+ optionally lifecycle yaml) committed."""
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

    add_paths = ["README.md", f"ai/features/{spec_id}.md", "ai/backlog.md"]

    if with_lifecycle:
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
        add_paths.append(f"ai/lifecycle/{spec_id}.yaml")

    (lc_dir / ".gitkeep").write_text("")
    add_paths.append("ai/lifecycle/.gitkeep")

    _git(repo, "add", *add_paths)
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _seed_db(
    project_id: str, project_path: str, pueue_id: int, task_label: str, skill: str = "autopilot"
) -> None:
    """Seed project_state + task_log so resolve_label and get_project_state work."""
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_state (project_id, path, provider) VALUES (?, ?, ?)",
            (project_id, project_path, "claude"),
        )
        conn.execute(
            "INSERT INTO task_log (project_id, task_label, skill, status, pueue_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (project_id, task_label, skill, "running", pueue_id),
        )


def _run_main(
    monkeypatch,
    pueue_id: int,
    result: str,
    exit_code: str | None,
    skill: str,
    task_status: str,
    merged: bool,
) -> None:
    """Invoke callback.main() end-to-end with the git/gate boundary controlled.

    `gate_logic.find_implementation_commit` stands in for "is this spec merged
    on origin/develop" wherever no real remote is set up (EC-1/2/4/5); EC-3
    sets up a real bare origin instead and leaves `merged=False` so the real
    branch_state() ahead-count produces branch_pushed_not_merged.
    """
    monkeypatch.setattr(
        callback,
        "extract_agent_output",
        lambda *a, **kw: (skill, "", task_status),
    )
    monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
    monkeypatch.setattr(
        gate_logic,
        "find_implementation_commit",
        lambda *a, **kw: "deadbee" if merged else None,
    )
    monkeypatch.setattr(callback_sync.time, "sleep", lambda *_a: None)

    argv = ["callback.py", str(pueue_id), "claude-runner", result]
    if exit_code is not None:
        argv.append(str(exit_code))
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys, "exit", lambda *_a, **_kw: None)

    callback.main()


def _events(wakes: list[tuple[str, str, Path | None]], skill: str) -> list[dict]:
    """Read the real JSON event_writer.write_event wrote, for every wake of `skill`."""
    out = []
    for s, _status, event_file in wakes:
        if s == skill and event_file is not None:
            out.append(json.loads(Path(event_file).read_text(encoding="utf-8")))
    return out


# ---------------------------------------------------------------------------
# EC-1: autopilot signals blocked, gate would say done -> event says blocked
# ---------------------------------------------------------------------------


def test_ec1_signaled_blocked_wakes_blocked(tmp_path, tmp_db, stub_pueue_bin, wakes, monkeypatch):
    spec_id = "TECH-901"
    project_id = "proj"
    pueue_id = 601
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(monkeypatch, pueue_id, "Success", None, "autopilot", "blocked", merged=True)

    events = _events(wakes, "autopilot")
    assert len(events) == 1, f"expected exactly 1 autopilot event, got {events!r}"
    assert events[0]["status"] == "blocked", events[0]
    assert "autopilot_signaled_blocked" in events[0]["message"], events[0]


# ---------------------------------------------------------------------------
# EC-2: ordinary done — regression guard
# ---------------------------------------------------------------------------


def test_ec2_done_wakes_once_done(tmp_path, tmp_db, stub_pueue_bin, wakes, monkeypatch):
    spec_id = "TECH-902"
    project_id = "proj"
    pueue_id = 602
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(monkeypatch, pueue_id, "Success", None, "autopilot", "complete", merged=True)

    events = _events(wakes, "autopilot")
    assert len(events) == 1, f"expected exactly 1 autopilot event, got {events!r}"
    assert events[0]["status"] == "done", events[0]


# ---------------------------------------------------------------------------
# EC-3: crashed run, branch pushed but not merged -> event says blocked
# ---------------------------------------------------------------------------


def test_ec3_failed_run_pushed_branch_wakes_blocked(
    tmp_path, tmp_db, stub_pueue_bin, wakes, monkeypatch
):
    spec_id = "TECH-903"
    project_id = "proj"
    pueue_id = 603
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)

    remote = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", "-b", "develop", str(remote)],
        check=True,
        capture_output=True,
    )
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "origin", "develop")
    _git(repo, "checkout", "-q", "-b", f"tech/{spec_id}")
    (repo / "src").mkdir()
    (repo / "src" / "x.py").write_text("x = 1\n")
    _git(repo, "add", "src/x.py")
    _git(repo, "commit", "-q", "-m", f"feat({spec_id}): wip")
    _git(repo, "push", "-q", "origin", f"tech/{spec_id}")
    _git(repo, "checkout", "-q", "develop")

    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(monkeypatch, pueue_id, "Failed", "124", "autopilot", "", merged=False)

    events = _events(wakes, "autopilot")
    assert len(events) == 1, f"expected exactly 1 autopilot event, got {events!r}"
    assert events[0]["status"] == "blocked", events[0]
    assert "branch_pushed_not_merged" in events[0]["message"], events[0]


# ---------------------------------------------------------------------------
# EC-4: Step 7 raises -> callback still wakes once, notes the lost verdict
# ---------------------------------------------------------------------------


def test_ec4_step7_raises_still_wakes(tmp_path, tmp_db, stub_pueue_bin, wakes, monkeypatch):
    spec_id = "TECH-904"
    project_id = "proj"
    pueue_id = 604
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(callback, "verify_status_sync", _raise)

    _run_main(monkeypatch, pueue_id, "Success", None, "autopilot", "complete", merged=True)

    events = _events(wakes, "autopilot")
    assert len(events) == 1, f"expected exactly 1 autopilot event, got {events!r}"
    assert events[0]["status"] == "done", events[0]
    assert "вердикт lifecycle недоступен: exception: RuntimeError" in events[0]["message"], events[
        0
    ]


# ---------------------------------------------------------------------------
# EC-5: no lifecycle record for the spec -> event notes no_decision
# ---------------------------------------------------------------------------


def test_ec5_no_lifecycle_record_wakes_no_decision(
    tmp_path, tmp_db, stub_pueue_bin, wakes, monkeypatch
):
    spec_id = "TECH-905"
    project_id = "proj"
    pueue_id = 605
    task_label = f"autopilot-{spec_id}"

    repo = _make_project(tmp_path, spec_id, with_lifecycle=False)
    _seed_db(project_id, str(repo), pueue_id, task_label)

    _run_main(monkeypatch, pueue_id, "Success", None, "autopilot", "complete", merged=True)

    events = _events(wakes, "autopilot")
    assert len(events) == 1, f"expected exactly 1 autopilot event, got {events!r}"
    assert "no_decision" in events[0]["message"], events[0]


# ---------------------------------------------------------------------------
# EC-8: qa/reflect are unaffected — their event is Step 5, Step 7 never runs
# ---------------------------------------------------------------------------


def test_ec8_qa_event_is_step5_only(tmp_path, tmp_db, stub_pueue_bin, wakes, monkeypatch):
    spec_id = "TECH-908"
    project_id = "proj"
    pueue_id = 608
    task_label = f"qa-{spec_id}"

    repo = _make_project(tmp_path, spec_id)
    _seed_db(project_id, str(repo), pueue_id, task_label, skill="qa")

    step7_calls: list[tuple] = []
    monkeypatch.setattr(
        callback, "verify_status_sync", lambda *a, **kw: step7_calls.append((a, kw))
    )

    _run_main(monkeypatch, pueue_id, "Success", None, "qa", "", merged=True)

    assert step7_calls == [], f"Step 7 must not run for skill=qa, got {step7_calls!r}"
    assert len(wakes) == 1, f"expected exactly 1 wake total, got {wakes!r}"
    assert wakes[0][0] == "qa"
    assert wakes[0][1] == "done"
