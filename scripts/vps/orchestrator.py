#!/usr/bin/env python3
"""
Module: orchestrator
Role: Main poll loop daemon — scan inbox, scan queued lifecycle, dispatch via pueue.
Uses: db (import), lifecycle (import), subprocess (pueue CLI), signal, threading
Used by: systemd (dld-orchestrator.service)

Replaces orchestrator.sh + inbox-processor.sh (ARCH-161).
Post-ARCH-186: reads task queue from ai/lifecycle/*.yaml (not ai/backlog.md).
"""

import atexit
import json
import logging
import logging.handlers
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import lifecycle  # noqa: E402

log = logging.getLogger("orchestrator")
_stop = Event()
_projects_mtime: float = 0.0


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


def sync_projects() -> None:
    """Hot-reload projects.json into SQLite when mtime changes."""
    global _projects_mtime
    projects_json = os.environ.get("PROJECTS_JSON", str(SCRIPT_DIR / "projects.json"))
    if not os.path.isfile(projects_json):
        log.warning("projects.json not found: %s", projects_json)
        return
    mtime = os.path.getmtime(projects_json)
    if mtime == _projects_mtime:
        return
    _projects_mtime = mtime
    with open(projects_json) as f:
        projects = json.load(f)
    db.seed_projects_from_json(projects)
    log.info("synced %d projects from %s", len(projects), projects_json)


_LIVE_PUEUE_STATES = frozenset({"Running", "Locked", "Queued", "Stashed", "Paused"})

# TECH-189 Task 4: bootstrap_new_specs anomaly detector.
# Normal cycles create 0-1 lifecycle yamls. >3 in one cycle = anomaly
# (backlog-write race, bulk import, etc). Today's incident (2026-05-23)
# created 15 in one cycle and burned ~$258 on retries.
BOOTSTRAP_ANOMALY_THRESHOLD = 3


def get_live_pueue_ids() -> set[int] | None:
    """Return live pueue task IDs. None on failure (skip watchdog, no false release).

    Modern pueue versions return `status` as a dict like `{"Queued": {...}}` or
    `{"Running": {...}}`. Older versions may return a bare string. We handle both.
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            log.warning("pueue status exit %d: %s", r.returncode, r.stderr[:200])
            return None
        data = json.loads(r.stdout)
        live: set[int] = set()
        for tid_str, task in data.get("tasks", {}).items():
            st = task.get("status", "")
            state_name: str = ""
            if isinstance(st, dict):
                state_name = next(iter(st.keys()), "")
            elif isinstance(st, str):
                state_name = st
            if state_name in _LIVE_PUEUE_STATES:
                live.add(int(tid_str))
        return live
    except Exception as exc:
        log.warning("get_live_pueue_ids failed: %s", exc)
        return None


def pueue_has_active_label(label: str) -> bool:
    """Return True if pueue already has a Running/Queued task with this label.

    Belt-and-suspenders guard against duplicate dispatch — even if the slot
    table is stale or out-of-sync, this catches the dup at the pueue layer.
    On failure returns False (fail-open — better to risk a duplicate than
    block all dispatches).
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        for _tid, task in data.get("tasks", {}).items():
            if task.get("label") != label:
                continue
            st = task.get("status", "")
            state_name = next(iter(st.keys()), "") if isinstance(st, dict) else st
            if state_name in _LIVE_PUEUE_STATES:
                return True
        return False
    except Exception as exc:
        log.warning("pueue_has_active_label check failed: %s", exc)
        return False


def pueue_has_active_spec(spec_id: str) -> bool:
    """Rule 8: True if any live pueue task has label ending with ':<spec_id>' (any project).

    Prevents cross-project double-dispatch of the same spec_id.
    Fail-open (returns False) so a pueue outage doesn't block all dispatches.
    """
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        suffix = f":{spec_id}"
        for _tid, task in data.get("tasks", {}).items():
            label = task.get("label", "")
            if not label.endswith(suffix):
                continue
            st = task.get("status", "")
            state_name = next(iter(st.keys()), "") if isinstance(st, dict) else st
            if state_name in _LIVE_PUEUE_STATES:
                return True
        return False
    except Exception as exc:
        log.warning("pueue_has_active_spec check failed: %s", exc)
        return False


