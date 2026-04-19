#!/usr/bin/env python3
"""
Scan durable orchestration artifacts for OpenClaw.

Purpose:
- read pending wake events written by callback/QA
- summarize new QA/reflect artifacts
- optionally mark events as processed

Usage:
  python3 scripts/vps/openclaw-artifact-scan.py --project-dir /path/to/repo
  python3 scripts/vps/openclaw-artifact-scan.py --project-dir /path/to/repo --mark-processed
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def extract_status(text: str) -> str:
    """Extract status from QA report.

    Supports two formats:
    1. Structured: '**Status:** passed' header line
    2. Hand-written/agent: no Status header (returns 'no_status_header')
    """
    for line in text.splitlines():
        if line.startswith("**Status:**"):
            val = line[len("**Status:**") :].strip().rstrip("*").strip()
            return val if val else "no_status_header"
    return "no_status_header"


def extract_spec(text: str) -> str:
    """Extract spec ID from QA report.

    Supports two formats:
    1. Structured: '**Spec:** TECH-153' header line
    2. Hand-written/agent: '# QA Report: TECH-151 — description' title
    """
    import re

    # Primary: explicit **Spec:** header
    for line in text.splitlines():
        if line.startswith("**Spec:**"):
            return line[len("**Spec:**") :].strip()

    # Fallback: extract from title '# QA Report: SPEC-ID ...'
    for line in text.splitlines():
        m = re.match(r"^#\s+QA Report:\s*(\S+)", line)
        if m:
            spec_id = m.group(1).rstrip(" —-")
            # Normalize: tech-151 → TECH-151
            prefix_match = re.match(r"^(tech|ftr|bug|arch)(-\d+)$", spec_id, re.IGNORECASE)
            if prefix_match:
                spec_id = prefix_match.group(1).upper() + prefix_match.group(2)
            return spec_id

    return ""


def summarize_md(path: Path, max_lines: int = 10) -> str:
    text = read_text(path)
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[:max_lines])[:1200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--mark-processed", action="store_true")
    args = ap.parse_args()

    project_dir = Path(args.project_dir).resolve()
    openclaw_dir = project_dir / "ai" / "openclaw"
    events_dir = openclaw_dir / "pending-events"
    processed_dir = openclaw_dir / "processed-events"
    qa_dir = project_dir / "ai" / "qa"
    reflect_dir = project_dir / "ai" / "reflect"

    events = []
    for event_file in sorted(events_dir.glob("*.json")):
        try:
            data = json.loads(read_text(event_file) or "{}")
        except Exception:
            data = {"error": "invalid-json"}
        data["file"] = str(event_file.relative_to(project_dir))
        related = data.get("artifact_rel") or ""
        artifact_summary = ""
        if related:
            artifact_path = project_dir / related
            if artifact_path.exists() and artifact_path.is_file():
                artifact_summary = summarize_md(artifact_path)
        data["artifact_summary"] = artifact_summary
        events.append(data)

    qa_reports = []
    qa_candidates = [p for p in qa_dir.glob("*.md") if p.name[:4].isdigit()]
    for qa_file in sorted(qa_candidates, reverse=True)[:10]:
        text = read_text(qa_file)
        qa_reports.append(
            {
                "file": str(qa_file.relative_to(project_dir)),
                "status": extract_status(text),
                "spec": extract_spec(text),
            }
        )

    reflect_reports = []
    for reflect_file in sorted(reflect_dir.glob("findings-*.md"), reverse=True)[:10]:
        reflect_reports.append(
            {
                "file": str(reflect_file.relative_to(project_dir)),
                "summary": summarize_md(reflect_file, max_lines=8),
            }
        )

    result = {
        "project_dir": str(project_dir),
        "pending_events": events,
        "qa_reports": qa_reports,
        "reflect_reports": reflect_reports,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.mark_processed and events:
        processed_dir.mkdir(parents=True, exist_ok=True)
        for event_file in sorted(events_dir.glob("*.json")):
            target = processed_dir / event_file.name
            event_file.rename(target)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
