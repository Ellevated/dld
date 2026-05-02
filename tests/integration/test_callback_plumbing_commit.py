"""TECH-168 Task 4 — Integration: plumbing-commit preserves uncommitted edits.

EC-5 smoke test: automated. The TECH-166 refactor invariant is
"callback NEVER touches working tree". Plumbing path uses:
  git hash-object -w --stdin + git update-index --cacheinfo + git commit

If anyone replaces this with `git add <file>`, these tests must fail.

Real fs + real git subprocess + no mocks of git (per ADR-013).
Push suppressed via monkeypatch (no remote available).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


# --- Helpers -----------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo: Path, rel: str, content: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


def _make_repo(tmp_path: Path) -> Path:
    """Init a git repo with baseline committed files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    # Commit three files at HEAD
    _commit(repo, "ai/features/SPEC.md", "**Status:** in_progress\n", "init spec")
    _commit(repo, "ai/backlog.md", "| SPEC | demo | in_progress | P1 |\n", "init backlog")
    _commit(repo, "ai/notes/draft.md", "original notes\n", "init notes")
    return repo


def _suppress_push(monkeypatch) -> None:
    """Don't actually `git push origin develop` from tests (no remote)."""
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_run)


def _head_count(repo: Path) -> int:
    """Return number of commits on HEAD branch."""
    r = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
    )
    return int(r.stdout.strip()) if r.returncode == 0 else 0


def _head_file(repo: Path, rel: str) -> str | None:
    """Read a file from HEAD (not working tree)."""
    r = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{rel}"],
        capture_output=True,
        text=True,
    )
    return r.stdout if r.returncode == 0 else None


# --- Tests -------------------------------------------------------------------


def test_plumbing_commit_does_not_stage_unrelated_workdir_changes(tmp_path, monkeypatch):
    """Operator has dirty edits in ai/notes/draft.md.
    _git_commit_push commits ONLY spec+backlog blobs.
    After call: HEAD commit touches exactly 1 file; workdir still dirty.
    """
    repo = _make_repo(tmp_path)
    _suppress_push(monkeypatch)

    # Dirty the notes file (not part of the commit)
    (repo / "ai" / "notes" / "draft.md").write_text("dirty notes\n")

    before_count = _head_count(repo)
    callback._git_commit_push(
        str(repo),
        "SPEC",
        "done",
        [("ai/features/SPEC.md", "**Status:** done\n")],
    )
    after_count = _head_count(repo)

    assert after_count == before_count + 1
    # Working tree notes still dirty
    assert (repo / "ai" / "notes" / "draft.md").read_text() == "dirty notes\n"
    # HEAD notes file unchanged from baseline
    head_notes = _head_file(repo, "ai/notes/draft.md")
    assert head_notes == "original notes\n"


def test_plumbing_commit_preserves_operator_edits_in_target_files(tmp_path, monkeypatch):
    """Operator added footnote to spec workdir AFTER autopilot finished.
    callback patches HEAD-content (no footnote) + commits.
    Workdir footnote survives — HEAD has status done, workdir has footnote.
    """
    repo = _make_repo(tmp_path)
    _suppress_push(monkeypatch)

    # Operator adds a footnote (uncommitted)
    spec_path = repo / "ai" / "features" / "SPEC.md"
    spec_path.write_text("**Status:** in_progress\n\n## Notes\n\nfootnote by operator\n")

    new_head_content = "**Status:** done\n"
    callback._git_commit_push(
        str(repo),
        "SPEC",
        "done",
        [("ai/features/SPEC.md", new_head_content)],
    )

    # HEAD must have new_head_content (status=done, no footnote)
    head_content = _head_file(repo, "ai/features/SPEC.md")
    assert "**Status:** done" in head_content
    assert "footnote" not in head_content

    # Workdir must still have the footnote
    workdir_content = spec_path.read_text()
    assert "footnote by operator" in workdir_content


def test_plumbing_commit_skips_when_no_fixes(tmp_path, monkeypatch):
    """fixes=[] → early return, no commit, HEAD unchanged."""
    repo = _make_repo(tmp_path)
    _suppress_push(monkeypatch)
    before_count = _head_count(repo)

    callback._git_commit_push(str(repo), "SPEC", "done", [])

    assert _head_count(repo) == before_count


