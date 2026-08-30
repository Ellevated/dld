# scripts/vps/tests/test_callback.py
"""Tests for callback.verify_status_sync (status auto-fix guards).

Post-ARCH-186: verify_status_sync delegates status writes to lifecycle.write_lifecycle.
Guards operate on lifecycle.read_lifecycle() state, not on markdown files.

Guard A: target=done  + lifecycle=blocked  → skip (respect blocked).
Guard B: target=blocked + lifecycle=done   → skip (respect done).
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import callback  # noqa: E402
import callback_circuit  # noqa: E402
import callback_logs  # noqa: E402
import callback_scope  # noqa: E402
import callback_sync  # noqa: E402
import db  # noqa: E402
import gate_logic  # noqa: E402
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


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """Fresh SQLite DB per test — prevents circuit breaker state from accumulating."""
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (Path(VPS_DIR) / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.close()
    db._MIGRATIONS_APPLIED = False
    with patch.object(db, "DB_PATH", db_path):
        yield


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    # Initial commit so HEAD exists
    (repo / "README.md").write_text("init\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


# ---------------------------------------------------------------------------
# EC-5 (devil DA-4): monkeypatch on gate_logic module attribute must intercept
# the call callback.verify_status_sync makes. This is the guard on the whole
# TECH-210 approach — if `from gate_logic import find_implementation_commit`
# is ever reintroduced in callback.py, this test fails because the name is
# bound at import time and monkeypatching gate_logic.find_implementation_commit
# no longer reaches the bound reference callback.py would be using.
# ---------------------------------------------------------------------------


class TestGateLogicModuleAttributePatchIntercepted:
    def test_find_implementation_commit_patch_is_used_not_real_function(
        self, git_repo, monkeypatch
    ):
        """Real git_repo has NO implementation commit — the real
        `gate_logic.find_implementation_commit` would return None here, giving
        `blocked`. If callback.py called it via `from gate_logic import
        find_implementation_commit` (a name bound at import time), this
        monkeypatch of the gate_logic module attribute would NOT be seen and
        the real function would run, giving `blocked` — this assertion would
        fail. Seeing `done` proves the module-attribute call form is in effect.
        """
        lifecycle.write_lifecycle(str(git_repo), "TECH-EC5", "in_progress")
        (git_repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
        (git_repo / "ai" / "features" / "TECH-EC5-spec.md").write_text(
            "# TECH-EC5\n\n## Allowed Files\n\n- `scripts/vps/callback.py`\n"
        )

        monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
        monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a, **kw: "deadbee")

        callback.verify_status_sync(str(git_repo), "TECH-EC5", target="done", pueue_id=5)

        data = lifecycle.read_lifecycle(str(git_repo), "TECH-EC5")
        assert data is not None
        assert data["status"] == "done", (
            "monkeypatch.setattr(gate_logic, 'find_implementation_commit', fake) "
            "must be what verify_status_sync sees — status did not reflect the fake, "
            "the real function ran instead (DA-4 trap: a `from gate_logic import ...` "
            "in callback.py would bind the name at import time and this patch would "
            "silently miss it)"
        )


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
        """Rule 3: no lifecycle.yaml → noop (spec not in this project)."""
        callback.verify_status_sync(str(git_repo), "BUG-99", target="done")
        data = lifecycle.read_lifecycle(str(git_repo), "BUG-99")
        assert data is None, "no lifecycle.yaml → noop, nothing written"


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
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        callback.verify_status_sync(str(git_repo), "BUG-4", target="done")
        after = sp.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        assert before == after, "no commit expected when already at target"

    def test_already_blocked_no_extra_commit(self, git_repo):
        import subprocess as sp

        lifecycle.write_lifecycle(str(git_repo), "BUG-5", "blocked")
        before = sp.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        callback.verify_status_sync(str(git_repo), "BUG-5", target="blocked")
        after = sp.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        assert before == after, "no commit expected when already at target"


# ---------------------------------------------------------------------------
# New test: lifecycle write path (ARCH-186 acceptance)
# ---------------------------------------------------------------------------


class TestCallbackCallsLifecycleWriteOncePerTerminalStatus:
    """verify_status_sync must write lifecycle exactly once per terminal status."""

    def test_lifecycle_written_done_when_gate_true(self, git_repo, monkeypatch):
        """Rule 1 gate returns True → lifecycle becomes done; exactly one new commit."""
        lifecycle.write_lifecycle(str(git_repo), "TECH-X", "in_progress")

        # Gate stubs
        monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
        monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a: "deadbee")
        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (10, 0, 1))

        # Need spec file with ## Allowed Files so gate branch is entered
        (git_repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
        (git_repo / "ai" / "features" / "TECH-X-spec.md").write_text(
            "# TECH-X\n\n## Allowed Files\n\n- `scripts/vps/callback.py`\n"
        )

        import subprocess as sp

        before_count = int(
            sp.run(
                ["git", "-C", str(git_repo), "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        callback.verify_status_sync(str(git_repo), "TECH-X", target="done", pueue_id=42)
        after_count = int(
            sp.run(
                ["git", "-C", str(git_repo), "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
            ).stdout.strip()
        )

        data = lifecycle.read_lifecycle(str(git_repo), "TECH-X")
        assert data is not None
        assert data["status"] == "done", f"expected done, got {data['status']}"
        # at least 1 lifecycle commit; backlog render may add a second
        assert after_count >= before_count + 1, (
            f"expected at least 1 new commit, got {after_count - before_count}"
        )

    def test_demoted_to_blocked_when_gate_false(self, git_repo, monkeypatch):
        """Rule 1 gate returns False → lifecycle demoted to blocked."""
        lifecycle.write_lifecycle(str(git_repo), "TECH-Y", "in_progress")

        monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
        monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a: None)
        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (0, 0, 0))

        (git_repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
        (git_repo / "ai" / "features" / "TECH-Y-spec.md").write_text(
            "# TECH-Y\n\n## Allowed Files\n\n- `scripts/vps/callback.py`\n"
        )
        mock_db = MagicMock()
        mock_db.count_demotes_since.return_value = 0
        monkeypatch.setattr(callback, "db", mock_db)
        monkeypatch.setattr(callback_circuit, "db", mock_db)
        monkeypatch.setattr(callback_scope, "db", mock_db)

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
        old.write_text("{}", encoding="utf-8")
        import os

        os.utime(old, (1000, 1000))
        # Patch SCRIPT_DIR
        monkeypatch.setattr(callback_logs, "SCRIPT_DIR", tmp_path)
        # Task started after mtime — old log must be skipped
        result = callback_logs._find_log_file("proj", after_ts=2000.0)
        assert result is None

    def test_returns_log_newer_than_after_ts(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        new = log_dir / "proj-new.log"
        new.write_text("{}", encoding="utf-8")
        import os

        os.utime(new, (5000, 5000))
        monkeypatch.setattr(callback_logs, "SCRIPT_DIR", tmp_path)
        result = callback_logs._find_log_file("proj", after_ts=2000.0)
        assert result == new

    def test_default_after_ts_zero_returns_any_log(self, tmp_path, monkeypatch):
        """Backward-compat: callers that don't pass after_ts get original behavior."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        f = log_dir / "proj-x.log"
        f.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(callback_logs, "SCRIPT_DIR", tmp_path)
        result = callback_logs._find_log_file("proj")
        assert result == f


