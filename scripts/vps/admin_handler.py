#!/usr/bin/env python3
"""
Module: admin_handler
Role: /addproject ConversationHandler wizard + /nexussync command.
Uses: db.py (add_project, get_project_state, get_project_by_topic),
      subprocess (pueue group add, nexus-cache-refresh.sh)
Used by: telegram-bot.py (ConversationHandler + /nexussync registered in main())
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

sys.path.insert(0, str(Path(__file__).parent))
import db

logger = logging.getLogger("dld-bot.admin")

SCRIPT_DIR = Path(__file__).parent
ALLOWED_USERS = set(
    int(uid.strip())
    for uid in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
)

# Conversation states
PROJECT_ID, PATH, TOPIC, PROVIDER, CONFIRM = range(5)


def _is_authorized(user_id: int) -> bool:
    return True if not ALLOWED_USERS else user_id in ALLOWED_USERS


async def start_addproject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: /addproject — ask for project_id."""
    if not _is_authorized(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "Register new project.\n\nEnter project ID (e.g., `my-saas-app`):",
        parse_mode="Markdown",
    )
    return PROJECT_ID


async def receive_project_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate project_id is unique, store in user_data."""
    pid = update.message.text.strip().lower()
    if not pid or " " in pid:
        await update.message.reply_text("Invalid ID (no spaces). Try again:")
        return PROJECT_ID
    existing = db.get_project_state(pid)
    if existing:
        await update.message.reply_text(
            f"Project `{pid}` already registered. Choose another ID:",
            parse_mode="Markdown",
        )
        return PROJECT_ID
    context.user_data["addproject"] = {"project_id": pid}
    await update.message.reply_text(
        "Enter absolute path on VDS (e.g., `/home/ubuntu/projects/my-app`):"
    )
    return PATH


async def receive_path(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate path exists and is a git repo."""
    path = update.message.text.strip()
    if not path.startswith("/"):
        await update.message.reply_text("Path must be absolute (start with /). Try again:")
        return PATH
    p = Path(path)
    if not p.is_dir():
        await update.message.reply_text("Path not found. Check the path and try again:")
        return PATH
    if not (p / ".git").is_dir():
        await update.message.reply_text(
            "Not a git repo (no .git/). Initialize git first, then try again:"
        )
        return PATH
    context.user_data["addproject"]["path"] = path
    await update.message.reply_text(
        "Send any message in the project's forum topic to capture its topic_id.\n"
        "Or enter the topic_id manually (a number):"
    )
    return TOPIC


