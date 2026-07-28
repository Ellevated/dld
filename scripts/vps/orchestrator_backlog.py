#!/usr/bin/env python3
"""
Module: orchestrator_backlog
Role: Backlog parser + lifecycle bootstrap — column-aware ai/backlog.md parsing
      (ADR-026), lifecycle.yaml creation for new Spark spec.md files, and stale
      autopilot-stash cleanup.
Uses: lifecycle (import), subprocess (git CLI), event_writer (lazy import)
Used by: orchestrator (facade re-export)
"""

import logging
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import lifecycle  # noqa: E402

log = logging.getLogger("orchestrator")


# TECH-189 Task 4: bootstrap_new_specs anomaly detector.
# Normal cycles create 0-1 lifecycle yamls. >3 in one cycle = anomaly
# (backlog-write race, bulk import, etc). Today's incident (2026-05-23)
# created 15 in one cycle and burned ~$258 on retries.
BOOTSTRAP_ANOMALY_THRESHOLD = 3


_VALID_STATUSES = frozenset(
    {"queued", "in_progress", "blocked", "done", "resumed", "draft", "stale"}
)
_SPEC_ID_RE_BS = re.compile(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*")


def _parse_backlog(text: str) -> dict[str, str | None]:
    """Column-aware backlog parser: extract {spec_id: status_or_None} from markdown table.

    Supports any column order (template format, awardybot/dowry short format, etc.).

    Algorithm:
    1. Find header row + divider pair (line with |---|---| pattern).
    2. Build column map {name_lower: index} from header row.
    3. For each spec-id data row:
       a. If 'status' column found in header → use that column's value if valid.
       b. Else (no header OR invalid value) → scan all columns for first valid status.
       c. If nothing valid → store None.
    4. If no header found → skip step 1/2; use scan-all-columns for every spec row.

    Returns dict[spec_id, status_str | None].
    """
    lines = text.splitlines()
    n = len(lines)

    # Divider pattern: a line that is only pipes, dashes, colons, spaces
    divider_re = re.compile(r"^\|[\s\-:|]+\|$")

    # Find header row index: the line immediately before a divider
    col_map: dict[str, int] = {}
    for i in range(1, n):
        if divider_re.match(lines[i].strip()):
            # lines[i-1] is the header
            raw_header = lines[i - 1]
            parts = [p.strip().lower() for p in raw_header.split("|")]
            # parts[0] == '' (before first |), parts[-1] == '' (after last |)
            # real columns: parts[1:-1]
            cols = parts[1:-1]
            col_map = {name: idx for idx, name in enumerate(cols)}
            break

    result: dict[str, str | None] = {}

    for line in lines:
        stripped = line.strip()
        # Must start with | and contain a spec-id in first pipe-column
        if not stripped.startswith("|"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        # parts[0] == '', spec-id in parts[1], parts[-1] == ''
        if len(parts) < 3:
            continue
        spec_id_candidate = parts[1].strip()
        if not _SPEC_ID_RE_BS.fullmatch(spec_id_candidate):
            continue
        spec_id = spec_id_candidate
        data_cols = parts[1:-1]  # actual column values (0-indexed matches col_map)

        status: str | None = None

        # Try header-guided extraction first
        if col_map and "status" in col_map:
            status_idx = col_map["status"]
            if status_idx < len(data_cols):
                candidate = data_cols[status_idx].lower().strip()
                if candidate in _VALID_STATUSES:
                    status = candidate

        # Fallback: scan all columns for a valid status value
        if status is None:
            for col_val in data_cols:
                candidate = col_val.lower().strip()
                if candidate in _VALID_STATUSES:
                    status = candidate
                    break

        result[spec_id] = status

    return result


def _bump_unparsable_counter(project_dir: str) -> None:
    """Increment ai/.bootstrap-unparsable-count for alerting; best-effort."""
    counter_path = Path(project_dir) / "ai" / ".bootstrap-unparsable-count"
    try:
        prev = int(counter_path.read_text().strip()) if counter_path.is_file() else 0
        counter_path.write_text(str(prev + 1))
    except Exception:  # noqa: BLE001
        pass


def _report_bootstrap_anomaly(created_count: int, project_dir: str) -> None:
    """TECH-189 Task 4 anomaly path, split out of bootstrap_new_specs (EC-8).

    No test patches into this — it exists only to keep the main loop under
    the 80-line ceiling (TECH-215 Task 6). Behaviour is unchanged: WARNING
    log, counter bump, best-effort Hermes notify, all gated on
    created_count > BOOTSTRAP_ANOMALY_THRESHOLD.
    """
    if created_count <= BOOTSTRAP_ANOMALY_THRESHOLD:
        return
    log.warning(
        "BOOTSTRAP_ANOMALY: created %d lifecycle yamls in one cycle for %s "
        "(threshold=%d) — possible backlog-write race or bulk-import",
        created_count,
        project_dir,
        BOOTSTRAP_ANOMALY_THRESHOLD,
    )
    counter_path = Path(project_dir) / "ai" / ".bootstrap-anomaly-count"
    try:
        prev = int(counter_path.read_text().strip()) if counter_path.is_file() else 0
        counter_path.write_text(str(prev + 1))
    except Exception:  # noqa: BLE001
        pass
    try:
        from event_writer import notify

        notify(
            project_dir.rstrip("/").split("/")[-1],
            f"BOOTSTRAP_ANOMALY: {created_count} lifecycle yamls in one cycle",
        )
    except Exception:  # noqa: BLE001
        pass


def bootstrap_new_specs(project_dir: str) -> None:
    """Create ai/lifecycle/{spec_id}.yaml for any NEW Spark spec.md without one.

    Spark writes spec.md but does NOT touch ai/lifecycle/. Orchestrator
    bootstraps the YAML on first sight so subsequent scan_queued sees it.

    Safety: only bootstrap if spec_id appears in current ai/backlog.md.
    Archived/orphan spec.md files (features/ without backlog row) are skipped —
    they're historical artifacts, not work to dispatch.
    """
    features_dir = Path(project_dir) / "ai" / "features"
    if not features_dir.is_dir():
        return
    # CR-5 (ARCH-196): Read backlog from HEAD, not WT — prevents TOCTOU (CWE-367)
    # when callback render commits or parallel spark edits are in flight.
    # Falls back to empty string for brand-new repos with no HEAD yet.
    try:
        backlog_text = subprocess.check_output(
            ["git", "show", "HEAD:ai/backlog.md"],
            cwd=project_dir,
            text=True,
            timeout=10,
        )
    except subprocess.CalledProcessError:
        backlog_text = ""  # new project / no HEAD yet
    # Column-aware parser: handles template format (status in 3rd col),
    # awardybot/dowry short format (status in 2nd col), and any other ordering.
    active_status = _parse_backlog(backlog_text)
    backlog_ids = set(
        m.group(0) for m in re.finditer(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*", backlog_text)
    )
    created_count = 0
    for spec_md in features_dir.glob("*.md"):
        m = re.search(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*", spec_md.name)
        if not m:
            continue
        spec_id = m.group(0)
        if spec_id not in backlog_ids:
            # Orphan spec.md (not in backlog) — skip. Historical artifact.
            continue
        # Check HEAD (plumbing-based), not WT file — lifecycle.py writes via
        # git plumbing, so the yaml is in HEAD but never in working tree.
        if lifecycle.read_lifecycle(project_dir, spec_id) is not None:
            continue
        priority, kind = _parse_priority_kind(spec_md)
        # Determine bootstrap status:
        #   - parseable active row → use its status (typically 'queued' for new Spark)
        #   - unparsable/missing row → 'queued' (safe fail-into-queue; logs WARNING +
        #     bumps .bootstrap-unparsable-count for operator alerting)
        status = active_status.get(spec_id)
        if status is None:
            log.warning(
                "BOOTSTRAP_UNPARSABLE: backlog status unparsable for %s in %s — "
                "defaulting to 'queued' (operator: verify backlog format)",
                spec_id,
                project_dir,
            )
            _bump_unparsable_counter(project_dir)
            status = "queued"
        try:
            lifecycle.create_initial(project_dir, spec_id, priority, kind, status=status)
            created_count += 1
            log.info(
                "BOOTSTRAP: created lifecycle.yaml for %s status=%s in %s",
                spec_id,
                status,
                project_dir,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("BOOTSTRAP: failed for %s: %s", spec_id, exc)

    _report_bootstrap_anomaly(created_count, project_dir)


def _parse_priority_kind(spec_md: Path) -> tuple:
    """Extract Priority and Kind from spec markdown header (best-effort).

    Returns ("p1", "tech") defaults if not found. Spec format:
        **Priority:** P0|P1|P2
        **Kind:** tech|ftr|bug|arch
    """
    text = spec_md.read_text(errors="replace")[:2000]
    p_m = re.search(r"\*\*Priority:\*\*\s*([pP][012])", text)
    k_m = re.search(r"\*\*Kind:\*\*\s*(tech|ftr|bug|arch)", text, re.IGNORECASE)
    priority = p_m.group(1).lower() if p_m else "p1"
    kind = k_m.group(1).lower() if k_m else "tech"
    return priority, kind


def cleanup_stale_stashes(project_dir: str, age_hours: int = 24) -> int:
    """Drop autopilot-temp-* stashes older than age_hours. Returns count dropped. Best-effort.

    CR-12 (ARCH-196): Stale autopilot stashes accumulate when autopilot is interrupted
    mid-stash and never pops. After 24h they're dead weight. Drop them at startup.
    """
    dropped = 0
    try:
        # Get stash list with timestamps
        output = subprocess.check_output(
            ["git", "stash", "list", "--format=%gd %gs %ci"],
            cwd=project_dir,
            text=True,
            timeout=15,
        ).strip()
        if not output:
            return 0

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=age_hours)

        # Parse stash entries (most recent first → drop in reverse to preserve indices)
        to_drop = []
        for line in output.splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            stash_ref = parts[0]
            msg_and_date = parts[2]
            if "autopilot-temp-" not in msg_and_date and "autopilot-phase3" not in msg_and_date:
                continue
            # Try to extract ISO timestamp from end of line (from --format=%ci)
            # Format: "stash@{N} On branch: msg YYYY-MM-DD HH:MM:SS +OFFSET"
            try:
                # %ci = "YYYY-MM-DD HH:MM:SS +OFFSET" — take last 3 space-separated tokens
                tokens = msg_and_date.rsplit(" ", 3)
                date_str = " ".join(tokens[-3:])
                stash_time = datetime.fromisoformat(date_str)
                if stash_time < cutoff:
                    to_drop.append(stash_ref)
            except (ValueError, IndexError):
                pass

        # Drop in reverse order to avoid index shifts
        for ref in reversed(to_drop):
            try:
                subprocess.check_call(
                    ["git", "stash", "drop", ref],
                    cwd=project_dir,
                    timeout=10,
                )
                dropped += 1
                log.info("Startup: dropped stale stash %s in %s", ref, project_dir)
            except subprocess.CalledProcessError:
                pass
    except Exception:  # noqa: BLE001
        pass  # best-effort
    return dropped