# ---------------------------------------------------------------------------
# TECH-197: Push-local + grace-retry + demote-once tests
# ---------------------------------------------------------------------------


def _make_origin_repo(tmp_path):
    """Create a bare 'origin' repo and a working repo cloned from it."""

    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-q", "-b", "develop")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / "README.md").write_text("init\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "push", "-u", "origin", "develop")
    return origin, repo


class TestPushLocalBeforeGate:
    """EC-6: impl merged to local develop, NOT pushed — callback pushes + gate→done.
    EC-7: impl on feature branch only — stays blocked.
    EC-9: push fails (no remote) → blocked, fail-closed, exactly 1 demote.
    """

    def test_ec6_push_local_recovers_timeout_interrupted_merge(self, tmp_path, monkeypatch):
        """BUG-1117 class: impl merged to local develop but not pushed to origin."""
        origin, repo = _make_origin_repo(tmp_path)

        # Create spec + lifecycle
        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "TECH-T6-spec.md").write_text(
            "# TECH-T6\n\n## Allowed Files\n\n- `src/main.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "TECH-T6", "in_progress")

        # Simulate: impl commit on local develop (not pushed)
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "main.py").write_text("# impl\n", encoding="utf-8")
        _git(repo, "add", "src/main.py")
        _git(repo, "commit", "-m", "feat(TECH-T6): implement feature")

        # Stub _commit_stats — no pueue_id so started_at=None anyway
        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (10, 0, 1))
        # Do NOT stub gate_logic.fetch_develop or find_implementation_commit — let them run real

        # autopilot_signaled=False, target=blocked → push-local should flush
        callback.verify_status_sync(
            str(repo),
            "TECH-T6",
            target="blocked",
            autopilot_signaled=False,
        )
        data = lifecycle.read_lifecycle(str(repo), "TECH-T6")
        assert data["status"] == "done", (
            f"push-local should flush impl to origin, gate→done; got {data['status']}"
        )

    def test_ec7_feature_branch_only_stays_blocked(self, tmp_path, monkeypatch):
        """BUG-1118 class: impl on feature branch only, not merged to develop."""
        origin, repo = _make_origin_repo(tmp_path)

        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "TECH-T7-spec.md").write_text(
            "# TECH-T7\n\n## Allowed Files\n\n- `src/app.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "TECH-T7", "in_progress")

        # Create feature branch with impl — NOT merged to develop
        _git(repo, "checkout", "-b", "feature/TECH-T7")
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "app.py").write_text("# feature\n", encoding="utf-8")
        _git(repo, "add", "src/app.py")
        _git(repo, "commit", "-m", "feat(TECH-T7): feature impl")
        _git(repo, "checkout", "develop")

        # Stub _commit_stats
        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (0, 0, 0))
        # Speed up grace-retry sleep
        monkeypatch.setattr(callback_sync.time, "sleep", lambda s: None)
        # Mock db for circuit-breaker accounting
        mock_db = MagicMock()
        mock_db.count_demotes_since.return_value = 0
        monkeypatch.setattr(callback, "db", mock_db)
        monkeypatch.setattr(callback_circuit, "db", mock_db)
        monkeypatch.setattr(callback_scope, "db", mock_db)

        callback.verify_status_sync(
            str(repo),
            "TECH-T7",
            target="blocked",
            autopilot_signaled=False,
        )
        data = lifecycle.read_lifecycle(str(repo), "TECH-T7")
        assert data["status"] == "blocked", "feature-branch-only must stay blocked (fail-closed)"

    def test_ec9_push_fails_stays_blocked_one_demote(self, tmp_path, monkeypatch):
        """Push origin fails (no remote) → blocked, exactly 1 demote."""
        # Repo WITHOUT origin remote
        repo = tmp_path / "no_origin"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "develop")
        _git(repo, "config", "user.email", "t@t")
        _git(repo, "config", "user.name", "t")
        (repo / "README.md").write_text("init\n", encoding="utf-8")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-q", "-m", "init")

        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "TECH-T9-spec.md").write_text(
            "# TECH-T9\n\n## Allowed Files\n\n- `src/x.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "TECH-T9", "in_progress")

        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (0, 0, 0))
        monkeypatch.setattr(callback_sync.time, "sleep", lambda s: None)
        mock_db = MagicMock()
        mock_db.count_demotes_since.return_value = 0
        monkeypatch.setattr(callback, "db", mock_db)
        monkeypatch.setattr(callback_circuit, "db", mock_db)
        monkeypatch.setattr(callback_scope, "db", mock_db)

        callback.verify_status_sync(
            str(repo),
            "TECH-T9",
            target="blocked",
            autopilot_signaled=False,
        )
        data = lifecycle.read_lifecycle(str(repo), "TECH-T9")
        assert data["status"] == "blocked", "no remote → blocked (fail-closed)"

        # Verify exactly 1 demote recorded
        demote_calls = [
            c
            for c in mock_db.record_decision.call_args_list
            if (c.kwargs.get("demoted") is True) or (len(c.args) > 4 and c.args[4] is True)
        ]
        assert len(demote_calls) == 1, f"expected exactly 1 demote, got {len(demote_calls)}"


