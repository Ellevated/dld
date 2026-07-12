"""
Module: test_callback_dispatch
Role: Regression tests for TECH-207 — _step6_dispatch_qa_reflect merge-confirmed fallback.

Tests ensure:
- EC-1: merged + no complete signal → QA + Reflect dispatched
- EC-2: no merge + no complete signal → neither dispatched
- EC-3: explicit task_status='complete' path unchanged
- EC-4: blocked/needs_review/non-done status → never dispatched
- EC-5: dedup intact — is_already_queued prevents double dispatch

All integration tests use real git repos (ADR-013: no DB mocks in integration tests).
Monkeypatching dispatch_qa/dispatch_reflect is required because _pueue_add needs
a live pueue daemon — we test the dispatch DECISION, not pueue submission.

NOTE: These tests WILL fail until Task 2 implements _step6_dispatch_qa_reflect
in callback.py.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import callback  # noqa: E402
import db  # noqa: E402


# ---------------------------------------------------------------------------
# Shared git helper
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
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


# ---------------------------------------------------------------------------
# DB isolation fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path):
    """Fresh SQLite DB per test — prevents circuit breaker state from accumulating."""
    db_path = str(tmp_path / "orchestrator.db")
    conn = sqlite3.connect(db_path)
    schema = (Path(VPS_DIR) / "schema.sql").read_text()
    conn.executescript(schema)
    conn.close()
    db._MIGRATIONS_APPLIED = False
    with patch.object(db, "DB_PATH", db_path):
        yield


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _make_origin_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare 'origin' repo and a working clone on develop branch."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "-q", "-b", "develop")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "push", "-u", "origin", "develop")
    return origin, repo


def _setup_spec(repo: Path, spec_id: str, allowed_file: str) -> None:
    """Create ai/features/{spec_id}-spec.md on disk with v1 allowlist marker."""
    features_dir = repo / "ai" / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    spec_path = features_dir / f"{spec_id}-spec.md"
    spec_path.write_text(
        f"# {spec_id}\n\n"
        "<!-- callback-allowlist v1: backticked paths only, one per row. -->\n\n"
        "## Allowed Files\n\n"
        f"- `{allowed_file}`\n"
    )


def _add_impl_commit(repo: Path, spec_id: str, file_path: str) -> None:
    """Create file, commit with feat({spec_id}): implement feature, push to origin/develop."""
    full_path = repo / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(f"# {spec_id} implementation\n")
    _git(repo, "add", file_path)
    _git(repo, "commit", "-m", f"feat({spec_id}): implement feature")
    _git(repo, "push", "origin", "develop")


def _seed_project(project_id: str, project_path: str, provider: str = "claude") -> None:
    """INSERT into project_state table so get_project_state returns data."""
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO project_state (project_id, path, provider) VALUES (?, ?, ?)",
        (project_id, project_path, provider),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# EC-1: merged + no complete signal → dispatch
# ---------------------------------------------------------------------------


class TestMergedNoCompleteSignal:
    def test_ec1_merged_no_complete_dispatches_qa_reflect(self, tmp_path, monkeypatch):
        """BUG-1387/BUG-1313 class: impl merged on origin/develop, task_status=''.

        Expectation: _step6_dispatch_qa_reflect dispatches QA + Reflect despite
        missing completion signal, because merge is independently confirmed.
        """
        _origin, repo = _make_origin_repo(tmp_path)

        spec_id = "BUG-901"
        allowed_file = "src/feature.py"
        _setup_spec(repo, spec_id, allowed_file)
        _add_impl_commit(repo, spec_id, allowed_file)
        _seed_project("testproj", str(repo))

        qa_calls = []
        reflect_calls = []

        def _mock_dispatch_qa(project_id, project_path, sid, provider):
            qa_calls.append({"project_id": project_id, "spec_id": sid})

        def _mock_dispatch_reflect(project_id, project_path, task_label, provider):
            reflect_calls.append({"project_id": project_id, "task_label": task_label})

        monkeypatch.setattr(callback, "dispatch_qa", _mock_dispatch_qa)
        monkeypatch.setattr(callback, "dispatch_reflect", _mock_dispatch_reflect)

        callback._step6_dispatch_qa_reflect(
            skill="autopilot",
            status="done",
            task_status="",
            project_id="testproj",
            task_label=f"testproj:{spec_id}",
            preview="",
        )

        assert len(qa_calls) == 1, f"expected 1 QA dispatch, got {len(qa_calls)}"
        assert qa_calls[0]["spec_id"] == spec_id
        assert len(reflect_calls) == 1, f"expected 1 reflect dispatch, got {len(reflect_calls)}"


# ---------------------------------------------------------------------------
# EC-2: no merge + no complete signal → skip
# ---------------------------------------------------------------------------


class TestNoMergeNoComplete:
    def test_ec2_no_merge_no_complete_skips_dispatch(self, tmp_path, monkeypatch):
        """SIGKILL / no-work case: task_status='' and NO impl commit on origin/develop.

        Expectation: neither QA nor Reflect dispatched (allowlist preserved).
        """
        _origin, repo = _make_origin_repo(tmp_path)

        spec_id = "BUG-902"
        allowed_file = "src/other.py"
        _setup_spec(repo, spec_id, allowed_file)
        # Intentionally NO _add_impl_commit — nothing pushed to origin/develop
        _seed_project("testproj", str(repo))

        qa_calls = []
        reflect_calls = []

        def _mock_dispatch_qa(project_id, project_path, sid, provider):
            qa_calls.append(sid)

        def _mock_dispatch_reflect(project_id, project_path, task_label, provider):
            reflect_calls.append(task_label)

        monkeypatch.setattr(callback, "dispatch_qa", _mock_dispatch_qa)
        monkeypatch.setattr(callback, "dispatch_reflect", _mock_dispatch_reflect)

        callback._step6_dispatch_qa_reflect(
            skill="autopilot",
            status="done",
            task_status="",
            project_id="testproj",
            task_label=f"testproj:{spec_id}",
            preview="",
        )

        assert len(qa_calls) == 0, "no QA must be dispatched when no impl commit on develop"
        assert len(reflect_calls) == 0, "no Reflect must be dispatched when no impl on develop"


# ---------------------------------------------------------------------------
# EC-3: explicit complete still dispatches normally
# ---------------------------------------------------------------------------


class TestExplicitCompleteUnchanged:
    def test_ec3_explicit_complete_dispatches_normally(self, tmp_path, monkeypatch):
        """task_status='complete' must dispatch QA + Reflect (original behavior)."""
        _origin, repo = _make_origin_repo(tmp_path)

        spec_id = "FTR-903"
        allowed_file = "src/service.py"
        _setup_spec(repo, spec_id, allowed_file)
        _seed_project("testproj", str(repo))

        qa_calls = []
        reflect_calls = []

        def _mock_dispatch_qa(project_id, project_path, sid, provider):
            qa_calls.append(sid)

        def _mock_dispatch_reflect(project_id, project_path, task_label, provider):
            reflect_calls.append(task_label)

        monkeypatch.setattr(callback, "dispatch_qa", _mock_dispatch_qa)
        monkeypatch.setattr(callback, "dispatch_reflect", _mock_dispatch_reflect)

        callback._step6_dispatch_qa_reflect(
            skill="autopilot",
            status="done",
            task_status="complete",
            project_id="testproj",
            task_label=f"testproj:{spec_id}",
            preview="",
        )

        assert len(qa_calls) == 1, "explicit 'complete' must dispatch QA"
        assert qa_calls[0] == spec_id
        assert len(reflect_calls) == 1, "explicit 'complete' must dispatch Reflect"


# ---------------------------------------------------------------------------
# EC-4: blocked / needs_review / non-done status never dispatch
# ---------------------------------------------------------------------------


class TestBlockedNeverDispatches:
    @pytest.mark.parametrize("blocked_status", ["blocked", "needs_review"])
    def test_ec4_blocked_status_skips_dispatch(
        self, tmp_path, monkeypatch, blocked_status
    ):
        """Explicit block signal always skips QA + Reflect, even if impl IS merged."""
        _origin, repo = _make_origin_repo(tmp_path)

        spec_id = "TECH-904"
        allowed_file = "src/handler.py"
        _setup_spec(repo, spec_id, allowed_file)
        _add_impl_commit(repo, spec_id, allowed_file)
        _seed_project("testproj", str(repo))

        qa_calls = []
        reflect_calls = []

        monkeypatch.setattr(
            callback, "dispatch_qa", lambda *a, **kw: qa_calls.append(a)
        )
        monkeypatch.setattr(
            callback, "dispatch_reflect", lambda *a, **kw: reflect_calls.append(a)
        )

        callback._step6_dispatch_qa_reflect(
            skill="autopilot",
            status="done",
            task_status=blocked_status,
            project_id="testproj",
            task_label=f"testproj:{spec_id}",
            preview="",
        )

        assert len(qa_calls) == 0, (
            f"task_status={blocked_status!r} must prevent QA dispatch"
        )
        assert len(reflect_calls) == 0, (
            f"task_status={blocked_status!r} must prevent Reflect dispatch"
        )

    def test_ec4_non_done_status_skips_dispatch(self, tmp_path, monkeypatch):
        """status='failed' (not 'done') must skip dispatch entirely."""
        _origin, repo = _make_origin_repo(tmp_path)

        spec_id = "FTR-905"
        allowed_file = "src/model.py"
        _setup_spec(repo, spec_id, allowed_file)
        # Even if impl is merged, status!=done must skip
        _add_impl_commit(repo, spec_id, allowed_file)
        _seed_project("testproj", str(repo))

        qa_calls = []
        reflect_calls = []

        monkeypatch.setattr(
            callback, "dispatch_qa", lambda *a, **kw: qa_calls.append(a)
        )
        monkeypatch.setattr(
            callback, "dispatch_reflect", lambda *a, **kw: reflect_calls.append(a)
        )

        callback._step6_dispatch_qa_reflect(
            skill="autopilot",
            status="failed",
            task_status="",
            project_id="testproj",
            task_label=f"testproj:{spec_id}",
            preview="",
        )

        assert len(qa_calls) == 0, "status='failed' must skip QA dispatch"
        assert len(reflect_calls) == 0, "status='failed' must skip Reflect dispatch"


# ---------------------------------------------------------------------------
# EC-5: dedup intact — is_already_queued prevents double dispatch
# ---------------------------------------------------------------------------


class TestDedupIntact:
    def test_ec5_dedup_prevents_double_qa_dispatch(self, monkeypatch):
        """dispatch_qa internal dedup: _pueue_add only called when is_already_queued=False.

        Tests the is_already_queued dedup inside dispatch_qa itself (which both
        the explicit_complete and merge_fallback paths use). First call goes
        through; second is blocked by is_already_queued returning True.
        """
        pueue_add_calls = []
        already_queued_responses = [False, True]  # first call: not queued; second: already queued
        call_count = {"n": 0}

        def _mock_is_already_queued(label: str) -> bool:
            idx = call_count["n"]
            call_count["n"] += 1
            return already_queued_responses[idx] if idx < len(already_queued_responses) else True

        def _mock_pueue_add(group: str, label: str, cmd: list) -> int | None:
            pueue_add_calls.append(label)
            return 42  # fake pueue_id

        monkeypatch.setattr(callback, "is_already_queued", _mock_is_already_queued)
        monkeypatch.setattr(callback, "_pueue_add", _mock_pueue_add)
        # Prevent DB calls in dispatch_qa
        monkeypatch.setattr(db, "try_acquire_slot", lambda *a, **kw: None)
        monkeypatch.setattr(db, "log_task", lambda *a, **kw: None)

        qa_label_first = "testproj:qa-BUG-901"
        qa_label_second = "testproj:qa-BUG-901"

        # First dispatch: not yet queued → should call _pueue_add
        callback.dispatch_qa("testproj", "/some/path", "BUG-901", "claude")
        # Second dispatch: already queued → should NOT call _pueue_add
        callback.dispatch_qa("testproj", "/some/path", "BUG-901", "claude")

        assert len(pueue_add_calls) == 1, (
            f"_pueue_add called {len(pueue_add_calls)} times; expected exactly 1 "
            f"(second dispatch should be blocked by is_already_queued)"
        )
        assert qa_label_first in pueue_add_calls[0], (
            f"expected label {qa_label_first!r} in pueue_add call, got {pueue_add_calls[0]!r}"
        )
        assert qa_label_second == qa_label_first  # sanity
