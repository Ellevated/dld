#!/usr/bin/env python3
"""
Module: orchestrator_inbox
Role: Hermes intake gate (ADR-021/022) — parse ai/inbox/ markdown files, dispatch
      only Status: queued (Hermes-promoted) via pueue.
Uses: db (import), orchestrator_slots (bound: _pueue_add, pueue_has_active_label)
Used by: orchestrator (facade re-export)
"""

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import db  # noqa: E402

# Bound form is required, not stylistic — tests patch `orchestrator_inbox._pueue_add`
# and `orchestrator_inbox.pueue_has_active_label`; attribute access on the source
# module would not be visible to those patches.
from orchestrator_slots import _pueue_add, pueue_has_active_label  # noqa: F401,E402

log = logging.getLogger("orchestrator")


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


def scan_inbox(project_id: str, project_dir: str) -> int:
    """Scan ai/inbox/ for Status: queued files (Hermes-promoted), dispatch each via pueue.

    TECH-181: status gate — only files explicitly promoted by Hermes to `queued`
    are dispatched. Legacy `new`, `draft`, `clarifying`, `stale`, `rejected` are
    ignored. Clean break, no auto-migration (see spec rationale).

    TECH-215 note for test authors: this reads THIS module's `SCRIPT_DIR`, so
    `patch("orchestrator.SCRIPT_DIR", tmp_path)` does NOT reach it. A test that
    patches the facade and then exercises this path will silently write
    `.task-cmd-*.txt` into the deployed `scripts/vps/` and shell out to the real
    pueue daemon. Patch `orchestrator_inbox.SCRIPT_DIR` instead.
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
