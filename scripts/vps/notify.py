#!/usr/bin/env python3
"""
Module: notify
Role: Standalone Telegram notification helper for bash scripts.
Uses: db.py, python-telegram-bot
Used by: pueue-callback.sh, orchestrator.sh, qa-loop.sh

Usage: python3 notify.py <project_id> <message>
"""

import asyncio
import os
import sys
from pathlib import Path

# Add script dir to path for db import
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import db


async def _send_message(text: str, thread_id: int | None = None) -> bool:
    """Send a Telegram message to TELEGRAM_CHAT_ID, optionally in a forum thread."""
    from telegram import Bot

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("[notify] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", file=sys.stderr)
        return False

    bot = Bot(token=token)
    try:
        await bot.send_message(
            chat_id=int(chat_id),
            message_thread_id=thread_id,
            text=text,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        print(f"[notify] Failed to send: {e}", file=sys.stderr)
        return False
    finally:
        await bot.shutdown()


async def send_to_project(project_id: str, text: str) -> bool:
    """Send a message to a project's Telegram topic.

    Looks up topic_id from SQLite, sends via Bot API.
    Falls back to General topic (no thread_id) if topic_id is None.
    """
    project = db.get_project_state(project_id)
    if project is None:
        print(f"[notify] Project not found: {project_id}", file=sys.stderr)
        return False

    topic_id = project.get("topic_id")
    # DA-4: message_thread_id=1 is General topic bug. Pass None instead.
    thread_id = topic_id if topic_id and topic_id != 1 else None
    return await _send_message(text, thread_id=thread_id)


async def send_to_general(text: str) -> bool:
    """Send a message to the General topic (no thread_id)."""
    return await _send_message(text)


def main() -> None:
    """CLI entrypoint: notify.py <project_id> <message>"""
    if len(sys.argv) < 3:
        print("Usage: notify.py <project_id> <message>", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    message = sys.argv[2]

    success = asyncio.run(send_to_project(project_id, message))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
