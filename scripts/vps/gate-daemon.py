#!/usr/bin/env python3
"""
Module: gate-daemon
Role: Shadow polling daemon — evaluates gate verdicts for in_progress/queued specs
      and writes results to JSONL shadow log. SHADOW_ONLY_MODE=True (Wave 1).
      Does NOT write lifecycle state. Does NOT import callback.

Uses:
  - gate_logic: fetch_develop, parse_allowed_files, find_implementation_commit
  - lifecycle: list_by_status
  - db: log_gate_cycle, get_all_projects
  - logging.handlers: RotatingFileHandler (shadow JSONL writer)
  - subprocess: git rev-parse origin/develop (SHA cache)

Used by:
  - systemd (dld-gate-daemon.service) — Wave 2 setup-vps.sh

FF-09 invariant: ZERO imports from callback. ZERO lifecycle.write_lifecycle calls.
SHADOW_ONLY_MODE guard: assert at process start + before any lifecycle code path.

Glossary: ai/glossary/orchestrator.md
"""

import atexit
import glob
import json
import logging
import logging.handlers
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import db  # noqa: E402
import gate_logic  # noqa: E402
import lifecycle  # noqa: E402

# SHADOW_ONLY_MODE guard — Wave 3 cutover not yet authorized.
SHADOW_ONLY_MODE = True
assert SHADOW_ONLY_MODE, "Wave 3 cutover not yet authorized"

log = logging.getLogger("gate-daemon")
_stop = Event()

# Per-project SHA cache: project_id -> last known origin/develop sha.
_origin_develop_sha: dict[str, str] = {}


