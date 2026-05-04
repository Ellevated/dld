# scripts/vps/tests/test_callback.py
"""Tests for callback.verify_status_sync (status auto-fix guards).

The two guards are symmetric:
  * target=done + spec=blocked  → skip (autopilot says blocked, respect it).
  * target=blocked + spec=done  → skip (final push/merge failed but work is
    on a feature branch — wiping done loses the signal).
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


# --- v3.15.6: backlog resync to spec authority on guard fire ---


class TestBacklogResyncToSpec:
    """Stop dispatch loops by syncing backlog → spec when guards fire.

    Scenario: backlog says queued/resumed, spec says blocked. Orchestrator
    sees queued, dispatches autopilot, autopilot SKIPs (inconsistency),
    callback target=done, Guard A fires. Without resync, backlog stays
    queued → next cycle dispatches again → loop ($0.30/cycle waste).
    Real case 2026-04-25: FTR-853 looped 11 times.
    """

    def test_guard_a_resyncs_backlog_when_spec_blocked(self, project):
        """target=done + spec=blocked + backlog=queued → backlog → blocked."""
        _write_spec(project, "BUG-10", "blocked")
        _write_backlog(project, "BUG-10", "queued")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-10", target="done")
        assert "| blocked |" in (project / "ai" / "backlog.md").read_text(), (
            "backlog resynced to spec's blocked"
        )
        # spec untouched
        assert "**Status:** blocked" in (project / "ai" / "features" / "BUG-10-test.md").read_text()
        mock_push.assert_called_once(), "resync should commit"

    def test_guard_a_resyncs_backlog_when_resumed(self, project):
        """Same shape with backlog=resumed (after operator resume)."""
        _write_spec(project, "BUG-11", "blocked")
        _write_backlog(project, "BUG-11", "resumed")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-11", target="done")
        assert "| blocked |" in (project / "ai" / "backlog.md").read_text()
        mock_push.assert_called_once()

    def test_guard_b_resyncs_backlog_when_spec_done(self, project):
        """target=blocked + spec=done + backlog=in_progress → backlog → done."""
        _write_spec(project, "BUG-12", "done")
        _write_backlog(project, "BUG-12", "in_progress")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-12", target="blocked")
        assert "| done |" in (project / "ai" / "backlog.md").read_text(), (
            "backlog resynced to spec's done"
        )
        # spec untouched
        assert "**Status:** done" in (project / "ai" / "features" / "BUG-12-test.md").read_text()
        mock_push.assert_called_once()

    def test_guard_a_no_commit_when_backlog_already_blocked(self, project):
        """Idempotency: guard fires but backlog already in sync → no commit."""
        _write_spec(project, "BUG-13", "blocked")
        _write_backlog(project, "BUG-13", "blocked")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-13", target="done")
        mock_push.assert_not_called()

    def test_guard_b_no_commit_when_backlog_already_done(self, project):
        """Idempotency: guard fires but backlog already in sync → no commit."""
        _write_spec(project, "BUG-14", "done")
        _write_backlog(project, "BUG-14", "done")
        with patch("callback._git_commit_push") as mock_push:
            callback.verify_status_sync(str(project), "BUG-14", target="blocked")
        mock_push.assert_not_called()


# --- v3.15.7: skill detection from pueue command (survives SIGKILL'd runners) ---


def _mock_pueue_status(task_id: str, command: str, start_iso: str = ""):
    """Build a MagicMock subprocess.run result for `pueue status --json`."""
    status = {"Running": {"start": start_iso}} if start_iso else {"Queued": {}}
    payload = {
        "tasks": {
            task_id: {
                "command": command,
                "original_command": command,
                "status": status,
                "label": "proj:SPEC-1",
            }
        }
    }
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps(payload)
    return m


class TestSkillFromPueueCommand:
    """Reproduce TECH-869 case: SIGKILL'd autopilot — log file is stale,
    pueue command is the only deterministic skill source."""

    def test_extracts_autopilot_from_run_agent_invocation(self):
        cmd = (
            "/home/dld/projects/dld/scripts/vps/run-agent.sh "
            "/home/dld/projects/awardybot claude autopilot /autopilot TECH-869"
        )
        with patch(
            "callback.subprocess.run",
            return_value=_mock_pueue_status("1120", cmd, "2026-04-26T17:26:08+03:00"),
        ):
            skill, start_ts = callback._skill_from_pueue_command("1120")
        assert skill == "autopilot"
        assert start_ts > 0

    def test_extracts_qa_skill(self):
        cmd = "/path/run-agent.sh /proj claude qa /qa TECH-869"
        with patch("callback.subprocess.run", return_value=_mock_pueue_status("5", cmd)):
            skill, _ = callback._skill_from_pueue_command("5")
        assert skill == "qa"

    def test_extracts_spark_skill(self):
        cmd = "/x/run-agent.sh /p claude spark /tmp/.task-cmd-X.txt"
        with patch("callback.subprocess.run", return_value=_mock_pueue_status("9", cmd)):
            skill, _ = callback._skill_from_pueue_command("9")
        assert skill == "spark"

    def test_returns_empty_on_pueue_failure(self):
        m = MagicMock()
        m.returncode = 1
        m.stderr = "daemon down"
        with patch("callback.subprocess.run", return_value=m):
            skill, ts = callback._skill_from_pueue_command("1")
        assert skill == ""
        assert ts == 0.0

    def test_returns_empty_when_command_unknown(self):
        cmd = "/some/other/script foo bar baz"
        with patch("callback.subprocess.run", return_value=_mock_pueue_status("2", cmd)):
            skill, _ = callback._skill_from_pueue_command("2")
        assert skill == ""


class TestFindLogFileFiltersStale:
    """Verify _find_log_file refuses logs older than the task's own start_ts.

    This is the actual TECH-869 fix: previously _find_log_file returned the
    latest mtime in logs/ regardless of when the current task started, so
    a SIGKILL'd run with no fresh log got the previous (qa) run's log
    mistakenly classified as autopilot's output.
    """

    def test_skips_old_logs(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        # Stale log (mtime in the past)
        old = log_dir / "proj-old.log"
        old.write_text("{}")
        import os

        os.utime(old, (1000, 1000))
        # Patch SCRIPT_DIR
        monkeypatch.setattr(callback, "SCRIPT_DIR", tmp_path)
        # Task started after mtime — old log must be skipped
        result = callback._find_log_file("proj", after_ts=2000.0)
        assert result is None

    def test_returns_log_newer_than_after_ts(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        new = log_dir / "proj-new.log"
        new.write_text("{}")
        import os

        os.utime(new, (5000, 5000))
        monkeypatch.setattr(callback, "SCRIPT_DIR", tmp_path)
        result = callback._find_log_file("proj", after_ts=2000.0)
        assert result == new

    def test_default_after_ts_zero_returns_any_log(self, tmp_path, monkeypatch):
        """Backward-compat: callers that don't pass after_ts get original behavior."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        f = log_dir / "proj-x.log"
        f.write_text("{}")
        monkeypatch.setattr(callback, "SCRIPT_DIR", tmp_path)
        result = callback._find_log_file("proj")
        assert result == f


