#!/usr/bin/env python3
"""
Module: telegram-bot
Role: Telegram bot with forum topic routing for multi-project orchestration.
Uses: db.py, notify.py, python-telegram-bot v21.9+
Used by: systemd (dld-telegram-bot.service)
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Add script dir for db import
sys.path.insert(0, str(Path(__file__).parent))
import db

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("dld-bot")

# Config from env
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
ALLOWED_USERS = set(
    int(uid.strip())
    for uid in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
)
SCRIPT_DIR = Path(__file__).parent

# Keyword routing patterns (Russian + English)
ROUTE_PATTERNS: dict[str, list[str]] = {
    "architect": [
        "архитектура",
        "спроектируй",
        "система",
        "домены",
        "как устроить",
        "интеграция",
        "design system",
        "bounded context",
        "data flow",
        "инфраструктура",
        "схема данных",
        "миграция",
        "рефакторинг архитектуры",
    ],
    "council": [
        "консилиум",
        "сравни подходы",
        "что лучше",
        "trade-off",
        "выбери между",
        "стоит ли",
        "плюсы и минусы",
        "совет директоров",
    ],
    "bughunt": [
        "баг хант",
        "охота на баги",
        "глубокий анализ багов",
        "много багов",
        "всё сломалось",
        "системные проблемы",
        "deep analysis",
        "bug hunt",
        "командный аудит багов",
    ],
    "spark_bug": [
        "баг",
        "ошибка",
        "не работает",
        "сломалось",
        "падает",
        "crash",
        "fix",
        "broken",
        "регрессия",
        "regression",
    ],
}


def detect_route(text: str) -> str:
    """Detect skill route from message text via keyword matching."""
    text_lower = text.lower()
    for route, keywords in ROUTE_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return route
    return "spark"


def is_authorized(user_id: int) -> bool:
    """Check if user is in allowed list."""
    if not ALLOWED_USERS:
        return True  # No whitelist = allow all (dev mode)
    return user_id in ALLOWED_USERS


def get_topic_id(update: Update) -> int | None:
    """Extract message_thread_id, handling General topic bug (DA-4)."""
    thread_id = getattr(update.effective_message, "message_thread_id", None)
    # DA-4: thread_id=1 is General topic, returns BadRequest if used
    if thread_id == 1:
        return None
    return thread_id


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command. Shows project state from SQLite + Pueue."""
    if not is_authorized(update.effective_user.id):
        return

    args = context.args or []
    topic_id = get_topic_id(update)

    if args:
        # /status <project_id>
        project = db.get_project_state(args[0])
        if not project:
            await update.message.reply_text(
                f"Project `{args[0]}` not found.", parse_mode="Markdown"
            )
            return
        await _send_project_status(update, project)
    elif topic_id:
        # In project topic — show this project
        project = db.get_project_by_topic(topic_id)
        if project:
            await _send_project_status(update, project)
        else:
            await update.message.reply_text("This topic is not linked to a project.")
    else:
        # General topic — show all projects
        projects = db.get_all_projects()
        if not projects:
            await update.message.reply_text("No projects configured.")
            return
        lines = ["*All Projects:*\n"]
        for p in projects:
            status_icon = {"idle": "⚪", "running": "🟢", "qa_pending": "🟡", "failed": "🔴"}.get(
                p["phase"], "⚫"
            )
            task_info = f" ({p['current_task']})" if p.get("current_task") else ""
            lines.append(f"{status_icon} `{p['project_id']}` — {p['phase']}{task_info}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _send_project_status(update: Update, project: dict) -> None:
    """Format and send detailed project status."""
    pueue_info = ""
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            pueue_data = json.loads(result.stdout)
            tasks = pueue_data.get("tasks", {})
            project_tasks = [
                t
                for t in tasks.values()
                if t.get("label", "").startswith(project["project_id"] + ":")
            ]
            if project_tasks:
                pueue_lines = []
                for t in project_tasks[-3:]:  # Last 3 tasks
                    pueue_lines.append(
                        f"  #{t['id']} {t.get('label', '')} — {t.get('status', '?')}"
                    )
                pueue_info = "\n*Pueue tasks:*\n" + "\n".join(pueue_lines)
    except Exception as e:
        logger.debug("pueue status unavailable: %s", e)

    slots = db.get_available_slots(project.get("provider", "claude"))
    msg = (
        f"*{project['project_id']}*\n"
        f"Phase: `{project['phase']}`\n"
        f"Provider: `{project.get('provider', 'claude')}`\n"
        f"Current task: `{project.get('current_task', 'none')}`\n"
        f"Auto-approve: `{project.get('auto_approve_timeout', 30)}s`\n"
        f"Available slots: `{slots}`\n"
        f"Path: `{project['path']}`"
        f"{pueue_info}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /run command. Triggers orchestrator cycle or writes to inbox."""
    if not is_authorized(update.effective_user.id):
        return

    args = context.args or []
    topic_id = get_topic_id(update)

    project = None
    task_text = None

    if args:
        project = db.get_project_state(args[0])
        if not project:
            await update.message.reply_text(
                f"Project `{args[0]}` not found.", parse_mode="Markdown"
            )
            return
        task_text = " ".join(args[1:]) if len(args) > 1 else None
    elif topic_id:
        project = db.get_project_by_topic(topic_id)

    if not project:
        await update.message.reply_text(
            "Specify project: `/run <project>` or use in project topic.",
            parse_mode="Markdown",
        )
        return

    if task_text:
        _save_to_inbox(project, task_text)
        await update.message.reply_text(
            f"Saved to inbox: `{task_text}`\nTriggering cycle...",
            parse_mode="Markdown",
        )

    # Touch trigger file for orchestrator
    trigger_file = SCRIPT_DIR / f".run-now-{project['project_id']}"
    trigger_file.touch()
    if not task_text:
        await update.message.reply_text(
            f"Triggered immediate cycle for `{project['project_id']}`.",
            parse_mode="Markdown",
        )


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pause command. Pauses project's Pueue group."""
    if not is_authorized(update.effective_user.id):
        return

    project = _resolve_project(update, context)
    if not project:
        await update.message.reply_text(
            "Specify project: `/pause <project>`", parse_mode="Markdown"
        )
        return

    try:
        result = subprocess.run(
            ["pueue", "pause", "--group", project["project_id"]], timeout=5, capture_output=True
        )
        if result.returncode != 0:
            await update.message.reply_text(f"Pause failed: pueue exited {result.returncode}")
            return
        db.update_project_phase(project["project_id"], "paused")
        await update.message.reply_text(f"Paused `{project['project_id']}`.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Pause failed: {e}")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /resume command. Resumes project's Pueue group."""
    if not is_authorized(update.effective_user.id):
        return

    project = _resolve_project(update, context)
    if not project:
        await update.message.reply_text(
            "Specify project: `/resume <project>`", parse_mode="Markdown"
        )
        return

    try:
        result = subprocess.run(
            ["pueue", "start", "--group", project["project_id"]], timeout=5, capture_output=True
        )
        if result.returncode != 0:
            await update.message.reply_text(f"Resume failed: pueue exited {result.returncode}")
            return
        db.update_project_phase(project["project_id"], "idle")
        await update.message.reply_text(
            f"Resumed `{project['project_id']}`.", parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"Resume failed: {e}")


def _resolve_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Resolve project from command args or topic_id."""
    args = context.args or []
    if args:
        return db.get_project_state(args[0])
    topic_id = get_topic_id(update)
    if topic_id:
        return db.get_project_by_topic(topic_id)
    return None


def _save_to_inbox(project: dict, text: str) -> Path:
    """Save a text message to project's ai/inbox/ directory."""
    inbox_dir = Path(project["path"]) / "ai" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    route = detect_route(text)

    filename = f"{timestamp}-telegram.md"
    filepath = inbox_dir / filename

    content = (
        f"# Idea: {timestamp}\n"
        f"**Source:** telegram\n"
        f"**Route:** {route}\n"
        f"**Status:** new\n"
        f"---\n"
        f"{text}\n"
    )
    filepath.write_text(content, encoding="utf-8")
    logger.info("Saved to inbox: %s (route=%s)", filepath, route)
    return filepath


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages in project topics -> save to inbox."""
    if not is_authorized(update.effective_user.id):
        return

    topic_id = get_topic_id(update)
    if not topic_id:
        return  # Ignore messages in General topic

    project = db.get_project_by_topic(topic_id)
    if not project:
        return  # Topic not linked to a project

    text = update.message.text
    if not text or text.startswith("/"):
        return

    _save_to_inbox(project, text)
    route = detect_route(text)

    await update.message.reply_text(
        f"Saved to inbox (route: `{route}`).\nOrchestrator will process on next cycle.",
        parse_mode="Markdown",
    )


def main() -> None:
    """Start the Telegram bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("run", cmd_run))
    application.add_handler(CommandHandler("pause", cmd_pause))
    application.add_handler(CommandHandler("resume", cmd_resume))

    # Text message handler (must be after commands)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Starting DLD Telegram bot (PTB v21.9+)")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
