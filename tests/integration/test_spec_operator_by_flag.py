"""ARCH-187 Task 10 — Integration: spec_operator.py --by mandate (ADR-024).

Real fs + real git (no mocks per ADR-013). Verifies that the operator CLI:

T1: rejects missing --by (argparse exit code 2, stderr names --by)
T2: rejects --by=hacker via argparse choices (exit code 2)
T3: demote accepts --by=qa, writes audit trail with by=qa
T4: force-done accepts --by=operator, writes audit trail with by=operator
T5: lifecycle yaml not bootstrapped → exit code 3 (proper diagnostic)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import lifecycle  # noqa: E402
import spec_operator  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_project(tmp_path: Path, spec_id: str, with_lifecycle: bool = True) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    (repo / "ai" / "features" / f"{spec_id}.md").write_text(
        f"# {spec_id}\n\n**Priority:** P1\n\n## Allowed Files\n\n- `src/foo.py`\n"
    )
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    if with_lifecycle:
        lifecycle.create_initial(repo, spec_id, priority="p1", kind="tech")
    return repo


# ---------------------------------------------------------------------------


def test_t1_demote_rejects_missing_by(tmp_path, capsys):
    """T1: argparse complains when --by absent (required=True)."""
    repo = _make_project(tmp_path, "TECH-910")
    with pytest.raises(SystemExit) as exc:
        spec_operator.main(["demote", str(repo), "TECH-910", "test reason"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "--by" in captured.err


def test_t2_demote_rejects_invalid_by(tmp_path, capsys):
    """T2: argparse rejects choices outside the allowed list."""
    repo = _make_project(tmp_path, "TECH-911")
    with pytest.raises(SystemExit) as exc:
        spec_operator.main(["demote", str(repo), "TECH-911", "test", "--by=hacker"])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    # argparse error mentions invalid choice
    assert "hacker" in captured.err or "invalid choice" in captured.err.lower()


def test_t3_demote_blocked_records_by_qa(tmp_path, capsys):
    """T3: demote --blocked --by=qa writes audit trail correctly."""
    repo = _make_project(tmp_path, "TECH-912")
    # Push spec to in_progress first (so demote → blocked is meaningful)
    lifecycle.write_lifecycle(repo, "TECH-912", "in_progress", by="orchestrator")

    rc = spec_operator.main(
        [
            "demote",
            str(repo),
            "TECH-912",
            "qa rejected",
            "--blocked",
            "--by=qa",
        ]
    )
    assert rc == 0

    data = lifecycle.read_lifecycle(repo, "TECH-912")
    assert data is not None
    assert data["status"] == "blocked"
    assert data["blocked_reason"] == "qa rejected"
    # last transition shows by=qa with the right destination
    last = data["transitions"][-1]
    assert last["to"] == "blocked"
    assert last["by"] == "qa"


def test_t4_force_done_records_by_operator(tmp_path):
    """T4: force-done --by=operator writes audit trail with operator identity."""
    repo = _make_project(tmp_path, "TECH-913")

    rc = spec_operator.main(
        [
            "force-done",
            str(repo),
            "TECH-913",
            "manual override after QA",
            "--by=operator",
        ]
    )
    assert rc == 0

    data = lifecycle.read_lifecycle(repo, "TECH-913")
    assert data is not None
    assert data["status"] == "done"
    assert data["blocked_reason"] == "manual override after QA"
    last = data["transitions"][-1]
    assert last["to"] == "done"
    assert last["by"] == "operator"
    # finished_at must be populated when entering done
    assert data["finished_at"] is not None


def test_t5_missing_lifecycle_yaml_returns_exit_3(tmp_path, capsys):
    """T5: project has spec but no lifecycle yaml → exit code 3 (proper signal)."""
    repo = _make_project(tmp_path, "TECH-914", with_lifecycle=False)

    rc = spec_operator.main(
        [
            "demote",
            str(repo),
            "TECH-914",
            "test",
            "--by=qa",
        ]
    )
    assert rc == 3
    captured = capsys.readouterr()
    assert "lifecycle yaml not found" in captured.err
    assert "never bootstrapped" in captured.err