class TestDemoteOnce:
    """EC-4: gate False × 3 retries → exactly 1 record_decision(demoted=True)."""

    def test_ec4_single_demote_across_retries(self, tmp_path, monkeypatch):
        origin, repo = _make_origin_repo(tmp_path)

        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "TECH-D4-spec.md").write_text(
            "# TECH-D4\n\n## Allowed Files\n\n- `src/d.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "TECH-D4", "in_progress")

        # Gate always returns False (nothing implemented on origin/develop)
        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (0, 0, 0))
        # Speed up: reduce sleep to 0
        monkeypatch.setattr(callback_sync.time, "sleep", lambda s: None)
        mock_db = MagicMock()
        mock_db.count_demotes_since.return_value = 0
        monkeypatch.setattr(callback, "db", mock_db)
        monkeypatch.setattr(callback_circuit, "db", mock_db)
        monkeypatch.setattr(callback_scope, "db", mock_db)

        callback.verify_status_sync(
            str(repo),
            "TECH-D4",
            target="blocked",
            autopilot_signaled=False,
        )
        data = lifecycle.read_lifecycle(str(repo), "TECH-D4")
        assert data["status"] == "blocked"

        # Exactly 1 demote, not 3+
        demote_calls = [
            c
            for c in mock_db.record_decision.call_args_list
            if (c.kwargs.get("demoted") is True) or (len(c.args) > 4 and c.args[4] is True)
        ]
        assert len(demote_calls) == 1, (
            f"expected 1 demote across retries, got {len(demote_calls)}: {demote_calls}"
        )


