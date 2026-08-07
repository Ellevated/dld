#!/usr/bin/env python3
"""
Module: orchestrator
Role: Main poll loop daemon — scan inbox, scan queued lifecycle, dispatch via pueue.
Uses: db (import), lifecycle (import), subprocess (pueue CLI), signal, threading
Used by: systemd (dld-orchestrator.service)

Replaces orchestrator.sh + inbox-processor.sh (ARCH-161).
Post-ARCH-186: reads task queue from ai/lifecycle/*.yaml (not ai/backlog.md).
"""

# ruff: noqa: I001
# Import order here is load-bearing, not stylistic: the sys.path bootstrap must
# run before the sibling imports, and the facade re-export block at the bottom
# must stay at the bottom (see the TECH-215 comment there). Auto-sorting either
# block breaks the module.

import atexit
import logging
import logging.handlers
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402

# gate_logic is not called from this module any more (the reconciliation step
# moved to orchestrator_queue), but the import is load-bearing: eight sites in
# test_orchestrator.py do patch.object(orchestrator.gate_logic, ...), which
# works by mutating the shared module object. Deleting this as a "dead import"
# breaks those eight tests. TECH-215.
import gate_logic  # noqa: E402,F401
import lifecycle  # noqa: E402
import orchestrator_queue  # noqa: E402

log = logging.getLogger("orchestrator")
_stop = Event()


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
        os.path.join(log_dir, "orchestrator.log"), when="midnight", backupCount=7, utc=True
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
    pid_file = SCRIPT_DIR / ".orchestrator.pid"
    pid_file.write_text(str(os.getpid()))
    atexit.register(lambda: pid_file.unlink(missing_ok=True))


