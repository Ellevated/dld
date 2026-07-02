# scripts/vps/tests/test_gate_logic.py
"""Pure-function tests for gate_logic.py (ARCH-190 Task 5 — Wave 1 MP-001).

Covers all P0 Devil's Advocate cases (DA-series) from the acceptance criteria
plus unit coverage for match_subject, parse_allowed_files_v1/legacy, fetch_develop.

ADR-013: NO mocks. Real git repos via subprocess in tmp_path (mirror test_callback.py).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

from gate_logic import (  # noqa: E402
    _parse_allowed_files_legacy,
    _parse_allowed_files_v1,
    fetch_develop,
    find_implementation_commit,
    match_subject,
    parse_allowed_files,
)

# ---------------------------------------------------------------------------
# Shared git helpers (mirror test_callback.py:34-51)
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
# Fixtures (mirror test_callback.py:67-78)
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path):
    """Bare develop-branch repo with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


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
    (local / "README.md").write_text("init\n")
    _git(local, "add", "README.md")
    _git(local, "commit", "-q", "-m", "init")
    _git(local, "push", "-q", "origin", "develop")
    return local


# ---------------------------------------------------------------------------
# Helper: add a file-touching commit with given subject + body
# ---------------------------------------------------------------------------


def _add_commit(
    repo: Path,
    filename: str,
    subject: str,
    body: str = "",
) -> str:
    """Create a file, stage it, and commit. Returns the commit SHA."""
    fpath = repo / filename
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(f"content for {filename}\n")
    _git(repo, "add", filename)
    msg = subject if not body else f"{subject}\n\n{body}"
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").strip()


def _push_to_remote(repo: Path) -> None:
    """Push develop branch to origin."""
    _git(repo, "push", "-q", "origin", "develop")


# ===========================================================================
# Part 1: match_subject — unit tests (no git)
# ===========================================================================


def test_match_subject_conventional_feat():
    """Conventional Commits form: feat(SPEC-A): description."""
    assert match_subject("feat(SPEC-A): implement the feature", "SPEC-A") is True


def test_match_subject_conventional_fix():
    """Conventional Commits form: fix(SPEC-A)!: description."""
    assert match_subject("fix(SPEC-A)!: critical fix", "SPEC-A") is True


def test_match_subject_merge_form():
    """Merge commit form: merge SPEC-A (spec_id directly after 'merge')."""
    # The regex is ^merge\s+{spec_id}\b — spec_id must come right after 'merge'.
    assert match_subject("Merge SPEC-A", "SPEC-A") is True


def test_match_subject_bare_prefix():
    """Legacy bare prefix form: SPEC-A: description."""
    assert match_subject("SPEC-A: implement the feature", "SPEC-A") is True


def test_match_subject_wrong_spec_id():
    """Negative: feat(BUG-200): work should NOT match TECH-189."""
    assert match_subject("feat(BUG-200): work", "TECH-189") is False


def test_DA4_growth_spec_id_match_subject():
    """DA-4: GROWTH-042 spec_id must be matched by match_subject."""
    assert match_subject("feat(GROWTH-042): add growth metric", "GROWTH-042") is True


# --- 2026-07-02 false-blocked regression (plpilot BUG-338/339, TECH-349) ----


def test_match_subject_trailing_parens_with_scope():
    """Real plpilot BUG-339 subject: domain scope + trailing (SPEC-ID)."""
    assert (
        match_subject(
            "fix(security): REVOKE public execute on 7 SECURITY DEFINER RPCs (BUG-339)",
            "BUG-339",
        )
        is True
    )


def test_match_subject_trailing_parens_no_scope():
    """Real plpilot BUG-338 subject: no scope, trailing (SPEC-ID)."""
    assert (
        match_subject(
            "fix: HTML-aware TG text truncation prevents broken tags (BUG-338)",
            "BUG-338",
        )
        is True
    )


def test_match_subject_trailing_parens_multi_spec():
    """Trailing parens with comma-separated spec ids matches each one."""
    subj = "fix: shared helper hardening (BUG-339, BUG-340)"
    assert match_subject(subj, "BUG-339") is True
    assert match_subject(subj, "BUG-340") is True
    assert match_subject(subj, "BUG-341") is False


