#!/usr/bin/env python3
"""
Module: callback
Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect.
Uses: db, event_writer, subprocess (pueue CLI fallback)
Used by: Pueue daemon (pueue.yml callback config)
CLI: python3 callback.py <pueue_id> '<group>' '<result>'
INVARIANT: Always exit 0. Every step in try/except.
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402
import event_writer  # noqa: E402

log = logging.getLogger("callback")


def _load_env() -> None:
    """Load .env from SCRIPT_DIR. Manual parser."""
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
    """Append-mode file + stderr logging."""
    log_file = SCRIPT_DIR / "callback-debug.log"
    handler = logging.FileHandler(str(log_file), mode="a")
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(stderr_handler)


def resolve_label(pueue_id: str) -> str:
    """Get task label. DB-first, pueue CLI fallback."""
    # Layer 1: DB (reliable — no socket dependency)
    try:
        row = db.get_task_by_pueue_id(int(pueue_id))
        if row:
            project_id = row["project_id"]
            task_label = row["task_label"]
            if task_label.startswith(f"{project_id}:"):
                label = task_label
            else:
                label = f"{project_id}:{task_label}"
            log.info("resolve_label from DB: %s", label)
            return label
    except Exception as exc:
        log.warning("resolve_label DB failed: %s", exc)

    # Layer 2: pueue CLI (fallback — may fail due to socket mismatch)
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        task = data.get("tasks", {}).get(pueue_id, {})
        label = task.get("label", "unknown") or "unknown"
        if label != "unknown":
            log.info("resolve_label from pueue: %s", label)
        return label
    except Exception:
        return "unknown"


def parse_label(label: str) -> tuple:
    """Split label into (project_id, task_label)."""
    if ":" in label:
        project_id, _, task_label = label.partition(":")
        return project_id, task_label
    log.warning("label '%s' has no colon", label)
    return label, label


def map_result(result: str) -> tuple:
    """Map pueue result string to (status, exit_code)."""
    if "Success" in result:
        return "done", 0
    return "failed", 1


def _find_log_file(project_name: str) -> Path | None:
    """Find most recent log file for project in logs/ dir."""
    log_dir = SCRIPT_DIR / "logs"
    if not log_dir.is_dir():
        return None
    pattern = f"{project_name}-*.log"
    files = sorted(log_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _parse_log_file(log_path: Path) -> tuple:
    """Parse JSON log file → (skill, result_preview)."""
    try:
        data = json.loads(log_path.read_text())
        skill = data.get("skill", "")
        preview = str(data.get("result_preview", ""))[:500]
        return skill, preview
    except Exception:
        return "", ""


def extract_agent_output(pueue_id: str, project_id: str = "") -> tuple:
    """Extract skill and result_preview. Log file → DB → pueue log → ("", "")."""
    # Layer 1: Read from log file (reliable — written by claude-runner.py)
    if project_id:
        try:
            state = db.get_project_state(project_id)
            if state:
                project_name = Path(state.get("path", "")).name
                if project_name:
                    log_path = _find_log_file(project_name)
                    if log_path:
                        skill, preview = _parse_log_file(log_path)
                        if skill:
                            log.info("extract_agent_output from log: %s", log_path.name)
                            return skill, preview
        except Exception as exc:
            log.warning("extract_agent_output log file failed: %s", exc)

    # Layer 1b: Try DB task_log for skill (if no log file found)
    try:
        row = db.get_task_by_pueue_id(int(pueue_id))
        if row and row.get("skill"):
            log.info("extract_agent_output skill from DB: %s", row["skill"])
            return row["skill"], ""
    except Exception as exc:
        log.warning("extract_agent_output DB failed: %s", exc)

    # Layer 2: pueue log (fallback — may fail due to socket mismatch)
    try:
        result = subprocess.run(
            ["pueue", "log", pueue_id, "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(result.stdout)
        task_data = data.get("tasks", {}).get(pueue_id, {})
        output = task_data.get("output", "")
        if not output:
            output = result.stdout

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{") and '"skill"' in line:
                try:
                    obj = json.loads(line)
                    skill = obj.get("skill", "")
                    preview = str(obj.get("result_preview", ""))[:500]
                    return skill, preview
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return "", ""


def resolve_spec_id(task_label: str, preview: str, project_path: str) -> str | None:
    """Multi-layer spec_id resolution."""
    spec_re = re.compile(r"(TECH|FTR|BUG|ARCH)-\d+")

    # Layer 1: from task label
    m = spec_re.search(task_label)
    if m:
        return m.group(0)

    # Layer 2: from preview text
    if preview:
        m = spec_re.search(preview)
        if m:
            return m.group(0)

    # Layer 3: from inbox done files
    if task_label.startswith("inbox-") and project_path:
        done_dir = Path(project_path) / "ai" / "inbox" / "done"
        if done_dir.is_dir():
            for f in sorted(done_dir.glob("*.md"), reverse=True):
                text = f.read_text(errors="replace")
                m = re.search(r"\*\*SpecID:\*\*\s*(\S+)", text)
                if m:
                    sm = spec_re.search(m.group(1))
                    if sm:
                        return sm.group(0)
    return None


def is_already_queued(label: str) -> bool:
    """Check if a task with this label is Running or Queued."""
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        for task in data.get("tasks", {}).values():
            if task.get("label") == label:
                status = task.get("status", {})
                if isinstance(status, dict) and ("Running" in status or "Queued" in status):
                    return True
        return False
    except Exception:
        return False


def _pueue_add(group: str, label: str, cmd: list) -> int | None:
    """Submit task to pueue. Returns task ID or None."""
    try:
        pueue_cmd = [
            "pueue",
            "add",
            "--group",
            group,
            "--label",
            label,
            "--print-task-id",
            "--",
        ] + cmd
        result = subprocess.run(
            pueue_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stdout.strip().splitlines():
            m = re.search(r"(\d+)", line.strip())
            if m:
                return int(m.group(1))
        return None
    except Exception:
        return None


def dispatch_qa(project_id: str, project_path: str, spec_id: str, provider: str) -> None:
    """Dispatch QA task via pueue."""
    qa_label = f"{project_id}:qa-{spec_id}"
    if is_already_queued(qa_label):
        log.info("skip duplicate QA: %s", qa_label)
        return
    runner_group = f"{provider}-runner"
    pueue_id = _pueue_add(
        runner_group,
        qa_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_path, provider, "qa", f"/qa {spec_id}"],
    )
    if pueue_id:
        db.try_acquire_slot(project_id, provider, pueue_id)
        db.log_task(project_id, qa_label, "qa", "running", pueue_id)
        log.info("QA dispatched: %s pueue_id=%d", qa_label, pueue_id)
    else:
        log.warning("QA dispatch failed: %s", qa_label)


def dispatch_reflect(project_id: str, project_path: str, task_label: str, provider: str) -> None:
    """Dispatch reflect task via pueue."""
    reflect_label = f"{project_id}:reflect-{task_label}"
    if is_already_queued(reflect_label):
        log.info("skip duplicate reflect: %s", reflect_label)
        return
    runner_group = f"{provider}-runner"
    pueue_id = _pueue_add(
        runner_group,
        reflect_label,
        [str(SCRIPT_DIR / "run-agent.sh"), project_path, provider, "reflect", "/reflect"],
    )
    if pueue_id:
        db.try_acquire_slot(project_id, provider, pueue_id)
        db.log_task(project_id, reflect_label, "reflect", "running", pueue_id)
        log.info("reflect dispatched: %s pueue_id=%d", reflect_label, pueue_id)
    else:
        log.warning("reflect dispatch failed: %s", reflect_label)


def _fix_spec_status(spec_path: Path, spec_id: str, target: str) -> bool:
    """Replace **Status:** <anything> with **Status:** <target> in spec file."""
    text = spec_path.read_text(errors="replace")
    new_text, count = re.subn(
        r"(\*\*Status:\*\*)\s*\S+",
        rf"\1 {target}",
        text,
        count=1,
    )
    if count:
        spec_path.write_text(new_text)
        log.info("STATUS_FIX: spec %s → %s in %s", spec_id, target, spec_path.name)
        return True
    return False


def _fix_backlog_status(backlog_path: Path, spec_id: str, target: str) -> bool:
    """Replace status column for spec_id row in backlog.md."""
    text = backlog_path.read_text(errors="replace")
    pattern = rf"(\|\s*{re.escape(spec_id)}\s*\|.*?\|)\s*\S+\s*(\|)"
    new_text, count = re.subn(pattern, rf"\1 {target} \2", text, count=1)
    if count:
        backlog_path.write_text(new_text)
        log.info("STATUS_FIX: backlog %s → %s", spec_id, target)
        return True
    return False


def _git_commit_push(project_path: str, spec_id: str, target: str, files: list) -> None:
    """Stage, commit, and push status fix."""
    git = ["git", "-C", project_path]
    subprocess.run(git + ["add"] + files, capture_output=True, timeout=10)
    subprocess.run(
        git + ["commit", "-m", f"docs: mark {spec_id} as {target} (callback auto-fix)"],
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        git + ["push", "origin", "develop"],
        capture_output=True,
        timeout=60,
    )
    log.info("STATUS_FIX: committed and pushed %s → %s", spec_id, target)


def verify_status_sync(project_path: str, spec_id: str, target: str = "done") -> None:
    """Check that spec file and backlog both have target status. Auto-fix if not."""
    p = Path(project_path)
    spec_re = re.compile(rf"\*\*Status:\*\*\s*{re.escape(target)}", re.IGNORECASE)
    backlog_re = re.compile(
        rf"\|\s*{re.escape(spec_id)}\s*\|.*?\|\s*{re.escape(target)}\s*\|",
        re.IGNORECASE,
    )

    # Check spec file
    spec_ok = False
    spec_file = None
    spec_files = list(p.glob(f"ai/features/{spec_id}*.md"))
    if not spec_files:
        log.warning("STATUS_SYNC: spec file not found for %s", spec_id)
    else:
        spec_file = spec_files[0]
        text = spec_file.read_text(errors="replace")
        if spec_re.search(text):
            spec_ok = True

    # Check backlog
    backlog_ok = False
    backlog_path = p / "ai" / "backlog.md"
    if not backlog_path.is_file():
        log.warning("STATUS_SYNC: backlog.md not found in %s", project_path)
    else:
        text = backlog_path.read_text(errors="replace")
        if backlog_re.search(text):
            backlog_ok = True

    if spec_ok and backlog_ok:
        log.info("STATUS_SYNC: %s — both spec and backlog are %s ✓", spec_id, target)
        return

    # Auto-fix
    fixed_files = []
    if not spec_ok and spec_file:
        if _fix_spec_status(spec_file, spec_id, target):
            fixed_files.append(str(spec_file.relative_to(p)))
        else:
            log.warning("STATUS_FIX: could not fix spec %s", spec_id)

    if not backlog_ok and backlog_path.is_file():
        if _fix_backlog_status(backlog_path, spec_id, target):
            fixed_files.append("ai/backlog.md")
        else:
            log.warning("STATUS_FIX: could not fix backlog for %s", spec_id)

    if fixed_files:
        log.warning(
            "STATUS_SYNC: %s — auto-fixed %d file(s) → %s: %s",
            spec_id,
            len(fixed_files),
            target,
            ", ".join(fixed_files),
        )
        _git_commit_push(project_path, spec_id, target, fixed_files)


def write_event_for_skill(project_path: str, skill: str, status: str, task_label: str) -> None:
    """Write OpenClaw event for applicable skills."""
    if skill not in ("autopilot", "qa", "reflect", "spark"):
        return
    if status != "done" and not (status == "failed" and skill == "qa"):
        return

    artifact_rel = ""
    p = Path(project_path)
    if skill == "qa":
        qa_files = sorted(p.glob("ai/qa/[0-9]*-*.md"))
        if qa_files:
            artifact_rel = str(qa_files[-1].relative_to(p))
    elif skill == "reflect":
        reflect_files = sorted(p.glob("ai/reflect/findings-*.md"))
        if reflect_files:
            artifact_rel = str(reflect_files[-1].relative_to(p))

    event_writer.notify(
        project_path,
        skill,
        status,
        f"{skill} {status} for {task_label}",
        artifact_rel,
    )


def main() -> None:
    """Main callback entry point. ALWAYS exits 0."""
    try:
        _load_env()
        _setup_logging()

        pueue_id = sys.argv[1] if len(sys.argv) > 1 else "0"
        group = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        result = sys.argv[3] if len(sys.argv) > 3 else "unknown"

        log.info("callback: id=%s group=%s result=%s", pueue_id, group, result)

        # Skip night-reviewer group
        if group == "night-reviewer":
            log.info("skip night-reviewer callback")
            sys.exit(0)

        label = resolve_label(pueue_id)
        project_id, task_label = parse_label(label)
        status, exit_code = map_result(result)

        log.info("parsed: project=%s task=%s status=%s", project_id, task_label, status)

        # Step 1: Release slot (ALWAYS)
        try:
            db.release_slot(pueue_id)
        except Exception as exc:
            log.warning("release_slot failed: %s", exc)

        # Step 2: Finish task
        try:
            db.finish_task(pueue_id, status, exit_code)
        except Exception as exc:
            log.warning("finish_task failed: %s", exc)

        # Step 3: Update phase
        try:
            if task_label.startswith(("qa-", "reflect-")):
                new_phase = "idle"  # non-blocking tail tasks
            elif status == "done":
                if task_label.startswith("inbox-"):
                    new_phase = "idle"
                else:
                    new_phase = "qa_pending"
            else:
                new_phase = "failed"

            current_task = task_label if new_phase == "qa_pending" else None
            db.update_project_phase(project_id, new_phase, current_task)
            log.info("phase updated: %s -> %s", project_id, new_phase)
        except Exception as exc:
            log.warning("update_phase failed: %s", exc)

        # Step 4: Extract agent output
        skill, preview = "", ""
        try:
            skill, preview = extract_agent_output(pueue_id, project_id)
            log.info("agent output: skill=%s preview_len=%d", skill, len(preview))
        except Exception as exc:
            log.warning("extract_agent_output failed: %s", exc)

        # Step 5: Write OpenClaw event
        try:
            project_path = ""
            state = db.get_project_state(project_id)
            if state:
                project_path = state.get("path", "")
            if project_path:
                write_event_for_skill(project_path, skill, status, task_label)
        except Exception as exc:
            log.warning("write_event failed: %s", exc)

        # Step 6: Post-autopilot tail — dispatch QA + Reflect
        if skill == "autopilot" and status == "done":
            try:
                state = db.get_project_state(project_id)
                if state:
                    project_path = state.get("path", "")
                    provider = state.get("provider", "claude") or "claude"
                    if project_path:
                        spec_id = resolve_spec_id(task_label, preview, project_path)
                        if spec_id:
                            dispatch_qa(project_id, project_path, spec_id, provider)
                        else:
                            log.info("skip QA: no spec_id resolved for %s", task_label)
                        dispatch_reflect(project_id, project_path, task_label, provider)
            except Exception as exc:
                log.warning("post-autopilot dispatch failed: %s", exc)

        # Step 7: Verify spec + backlog status sync
        if skill == "autopilot" and status in ("done", "failed"):
            try:
                if not project_path:
                    state = db.get_project_state(project_id)
                    project_path = state.get("path", "") if state else ""
                if project_path:
                    sid = resolve_spec_id(task_label, preview, project_path)
                    if sid:
                        target = "done" if status == "done" else "blocked"
                        verify_status_sync(project_path, sid, target)
            except Exception as exc:
                log.warning("status_sync check failed: %s", exc)

    except Exception:
        log.exception("callback fatal error")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
