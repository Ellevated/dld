# scripts/vps/tests/test_callback.py
"""Tests for callback.verify_status_sync (status auto-fix guards).

Post-ARCH-186: verify_status_sync delegates status writes to lifecycle.write_lifecycle.
Guards operate on lifecycle.read_lifecycle() state, not on markdown files.

Guard A: target=done  + lifecycle=blocked  → skip (respect blocked).
Guard B: target=blocked + lifecycle=done   → skip (respect done).
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import callback  # noqa: E402
import lifecycle  # noqa: E402


# ---------------------------------------------------------------------------
# Shared git helpers
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    import os

    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "HOME": str(repo),
    }
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **env},
    )
    return r.stdout


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    # Initial commit so HEAD exists
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


# ---------------------------------------------------------------------------
# Guard A: target=done + lifecycle=blocked → skip
# ---------------------------------------------------------------------------


class TestDoneOverBlockedGuard:
    def test_done_target_respects_blocked_lifecycle(self, git_repo):
        """lifecycle says blocked; callback with target=done must skip write."""
        lifecycle.write_lifecycle(str(git_repo), "BUG-1", "blocked")
        callback.verify_status_sync(str(git_repo), "BUG-1", target="done")
        data = lifecycle.read_lifecycle(str(git_repo), "BUG-1")
        assert data["status"] == "blocked", "lifecycle blocked must be preserved"

    def test_done_guard_skips_write_when_no_lifecycle(self, git_repo):
        """No lifecycle yet (first time): target=done should write done."""
        callback.verify_status_sync(str(git_repo), "BUG-99", target="done")
        data = lifecycle.read_lifecycle(str(git_repo), "BUG-99")
        assert data is not None
        assert data["status"] == "done"


# ---------------------------------------------------------------------------
# Guard B: target=blocked + lifecycle=done → skip
# ---------------------------------------------------------------------------


class TestBlockedOverDoneGuard:
    def test_blocked_target_respects_done_lifecycle(self, git_repo):
        """Reproduces BUG-376/BUG-374/BUG-865 scenario.

        Autopilot finished all per-task code → lifecycle=done.
        Final push failed → pueue exit=1 → callback target=blocked.
        Guard B must protect the done state.
        """
        lifecycle.write_lifecycle(str(git_repo), "BUG-2", "done")
        callback.verify_status_sync(str(git_repo), "BUG-2", target="blocked")
        data = lifecycle.read_lifecycle(str(git_repo), "BUG-2")
        assert data["status"] == "done", "lifecycle done must be preserved"

    def test_blocked_target_writes_when_lifecycle_in_progress(self, git_repo):
        """Sanity: guard only fires for done lifecycle; in_progress gets blocked."""
        lifecycle.write_lifecycle(str(git_repo), "BUG-3", "in_progress")
        callback.verify_status_sync(str(git_repo), "BUG-3", target="blocked")
        data = lifecycle.read_lifecycle(str(git_repo), "BUG-3")
        assert data["status"] == "blocked"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotent:
    def test_already_done_no_extra_commit(self, git_repo):
        """If lifecycle already has target status, no extra commit."""
        import subprocess as sp
        lifecycle.write_lifecycle(str(git_repo), "BUG-4", "done")
        before = sp.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
        callback.verify_status_sync(str(git_repo), "BUG-4", target="done")
        after = sp.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
        assert before == after, "no commit expected when already at target"

    def test_already_blocked_no_extra_commit(self, git_repo):
        import subprocess as sp
        lifecycle.write_lifecycle(str(git_repo), "BUG-5", "blocked")
        before = sp.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
        callback.verify_status_sync(str(git_repo), "BUG-5", target="blocked")
        after = sp.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
        assert before == after, "no commit expected when already at target"


# ---------------------------------------------------------------------------
# New test: lifecycle write path (ARCH-186 acceptance)
# ---------------------------------------------------------------------------


class TestCallbackCallsLifecycleWriteOncePerTerminalStatus:
    """verify_status_sync must write lifecycle exactly once per terminal status."""

    def test_lifecycle_written_done_with_impl_commits(self, git_repo, monkeypatch):
        """When _has_implementation_commits returns True, lifecycle must become done."""
        lifecycle.write_lifecycle(str(git_repo), "TECH-X", "in_progress")

        # Stub implementation guard to return True (no need for real commits)
        monkeypatch.setattr(callback, "_has_implementation_commits", lambda *a, **kw: True)
        monkeypatch.setattr(callback, "_get_started_at", lambda *a: "2026-01-01T00:00:00Z")
        monkeypatch.setattr(callback, "_commit_stats", lambda *a: (10, 0, 1))
        monkeypatch.setattr(callback, "is_merged_to_develop", lambda *a: True)

        import subprocess as sp
        before_count = int(
            sp.run(
                ["git", "-C", str(git_repo), "rev-list", "--count", "HEAD"],
                capture_output=True, text=True
            ).stdout.strip()
        )
        callback.verify_status_sync(str(git_repo), "TECH-X", target="done", pueue_id=42)
        after_count = int(
            sp.run(
                ["git", "-C", str(git_repo), "rev-list", "--count", "HEAD"],
                capture_output=True, text=True
            ).stdout.strip()
        )

        data = lifecycle.read_lifecycle(str(git_repo), "TECH-X")
        assert data is not None
        assert data["status"] == "done", f"expected done, got {data['status']}"
        # Exactly one new lifecycle commit (the write)
        assert after_count == before_count + 1, (
            f"expected exactly 1 new commit, got {after_count - before_count}"
        )

    def test_demoted_to_blocked_when_no_impl_commits(self, git_repo, monkeypatch):
        """When no implementation commits found, must demote to blocked."""
        lifecycle.write_lifecycle(str(git_repo), "TECH-Y", "in_progress")

        monkeypatch.setattr(callback, "_has_implementation_commits", lambda *a, **kw: False)
        monkeypatch.setattr(callback, "_spec_has_merged_implementation", lambda *a: (False, []))
        monkeypatch.setattr(callback, "_get_started_at", lambda *a: "2026-01-01T00:00:00Z")
        monkeypatch.setattr(callback, "_commit_stats", lambda *a: (0, 0, 0))

        # Need a minimal spec file with ## Allowed Files for the guard
        (git_repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
        (git_repo / "ai" / "features" / "TECH-Y-spec.md").write_text(
            "# TECH-Y\n\n**Status:** in_progress\n\n## Allowed Files\n\n<!-- callback-allowlist v1 -->\n- `scripts/vps/callback.py`\n"
        )
        monkeypatch.setattr(callback, "_parse_allowed_files",
                            lambda *a: ["scripts/vps/callback.py"])
        mock_db = MagicMock()
        mock_db.count_demotes_since.return_value = 0
        monkeypatch.setattr(callback, "db", mock_db)

        callback.verify_status_sync(str(git_repo), "TECH-Y", target="done", pueue_id=99)
        data = lifecycle.read_lifecycle(str(git_repo), "TECH-Y")
        assert data is not None
        assert data["status"] == "blocked", f"expected blocked (demote), got {data['status']}"


# ---------------------------------------------------------------------------
# v3.15.7: skill detection from pueue command (survives SIGKILL'd runners)
# ---------------------------------------------------------------------------


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
        assert callback._subject_implements("feat(FTR-925,FTR-926): both", "FTR-925")
        assert callback._subject_implements("feat(FTR-925, FTR-926): both", "FTR-926")

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
        assert not callback._subject_implements("feat: FTR-925 something", "FTR-925")

    def test_wrong_scope_does_not_match(self):
        assert not callback._subject_implements("feat(FTR-923): impl", "FTR-925")

    def test_empty_inputs(self):
        assert not callback._subject_implements("", "FTR-925")
        assert not callback._subject_implements("feat(FTR-925): x", "")


# --- TECH-177: Integration with real git repo --------------------------------


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
        _commit(git_repo, "feat(FTR-923): impl X", body="see also FTR-925", files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            ["a.py"],
        )
        assert matched is False
        assert hashes == []

    def test_subject_scope_match(self, git_repo):
        _commit(git_repo, "feat(FTR-925): impl Y", files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            ["a.py"],
        )
        assert matched is True
        assert len(hashes) == 1

    def test_legacy_bare_subject_match(self, git_repo):
        _commit(git_repo, "FTR-925: impl", files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            ["a.py"],
        )
        assert matched is True
        assert len(hashes) == 1

    def test_merge_subject_match(self, git_repo):
        _commit(git_repo, "merge FTR-925: rollup", files={"a.py": "v1"})
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            ["a.py"],
        )
        assert matched is True
        assert len(hashes) == 1

    def test_footer_trailer_does_not_match(self, git_repo):
        _commit(
            git_repo,
            "feat(other): unrelated",
            body="Refs: FTR-925\nCo-authored-by: x <x@x>",
            files={"a.py": "v1"},
        )
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            ["a.py"],
        )
        assert matched is False
        assert hashes == []

    def test_path_filter_still_required(self, git_repo):
        """Subject match alone is not enough — file must be in allowed list."""
        _commit(git_repo, "feat(FTR-925): impl", files={"other.py": "v1"})
        matched, _ = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            ["a.py"],
        )
        assert matched is False

    def test_empty_allowed(self, git_repo):
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            [],
        )
        assert matched is False
        assert hashes == []

    def test_none_allowed(self, git_repo):
        matched, hashes = callback._spec_has_merged_implementation(
            str(git_repo),
            "FTR-925",
            None,
        )
        assert matched is False
        assert hashes == []