def test_match_subject_trailing_parens_free_text_rejected():
    """`(see SPEC-ID)` is a cross-reference, not a declaration → reject."""
    assert match_subject("fix: adjust helper (see BUG-339)", "BUG-339") is False


def test_match_subject_mid_subject_parens_rejected():
    """Parenthesized ID NOT at end of subject stays rejected."""
    assert match_subject("fix: revert (BUG-339) partial change now", "BUG-339") is False


def test_match_subject_merge_colon_form():
    """Real plpilot TECH-349 subject: `merge: feature/SPEC-ID — ...`."""
    assert (
        match_subject(
            "merge: feature/TECH-349 — Edge resilience (CORS fail-fast + timeouts)",
            "TECH-349",
        )
        is True
    )


def test_match_subject_merge_branch_quoted_form():
    """Git default merge subject: Merge branch 'fix/SPEC-ID-slug'."""
    assert (
        match_subject(
            "Merge branch 'fix/BUG-346-one-time-receipt-phantom' into develop",
            "BUG-346",
        )
        is True
    )


def test_match_subject_merge_branch_wrong_spec_rejected():
    """Merge of an UNRELATED branch must not match a different spec."""
    assert (
        match_subject(
            "Merge branch 'fix/BUG-346-one-time-receipt-phantom' into develop",
            "BUG-347",
        )
        is False
    )
    # Spec id boundary: BUG-346 must not match inside BUG-3468.
    assert match_subject("Merge branch 'fix/BUG-3468-x'", "BUG-346") is False


# ===========================================================================
# Part 2: _parse_allowed_files_v1 — unit tests (no git)
# ===========================================================================

_V1_SPEC_HAPPY = """\
## Spec heading

## Allowed Files
<!-- callback-allowlist v1 -->

- `scripts/vps/gate_logic.py` — extract
- `scripts/vps/tests/test_gate_logic.py` — tests

## Next Section
"""

_V1_SPEC_EMPTY_MARKER = """\
## Allowed Files
<!-- callback-allowlist v1 -->

No bullets here.

"""

_V1_SPEC_NO_MARKER = """\
## Allowed Files

- `scripts/vps/gate_logic.py`

"""


def test_parse_allowed_files_v1_happy_path():
    """v1 happy path: marker present + two canonical bullets."""
    result = _parse_allowed_files_v1(_V1_SPEC_HAPPY)
    assert result == [
        "scripts/vps/gate_logic.py",
        "scripts/vps/tests/test_gate_logic.py",
    ]


def test_parse_allowed_files_v1_empty_marker_returns_empty_list():
    """v1 marker present but zero valid bullets → degrade-closed (empty list)."""
    result = _parse_allowed_files_v1(_V1_SPEC_EMPTY_MARKER)
    assert result == []


def test_parse_allowed_files_v1_no_marker_returns_none():
    """v1 heading present but no marker → caller should fall back to legacy."""
    result = _parse_allowed_files_v1(_V1_SPEC_NO_MARKER)
    assert result is None


# ===========================================================================
# Part 3: _parse_allowed_files_legacy — unit tests (no git)
# ===========================================================================

_LEGACY_SPEC_STANDARD_HEADING = """\
## Spec

## Allowed Files

- `scripts/vps/callback.py`
- `scripts/vps/db.py`

## End
"""

_LEGACY_SPEC_UPDATED_HEADING = """\
## Updated Allowed Files

`scripts/vps/orchestrator.py`

"""

_LEGACY_SPEC_NO_SECTION = """\
## Some Section

Nothing relevant here.

"""


def test_parse_allowed_files_legacy_happy_path():
    """Legacy standard heading extracts backticked paths."""
    result = _parse_allowed_files_legacy(_LEGACY_SPEC_STANDARD_HEADING)
    assert result is not None
    assert "scripts/vps/callback.py" in result
    assert "scripts/vps/db.py" in result


def test_parse_allowed_files_legacy_updated_heading():
    """Legacy 'Updated Allowed Files' heading variant is accepted."""
    result = _parse_allowed_files_legacy(_LEGACY_SPEC_UPDATED_HEADING)
    assert result is not None
    assert "scripts/vps/orchestrator.py" in result