def release_orphan_slots() -> int:
    """Release slots whose pueue tasks are gone. 0 if pueue unreachable (BUG-162)."""
    live_ids = get_live_pueue_ids()
    if live_ids is None:
        return 0
    occupied = db.get_occupied_slots()
    if not occupied:
        return 0
    released = 0
    for slot in occupied:
        pueue_id = slot["pueue_id"]
        if pueue_id not in live_ids:
            pid = db.release_slot(pueue_id)
            log.warning(
                "watchdog: released orphan slot=%d project=%s pueue_id=%d acquired_at=%s",
                slot["slot_number"],
                pid or slot.get("project_id"),
                pueue_id,
                slot.get("acquired_at", "unknown"),
            )
            released += 1
    if released:
        log.info("watchdog: released %d orphan slot(s) total", released)
    return released


def is_agent_running(project_id: str) -> bool:
    """Return True if a pueue task with this project's label prefix is Running."""
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(r.stdout)
        for task in data.get("tasks", {}).values():
            label = task.get("label", "")
            status = task.get("status", "")
            if (
                label.startswith(f"{project_id}:")
                and isinstance(status, dict)
                and "Running" in status
            ):
                return True
    except Exception:
        pass
    return False


def git_pull(project_id: str, project_dir: str) -> None:
    """Pull develop branch via ff-only. Skip cycle if not fast-forward.

    Post-ARCH-186: no autostash, no stash pop, no marker restore. The
    no-dirty-WT invariant (assert_clean_lifecycle_tree at startup +
    structural impossibility from lifecycle.py atomic plumbing) means
    the WT is always clean when this runs. If pull fails (e.g. divergence),
    skip the cycle and log — operator will resolve.
    """
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return
    if is_agent_running(project_id):
        log.info("skip git pull — agent running: %s", project_id)
        return
    try:
        pull = subprocess.run(
            ["git", "-C", project_dir, "pull", "--ff-only", "origin", "develop"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if pull.returncode != 0:
            log.warning(
                "git pull (ff-only) failed for %s: %s — skip cycle",
                project_dir,
                (pull.stderr or "")[:200],
            )
    except subprocess.TimeoutExpired as exc:
        log.warning("git_pull timeout for %s: %s", project_dir, exc)


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
    backlog_path = Path(project_dir) / "ai" / "backlog.md"
    if not backlog_path.is_file():
        return
    backlog_text = backlog_path.read_text(errors="replace")
    # Active backlog rows: | ID | desc | status | priority | spec |
    # Archive rows after "## ✅ DONE" header: | ID | desc | spec | (3 cols, implied done)
    active_re = re.compile(
        r"^\|\s*(?P<id>(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*)\s*\|"
        r"[^|]+\|\s*(?P<status>queued|in_progress|blocked|done|resumed|draft)\s*\|",
        re.MULTILINE,
    )
    active_status = {m.group("id"): m.group("status") for m in active_re.finditer(backlog_text)}
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
        #   - in backlog but archive/malformed → 'done' (historical, never dispatch)
        status = active_status.get(spec_id, "done")
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

    if created_count > BOOTSTRAP_ANOMALY_THRESHOLD:
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


def startup_reconcile() -> None:
    """One-shot at daemon boot: assert clean lifecycle WT + reconcile orphans.

    For every project, abort if ai/lifecycle/ working-tree is dirty (uncommitted
    drift = data loss risk). Then demote any in_progress lifecycle whose
    pueue_id is not alive (crash recovery).
    """
    alive = get_live_pueue_ids() or set()
    for proj in db.get_all_projects():
        pdir = proj["path"]
        if not os.path.isdir(os.path.join(pdir, "ai", "lifecycle")):
            continue
        lifecycle.assert_clean_lifecycle_tree(pdir)  # raises on dirty
        reconciled = lifecycle.reconcile_orphans(pdir, alive)
        if reconciled:
            log.warning(
                "startup_reconcile: demoted %d orphans in %s: %s",
                len(reconciled),
                proj["project_id"],
                reconciled,
            )


def _parse_inbox_file(filepath: Path) -> dict:
    """Extract route/source/provider/context/idea_text from inbox markdown."""
    lines = filepath.read_text(errors="replace").splitlines()

    def extract(key: str, default: str = "") -> str:
        for ln in lines:
            m = re.match(rf"^\*\*{key}:\*\*\s+(.+)", ln)
            if m:
                return m.group(1).strip()
        return default

    idea_lines, in_body = [], False
    for ln in lines:
        if ln.strip() == "---":
            in_body = True
        elif in_body:
            idea_lines.append(ln)
            if len(idea_lines) >= 50:
                break
    idea_text = " ".join(idea_lines).strip()
    if not idea_text:
        idea_text = " ".join(
            ln
            for ln in lines[:20]
            if not re.match(r"^\*\*(Source|Route|Status|Context|Provider|Project):\*\*|^#", ln)
        ).strip()
    return {
        "route": extract("Route", "spark"),
        "source": extract("Source", "openclaw"),
        "provider": extract("Provider", ""),
        "context": extract("Context", ""),
        "idea_text": idea_text,
    }


_ROUTE_SKILL_MAP = {
    "spark": "spark",
    "architect": "architect",
    "council": "council",
    "spark_bug": "spark",
    "bughunt": "bughunt",
    "qa": "qa",
    "reflect": "reflect",
    "scout": "scout",
}


def _pueue_add(group: str, label: str, cmd: list, env: dict | None = None) -> int | None:
    """Submit task to pueue group. Returns pueue task ID or None."""
    pueue_cmd = ["pueue", "add", "--group", group, "--label", label, "--print-task-id", "--"] + cmd
    run_env = {**os.environ, **env} if env else None
    try:
        r = subprocess.run(pueue_cmd, capture_output=True, text=True, timeout=30, env=run_env)
        for ln in r.stdout.strip().splitlines():
            ln = ln.strip()
            if ln.isdigit():
                return int(ln)
            m = re.search(r"(\d+)", ln)
            if m:
                return int(m.group(1))
        log.warning("pueue add: no task ID in output: %s", r.stdout[:200])
    except Exception as exc:
        log.error("pueue add failed: %s", exc)
    return None


def scan_inbox(project_id: str, project_dir: str) -> int:
    """Scan ai/inbox/ for Status: queued files (Hermes-promoted), dispatch each via pueue.

    TECH-181: status gate — only files explicitly promoted by Hermes to `queued`
    are dispatched. Legacy `new`, `draft`, `clarifying`, `stale`, `rejected` are
    ignored. Clean break, no auto-migration (see spec rationale).
    """
    inbox_dir = Path(project_dir) / "ai" / "inbox"
    if not inbox_dir.is_dir():
        return 0

    _inbox_queued_re = re.compile(r"\*\*Status:\*\*\s*queued", re.IGNORECASE)

    count = 0
    for inbox_file in sorted(inbox_dir.glob("*.md")):
        text = inbox_file.read_text(errors="replace")
        if not _inbox_queued_re.search(text):
            continue

        log.info("processing inbox: %s/%s", project_id, inbox_file.name)
        meta = _parse_inbox_file(inbox_file)
        skill = _ROUTE_SKILL_MAP.get(meta["route"], "spark")

        text = _inbox_queued_re.sub("**Status:** processing", text)
        inbox_file.write_text(text)
        done_dir = inbox_dir / "done"
        done_dir.mkdir(exist_ok=True)
        done_file = done_dir / inbox_file.name
        inbox_file.rename(done_file)
        provider = meta["provider"]
        if not provider:
            state = db.get_project_state(project_id)
            provider = (state["provider"] if state else None) or "claude"
        headless = f"[headless] Source: {meta['source']}."
        if meta["context"]:
            headless += f" Context: {meta['context']}."
        headless += f" {meta['idea_text']}"
        task_cmd = f"/{skill} {headless}"
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        task_file = SCRIPT_DIR / f".task-cmd-{ts}.txt"
        task_file.write_text(task_cmd)
        task_label = f"{project_id}:inbox-{ts}"
        if pueue_has_active_label(task_label):
            log.info("skip inbox dispatch: %s already in pueue", task_label)
            continue
        pueue_env = {"CLAUDE_PROJECT_DIR": project_dir, "CLAUDE_CURRENT_SPEC_PATH": str(done_file)}
        pueue_id = _pueue_add(
            f"{provider}-runner",
            task_label,
            [str(SCRIPT_DIR / "run-agent.sh"), project_dir, provider, skill, str(task_file)],
            env=pueue_env,
        )
        if pueue_id is not None:
            db.try_acquire_slot(project_id, provider, pueue_id)
            db.log_task(project_id, task_label, skill, "queued", pueue_id)
            db.update_project_phase(project_id, "processing_inbox", task_label)
            log.info("inbox dispatched: %s label=%s pueue_id=%d", project_id, task_label, pueue_id)
        else:
            log.error("inbox dispatch failed: %s/%s", project_id, inbox_file.name)
        count += 1
    return count


def scan_queued(project_id: str, project_dir: str) -> bool:
    """Find first queued/resumed spec via lifecycle.yaml and dispatch autopilot.

    Returns True if dispatched. Post-ARCH-186: reads ai/lifecycle/*.yaml
    (HEAD-based), not ai/backlog.md (which is now an auto-rendered read-only view).
    """
    queued_list = lifecycle.list_by_status(project_dir, {"queued", "resumed"})
    if not queued_list:
        return False

    # First match wins. (Priority sorting can be layered later; current
    # backlog.md picked first textual match too.)
    spec_id = queued_list[0]["spec_id"]

    # Skip dispatch if this spec was recently processed — avoids re-dispatch loops.
    # - blocked in last 30 min: guard demoted it, needs human intervention
    # - done in last 5 min: callback just wrote done but git pull may have pulled stale queued
    audit_log = SCRIPT_DIR / "callback-audit.jsonl"
    if audit_log.is_file():
        now = datetime.now(tz=timezone.utc).timestamp()
        cutoff_blocked = now - 30 * 60
        cutoff_done = now - 5 * 60
        try:
            for raw in audit_log.read_text().splitlines()[-200:]:
                entry = json.loads(raw)
                if entry.get("spec_id") != spec_id:
                    continue
                ts_str = entry.get("ts", "")
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                target_out = entry.get("target_out")
                reason = entry.get("reason", "")
                if target_out == "blocked" and reason != "fixed" and ts > cutoff_blocked:
                    log.info("skip dispatch: %s demoted recently (%s)", spec_id, reason)
                    return False
                if target_out == "done" and ts > cutoff_done:
                    log.info("skip dispatch: %s completed recently (%s)", spec_id, reason)
                    return False
        except Exception:
            pass

    state = db.get_project_state(project_id)
    provider = (state["provider"] if state else None) or "claude"

    features_dir = Path(project_dir) / "ai" / "features"
    spec_files = list(features_dir.glob(f"{spec_id}*"))
    if spec_files:
        m = re.search(
            r"^provider:\s+(\w+)", spec_files[0].read_text(errors="replace"), re.MULTILINE
        )
        if m and db.get_available_slots(m.group(1)) >= 0:
            provider = m.group(1)

    if db.get_available_slots(provider) < 1:
        log.info("no slots for %s provider=%s", project_id, provider)
        return False

    task_label = f"{project_id}:{spec_id}"
    if pueue_has_active_label(task_label):
        log.info("skip dispatch: %s already in pueue", task_label)
        return False
    if pueue_has_active_spec(spec_id):
        log.info("skip dispatch: %s live in pueue under another project (Rule 8)", spec_id)
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
    )
    if pueue_id is None:
        log.error("pueue submission failed: %s/%s", project_id, spec_id)
        return False

    db.try_acquire_slot(project_id, provider, pueue_id)
    db.log_task(
        project_id,
        task_label,
        "autopilot",
        "running",
        pueue_id,
        branch=f"feature/{spec_id}",
    )
    db.update_project_phase(project_id, "autopilot", spec_id)
    log.info("autopilot submitted: %s spec=%s pueue_id=%d", project_id, spec_id, pueue_id)
    return True


def dispatch_night_review() -> None:
    """Check .review-trigger and dispatch night reviewer if present."""
    trigger = SCRIPT_DIR / ".review-trigger"
    if not trigger.is_file():
        return
    project_ids = trigger.read_text().strip()
    trigger.unlink(missing_ok=True)
    if not project_ids:
        return
    log.info("dispatching night review: %s", project_ids)
    _pueue_add(
        "night-reviewer",
        "night-review",
        [str(SCRIPT_DIR / "night-reviewer.sh")] + project_ids.split(),
    )


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
        log.info("cycle complete, sleeping %ds", poll_interval)
        _stop.wait(poll_interval)

    log.info("orchestrator stopped")


if __name__ == "__main__":
    main()
