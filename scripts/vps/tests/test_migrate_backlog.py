"""
Tests for migrate_backlog_to_lifecycle.py

Covers:
  - test_happy_path_dry_run: dry run prints, no files written
  - test_happy_path_commit_round_trip: --commit writes files, round-trip OK
  - test_mismatch_aborts: backlog/spec mismatch → exit 2, no files
  - test_idempotent_rerun: second --commit run is no-op, exit 0
"""

import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).parent.parent / "migrate_backlog_to_lifecycle.py"

BACKLOG_QUEUED = """\
# DLD Backlog

## P1

| ID | Task | Status | Priority | Feature.md |
|----|------|--------|----------|------------|
| TECH-001 | Test task | queued | P1 | [spec](features/TECH-001-test.md) |
"""

SPEC_QUEUED = """\
# TECH-001 — Test

**Status:** queued

Some content here.
"""

BACKLOG_DONE = """\
# DLD Backlog

## P1

| ID | Task | Status | Priority | Feature.md |
|----|------|--------|----------|------------|
| TECH-001 | Test task | done | P1 | [spec](features/TECH-001-test.md) |
"""

SPEC_DONE = """\
# TECH-001 — Test

**Status:** done

Some content.
"""

SPEC_MISMATCHED = """\
# TECH-001 — Test

**Status:** done

Different from backlog.
"""


def _setup_repo(tmp_path: Path, backlog_content: str, spec_content: str) -> Path:
    """Create minimal repo structure for migration tests."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    lifecycle = tmp_path / "ai" / "lifecycle"
    lifecycle.mkdir(parents=True)
    (lifecycle / ".gitkeep").touch()

    (tmp_path / "ai" / "backlog.md").write_text(backlog_content, encoding="utf-8")
    (features / "TECH-001-test.md").write_text(spec_content, encoding="utf-8")
    return tmp_path


def _run(repo: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), *extra_args],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_happy_path_dry_run(tmp_path: Path) -> None:
    """Dry run: prints proposed YAML, exit 0, no files written."""
    repo = _setup_repo(tmp_path, BACKLOG_QUEUED, SPEC_QUEUED)

    result = _run(repo)

    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "TECH-001" in result.stdout
    assert "queued" in result.stdout
    assert "Would write" in result.stdout

    # No YAML files written (only .gitkeep)
    lifecycle_dir = repo / "ai" / "lifecycle"
    yaml_files = list(lifecycle_dir.glob("*.yaml"))
    assert yaml_files == [], f"Expected no yaml files, got: {yaml_files}"


def test_happy_path_commit_round_trip(tmp_path: Path) -> None:
    """--commit writes yaml, round-trip succeeds, exit 0."""
    repo = _setup_repo(tmp_path, BACKLOG_QUEUED, SPEC_QUEUED)

    result = _run(repo, "--commit")

    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Round-trip self-test: OK" in result.stdout

    lifecycle_file = repo / "ai" / "lifecycle" / "TECH-001.yaml"
    assert lifecycle_file.exists(), "Expected TECH-001.yaml to be written"

    data = yaml.safe_load(lifecycle_file.read_text(encoding="utf-8"))
    assert data["spec_id"] == "TECH-001"
    assert data["status"] == "queued"
    assert data["priority"] == "p1"
    assert data["kind"] == "tech"
    assert data["updated_by"] == "migration"
    assert data["version"] == 1
    assert data["transitions"] == []


def test_mismatch_aborts(tmp_path: Path) -> None:
    """Backlog says queued, spec says done → exit 2, no YAML files written."""
    # Backlog says queued, spec says done
    repo = _setup_repo(tmp_path, BACKLOG_QUEUED, SPEC_MISMATCHED)

    result = _run(repo, "--commit")

    assert result.returncode == 2, f"Expected exit 2, got {result.returncode}"
    assert "MISMATCH" in result.stderr
    assert "TECH-001" in result.stderr
    assert "backlog=queued" in result.stderr
    assert "spec=done" in result.stderr

    # No YAML files should be written
    lifecycle_dir = repo / "ai" / "lifecycle"
    yaml_files = list(lifecycle_dir.glob("*.yaml"))
    assert yaml_files == [], f"No yaml files should be written on mismatch: {yaml_files}"


def test_idempotent_rerun(tmp_path: Path) -> None:
    """Running --commit twice: second run is no-op, exit 0, 'Already migrated'."""
    repo = _setup_repo(tmp_path, BACKLOG_DONE, SPEC_DONE)

    # First run
    first = _run(repo, "--commit")
    assert first.returncode == 0, f"First run failed: {first.stderr}"

    # Second run
    second = _run(repo, "--commit")
    assert second.returncode == 0, f"Second run failed: {second.stderr}"
    assert "Already migrated" in second.stdout, (
        f"Expected 'Already migrated' in stdout, got: {second.stdout}"
    )


def test_dry_run_does_not_write_on_done_status(tmp_path: Path) -> None:
    """Dry run with done status: still no files written."""
    repo = _setup_repo(tmp_path, BACKLOG_DONE, SPEC_DONE)

    result = _run(repo)

    assert result.returncode == 0
    assert "done" in result.stdout
    yaml_files = list((repo / "ai" / "lifecycle").glob("*.yaml"))
    assert yaml_files == []


def test_missing_spec_file_uses_backlog_status(tmp_path: Path) -> None:
    """If spec file is missing, backlog status is used without error."""
    features = tmp_path / "ai" / "features"
    features.mkdir(parents=True)
    lifecycle = tmp_path / "ai" / "lifecycle"
    lifecycle.mkdir(parents=True)
    (lifecycle / ".gitkeep").touch()

    # Backlog references a spec that doesn't exist as a file
    backlog = """\
# Backlog

## P1

| ID | Task | Status | Priority | Feature.md |
|----|------|--------|----------|------------|
| FTR-999 | No-file task | done | P1 | none |
"""
    (tmp_path / "ai" / "backlog.md").write_text(backlog, encoding="utf-8")

    result = _run(tmp_path, "--commit")

    assert result.returncode == 0, f"stderr: {result.stderr}"
    lifecycle_file = tmp_path / "ai" / "lifecycle" / "FTR-999.yaml"
    assert lifecycle_file.exists()
    data = yaml.safe_load(lifecycle_file.read_text(encoding="utf-8"))
    assert data["status"] == "done"
    assert data["kind"] == "ftr"
