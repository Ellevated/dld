# scripts/vps/tests/test_gate_ancestry.py
"""Ancestry-gate tests for gate_ancestry.py (TECH-220).

Standalone file — scripts/vps/tests/test_gate_logic.py is out of the Allowed
Files list for this spec, so the git fixtures it uses (`_git`,
`git_repo_with_remote`, `_add_commit`, `_push_to_remote`) are copied here
verbatim rather than imported (test_gate_logic.py:35-125).

ADR-013: NO mocks. Real git repos via subprocess in tmp_path.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

# ---------------------------------------------------------------------------
# Shared git helpers (copied from test_gate_logic.py:35-125 — see module
# docstring for why this is a copy, not an import)
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


@pytest.fixture
def git_repo_with_remote(tmp_path):
    """Local repo + bare remote so origin/develop is resolvable.

    Structure:
        remote/    — bare clone (acts as origin)
        local/     — working copy with origin pointing at remote/
    """
    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    local.mkdir()

    # Initialise remote as bare
    subprocess.run(
        ["git", "init", "--bare", "-q", "-b", "develop", str(remote)],
        check=True,
    )
    # Initialise local
    _git(local, "init", "-q", "-b", "develop")
    _git(local, "config", "user.email", "t@t")
    _git(local, "config", "user.name", "t")
    _git(local, "remote", "add", "origin", str(remote))
    # First commit + push so origin/develop exists
    (local / "README.md").write_text("init\n", encoding="utf-8")
    _git(local, "add", "README.md")
    _git(local, "commit", "-q", "-m", "init")
    _git(local, "push", "-q", "origin", "develop")
    return local


def _add_commit(
    repo: Path,
    filename: str,
    subject: str,
    body: str = "",
) -> str:
    """Create a file, stage it, and commit. Returns the commit SHA."""
    fpath = repo / filename
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(f"content for {filename}\n", encoding="utf-8")
    _git(repo, "add", filename)
    msg = subject if not body else f"{subject}\n\n{body}"
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").strip()


def _push_to_remote(repo: Path) -> None:
    """Push develop branch to origin."""
    _git(repo, "push", "-q", "origin", "develop")


# --- TECH-220: ancestry gate ------------------------------------------------

from gate_ancestry import (  # noqa: E402
    branch_ref_for,
    fetch_branch,
    find_implementation,
    find_merged_branch,
)


def _spec_birth(repo: Path, spec_id: str) -> None:
    """Spark-коммит спеки на develop — он же нижняя граница ff-диффа."""
    _add_commit(repo, f"ai/features/{spec_id}-2026-08-30-x.md", f"docs({spec_id}): spec")


def _ff_merge_branch(repo: Path, branch: str, files: list[str], subject: str) -> str:
    """Ветка от develop, коммит, ff-only merge, push ветки И develop."""
    _git(repo, "checkout", "-q", "-b", branch)
    for f in files:
        _add_commit(repo, f, subject)
    _git(repo, "push", "-q", "-u", "origin", branch)
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "--ff-only", "-q", branch)
    _git(repo, "push", "-q", "origin", "develop")
    _git(repo, "fetch", "-q", "origin")
    return _git(repo, "rev-parse", branch).strip()


class TestAncestryGate:
    def test_ec1_merged_branch_touching_allowed_file(self, git_repo_with_remote):
        """EC-1: ветка влита ff-only, subject гейту непонятен → ancestry."""
        repo = git_repo_with_remote
        _spec_birth(repo, "BUG-9")
        _push_to_remote(repo)
        tip = _ff_merge_branch(repo, "fix/BUG-9", ["src/x.py"], "feat(managed): x")

        assert find_merged_branch(str(repo), "BUG-9", ["src/x.py"]) == tip
        assert find_implementation(str(repo), "BUG-9", ["src/x.py"]) == (tip, "ancestry")

    def test_ec2_bookkeeping_only_branch_is_not_evidence(self, git_repo_with_remote):
        """EC-2: ветка из одних ai/-коммитов влита → не done (devil DA-1, ADR-025)."""
        repo = git_repo_with_remote
        _spec_birth(repo, "BUG-10")
        _push_to_remote(repo)
        _ff_merge_branch(repo, "fix/BUG-10", ["ai/diary/2026-08-30.md"], "docs(BUG-10): diary")

        assert find_merged_branch(str(repo), "BUG-10", ["src/x.py", "ai/diary/x.md"]) is None
        assert find_implementation(str(repo), "BUG-10", ["src/x.py"]) == (None, "none")

    def test_ec3_branch_prefix_map(self):
        """EC-3: карта префиксов, включая GROWTH; неизвестный тип → ValueError."""
        assert branch_ref_for("FTR-9") == "feature/FTR-9"
        assert branch_ref_for("BUG-9") == "fix/BUG-9"
        assert branch_ref_for("TECH-9") == "tech/TECH-9"
        assert branch_ref_for("ARCH-9") == "arch/ARCH-9"
        assert branch_ref_for("GROWTH-9") == "growth/GROWTH-9"
        with pytest.raises(ValueError):
            branch_ref_for("XXX-9")

    def test_ec4_pushed_but_not_merged_falls_back(self, git_repo_with_remote):
        """EC-4: ветка на origin, но не предок develop → ancestry None, subject решает."""
        repo = git_repo_with_remote
        _spec_birth(repo, "BUG-11")
        _push_to_remote(repo)
        _git(repo, "checkout", "-q", "-b", "fix/BUG-11")
        _add_commit(repo, "src/y.py", "feat(managed): y")
        _git(repo, "push", "-q", "-u", "origin", "fix/BUG-11")
        _git(repo, "checkout", "-q", "develop")
        _git(repo, "fetch", "-q", "origin")

        assert find_merged_branch(str(repo), "BUG-11", ["src/y.py"]) is None
        assert find_implementation(str(repo), "BUG-11", ["src/y.py"]) == (None, "none")

    def test_ec5_squash_merge_falls_back_to_subject(self, git_repo_with_remote):
        """EC-5: ветки нет, но subject несёт id → ("<sha>", "subject")."""
        repo = git_repo_with_remote
        sha = _add_commit(repo, "src/z.py", "feat(FTR-9): squashed work")
        _push_to_remote(repo)
        _git(repo, "fetch", "-q", "origin")

        assert find_implementation(str(repo), "FTR-9", ["src/z.py"]) == (sha, "subject")

    def test_ec6_subspec_suffix_never_cross_matches(self, git_repo_with_remote):
        """EC-6: arch/ARCH-176a влита — ARCH-176 не должна засчитаться (devil DA-8)."""
        repo = git_repo_with_remote
        _spec_birth(repo, "ARCH-176a")
        _push_to_remote(repo)
        _ff_merge_branch(repo, "arch/ARCH-176a", ["src/sub.py"], "feat(managed): sub")

        assert branch_ref_for("ARCH-176a") == "arch/ARCH-176a"
        assert find_merged_branch(str(repo), "ARCH-176", ["src/sub.py"]) is None

    def test_ec8_git_failure_is_fail_closed(self, tmp_path):
        """EC-8: не-репозиторий → (None, "none"), исключение не выходит наружу."""
        broken = tmp_path / "notarepo"
        broken.mkdir()
        assert find_merged_branch(str(broken), "TECH-9", ["src/x.py"]) is None
        assert find_implementation(str(broken), "TECH-9", ["src/x.py"]) == (None, "none")
        assert fetch_branch(str(broken), "TECH-9") is False
