#!/usr/bin/env python3
"""
Module: approve_handler
Role: Evening review prompt + finding approve/reject callbacks.
Uses: db.py (get_all_projects, get_finding_by_id, update_finding_status, get_all_findings),
      python-telegram-bot (InlineKeyboardButton/Markup, CallbackQueryHandler)
Used by: telegram-bot.py (handlers registered in main())
"""

import logging
import os
import sys
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

sys.path.insert(0, str(Path(__file__).parent))
import db

logger = logging.getLogger("dld-bot.approve")

SCRIPT_DIR = Path(__file__).parent
CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
REVIEW_TIME = os.environ.get("REVIEW_TIME", "22:00")
REVIEW_TZ = os.environ.get("REVIEW_TZ", "Europe/Moscow")


def _build_project_keyboard(projects: list[dict], selected: set) -> InlineKeyboardMarkup:
    """Build inline keyboard with project toggle buttons and a Launch row."""
    rows = []
    for p in projects:
        pid = p["project_id"]
        label = f"✅ {pid}" if pid in selected else pid
        rows.append([InlineKeyboardButton(label, callback_data=f"toggle:{pid}")])
    rows.append([InlineKeyboardButton("Launch Review", callback_data="launch_review")])
    return InlineKeyboardMarkup(rows)


def register_evening_job(app) -> None:
    """Register daily evening review prompt job.

    Parses REVIEW_TIME (HH:MM) and REVIEW_TZ env vars.
    Uses app.job_queue.run_daily with zoneinfo timezone.
    """
    hour, minute = (int(x) for x in REVIEW_TIME.split(":"))
    tz = ZoneInfo(REVIEW_TZ)
    app.job_queue.run_daily(
        evening_prompt,
        time=time(hour=hour, minute=minute, tzinfo=tz),
    )
    logger.info("Evening prompt scheduled at %s %s", REVIEW_TIME, REVIEW_TZ)


async def evening_prompt(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: send evening review message with project toggle keyboard."""
    projects = db.get_all_projects()
    if not projects:
        logger.info("Evening prompt: no enabled projects")
        return
    context.bot_data.setdefault("night_selected", set())
    selected: set = context.bot_data["night_selected"]
    keyboard = _build_project_keyboard(projects, selected)
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text="Evening review. Select projects to scan tonight:",
        reply_markup=keyboard,
    )


async def handle_project_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle project selection; edit message to reflect new state."""
    query = update.callback_query
    await query.answer()
    project_id = query.data.split(":", 1)[1]
    selected: set = context.bot_data.setdefault("night_selected", set())
    if project_id in selected:
        selected.discard(project_id)
    else:
        selected.add(project_id)
    projects = db.get_all_projects()
    keyboard = _build_project_keyboard(projects, selected)
    await query.edit_message_reply_markup(reply_markup=keyboard)


async def handle_launch_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Write .review-trigger file and clear selection."""
    query = update.callback_query
    await query.answer()
    selected: set = context.bot_data.get("night_selected", set())
    trigger = SCRIPT_DIR / ".review-trigger"
    trigger.write_text("\n".join(sorted(selected)) + "\n", encoding="utf-8")
    n = len(selected)
    context.bot_data["night_selected"] = set()
    await query.edit_message_text(f"Review scheduled for {n} projects")


# ---------------------------------------------------------------------------
# Finding approve / reject
# ---------------------------------------------------------------------------


def _write_finding_to_inbox(project: dict, finding: dict) -> None:
    """Write approved finding as an inbox spec file."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    inbox = Path(project["path"]) / "ai" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    p = inbox / f"{ts}-night-finding-{finding['id']}.md"
    lines = [
        f"# Finding: {finding['summary']}",
        f"Route: spark_bug",
        f"Status: new",
        f"Severity: {finding.get('severity', 'unknown')}",
        f"Confidence: {finding.get('confidence', 'unknown')}",
        "",
    ]
    if finding.get("file_path"):
        lines.append(f"File: {finding['file_path']}")
    if finding.get("line_range"):
        lines.append(f"Lines: {finding['line_range']}")
    if finding.get("suggestion"):
        lines.append(f"\n## Suggestion\n{finding['suggestion']}")
    p.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote finding %s to %s", finding["id"], p)


async def handle_finding_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a single finding: update DB + write inbox."""
    query = update.callback_query
    await query.answer()
    finding_id = int(query.data.split(":", 1)[1])
    db.update_finding_status(finding_id, "approved")
    finding = db.get_finding_by_id(finding_id)
    if finding:
        project = db.get_project_state(finding["project_id"])
        if project:
            _write_finding_to_inbox(project, finding)
    await query.edit_message_text(f"Находка #{finding_id} принята")


async def handle_finding_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a single finding."""
    query = update.callback_query
    await query.answer()
    finding_id = int(query.data.split(":", 1)[1])
    db.update_finding_status(finding_id, "rejected")
    await query.edit_message_text(f"Находка #{finding_id} отклонена")


async def handle_approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve all 'sent' findings for a project."""
    query = update.callback_query
    await query.answer()
    project_id = query.data.split(":", 1)[1]
    findings = db.get_all_findings(project_id, status="sent")
    project = db.get_project_state(project_id)
    for f in findings:
        db.update_finding_status(f["id"], "approved")
        if project:
            _write_finding_to_inbox(project, f)
    await query.edit_message_text(f"Все приняты ({len(findings)} находок)")


async def handle_reject_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject all 'sent' findings for a project."""
    query = update.callback_query
    await query.answer()
    project_id = query.data.split(":", 1)[1]
    findings = db.get_all_findings(project_id, status="sent")
    for f in findings:
        db.update_finding_status(f["id"], "rejected")
    await query.edit_message_text(f"Все отклонены ({len(findings)} находок)")


# ---------------------------------------------------------------------------
# Spec approve / rework / reject (FTR-149: human-in-the-loop)
# ---------------------------------------------------------------------------

MAX_REWORK_ITERATIONS = 3


def _update_spec_status(project_path: str, spec_id: str, new_status: str) -> bool:
    """Update status in spec file and backlog. Returns True on success."""
    import glob as glob_mod
    import re
    import subprocess

    project = Path(project_path)
    # Find spec file
    pattern = str(project / f"ai/features/{spec_id}*")
    matches = glob_mod.glob(pattern)
    if not matches:
        logger.error("Spec file not found: %s", pattern)
        return False
    spec_file = Path(matches[0])

    # Update spec file status
    content = spec_file.read_text(encoding="utf-8")
    content = re.sub(
        r"\*\*Status:\*\*\s*\w+",
        f"**Status:** {new_status}",
        content,
        count=1,
    )
    spec_file.write_text(content, encoding="utf-8")

    # Update backlog
    backlog = project / "ai/backlog.md"
    if backlog.exists():
        bl_content = backlog.read_text(encoding="utf-8")
        bl_content = re.sub(
            rf"(\|\s*{re.escape(spec_id)}\s*\|[^|]*\|)\s*\w+\s*\|",
            rf"\1 {new_status} |",
            bl_content,
        )
        backlog.write_text(bl_content, encoding="utf-8")

    # Commit + push
    try:
        subprocess.run(
            ["git", "add", str(spec_file), str(backlog)],
            cwd=str(project), capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", f"docs: {spec_id} status → {new_status}"],
            cwd=str(project), capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "push", "origin", "develop"],
            cwd=str(project), capture_output=True, timeout=30,
        )
    except Exception as e:
        logger.error("Git operations failed for %s: %s", spec_id, e)
        return False
    return True


