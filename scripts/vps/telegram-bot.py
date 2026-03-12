#!/usr/bin/env python3
"""
Module: telegram-bot
Role: Telegram bot with forum topic routing for multi-project orchestration.
Uses: db.py, admin_handler.py, python-telegram-bot v21.9+
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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

sys.path.insert(0, str(Path(__file__).parent))
import db
from admin_handler import cmd_nexussync, create_addproject_handler
from approve_handler import (
    handle_approve_all,
    handle_finding_approve,
    handle_finding_reject,
    handle_launch_review,
    handle_project_toggle,
    handle_reject_all,
    handle_rework_comment,
    handle_spec_approve,
    handle_spec_reject,
    handle_spec_rework,
    register_evening_job,
)
from photo_handler import handle_photo
from voice_handler import handle_voice

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("dld-bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
ALLOWED_USERS = set(
    int(uid.strip())
    for uid in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
)
SCRIPT_DIR = Path(__file__).parent

# fmt: off
ROUTE_PATTERNS: dict[str, list[str]] = {
    "qa":        ["проверь как работает", "протестируй", "потыкай", "ручное тестирование",
                  "проведи qa", "qa тест", "тест лигал", "тест воронк", "проверь воронку",
                  "проверь на проде", "check how", "manual test", "smoke test"],
    "architect": ["архитектура", "спроектируй", "домены", "как устроить", "интеграция",
                  "design system", "bounded context", "data flow", "инфраструктура",
                  "схема данных", "миграция", "рефакторинг архитектуры"],
    "council":   ["консилиум", "сравни подходы", "что лучше", "trade-off",
                  "выбери между", "стоит ли", "плюсы и минусы", "совет директоров"],
    "bughunt":   ["баг хант", "охота на баги", "глубокий анализ багов", "много багов",
                  "всё сломалось", "системные проблемы", "deep analysis", "bug hunt",
                  "командный аудит багов"],
    "spark_bug": ["баг", "ошибка", "не работает", "сломалось", "падает",
                  "crash", "fix", "broken", "регрессия", "regression"],
    "reflect":   ["рефлексия", "рефлект", "что мы узнали", "reflect"],
    "scout":     ["разведка", "исследуй", "найди информацию", "scout", "research"],
}
# fmt: on


def detect_route(text: str) -> str:
    text_lower = text.lower()
    for route, keywords in ROUTE_PATTERNS.items():
        if any(kw in text_lower for kw in keywords):
            return route
    return "spark"


def is_authorized(user_id: int) -> bool:
    return True if not ALLOWED_USERS else user_id in ALLOWED_USERS


def get_topic_id(update: Update) -> int | None:
    thread_id = getattr(update.effective_message, "message_thread_id", None)
    return None if thread_id == 1 else thread_id  # DA-4: thread_id=1 is General topic


def _resolve_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    args = context.args or []
    if args:
        return db.get_project_state(args[0])
    topic_id = get_topic_id(update)
    return db.get_project_by_topic(topic_id) if topic_id else None


def _save_to_inbox(project: dict, text: str) -> Path:
    inbox_dir = Path(project["path"]) / "ai" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    route = detect_route(text)
    filepath = inbox_dir / f"{timestamp}-telegram.md"
    filepath.write_text(
        f"# Idea: {timestamp}\n**Source:** telegram\n**Route:** {route}\n**Status:** new\n---\n{text}\n",
        encoding="utf-8",
    )
    logger.info("Saved to inbox: %s (route=%s)", filepath, route)
    return filepath


# fmt: off
def _submit_to_pueue(project: dict, task_id: str) -> bool:
    """Submit task to Pueue. Returns True on success."""
    pid = project["project_id"]
    task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
                f"claude -p /autopilot {task_id}", project.get("provider", "claude"), "autopilot"]
    r = subprocess.run(
        ["pueue", "add", "--group", pid, "--label", f"{pid}:{task_id}", "--print-task-id", "--"] + task_cmd,
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0:
        logger.info("Submitted %s:%s to pueue (job %s)", pid, task_id, r.stdout.strip())
        return True
    logger.error("pueue add failed: %s", r.stderr)
    return False
# fmt: on


# fmt: off
async def auto_approve_start(
    project_id: str, task_id: str, summary: str, scope: str,
    topic_id: int, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Send approval prompt to topic with countdown; schedule auto-fire."""
    project = db.get_project_state(project_id)
    if not project:
        return
    timeout = int(project.get("auto_approve_timeout", 30))
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("В работу", callback_data=f"approve:{project_id}:{task_id}"),
        InlineKeyboardButton("Отмена",  callback_data=f"cancel:{project_id}:{task_id}"),
    ]])
    countdown = f"Автостарт через {timeout}с..." if timeout > 0 else "Жду подтверждения."
    msg = await context.bot.send_message(
        chat_id=CHAT_ID, message_thread_id=topic_id,
        text=f"Спека готова: {task_id}\n{summary}\nОбъём: {scope}\n\n{countdown}",
        reply_markup=keyboard,
    )
    if timeout > 0:
        context.job_queue.run_once(
            _auto_approve_fire, when=timeout,
            data={"project_id": project_id, "task_id": task_id,
                  "chat_id": CHAT_ID, "message_id": msg.message_id, "topic_id": topic_id},
            name=f"approve:{project_id}:{task_id}", chat_id=CHAT_ID,
        )