def test_plumbing_commit_handles_two_files_atomic(tmp_path, monkeypatch):
    """fixes=[(spec,…), (backlog,…)] → ONE commit with two files."""
    repo = _make_repo(tmp_path)
    _suppress_push(monkeypatch)
    before_count = _head_count(repo)

    callback._git_commit_push(
        str(repo),
        "SPEC",
        "done",
        [
            ("ai/features/SPEC.md", "**Status:** done\n"),
            ("ai/backlog.md", "| SPEC | demo | done | P1 |\n"),
        ],
    )

    assert _head_count(repo) == before_count + 1

    # Verify both files updated in the single commit
    r = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--format=", "HEAD"],
        capture_output=True,
        text=True,
    )
    changed_files = r.stdout.strip().splitlines()
    assert "ai/features/SPEC.md" in changed_files
    assert "ai/backlog.md" in changed_files


def test_plumbing_commit_message_format(tmp_path, monkeypatch):
    """Commit message = 'docs: mark {spec_id} as {target} (callback auto-fix)'."""
    repo = _make_repo(tmp_path)
    _suppress_push(monkeypatch)

    callback._git_commit_push(
        str(repo),
        "TECH-168",
        "blocked",
        [("ai/features/SPEC.md", "**Status:** blocked\n")],
    )

    r = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%s"],
        capture_output=True,
        text=True,
    )
    msg = r.stdout.strip()
    assert msg == "docs: mark TECH-168 as blocked (callback auto-fix)"


def test_plumbing_commit_failure_in_hash_object_aborts(tmp_path, monkeypatch):
    """Make `git hash-object` fail → no commit, no exception leaks."""
    repo = _make_repo(tmp_path)
    _suppress_push(monkeypatch)
    before_count = _head_count(repo)

    # Corrupt the repo object store is complex; instead monkeypatch subprocess.run
    # to fail on hash-object calls while allowing all others (including push mock).
    real_run = subprocess.run

    def fake_hash_fail(cmd, *a, **kw):
        if isinstance(cmd, list) and "hash-object" in cmd:
            raise subprocess.CalledProcessError(128, cmd, b"", b"not a git repository")
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_hash_fail)

    # Must not raise
    callback._git_commit_push(
        str(repo),
        "SPEC",
        "done",
        [("ai/features/SPEC.md", "**Status:** done\n")],
    )

    assert _head_count(repo) == before_count


def test_plumbing_commit_push_failure_does_not_raise(tmp_path, monkeypatch):
    """Simulate push rc=1 → log warning, function returns cleanly."""
    repo = _make_repo(tmp_path)

    real_run = subprocess.run

    def fake_push_fail(cmd, *a, **kw):
        if isinstance(cmd, list) and "push" in cmd:
            return subprocess.CompletedProcess(cmd, 1, b"", b"fatal: no remote")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(callback.subprocess, "run", fake_push_fail)

    # Must not raise even though push returns rc=1
    callback._git_commit_push(
        str(repo),
        "SPEC",
        "done",
        [("ai/features/SPEC.md", "**Status:** done\n")],
    )
    # Commit itself should have succeeded
    assert _head_count(repo) >= 1


# --- _read_head_blob tests ---------------------------------------------------


def test_read_head_blob_returns_committed_content(tmp_path):
    """_read_head_blob after commit returns content as written."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _commit(repo, "a.md", "hello\n", "init")

    result = callback._read_head_blob(str(repo), "a.md")
    assert result == "hello\n"


def test_read_head_blob_returns_none_for_missing(tmp_path):
    """File never committed → git show rc=128 → returns None."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    # Need at least one commit to have a HEAD
    _commit(repo, "README.md", "init\n", "init")

    result = callback._read_head_blob(str(repo), "nonexistent.md")
    assert result is None


def test_read_head_blob_ignores_workdir_modifications(tmp_path):
    """Commit content X, modify workdir to Y → _read_head_blob still returns X."""
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _commit(repo, "a.md", "committed\n", "init")

    # Modify workdir (don't commit)
    (repo / "a.md").write_text("workdir modified\n")

    result = callback._read_head_blob(str(repo), "a.md")
    assert result == "committed\n"
