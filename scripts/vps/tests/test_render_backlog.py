"""
Unit tests for scripts/vps/render_backlog.py.

Uses real filesystem + git (no mocks — ADR-013).
Shares tmp_git_repo fixture pattern from test_lifecycle.py.
"""

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

# Make scripts/vps importable
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

import render_backlog  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_git_repo(tmp_path):
    """Minimal git repo with initial commit, ai/lifecycle/ and ai/features/ dirs."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test User")

    lc_dir = repo / "ai" / "lifecycle"
    lc_dir.mkdir(parents=True)
    (lc_dir / ".gitkeep").write_text("", encoding="utf-8")

    feat_dir = repo / "ai" / "features"
    feat_dir.mkdir(parents=True)
    (feat_dir / ".gitkeep").write_text("", encoding="utf-8")

    git("add", ".")
    git("commit", "-m", "init")

    return repo


def _write_yaml_and_commit(repo: Path, spec_id: str, data: dict) -> None:
    """Write lifecycle yaml to working tree and commit it."""
    path = repo / "ai" / "lifecycle" / f"{spec_id}.yaml"
    path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")

    def git(*args):
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    git("add", str(path))
    git("commit", "-m", f"lifecycle({spec_id}): test")


# ---------------------------------------------------------------------------
# Test 1: render_matches_format
# ---------------------------------------------------------------------------


def test_render_matches_format(tmp_git_repo):
    """Write 3 lifecycle YAMLs (p0/p1/p2 with mixed statuses), render, assert structure."""
    repo = tmp_git_repo

    p0_data = {
        "spec_id": "TECH-100",
        "status": "in_progress",
        "priority": "p0",
        "kind": "tech",
        "updated_at": "2026-05-16T10:00:00Z",
        "finished_at": None,
        "blocked_reason": None,
    }
    p1_data = {
        "spec_id": "FTR-200",
        "status": "queued",
        "priority": "p1",
        "kind": "ftr",
        "updated_at": "2026-05-15T08:00:00Z",
        "finished_at": None,
        "blocked_reason": None,
    }
    p2_data = {
        "spec_id": "BUG-300",
        "status": "blocked",
        "priority": "p2",
        "kind": "bug",
        "updated_at": "2026-05-14T12:00:00Z",
        "finished_at": None,
        "blocked_reason": "needs human",
    }

    _write_yaml_and_commit(repo, "TECH-100", p0_data)
    _write_yaml_and_commit(repo, "FTR-200", p1_data)
    _write_yaml_and_commit(repo, "BUG-300", p2_data)

    result = render_backlog.render_backlog(repo)

    # Basic structure
    assert "# DLD Backlog" in result
    assert "AUTO-GENERATED" in result
    assert "do not edit manually" in result

    # All 3 spec IDs appear
    assert "TECH-100" in result
    assert "FTR-200" in result
    assert "BUG-300" in result

    # P0 section appears before P1 section
    p0_pos = result.index("P0 —")
    p1_pos = result.index("P1 —")
    p2_pos = result.index("P2 —")
    assert p0_pos < p1_pos < p2_pos

    # Done section present
    assert "Done (last 30 days)" in result


# ---------------------------------------------------------------------------
# Test 2: render_skips_corrupt_yaml
# ---------------------------------------------------------------------------


def test_render_skips_corrupt_yaml(tmp_git_repo, caplog):
    """Write 2 valid + 1 corrupt yaml — valid specs appear, corrupt is skipped with warning."""
    import logging

    repo = tmp_git_repo

    valid1 = {
        "spec_id": "TECH-10",
        "status": "queued",
        "priority": "p1",
        "kind": "tech",
        "updated_at": "2026-05-16T09:00:00Z",
        "finished_at": None,
        "blocked_reason": None,
    }
    valid2 = {
        "spec_id": "FTR-20",
        "status": "queued",
        "priority": "p1",
        "kind": "ftr",
        "updated_at": "2026-05-16T09:30:00Z",
        "finished_at": None,
        "blocked_reason": None,
    }

    _write_yaml_and_commit(repo, "TECH-10", valid1)
    _write_yaml_and_commit(repo, "FTR-20", valid2)

    # Write corrupt yaml and commit it directly
    corrupt_path = repo / "ai" / "lifecycle" / "ARCH-99.yaml"
    corrupt_path.write_text("not: valid: yaml: content: :\n  - broken: [unclosed", encoding="utf-8")

    def git(*args):
        r = subprocess.run(
            ["git"] + list(args),
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"git {args} failed: {r.stderr.strip()}")

    git("add", str(corrupt_path))
    git("commit", "-m", "lifecycle(ARCH-99): corrupt test")

    with caplog.at_level(logging.WARNING, logger="render_backlog"):
        result = render_backlog.render_backlog(repo)

    # Valid specs present
    assert "TECH-10" in result
    assert "FTR-20" in result

    # Corrupt spec absent
    assert "ARCH-99" not in result

    # Warning was logged
    assert any("ARCH-99" in msg or "skipping" in msg.lower() for msg in caplog.messages)


# ---------------------------------------------------------------------------
# Test 3: render_round_trip
# ---------------------------------------------------------------------------


def test_render_round_trip(tmp_git_repo):
    """Write yamls, render, parse rendered markdown, assert status set matches."""
    repo = tmp_git_repo

    # Use a recent finished_at so the done spec lands in "Done (last 30 days)"
    # rather than the collapsed "Older than 30 days" bucket. Computed relative
    # to now so the round-trip assertion can never age out (was a date-bomb:
    # hardcoded 2026-05-16 silently dropped BUG-3 once 30 days elapsed).
    recent = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    specs = [
        {
            "spec_id": "TECH-1",
            "status": "queued",
            "priority": "p1",
            "kind": "tech",
            "updated_at": "2026-05-16T10:00:00Z",
            "finished_at": None,
            "blocked_reason": None,
        },
        {
            "spec_id": "FTR-2",
            "status": "in_progress",
            "priority": "p0",
            "kind": "ftr",
            "updated_at": "2026-05-16T11:00:00Z",
            "finished_at": None,
            "blocked_reason": None,
        },
        {
            "spec_id": "BUG-3",
            "status": "done",
            "priority": "p1",
            "kind": "bug",
            "updated_at": recent,
            "finished_at": recent,
            "blocked_reason": None,
        },
    ]

    for s in specs:
        _write_yaml_and_commit(repo, s["spec_id"], s)

    rendered = render_backlog.render_backlog(repo)

    # Parse spec IDs from rendered markdown by scanning table rows
    found_ids = set()
    for line in rendered.splitlines():
        if line.startswith("| ") and not line.startswith("| ID ") and not line.startswith("|-"):
            parts = [p.strip() for p in line.split("|")]
            # parts[0] is empty, parts[1] is ID-or-text
            candidate = parts[1] if len(parts) > 1 else ""
            # Match known spec_id format: WORD-DIGITS
            if candidate and "-" in candidate and not candidate.startswith("Older"):
                found_ids.add(candidate)

    expected_ids = {s["spec_id"] for s in specs}
    assert expected_ids == found_ids, f"Mismatch: expected {expected_ids}, found {found_ids}"


# ---------------------------------------------------------------------------
# sync_status — status-only in-place update (preserves founder content)
# ---------------------------------------------------------------------------


def test_sync_status_updates_only_status_preserving_content(tmp_git_repo):
    repo = tmp_git_repo
    _write_yaml_and_commit(repo, "TECH-1", {"spec_id": "TECH-1", "status": "done", "kind": "tech"})
    _write_yaml_and_commit(repo, "FTR-2", {"spec_id": "FTR-2", "status": "blocked", "kind": "ftr"})

    backlog = (
        "# DLD Backlog\n\n## P1\n\n"
        "| ID | Status | Kind | Updated | Spec |\n|----|--------|------|---------|------|\n"
        "| TECH-1 | queued | tech | 2026-06-20 | [spec](features/x.md) — rich — desc ⛔ AFTER FTR-2 |\n"
        "| FTR-2 | queued | ftr | 2026-06-20 | [spec](features/y.md) — keep me |\n"
    )
    out = render_backlog.sync_status(repo, backlog)
    assert (
        "| TECH-1 | done | tech | 2026-06-20 | [spec](features/x.md) — rich — desc ⛔ AFTER FTR-2 |"
        in out
    )
    assert "| FTR-2 | blocked | ftr | 2026-06-20 | [spec](features/y.md) — keep me |" in out
    # rich description + AFTER marker survive exactly once
    assert out.count("⛔ AFTER FTR-2") == 1


def test_sync_status_leaves_unknown_specs_and_prose_untouched(tmp_git_repo):
    repo = tmp_git_repo
    _write_yaml_and_commit(repo, "TECH-1", {"spec_id": "TECH-1", "status": "done", "kind": "tech"})
    backlog = (
        "| ID | Status | Kind | Updated | Spec |\n|----|--------|------|---------|------|\n"
        "| TECH-1 | queued | tech | 2026-06-20 | x |\n"
        "| NOPE-9 | queued | bug | 2026-06-20 | not in lifecycle |\n"
        "\nProse — untouched | with a pipe |\n"
    )
    out = render_backlog.sync_status(repo, backlog)
    assert "| TECH-1 | done |" in out
    assert "| NOPE-9 | queued |" in out  # absent from lifecycle → unchanged
    assert "Prose — untouched | with a pipe |" in out


def test_sync_status_override_for_inflight_write(tmp_git_repo):
    """override carries the status of a spec whose YAML is not yet in HEAD."""
    repo = tmp_git_repo
    _write_yaml_and_commit(
        repo, "TECH-1", {"spec_id": "TECH-1", "status": "queued", "kind": "tech"}
    )
    backlog = (
        "| ID | Status | Kind | Updated | Spec |\n|----|--------|------|---------|------|\n"
        "| TECH-1 | queued | tech | 2026-06-20 | x |\n"
    )
    out = render_backlog.sync_status(repo, backlog, overrides={"TECH-1": "done"})
    assert "| TECH-1 | done |" in out


def test_sync_status_byte_identical_when_already_synced(tmp_git_repo):
    repo = tmp_git_repo
    _write_yaml_and_commit(repo, "TECH-1", {"spec_id": "TECH-1", "status": "done", "kind": "tech"})
    backlog = (
        "| ID | Status | Kind | Updated | Spec |\n|----|--------|------|---------|------|\n"
        "| TECH-1 | done | tech | 2026-06-20 | x |\n"
    )
    out = render_backlog.sync_status(repo, backlog)
    assert out == backlog