def git_pull(project_id: str, project_dir: str) -> None:
    """Advance develop via fetch + ff-only merge. Skip cycle if not fast-forward.

    Post-ARCH-186: no autostash, no stash pop, no marker restore. The
    no-dirty-WT invariant (assert_clean_lifecycle_tree at startup +
    structural impossibility from lifecycle.py atomic plumbing) means
    the WT is always clean when this runs. If the merge fails (e.g. divergence),
    skip the cycle and log — operator will resolve.

    Uses `fetch` + `merge --ff-only origin/develop` rather than
    `pull --ff-only origin develop`: the latter merges from the shared,
    non-atomic .git/FETCH_HEAD, which races with the gate-daemon's concurrent
    `git fetch` and intermittently dies "Cannot fast-forward to multiple
    branches". Merging from the tracking ref is immune to that race.
    """
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return
    if is_agent_running(project_id):
        log.info("skip git pull — agent running: %s", project_id)
        return
    try:
        # FETCH_HEAD-race fix: gate-daemon (git fetch, 60s) and orchestrator
        # (here) both touch the shared, non-atomic .git/FETCH_HEAD. Plain
        # `git pull origin develop` resolves its merge head from FETCH_HEAD, so
        # a concurrent fetch can inject a second for-merge entry →
        # "Cannot fast-forward to multiple branches". Fetch, then merge from the
        # atomically-updated tracking ref (origin/develop) — never FETCH_HEAD —
        # which can only ever point at a single commit.
        fetch = subprocess.run(
            ["git", "-C", project_dir, "fetch", "--quiet", "origin", "develop"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if fetch.returncode != 0:
            log.warning(
                "git fetch failed for %s: %s — skip cycle",
                project_dir,
                (fetch.stderr or "")[:200],
            )
            return
        merge = subprocess.run(
            ["git", "-C", project_dir, "merge", "--ff-only", "origin/develop"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if merge.returncode != 0:
            log.warning(
                "git merge --ff-only origin/develop failed for %s: %s — skip cycle",
                project_dir,
                (merge.stderr or "")[:200],
            )
    except subprocess.TimeoutExpired as exc:
        log.warning("git_pull timeout for %s: %s", project_dir, exc)


def startup_reconcile() -> None:
    """One-shot at daemon boot: assert clean lifecycle WT + reconcile orphans.

    For every project, abort if ai/lifecycle/ working-tree is dirty (uncommitted
    drift = data loss risk). Then demote any in_progress lifecycle whose
    pueue_id is not alive (crash recovery). Fail-closed: if pueue status is
    unavailable, orphan reconciliation is skipped for all projects (integrity
    checks still run) rather than demoting every live spec.
    """
    # get_live_pueue_ids returns None on failure and an empty set when pueue is
    # genuinely idle — the distinction is the whole point of its contract. Folding
    # None into set() (`or set()`, until BUG-218) made an unreachable pueue look
    # like "nothing is running", which demotes every live spec. Harmless while
    # nothing was ever in_progress; a mass-demote of running work now that specs
    # actually reach that status.
    alive = get_live_pueue_ids()
    if alive is None:
        log.warning("startup_reconcile: pueue status unavailable — skipping orphan reconciliation")
    for proj in db.get_all_projects():
        pdir = proj["path"]
        if not os.path.isdir(os.path.join(pdir, "ai", "lifecycle")):
            continue
        cleanup_stale_stashes(pdir)
        lifecycle.assert_clean_lifecycle_tree(pdir)  # raises on dirty
        if alive is None:
            continue
        reconciled = lifecycle.reconcile_orphans(pdir, alive)
        if reconciled:
            log.warning(
                "startup_reconcile: demoted %d orphans in %s: %s",
                len(reconciled),
                proj["project_id"],
                reconciled,
            )


def _select_dispatchable_spec(project_dir: str, queued_list: list) -> str | None:
    """BUG-206: first queued/resumed spec with no unmet `AFTER <ID>` dependency.

    Extracted for EC-8 (scan_queued length), but kept in orchestrator.py rather
    than orchestrator_queue.py: 13 tests patch `orchestrator._unmet_dependencies`,
    which resolves bare-name only against THIS module's globals. A sibling
    calling the same bare name would look it up in its own `__dict__` first and
    silently miss the patch (Python docs, "Where to patch").
    """
    for cand in queued_list:
        cid = cand["spec_id"]
        unmet = _unmet_dependencies(project_dir, cid)
        if unmet:
            log.info("DEP_GATE: skip %s — unmet dependency %s (not done)", cid, ", ".join(unmet))
            continue
        return cid
    return None


def scan_queued(project_id: str, project_dir: str) -> bool:
    """Find first queued/resumed spec via lifecycle.yaml and dispatch autopilot.

    Returns True if dispatched. Post-ARCH-186: reads ai/lifecycle/*.yaml
    (HEAD-based), not ai/backlog.md (which is now an auto-rendered read-only view).

    The body stays in this module on purpose (TECH-215): four test files reach
    into it through `orchestrator.<name>` monkeypatches or by grepping this
    file's source, and none of them are editable under this spec's Allowed
    Files. Steps with no such coupling live in orchestrator_queue.
    """
    queued_list = lifecycle.list_by_status(project_dir, {"queued", "resumed"})
    if not queued_list:
        return False

    spec_id = _select_dispatchable_spec(project_dir, queued_list)
    if spec_id is None:
        return False

    gate = orchestrator_queue.gate_before_pueue_add(
        project_id, project_dir, spec_id, SCRIPT_DIR / "callback-audit.jsonl"
    )
    if gate is None:
        return False
    spec_files, provider = gate

    task_label = f"{project_id}:{spec_id}"
    if pueue_has_active_label(task_label):
        log.info("skip dispatch: %s already in pueue", task_label)
        return False
    if pueue_has_active_spec(spec_id):
        log.info("skip dispatch: %s live in pueue under another project (Rule 8)", spec_id)
        return False

    # BUG-199: pin spec path for the pre-edit hook's Allowed Files enforcement.
    # Without this, inferSpecFromBranch() returns null on develop after
    # merge-back, and the hook degrades OPEN — allowing out-of-scope edits.
    spec_path = str(spec_files[0])
    pueue_env = {"CLAUDE_PROJECT_DIR": project_dir, "CLAUDE_CURRENT_SPEC_PATH": spec_path}

    if not orchestrator_queue.status_still_dispatchable(project_dir, spec_id):
        return False
    if orchestrator_queue.reconcile_if_implemented(project_dir, spec_id, spec_files[0]):
        return False

    pueue_id = _pueue_add(
        f"{provider}-runner",
        task_label,
        [
            str(SCRIPT_DIR / "run-agent.sh"),
            project_dir,
            provider,
            "autopilot",
            f"/autopilot {spec_id}",
        ],
        env=pueue_env,
    )
    if pueue_id is None:
        log.error("pueue submission failed: %s/%s", project_id, spec_id)
        return False

    orchestrator_queue.record_dispatch(
        project_id, project_dir, spec_id, provider, task_label, pueue_id
    )
    log.info("autopilot submitted: %s spec=%s pueue_id=%d", project_id, spec_id, pueue_id)
    return True


def process_project(project_id: str, project_dir: str) -> None:
    """Process one project: git pull, inbox, lifecycle bootstrap, queued scan, invariant check."""
    git_pull(project_id, project_dir)
    scan_inbox(project_id, project_dir)
    bootstrap_new_specs(project_dir)
    scan_queued(project_id, project_dir)
    state = db.get_project_state(project_id)
    if state and state.get("phase") == "qa_pending" and not state.get("current_task"):
        log.warning("qa_pending invariant: resetting %s to idle", project_id)
        db.update_project_phase(project_id, "idle", None)


MIN_CYCLE_SLEEP = 30  # floor (s): a pass slower than the window must not busy-loop git


def _next_sleep(poll_interval: float, pass_elapsed: float) -> float:
    """Remaining poll window after a pass that took pass_elapsed seconds.

    Keeps the cycle PERIOD at poll_interval rather than poll_interval + pass
    time. The old flat sleep-after-pass pushed the real period to ~7-8 min
    (300s sleep + ~3 min pass over 10 projects), so a queued spec that landed
    just after its project's turn waited a whole extra pass before dispatch.
    Floored at MIN_CYCLE_SLEEP so a pass slower than the window can't hammer git
    in a tight loop.
    """
    return max(float(MIN_CYCLE_SLEEP), poll_interval - pass_elapsed)


def main() -> None:
    """Main entry point — poll loop."""
    _load_env()
    _setup_logging()
    _write_pid()
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    poll_interval = int(os.environ.get("POLL_INTERVAL", "300"))
    log.info("orchestrator starting pid=%d poll=%ds", os.getpid(), poll_interval)

    try:
        sync_projects()  # ensure projects in DB before reconcile
        startup_reconcile()
    except Exception:
        log.exception("startup_reconcile FATAL — aborting daemon")
        return

    while not _stop.is_set():
        cycle_start = time.monotonic()
        try:
            release_orphan_slots()  # BUG-162: clean stale slots before dispatch
            sync_projects()
            dispatch_night_review()
            for proj in db.get_all_projects():
                if _stop.is_set():
                    break
                pid, pdir = proj["project_id"], proj["path"]
                trigger = SCRIPT_DIR / f".run-now-{pid}"
                if trigger.is_file():
                    trigger.unlink(missing_ok=True)
                    log.info("run-now trigger: %s", pid)
                process_project(pid, pdir)
        except Exception:
            log.exception("cycle error")
        # TECH-189 Task 8: heartbeat — external monitor reads this file.
        try:
            ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            (SCRIPT_DIR / ".orchestrator-heartbeat").write_text(ts)
        except Exception:  # noqa: BLE001
            log.warning("heartbeat write failed")
        # Pace by PERIOD, not delay-after-pass: subtract how long the pass took
        # so passes recur every poll_interval (intended 5 min) instead of
        # poll_interval + pass_duration (~7-8 min).
        pass_elapsed = time.monotonic() - cycle_start
        sleep_for = _next_sleep(poll_interval, pass_elapsed)
        log.info(
            "cycle complete in %.0fs, sleeping %.0fs (period target %ds)",
            pass_elapsed,
            sleep_for,
            poll_interval,
        )
        _stop.wait(sleep_for)

    log.info("orchestrator stopped")


# ---------------------------------------------------------------------------
# TECH-215: facade re-exports. Form `from X import Y` is required, not
# stylistic — tests patch `orchestrator.<name>`, and functions remaining in
# this file resolve names in THIS module's dict. Attribute access
# (`orchestrator_slots.f()`) would not be visible to those patches.
# ---------------------------------------------------------------------------
from orchestrator_slots import (  # noqa: F401,E402
    _LIVE_PUEUE_STATES,
    _pueue_add,
    get_live_pueue_ids,
    is_agent_running,
    pueue_has_active_label,
    pueue_has_active_spec,
    release_orphan_slots,
    sync_projects,
)
from orchestrator_backlog import (  # noqa: F401,E402
    BOOTSTRAP_ANOMALY_THRESHOLD,
    _bump_unparsable_counter,
    _parse_backlog,
    _parse_priority_kind,
    bootstrap_new_specs,
    cleanup_stale_stashes,
)
from orchestrator_inbox import (  # noqa: F401,E402
    _ROUTE_SKILL_MAP,
    _parse_inbox_file,
    scan_inbox,
)
from orchestrator_queue import (  # noqa: F401,E402
    _AFTER_DEP_RE,
    _backlog_deps,
    _unmet_dependencies,
    dispatch_night_review,
)


if __name__ == "__main__":
    main()
