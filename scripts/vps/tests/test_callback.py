# scripts/vps/tests/test_callback.py
"""Tests for callback.verify_status_sync (status auto-fix guards).

The two guards are symmetric:
  * target=done + spec=blocked  → skip (autopilot says blocked, respect it).
  * target=blocked + spec=done  → skip (final push/merge failed but work is
    on a feature branch — wiping done loses the signal).
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import callback  # noqa: E402


@pytest.fixture
def project(tmp_path):
    """Create a fake project with ai/features/<spec>.md and ai/backlog.md."""
    p = tmp_path / "proj"
    (p / "ai" / "features").mkdir(parents=True)
    return p


def _write_spec(project: Path, spec_id: str, status: str) -> Path:
    f = project / "ai" / "features" / f"{spec_id}-test.md"
    f.write_text(f"# {spec_id}\n\n**Status:** {status}\n")
    return f


def _write_backlog(project: Path, spec_id: str, status: str) -> None:
    (project / "ai" / "backlog.md").write_text(
        f"| ID | Title | Status |\n|---|---|---|\n| {spec_id} | t | {status} |\n"
    )


# --- Guard 1: target=done + spec=blocked → skip ---


class TestDoneOverBlockedGuard:
    def test_done_target_respects_blocked_spec(self, project):
        spec = _write_spec(project, "BUG-1", "blocked")
        _write_backlog(project, "BUG-1", "blocked")
        callback.verify_status_sync(str(project), "BUG-1", target="done")
        # Spec untouched
        assert "**Status:** blocked" in spec.read_text()
        # Backlog untouched
        assert "| blocked |" in (project / "ai" / "backlog.md").read_text()


# --- Guard 2 (NEW 2026-04-25): target=blocked + spec=done → skip ---


class TestBlockedOverDoneGuard:
    def test_blocked_target_respects_done_spec(self, project):
        """Reproduces the BUG-376 / BUG-374 / BUG-865 scenario.

        Autopilot finished all per-task code, marked spec done, then the
        final merge-to-develop step failed. Pueue exit=1 → callback called
        with target=blocked. Without this guard, done was wiped and the
        feature branch was orphaned.
        """
        spec = _write_spec(project, "BUG-2", "done")
        _write_backlog(project, "BUG-2", "done")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-2", target="blocked")
        assert "**Status:** done" in spec.read_text(), "spec done preserved"
        assert "| done |" in (project / "ai" / "backlog.md").read_text(), "backlog done preserved"
        mock_push.assert_not_called(), "no auto-fix commit when guard fires"

    def test_blocked_target_still_writes_when_spec_not_done(self, project):
        """Sanity: guard only fires for done spec; other states get blocked."""
        _write_spec(project, "BUG-3", "in_progress")
        _write_backlog(project, "BUG-3", "in_progress")
        with patch("callback._git_commit_push"):
            callback.verify_status_sync(str(project), "BUG-3", target="blocked")
        assert "**Status:** blocked" in (project / "ai" / "features" / "BUG-3-test.md").read_text()


# --- Both guards: idempotent (target already matches) ---


class TestIdempotent:
    def test_already_done_no_op(self, project):
        _write_spec(project, "BUG-4", "done")
        _write_backlog(project, "BUG-4", "done")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-4", target="done")
        mock_push.assert_not_called()

    def test_already_blocked_no_op(self, project):
        _write_spec(project, "BUG-5", "blocked")
        _write_backlog(project, "BUG-5", "blocked")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-5", target="blocked")
        mock_push.assert_not_called()