class TestGraceRetry:
    """EC-8: impl pushed to origin 1 fetch-cycle late → grace-retry resolves."""

    def test_ec8_resolves_on_second_fetch(self, tmp_path, monkeypatch):
        origin, repo = _make_origin_repo(tmp_path)

        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "TECH-G8-spec.md").write_text(
            "# TECH-G8\n\n## Allowed Files\n\n- `src/g.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "TECH-G8", "in_progress")

        # Simulate: push impl to origin on the "second" fetch check
        call_count = {"n": 0}
        original_is_done = gate_logic.find_implementation_commit

        def _delayed_is_done(pp, sid, af):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # first check: not visible yet
            # Push impl BEFORE second check (simulates network lag)
            (repo / "src").mkdir(exist_ok=True)
            (repo / "src" / "g.py").write_text("# impl\n", encoding="utf-8")
            _git(repo, "add", "src/g.py")
            _git(repo, "commit", "-m", "feat(TECH-G8): implement")
            _git(repo, "push", "origin", "develop")
            return original_is_done(pp, sid, af)

        monkeypatch.setattr(gate_logic, "find_implementation_commit", _delayed_is_done)
        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (10, 0, 1))
        monkeypatch.setattr(callback_sync.time, "sleep", lambda s: None)

        callback.verify_status_sync(
            str(repo),
            "TECH-G8",
            target="blocked",
            autopilot_signaled=False,
        )
        data = lifecycle.read_lifecycle(str(repo), "TECH-G8")
        assert data["status"] == "done", (
            f"grace-retry should resolve on 2nd attempt; got {data['status']}"
        )


class TestAutopilotSignaledOverride:
    """TECH-197 critical: autopilot_signaled=True blocks gate=done override."""

    def test_signaled_blocked_overrides_gate_done(self, tmp_path, monkeypatch):
        """When autopilot explicitly signals blocked, gate=done is overridden."""
        origin, repo = _make_origin_repo(tmp_path)

        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "TECH-AS-spec.md").write_text(
            "# TECH-AS\n\n## Allowed Files\n\n- `src/as.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "TECH-AS", "in_progress")

        # Impl is on origin (gate would return True)
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "as.py").write_text("# impl\n", encoding="utf-8")
        _git(repo, "add", "src/as.py")
        _git(repo, "commit", "-m", "feat(TECH-AS): implement")
        _git(repo, "push", "origin", "develop")

        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (10, 0, 1))
        mock_db = MagicMock()
        mock_db.count_demotes_since.return_value = 0
        monkeypatch.setattr(callback, "db", mock_db)
        monkeypatch.setattr(callback_circuit, "db", mock_db)
        monkeypatch.setattr(callback_scope, "db", mock_db)

        # autopilot_signaled=True + target=blocked → must stay blocked
        callback.verify_status_sync(
            str(repo),
            "TECH-AS",
            target="blocked",
            autopilot_signaled=True,
        )
        data = lifecycle.read_lifecycle(str(repo), "TECH-AS")
        assert data["status"] == "blocked", "autopilot_signaled=True must override gate=done"

    def test_not_signaled_lets_gate_decide(self, tmp_path, monkeypatch):
        """When autopilot did NOT signal (timeout), gate=done is honored."""
        origin, repo = _make_origin_repo(tmp_path)

        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "TECH-NS-spec.md").write_text(
            "# TECH-NS\n\n## Allowed Files\n\n- `src/ns.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "TECH-NS", "in_progress")

        # Impl on origin
        (repo / "src").mkdir(exist_ok=True)
        (repo / "src" / "ns.py").write_text("# impl\n", encoding="utf-8")
        _git(repo, "add", "src/ns.py")
        _git(repo, "commit", "-m", "feat(TECH-NS): implement")
        _git(repo, "push", "origin", "develop")

        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (10, 0, 1))

        # autopilot_signaled=False + target=blocked → gate decides (done)
        callback.verify_status_sync(
            str(repo),
            "TECH-NS",
            target="blocked",
            autopilot_signaled=False,
        )
        data = lifecycle.read_lifecycle(str(repo), "TECH-NS")
        assert data["status"] == "done", "not-signaled + impl on origin → gate should decide done"

    def test_signaled_blocked_no_impl_reason_is_autopilot_not_no_merged(
        self, tmp_path, monkeypatch
    ):
        """Regression (ARCH-1246 / FTR-1245, 2026-06-20): a deliberate self-block
        on an unmet dependency makes 0 commits. The blocked_reason must reflect
        the autopilot's explicit signal — NOT the misleading
        no_merged_implementation hint that tells the operator to force-done."""
        origin, repo = _make_origin_repo(tmp_path)

        (repo / "ai" / "features").mkdir(parents=True)
        (repo / "ai" / "features" / "ARCH-DEP-spec.md").write_text(
            "# ARCH-DEP\n\n## Allowed Files\n\n- `src/dep.py`\n"
        )
        lifecycle.write_lifecycle(str(repo), "ARCH-DEP", "in_progress")

        # Gate is FALSE (no impl on origin) + autopilot explicitly blocked.
        monkeypatch.setattr(gate_logic, "fetch_develop", lambda *a, **kw: True)
        monkeypatch.setattr(gate_logic, "find_implementation_commit", lambda *a: None)
        monkeypatch.setattr(callback_scope, "_commit_stats", lambda *a: (0, 0, 0))
        mock_db = MagicMock()
        mock_db.count_demotes_since.return_value = 0
        monkeypatch.setattr(callback, "db", mock_db)
        monkeypatch.setattr(callback_circuit, "db", mock_db)
        monkeypatch.setattr(callback_scope, "db", mock_db)

        callback.verify_status_sync(
            str(repo),
            "ARCH-DEP",
            target="blocked",
            pueue_id=631,
            autopilot_signaled=True,
        )
        data = lifecycle.read_lifecycle(str(repo), "ARCH-DEP")
        assert data["status"] == "blocked"
        assert data.get("blocked_reason") == "autopilot_signaled_blocked"
        assert "no_merged_implementation" not in (data.get("blocked_reason") or "")