async def receive_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Capture topic_id from current thread or manual input."""
    text = update.message.text.strip()
    thread_id = getattr(update.effective_message, "message_thread_id", None)

    topic_id = None
    if text.isdigit():
        topic_id = int(text)
    elif thread_id and thread_id != 1:
        topic_id = thread_id

    if topic_id is None:
        await update.message.reply_text(
            "Could not detect topic. Enter topic_id as a number, or send from the correct topic:"
        )
        return TOPIC

    # Check topic not already bound within this chat
    chat = update.effective_chat
    chat_id = int(chat.id) if chat else None
    existing = db.get_project_by_topic(topic_id, chat_id=chat_id)
    if existing:
        await update.message.reply_text(
            f"Topic {topic_id} already bound to `{existing['project_id']}`. Choose another topic:",
            parse_mode="Markdown",
        )
        return TOPIC

    context.user_data["addproject"]["topic_id"] = topic_id
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Claude", callback_data="addproject:provider:claude"),
                InlineKeyboardButton("Codex", callback_data="addproject:provider:codex"),
                InlineKeyboardButton("Gemini", callback_data="addproject:provider:gemini"),
            ]
        ]
    )
    await update.message.reply_text("Default provider?", reply_markup=keyboard)
    return PROVIDER


async def handle_provider_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle inline keyboard provider selection."""
    query = update.callback_query
    await query.answer()
    provider = query.data.split(":")[-1]
    context.user_data["addproject"]["provider"] = provider

    data = context.user_data["addproject"]
    summary = (
        f"*Register project:*\n"
        f"ID: `{data['project_id']}`\n"
        f"Path: `{data['path']}`\n"
        f"Topic: `{data['topic_id']}`\n"
        f"Provider: `{provider}`"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data="addproject:confirm"),
                InlineKeyboardButton("Cancel", callback_data="addproject:cancel"),
            ]
        ]
    )
    await query.edit_message_text(summary, reply_markup=keyboard, parse_mode="Markdown")
    return CONFIRM


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm: insert into DB, create pueue group, notify."""
    query = update.callback_query
    await query.answer()

    data = context.user_data.get("addproject", {})
    if not data:
        await query.edit_message_text("No registration data found. Start over with /addproject.")
        return ConversationHandler.END

    pid = data["project_id"]
    path = data["path"]
    topic_id = data["topic_id"]
    provider = data.get("provider", "claude")

    # Insert into SQLite
    chat = update.effective_chat
    chat_id = int(chat.id) if chat else None
    db.add_project(pid, path, topic_id, provider, chat_id=chat_id)

    # Create pueue group for the project
    try:
        subprocess.run(["pueue", "group", "add", pid], capture_output=True, text=True, timeout=5)
        subprocess.run(
            ["pueue", "parallel", "1", "--group", pid], capture_output=True, text=True, timeout=5
        )
    except Exception as e:
        logger.warning("pueue group creation failed for %s: %s", pid, e)

    # Trigger immediate Nexus cache refresh for new project
    cache_script = SCRIPT_DIR / "nexus-cache-refresh.sh"
    if cache_script.is_file():
        try:
            subprocess.run(["bash", str(cache_script)], capture_output=True, timeout=30)
        except Exception:
            pass

    context.user_data.pop("addproject", None)
    await query.edit_message_text(
        f"Project `{pid}` registered!\n"
        f"Path: `{path}`\n"
        f"Topic: {topic_id}\n"
        f"Provider: {provider}\n"
        f"Pueue group: {pid}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def handle_cancel_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel registration wizard."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("addproject", None)
    await query.edit_message_text("Registration cancelled.")
    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /cancel during wizard."""
    context.user_data.pop("addproject", None)
    await update.message.reply_text("Registration cancelled.")
    return ConversationHandler.END


def create_addproject_handler() -> ConversationHandler:
    """Build and return the /addproject ConversationHandler."""
    return ConversationHandler(
        entry_points=[CommandHandler("addproject", start_addproject)],
        states={
            PROJECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_project_id)],
            PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_path)],
            TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_topic)],
            PROVIDER: [
                CallbackQueryHandler(handle_provider_select, pattern=r"^addproject:provider:"),
            ],
            CONFIRM: [
                CallbackQueryHandler(handle_confirm, pattern=r"^addproject:confirm$"),
                CallbackQueryHandler(handle_cancel_wizard, pattern=r"^addproject:cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        conversation_timeout=120,
    )


async def cmd_nexussync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run nexus-cache-refresh.sh and report result."""
    if not _is_authorized(update.effective_user.id):
        return

    cache_script = SCRIPT_DIR / "nexus-cache-refresh.sh"
    if not cache_script.is_file():
        await update.message.reply_text("nexus-cache-refresh.sh not found.")
        return

    try:
        result = subprocess.run(
            ["bash", str(cache_script)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            # Count cached files
            cache_dir = Path("/var/dld/nexus-cache")
            count = len(list(cache_dir.glob("*.json"))) if cache_dir.is_dir() else 0
            await update.message.reply_text(f"Synced {count} projects from Nexus.")
        else:
            await update.message.reply_text(
                f"Nexus sync failed (exit {result.returncode}):\n{result.stderr[:200]}"
            )
    except subprocess.TimeoutExpired:
        await update.message.reply_text("Nexus sync timed out (60s).")
    except Exception as e:
        await update.message.reply_text(f"Nexus sync error: {e}")
