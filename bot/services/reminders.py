"""Deadline reminder job — runs periodically via the bot's JobQueue."""
from __future__ import annotations

from datetime import datetime

from telegram.ext import ContextTypes

from bot import database as db
from bot.config import TASK_STATUSES
from bot.utils import days_left


async def check_deadlines(context: ContextTypes.DEFAULT_TYPE) -> None:
    """DM assignees / project chat when deadlines are near or overdue."""
    now = datetime.utcnow()

    for p in db.list_projects():
        d = days_left(p["deadline"])
        if d is None:
            continue
        for kind, label in ((2, "2 روز"), (0, "امروز"), (-1, "گذشته")):
            if d != kind:
                continue
            if db.already_reminded(p["id"], None, f"proj:{kind}"):
                continue
            msg = (
                f"⏰ <b>یادآور ددلاین پروژه</b>\n"
                f"📁 {p['title']}\n"
                f"🕓 {p['deadline']} · ددلاین {label}!"
            )
            chat_id = p["chat_id"] or context.bot_data.get("group_chat_id")
            if chat_id:
                try:
                    await context.bot.send_message(chat_id, msg)
                except Exception:
                    pass
            db.mark_reminded(p["id"], None, f"proj:{kind}")

    for tk in db.list_tasks():
        if tk["status"] == "done":
            continue
        d = days_left(tk["deadline"])
        if d is None:
            continue
        for kind, label in ((1, "فردا"), (0, "امروز")):
            if d != kind:
                continue
            if db.already_reminded(None, tk["id"], f"task:{kind}"):
                continue
            msg = (
                f"🧩 <b>یادآور تسک</b>\n"
                f"📌 {tk['title']}\n"
                f"📁 {tk['project_title']}\n"
                f"🕓 ددلاین {label}! ({tk['deadline']})\n"
                f"وضعیت فعلی: {TASK_STATUSES[tk['status']]['emoji']} {TASK_STATUSES[tk['status']]['label']}"
            )
            if tk["assignee_tg"]:
                try:
                    await context.bot.send_message(tk["assignee_tg"], msg)
                except Exception:
                    pass
            db.mark_reminded(None, tk["id"], f"task:{kind}")
    _ = now