async def handle_spec_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve spec: draft → queued. Orchestrator will pick it up for autopilot."""
    query = update.callback_query
    await query.answer()
    _, project_id, spec_id = query.data.split(":", 2)
    project = db.get_project_state(project_id)
    if not project:
        await query.edit_message_text(f"Project {project_id} not found")
        return
    ok = _update_spec_status(project["path"], spec_id, "queued")
    if ok:
        await query.edit_message_text(f"\u2705 {spec_id} принята → в очередь")
    else:
        await query.edit_message_text(f"Не удалось обновить статус {spec_id}")


async def handle_spec_rework(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rework spec: ask user for comment, then save to inbox for spark re-processing."""
    query = update.callback_query
    await query.answer()
    _, project_id, spec_id = query.data.split(":", 2)

    # Track rework iterations
    rework_key = f"rework_count:{project_id}:{spec_id}"
    count = context.bot_data.get(rework_key, 0) + 1
    context.bot_data[rework_key] = count

    if count > MAX_REWORK_ITERATIONS:
        project = db.get_project_state(project_id)
        if project:
            _update_spec_status(project["path"], spec_id, "blocked")
        await query.edit_message_text(
            f"\u26a0\ufe0f {spec_id}: лимит доработок ({MAX_REWORK_ITERATIONS}) исчерпан → заблокирована"
        )
        return

    # Store pending rework info, ask for comment
    context.bot_data[f"rework_pending:{query.message.message_thread_id}"] = {
        "project_id": project_id,
        "spec_id": spec_id,
    }
    await query.edit_message_text(
        f"\u270f\ufe0f {spec_id}: напиши что доработать (ответом в этот топик):"
    )


async def handle_rework_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture rework comment and save to inbox for spark re-processing."""
    topic_id = getattr(update.effective_message, "message_thread_id", None)
    if topic_id == 1:
        topic_id = None
    if not topic_id:
        return None

    pending_key = f"rework_pending:{topic_id}"
    pending = context.bot_data.get(pending_key)
    if not pending:
        return None

    project_id = pending["project_id"]
    spec_id = pending["spec_id"]
    comment = update.message.text
    del context.bot_data[pending_key]

    project = db.get_project_state(project_id)
    if not project:
        await update.message.reply_text(f"Project {project_id} not found")
        return

    # Find spec file path for Context field
    import glob as glob_mod

    pattern = str(Path(project["path"]) / f"ai/features/{spec_id}*")
    matches = glob_mod.glob(pattern)
    spec_path = f"ai/features/{Path(matches[0]).name}" if matches else f"ai/features/{spec_id}.md"

    # Write rework request to inbox
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    inbox_dir = Path(project["path"]) / "ai" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    inbox_file = inbox_dir / f"{ts}-rework-{spec_id}.md"
    inbox_file.write_text(
        f"# Idea: {ts}\n"
        f"**Source:** human\n"
        f"**Route:** spark\n"
        f"**Status:** new\n"
        f"**Context:** {spec_path}\n"
        f"---\n"
        f"[headless] Доработай спеку {spec_id}: {comment}\n",
        encoding="utf-8",
    )
    await update.message.reply_text(
        f"Замечание сохранено. Spark доработает {spec_id} в следующем цикле."
    )


async def handle_spec_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject spec: draft → rejected. File is preserved but autopilot won't touch it."""
    query = update.callback_query
    await query.answer()
    _, project_id, spec_id = query.data.split(":", 2)
    project = db.get_project_state(project_id)
    if not project:
        await query.edit_message_text(f"Project {project_id} not found")
        return
    ok = _update_spec_status(project["path"], spec_id, "rejected")
    if ok:
        await query.edit_message_text(f"\u274c {spec_id} отклонена")
    else:
        await query.edit_message_text(f"Не удалось отклонить {spec_id}")
