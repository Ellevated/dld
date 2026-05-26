"""TECH-194 Task 2 — Integration: pre-commit hook blocks lifecycle commits from worktrees.

Tests Layer C fixes:
  C1: hook rejects direct ai/lifecycle/ commit from a worktree
  C2: hook does not fail-open when worktree branch lacks .claude/hooks/
  C3: LIFECYCLE_WRITE_AUTHORIZED=1 allows commit (bypass path)
  C4: install-hooks-all-worktrees.sh converts relative hooksPath to absolute

No mocks per ADR-013. Uses real git repos, real bash, real node.
Skips gracefully when node or bash is missing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GIT_HOOKS_DIR = PROJECT_ROOT / ".git-hooks"
GUARD_MJS = PROJECT_ROOT / ".claude" / "hooks" / "pre-commit-lifecycle-guard.mjs"
INSTALL_HELPER = PROJECT_ROOT / "scripts" / "vps" / "install-hooks-all-worktrees.sh"
EVENT_WRITER = PROJECT_ROOT / "scripts" / "vps" / "event_writer.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_node() -> bool:
    return shutil.which("node") is not None


def _has_bash() -> bool:
    return shutil.which("bash") is not None


def _git(repo: Path, *args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        env=full_env,
    )


def _init_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with ai/lifecycle/ and .git-hooks/pre-commit wired."""
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")

    # Create ai/lifecycle/ directory with .gitkeep
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("")

    # Copy real .git-hooks/pre-commit from project root (with C2 GIT_COMMON_DIR fix)
    hooks_dir = repo / ".git-hooks"
    hooks_dir.mkdir()
    shutil.copy(GIT_HOOKS_DIR / "pre-commit", hooks_dir / "pre-commit")
    (hooks_dir / "pre-commit").chmod(0o755)

    # Copy real guard.mjs from project root (with C3 absolute path fix)
    claude_hooks = repo / ".claude" / "hooks"
    claude_hooks.mkdir(parents=True)
    shutil.copy(GUARD_MJS, claude_hooks / "pre-commit-lifecycle-guard.mjs")
    (claude_hooks / "pre-commit-lifecycle-guard.mjs").chmod(0o755)

    # Initial commit
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")

    # Set absolute hooksPath (C1 fix)
    abs_hooks = str(hooks_dir)
    _git(repo, "config", "core.hooksPath", abs_hooks)

    return repo


def _make_worktree(repo: Path, wt_name: str, branch: str) -> Path:
    """Add a worktree for the given branch."""
    wt_path = repo.parent / wt_name
    _git(repo, "worktree", "add", str(wt_path), "-b", branch)
    return wt_path


def _stage_lifecycle_yaml(repo_or_wt: Path, spec_id: str = "TEST-001") -> Path:
    """Stage a new ai/lifecycle/*.yaml file in the given worktree/repo."""
    yaml_path = repo_or_wt / "ai" / "lifecycle" / f"{spec_id}.yaml"
    yaml_path.write_text(f"spec_id: {spec_id}\nstatus: queued\n")
    _git(repo_or_wt, "add", f"ai/lifecycle/{spec_id}.yaml")
    return yaml_path


def _commit(
    repo_or_wt: Path,
    msg: str = "chore: test commit",
    env: dict | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    base_env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@test.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@test.com",
    }
    if env:
        base_env.update(env)
    return subprocess.run(
        ["git", "-C", str(repo_or_wt), "commit", "-m", msg],
        capture_output=True,
        text=True,
        check=check,
        env={**os.environ, **base_env},
    )