def test_parse_allowed_files_legacy_no_section_returns_none():
    """No heading at all → returns None."""
    result = _parse_allowed_files_legacy(_LEGACY_SPEC_NO_SECTION)
    assert result is None


# ===========================================================================
# Part 4: parse_allowed_files (public API, file-based) — unit tests
# ===========================================================================


def test_DA5_spec_without_allowed_files_returns_none(tmp_path):
    """DA-5: spec file without ## Allowed Files section → parse_allowed_files returns None."""
    spec = tmp_path / "SPEC-A.md"
    spec.write_text("# Feature\n\nNo allowed files section.\n")
    assert parse_allowed_files(spec) is None


def test_parse_allowed_files_v1_from_file(tmp_path):
    """parse_allowed_files reads file and returns v1 canonical paths."""
    spec = tmp_path / "SPEC-B.md"
    spec.write_text(_V1_SPEC_HAPPY)
    result = parse_allowed_files(spec)
    assert result == [
        "scripts/vps/gate_logic.py",
        "scripts/vps/tests/test_gate_logic.py",
    ]


def test_parse_allowed_files_missing_file_returns_none(tmp_path):
    """Non-existent spec file → returns None (OSError handled)."""
    result = parse_allowed_files(tmp_path / "nonexistent.md")
    assert result is None


# ===========================================================================
# Part 5: fetch_develop — uses real git repo
# ===========================================================================


def test_fetch_develop_succeeds_with_valid_remote(git_repo_with_remote):
    """fetch_develop returns True when origin/develop is reachable (local bare remote)."""
    result = fetch_develop(str(git_repo_with_remote), timeout=10)
    assert result is True


def test_fetch_develop_timeout_returns_false(git_repo_with_remote):
    """fetch_develop returns False when subprocess times out (TimeoutExpired is SubprocessError).

    timeout=0 forces an immediate SubprocessError.TimeoutExpired which the function
    catches and converts to False.
    """
    result = fetch_develop(str(git_repo_with_remote), timeout=0)
    assert result is False


# ===========================================================================
# Part 6: find_implementation_commit — real git repos
# ===========================================================================


def test_DA6_golden_oracle_commit_on_allowed_file(git_repo_with_remote):
    """DA-6: commit feat(SPEC-A): work touching allowed file → returns sha."""
    repo = git_repo_with_remote
    sha = _add_commit(repo, "scripts/vps/gate_logic.py", "feat(SPEC-A): implement work")
    _push_to_remote(repo)

    result = find_implementation_commit(str(repo), "SPEC-A", ["scripts/vps/gate_logic.py"])
    assert result == sha


def test_DA1_body_mention_not_matched(git_repo_with_remote):
    """DA-1: commit body mentions SPEC-A but subject is for SPEC-B → returns None.

    The commit touches SPEC-A's allowed file BUT its subject only declares SPEC-B.
    Body cross-reference must NOT trigger a match.
    """
    repo = git_repo_with_remote
    _add_commit(
        repo,
        "scripts/vps/gate_logic.py",
        "feat(SPEC-B): implement work",
        body="See also SPEC-A for context",
    )
    _push_to_remote(repo)

    result = find_implementation_commit(str(repo), "SPEC-A", ["scripts/vps/gate_logic.py"])
    assert result is None


def test_DA9_cross_spec_subject_not_matched(git_repo_with_remote):
    """DA-9: commit feat(TECH-189): work, refs ARCH-191 touching ARCH-191's allowed file.

    The commit subject declares TECH-189 but touches ARCH-191's allowed file.
    find_implementation_commit("ARCH-191", ...) must return None — the subject
    only mentions TECH-189.
    """
    repo = git_repo_with_remote
    _add_commit(
        repo,
        "scripts/vps/tests/test_gate_logic.py",
        "feat(TECH-189): work, refs ARCH-191",
    )
    _push_to_remote(repo)

    result = find_implementation_commit(
        str(repo), "ARCH-191", ["scripts/vps/tests/test_gate_logic.py"]
    )
    assert result is None