class TestParseLogTaskStatus:
    """_parse_log_file must recover task_status even when the agent wraps it in a
    markdown ```json fence instead of a bare-JSON final message.

    Regression (ARCH-1246 / FTR-1245, 2026-06-20): Opus 4.x emitted a markdown
    block report with task_status inside a fence; the old whole-preview json.loads
    failed, the blocked signal was lost, and the spec was mislabeled
    no_merged_implementation instead of being honored as a deliberate block.
    """

    def _write_log(self, tmp_path, payload):
        p = tmp_path / "proj-20260620-000000.log"
        p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return p

    def test_top_level_field_preferred(self, tmp_path):
        log = self._write_log(
            tmp_path,
            {"skill": "autopilot", "task_status": "blocked", "result_preview": "prose"},
        )
        _skill, _preview, task_status = callback._parse_log_file(log)
        assert task_status == "blocked"

    def test_markdown_fenced_json_extracted(self, tmp_path):
        preview = (
            "**ARCH-1246 заблокирован — зависимость TECH-1244 не выполнена.**\n\n"
            "Рекомендация: сначала запустить TECH-1244.\n\n"
            '```json\n{\n  "task_status": "blocked",\n'
            '  "result_preview": "dep not done"\n}\n```'
        )
        log = self._write_log(tmp_path, {"skill": "autopilot", "result_preview": preview})
        _skill, _preview, task_status = callback._parse_log_file(log)
        assert task_status == "blocked"

    def test_not_lost_to_500_char_truncation(self, tmp_path):
        # task_status sits beyond the 500-char display preview but within full text.
        preview = ("x" * 600) + '\n```json\n{"task_status": "needs_review"}\n```'
        log = self._write_log(tmp_path, {"skill": "autopilot", "result_preview": preview})
        _skill, _preview, task_status = callback._parse_log_file(log)
        assert task_status == "needs_review"

    def test_bare_json_legacy_preview_still_works(self, tmp_path):
        preview = '{"task_status": "complete", "result_preview": "done"}'
        log = self._write_log(tmp_path, {"skill": "autopilot", "result_preview": preview})
        _skill, _preview, task_status = callback._parse_log_file(log)
        assert task_status == "complete"

    def test_no_signal_returns_empty(self, tmp_path):
        log = self._write_log(tmp_path, {"skill": "autopilot", "result_preview": "no signal here"})
        _skill, _preview, task_status = callback._parse_log_file(log)
        assert task_status == ""
