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


async def send_spec_approval(
    project_id: str, spec_id: str, title: str, problem: str, tasks_count: int
) -> bool:
    """Send spec approval message with Approve/Rework/Cancel buttons."""
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    project = db.get_project_state(project_id)
    if not project:
        print(f"[notify] Project not found: {project_id}", file=sys.stderr)
        return False

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("[notify] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", file=sys.stderr)
        return False

    topic_id = project.get("topic_id")
    thread_id = topic_id if topic_id and topic_id != 1 else None

    # Clean title: remove spec ID prefix if already present (e.g. "Feature: [FTR-242] ...")
    clean_title = title
    if spec_id in clean_title:
        import re
        clean_title = re.sub(r'(?:Feature|Bug Fix|Tech|Arch):\s*\[' + re.escape(spec_id) + r'\]\s*', '', clean_title).strip()
        clean_title = clean_title.lstrip('—– ').strip()

    # Truncate long summaries (result_preview from spark can be 500+ chars)
    summary = problem[:400] if problem else "—"

    parts = [f"\U0001f4cb {spec_id} — {clean_title}"]
    parts.append(f"Проект: {project_id}")
    parts.append("")
    parts.append(summary)
    if tasks_count > 0:
        parts.append(f"\nЗадач: {tasks_count}")
    text = "\n".join(parts)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\u2705 В работу", callback_data=f"spec_approve:{project_id}:{spec_id}"),
            InlineKeyboardButton("\u270f\ufe0f Доработать", callback_data=f"spec_rework:{project_id}:{spec_id}"),
            InlineKeyboardButton("\u274c Отклонить", callback_data=f"spec_reject:{project_id}:{spec_id}"),
        ]
    ])

    bot = Bot(token=token)
    try:
        await bot.send_message(
            chat_id=int(chat_id),
            message_thread_id=thread_id,
            text=text,
            reply_markup=keyboard,
        )
        return True
    except Exception as e:
        print(f"[notify] Failed to send spec approval: {e}", file=sys.stderr)
        return False
    finally:
        await bot.shutdown()


def main() -> None:
    """CLI entrypoint: notify.py <project_id> <message>
    or: notify.py --spec-approval <project_id> <spec_id> <title> <problem> <tasks_count>
    """
    if len(sys.argv) >= 2 and sys.argv[1] == "--spec-approval":
        if len(sys.argv) < 7:
            print(
                "Usage: notify.py --spec-approval <project_id> <spec_id> <title> <problem> <tasks_count>",
                file=sys.stderr,
            )
            sys.exit(1)
        success = asyncio.run(
            send_spec_approval(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6]))
        )
        sys.exit(0 if success else 1)

    if len(sys.argv) < 3:
        print("Usage: notify.py <project_id> <message>", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    message = sys.argv[2]

    success = asyncio.run(send_to_project(project_id, message))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
