"""TECH-166 — unit tests for callback.py implementation guard.

EC-1..EC-3: _parse_allowed_files parser variants.
EC-4..EC-6: _is_done_on_develop gate (replaces deleted _has_implementation_commits).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402


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


# --- _is_done_on_develop (Rule 1 gate) ----------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _commit_to(repo: Path, rel: str, content: str, msg: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)


@pytest.fixture
def dev_repo(tmp_path):
    """Local repo with bare remote; origin/develop tracking ref ready."""
    bare = tmp_path / "remote.git"
    bare.mkdir()
    subprocess.run(
        ["git", "init", "--bare", "-q", "-b", "develop", str(bare)],
        check=True,
        capture_output=True,
    )
    local = tmp_path / "local"
    local.mkdir()
    _git(local, "init", "-q", "-b", "develop")
    _git(local, "config", "user.email", "t@t")
    _git(local, "config", "user.name", "t")
    _git(local, "remote", "add", "origin", str(bare))
    (local / "README.md").write_text("init\n")
    _git(local, "add", "README.md")
    _git(local, "commit", "-q", "-m", "init")
    _git(local, "push", "-q", "-u", "origin", "develop")
    return local


def test_ec4_done_on_develop_true(dev_repo):
    """EC-4: commit on origin/develop with spec_id in subject + allowed file → True."""
    _commit_to(dev_repo, "src/foo.py", "x=1\n", "feat(TECH-XXX): impl")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin", "develop")

    assert callback._is_done_on_develop(str(dev_repo), "TECH-XXX", ["src/foo.py"]) is True


def test_ec5_done_on_develop_wrong_file(dev_repo):
    """EC-5: subject matches spec_id but allowed file not touched → False."""
    _commit_to(dev_repo, "docs/note.md", "n\n", "feat(TECH-XXX): note only")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin", "develop")

    assert callback._is_done_on_develop(str(dev_repo), "TECH-XXX", ["src/foo.py"]) is False


def test_ec6_done_on_develop_no_remote(tmp_path):
    """EC-6: no origin/develop exists → graceful False, no exception."""
    repo = tmp_path / "bare"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "develop"], check=True, capture_output=True
    )
    assert callback._is_done_on_develop(str(repo), "TECH-XXX", ["src/foo.py"]) is False


# --- 2026-07-02 false-blocked regression (plpilot BUG-338/339, TECH-349) ------
# Keep in sync with scripts/vps/tests/test_gate_logic.py (L-derived-2).


def test_ec7_trailing_parens_subject(dev_repo):
    """Trailing (SPEC-ID) subject form counts as implementation."""
    _commit_to(dev_repo, "src/foo.py", "x=1\n", "fix: revoke grants on RPCs (BUG-339)")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin", "develop")

    assert callback._is_done_on_develop(str(dev_repo), "BUG-339", ["src/foo.py"]) is True


def test_ec8_trailing_parens_free_text_rejected():
    """`(see SPEC-ID)` cross-reference stays rejected (TECH-177 discipline)."""
    assert callback._subject_implements("fix: adjust helper (see BUG-339)", "BUG-339") is False
    assert callback._subject_implements("fix: revert (BUG-339) partial now", "BUG-339") is False


def test_ec9_merge_commit_found_via_first_parent(dev_repo):
    """No-ff merge commit `Merge SPEC-ID: ...` is found even though the
    path-filtered default log simplifies it away (plpilot BUG-338)."""
    _git(dev_repo, "checkout", "-q", "-b", "feature/BUG-338")
    _commit_to(dev_repo, "src/text.py", "y=1\n", "fix: truncation without spec id")
    _git(dev_repo, "checkout", "-q", "develop")
    _git(
        dev_repo,
        "merge",
        "--no-ff",
        "-q",
        "-m",
        "Merge BUG-338: HTML-aware TG text truncation",
        "feature/BUG-338",
    )
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin", "develop")

    assert callback._is_done_on_develop(str(dev_repo), "BUG-338", ["src/text.py"]) is True
