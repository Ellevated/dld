# tests/unit/test_check_fleet_drift.py
"""The fleet-drift gate must report drift it cannot see any other way.

DLD's prompt tree reaches downstream projects by hand. Nobody could answer "is project X
current?" without diffing 150 files by eye, so for three months nobody asked — and the
answer, when an audit finally looked on 2026-08-31, was ~100 diverged files per project
and two gate scripts absent from all seven while template prompts invoked them.

Four behaviours carry that guarantee, and each has a way of quietly not working:
  1. an ABSENT file counts as drift — this is the exit-127 case, the loud one
  2. a MODIFIED file counts as drift — the quiet one
  3. the baseline grants a debt budget, exactly like `check-loc-limit.sh`
  4. a marker whose digest no longer matches the files on disk reports STALE

(4) is the point of the whole design. A marker that is read rather than verified is the
failure this repository has hit three times — `index_status.head_sha` reporting fresh
because it is read live from git, `file.py:LINE` citations pointing past the end of a
file, an exit code nobody ever wrote. Here the marker is recomputed from disk on every
run, so "synced" is a measurement and not a claim.

ADR-013: no mocks. A real template tree and a real project tree in tmp_path, the real
script in a subprocess, real exit codes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check-fleet-drift.py"

# One file per synced glob family, so the test exercises the real SYNCED_GLOBS rather
# than a shape invented here.
FILES = {
    ".claude/agents/coder.md": "# coder\n",
    ".claude/skills/spark/SKILL.md": "# spark\n",
    ".claude/scripts/validate-allowlist.mjs": "// allowlist\n",
}


def _tree(root: Path, files: dict) -> Path:
    for rel, body in files.items():
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(body, encoding="utf-8", newline="\n")
    return root


@pytest.fixture
def template(tmp_path: Path) -> Path:
    return _tree(tmp_path / "template", FILES)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return _tree(tmp_path / "proj", FILES)


def run(project: Path, template: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(project), "--template", str(template), "--json", *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def verdict(res: subprocess.CompletedProcess) -> dict:
    return json.loads(res.stdout)[0]


def test_identical_tree_is_clean(project, template):
    """The baseline case: a project that matches template must not fail the gate."""
    res = run(project, template)
    assert res.returncode == 0, res.stdout + res.stderr
    v = verdict(res)
    assert v["drift"] == 0
    assert v["identical"] == len(FILES)


def test_absent_file_is_drift(project, template):
    """The exit-127 case: a prompt invokes a gate script the project never received."""
    (project / ".claude/scripts/validate-allowlist.mjs").unlink()

    res = run(project, template)
    assert res.returncode == 1
    v = verdict(res)
    assert v["absent"] == [".claude/scripts/validate-allowlist.mjs"]
    assert v["drift"] == 1


def test_modified_file_is_drift(project, template):
    """The quiet case: the file is present, and says something else."""
    (project / ".claude/agents/coder.md").write_text("# coder, edited\n", encoding="utf-8")

    res = run(project, template)
    assert res.returncode == 1
    v = verdict(res)
    assert v["differs"] == [".claude/agents/coder.md"]
    assert not v["absent"], "a modified file must not be counted as absent"


def test_baseline_grants_a_budget(project, template, tmp_path):
    """Registered debt does not fail the gate — the `check-loc-limit.sh` contract."""
    (project / ".claude/agents/coder.md").write_text("# coder, edited\n", encoding="utf-8")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("# known debt\nproj = 1\n", encoding="utf-8")

    res = run(project, template, "--baseline", str(baseline))
    assert res.returncode == 0, res.stdout + res.stderr
    assert verdict(res)["drift"] == 1, "the drift is still reported, just not fatal"


def test_apply_syncs_and_stamps_an_honest_marker(project, template):
    """--apply must leave the project clean AND carry a marker that verifies."""
    (project / ".claude/scripts/validate-allowlist.mjs").unlink()
    (project / ".claude/agents/coder.md").write_text("# stale\n", encoding="utf-8")

    assert run(project, template).returncode == 1

    res = run(project, template, "--apply")
    assert res.returncode == 0, res.stdout + res.stderr
    v = verdict(res)
    assert v["drift"] == 0
    assert not v["marker"].startswith("STALE"), v["marker"]
    assert (project / ".claude/DLD_VERSION").is_file()


def test_marker_goes_stale_when_a_synced_file_is_edited(project, template):
    """The load-bearing case: the marker is recomputed from disk, so it cannot lie.

    A project synced yesterday and edited today still *claims* yesterday's version. The
    gate must call that STALE on the strength of the files themselves, without trusting
    a word the marker says.
    """
    run(project, template, "--apply")
    stamped = json.loads((project / ".claude/DLD_VERSION").read_text(encoding="utf-8"))

    (project / ".claude/agents/coder.md").write_text("# edited after sync\n", encoding="utf-8")

    res = run(project, template)
    assert res.returncode == 1
    v = verdict(res)
    assert v["marker"].startswith("STALE"), f"marker still claims {v['marker']}"
    # The marker file was not touched — it is the recomputation that caught this.
    on_disk = json.loads((project / ".claude/DLD_VERSION").read_text(encoding="utf-8"))
    assert on_disk == stamped


def test_hand_written_marker_does_not_buy_a_clean_report(project, template):
    """Forging the marker must not work — writing one by hand is the obvious cheat."""
    marker = project / ".claude/DLD_VERSION"
    marker.write_text(
        json.dumps({"synced_from": "deadbee", "manifest_sha256": "0" * 64}) + "\n",
        encoding="utf-8",
    )

    res = run(project, template)
    assert res.returncode == 1
    assert verdict(res)["marker"] == "STALE:deadbee"


def test_unreadable_marker_is_stale_not_a_crash(project, template):
    """A truncated marker must degrade to STALE — a gate that crashes gets switched off."""
    (project / ".claude/DLD_VERSION").write_text("{ not json", encoding="utf-8")

    res = run(project, template)
    assert res.returncode == 1
    assert verdict(res)["marker"] == "STALE:unreadable"


def test_apply_absent_delivers_missing_without_touching_local_work(project, template):
    """The safety property the fleet rollout rests on.

    Delivering a file the project lacks closes the exit-127 case. Overwriting a file the
    project has is a different act with a different risk: AwardyBot carries 364 local
    commits under `.claude/`, and blind overwriting is what got `upgrade.mjs` deleted.
    `--apply-absent` must do the first and never the second.
    """
    (project / ".claude/scripts/validate-allowlist.mjs").unlink()
    local = project / ".claude/agents/coder.md"
    local.write_text("# coder, local work\n", encoding="utf-8")

    res = run(project, template, "--apply-absent")

    assert (project / ".claude/scripts/validate-allowlist.mjs").is_file(), (
        "missing file not delivered"
    )
    assert local.read_text(encoding="utf-8") == "# coder, local work\n", "local work overwritten"
    v = verdict(res)
    assert not v["absent"]
    assert v["differs"] == [".claude/agents/coder.md"], "the remaining drift must still be reported"
    assert res.returncode == 1, "a partially synced project is not clean"


def test_apply_absent_does_not_stamp_a_marker(project, template):
    """A partial sync must not leave a marker claiming this template version."""
    (project / ".claude/scripts/validate-allowlist.mjs").unlink()
    (project / ".claude/agents/coder.md").write_text("# local\n", encoding="utf-8")

    run(project, template, "--apply-absent")

    assert not (project / ".claude/DLD_VERSION").exists(), (
        "absent-only sync stamped a version marker — the project is not at that version"
    )
