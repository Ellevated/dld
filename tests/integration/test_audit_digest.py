"""TECH-171 — Integration tests for audit_digest.py.

EC-3: digest script correctly aggregates JSONL for last 24h.

No mocks — uses real filesystem + real audit_digest module functions.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "vps"
sys.path.insert(0, str(SCRIPT_DIR))

import audit_digest  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


# ── read_records ──────────────────────────────────────────────────────────────

def test_read_records_empty_file(tmp_path):
    """Empty file → empty list."""
    audit_file = tmp_path / "audit.jsonl"
    audit_file.write_text("")
    result = audit_digest.read_records(audit_file, since_hours=24)
    assert result == []


def test_read_records_missing_file(tmp_path):
    """Missing file → empty list (no exception)."""
    audit_file = tmp_path / "nonexistent.jsonl"
    result = audit_digest.read_records(audit_file, since_hours=24)
    assert result == []


def test_read_records_filters_old_records(tmp_path):
    """Records older than window are excluded."""
    now = _now_utc()
    records = [
        {"ts": _ts(now - timedelta(hours=1)), "spec_id": "FTR-001"},  # in window
        {"ts": _ts(now - timedelta(hours=25)), "spec_id": "FTR-002"},  # outside window
    ]
    audit_file = tmp_path / "audit.jsonl"
    _write_jsonl(audit_file, records)
    result = audit_digest.read_records(audit_file, since_hours=24)
    assert len(result) == 1
    assert result[0]["spec_id"] == "FTR-001"


def test_read_records_includes_all_recent(tmp_path):
    """All records within window are returned."""
    now = _now_utc()
    records = [
        {"ts": _ts(now - timedelta(minutes=5)), "spec_id": f"FTR-{i}"}
        for i in range(5)
    ]
    audit_file = tmp_path / "audit.jsonl"
    _write_jsonl(audit_file, records)
    result = audit_digest.read_records(audit_file, since_hours=24)
    assert len(result) == 5


def test_read_records_skips_invalid_json_lines(tmp_path):
    """Lines with invalid JSON are silently skipped."""
    now = _now_utc()
    audit_file = tmp_path / "audit.jsonl"
    with audit_file.open("w") as fh:
        fh.write(json.dumps({"ts": _ts(now), "spec_id": "FTR-001"}) + "\n")
        fh.write("NOT JSON\n")
        fh.write(json.dumps({"ts": _ts(now), "spec_id": "FTR-002"}) + "\n")
    result = audit_digest.read_records(audit_file, since_hours=24)
    assert len(result) == 2


def test_read_records_skips_missing_ts(tmp_path):
    """Records without ts are skipped."""
    audit_file = tmp_path / "audit.jsonl"
    audit_file.write_text(json.dumps({"spec_id": "FTR-001", "no_ts": True}) + "\n")
    result = audit_digest.read_records(audit_file, since_hours=24)
    assert len(result) == 0


# ── aggregate ─────────────────────────────────────────────────────────────────

def test_aggregate_counts_done(tmp_path):
    """done records are counted per project."""
    records = [
        {"project_id": "alpha", "target_out": "done"},
        {"project_id": "alpha", "target_out": "done"},
        {"project_id": "beta", "target_out": "done"},
    ]
    agg = audit_digest.aggregate(records)
    assert agg["alpha"]["done"] == 2
    assert agg["beta"]["done"] == 1
    assert agg["alpha"]["demotes"] == []


def test_aggregate_collects_demotes(tmp_path):
    """Non-done target_out goes into demotes list."""
    records = [
        {"project_id": "alpha", "target_out": "blocked", "spec_id": "FTR-001",
         "reason": "no_implementation_commits"},
        {"project_id": "alpha", "target_out": "done"},
    ]
    agg = audit_digest.aggregate(records)
    assert agg["alpha"]["done"] == 1
    assert len(agg["alpha"]["demotes"]) == 1
    assert agg["alpha"]["demotes"][0]["spec_id"] == "FTR-001"


def test_aggregate_unknown_project_id(tmp_path):
    """Records without project_id use 'unknown' key."""
    records = [{"target_out": "done"}]
    agg = audit_digest.aggregate(records)
    assert "unknown" in agg
    assert agg["unknown"]["done"] == 1


def test_aggregate_multiple_projects(tmp_path):
    """Multiple projects are aggregated independently."""
    now = _now_utc()
    records = [
        {"project_id": "awardybot", "target_out": "done"},
        {"project_id": "awardybot", "target_out": "done"},
        {"project_id": "awardybot", "target_out": "blocked", "spec_id": "FTR-897",
         "reason": "no_implementation_commits"},
        {"project_id": "dowry", "target_out": "done"},
        {"project_id": "dowry", "target_out": "done"},
        {"project_id": "dowry", "target_out": "done"},
        {"project_id": "wb", "target_out": "blocked", "spec_id": "ARCH-176a",
         "reason": "no_implementation_commits"},
        {"project_id": "wb", "target_out": "blocked", "spec_id": "ARCH-176b",
         "reason": "no_implementation_commits"},
    ]
    agg = audit_digest.aggregate(records)
    assert agg["awardybot"]["done"] == 2
    assert len(agg["awardybot"]["demotes"]) == 1
    assert agg["dowry"]["done"] == 3
    assert agg["dowry"]["demotes"] == []
    assert agg["wb"]["done"] == 0
    assert len(agg["wb"]["demotes"]) == 2


# ── format_digest ─────────────────────────────────────────────────────────────

def test_format_digest_header_contains_date():
    """Header line contains the date label."""
    agg = {}
    path = Path("/tmp/test.jsonl")
    msg = audit_digest.format_digest(agg, path, "02.05")
    assert "02.05" in msg


def test_format_digest_empty_shows_no_records():
    """Empty aggregation shows placeholder."""
    agg = {}
    msg = audit_digest.format_digest(agg, Path("/tmp/x.jsonl"), "02.05")
    assert "no records" in msg.lower()


def test_format_digest_zero_demotes_no_detail_link():
    """When no demotes, no link to JSONL shown."""
    agg = {"myproject": {"done": 5, "demotes": []}}
    msg = audit_digest.format_digest(agg, Path("/tmp/audit.jsonl"), "02.05")
    assert "/tmp/audit.jsonl" not in msg
    assert "5 done" in msg


def test_format_digest_with_demotes_shows_link():
    """When demotes exist, audit log path appears in message."""
    agg = {
        "myproject": {
            "done": 3,
            "demotes": [{"spec_id": "FTR-001", "reason": "no_implementation_commits"}],
        }
    }
    audit_path = Path("/tmp/callback-audit.jsonl")
    msg = audit_digest.format_digest(agg, audit_path, "02.05")
    assert str(audit_path) in msg
    assert "FTR-001" in msg


def test_format_digest_spec_goal_example():
    """Reproduces the spec's example output (approximate match)."""
    agg = {
        "awardybot": {
            "done": 12,
            "demotes": [{"spec_id": "FTR-897", "reason": "no_implementation_commits"}],
        },
        "dowry": {"done": 3, "demotes": []},
        "gipotenuza": {"done": 5, "demotes": []},
        "wb": {
            "done": 0,
            "demotes": [
                {"spec_id": f"ARCH-176{s}", "reason": "no_implementation_commits"}
                for s in ("a", "b", "c", "d")
            ],
        },
    }
    msg = audit_digest.format_digest(agg, Path("/tmp/audit.jsonl"), "02.05")
    # Projects appear
    assert "awardybot" in msg
    assert "dowry" in msg
    assert "gipotenuza" in msg
    assert "wb" in msg
    # Demote info
    assert "FTR-897" in msg
    assert "ARCH-176" in msg
    # Clean projects
    assert "3 done" in msg  # dowry