def _load_env() -> None:
    """Load .env from SCRIPT_DIR. Manual parser, no dotenv dependency."""
    env_file = SCRIPT_DIR / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def _setup_logging() -> None:
    """JSON structured logging with daily rotation, 7-day retention."""
    log_dir = os.environ.get("LOG_DIR", "/var/log/dld-orchestrator")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = str(SCRIPT_DIR / "logs")
        os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter(
        '{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    fh = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, "gate-daemon.log"), when="midnight", backupCount=7, utc=True
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(sh)


def _signal_handler(signum: int, _frame) -> None:
    log.info("signal %d received, stopping", signum)
    _stop.set()


def _write_pid() -> None:
    pid_file = SCRIPT_DIR / ".gate-daemon.pid"
    pid_file.write_text(str(os.getpid()))
    atexit.register(lambda: pid_file.unlink(missing_ok=True))


def _make_shadow_handler() -> logging.handlers.RotatingFileHandler:
    """Create the RotatingFileHandler for shadow JSONL output."""
    shadow_path = os.environ.get(
        "GATE_DAEMON_SHADOW_LOG",
        str(SCRIPT_DIR / "gate-daemon-shadow.jsonl"),
    )
    handler = logging.handlers.RotatingFileHandler(
        shadow_path,
        maxBytes=100 * 1024 * 1024,  # 100 MiB
        backupCount=5,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


_shadow_log = logging.getLogger("gate-daemon.shadow")


def _init_shadow_logger(handler: logging.handlers.RotatingFileHandler) -> None:
    _shadow_log.addHandler(handler)
    _shadow_log.setLevel(logging.INFO)
    _shadow_log.propagate = False


def _write_shadow(record: dict) -> None:
    """Append one JSON line to the shadow JSONL log."""
    _shadow_log.info(json.dumps(record, separators=(",", ":")))


def _get_origin_develop_sha(project_path: str) -> str | None:
    """Return current origin/develop sha for project_path, or None on error."""
    try:
        r = subprocess.run(
            ["git", "-C", project_path, "rev-parse", "origin/develop"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("rev-parse origin/develop failed for %s: %s", project_path, exc)
    return None


def _find_spec_path(project_dir: str, spec_id: str) -> Path | None:
    """Glob for spec markdown file in ai/features/."""
    pattern = str(Path(project_dir) / "ai" / "features" / f"{spec_id}*.md")
    matches = glob.glob(pattern)
    if matches:
        return Path(matches[0])
    return None


def _evaluate_project(
    project_id: str,
    project_path: str,
    cycle_count: int,
    cycle_start_ts: str,
) -> tuple[int, int, str | None]:
    """Evaluate all in_progress/queued specs for one project.

    Returns (specs_evaluated, verdicts_written, error_msg_or_None).
    """
    # Step 1: fetch origin/develop (aggressive 15s timeout).
    gate_logic.fetch_develop(project_path, timeout=15)

    # Step 2: SHA cache — skip per-spec git log if develop unchanged.
    new_sha = _get_origin_develop_sha(project_path)
    old_sha = _origin_develop_sha.get(project_id)
    sha_unchanged = new_sha is not None and new_sha == old_sha
    if new_sha is not None:
        _origin_develop_sha[project_id] = new_sha

    # Step 3: list in_progress and queued specs.
    try:
        specs = lifecycle.list_by_status(project_path, {"in_progress", "queued"})
    except Exception as exc:
        msg = f"list_by_status failed for {project_id}: {exc}"
        log.warning(msg)
        return 0, 0, msg

    as_of_ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    specs_evaluated = 0
    verdicts_written = 0

    for lc_data in specs:
        spec_id = lc_data.get("spec_id", "")
        if not spec_id:
            continue

        specs_evaluated += 1

        if sha_unchanged:
            _write_shadow(
                {
                    "cycle_start_ts": cycle_start_ts,
                    "as_of_ts": as_of_ts,
                    "project": project_id,
                    "spec_id": spec_id,
                    "gate_verdict": "skipped",
                    "gate_reason": "sha_unchanged",
                    "matching_commit_sha": None,
                    "allowed_files_count": 0,
                    "shadow_only": True,
                }
            )
            verdicts_written += 1
            continue

        spec_path = _find_spec_path(project_path, spec_id)
        if spec_path is None:
            _write_shadow(
                {
                    "cycle_start_ts": cycle_start_ts,
                    "as_of_ts": as_of_ts,
                    "project": project_id,
                    "spec_id": spec_id,
                    "gate_verdict": "blocked",
                    "gate_reason": "spec_file_not_found",
                    "matching_commit_sha": None,
                    "allowed_files_count": 0,
                    "shadow_only": True,
                }
            )
            verdicts_written += 1
            continue

        allowed = gate_logic.parse_allowed_files(spec_path)
        if allowed is None:
            _write_shadow(
                {
                    "cycle_start_ts": cycle_start_ts,
                    "as_of_ts": as_of_ts,
                    "project": project_id,
                    "spec_id": spec_id,
                    "gate_verdict": "blocked",
                    "gate_reason": "missing_allowed_files",
                    "matching_commit_sha": None,
                    "allowed_files_count": 0,
                    "shadow_only": True,
                }
            )
            verdicts_written += 1
            continue

        sha = gate_logic.find_implementation_commit(project_path, spec_id, allowed)
        if sha:
            verdict = "done"
            reason = f"subject_matched:{sha[:12]}"
        else:
            verdict = "in_progress"
            reason = "no_matching_commit"

        _write_shadow(
            {
                "cycle_start_ts": cycle_start_ts,
                "as_of_ts": as_of_ts,
                "project": project_id,
                "spec_id": spec_id,
                "gate_verdict": verdict,
                "gate_reason": reason,
                "matching_commit_sha": sha,
                "allowed_files_count": len(allowed),
                "shadow_only": True,
            }
        )
        verdicts_written += 1

    return specs_evaluated, verdicts_written, None


def _get_projects() -> list[dict]:
    """Load projects from PROJECTS_JSON (if set) or fall back to db.get_all_projects()."""
    projects_json = os.environ.get("PROJECTS_JSON", "")
    if projects_json and os.path.isfile(projects_json):
        try:
            with open(projects_json) as f:
                raw = json.load(f)
            result = []
            for p in raw:
                pid = p.get("id") or p.get("project_id", "")
                pdir = p.get("path", "")
                if pid and pdir:
                    result.append({"project_id": pid, "path": pdir})
            if result:
                return result
        except Exception as exc:
            log.warning("PROJECTS_JSON load failed %s: %s — fallback to db", projects_json, exc)
    return db.get_all_projects()


def main() -> None:
    """Main entry point — shadow polling loop."""
    _load_env()
    _setup_logging()

    # SHADOW_ONLY_MODE re-assert at process start (defense-in-depth).
    assert SHADOW_ONLY_MODE, "Wave 3 cutover not yet authorized"

    _write_pid()
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    poll_interval = int(os.environ.get("POLL_INTERVAL", "60"))
    shadow_handler = _make_shadow_handler()
    _init_shadow_logger(shadow_handler)

    log.info(
        "gate-daemon starting pid=%d poll=%ds shadow_only=%s",
        os.getpid(),
        poll_interval,
        SHADOW_ONLY_MODE,
    )

    cycle_count = 0

    while not _stop.is_set():
        cycle_start = time.monotonic()
        cycle_start_ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cycle_count += 1

        total_specs = 0
        total_verdicts = 0
        cycle_errors: list[str] = []

        try:
            projects = _get_projects()
        except Exception as exc:
            log.exception("cycle %d: failed to load projects", cycle_count)
            projects = []
            cycle_errors.append(str(exc))

        for proj in projects:
            if _stop.is_set():
                break
            pid = proj.get("project_id", "")
            pdir = proj.get("path", "")
            if not pid or not pdir:
                continue
            try:
                ev, vw, err = _evaluate_project(pid, pdir, cycle_count, cycle_start_ts)
                total_specs += ev
                total_verdicts += vw
                if err:
                    cycle_errors.append(err)
            except Exception as exc:
                log.warning("cycle %d project %s error: %s", cycle_count, pid, exc)
                cycle_errors.append(f"{pid}: {exc}")

        # Post-cycle: write gate_health row + heartbeat.
        error_summary = "; ".join(cycle_errors[:5]) if cycle_errors else None
        try:
            db.log_gate_cycle(
                cycle_count=cycle_count,
                last_poll_at=cycle_start_ts,
                in_progress_specs=total_specs,
                decisions_this_cycle=total_verdicts,
                error_msg=error_summary,
            )
        except (sqlite3.Error, OSError):
            log.exception("cycle %d: log_gate_cycle failed", cycle_count)

        try:
            ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            (SCRIPT_DIR / ".gate-daemon-heartbeat").write_text(ts)
        except OSError:
            log.warning("heartbeat write failed")

        elapsed = time.monotonic() - cycle_start
        log.info(
            "cycle=%d evaluated=%d projects=%d duration=%.1fs",
            cycle_count,
            total_verdicts,
            len(projects),
            elapsed,
        )

        _stop.wait(max(0.0, poll_interval - elapsed))

    log.info("gate-daemon stopped")


if __name__ == "__main__":
    main()
