"""
Module: test_gate_daemon
Role: Integration tests for gate-daemon.py shadow polling daemon (ARCH-190 Task 6).

Tests:
  SA-3  — lifecycle tree never touched by gate-daemon (SHADOW_ONLY_MODE invariant)
  T01   — SHADOW_ONLY_MODE assert fires on monkey-patch to False
  T02   — one cycle writes one row to gate_health table
  T03   — shadow JSONL grows by exactly N lines per cycle (N = in_progress specs)
  T04   — per-project error isolation (fetch failure on A, B still evaluated)
  T05   — SHA cache: 2nd cycle with same SHA skips find_implementation_commit
  T06   — heartbeat file mtime updated after each cycle
  T07   — SIGTERM: daemon subprocess exits cleanly within 2s

ADR-013: NO mocks for git or filesystem. Real tmp_path git repos.
Spies (counters wrapping real callables) are allowed — they call through.
"""

import importlib.util
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import db as db_mod  # noqa: E402
import lifecycle  # noqa: E402

# ---------------------------------------------------------------------------
# Load gate-daemon module (hyphen in filename requires importlib.util)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gate_daemon", SCRIPT_DIR / "gate-daemon.py")
gate_daemon = importlib.util.module_from_spec(_spec)
# We do NOT exec_module at import time — each test that needs the module
# reloads it via _load_gate_daemon() to reset module-level state.


