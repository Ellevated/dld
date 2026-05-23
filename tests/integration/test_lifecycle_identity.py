"""ARCH-187 Task 9 — Integration: lifecycle write identity enforcement (ADR-024).

Real fs + real git (no mocks per ADR-013). Verifies the `by=` frozenset gate:

T1: write_lifecycle rejects unknown writer with ValueError naming allowed set
T2: write_lifecycle accepts all 8 _ALLOWED_WRITERS values
T3: create_initial uses by=orchestrator (hardcoded) — accepted
T4: build_initial_yaml rejects unknown writer with ValueError
T5: by= value lands verbatim in transitions[] audit trail (audit-record contract)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import yaml  # noqa: E402

import lifecycle  # noqa: E402


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("")
    _git(repo, "add", "ai/lifecycle/.gitkeep")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


# ---------------------------------------------------------------------------


def test_t1_write_lifecycle_rejects_unknown_writer(tmp_path):
    """T1: unknown by= value triggers ValueError naming the allowed set."""
    repo = _init_repo(tmp_path)
    lifecycle.create_initial(repo, "TECH-901", priority="p1", kind="tech")

    with pytest.raises(ValueError) as exc:
        lifecycle.write_lifecycle(repo, "TECH-901", "blocked", by="hacker")

    msg = str(exc.value)
    assert "invalid by='hacker'" in msg
    # All 8 _ALLOWED_WRITERS members must be named in the error so the
    # caller can see what's expected without reading source.
    for expected in (
        "callback", "orchestrator", "spark", "operator",
        "qa", "audit", "autopilot", "migration",
    ):
        assert expected in msg, f"allowed writer {expected!r} missing from error: {msg}"


def test_t2_write_lifecycle_accepts_all_allowed_writers(tmp_path):
    """T2: every _ALLOWED_WRITERS value is accepted (no spurious gate)."""
    repo = _init_repo(tmp_path)
    lifecycle.create_initial(repo, "TECH-902", priority="p1", kind="tech")

    # Sweep all 8 — each call appends a transition; final state holds the last by.
    for writer in sorted(lifecycle._ALLOWED_WRITERS):
        lifecycle.write_lifecycle(
            repo, "TECH-902", "in_progress", by=writer, reason=None
        )

    final = lifecycle.read_lifecycle(repo, "TECH-902")
    assert final is not None
    assert final["status"] == "in_progress"
    # Transitions array preserves each writer in order
    by_chain = [t.get("by") for t in final["transitions"]]
    # First N entries are the 8 sweep writers (sorted alphabetically by frozenset iter)
    for writer in sorted(lifecycle._ALLOWED_WRITERS):
        assert writer in by_chain, f"writer {writer!r} not recorded in transitions"


def test_t3_create_initial_uses_orchestrator_writer(tmp_path):
    """T3: create_initial hardcodes by=orchestrator — passes gate, records identity."""
    repo = _init_repo(tmp_path)
    lifecycle.create_initial(repo, "TECH-903", priority="p1", kind="tech")

    data = lifecycle.read_lifecycle(repo, "TECH-903")
    assert data is not None
    assert data["status"] == "queued"
    # updated_by field captures the create_initial writer
    assert data.get("updated_by") == "orchestrator"


def test_t4_build_initial_yaml_rejects_unknown_writer():
    """T4: build_initial_yaml (used by migrate) gates on by= too."""
    with pytest.raises(ValueError) as exc:
        lifecycle.build_initial_yaml(
            "TECH-904",
            status="queued",
            priority="p1",
            kind="tech",
            by="hacker",
        )
    assert "invalid by='hacker'" in str(exc.value)
    assert "migration" in str(exc.value)  # default acceptable writer

    # Sanity: default 'migration' works
    out = lifecycle.build_initial_yaml(
        "TECH-904", status="queued", priority="p1", kind="tech"
    )
    parsed = yaml.safe_load(out)
    assert parsed["spec_id"] == "TECH-904"
    assert parsed["updated_by"] == "migration"


def test_t5_by_value_lands_verbatim_in_audit_trail(tmp_path):
    """T5: by= becomes a permanent audit record in transitions[].by — the
    audit-record contract from qa SKILL identity callout."""
    repo = _init_repo(tmp_path)
    lifecycle.create_initial(repo, "TECH-905", priority="p1", kind="tech")

    # operator forces in_progress, callback later writes blocked, qa marks done
    lifecycle.write_lifecycle(
        repo, "TECH-905", "in_progress", by="operator", reason="manual override"
    )
    lifecycle.write_lifecycle(
        repo, "TECH-905", "blocked", by="callback", reason="impl_guard demote"
    )
    lifecycle.write_lifecycle(
        repo, "TECH-905", "done", by="qa", reason="qa accepted"
    )

    data = lifecycle.read_lifecycle(repo, "TECH-905")
    assert data is not None

    # create_initial writes top-level updated_by (no transition appended for
    # the initial state); write_lifecycle appends one entry per call.
    transitions = data["transitions"]
    assert len(transitions) == 3, f"expected 3 transitions, got {len(transitions)}"
    by_chain = [t.get("by") for t in transitions]
    assert by_chain == ["operator", "callback", "qa"], (
        f"audit-trail order mismatch: {by_chain}"
    )
    # updated_by reflects the LAST writer (post-overwrite)
    assert data.get("updated_by") == "qa"
    # blocked_reason field captures the latest non-None reason (qa supplied
    # "qa accepted" most recently)
    assert data.get("blocked_reason") == "qa accepted"
    # Each transition entry holds from/to/at/by/pueue_id — confirm by-tag
    # survives the round-trip through git plumbing + yaml.safe_dump.
    for t in transitions:
        assert t.get("by") in lifecycle._ALLOWED_WRITERS, (
            f"transition recorded unauthorized writer: {t}"
        )
