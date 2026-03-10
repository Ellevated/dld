#!/usr/bin/env python3
"""
DLD VPS Autonomous Pipeline — Telegram Bot
Receives ideas (text + voice) and saves them to ai/inbox/.

Usage:
    python3 scripts/vps/telegram-bot.py

Requires:
    pip install python-telegram-bot openai groq
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load config
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try project root
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ── Configuration ──

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USERS = {
    int(uid.strip())
    for uid in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
}
PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", Path(__file__).parent.parent.parent))
INBOX_DIR = Path(os.environ.get("INBOX_DIR", PROJECT_DIR / "ai" / "inbox"))
WHISPER_PROVIDER = os.environ.get("WHISPER_PROVIDER", "groq")

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("dld-bot")


# ── Auth ──

def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS:
        log.warning("TELEGRAM_ALLOWED_USERS not set — rejecting all users")
        return False
    return user_id in ALLOWED_USERS


# ── Voice Transcription ──

async def transcribe_voice(file_path: str) -> str:
    """Transcribe voice message using configured provider."""
    if WHISPER_PROVIDER == "groq":
        return await _transcribe_groq(file_path)
    elif WHISPER_PROVIDER == "openai":
        return await _transcribe_openai(file_path)
    else:
        raise ValueError(f"Unknown WHISPER_PROVIDER: {WHISPER_PROVIDER}")


async def _transcribe_groq(file_path: str) -> str:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(file_path), f),
            model="whisper-large-v3",
            language="ru",
        )
    return transcription.text


async def _transcribe_openai(file_path: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=f,
            model="whisper-1",
            language="ru",
        )
    return transcription.text


# ── Inbox ──

def save_to_inbox(text: str, source: str, user_name: str) -> Path:
    """Save idea to ai/inbox/ as markdown file."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    filename = f"{timestamp}-{source}.md"
    filepath = INBOX_DIR / filename

    content = f"""# Idea: {timestamp}

**Source:** {source}
**From:** {user_name}
**Date:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
**Status:** new

---

{text.strip()}
"""
    filepath.write_text(content, encoding="utf-8")
    log.info("Saved idea to %s", filepath)
    return filepath


# ── Handlers ──

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(
        "DLD Autonomous Pipeline\n\n"
        "Send me ideas (text or voice) — they'll go into the inbox.\n\n"
        "Commands:\n"
        "/status — current backlog status\n"
        "/queue — list queued specs\n"
        "/inbox — list pending ideas\n"
        "/run — trigger autopilot now"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    backlog = PROJECT_DIR / "ai" / "backlog.md"
    if not backlog.exists():
        await update.message.reply_text("No backlog.md found.")
        return

    content = backlog.read_text(encoding="utf-8")
    # Count statuses
    counts = {}
    for status in ["draft", "queued", "in_progress", "blocked", "done"]:
        counts[status] = content.lower().count(f"| {status}")

    inbox_count = len(list(INBOX_DIR.glob("*.md"))) if INBOX_DIR.exists() else 0

    msg = (
        f"Inbox: {inbox_count} ideas\n"
        f"Draft: {counts['draft']}\n"
        f"Queued: {counts['queued']}\n"
        f"In progress: {counts['in_progress']}\n"
        f"Blocked: {counts['blocked']}\n"
        f"Done: {counts['done']}"
    )
    await update.message.reply_text(msg)


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    backlog = PROJECT_DIR / "ai" / "backlog.md"
    if not backlog.exists():
        await update.message.reply_text("No backlog.md found.")
        return

    lines = backlog.read_text(encoding="utf-8").split("\n")
    queued = [ln for ln in lines if "queued" in ln.lower() or "resumed" in ln.lower()]
    if not queued:
        await update.message.reply_text("No queued specs.")
        return
    await update.message.reply_text("Queued:\n" + "\n".join(queued[:15]))


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    if not INBOX_DIR.exists():
        await update.message.reply_text("Inbox empty.")
        return

    files = sorted(INBOX_DIR.glob("*.md"))
    if not files:
        await update.message.reply_text("Inbox empty.")
        return

    msg = "Inbox:\n"
    for f in files[:20]:
        msg += f"- {f.name}\n"
    await update.message.reply_text(msg)


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    await update.message.reply_text("Triggering autopilot... (touch .run-now)")
    trigger = PROJECT_DIR / ".run-now"
    trigger.touch()


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return

    text = update.message.text
    user = update.effective_user
    user_name = user.full_name or user.username or str(user.id)

    filepath = save_to_inbox(text, "text", user_name)
    await update.message.reply_text(f"Saved to inbox: {filepath.name}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return

    user = update.effective_user
    user_name = user.full_name or user.username or str(user.id)

    await update.message.reply_text("Transcribing voice...")

    voice = update.message.voice or update.message.audio
    file = await context.bot.get_file(voice.file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await file.download_to_drive(tmp_path)

    try:
        transcript = await transcribe_voice(tmp_path)
    finally:
        os.unlink(tmp_path)

    filepath = save_to_inbox(transcript, "voice", user_name)
    # Show first 200 chars of transcript
    preview = transcript[:200] + ("..." if len(transcript) > 200 else "")
    await update.message.reply_text(
        f"Transcribed & saved:\n\n{preview}\n\nFile: {filepath.name}"
    )


# ── Main ──

def main() -> None:
    log.info("Starting DLD Telegram Bot")
    log.info("Project: %s", PROJECT_DIR)
    log.info("Inbox: %s", INBOX_DIR)
    log.info("Allowed users: %s", ALLOWED_USERS)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("inbox", cmd_inbox))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    log.info("Bot started. Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
