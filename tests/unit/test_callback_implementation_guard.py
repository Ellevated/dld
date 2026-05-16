"""TECH-166 — unit tests for callback.py implementation guard.

Covers EC-1..EC-7: parser variants, guard window/allowed-list semantics,
degrade-open behavior, and reason annotation via lifecycle.yaml (ARCH-186).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import lifecycle  # noqa: E402


# --- _parse_allowed_files ----------------------------------------------------


def _spec(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "TECH-XXX.md"
    p.write_text(body)
    return p


def test_ec1_parser_typical_spec(tmp_path):
    """EC-1: standard ## Allowed Files with backticked paths → list of paths."""
    spec = _spec(
        tmp_path,
        """\
# TECH-XXX

## Allowed Files

1. `scripts/vps/callback.py` — modify
2. `tests/unit/test_x.py` — NEW
3. `ai/glossary/x.md` — touch
4. `db/schema.sql` — extend
5. `pueue.yml` — config

## Tests
""",
    )
    out = callback._parse_allowed_files(spec)
    assert out == [
        "scripts/vps/callback.py",
        "tests/unit/test_x.py",
        "ai/glossary/x.md",
        "db/schema.sql",
        "pueue.yml",
    ]


def test_ec2_parser_no_allowed_files_section(tmp_path):
    """EC-2: legacy spec without section → None (degrade open sentinel)."""
    spec = _spec(tmp_path, "# Spec\n\n## Tests\n\n- foo\n")
    assert callback._parse_allowed_files(spec) is None


def test_ec3_parser_section_present_but_empty(tmp_path):
    """EC-3: section exists, no backticked paths → [] (explicit empty)."""
    spec = _spec(tmp_path, "# Spec\n\n## Allowed Files\n\nnone\n\n## Tests\n")
    assert callback._parse_allowed_files(spec) == []


# --- _has_implementation_commits ---------------------------------------------


@pytest.fixture
def git_repo(tmp_path):
    """Initialize a tmp git repo with one baseline commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (repo / "README.md").write_text("init\n")
    run("add", "README.md")
    run("commit", "-q", "-m", "init")
    return repo


def _commit(repo: Path, rel: str, content: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", msg],
        check=True,
        capture_output=True,
    )


def _now_iso() -> str:
    # Match git log --since acceptance and task_log default format.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def test_ec4_guard_commit_on_allowed_file(git_repo):
    """EC-4: commit touching allowed file after started_at → True."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(git_repo, "src/foo.py", "x=1\n", "feat: foo")
    assert callback._has_implementation_commits(str(git_repo), ["src/foo.py"], started_at) is True


def test_ec5_guard_only_doc_commits(git_repo):
    """EC-5: commit only on non-allowed path → False (demote)."""
    started_at = _now_iso()
    time.sleep(1.1)
    _commit(git_repo, "docs/x.md", "doc\n", "docs: x")
    assert callback._has_implementation_commits(str(git_repo), ["src/foo.py"], started_at) is False


def test_ec6_guard_commit_before_started_at(git_repo):
    """EC-6: commit predates started_at → window excludes it → False."""
    _commit(git_repo, "src/foo.py", "x=1\n", "feat: foo (early)")
    time.sleep(1.1)
    started_at = _now_iso()
    assert callback._has_implementation_commits(str(git_repo), ["src/foo.py"], started_at) is False


def test_ec7_guard_no_started_at_or_allowed(git_repo):
    """EC-7: missing started_at OR allowed=None → True (degrade open)."""
    assert callback._has_implementation_commits(str(git_repo), ["src/foo.py"], None) is True
    assert callback._has_implementation_commits(str(git_repo), None, _now_iso()) is True


def test_guard_explicit_empty_allowlist_blocks(git_repo):
    """EC-3 follow-through: empty allowed list → False (explicit no-impl)."""
    assert callback._has_implementation_commits(str(git_repo), [], _now_iso()) is False


# --- _append_blocked_reason (ARCH-186: delegates to lifecycle.yaml) ----------


@pytest.fixture()
def lifecycle_git_repo(tmp_path):
    """Minimal git repo with ai/lifecycle/.gitkeep committed — supports lifecycle writes."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(
            ["git"] + list(args), cwd=str(repo), check=True, capture_output=True, text=True
        )

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("")
    git("add", ".")
    git("commit", "-m", "init")
    return repo


def test_append_blocked_reason_writes_lifecycle_yaml(lifecycle_git_repo):
    """NEW signature: _append_blocked_reason(project_path, spec_id, reason, pueue_id)
    writes status=blocked + blocked_reason to lifecycle.yaml via lifecycle module.

    Pre-seed with create_initial so write_lifecycle sees existing=dict and stores reason.
    (When existing=None, lifecycle._build_yaml_content drops reason — design constraint.)
    """
    repo = lifecycle_git_repo
    spec_id = "TECH-TEST-1"
    reason = "no_implementation_commits"

    # create_initial → existing YAML exists → subsequent write stores blocked_reason
    lifecycle.create_initial(str(repo), spec_id, "p1", "tech")
    callback._append_blocked_reason(str(repo), spec_id, reason, pueue_id=None)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None, "lifecycle.yaml must be committed after _append_blocked_reason"
    assert data["status"] == "blocked"
    assert data["blocked_reason"] == reason


def test_append_blocked_reason_idempotent(lifecycle_git_repo):
    """Calling twice with same reason → status=blocked, blocked_reason unchanged."""
    repo = lifecycle_git_repo
    spec_id = "TECH-TEST-2"
    reason = "no_implementation_commits"

    lifecycle.create_initial(str(repo), spec_id, "p1", "tech")
    callback._append_blocked_reason(str(repo), spec_id, reason, pueue_id=None)
    callback._append_blocked_reason(str(repo), spec_id, reason, pueue_id=None)

    data = lifecycle.read_lifecycle(str(repo), spec_id)
    assert data is not None
    assert data["status"] == "blocked"
    assert data["blocked_reason"] == reason
