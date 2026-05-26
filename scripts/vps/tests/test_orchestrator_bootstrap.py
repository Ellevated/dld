"""
TECH-195 — Tests for column-aware backlog parser + safe default=queued.

Covers:
  - Unit: _parse_backlog() for template-format / short-format / no-header /
    unparsable rows.
  - Integration (real-git): bootstrap_new_specs() with awardybot-style backlog
    creates yaml status=queued, NOT done.
  - Regression: bootstrap is idempotent (existing yaml not overwritten).
  - Counter: .bootstrap-unparsable-count increments on unparsable row.

All tests use scripts/vps/tests fixtures (tmp_git_repo mirrors
test_orchestrator_lifecycle.py).
"""

import subprocess
import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import lifecycle  # noqa: E402
import orchestrator  # noqa: E402
from orchestrator import _bump_unparsable_counter, _parse_backlog  # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Unit tests for _parse_backlog (Task 1)
# ──────────────────────────────────────────────────────────────────────


def test_parse_backlog_template_format():
    """| ID | description | status | priority | spec | — status in col 2."""
    text = (
        "| ID | description | status | priority | spec |\n"
        "|---|---|---|---|---|\n"
        "| TECH-100 | Some description | queued | P1 | [spec](x) |\n"
        "| FTR-101 | Other       | in_progress | P0 | [spec](y) |\n"
    )
    result = _parse_backlog(text)
    assert result["TECH-100"] == "queued"
    assert result["FTR-101"] == "in_progress"


def test_parse_backlog_short_format():
    """| ID | status | kind | date | spec | — awardybot/dowry/dld layout."""
    text = (
        "| ID | status | kind | date | spec |\n"
        "|---|---|---|---|---|\n"
        "| TECH-1082 | queued | tech | 2026-05-26 | [spec](x) |\n"
        "| BUG-1074  | queued | bug  | 2026-05-25 | [spec](y) |\n"
    )
    result = _parse_backlog(text)
    assert result["TECH-1082"] == "queued"
    assert result["BUG-1074"] == "queued"


def test_parse_backlog_short_format_status_in_column_2():
    """Variant: | ID | priority | status | spec | — status in col 2 (different header)."""
    text = (
        "| ID | priority | status | spec |\n"
        "|---|---|---|---|\n"
        "| ARCH-50 | P0 | blocked | [spec](x) |\n"
    )
    result = _parse_backlog(text)
    assert result["ARCH-50"] == "blocked"


def test_parse_backlog_case_insensitive_status_column():
    """Header `Status` (capital) and STATUS work too."""
    text = (
        "| ID | Status | Priority |\n"
        "|---|---|---|\n"
        "| TECH-1 | queued | P1 |\n"
    )
    result = _parse_backlog(text)
    assert result["TECH-1"] == "queued"


def test_parse_backlog_no_header_falls_back_to_value_scan():
    """No `|---|---|` divider above → fallback scan all columns for valid status."""
    text = (
        "Some preamble without any markdown table header.\n"
        "| TECH-200 | this row has no header | queued | extra |\n"
    )
    result = _parse_backlog(text)
    # No header → fallback scan finds 'queued' anywhere.
    assert result["TECH-200"] == "queued"


def test_parse_backlog_unparsable_row_returns_none():
    """Row with no valid status anywhere → None (NOT 'done')."""
    text = (
        "| ID | description |\n"
        "|---|---|\n"
        "| FTR-200 | this row is broken — no status anywhere |\n"
    )
    result = _parse_backlog(text)
    assert result["FTR-200"] is None


def test_parse_backlog_invalid_status_value_falls_back():
    """Header has `status` col but value is garbage → fallback scan finds nothing valid."""
    text = (
        "| ID | status | kind |\n"
        "|---|---|---|\n"
        "| TECH-300 | not-a-status | bug |\n"
    )
    result = _parse_backlog(text)
    assert result["TECH-300"] is None


def test_parse_backlog_mixed_ids_growth_prefix():
    """GROWTH-N (added in TECH-189 Task 6) also parses."""
    text = (
        "| ID | status |\n"
        "|---|---|\n"
        "| GROWTH-1 | queued |\n"
        "| TECH-1a  | done |\n"
    )
    result = _parse_backlog(text)
    assert result["GROWTH-1"] == "queued"
    assert result["TECH-1a"] == "done"