def test_DA4_growth_spec_id_found_on_develop(git_repo_with_remote):
    """DA-4: GROWTH-042 spec_id found via find_implementation_commit."""
    repo = git_repo_with_remote
    sha = _add_commit(
        repo,
        "scripts/vps/gate-daemon.py",
        "feat(GROWTH-042): add growth metric collector",
    )
    _push_to_remote(repo)

    result = find_implementation_commit(str(repo), "GROWTH-042", ["scripts/vps/gate-daemon.py"])
    assert result == sha


def test_find_implementation_commit_returns_none_when_no_commits(git_repo_with_remote):
    """No matching commits → returns None (initial commit only, unrelated subject)."""
    repo = git_repo_with_remote
    result = find_implementation_commit(str(repo), "TECH-999", ["scripts/vps/gate_logic.py"])
    assert result is None


def test_find_implementation_commit_empty_allowed_files_returns_none(git_repo_with_remote):
    """Conservative fail-closed: empty allowed_files → returns None immediately."""
    result = find_implementation_commit(str(git_repo_with_remote), "SPEC-A", [])
    assert result is None


def test_find_implementation_commit_wrong_file_returns_none(git_repo_with_remote):
    """Commit touches file not in allowed_files → path filter excludes it → None."""
    repo = git_repo_with_remote
    # Commit touches an UNRELATED file
    _add_commit(repo, "scripts/vps/unrelated.py", "feat(SPEC-A): implement work")
    _push_to_remote(repo)

    # Allowed list does NOT include unrelated.py
    result = find_implementation_commit(str(repo), "SPEC-A", ["scripts/vps/gate_logic.py"])
    assert result is None


# --- 2026-07-02 merge-commit visibility regression (plpilot BUG-338) --------


def _merge_feature_branch(
    repo: Path,
    branch: str,
    filename: str,
    feature_subject: str,
    merge_subject: str,
) -> str:
    """Create a feature branch with one commit, no-ff merge it into develop.

    Returns the merge commit SHA.
    """
    _git(repo, "checkout", "-q", "-b", branch)
    _add_commit(repo, filename, feature_subject)
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "--no-ff", "-q", "-m", merge_subject, branch)
    return _git(repo, "rev-parse", "HEAD").strip()


def test_merge_commit_subject_found_via_first_parent(git_repo_with_remote):
    """Regression (plpilot BUG-338): feature commit has NO spec id in subject,
    only the no-ff merge commit declares it (`Merge SPEC-ID: ...`).

    Default path-filtered `git log` simplifies the merge away (TREESAME to the
    feature parent) — the `--first-parent` pass must still find it.
    """
    repo = git_repo_with_remote
    merge_sha = _merge_feature_branch(
        repo,
        "feature/BUG-338",
        "src/text-safety.ts",
        "fix: HTML-aware truncation without spec id anywhere",
        "Merge BUG-338: HTML-aware TG text truncation",
    )
    _push_to_remote(repo)

    result = find_implementation_commit(str(repo), "BUG-338", ["src/text-safety.ts"])
    assert result == merge_sha


def test_merge_branch_default_subject_found(git_repo_with_remote):
    """Regression (plpilot BUG-346): git default `Merge branch 'fix/SPEC-ID-slug'`
    merge subject is found even when the feature commit subject has no scope."""
    repo = git_repo_with_remote
    merge_sha = _merge_feature_branch(
        repo,
        "fix/BUG-346-one-time-receipt-phantom",
        "src/receipt-service.ts",
        "fix: one-time receipt phantom recurring",
        "Merge branch 'fix/BUG-346-one-time-receipt-phantom' into develop",
    )
    _push_to_remote(repo)

    result = find_implementation_commit(str(repo), "BUG-346", ["src/receipt-service.ts"])
    assert result == merge_sha


def test_merge_of_unrelated_spec_not_matched(git_repo_with_remote):
    """Fail-closed: a merge bringing changes into an allowed file but declaring
    a DIFFERENT spec id must not match."""
    repo = git_repo_with_remote
    _merge_feature_branch(
        repo,
        "feature/BUG-777",
        "src/shared.ts",
        "fix: shared change",
        "Merge BUG-777: unrelated work touching shared file",
    )
    _push_to_remote(repo)

    result = find_implementation_commit(str(repo), "BUG-888", ["src/shared.ts"])
    assert result is None
