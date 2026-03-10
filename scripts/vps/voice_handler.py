#!/usr/bin/env python3
"""
Module: voice_handler
Role: Groq Whisper STT + Telegram voice message handler.
Uses: groq SDK, telegram-bot._save_to_inbox, telegram-bot.is_authorized,
      telegram-bot.get_topic_id, db.get_project_by_topic
Used by: telegram-bot (registered as MessageHandler for VOICE)
"""

import asyncio
import io
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("dld-bot.voice")


def transcribe_voice(ogg_bytes: bytes) -> str:
    """Transcribe OGG voice bytes via Groq Whisper API.

    Args:
        ogg_bytes: Raw OGG audio bytes from Telegram.

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError: If GROQ_API_KEY is missing.
        groq.RateLimitError: On 429 (caller should retry).
        groq.InternalServerError: On 5xx.
    """
    import groq  # lazy import — not everyone has it installed

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")

    client = groq.Groq(api_key=api_key)
    buf = io.BytesIO(ogg_bytes)
    buf.name = "voice.ogg"  # Groq requires a filename to detect format

    transcription = client.audio.transcriptions.create(
        file=buf,
        model="whisper-large-v3",
        language="ru",
        response_format="text",
    )
    # response_format="text" returns a plain string, not an object
    return transcription if isinstance(transcription, str) else transcription.text


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB async handler for voice messages in project forum topics.

    Imports from telegram_bot module at call time to avoid circular imports.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    import db

    # telegram-bot.py has a hyphen so it can't be imported normally.
    # When handle_voice is called, telegram-bot.py is __main__ (or already
    # loaded into sys.modules["telegram_bot"] by the time this handler fires).
    tb = sys.modules.get("telegram_bot") or sys.modules.get("__main__")

    is_authorized = tb.is_authorized
    get_topic_id = tb.get_topic_id
    _save_to_inbox = tb._save_to_inbox

    if not is_authorized(update.effective_user.id):
        return

    topic_id = get_topic_id(update)
    project = db.get_project_by_topic(topic_id) if topic_id else None
    if not project:
        return

    voice = update.message.voice
    tg_file = await voice.get_file()
    ogg_bytes = bytes(await tg_file.download_as_bytearray())

    import groq as groq_module

    try:
        text = transcribe_voice(ogg_bytes)
    except RuntimeError:
        await update.message.reply_text("Voice not configured")
        return
    except groq_module.RateLimitError:
        await asyncio.sleep(2)
        try:
            text = transcribe_voice(ogg_bytes)
        except Exception as exc:
            logger.error("Groq retry failed: %s", exc)
            await update.message.reply_text("Transcription error")
            return
    except groq_module.InternalServerError:
        await update.message.reply_text("Voice unavailable, send text")
        return
    except Exception as exc:
        logger.error("Voice transcription error: %s", exc)
        await update.message.reply_text("Transcription error")
        return

    _save_to_inbox(project, text)
    await update.message.reply_text(f"Записано: {text[:100]}...")
