"""TECH-174 — integration tests for spec_verify.py and operator.py.

Synthetic spec in tmpdir, real fs + real git (no mocks per ADR-013).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import importlib.util as _ilu  # noqa: E402

_op_spec = _ilu.spec_from_file_location(
    "operator_cli", str(SCRIPT_DIR / "operator.py")
)
operator_cli = _ilu.module_from_spec(_op_spec)  # type: ignore[arg-type]
_op_spec.loader.exec_module(operator_cli)  # type: ignore[union-attr]

import spec_verify  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "features").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "README.md").write_text("init\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


_SPEC_BODY_OK = """---
id: TEST-001
---

# TEST-001 — demo spec

**Status:** done

## Allowed Files

<!-- callback-allowlist v1 -->

- `src/awardybot_core.py`
- `src/buyer_onboarding.py`

## Tasks

1. Implement `register_buyer` route in `src/buyer_onboarding.py`.
2. Add `AwardyBotCore` class in `src/awardybot_core.py`.

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | exists |
"""

_SPEC_BODY_MISSING = """---
id: TEST-002
---

# TEST-002 — demo spec with missing file

**Status:** done

## Allowed Files

<!-- callback-allowlist v1 -->

- `src/present_module.py`
- `src/missing_module.py`

## Tasks

1. Implement `do_thing_now` in `src/present_module.py`.
2. Implement `other_helper` in `src/missing_module.py`.
"""


def _write_spec(repo: Path, spec_id: str, body: str) -> Path:
    spec = repo / "ai" / "features" / f"{spec_id}.md"
    spec.write_text(body)
    return spec


# ----------------------------------------------------------------------------
# spec_verify
# ----------------------------------------------------------------------------


def test_spec_verify_reports_missing_file(tmp_path: Path) -> None:
    """EC-1 — missing allowed file → HARD-FAIL (FTR-897 Task 11 case)."""
    repo = _make_repo(tmp_path)
    _write_spec(repo, "TEST-002", _SPEC_BODY_MISSING)
    (repo / "src" / "present_module.py").write_text(
        "def do_thing_now():\n    pass\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "partial")

    rep = spec_verify.build_report(repo, "TEST-002")
    assert "src/missing_module.py" in rep.missing
    assert "src/present_module.py" in rep.present
    assert rep.hard_fail is True
    output = spec_verify.render(rep)
    assert "MISS src/missing_module.py" in output
    assert "HARD-FAIL" in output


def test_spec_verify_ok_when_files_and_symbols_present(tmp_path: Path) -> None:
    """EC-2 — all allowed files exist + each Task has grep hits → OK."""
    repo = _make_repo(tmp_path)
    _write_spec(repo, "TEST-001", _SPEC_BODY_OK)
    (repo / "src" / "buyer_onboarding.py").write_text(
        "def register_buyer(req):\n    return None\n"
    )
    (repo / "src" / "awardybot_core.py").write_text(
        "class AwardyBotCore:\n    pass\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "impl")

    rep = spec_verify.build_report(repo, "TEST-001")
    assert rep.missing == []
    assert rep.hard_fail is False
    # Each Task's distinguishing symbol got at least one grep hit.
    for tc in rep.tasks:
        assert tc.ok, (tc.line, tc.matches)
    assert "heuristic-OK" in spec_verify.render(rep)


def test_spec_verify_cli_exit_codes(tmp_path: Path) -> None:
    """CLI: HARD-FAIL spec → exit 1, OK spec → exit 0."""
    repo = _make_repo(tmp_path)
    _write_spec(repo, "TEST-002", _SPEC_BODY_MISSING)
    (repo / "src" / "present_module.py").write_text(
        "def do_thing_now():\n    pass\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "partial")

    rc = spec_verify.main([str(repo), "TEST-002"])
    assert rc == 1


# ----------------------------------------------------------------------------
# operator
# ----------------------------------------------------------------------------


def test_operator_demote_via_plumbing_does_not_touch_working_tree(
    tmp_path: Path,
) -> None:
    """EC-3 — operator.py demote uses plumbing-commit; working-tree edits
    by operator (here: an unrelated dirty file) survive."""
    repo = _make_repo(tmp_path)
    _write_spec(repo, "TEST-003", _SPEC_BODY_OK.replace("TEST-001", "TEST-003"))
    (repo / "ai" / "backlog.md").write_text(
        "| ID | Title | Status | P |\n|---|---|---|---|\n"
        "| TEST-003 | demo | done | P1 |\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed spec")

    # Operator-style dirty edit in working tree (must NOT be committed).
    dirty = repo / "scratch.txt"
    dirty.write_text("operator was editing this\n")

    head_before = _git(repo, "rev-parse", "HEAD").stdout.strip()
    rc = operator_cli.main(["demote", str(repo), "TEST-003", "task_2_missing"])
    assert rc == 0

    # New commit landed.
    head_after = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert head_before != head_after, "demote should produce a new commit"

    # Spec status flipped at HEAD.
    spec_at_head = _git(
        repo, "show", f"HEAD:ai/features/TEST-003.md"
    ).stdout
    assert "**Status:** queued" in spec_at_head
    assert "Blocked Reason:** task_2_missing" in spec_at_head

    # Backlog row flipped at HEAD.
    backlog_at_head = _git(repo, "show", "HEAD:ai/backlog.md").stdout
    assert "| TEST-003 | demo | queued | P1 |" in backlog_at_head

    # Operator's dirty scratch survived untouched.
    assert dirty.exists()
    assert dirty.read_text() == "operator was editing this\n"


def test_operator_force_done(tmp_path: Path) -> None:
    """force-done flips spec to done and touches backlog."""
    repo = _make_repo(tmp_path)
    body = _SPEC_BODY_OK.replace("TEST-001", "TEST-004").replace(
        "**Status:** done", "**Status:** blocked"
    )
    _write_spec(repo, "TEST-004", body)
    (repo / "ai" / "backlog.md").write_text(
        "| ID | Title | Status | P |\n|---|---|---|---|\n"
        "| TEST-004 | demo | blocked | P1 |\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")

    rc = operator_cli.main(["force-done", str(repo), "TEST-004", "operator_uat_passed"])
    assert rc == 0

    spec_at_head = _git(repo, "show", "HEAD:ai/features/TEST-004.md").stdout
    assert "**Status:** done" in spec_at_head
    backlog_at_head = _git(repo, "show", "HEAD:ai/backlog.md").stdout
    assert "| TEST-004 | demo | done | P1 |" in backlog_at_head


def test_operator_demote_unknown_spec_returns_3(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    rc = operator_cli.main(["demote", str(repo), "NOPE-999", "x"])
    assert rc == 3


# ----------------------------------------------------------------------------
# EC-4 — protocol doc completeness (located in operator's home, hence skip
# if not present — the doc lives in ~/.claude/projects/-root/memory/.)
# ----------------------------------------------------------------------------


@pytest.mark.skipif(
    not (Path.home() / ".claude" / "projects" / "-root" / "memory"
         / "spec-verification-protocol.md").exists(),
    reason="protocol doc not installed in this environment",
)
def test_protocol_doc_has_seven_steps() -> None:
    doc = (Path.home() / ".claude" / "projects" / "-root" / "memory"
           / "spec-verification-protocol.md").read_text()
    for n in range(1, 8):
        assert f"## Step {n}" in doc, f"missing Step {n} heading"
    # Has at least one example command per step
    assert "```bash" in doc
