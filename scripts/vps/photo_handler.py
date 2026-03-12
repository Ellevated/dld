#!/usr/bin/env python3
"""
Module: photo_handler
Role: Telegram photo message handler — saves screenshots to inbox.
Uses: telegram-bot._save_to_inbox, telegram-bot.is_authorized,
      telegram-bot.get_topic_id, telegram-bot.detect_route, db.get_project_by_topic
Used by: telegram-bot (registered as MessageHandler for PHOTO)
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("dld-bot.photo")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages in project forum topics.

    Downloads the photo, saves to ai/inbox/img/, creates inbox file
    with markdown image link and caption text.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    import db

    tb = sys.modules.get("telegram_bot") or sys.modules.get("__main__")
    is_authorized = tb.is_authorized
    get_topic_id = tb.get_topic_id
    detect_route = tb.detect_route

    if not is_authorized(update.effective_user.id):
        return

    topic_id = get_topic_id(update)
    project = db.get_project_by_topic(topic_id) if topic_id else None
    if not project:
        return

    # Download the highest resolution photo
    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    photo_bytes = bytes(await tg_file.download_as_bytearray())

    # Save photo to ai/inbox/img/
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    inbox_dir = Path(project["path"]) / "ai" / "inbox"
    img_dir = inbox_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    img_filename = f"{timestamp}.jpg"
    img_path = img_dir / img_filename
    img_path.write_bytes(photo_bytes)
    logger.info("Saved photo: %s (%d bytes)", img_path, len(photo_bytes))

    # Build inbox text from caption
    caption = update.message.caption or ""
    if caption:
        route = detect_route(caption)
        text = f"![screenshot](img/{img_filename})\n\n{caption}"
    else:
        route = "spark"
        text = (
            f"![screenshot](img/{img_filename})\n\n"
            f"Скриншот без описания. Проанализируй что на нём."
        )

    # Create inbox file
    filepath = inbox_dir / f"{timestamp}-photo.md"
    filepath.write_text(
        f"# Idea: {timestamp}\n"
        f"**Source:** telegram\n"
        f"**Route:** {route}\n"
        f"**Status:** new\n"
        f"---\n"
        f"{text}\n",
        encoding="utf-8",
    )
    logger.info("Saved photo inbox: %s (route=%s)", filepath, route)
    _ROUTE_LABELS = {
        "spark": "Создам спеку",
        "spark_bug": "Разберу баг",
        "architect": "Запущу архитектора",
        "council": "Соберу консилиум",
        "bughunt": "Охота на баги",
    }
    label = _ROUTE_LABELS.get(route, "Обработаю")
    await update.message.reply_text(f"📸 Принято. {label} на следующем цикле.")