def test_parse_backlog_skips_non_spec_rows():
    """Rows without spec_id (e.g. section markers) are not in result."""
    text = (
        "| ID | status |\n"
        "|---|---|\n"
        "| TECH-1 | queued |\n"
        "| some other row | data |\n"
    )
    result = _parse_backlog(text)
    assert "TECH-1" in result
    assert len(result) == 1


def test_parse_backlog_empty_input():
    """Empty input → empty dict, not crash."""
    assert _parse_backlog("") == {}


# ──────────────────────────────────────────────────────────────────────
# Counter helper (Task 1)
# ──────────────────────────────────────────────────────────────────────


def test_bump_unparsable_counter_creates_and_increments(tmp_path):
    """First call creates file with '1', second call increments to '2'."""
    project = tmp_path / "proj"
    (project / "ai").mkdir(parents=True)
    counter = project / "ai" / ".bootstrap-unparsable-count"
    assert not counter.exists()
    _bump_unparsable_counter(str(project))
    assert counter.read_text().strip() == "1"
    _bump_unparsable_counter(str(project))
    assert counter.read_text().strip() == "2"


# ──────────────────────────────────────────────────────────────────────
# Integration (real-git): bootstrap_new_specs end-to-end
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Real git repo for integration tests (mirrors test_orchestrator_lifecycle.py)."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")
    (repo / "ai" / "lifecycle").mkdir(parents=True)
    (repo / "ai" / "lifecycle" / ".gitkeep").write_text("")
    (repo / "ai" / "features").mkdir(parents=True, exist_ok=True)
    git("add", ".")
    git("commit", "-m", "init")
    return repo


def test_bootstrap_short_format_awardybot_style(tmp_git_repo):
    """awardybot/dowry-style backlog → bootstrap creates yaml status=queued (not done)."""
    spec = tmp_git_repo / "ai" / "features" / "TECH-1082-foo.md"
    spec.write_text("# TECH-1082\n**Priority:** P2\n**Kind:** tech\n")
    (tmp_git_repo / "ai" / "backlog.md").write_text(
        "| ID | status | kind | date | spec |\n"
        "|---|---|---|---|---|\n"
        "| TECH-1082 | queued | tech | 2026-05-26 | [spec](x) |\n"
    )
    orchestrator.bootstrap_new_specs(str(tmp_git_repo))
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-1082")
    assert data is not None, "yaml should exist after bootstrap"
    assert data["status"] == "queued", (
        f"S1 regression: expected queued, got {data['status']!r} — "
        "short-format backlog must NOT fall through to 'done'"
    )
    assert data["transitions"] == []
    assert data["pueue_id"] is None


def test_bootstrap_default_queued_not_done(tmp_git_repo):
    """Unparsable row in backlog → bootstrap defaults to queued, NOT done (the bug)."""
    spec = tmp_git_repo / "ai" / "features" / "TECH-999-broken.md"
    spec.write_text("# TECH-999\n**Priority:** P1\n**Kind:** tech\n")
    # Row references spec_id but provides no parseable status anywhere.
    (tmp_git_repo / "ai" / "backlog.md").write_text(
        "| ID | description |\n"
        "|---|---|\n"
        "| TECH-999 | this row has nothing parseable as status |\n"
    )
    orchestrator.bootstrap_new_specs(str(tmp_git_repo))
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-999")
    assert data is not None
    assert data["status"] == "queued", (
        "TECH-195 invariant: unparsable status MUST NOT silently default to 'done' "
        "(that was the bootstrap-as-done bug). Must fail-into-queue."
    )
    # Counter incremented.
    counter = tmp_git_repo / "ai" / ".bootstrap-unparsable-count"
    assert counter.exists(), "counter file should be created on unparsable row"
    assert counter.read_text().strip() == "1"


def test_bootstrap_template_format_still_works(tmp_git_repo):
    """Regression: template-format backlog (| ID | desc | status | ... |) still parses."""
    spec = tmp_git_repo / "ai" / "features" / "TECH-500-bar.md"
    spec.write_text("# TECH-500\n**Priority:** P1\n**Kind:** tech\n")
    (tmp_git_repo / "ai" / "backlog.md").write_text(
        "| ID | description | status | priority | spec |\n"
        "|---|---|---|---|---|\n"
        "| TECH-500 | foo bar | queued | P1 | [spec](x) |\n"
    )
    orchestrator.bootstrap_new_specs(str(tmp_git_repo))
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-500")
    assert data["status"] == "queued"


