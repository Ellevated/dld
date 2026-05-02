#!/usr/bin/env python3
"""
Module: audit_digest
Role: Daily digest of callback-audit.jsonl — group by project/verdict, send Telegram via event_writer.
Uses: event_writer:notify, stdlib (json, argparse, datetime, pathlib, os, sys)
Used by: cron @ 09:00 (setup-vps.sh --phase3)
CLI: python3 audit_digest.py [--since-hours N] [--audit-log PATH]

TECH-171: reads CALLBACK_AUDIT_LOG (or default) and produces a summary for yesterday.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import event_writer  # noqa: E402


# ── Audit log path ────────────────────────────────────────────────────────────

def _audit_log_path() -> Path:
    """Return path from CALLBACK_AUDIT_LOG env or default."""
    env_val = os.environ.get("CALLBACK_AUDIT_LOG", "")
    if env_val:
        return Path(env_val)
    return SCRIPT_DIR / "callback-audit.jsonl"


# ── Reading + filtering ───────────────────────────────────────────────────────

def read_records(audit_path: Path, since_hours: int = 24) -> list[dict]:
    """Read JSONL records from audit_path written within the last `since_hours`.

    Args:
        audit_path: Path to callback-audit.jsonl.
        since_hours: How many hours back to include (default 24 = last 24h).

    Returns:
        List of record dicts.
    """
    if not audit_path.is_file():
        return []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=since_hours)
    records: list[dict] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_str = rec.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if ts >= cutoff:
            records.append(rec)
    return records


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(records: list[dict]) -> dict[str, dict]:
    """Group records by project_id.

    Returns dict:
        project_id -> {
            "done": int,
            "demotes": list[dict]  # target_out != done
        }
    """
    result: dict[str, dict] = defaultdict(lambda: {"done": 0, "demotes": []})
    for rec in records:
        pid = rec.get("project_id", "unknown")
        target_out = rec.get("target_out", "")
        if target_out == "done":
            result[pid]["done"] += 1
        else:
            result[pid]["demotes"].append(rec)
    return dict(result)


# ── Formatting ────────────────────────────────────────────────────────────────

def format_digest(aggregated: dict[str, dict], audit_path: Path, date_label: str) -> str:
    """Build human-readable digest message.

    Args:
        aggregated: Output of aggregate().
        audit_path: Path to audit log (shown at end if demotes exist).
        date_label: Short date string for the header (e.g. "02.05").

    Returns:
        Multi-line string suitable for Telegram message.
    """
    lines = [f"Callback digest {date_label} (last 24h)"]
    total_demotes = 0
    for project_id in sorted(aggregated):
        data = aggregated[project_id]
        done_count = data["done"]
        demotes = data["demotes"]
        total_demotes += len(demotes)
        if demotes:
            spec_list = "/".join(d.get("spec_id", "?") for d in demotes[:4])
            if len(demotes) > 4:
                spec_list += f"/+{len(demotes) - 4}"
            first_reason = demotes[0].get("reason", "?")
            short_reason = first_reason.replace("no_implementation_commits", "no_impl")
            lines.append(
                f"  {project_id}: {done_count} done, {len(demotes)} demote"
                f" ({spec_list} -> blocked, {short_reason})"
            )
        else:
            lines.append(f"  {project_id}: {done_count} done, 0 demote")
    if not aggregated:
        lines.append("  (no records in last 24h)")
    if total_demotes > 0:
        lines.append(f"\nDetails: {audit_path}")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def _find_project_path() -> str:
    """Best-effort: find a project path to anchor the event_writer output.

    event_writer.notify() writes a pending-event JSON under <project_path>/ai/openclaw/.
    For the digest we use the dld repo itself (parent of SCRIPT_DIR) as the sink.
    """
    return str(SCRIPT_DIR.parent.parent)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Daily callback audit digest")
    parser.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="Look-back window in hours (default: 24)",
    )
    parser.add_argument(
        "--audit-log",
        type=str,
        default="",
        help="Override CALLBACK_AUDIT_LOG path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to stdout instead of sending via event_writer",
    )
    args = parser.parse_args()

    if args.audit_log:
        audit_path = Path(args.audit_log)
    else:
        audit_path = _audit_log_path()

    records = read_records(audit_path, since_hours=args.since_hours)
    aggregated = aggregate(records)
    date_label = datetime.now(tz=timezone.utc).strftime("%d.%m")
    message = format_digest(aggregated, audit_path, date_label)

    if args.dry_run:
        print(message)
        return

    project_path = _find_project_path()
    event_writer.notify(
        project_path,
        skill="digest",
        status="done",
        message=message,
    )
    print(f"Digest sent ({len(records)} records, {sum(len(v['demotes']) for v in aggregated.values())} demotes)")


if __name__ == "__main__":
    main()
