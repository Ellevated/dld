"""TECH-166 — unit tests for callback.py implementation guard.

EC-1..EC-3: _parse_allowed_files parser variants.
EC-4..EC-9: gate_logic.find_implementation_commit gate (replaces deleted
_has_implementation_commits). TECH-210: retargeted from callback._is_done_on_develop
(bool) to gate_logic.find_implementation_commit (str | None, the single source
callback.py now calls) — sha-truthy/None replaces is True/is False.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402
import gate_logic  # noqa: E402


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


# --- gate_logic.find_implementation_commit (Rule 1 gate) ----------------------


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
    """EC-4: commit on origin/develop with spec_id in subject + allowed file → sha."""
    _commit_to(dev_repo, "src/foo.py", "x=1\n", "feat(TECH-XXX): impl")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin", "develop")

    assert (
        gate_logic.find_implementation_commit(str(dev_repo), "TECH-XXX", ["src/foo.py"])
        is not None
    )


def test_ec5_done_on_develop_wrong_file(dev_repo):
    """EC-5: subject matches spec_id but allowed file not touched → None."""
    _commit_to(dev_repo, "docs/note.md", "n\n", "feat(TECH-XXX): note only")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin", "develop")

    assert gate_logic.find_implementation_commit(str(dev_repo), "TECH-XXX", ["src/foo.py"]) is None


def test_ec6_done_on_develop_no_remote(tmp_path):
    """EC-6: no origin/develop exists → graceful None, no exception."""
    repo = tmp_path / "bare"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q", "-b", "develop"], check=True, capture_output=True
    )
    assert gate_logic.find_implementation_commit(str(repo), "TECH-XXX", ["src/foo.py"]) is None


# --- 2026-07-02 false-blocked regression (plpilot BUG-338/339, TECH-349) ------
# Keep in sync with scripts/vps/tests/test_gate_logic.py (L-derived-2).


def test_ec7_trailing_parens_subject(dev_repo):
    """Trailing (SPEC-ID) subject form counts as implementation."""
    _commit_to(dev_repo, "src/foo.py", "x=1\n", "fix: revoke grants on RPCs (BUG-339)")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin", "develop")

    assert (
        gate_logic.find_implementation_commit(str(dev_repo), "BUG-339", ["src/foo.py"])
        is not None
    )


def test_ec8_trailing_parens_free_text_rejected():
    """`(see SPEC-ID)` cross-reference stays rejected (TECH-177 discipline)."""
    assert gate_logic.match_subject("fix: adjust helper (see BUG-339)", "BUG-339") is False
    assert gate_logic.match_subject("fix: revert (BUG-339) partial now", "BUG-339") is False


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

    assert (
        gate_logic.find_implementation_commit(str(dev_repo), "BUG-338", ["src/text.py"])
        is not None
    )


# --- TECH-220: self-block outranks a positive ancestry verdict ---------------

import gate_ancestry  # noqa: E402
import lifecycle  # noqa: E402


def test_tech220_self_block_overrides_ancestry(dev_repo, monkeypatch, tmp_path):
    """EC-7 (devil DA-11): ветка влита, но автопилот сам сказал blocked."""
    spec_id = "TECH-220T"
    _commit_to(
        dev_repo,
        f"ai/features/{spec_id}-2026-08-30-x.md",
        f"# {spec_id}\n\n## Allowed Files\n\n- `src/foo.py`\n",
        f"docs({spec_id}): spec",
    )
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "checkout", "-q", "-b", f"tech/{spec_id}")
    _commit_to(dev_repo, "src/foo.py", "x=1\n", "feat(managed): impl")
    _git(dev_repo, "push", "-q", "-u", "origin", f"tech/{spec_id}")
    _git(dev_repo, "checkout", "-q", "develop")
    _git(dev_repo, "merge", "--ff-only", "-q", f"tech/{spec_id}")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin")
    lifecycle.write_lifecycle(str(dev_repo), spec_id, "in_progress")

    # Ancestry сама по себе положительна
    assert gate_ancestry.find_merged_branch(str(dev_repo), spec_id, ["src/foo.py"]) is not None

    # Also assert gate_via reaches the audit JSONL line — same call, public
    # contract (callback.verify_status_sync), not a private helper.
    audit_path = tmp_path / "tech220-audit.jsonl"
    monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(audit_path))

    callback.verify_status_sync(str(dev_repo), spec_id, target="blocked", autopilot_signaled=True)
    data = lifecycle.read_lifecycle(str(dev_repo), spec_id)
    assert data["status"] == "blocked"
    assert data.get("blocked_reason") == "autopilot_signaled_blocked"

    audit_lines = [json.loads(ln) for ln in audit_path.read_text().splitlines() if ln.strip()]
    audit_row = next(r for r in audit_lines if r["spec_id"] == spec_id)
    assert audit_row["target_out"] == "blocked"
    assert audit_row.get("gate_via") == "ancestry", (
        "self-block overrides status, but the gate's own finding (ancestry) "
        "must still land on the audit line"
    )


# --- TECH-220 EC-12: one (spec, git state) -> one verdict at all 4 sites -----

_VPS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"


def _load_gate_daemon():
    """gate-daemon.py has a hyphen — importlib.util load, mirrors
    scripts/vps/tests/test_gate_daemon.py."""
    spec = importlib.util.spec_from_file_location(
        "gate_daemon_tech220", _VPS_DIR / "gate-daemon.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tech220_ec12_four_call_sites_agree(dev_repo, monkeypatch, tmp_path):
    """EC-12 (devil SA-5, P0): the same (spec, git state) produces the same
    verdict at all four gate call sites. Not asserted by re-deriving the
    verdict independently per site — a spy wraps the ONE
    `gate_ancestry.find_implementation` all four sites import as a module
    attribute and call through to the real (subprocess, no mock) result
    (ADR-013: spies that call through are allowed). Every site observing the
    identical (sha, via) from that single shared call IS the proof they share
    one gate, not four copies of it.
    """
    import callback_dispatch  # noqa: E402 — local: avoid shadowing module-level `callback`
    import callback_sync  # noqa: E402
    import orchestrator_queue  # noqa: E402

    gd = _load_gate_daemon()

    spec_id = "TECH-220E"
    spec_rel = f"ai/features/{spec_id}-2026-08-30-x.md"
    _commit_to(
        dev_repo,
        spec_rel,
        f"# {spec_id}\n\n## Allowed Files\n\n- `src/foo.py`\n",
        f"docs({spec_id}): spec",
    )
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "checkout", "-q", "-b", f"tech/{spec_id}")
    _commit_to(dev_repo, "src/foo.py", "x=1\n", "feat(managed): impl")
    _git(dev_repo, "push", "-q", "-u", "origin", f"tech/{spec_id}")
    _git(dev_repo, "checkout", "-q", "develop")
    _git(dev_repo, "merge", "--ff-only", "-q", f"tech/{spec_id}")
    _git(dev_repo, "push", "-q", "origin", "develop")
    _git(dev_repo, "fetch", "-q", "origin")
    lifecycle.write_lifecycle(str(dev_repo), spec_id, "in_progress")

    allowed = ["src/foo.py"]
    real_find_implementation = gate_ancestry.find_implementation
    calls: list[tuple[str | None, str]] = []

    def _spy(project_path, spec_id_arg, allowed_files):
        result = real_find_implementation(project_path, spec_id_arg, allowed_files)
        calls.append(result)
        return result

    monkeypatch.setattr(gate_ancestry, "find_implementation", _spy)

    shadow_log_path = tmp_path / "gate-daemon-shadow-ec12.jsonl"
    monkeypatch.setenv("GATE_DAEMON_SHADOW_LOG", str(shadow_log_path))
    handler = gd._make_shadow_handler()
    gd._init_shadow_logger(handler)

    # Order matters: gate-daemon reads in_progress/queued specs, so it must
    # run before orchestrator_queue flips this spec to done.
    status_sync, _reason_sync, via_sync = callback_sync._decide_status(
        str(dev_repo), spec_id, "proj", allowed, autopilot_signaled=False
    )
    dispatch_confirmed = callback_dispatch._merge_confirmed(
        str(dev_repo), spec_id, "label", "aborted"
    )
    _ev, _vw, _err = gd._evaluate_project("proj", str(dev_repo), 1, "2026-08-30T00:00:00Z")
    reconciled = orchestrator_queue.reconcile_if_implemented(
        str(dev_repo), spec_id, Path(dev_repo) / spec_rel
    )

    assert status_sync == "done"
    assert dispatch_confirmed is True
    assert reconciled is True

    # All 4 call sites went through the same gate_ancestry.find_implementation.
    assert len(calls) == 4
    shas = {c[0] for c in calls}
    vias = {c[1] for c in calls}
    assert len(shas) == 1 and None not in shas
    assert vias == {"ancestry"}
    assert via_sync == "ancestry"

    shadow_rows = [json.loads(ln) for ln in shadow_log_path.read_text().splitlines() if ln.strip()]
    shadow_row = next(r for r in shadow_rows if r["spec_id"] == spec_id)
    assert shadow_row["gate_via"] == "ancestry"
    assert shadow_row["gate_verdict"] == "done"