# ---------------------------------------------------------------------------
# Test 1: worktree commit blocked (C1 + C2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_node(), reason="node not available")
@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_worktree_commit_blocked(tmp_path):
    """C1+C2: commit of ai/lifecycle/ from worktree is rejected (exit 1).

    Verifies that:
    - absolute hooksPath works from any worktree CWD
    - GIT_COMMON_DIR resolution finds guard.mjs in main repo even from worktree
    """
    repo = _init_repo(tmp_path)
    wt = _make_worktree(repo, "wt-blocked", "feature/test-blocked")

    _stage_lifecycle_yaml(wt, "BLOCKED-001")
    result = _commit(wt, "chore: should be blocked", check=False)

    assert result.returncode != 0, (
        f"Expected hook to block commit, but it succeeded.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # Guard message should appear
    assert "lifecycle" in result.stderr.lower() or "lifecycle" in result.stdout.lower(), (
        f"Expected lifecycle guard message in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 2: LIFECYCLE_WRITE_AUTHORIZED=1 allows commit (C3 bypass path)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_node(), reason="node not available")
@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_worktree_commit_allowed_with_authorized(tmp_path):
    """C3: LIFECYCLE_WRITE_AUTHORIZED=1 env var allows bypass (exit 0).

    The bypass path in guard.mjs calls event_writer.py (best-effort).
    The commit must succeed regardless of whether event_writer.py exists.
    """
    repo = _init_repo(tmp_path)
    wt = _make_worktree(repo, "wt-authorized", "feature/test-authorized")

    _stage_lifecycle_yaml(wt, "AUTHORIZED-001")
    result = _commit(
        wt,
        "chore: authorized bypass",
        env={"LIFECYCLE_WRITE_AUTHORIZED": "1"},
        check=False,
    )

    assert result.returncode == 0, (
        f"Expected authorized bypass to allow commit, but it failed.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 3: guard runs when worktree branch lacks .claude/hooks/ (C2 no fail-open)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_node(), reason="node not available")
@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_guard_runs_when_worktree_branch_lacks_claude_hooks(tmp_path):
    """C2: guard still runs from worktree even if branch doesn't contain .claude/hooks/.

    The GIT_COMMON_DIR resolution ensures guard.mjs is always sourced from the
    main repo, not the worktree's branch-level files.
    """
    repo = _init_repo(tmp_path)

    # Create worktree on a fresh branch that starts clean (no .claude/hooks/ yet)
    # We simulate by removing .claude/hooks from the worktree's working copy
    # (the hook is in the main repo, so GIT_COMMON_DIR should still find it)
    wt = _make_worktree(repo, "wt-no-hooks", "feature/test-no-hooks")

    # Remove .claude/hooks/ from the worktree working directory
    # (simulates a branch that doesn't have this dir in its tracked files)
    wt_claude_hooks = wt / ".claude" / "hooks"
    if wt_claude_hooks.exists():
        shutil.rmtree(wt_claude_hooks)

    _stage_lifecycle_yaml(wt, "NOFAIL-001")
    result = _commit(wt, "chore: no fail-open test", check=False)

    # Hook must still run and block the commit — NOT silently pass (fail-open)
    assert result.returncode != 0, (
        f"Expected guard to block even without .claude/hooks/ in worktree branch.\n"
        f"This would be fail-open (C2 bug).\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Test 4: install-hooks-all-worktrees.sh converts relative to absolute (C1 migration)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_bash(), reason="bash not available")
def test_install_helper_converts_relative_to_absolute(tmp_path):
    """C1: install-hooks-all-worktrees.sh re-sets hooksPath to absolute value."""
    if not INSTALL_HELPER.exists():
        pytest.skip(f"install-hooks-all-worktrees.sh not found at {INSTALL_HELPER}")

    repo = _init_repo(tmp_path)

    # Pre-set relative hooksPath (simulates legacy setup)
    _git(repo, "config", "core.hooksPath", ".git-hooks")
    current = _git(repo, "config", "core.hooksPath").stdout.strip()
    assert current == ".git-hooks", f"Pre-condition: expected relative path, got {current!r}"

    # Create a minimal projects.json pointing at our temp repo
    projects_json = tmp_path / "test-projects.json"
    projects_json.write_text(json.dumps([{"id": "test", "path": str(repo)}]))

    # Run the migration helper
    result = subprocess.run(
        ["bash", str(INSTALL_HELPER), str(projects_json)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ},
    )

    assert result.returncode == 0, (
        f"install-hooks-all-worktrees.sh failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Verify hooksPath is now absolute
    new_hooks_path = _git(repo, "config", "core.hooksPath").stdout.strip()
    assert new_hooks_path.startswith("/"), (
        f"Expected absolute hooksPath after migration, got: {new_hooks_path!r}\n"
        f"Script output:\n{result.stdout}"
    )
    assert new_hooks_path == str(repo / ".git-hooks"), (
        f"Expected hooksPath={repo / '.git-hooks'}, got {new_hooks_path!r}"
    )
    assert "[FIX]" in result.stdout, (
        f"Expected [FIX] marker in output (indicating migration happened).\n{result.stdout}"
    )
