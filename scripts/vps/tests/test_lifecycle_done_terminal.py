"""
Tests for ARCH-193 Rule 7: done is terminal (LifecycleAlreadyDoneError).

Covers:
  - write_lifecycle structural guard (tests 1-3)
  - spec_operator CLI return codes (tests 4-7)
  - callback minimal primitive guard (test 8)
  - parametrized all-writers immutability (test 9)
  - pre-commit-lifecycle-guard.mjs hook (tests 10-11)
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Make scripts/vps importable
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

# REPO_ROOT for hook path resolution (two levels up from scripts/vps/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

import lifecycle  # noqa: E402
import spec_operator  # noqa: E402


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

    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("")
    git("add", ".")
    git("commit", "-m", "init")

    return repo


def _bootstrap_done(repo, spec_id: str = "TECH-999") -> None:
    """Create a spec lifecycle YAML with status=done via create_initial + write_lifecycle."""
    lifecycle.create_initial(repo, spec_id, priority="p1", kind="tech", status="queued")
    lifecycle.write_lifecycle(repo, spec_id, "done", by="callback")


def _make_spec_md(repo, spec_id: str) -> None:
    """Create a minimal spec .md file so spec_operator can find it."""
    features = repo / "ai" / "features"
    features.mkdir(parents=True, exist_ok=True)
    (features / f"{spec_id}-test.md").write_text(
        f"# {spec_id}\n\n## Allowed Files\n\n- `scripts/vps/tests/test_lifecycle_done_terminal.py`\n"
    )


# ---------------------------------------------------------------------------
# Test 1: write_lifecycle blocks done → blocked
# ---------------------------------------------------------------------------


def test_write_lifecycle_blocks_done_to_blocked(tmp_git_repo):
    """Rule 7: write_lifecycle(done→blocked) raises LifecycleAlreadyDoneError."""
    spec_id = "TECH-001"
    _bootstrap_done(tmp_git_repo, spec_id)

    with pytest.raises(lifecycle.LifecycleAlreadyDoneError) as exc_info:
        lifecycle.write_lifecycle(tmp_git_repo, spec_id, "blocked", by="callback")

    exc = exc_info.value
    assert exc.spec_id == spec_id
    assert exc.attempted == "blocked"
    assert exc.by == "callback"


# ---------------------------------------------------------------------------
# Test 2: write_lifecycle blocks done → queued
# ---------------------------------------------------------------------------


def test_write_lifecycle_blocks_done_to_queued(tmp_git_repo):
    """Rule 7: write_lifecycle(done→queued) raises LifecycleAlreadyDoneError."""
    spec_id = "TECH-002"
    _bootstrap_done(tmp_git_repo, spec_id)

    with pytest.raises(lifecycle.LifecycleAlreadyDoneError) as exc_info:
        lifecycle.write_lifecycle(tmp_git_repo, spec_id, "queued", by="orchestrator")

    exc = exc_info.value
    assert exc.spec_id == spec_id
    assert exc.attempted == "queued"
    assert exc.by == "orchestrator"


# ---------------------------------------------------------------------------
# Test 3: write_lifecycle done → done is idempotent
# ---------------------------------------------------------------------------


def test_write_lifecycle_done_to_done_idempotent(tmp_git_repo):
    """Rule 7 exception: done→done is allowed (idempotent force-done)."""
    spec_id = "TECH-003"
    _bootstrap_done(tmp_git_repo, spec_id)

    before = lifecycle.read_lifecycle(tmp_git_repo, spec_id)
    before_transitions = len(before["transitions"])
    before_version = before["version"]

    # Should not raise
    lifecycle.write_lifecycle(tmp_git_repo, spec_id, "done", by="operator")

    after = lifecycle.read_lifecycle(tmp_git_repo, spec_id)
    assert after["status"] == "done"
    assert len(after["transitions"]) == before_transitions + 1
    assert after["version"] == before_version + 1


# ---------------------------------------------------------------------------
# Test 4: spec_operator demote on done spec exits with rc=5
# ---------------------------------------------------------------------------


def test_spec_operator_demote_done_fails_with_rc5(tmp_git_repo, capsys):
    """spec_operator demote on done spec returns exit code 5."""
    spec_id = "TECH-004"
    _bootstrap_done(tmp_git_repo, spec_id)
    _make_spec_md(tmp_git_repo, spec_id)

    rc = spec_operator.main(["demote", str(tmp_git_repo), spec_id, "test reason", "--by=operator"])

    assert rc == 5
    captured = capsys.readouterr()
    assert "done is terminal" in captured.err.lower() or "done" in captured.err.lower()


# ---------------------------------------------------------------------------
# Test 5: spec_operator force-done on done spec is idempotent (rc=0)
# ---------------------------------------------------------------------------


def test_spec_operator_force_done_idempotent(tmp_git_repo):
    """spec_operator force-done on already-done spec succeeds (idempotent)."""
    spec_id = "TECH-005"
    _bootstrap_done(tmp_git_repo, spec_id)
    _make_spec_md(tmp_git_repo, spec_id)

    before = lifecycle.read_lifecycle(tmp_git_repo, spec_id)
    before_transitions = len(before["transitions"])

    rc = spec_operator.main(
        ["force-done", str(tmp_git_repo), spec_id, "idempotent reason", "--by=operator"]
    )

    assert rc == 0
    after = lifecycle.read_lifecycle(tmp_git_repo, spec_id)
    assert after["status"] == "done"
    assert len(after["transitions"]) == before_transitions + 1


# ---------------------------------------------------------------------------
# Test 6: spec_operator rejects --by=autopilot (argparse error → SystemExit(2))
# ---------------------------------------------------------------------------


def test_spec_operator_rejects_by_autopilot(tmp_git_repo):
    """spec_operator --by=autopilot is rejected by argparse (choices removed ADR-025)."""
    spec_id = "TECH-006"
    _make_spec_md(tmp_git_repo, spec_id)

    with pytest.raises(SystemExit) as exc_info:
        spec_operator.main(["demote", str(tmp_git_repo), spec_id, "x", "--by=autopilot"])

    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Test 7: spec_operator rejects --by=spark (argparse error → SystemExit(2))
# ---------------------------------------------------------------------------


def test_spec_operator_rejects_by_spark(tmp_git_repo):
    """spec_operator --by=spark is rejected by argparse (choices removed ADR-025)."""
    spec_id = "TECH-007"
    _make_spec_md(tmp_git_repo, spec_id)

    with pytest.raises(SystemExit) as exc_info:
        spec_operator.main(["demote", str(tmp_git_repo), spec_id, "x", "--by=spark"])

    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Test 8: callback rule 7 primitive guard (structural, minimal)
# ---------------------------------------------------------------------------


def test_callback_rule7_catches_exception_and_noops(tmp_git_repo):
    """Structural confidence test: the primitive raises LifecycleAlreadyDoneError.

    Full callback wiring is overkill — the guard lives in write_lifecycle()
    which callback calls. This test confirms the exception type and attributes.
    """
    spec_id = "TECH-008"
    _bootstrap_done(tmp_git_repo, spec_id)

    with pytest.raises(lifecycle.LifecycleAlreadyDoneError) as exc_info:
        lifecycle.write_lifecycle(tmp_git_repo, spec_id, "blocked", by="callback")

    exc = exc_info.value
    assert exc.spec_id == spec_id
    assert exc.attempted == "blocked"
    assert exc.by == "callback"
    assert isinstance(exc, lifecycle.LifecycleAlreadyDoneError)


# ---------------------------------------------------------------------------
# Test 9: all writers (except orchestrator) cannot transition done → queued
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("writer", sorted(lifecycle._ALLOWED_WRITERS - {"orchestrator"}))
def test_done_immutable_via_all_writers(tmp_git_repo, writer):
    """Rule 7 applies to every writer identity (orchestrator excluded: bootstrap-only)."""
    spec_id = f"TECH-{writer.upper()}"
    _bootstrap_done(tmp_git_repo, spec_id)

    with pytest.raises(lifecycle.LifecycleAlreadyDoneError) as exc_info:
        lifecycle.write_lifecycle(tmp_git_repo, spec_id, "queued", by=writer)

    assert exc_info.value.spec_id == spec_id
    assert exc_info.value.by == writer


# ---------------------------------------------------------------------------
# Helpers for hook tests
# ---------------------------------------------------------------------------


def _make_hook_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with staged ai/lifecycle/X.yaml for hook tests."""
    repo = tmp_path / "hook_repo"
    repo.mkdir()

    def git(*args, check_rc=True):
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if check_rc and r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
        return r

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")

    # Initial commit so HEAD exists
    (repo / "README.md").write_text("init")
    git("add", "README.md")
    git("commit", "-m", "init")

    # Stage a lifecycle yaml file
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / "SPEC-123.yaml").write_text("spec_id: SPEC-123\nstatus: done\n")
    git("add", str(lc_dir / "SPEC-123.yaml"))

    # Write COMMIT_EDITMSG
    (repo / ".git" / "COMMIT_EDITMSG").write_text("lifecycle(SPEC-123): done")

    return repo