def test_bootstrap_idempotent_after_refactor(tmp_git_repo):
    """Regression (Task 1): if yaml exists in HEAD, bootstrap does not overwrite."""
    lifecycle.create_initial(tmp_git_repo, "TECH-600", "p0", "tech")
    spec = tmp_git_repo / "ai" / "features" / "TECH-600-x.md"
    spec.write_text("# TECH-600\n**Priority:** P0\n**Kind:** tech\n")
    (tmp_git_repo / "ai" / "backlog.md").write_text(
        "| ID | status |\n|---|---|\n| TECH-600 | done |\n"
    )
    # Bootstrap should be a no-op even though backlog claims `done`.
    orchestrator.bootstrap_new_specs(str(tmp_git_repo))
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-600")
    # create_initial creates status=queued; bootstrap should leave it.
    assert data["status"] == "queued"


def test_bootstrap_skips_orphan_spec_not_in_backlog(tmp_git_repo):
    """spec.md without backlog entry → bootstrap skips it (existing safety preserved)."""
    spec = tmp_git_repo / "ai" / "features" / "TECH-777-orphan.md"
    spec.write_text("# TECH-777\n**Priority:** P1\n**Kind:** tech\n")
    (tmp_git_repo / "ai" / "backlog.md").write_text(
        "| ID | status |\n|---|---|\n| TECH-888 | queued |\n"
    )
    orchestrator.bootstrap_new_specs(str(tmp_git_repo))
    assert lifecycle.read_lifecycle(tmp_git_repo, "TECH-777") is None


# ──────────────────────────────────────────────────────────────────────
# Recovery script (Task 2)
# ──────────────────────────────────────────────────────────────────────

import json as _json  # noqa: E402

from recover_bootstrap_as_done import (  # noqa: E402
    _is_bootstrap_as_done,
    find_bootstrap_as_done,
    run as recover_run,
)


def test_is_bootstrap_as_done_classic_signature():
    """status=done + empty transitions + null pueue_id + null finished_at → True."""
    assert _is_bootstrap_as_done(
        {
            "status": "done",
            "transitions": [],
            "pueue_id": None,
            "finished_at": None,
        }
    )


def test_is_bootstrap_as_done_rejects_legitimate_done():
    """Done with transitions populated → legitimate, NOT bootstrap artifact."""
    assert not _is_bootstrap_as_done(
        {
            "status": "done",
            "transitions": [{"to": "in_progress", "by": "callback", "at": "x"}],
            "pueue_id": 42,
            "finished_at": "2026-05-26T10:00:00Z",
        }
    )


def test_is_bootstrap_as_done_rejects_non_done():
    """Status != done → never a bootstrap-as-done candidate."""
    assert not _is_bootstrap_as_done(
        {"status": "queued", "transitions": [], "pueue_id": None, "finished_at": None}
    )


def test_is_bootstrap_as_done_rejects_dispatched_done():
    """status=done but pueue_id present → ran at least once, not bootstrap artifact."""
    assert not _is_bootstrap_as_done(
        {"status": "done", "transitions": [], "pueue_id": 100, "finished_at": None}
    )


def test_find_bootstrap_as_done_filters_by_signature(tmp_git_repo):
    """Mixed lifecycle: 2 bootstrap-as-done + 1 legit done → returns only the 2."""
    # Bootstrap-as-done (S1 simulation) — create_initial(status="done")
    # produces exactly the 4-criteria signature (no transitions, pueue_id=None,
    # finished_at=None).
    lifecycle.create_initial(tmp_git_repo, "TECH-1082", "p2", "tech", status="done")
    lifecycle.create_initial(tmp_git_repo, "BUG-1074", "p1", "bug", status="done")
    # Legitimate done (with transitions + auto-set finished_at):
    lifecycle.create_initial(tmp_git_repo, "TECH-900", "p1", "tech", status="queued")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-900", "done", pueue_id=42)
    candidates = find_bootstrap_as_done(str(tmp_git_repo))
    assert candidates == ["BUG-1074", "TECH-1082"]


def test_recover_dry_run_makes_no_changes(tmp_git_repo, capsys, tmp_path):
    """--dry-run (default) finds candidates but does not call spec_operator."""
    lifecycle.create_initial(tmp_git_repo, "TECH-1082", "p2", "tech", status="done")

    # Build a minimal projects.json pointing at our tmp_git_repo
    pj = tmp_path / "projects.json"
    pj.write_text(_json.dumps([{"project_id": "tmp", "path": str(tmp_git_repo)}]))

    rc = recover_run(
        dry_run=True,
        project_filter=None,
        projects_json=str(pj),
        json_output=False,
        reason="test",
    )
    assert rc == 0
    # Status unchanged
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-1082")
    assert data["status"] == "done"
    assert data["transitions"] == []
    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
    assert "TECH-1082" in captured.out


