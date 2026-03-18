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
    if app.job_queue is None:
        logger.warning("JobQueue not available (install python-telegram-bot[job-queue]). Evening prompt disabled.")
        return
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


async def handle_finding_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a single finding: update DB only. OpenClaw decides next action."""
    query = update.callback_query
    await query.answer()
    finding_id = int(query.data.split(":", 1)[1])
    db.update_finding_status(finding_id, "approved")
    await query.edit_message_text(f"Находка #{finding_id} принята. OpenClaw разберёт её отдельно.")


async def handle_finding_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a single finding."""
    query = update.callback_query
    await query.answer()
    finding_id = int(query.data.split(":", 1)[1])
    db.update_finding_status(finding_id, "rejected")
    await query.edit_message_text(f"Находка #{finding_id} отклонена")


async def handle_approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve all 'sent' findings for a project. No inbox writes here."""
    query = update.callback_query
    await query.answer()
    project_id = query.data.split(":", 1)[1]
    findings = db.get_all_findings(project_id, status="sent")
    for f in findings:
        db.update_finding_status(f["id"], "approved")
    await query.edit_message_text(f"Все приняты ({len(findings)} находок). OpenClaw разберёт их отдельно.")


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
# Legacy spec approval callbacks removed in north-star flow.
# Spark should create queued specs directly; OpenClaw owns follow-up intake.
# ---------------------------------------------------------------------------


async def handle_rework_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """No-op legacy hook kept only to avoid bot import breakage."""
    return None