# --- TECH-177: Subject-only matcher for _spec_has_merged_implementation ------


class TestSubjectImplements:
    """Unit tests for the pure subject-line classifier."""

    def test_conventional_scope_match(self):
        assert callback._subject_implements("feat(FTR-925): impl", "FTR-925")

    def test_conventional_scope_with_bang(self):
        assert callback._subject_implements("fix(FTR-925)!: breaking", "FTR-925")

    def test_conventional_multi_scope_match(self):
        assert callback._subject_implements(
            "feat(FTR-925,FTR-926): both", "FTR-925"
        )
        assert callback._subject_implements(
            "feat(FTR-925, FTR-926): both", "FTR-926"
        )

    def test_legacy_bare_match(self):
        assert callback._subject_implements("FTR-925: impl Y", "FTR-925")

    def test_merge_match(self):
        assert callback._subject_implements("merge FTR-925", "FTR-925")
        assert callback._subject_implements("merge FTR-925: impl", "FTR-925")
        assert callback._subject_implements("Merge FTR-925", "FTR-925")

    def test_body_mention_does_not_match(self):
        # subject is just the first line; body never reaches this function.
        # But verify subjects that LOOK like body-style mentions are rejected.
        assert not callback._subject_implements(
            "feat(FTR-923): impl X (see also FTR-925)", "FTR-925"
        )

    def test_id_after_colon_does_not_match(self):
        assert not callback._subject_implements(
            "feat: FTR-925 something", "FTR-925"
        )

    def test_wrong_scope_does_not_match(self):
        assert not callback._subject_implements(
            "feat(FTR-923): impl", "FTR-925"
        )

    def test_empty_inputs(self):
        assert not callback._subject_implements("", "FTR-925")
        assert not callback._subject_implements("feat(FTR-925): x", "")


# --- TECH-177: Integration with real git repo --------------------------------


def _git(repo: Path, *args: str) -> str:
    import subprocess
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "HOME": str(repo),
    }
    import os
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
        env={**os.environ, **env},
    )
    return r.stdout


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    return repo


def _commit(repo: Path, subject: str, body: str = "", *, files: dict[str, str] | None = None):
    files = files or {"a.py": "x"}
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        # Append unique content so each commit is a real change
        p.write_text(p.read_text() + "\n" + content if p.exists() else content)
    _git(repo, "add", *files.keys())
    msg = subject + (("\n\n" + body) if body else "")
    _git(repo, "commit", "-q", "-m", msg)


class TestSpecHasMergedImplementation:
    def test_cross_mention_in_body_does_not_match(self, git_repo):
        """Regression: awardybot 2026-05-04 incident.

        Commit implements FTR-923 with cross-reference to FTR-925 in body,
        and touches a file that is also in FTR-925's Allowed Files. Must NOT
        be treated as FTR-925 implementation.
        """
        _commit(git_repo, "feat(FTR-923): impl X", body="see also FTR-925",
                files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", ["a.py"],
        )
        assert matched is False
        assert hashes == []

    def test_subject_scope_match(self, git_repo):
        _commit(git_repo, "feat(FTR-925): impl Y", files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", ["a.py"],
        )
        assert matched is True
        assert len(hashes) == 1

    def test_legacy_bare_subject_match(self, git_repo):
        _commit(git_repo, "FTR-925: impl", files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", ["a.py"],
        )
        assert matched is True
        assert len(hashes) == 1

    def test_merge_subject_match(self, git_repo):
        _commit(git_repo, "merge FTR-925: rollup", files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", ["a.py"],
        )
        assert matched is True
        assert len(hashes) == 1

    def test_footer_trailer_does_not_match(self, git_repo):
        _commit(git_repo, "feat(other): unrelated",
                body="Refs: FTR-925\nCo-authored-by: x <x@x>",
                files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", ["a.py"],
        )
        assert matched is False
        assert hashes == []

    def test_path_filter_still_required(self, git_repo):
        """Subject match alone is not enough — file must be in allowed list."""
        _commit(git_repo, "feat(FTR-925): impl", files={"other.py": "v1"})
        matched, _ = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", ["a.py"],
        )
        assert matched is False

    def test_empty_allowed(self, git_repo):
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", [],
        )
        assert matched is False
        assert hashes == []

    def test_none_allowed(self, git_repo):
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo), "FTR-925", None,
        )
        assert matched is False
        assert hashes == []
