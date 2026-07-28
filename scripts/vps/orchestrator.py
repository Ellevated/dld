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
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import gate_logic  # noqa: E402
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
        cleanup_stale_stashes(pdir)
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


# BUG-206: dependency-aware dispatch. Specs declare ordering with an
# "AFTER <SPEC-ID>" marker in their backlog row (the uniform place this
# convention lives — spec prose is too noisy to parse reliably). scan_queued
# must not dispatch a spec whose declared dependency is not yet done, or the
# autopilot burns a full run self-blocking on the unmet prerequisite
# (ARCH-1246/FTR-1245 vs the still-queued TECH-1244, awardybot 2026-06-20).
# Dependency EDGE comes from the backlog; dependency STATUS from the lifecycle SoT.
_AFTER_DEP_RE = re.compile(r"\bafter\s+([A-Z]{2,5}-\d+)", re.IGNORECASE)


def _backlog_deps(project_dir: str, spec_id: str) -> set:
    """Declared 'AFTER <ID>' dependencies for spec_id, read from its backlog row.

    Returns an empty set when the backlog, the row, or the marker is absent —
    conservative by design: a missing marker means no gate, never a stall.
    """
    backlog = Path(project_dir) / "ai" / "backlog.md"
    if not backlog.is_file():
        return set()
    row_re = re.compile(rf"^\s*\|\s*{re.escape(spec_id)}\s*\|")
    try:
        for line in backlog.read_text(errors="replace").splitlines():
            if row_re.match(line):
                deps = {m.group(1).upper() for m in _AFTER_DEP_RE.finditer(line)}
                deps.discard(spec_id)
                return deps
    except OSError:
        pass
    return set()


def _unmet_dependencies(project_dir: str, spec_id: str) -> list:
    """Subset of spec_id's declared deps whose lifecycle status is not 'done'.

    A dependency absent from lifecycle is treated as MET — avoids a permanent
    stall on a stale/archived reference. Prefer a false-negative (dispatch, then
    the autopilot self-blocks and is correctly labeled by callback) over a
    false-positive (a spec that silently never dispatches).
    """
    unmet = []
    for dep in sorted(_backlog_deps(project_dir, spec_id)):
        dep_lc = lifecycle.read_lifecycle(project_dir, dep)
        if dep_lc and dep_lc.get("status") != "done":
            unmet.append(dep)
    return unmet