def test_recover_confirm_demotes_via_recovery_primitive(tmp_git_repo, tmp_path):
    """--confirm: bootstrap-as-done specs become status=queued with operator transition."""
    lifecycle.create_initial(tmp_git_repo, "TECH-1082", "p2", "tech", status="done")
    lifecycle.create_initial(tmp_git_repo, "BUG-1074", "p1", "bug", status="done")

    pj = tmp_path / "projects.json"
    pj.write_text(_json.dumps([{"project_id": "tmp", "path": str(tmp_git_repo)}]))

    rc = recover_run(
        dry_run=False,
        project_filter=None,
        projects_json=str(pj),
        json_output=False,
        reason="TECH-195 recovery test",
    )
    assert rc == 0
    for spec_id in ("TECH-1082", "BUG-1074"):
        data = lifecycle.read_lifecycle(tmp_git_repo, spec_id)
        assert data["status"] == "queued", f"{spec_id} should be demoted to queued"
        # recover_bootstrap_artifact records a transition with by=operator
        assert any(t.get("by") == "operator" for t in data["transitions"]), (
            f"{spec_id} should have an operator transition"
        )


def test_recover_json_output(tmp_git_repo, capsys, tmp_path):
    """--json emits valid JSON structure with project list."""
    lifecycle.create_initial(tmp_git_repo, "TECH-1082", "p2", "tech", status="done")
    pj = tmp_path / "projects.json"
    pj.write_text(_json.dumps([{"project_id": "tmp", "path": str(tmp_git_repo)}]))

    rc = recover_run(
        dry_run=True,
        project_filter=None,
        projects_json=str(pj),
        json_output=True,
        reason="test",
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = _json.loads(out)
    assert payload["dry_run"] is True
    assert len(payload["projects"]) == 1
    proj = payload["projects"][0]
    assert proj["project_id"] == "tmp"
    assert proj["candidates"] == ["TECH-1082"]
    assert proj["count"] == 1


def test_recover_does_not_touch_legitimate_done(tmp_git_repo, tmp_path):
    """A done spec with transitions+pueue_id is NEVER demoted by recovery."""
    lifecycle.create_initial(tmp_git_repo, "TECH-900", "p1", "tech", status="queued")
    # write_lifecycle("done") auto-sets finished_at and adds a transition,
    # so this is a legitimate done.
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-900", "done", pueue_id=42)
    pj = tmp_path / "projects.json"
    pj.write_text(_json.dumps([{"project_id": "tmp", "path": str(tmp_git_repo)}]))

    recover_run(
        dry_run=False,
        project_filter=None,
        projects_json=str(pj),
        json_output=False,
        reason="test",
    )
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-900")
    assert data["status"] == "done", "legitimate done MUST remain done"


def test_recover_bootstrap_artifact_refuses_legitimate_done(tmp_git_repo):
    """Direct primitive call: legit done raises NotBootstrapArtifactError (Rule 7 honored)."""
    lifecycle.create_initial(tmp_git_repo, "TECH-901", "p1", "tech", status="queued")
    lifecycle.write_lifecycle(tmp_git_repo, "TECH-901", "done", pueue_id=42)
    import pytest

    with pytest.raises(lifecycle.NotBootstrapArtifactError):
        lifecycle.recover_bootstrap_artifact(
            tmp_git_repo, "TECH-901", reason="test", by="operator"
        )


def test_recover_bootstrap_artifact_demotes_bootstrap_signature(tmp_git_repo):
    """Direct primitive call: bootstrap-as-done → demoted to queued with transition."""
    lifecycle.create_initial(tmp_git_repo, "TECH-1082", "p2", "tech", status="done")
    lifecycle.recover_bootstrap_artifact(
        tmp_git_repo, "TECH-1082", reason="TECH-195 test", by="operator"
    )
    data = lifecycle.read_lifecycle(tmp_git_repo, "TECH-1082")
    assert data["status"] == "queued"
    assert any(
        t.get("by") == "operator" and t.get("to") == "queued"
        for t in data.get("transitions", [])
    )
