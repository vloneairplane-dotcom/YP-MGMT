"""Group-mode commands: /start, /team, /tasks, /deadline, /idea, /whoami + broadcast."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.services import idea_engine
from bot.utils import deadline_badge, esc, role_badge, user_of


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = user_of(update, context)
    if not user or not update.effective_message:
        return
    await update.effective_message.reply_text(
        f"👤 <b>{esc(user['full_name'])}</b>\n{role_badge(user)}",
    )


async def cmd_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.handlers.admin import show_team
    await show_team(update, context)


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.handlers.tasks import show_my_tasks
    await show_my_tasks(update, context)


async def cmd_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.handlers.projects import show_deadlines
    await show_deadlines(update, context)


async def cmd_idea(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = user_of(update, context)
    if not update.effective_message:
        return
    import random
    cat = random.choice(list(idea_engine.BANKS))
    text = idea_engine.generate(cat)
    db.log_idea(user["id"] if user else None, cat, text)
    await update.effective_message.reply_text(
        texts.idea_card(cat, text), reply_markup=kb.idea_again(cat))


async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """If admin typed a broadcast message, fan it out to all members."""
    user = user_of(update, context)
    if not user or not update.effective_message:
        return
    if not context.user_data.get("broadcast"):
        return
    if user["role"] not in {"admin", "manager"}:
        return
    context.user_data["broadcast"] = False
    text = (update.effective_message.text or "").strip()
    sent = 0
    for u in db.list_users():
        if not u["tg_id"]:
            continue
        try:
            await context.bot.send_message(u["tg_id"], f"📣 <b>اعلان تیم</b>\n─────────────────────\n{esc(text)}")
            sent += 1
        except Exception:
            pass
    await update.effective_message.reply_text(f"📣 اعلان برای {sent} نفر ارسال شد ✅")
