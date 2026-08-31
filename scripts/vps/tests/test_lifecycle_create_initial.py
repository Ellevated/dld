"""Tests for lifecycle.create_initial priority normalization (TECH-200).

Verifies that priority is lowercased, stripped, and validated against the
{p0, p1, p2} enum before being persisted. Unknown values default to p1
with a WARNING. Regression: uppercase priority no longer silently drops
specs from render_backlog output.
"""

import logging
import subprocess
import sys
from pathlib import Path

import pytest

# Make scripts/vps importable
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import render_backlog  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Minimal git repo with one initial commit and ai/lifecycle/ dir."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")

    # Create ai/lifecycle/ with a .gitkeep so HEAD exists
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "init")

    return repo


# ---------------------------------------------------------------------------
# Test 1: Uppercase priority normalized to lowercase
# ---------------------------------------------------------------------------


def test_uppercase_priority_normalized(tmp_git_repo):
    lifecycle.create_initial(tmp_git_repo, "TECH-T1", priority="P0", kind="tech", by="orchestrator")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-T1")
    assert data["priority"] == "p0"


# ---------------------------------------------------------------------------
# Test 2: Mixed case + whitespace stripped and lowercased
# ---------------------------------------------------------------------------


def test_mixed_whitespace_priority_normalized(tmp_git_repo):
    lifecycle.create_initial(
        tmp_git_repo, "TECH-T2", priority=" P2 ", kind="tech", by="orchestrator"
    )
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-T2")
    assert data["priority"] == "p2"


# ---------------------------------------------------------------------------
# Test 3: Unknown priority defaults to p1 with WARNING
# ---------------------------------------------------------------------------


def test_unknown_priority_defaults_with_warning(tmp_git_repo, caplog):
    with caplog.at_level(logging.WARNING, logger="lifecycle"):
        lifecycle.create_initial(
            tmp_git_repo,
            "TECH-T3",
            priority="urgent",
            kind="tech",
            by="orchestrator",
        )
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-T3")
    assert data["priority"] == "p1"
    assert "unknown priority" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Test 4: None priority defaults to p1
# ---------------------------------------------------------------------------


def test_none_priority_defaults_to_p1(tmp_git_repo):
    lifecycle.create_initial(tmp_git_repo, "TECH-T4", priority=None, kind="tech", by="orchestrator")
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-T4")
    assert data["priority"] == "p1"


# ---------------------------------------------------------------------------
# Test 5: Uppercase priority renders in correct backlog group (regression)
# ---------------------------------------------------------------------------


def test_renders_in_correct_group(tmp_git_repo):
    """Regression: a spec created with uppercase 'P1' must appear in the
    rendered backlog under the P1 group, not silently disappear."""
    lifecycle.create_initial(tmp_git_repo, "FTR-T5", priority="P1", kind="ftr", by="orchestrator")
    output = render_backlog.render_backlog(tmp_git_repo)
    assert "FTR-T5" in output, f"Spec FTR-T5 not found in rendered backlog:\n{output}"
