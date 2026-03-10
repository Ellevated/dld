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
    await query.edit_message_text(f"Approved finding #{finding_id}")


async def handle_finding_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a single finding."""
    query = update.callback_query
    await query.answer()
    finding_id = int(query.data.split(":", 1)[1])
    db.update_finding_status(finding_id, "rejected")
    await query.edit_message_text(f"Rejected finding #{finding_id}")


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
    await query.edit_message_text(f"All approved ({len(findings)} findings)")


async def handle_reject_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject all 'sent' findings for a project."""
    query = update.callback_query
    await query.answer()
    project_id = query.data.split(":", 1)[1]
    findings = db.get_all_findings(project_id, status="sent")
    for f in findings:
        db.update_finding_status(f["id"], "rejected")
    await query.edit_message_text(f"All rejected ({len(findings)} findings)")


# ---------------------------------------------------------------------------
# Confirm spec → submit to pueue
# ---------------------------------------------------------------------------


async def handle_confirm_spec(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm a spec and submit it to pueue via telegram-bot._submit_to_pueue."""
    query = update.callback_query
    await query.answer()
    spec_id = query.data.split(":", 1)[1]

    # telegram-bot.py runs as __main__ or is already in sys.modules
    tb = sys.modules.get("telegram_bot") or sys.modules.get("__main__")
    _submit_to_pueue = tb._submit_to_pueue
    get_topic_id = tb.get_topic_id

    topic_id = get_topic_id(update)
    project = db.get_project_by_topic(topic_id) if topic_id else None
    if not project:
        await query.edit_message_text(f"No project for this topic")
        return
    ok = _submit_to_pueue(project, spec_id)
    await query.edit_message_text(f"Started {spec_id}" if ok else f"Submit failed: {spec_id}")