def scan_queued(project_id: str, project_dir: str) -> bool:
    """Find first queued/resumed spec via lifecycle.yaml and dispatch autopilot.

    Returns True if dispatched. Post-ARCH-186: reads ai/lifecycle/*.yaml
    (HEAD-based), not ai/backlog.md (which is now an auto-rendered read-only view).
    """
    queued_list = lifecycle.list_by_status(project_dir, {"queued", "resumed"})
    if not queued_list:
        return False

    # BUG-206: dependency-aware selection. Pick the first queued/resumed spec
    # whose declared "AFTER <ID>" dependencies are all done. Skipping a
    # dep-unmet spec (instead of dispatching it) prevents the autopilot from
    # burning a full run self-blocking on an unmet prerequisite. Specs without a
    # marker, or whose deps are all done, dispatch as before (first match wins).
    spec_id = None
    for cand in queued_list:
        cid = cand["spec_id"]
        unmet = _unmet_dependencies(project_dir, cid)
        if unmet:
            log.info("DEP_GATE: skip %s — unmet dependency %s (not done)", cid, ", ".join(unmet))
            continue
        spec_id = cid
        break
    if spec_id is None:
        return False

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

    # SPEC-READINESS GATE (2026-07-26). Spec-first ID CAS (ARCH-196/ADR-027) has
    # spark claim the ID through create_initial() — which writes status=queued and
    # pushes — minutes before the spec body itself is written and committed. This
    # orchestrator polls every ~60s, so an interactive spark run reliably loses the
    # race: we dispatch, the session finds no spec, and callback blocks it with
    # missing_allowed_files. Observed on awardybot BUG-1410 (pueue 995, dead in 18s).
    #
    # A queued lifecycle row with no spec body on disk is never dispatchable, so
    # skip the cycle instead of burning a slot and a session. The row is left at
    # queued: once spark commits the body, the next cycle picks it up normally.
    # A row that stays here forever is an orphan, not a race — lifecycle_audit.py
    # reports that case.
    if not spec_files:
        log.info(
            "skip dispatch: %s queued but no spec body in ai/features/ yet "
            "(spec-first ID claim not finished; orphan if it persists)",
            spec_id,
        )
        return False

    # Provider selection. Claude runs everything by default; a spec may name a
    # different provider, which is treated as a deliberate request rather than a
    # hint — so a busy provider makes the spec wait rather than silently running
    # somewhere else.
    #
    # The old condition was `get_available_slots(requested) >= 0`, and COUNT(*) is
    # never negative, so the spec's provider always won — including when it named
    # a provider with no slots configured at all (a typo, or a runner that was
    # never installed). Capacity 0 then failed the check below every cycle, and
    # the spec sat queued forever under a log line reading "no slots".
    m = re.search(r"^provider:\s+(\w+)", spec_files[0].read_text(errors="replace"), re.MULTILINE)
    if m:
        requested = m.group(1)
        if db.get_provider_capacity(requested) > 0:
            provider = requested
        else:
            log.warning(
                "spec %s requests provider=%s which has no slots configured — falling back to %s",
                spec_id,
                requested,
                provider,
            )

    if db.get_available_slots(provider) < 1:
        log.info("no slots for %s provider=%s (busy)", project_id, provider)
        return False

    task_label = f"{project_id}:{spec_id}"
    if pueue_has_active_label(task_label):
        log.info("skip dispatch: %s already in pueue", task_label)
        return False
    if pueue_has_active_spec(spec_id):
        log.info("skip dispatch: %s live in pueue under another project (Rule 8)", spec_id)
        return False
    # BUG-199: pin spec path for the pre-edit hook's Allowed Files enforcement.
    # Without this, inferSpecFromBranch() returns null on develop after merge-back,
    # and the hook degrades open — allowing out-of-scope edits.
    spec_path = str(spec_files[0])
    pueue_env = {"CLAUDE_PROJECT_DIR": project_dir, "CLAUDE_CURRENT_SPEC_PATH": spec_path}
    # BUG-205: authoritative TOCTOU re-check.  The list_by_status() snapshot
    # (top of scan_queued) can go stale before we actually dispatch: callback
    # runs as a SEPARATE process and may have written blocked/done for this
    # spec via git plumbing, and git_pull is skipped while an agent is running
    # (stale local HEAD).  The callback-audit.jsonl guard above is node-local +
    # time-windowed, NOT authoritative.  Re-read the lifecycle SoT (HEAD) for
    # THIS spec right before pueue add; abort if it is no longer dispatchable.
    fresh = lifecycle.read_lifecycle(project_dir, spec_id)
    fresh_status = fresh.get("status") if fresh else None
    if fresh_status not in ("queued", "resumed"):
        log.info(
            "skip dispatch: %s status changed to %s after scan (TOCTOU re-check)",
            spec_id,
            fresh_status,
        )
        return False
    # RECONCILIATION GATE: a queued spec may already be implemented on
    # origin/develop — work landed via another developer, another window,
    # another node, or an autopilot session whose callback never fired. The
    # single-writer model (ADR-023) only updates status through callback on THIS
    # orchestrator's pueue completions, so out-of-band work leaves the lifecycle
    # stuck at queued. Without this gate we re-dispatch (burn a full session)
    # only for the callback guard to rubber-stamp done post-hoc. Run the SAME
    # check the callback guard / gate-daemon use (gate_logic), but BEFORE
    # dispatch: if the work is already on develop, mark done directly
    # (orchestrator is in _ALLOWED_WRITERS) and skip the session. Fail-closed:
    # only reconcile on a positive allowlist AND a positive commit match;
    # otherwise dispatch as normal (no worse than before this gate existed).
    allowed_files = gate_logic.parse_allowed_files(spec_files[0])
    if allowed_files:
        gate_logic.fetch_develop(project_dir)
        impl_sha = gate_logic.find_implementation_commit(project_dir, spec_id, allowed_files)
        if impl_sha:
            try:
                lifecycle.write_lifecycle(
                    project_dir,
                    spec_id,
                    "done",
                    by="orchestrator",
                    reason=f"already_implemented_on_develop:{impl_sha[:12]}",
                )
                log.info(
                    "reconciled: %s already implemented on develop (%s) — marked done, no dispatch",
                    spec_id,
                    impl_sha[:12],
                )
            except lifecycle.LifecycleAlreadyDoneError:
                log.info("reconcile noop: %s already done (race)", spec_id)
            except lifecycle.LifecycleWriteRaceError:
                log.info("reconcile deferred: %s CAS race, retry next cycle", spec_id)
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
    # Lifecycle SoT must show the spec is running (ADR-023). Without this the
    # documented queued → in_progress → done flow never happens: started_at stays
    # null forever and reconcile_orphans has nothing to reconcile.
    #
    # After _pueue_add, never before: the yaml needs the real pueue_id, and
    # reconcile_orphans keys crash recovery on it.
    #
    # A failed write must NEVER unwind the dispatch — the task is already queued
    # in pueue and will run regardless. Worst case we degrade to today's
    # behaviour (status stays queued), which pueue_has_active_label already
    # tolerates. So: log and continue, never re-raise, never return False.
    try:
        lifecycle.write_lifecycle(
            project_dir,
            spec_id,
            "in_progress",
            by="orchestrator",
            pueue_id=pueue_id,
        )
    except lifecycle.LifecycleAlreadyDoneError:
        # Rule 7 (ADR-025): callback closed the spec between the TOCTOU re-check
        # and here. The dispatch cannot be unwound — the pueue task is queued and
        # will start a session against a spec that is now done. How cheaply that
        # session exits is the autopilot skill's early-exit check, not ours.
        log.warning("in_progress skipped: %s already done (race)", spec_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("in_progress write failed for %s (dispatch stands): %s", spec_id, exc)
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


if __name__ == "__main__":
    main()
