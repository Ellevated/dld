"""
Module: runner_heartbeat
Role: write the per-turn heartbeat file that heartbeat_reaper.py reads to
      detect wedged autopilot sessions.
Uses: json, os, datetime, pathlib

Used by:
  - claude-runner.py
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _write_heartbeat(
    log_dir: Path,
    project_name: str,
    ts_label: str,
    turn: int,
    elapsed_s: int,
    last_tool: str | None,
    started_at_iso: str,
    model: str,
) -> None:
    """Atomic per-turn heartbeat (best-effort, ADR-004). cost_usd omitted (SDK: ResultMessage only)."""
    try:
        hb_path = log_dir / f"{project_name}-{ts_label}.heartbeat.json"
        tmp_path = hb_path.with_suffix(".tmp")
        data = {
            "turn": turn,
            "elapsed_s": elapsed_s,
            "last_tool": last_tool,
            "started_at": started_at_iso,
            "model": model,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        tmp_path.write_text(json.dumps(data, ensure_ascii=False))
        os.replace(str(tmp_path), str(hb_path))
    except Exception:  # noqa: BLE001 — heartbeat is best-effort (ADR-004 style)
        pass