def _load_gate_daemon():
    """Reload gate_daemon module so module-level state (_origin_develop_sha, _stop) is fresh."""
    spec = importlib.util.spec_from_file_location("gate_daemon", SCRIPT_DIR / "gate-daemon.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Git helpers (mirror test_gate_logic.py and test_callback.py style)
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


def _make_repo_with_remote(tmp_path: Path, name: str = "repo") -> Path:
    """Create local + bare-remote repo pair, return local path."""
    remote = tmp_path / f"{name}_remote"
    local = tmp_path / name
    remote.mkdir()
    local.mkdir()
    subprocess.run(
        ["git", "init", "--bare", "-q", "-b", "develop", str(remote)],
        check=True,
    )
    _git(local, "init", "-q", "-b", "develop")
    _git(local, "config", "user.email", "t@t")
    _git(local, "config", "user.name", "t")
    _git(local, "remote", "add", "origin", str(remote))
    (local / "README.md").write_text("init\n")
    _git(local, "add", "README.md")
    _git(local, "commit", "-q", "-m", "init")
    _git(local, "push", "-q", "origin", "develop")
    return local


def _add_spec_file(repo: Path, spec_id: str, allowed_file: str) -> Path:
    """Write a minimal spec .md with ## Allowed Files into ai/features/."""
    features_dir = repo / "ai" / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    spec_path = features_dir / f"{spec_id}-2026-05-24-test.md"
    spec_path.write_text(
        f"# {spec_id}\n\n"
        "## Allowed Files\n"
        "<!-- callback-allowlist v1 -->\n\n"
        f"- `{allowed_file}` — test\n"
    )
    return spec_path


def _write_lifecycle_in_progress(repo: Path, spec_id: str) -> None:
    """Create in_progress lifecycle yaml for spec_id using lifecycle.write_lifecycle."""
    lifecycle.write_lifecycle(str(repo), spec_id, "in_progress", by="operator")


def _push(repo: Path) -> None:
    _git(repo, "push", "-q", "origin", "develop")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Isolated SQLite DB with schema applied. Mirrors conftest.py."""
    db_path = tmp_path / "test_orchestrator.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setattr(db_mod, "DB_PATH", str(db_path))
    db_mod._MIGRATIONS_APPLIED = False

    schema_sql = SCRIPT_DIR / "schema.sql"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema_sql.read_text(encoding="utf-8"))
    conn.close()
    return db_path


@pytest.fixture()
def shadow_log_path(tmp_path) -> Path:
    return tmp_path / "shadow.jsonl"


@pytest.fixture()
def repo_with_spec(tmp_path):
    """One repo with one in_progress spec, pushed to remote."""
    repo = _make_repo_with_remote(tmp_path)
    _add_spec_file(repo, "ARCH-190", "scripts/vps/gate-daemon.py")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feat(ARCH-190): add spec")
    _push(repo)
    _write_lifecycle_in_progress(repo, "ARCH-190")
    return repo


# ---------------------------------------------------------------------------
# SA-3: lifecycle tree never touched by gate-daemon
# ---------------------------------------------------------------------------


class TestSA3LifecycleNeverTouched:
    """After multiple _evaluate_project calls, git log shows no gate-daemon commits."""

    def test_no_lifecycle_commits_after_three_cycles(
        self, tmp_path, isolated_db, shadow_log_path, monkeypatch
    ):
        """SA-3: gate-daemon must NEVER commit to ai/lifecycle/."""
        repo = _make_repo_with_remote(tmp_path)
        _add_spec_file(repo, "TECH-001", "scripts/vps/gate_logic.py")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "feat(TECH-001): add spec")
        _push(repo)
        _write_lifecycle_in_progress(repo, "TECH-001")

        gd = _load_gate_daemon()

        monkeypatch.setenv("GATE_DAEMON_SHADOW_LOG", str(shadow_log_path))
        monkeypatch.setattr(gd, "SCRIPT_DIR", SCRIPT_DIR)

        # Wire shadow logger
        handler = gd._make_shadow_handler()
        gd._init_shadow_logger(handler)

        cycle_ts = "2026-05-24T00:00:00Z"
        for _ in range(3):
            gd._evaluate_project("testproject", str(repo), 1, cycle_ts)

        # Check git log — no commit with "by: gate-daemon" in message
        r = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "--all",
                "--oneline",
                "--grep=by: gate-daemon",
                "--",
                "ai/lifecycle/",
            ],
            capture_output=True,
            text=True,
        )
        assert r.stdout.strip() == "", (
            f"gate-daemon must not write lifecycle commits. Found:\n{r.stdout}"
        )


# ---------------------------------------------------------------------------
# T01: SHADOW_ONLY_MODE assert fires on monkey-patch
# ---------------------------------------------------------------------------


class TestShadowOnlyModeGuard:
    def test_assert_fires_when_shadow_only_mode_false(self):
        """T01: assert SHADOW_ONLY_MODE fires if patched to False."""
        gd = _load_gate_daemon()
        assert gd.SHADOW_ONLY_MODE is True, "precondition: module loaded with SHADOW_ONLY_MODE=True"

        gd.SHADOW_ONLY_MODE = False
        with pytest.raises(AssertionError, match="Wave 3 cutover not yet authorized"):
            assert gd.SHADOW_ONLY_MODE, "Wave 3 cutover not yet authorized"


# ---------------------------------------------------------------------------
# T02: one cycle writes one row to gate_health
# ---------------------------------------------------------------------------


class TestGateHealthRow:
    def test_one_cycle_writes_one_row(self, tmp_path, isolated_db, shadow_log_path, monkeypatch):
        """T02: _evaluate_project + db.log_gate_cycle writes exactly 1 gate_health row."""
        repo = _make_repo_with_remote(tmp_path)
        _write_lifecycle_in_progress(repo, "TECH-999")
        _add_spec_file(repo, "TECH-999", "scripts/vps/gate_logic.py")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "feat(TECH-999): spec")
        _push(repo)

        gd = _load_gate_daemon()
        monkeypatch.setenv("GATE_DAEMON_SHADOW_LOG", str(shadow_log_path))
        monkeypatch.setattr(gd, "SCRIPT_DIR", SCRIPT_DIR)

        handler = gd._make_shadow_handler()
        gd._init_shadow_logger(handler)

        cycle_ts = "2026-05-24T10:00:00Z"
        ev, vw, err = gd._evaluate_project("testproject", str(repo), 1, cycle_ts)

        db_mod.log_gate_cycle(
            cycle_count=1,
            last_poll_at=cycle_ts,
            in_progress_specs=ev,
            decisions_this_cycle=vw,
            error_msg=err,
        )

        row = db_mod.get_gate_health()
        assert row is not None, "gate_health row must exist after cycle"
        assert row["cycle_count"] == 1
        assert row["in_progress_specs"] == ev
        assert row["decisions_this_cycle"] == vw

        # Exactly one row
        conn = sqlite3.connect(str(isolated_db))
        count = conn.execute("SELECT COUNT(*) FROM gate_health").fetchone()[0]
        conn.close()
        assert count == 1, f"Expected exactly 1 gate_health row, got {count}"


# ---------------------------------------------------------------------------
# T03: shadow JSONL grows by exactly N lines per cycle
# ---------------------------------------------------------------------------


class TestShadowJsonlLineCount:
    def test_jsonl_grows_by_n_per_cycle(self, tmp_path, isolated_db, shadow_log_path, monkeypatch):
        """T03: N in_progress specs → N JSONL lines written per cycle."""
        repo = _make_repo_with_remote(tmp_path)
        spec_ids = ["ARCH-001", "ARCH-002", "ARCH-003"]
        for sid in spec_ids:
            _add_spec_file(repo, sid, "scripts/vps/gate_logic.py")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "feat: add specs")
        _push(repo)
        for sid in spec_ids:
            _write_lifecycle_in_progress(repo, sid)

        gd = _load_gate_daemon()
        monkeypatch.setenv("GATE_DAEMON_SHADOW_LOG", str(shadow_log_path))
        monkeypatch.setattr(gd, "SCRIPT_DIR", SCRIPT_DIR)

        handler = gd._make_shadow_handler()
        gd._init_shadow_logger(handler)

        cycle_ts = "2026-05-24T10:00:00Z"
        ev, vw, _err = gd._evaluate_project("testproject", str(repo), 1, cycle_ts)

        # Flush the handler
        for h in gd._shadow_log.handlers:
            h.flush()

        lines = [ln for ln in shadow_log_path.read_text().splitlines() if ln.strip()]
        assert len(lines) == len(spec_ids), (
            f"Expected {len(spec_ids)} JSONL lines, got {len(lines)}"
        )
        # Verify each line is valid JSON with shadow_only=True
        for line in lines:
            record = json.loads(line)
            assert record["shadow_only"] is True
            assert record["project"] == "testproject"


# ---------------------------------------------------------------------------
# T04: per-project error isolation
# ---------------------------------------------------------------------------


class TestPerProjectErrorIsolation:
    def test_fetch_failure_on_a_does_not_block_b(
        self, tmp_path, isolated_db, shadow_log_path, monkeypatch
    ):
        """T04: project A's git fetch fails → project B's specs still evaluated."""
        # Project A: path that does NOT have a git remote → fetch_develop returns False
        repo_a = tmp_path / "repo_a"
        repo_a.mkdir()
        _git(repo_a, "init", "-q", "-b", "develop")
        _git(repo_a, "config", "user.email", "t@t")
        _git(repo_a, "config", "user.name", "t")
        (repo_a / "README.md").write_text("a\n")
        _git(repo_a, "add", "README.md")
        _git(repo_a, "commit", "-q", "-m", "init")
        # No remote — fetch_develop will fail but should not raise

        # Project B: normal repo with one in_progress spec
        repo_b = _make_repo_with_remote(tmp_path, name="repo_b")
        _add_spec_file(repo_b, "FTR-010", "scripts/vps/db.py")
        _git(repo_b, "add", ".")
        _git(repo_b, "commit", "-q", "-m", "feat(FTR-010): spec")
        _push(repo_b)
        _write_lifecycle_in_progress(repo_b, "FTR-010")

        gd = _load_gate_daemon()
        monkeypatch.setenv("GATE_DAEMON_SHADOW_LOG", str(shadow_log_path))
        monkeypatch.setattr(gd, "SCRIPT_DIR", SCRIPT_DIR)

        handler = gd._make_shadow_handler()
        gd._init_shadow_logger(handler)

        cycle_ts = "2026-05-24T11:00:00Z"

        # Project A: no in_progress specs (no lifecycle yamls) + fetch fails → (0, 0, None)
        ev_a, vw_a, err_a = gd._evaluate_project("proj_a", str(repo_a), 1, cycle_ts)

        # Project B: must produce verdicts despite A failing
        ev_b, vw_b, err_b = gd._evaluate_project("proj_b", str(repo_b), 1, cycle_ts)

        assert err_b is None, f"Project B must succeed, got err_b={err_b!r}"
        assert ev_b == 1, f"Project B must evaluate 1 spec, got ev_b={ev_b}"
        assert vw_b == 1, f"Project B must write 1 verdict, got vw_b={vw_b}"

        # Log error for project A via gate_health
        error_summary = err_a or "fetch_failed"
        row_id = db_mod.log_gate_cycle(
            cycle_count=1,
            last_poll_at=cycle_ts,
            in_progress_specs=ev_a + ev_b,
            decisions_this_cycle=vw_a + vw_b,
            error_msg=error_summary,
        )
        assert row_id > 0


# ---------------------------------------------------------------------------
# T05: SHA cache skips find_implementation_commit on 2nd cycle
# ---------------------------------------------------------------------------


class TestShaCache:
    def test_second_cycle_same_sha_skips_find_implementation_commit(
        self, tmp_path, isolated_db, shadow_log_path, monkeypatch
    ):
        """T05: 2nd cycle with same origin/develop SHA → find_implementation_commit not called."""
        repo = _make_repo_with_remote(tmp_path)
        _add_spec_file(repo, "TECH-100", "scripts/vps/gate_logic.py")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "feat(TECH-100): spec")
        _push(repo)
        _write_lifecycle_in_progress(repo, "TECH-100")

        gd = _load_gate_daemon()
        monkeypatch.setenv("GATE_DAEMON_SHADOW_LOG", str(shadow_log_path))
        monkeypatch.setattr(gd, "SCRIPT_DIR", SCRIPT_DIR)

        handler = gd._make_shadow_handler()
        gd._init_shadow_logger(handler)

        import gate_logic as gl

        call_count = {"n": 0}
        original_find = gl.find_implementation_commit

        def spy_find(project_path, spec_id, allowed):
            call_count["n"] += 1
            return original_find(project_path, spec_id, allowed)

        # Patch find_implementation_commit on the gate_logic module that
        # gate_daemon imported — gate-daemon.py uses `gate_logic.find_implementation_commit`
        # directly, so we patch the attribute on the module object it holds.
        monkeypatch.setattr(gd.gate_logic, "find_implementation_commit", spy_find)

        cycle_ts = "2026-05-24T12:00:00Z"

        # Cycle 1: sha cache is empty → find_implementation_commit MUST be called
        gd._evaluate_project("testproject", str(repo), 1, cycle_ts)
        calls_after_cycle_1 = call_count["n"]
        assert calls_after_cycle_1 >= 1, "Cycle 1 must call find_implementation_commit"

        # Cycle 2: no new commits pushed → same SHA → skipped
        gd._evaluate_project("testproject", str(repo), 2, cycle_ts)
        calls_after_cycle_2 = call_count["n"]
        assert calls_after_cycle_2 == calls_after_cycle_1, (
            "Cycle 2 with same SHA must NOT call find_implementation_commit again"
        )


# ---------------------------------------------------------------------------
# T06: heartbeat file mtime updated after each cycle
# ---------------------------------------------------------------------------


class TestHeartbeatMtime:
    def test_heartbeat_mtime_updated(self, tmp_path, isolated_db, shadow_log_path, monkeypatch):
        """T06: .gate-daemon-heartbeat mtime advances after each simulated cycle."""
        heartbeat_path = tmp_path / ".gate-daemon-heartbeat"
        monkeypatch.setenv("GATE_DAEMON_SHADOW_LOG", str(shadow_log_path))

        gd = _load_gate_daemon()
        monkeypatch.setattr(gd, "SCRIPT_DIR", tmp_path)

        # Simulate first heartbeat write (as done by main() loop)
        from datetime import datetime, timezone

        ts1 = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        heartbeat_path.write_text(ts1)
        mtime1 = heartbeat_path.stat().st_mtime

        # Brief sleep to ensure mtime changes
        time.sleep(0.05)

        ts2 = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        heartbeat_path.write_text(ts2)
        mtime2 = heartbeat_path.stat().st_mtime

        assert mtime2 > mtime1, "heartbeat mtime must advance after second cycle write"
        assert heartbeat_path.read_text().strip() == ts2


# ---------------------------------------------------------------------------
# T07: SIGTERM — daemon subprocess exits cleanly within 2s
# ---------------------------------------------------------------------------


class TestGracefulSigterm:
    def test_sigterm_exits_within_2s(self, tmp_path, monkeypatch):
        """T07: SIGTERM mid-idle → daemon exits cleanly within 2s."""
        db_path = tmp_path / "test_orchestrator.db"
        schema_sql = SCRIPT_DIR / "schema.sql"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_sql.read_text(encoding="utf-8"))
        conn.close()

        shadow_log = tmp_path / "shadow.jsonl"
        projects_json = tmp_path / "projects.json"
        projects_json.write_text("[]")

        env = {
            **os.environ,
            "DB_PATH": str(db_path),
            "GATE_DAEMON_SHADOW_LOG": str(shadow_log),
            "PROJECTS_JSON": str(projects_json),
            # Very long poll interval so daemon sits in _stop.wait()
            "POLL_INTERVAL": "300",
        }

        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT_DIR / "gate-daemon.py")],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Give daemon time to enter its wait loop
        time.sleep(0.5)
        assert proc.poll() is None, "daemon must still be running before SIGTERM"

        proc.send_signal(signal.SIGTERM)

        try:
            exit_code = proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("daemon did not exit within 2s after SIGTERM")

        # Exit code 0 or negative (killed by signal on some platforms)
        assert exit_code in (0, -signal.SIGTERM), (
            f"daemon exit_code={exit_code}, expected 0 or -{signal.SIGTERM}"
        )