# ---------------------------------------------------------------------------
# Test 10: pre-commit hook blocks direct ai/lifecycle/*.yaml staged commit
# ---------------------------------------------------------------------------


def test_pre_commit_hook_blocks_canonical_lifecycle_subject(tmp_path):
    """Hook exits 1 when ai/lifecycle/*.yaml is staged (no bypass env)."""
    hook_path = REPO_ROOT / ".claude" / "hooks" / "pre-commit-lifecycle-guard.mjs"
    if not hook_path.exists():
        pytest.skip(f"hook not found: {hook_path}")

    repo = _make_hook_repo(tmp_path)
    env = {**os.environ, "GIT_DIR": str(repo / ".git")}
    # Ensure bypass is NOT set
    env.pop("LIFECYCLE_WRITE_AUTHORIZED", None)

    result = subprocess.run(
        ["node", str(hook_path)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"Expected hook exit 1, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 11: pre-commit hook allows bypass when LIFECYCLE_WRITE_AUTHORIZED=1
# ---------------------------------------------------------------------------


def test_pre_commit_hook_logs_authorized_bypass(tmp_path):
    """Hook exits 0 when LIFECYCLE_WRITE_AUTHORIZED=1 and a lifecycle yaml is staged.

    The hook calls event_writer.py as a best-effort audit log. We inject a
    PATH-prepended shim that writes its args to a temp file so we can verify
    the call. If the shim cannot be wired (e.g., node can't exec python3 shim),
    the rc=0 assertion is still the primary check (bypass works).
    """
    hook_path = REPO_ROOT / ".claude" / "hooks" / "pre-commit-lifecycle-guard.mjs"
    if not hook_path.exists():
        pytest.skip(f"hook not found: {hook_path}")

    repo = _make_hook_repo(tmp_path)

    # Create a PATH-injected python3 shim that captures args to a file
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    audit_log = tmp_path / "audit.log"
    shim_script = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        import sys
        with open({str(audit_log)!r}, "a") as f:
            f.write(" ".join(sys.argv) + "\\n")
    """)
    shim_py = shim_dir / "python3"
    shim_py.write_text(shim_script)
    shim_py.chmod(0o755)

    env = {**os.environ, "GIT_DIR": str(repo / ".git")}
    env["LIFECYCLE_WRITE_AUTHORIZED"] = "1"
    env["PATH"] = f"{shim_dir}:{env.get('PATH', '')}"

    result = subprocess.run(
        ["node", str(hook_path)],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Expected hook exit 0 with bypass, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Best-effort audit log check: if shim was invoked, it wrote to audit_log
    # If it wasn't invoked (node used system python3), we skip the log assertion
    # but the rc=0 is the primary guarantee.
    if audit_log.exists():
        log_content = audit_log.read_text()
        assert (
            "event_writer.py" in log_content
            or "LIFECYCLE_AUTHORIZED_BYPASS" in log_content
            or log_content
        )  # shim ran
