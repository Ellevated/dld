"""TECH-171 — Unit tests for audit log helpers in callback.py.

EC-1: Each verify_status_sync call writes exactly 1 JSON line.
EC-2: The record contains all required keys.

No DB, no subprocess calls — only the JSONL write/read helpers are exercised.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import callback  # noqa: E402

# Required keys per spec (TECH-171 Goal section)
REQUIRED_KEYS = {
    "ts",
    "project_id",
    "spec_id",
    "pueue_id",
    "target_in",
    "target_out",
    "reason",
    "allowed_count",
    "code_loc",
    "test_loc",
    "code_commits",
    "started_at",
    "duration_ms",
}


# ── _write_audit / _audit_log_path ────────────────────────────────────────────

def test_write_audit_creates_file(tmp_path):
    """_write_audit creates the file if it doesn't exist."""
    audit_file = tmp_path / "test-audit.jsonl"
    import os
    os.environ["CALLBACK_AUDIT_LOG"] = str(audit_file)
    try:
        record = {
            "ts": "2026-05-02T09:00:00Z",
            "project_id": "myproject",
            "spec_id": "FTR-001",
            "pueue_id": 42,
            "target_in": "done",
            "target_out": "done",
            "reason": "fixed",
            "allowed_count": 3,
            "code_loc": 100,
            "test_loc": 20,
            "code_commits": 2,
            "started_at": "2026-05-01T19:00:00Z",
            "duration_ms": 50,
        }
        callback._write_audit(record)
        assert audit_file.exists()
    finally:
        del os.environ["CALLBACK_AUDIT_LOG"]


def test_write_audit_appends_lines(tmp_path):
    """_write_audit appends one line per call (EC-1 — N calls → N lines)."""
    audit_file = tmp_path / "test-audit.jsonl"
    import os
    os.environ["CALLBACK_AUDIT_LOG"] = str(audit_file)
    try:
        for i in range(3):
            callback._write_audit({"spec_id": f"FTR-{i}", "i": i})
        lines = [ln for ln in audit_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 3
    finally:
        del os.environ["CALLBACK_AUDIT_LOG"]


def test_write_audit_each_line_valid_json(tmp_path):
    """Each appended line is parseable JSON."""
    audit_file = tmp_path / "test-audit.jsonl"
    import os
    os.environ["CALLBACK_AUDIT_LOG"] = str(audit_file)
    try:
        callback._write_audit({"key": "value", "num": 1})
        callback._write_audit({"key": "other", "num": 2})
        for line in audit_file.read_text().splitlines():
            obj = json.loads(line)
            assert isinstance(obj, dict)
    finally:
        del os.environ["CALLBACK_AUDIT_LOG"]


# ── _emit_audit ───────────────────────────────────────────────────────────────

def test_emit_audit_all_required_keys_present(tmp_path):
    """EC-2 — record contains all required keys."""
    audit_file = tmp_path / "emit-test.jsonl"
    import os
    os.environ["CALLBACK_AUDIT_LOG"] = str(audit_file)
    try:
        start = time.monotonic()
        callback._emit_audit(
            project_id="myproject",
            spec_id="TECH-099",
            pueue_id=101,
            target_in="done",
            target_out="blocked",
            reason="no_implementation_commits",
            allowed_count=5,
            code_loc=0,
            test_loc=0,
            code_commits=0,
            started_at="2026-05-01T19:00:00Z",
            start_wall=start,
        )
        lines = [ln for ln in audit_file.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1, "Exactly one line written"
        record = json.loads(lines[0])
        missing = REQUIRED_KEYS - set(record.keys())
        assert not missing, f"Missing required keys: {missing}"
    finally:
        del os.environ["CALLBACK_AUDIT_LOG"]


def test_emit_audit_duration_nonnegative(tmp_path):
    """duration_ms is non-negative."""
    audit_file = tmp_path / "dur-test.jsonl"
    import os
    os.environ["CALLBACK_AUDIT_LOG"] = str(audit_file)
    try:
        start = time.monotonic()
        time.sleep(0.001)
        callback._emit_audit(
            project_id="proj",
            spec_id="FTR-1",
            pueue_id=1,
            target_in="done",
            target_out="done",
            reason="fixed",
            allowed_count=2,
            code_loc=10,
            test_loc=5,
            code_commits=1,
            started_at=None,
            start_wall=start,
        )
        record = json.loads(audit_file.read_text().strip())
        assert record["duration_ms"] >= 0
    finally:
        del os.environ["CALLBACK_AUDIT_LOG"]


def test_emit_audit_ts_format(tmp_path):
    """ts field has ISO 8601 format ending in Z."""
    audit_file = tmp_path / "ts-test.jsonl"
    import os
    os.environ["CALLBACK_AUDIT_LOG"] = str(audit_file)
    try:
        callback._emit_audit(
            project_id="proj",
            spec_id="FTR-2",
            pueue_id=2,
            target_in="done",
            target_out="done",
            reason="already_correct",
            allowed_count=1,
            code_loc=0,
            test_loc=0,
            code_commits=0,
            started_at=None,
            start_wall=time.monotonic(),
        )
        record = json.loads(audit_file.read_text().strip())
        ts = record["ts"]
        assert ts.endswith("Z"), f"ts should end with Z: {ts}"
        # Should parse without error
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None
    finally:
        del os.environ["CALLBACK_AUDIT_LOG"]


# ── _is_test_path ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,expected", [
    ("tests/unit/test_foo.py", True),
    ("tests/integration/test_bar.py", True),
    ("src/domains/foo/foo_test.py", True),
    ("src/domains/foo/foo.test.ts", True),
    ("src/domains/foo/foo.spec.ts", True),
    ("src/domains/foo/service.py", False),
    ("scripts/vps/callback.py", False),
    ("ai/features/FTR-001.md", False),
])
def test_is_test_path(path, expected):
    assert callback._is_test_path(path) == expected


# ── _commit_stats ─────────────────────────────────────────────────────────────

def test_commit_stats_returns_zeros_on_empty_allowed():
    """Empty allowed list → (0, 0, 0) — no subprocess needed."""
    result = callback._commit_stats("/nonexistent", [], "2026-01-01T00:00:00Z")
    assert result == (0, 0, 0)


def test_commit_stats_returns_zeros_on_none_allowed():
    """None allowed → (0, 0, 0)."""
    result = callback._commit_stats("/nonexistent", None, "2026-01-01T00:00:00Z")
    assert result == (0, 0, 0)


def test_commit_stats_returns_zeros_on_none_started_at():
    """None started_at → (0, 0, 0)."""
    result = callback._commit_stats("/nonexistent", ["src/foo.py"], None)
    assert result == (0, 0, 0)
