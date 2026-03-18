#!/usr/bin/env python3
"""
Module: orchestrator
Role: Main poll loop daemon — scan inbox, scan backlog, dispatch via pueue.
Uses: db (import), subprocess (pueue CLI), signal, threading
Used by: systemd (dld-orchestrator.service)

Replaces orchestrator.sh + inbox-processor.sh (ARCH-161).
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
        os.path.join(log_dir, "orchestrator.log"),
        when="midnight", backupCount=7, utc=True,
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


def is_agent_running(project_id: str) -> bool:
    """Return True if a pueue task with this project's label prefix is Running."""
    try:
        r = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(r.stdout)
        for task in data.get("tasks", {}).values():
            label = task.get("label", "")
            status = task.get("status", "")
            if label.startswith(f"{project_id}:") and isinstance(status, dict) and "Running" in status:
                return True
    except Exception:
        pass
    return False


def git_pull(project_id: str, project_dir: str) -> None:
    """Pull develop branch. Skip if agent running or not a git repo."""
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return
    if is_agent_running(project_id):
        log.info("skip git pull — agent running: %s", project_id)
        return
    try:
        diff = subprocess.run(
            ["git", "-C", project_dir, "diff", "--quiet"], capture_output=True, timeout=30,
        )
        cached = subprocess.run(
            ["git", "-C", project_dir, "diff", "--cached", "--quiet"], capture_output=True, timeout=30,
        )
        if diff.returncode == 0 and cached.returncode == 0:
            subprocess.run(
                ["git", "-C", project_dir, "pull", "--rebase", "origin", "develop"],
                capture_output=True, text=True, timeout=120, check=True,
            )
        else:
            subprocess.run(
                ["git", "-C", project_dir, "fetch", "origin", "develop"],
                capture_output=True, timeout=60, check=True,
            )
            subprocess.run(
                ["git", "-C", project_dir, "rebase", "--autostash", "origin/develop"],
                capture_output=True, text=True, timeout=120, check=True,
            )
    except subprocess.CalledProcessError as exc:
        subprocess.run(["git", "-C", project_dir, "rebase", "--abort"], capture_output=True, timeout=30)
        log.warning("git pull failed: %s — %s", project_dir, (exc.stderr or "")[:200])


def _parse_inbox_file(filepath: Path) -> dict:
    """Extract route/source/provider/context/idea_text from inbox markdown."""
    text = filepath.read_text(errors="replace")
    lines = text.splitlines()

    def extract(key: str, default: str = "") -> str:
        for line in lines:
            m = re.match(rf"^\*\*{key}:\*\*\s+(.+)", line)
            if m:
                return m.group(1).strip()
        return default

    idea_lines, in_body = [], False
    for line in lines:
        if line.strip() == "---":
            in_body = True
            continue
        if in_body:
            idea_lines.append(line)
            if len(idea_lines) >= 50:
                break

    idea_text = " ".join(idea_lines).strip()
    if not idea_text:
        idea_text = " ".join(
            ln for ln in lines[:20]
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
    "spark": "spark", "architect": "architect", "council": "council",
    "spark_bug": "spark", "bughunt": "bughunt", "qa": "qa",
    "reflect": "reflect", "scout": "scout",
}


def _pueue_add(group: str, label: str, cmd: list, env: dict | None = None) -> int | None:
    """Submit task to pueue group. Returns pueue task ID or None."""
    pueue_cmd = ["pueue", "add", "--group", group, "--label", label, "--print-task-id", "--"] + cmd
    env_overrides = {}
    if env:
        env_overrides = {**os.environ, **env}
    try:
        r = subprocess.run(
            pueue_cmd,
            capture_output=True, text=True, timeout=30,
            env=env_overrides if env_overrides else None,
        )
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
            m = re.search(r"(\d+)", line)
            if m:
                return int(m.group(1))
        log.warning("pueue add: no task ID in output: %s", r.stdout[:200])
    except Exception as exc:
        log.error("pueue add failed: %s", exc)
    return None


def scan_inbox(project_id: str, project_dir: str) -> int:
    """Scan ai/inbox/ for Status: new files, dispatch each via pueue."""
    inbox_dir = Path(project_dir) / "ai" / "inbox"
    if not inbox_dir.is_dir():
        return 0

    count = 0
    for inbox_file in sorted(inbox_dir.glob("*.md")):
        if "**Status:** new" not in inbox_file.read_text(errors="replace"):
            continue

        log.info("processing inbox: %s/%s", project_id, inbox_file.name)
        meta = _parse_inbox_file(inbox_file)
        skill = _ROUTE_SKILL_MAP.get(meta["route"], "spark")

        text = inbox_file.read_text(errors="replace")
        text = text.replace("**Status:** new", "**Status:** processing")
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
        pueue_env = {
            "CLAUDE_PROJECT_DIR": project_dir,
            "CLAUDE_CURRENT_SPEC_PATH": str(done_file),
        }
        pueue_id = _pueue_add(
            f"{provider}-runner", task_label,
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


def scan_backlog(project_id: str, project_dir: str) -> bool:
    """Find first queued spec and dispatch autopilot. Returns True if dispatched."""
    backlog = Path(project_dir) / "ai" / "backlog.md"
    if not backlog.is_file():
        return False

    spec_id = None
    for line in backlog.read_text().splitlines():
        if re.search(r"\|\s*queued\s*\|", line):
            m = re.search(r"(TECH|FTR|BUG|ARCH)-\d+", line)
            if m:
                spec_id = m.group(0)
                break
    if not spec_id:
        return False

    state = db.get_project_state(project_id)
    provider = (state["provider"] if state else None) or "claude"

    features_dir = Path(project_dir) / "ai" / "features"
    spec_files = list(features_dir.glob(f"{spec_id}*"))
    if spec_files:
        m = re.search(r"^provider:\s+(\w+)", spec_files[0].read_text(errors="replace"), re.MULTILINE)
        if m and db.get_available_slots(m.group(1)) >= 0:
            provider = m.group(1)

    if db.get_available_slots(provider) < 1:
        log.info("no slots for %s provider=%s", project_id, provider)
        return False

    task_label = f"{project_id}:{spec_id}"
    pueue_id = _pueue_add(
        f"{provider}-runner", task_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_dir, provider, "autopilot", f"/autopilot {spec_id}"],
    )
    if pueue_id is None:
        log.error("pueue submission failed: %s/%s", project_id, spec_id)
        return False

    db.try_acquire_slot(project_id, provider, pueue_id)
    db.log_task(project_id, task_label, "autopilot", "running", pueue_id)
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
        "night-reviewer", "night-review",
        [str(SCRIPT_DIR / "night-reviewer.sh")] + project_ids.split(),
    )


def process_project(project_id: str, project_dir: str) -> None:
    """Process one project: git pull, inbox, backlog, invariant check."""
    git_pull(project_id, project_dir)
    scan_inbox(project_id, project_dir)
    scan_backlog(project_id, project_dir)
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

    while not _stop.is_set():
        try:
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
