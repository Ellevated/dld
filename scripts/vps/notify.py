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


def _tg_escape(text: str) -> str:
    """Escape Markdown special chars for Telegram."""
    for ch in ("*", "_", "`", "["):
        text = text.replace(ch, "\\" + ch)
    # Strip surrogates
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    return text


def _parse_spec_for_approval(project_path: str, spec_id: str) -> dict:
    """Parse spec file and extract fields for approval message.

    Returns dict with keys: title, why, scope, tasks, approach, priority.
    All values are strings (or list of strings for tasks).
    Returns empty dict on any error.
    """
    import glob as glob_mod
    import re

    result: dict = {}
    pattern = f"{project_path}/ai/features/{spec_id}*"
    matches = glob_mod.glob(pattern)
    if not matches:
        return result

    try:
        content = Path(matches[0]).read_text(encoding="utf-8")
    except Exception:
        return result

    lines = content.split("\n")

    # Title from first # heading
    for line in lines[:5]:
        if line.startswith("# "):
            result["title"] = line[2:].strip()
            break

    # Priority from Status line
    m = re.search(r"\*\*Priority:\*\*\s*(\S+)", content)
    if m:
        result["priority"] = m.group(1)

    # Extract sections by ## headers
    sections: dict[str, list[str]] = {}
    current_section = ""
    for line in lines:
        if line.startswith("## "):
            current_section = line[3:].strip().lower()
            sections[current_section] = []
        elif current_section and line.strip() != "---":
            sections.setdefault(current_section, []).append(line)

    # Why: first meaningful paragraph from ## Why
    why_lines = sections.get("why", [])
    if why_lines:
        # Take first non-empty lines until blank line or 3 lines
        why_text = []
        for wl in why_lines:
            stripped = wl.strip()
            if not stripped and why_text:
                break
            if stripped:
                why_text.append(stripped)
            if len(why_text) >= 3:
                break
        result["why"] = " ".join(why_text)

    # Scope: extract "In scope" items
    scope_lines = sections.get("scope", [])
    in_scope_items = []
    in_scope = False
    for sl in scope_lines:
        if "in scope" in sl.lower():
            in_scope = True
            continue
        if "out of scope" in sl.lower():
            in_scope = False
            continue
        if in_scope and sl.strip().startswith("-"):
            item = sl.strip().lstrip("- ").strip()
            if item:
                in_scope_items.append(item)
    if in_scope_items:
        result["scope"] = "; ".join(in_scope_items[:4])

    # Tasks: from ## Implementation Plan — ### Task N: title
    tasks = []
    for line in lines:
        m = re.match(r"^###\s+Task\s+\d+[:\s]+(.+)", line)
        if m:
            task_name = m.group(1).strip()
            # Clean up task name
            task_name = re.sub(r"\*\*Type:\*\*.*", "", task_name).strip()
            if task_name:
                tasks.append(task_name)
    if tasks:
        result["tasks"] = tasks

    # Approach: selected approach summary
    approach_lines = sections.get("approaches", [])
    for al in approach_lines:
        if al.strip().startswith("**Summary:**"):
            result["approach"] = al.strip().replace("**Summary:**", "").strip()
            break
    # Fallback: from ### Selected rationale
    if "approach" not in result:
        for al in approach_lines:
            if "rationale" in al.lower() and "**" in al:
                clean = re.sub(r"\*\*.*?\*\*\s*", "", al).strip()
                if clean:
                    result["approach"] = clean[:200]
                    break

    return result


async def send_spec_approval(
    project_id: str, spec_id: str, title: str = "", problem: str = "", tasks_count: int = 0
) -> bool:
    """Send spec approval message with Approve/Rework/Cancel buttons.

    Reads the actual spec file to build an informative message with:
    - Why (problem description)
    - Scope summary
    - Task list with names
    Falls back to passed args if spec file is unreadable.
    """
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

    # Read spec file for rich content
    spec_data = _parse_spec_for_approval(project["path"], spec_id)

    # Use spec data or fall back to passed args
    display_title = spec_data.get("title") or title
    # Clean title: remove spec ID prefix if already present
    if spec_id in display_title:
        import re
        display_title = re.sub(
            r'(?:Feature|Bug Fix|Tech|Arch):\s*\[' + re.escape(spec_id) + r'\]\s*',
            '', display_title,
        ).strip().lstrip('— ').strip()

    why = spec_data.get("why", "")
    scope = spec_data.get("scope", "")
    tasks = spec_data.get("tasks", [])
    approach = spec_data.get("approach", "")
    priority = spec_data.get("priority", "")

    # Build message
    header = f"\U0001f4cb *{spec_id}* — {display_title}"
    if priority:
        header += f" ({priority})"

    parts = [header, ""]

    if why:
        parts.append(f"*Проблема:* {_tg_escape(why[:300])}")
        parts.append("")

    if approach:
        parts.append(f"*Решение:* {_tg_escape(approach[:200])}")
        parts.append("")

    if scope:
        parts.append(f"*Скоуп:* {_tg_escape(scope[:200])}")
        parts.append("")

    if tasks:
        parts.append(f"*Задачи ({len(tasks)}):*")
        for i, task_name in enumerate(tasks[:6], 1):
            parts.append(f"  {i}. {_tg_escape(task_name)}")
        if len(tasks) > 6:
            parts.append(f"  ... и ещё {len(tasks) - 6}")
        parts.append("")
    elif tasks_count > 0:
        parts.append(f"Задач: {tasks_count}")
        parts.append("")

    # Fallback: if no spec data at all, show old-style summary
    if not why and not tasks and problem:
        summary = problem[:400]
        summary = summary.encode("utf-8", errors="replace").decode("utf-8")
        parts.append(_tg_escape(summary))
        parts.append("")

    text = "\n".join(parts).strip()

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
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        print(f"[notify] Failed to send spec approval: {e}", file=sys.stderr)
        # Retry without Markdown on parse error
        if "parse entities" in str(e).lower():
            try:
                plain = text.replace("*", "").replace("_", "").replace("`", "")
                await bot.send_message(
                    chat_id=int(chat_id),
                    message_thread_id=thread_id,
                    text=plain,
                    reply_markup=keyboard,
                )
                return True
            except Exception as e2:
                print(f"[notify] Retry without Markdown also failed: {e2}", file=sys.stderr)
        return False
    finally:
        await bot.shutdown()


def main() -> None:
    """CLI entrypoint: notify.py <project_id> <message>
    or: notify.py --spec-approval <project_id> <spec_id> <title> <problem> <tasks_count>
    """
    if len(sys.argv) >= 2 and sys.argv[1] == "--spec-approval":
        # New: notify.py --spec-approval <project_id> <spec_id> [title] [problem] [tasks_count]
        # Only project_id and spec_id are required — rest is read from spec file
        if len(sys.argv) < 4:
            print(
                "Usage: notify.py --spec-approval <project_id> <spec_id> [title] [problem] [tasks_count]",
                file=sys.stderr,
            )
            sys.exit(1)
        title = sys.argv[4] if len(sys.argv) > 4 else ""
        problem = sys.argv[5] if len(sys.argv) > 5 else ""
        tasks_count = int(sys.argv[6]) if len(sys.argv) > 6 else 0
        success = asyncio.run(
            send_spec_approval(sys.argv[2], sys.argv[3], title, problem, tasks_count)
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