# fmt: on


# fmt: off
async def _auto_approve_fire(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: timeout fired, submit to Pueue."""
    d = context.job.data
    project = db.get_project_state(d["project_id"])
    if not project:
        return
    ok = _submit_to_pueue(project, d["task_id"])
    label = "Автостарт —" if ok else "Ошибка запуска:"
    await context.bot.edit_message_text(
        chat_id=d["chat_id"], message_id=d["message_id"],
        text=f"{label} {d['task_id']}",
    )
# fmt: on


async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback: [Approve] button pressed — cancel timer, submit immediately."""
    query = update.callback_query
    await query.answer()
    _, project_id, task_id = query.data.split(":", 2)
    job_name = f"approve:{project_id}:{task_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    project = db.get_project_state(project_id)
    if not project:
        await query.edit_message_text(f"Проект {project_id} не найден.")
        return
    success = _submit_to_pueue(project, task_id)
    await query.edit_message_text(
        f"Запущено: {task_id}" if success else f"Ошибка запуска {task_id}"
    )


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback: [Cancel] button pressed — cancel timer, do not submit."""
    query = update.callback_query
    await query.answer()
    _, project_id, task_id = query.data.split(":", 2)
    for job in context.job_queue.get_jobs_by_name(f"approve:{project_id}:{task_id}"):
        job.schedule_removal()
    await query.edit_message_text(f"Отменено: {task_id}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    args = context.args or []
    topic_id = get_topic_id(update)
    if args:
        project = db.get_project_state(args[0])
        if not project:
            await update.message.reply_text(
                f"Проект `{args[0]}` не найден.", parse_mode="Markdown"
            )
            return
        await _send_project_status(update, project)
    elif topic_id:
        project = db.get_project_by_topic(topic_id)
        if project:
            await _send_project_status(update, project)
        else:
            await update.message.reply_text("Этот топик не привязан к проекту.")
    else:
        projects = db.get_all_projects()
        if not projects:
            await update.message.reply_text("Проекты не настроены.")
            return
        # fmt: off
        icons = {"idle": "⚪", "running": "🟢", "qa_pending": "🟡", "failed": "🔴",
                 "night_reviewing": "🔍", "night_pending": "🌙", "night_failed": "💀"}
        # fmt: on
        lines = ["*Все проекты:*\n"] + [
            f"{icons.get(p['phase'], '⚫')} `{p['project_id']}` — {p['phase']}"
            + (f" ({p['current_task']})" if p.get("current_task") else "")
            for p in projects
        ]
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _send_project_status(update: Update, project: dict) -> None:
    pueue_info = ""
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            tasks = json.loads(result.stdout).get("tasks", {})
            project_tasks = [
                t
                for t in tasks.values()
                if t.get("label", "").startswith(project["project_id"] + ":")
            ]
            if project_tasks:
                pueue_info = "\n*Pueue tasks:*\n" + "\n".join(
                    f"  #{t['id']} {t.get('label', '')} — {t.get('status', '?')}"
                    for t in project_tasks[-3:]
                )
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
        f"Path: `{project['path']}`{pueue_info}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    args = context.args or []
    topic_id = get_topic_id(update)
    project, task_text = None, None
    if args:
        project = db.get_project_state(args[0])
        if not project:
            await update.message.reply_text(
                f"Проект `{args[0]}` не найден.", parse_mode="Markdown"
            )
            return
        task_text = " ".join(args[1:]) if len(args) > 1 else None
    elif topic_id:
        project = db.get_project_by_topic(topic_id)
    if not project:
        await update.message.reply_text(
            "Укажи проект: `/run <project>` или пиши в топик проекта.", parse_mode="Markdown"
        )
        return
    if task_text:
        _save_to_inbox(project, task_text)
        await update.message.reply_text(f"Принято. Запускаю цикл для `{project['project_id']}`.", parse_mode="Markdown")
    trigger_file = SCRIPT_DIR / f".run-now-{project['project_id']}"
    trigger_file.touch()
    if not task_text:
        await update.message.reply_text(
            f"Запускаю цикл для `{project['project_id']}`.", parse_mode="Markdown"
        )


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            await update.message.reply_text(f"Не удалось поставить на паузу (код {result.returncode})")
            return
        db.update_project_phase(project["project_id"], "paused")
        await update.message.reply_text(f"`{project['project_id']}` на паузе.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Ошибка паузы: {e}")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    project = _resolve_project(update, context)
    if not project:
        await update.message.reply_text(
            "Укажи проект: `/resume <project>`", parse_mode="Markdown"
        )
        return
    try:
        result = subprocess.run(
            ["pueue", "start", "--group", project["project_id"]], timeout=5, capture_output=True
        )
        if result.returncode != 0:
            await update.message.reply_text(f"Не удалось возобновить (код {result.returncode})")
            return
        db.update_project_phase(project["project_id"], "idle")
        await update.message.reply_text(f"`{project['project_id']}` возобновлён.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Ошибка возобновления: {e}")


HEAVY_ROUTES = {"architect", "council", "bughunt"}
# In-memory pending heavy skill confirmations: key=msg_hash → {project, text, route, ts}
_pending_heavy: dict[str, dict] = {}


def _msg_hash(text: str) -> str:
    import hashlib
    return hashlib.md5(text.encode()).hexdigest()[:12]


async def handle_confirm_heavy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback for heavy skill confirmation: Да / Нет / → Spark."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":", 3)  # confirm_heavy:{action}:{project_id}:{msg_hash}
    action, project_id, msg_hash = parts[1], parts[2], parts[3]

    pending = _pending_heavy.pop(msg_hash, None)
    if not pending:
        await query.edit_message_text("Подтверждение устарело (1 час).")
        return

    project = db.get_project_state(project_id)
    if not project:
        await query.edit_message_text(f"Проект {project_id} не найден.")
        return

    if action == "yes":
        _save_to_inbox(project, pending["text"])
        await query.edit_message_text(f"Принято. Запускаю `{pending['route']}`.")
    elif action == "spark":
        # Override route: save as spark instead
        inbox_dir = Path(project["path"]) / "ai" / "inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filepath = inbox_dir / f"{ts}-telegram.md"
        filepath.write_text(
            f"# Idea: {ts}\n**Source:** telegram\n**Route:** spark\n**Status:** new\n---\n{pending['text']}\n",
            encoding="utf-8",
        )
        await query.edit_message_text("Перенаправлено в Spark.")
    else:  # no
        await query.edit_message_text("Отменено.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    topic_id = get_topic_id(update)
    if not topic_id:
        return
    # Check for pending rework comment first
    pending_key = f"rework_pending:{topic_id}"
    if context.bot_data.get(pending_key):
        await handle_rework_comment(update, context)
        return
    project = db.get_project_by_topic(topic_id)
    if not project:
        return
    text = update.message.text
    if not text or text.startswith("/"):
        return
    route = detect_route(text)

    # Heavy skills require confirmation
    if route in HEAVY_ROUTES:
        h = _msg_hash(text)
        _pending_heavy[h] = {
            "project_id": project["project_id"],
            "text": text,
            "route": route,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        # Cleanup old entries (TTL 1 hour)
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        expired = [k for k, v in _pending_heavy.items()
                   if datetime.fromisoformat(v["ts"]).timestamp() < cutoff]
        for k in expired:
            del _pending_heavy[k]

        pid = project["project_id"]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Да \u2705", callback_data=f"confirm_heavy:yes:{pid}:{h}"),
            InlineKeyboardButton("Нет \u274c", callback_data=f"confirm_heavy:no:{pid}:{h}"),
            InlineKeyboardButton("\u2192 Spark", callback_data=f"confirm_heavy:spark:{pid}:{h}"),
        ]])
        await update.message.reply_text(
            f"Запустить *{route}* для *{pid}*? Это тяжёлый skill.",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return

    _save_to_inbox(project, text)
    _ROUTE_LABELS = {
        "spark": "Создам спеку",
        "spark_bug": "Разберу баг",
        "architect": "Запущу архитектора",
        "council": "Соберу консилиум",
        "bughunt": "Запущу охоту на баги",
        "reflect": "Запущу рефлексию",
        "scout": "Отправлю на разведку",
    }
    label = _ROUTE_LABELS.get(route, "Обработаю")
    await update.message.reply_text(f"Принято. {label} на следующем цикле.")


def _kill_other_instances() -> None:
    """Kill any other telegram-bot.py processes to prevent duplicate responses."""
    import signal
    my_pid = os.getpid()
    for line in subprocess.run(
        ["pgrep", "-f", "telegram-bot.py"], capture_output=True, text=True
    ).stdout.strip().split("\n"):
        pid = int(line.strip()) if line.strip().isdigit() else 0
        if pid and pid != my_pid:
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info("Killed stale bot instance PID %d", pid)
            except OSError:
                pass


def main() -> None:
    _kill_other_instances()
    application = Application.builder().token(BOT_TOKEN).build()
    # ConversationHandler must be registered BEFORE generic text handler
    application.add_handler(create_addproject_handler())
    application.add_handler(CommandHandler("nexussync", cmd_nexussync))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("run", cmd_run))
    application.add_handler(CommandHandler("pause", cmd_pause))
    application.add_handler(CommandHandler("resume", cmd_resume))
    # fmt: off
    application.add_handler(CallbackQueryHandler(handle_project_toggle, pattern=r"^toggle:"))
    application.add_handler(CallbackQueryHandler(handle_launch_review, pattern=r"^launch_review$"))
    application.add_handler(CallbackQueryHandler(handle_finding_approve, pattern=r"^approve_finding:"))
    application.add_handler(CallbackQueryHandler(handle_finding_reject, pattern=r"^reject_finding:"))
    application.add_handler(CallbackQueryHandler(handle_approve_all, pattern=r"^approve_all:"))
    application.add_handler(CallbackQueryHandler(handle_reject_all, pattern=r"^reject_all:"))
    application.add_handler(CallbackQueryHandler(handle_spec_approve, pattern=r"^spec_approve:"))
    application.add_handler(CallbackQueryHandler(handle_spec_rework, pattern=r"^spec_rework:"))
    application.add_handler(CallbackQueryHandler(handle_spec_reject, pattern=r"^spec_reject:"))
    application.add_handler(CallbackQueryHandler(handle_confirm_heavy, pattern=r"^confirm_heavy:"))
    application.add_handler(CallbackQueryHandler(handle_approve, pattern=r"^approve:"))
    application.add_handler(CallbackQueryHandler(handle_cancel, pattern=r"^cancel:"))
    application.add_handler(MessageHandler(filters.VOICE & filters.ChatType.SUPERGROUP, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.SUPERGROUP, handle_photo))
    # fmt: on
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    register_evening_job(application)
    logger.info("Starting DLD Telegram bot (PTB v21.9+)")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
