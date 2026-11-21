"""Idea generator handlers — the 'ایده بگیر' panel."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.services import idea_engine
from bot.utils import user_of


async def show_ideas_menu(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          edit: bool = False) -> None:
    text = (
        "💡 <b>ایده بگیر</b>\n"
        "─────────────────────\n"
        "یه دسته انتخاب کن تا برات ایده بسازم:\n"
        "هر بار «یه ایده‌ی دیگه» رو بزنی یه ایده‌ی تازه میاد."
    )
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb.ideas_menu())
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=kb.ideas_menu())


async def idea_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user = user_of(update, context)
    category = (query.data or "").split(":")[1]

    if category == "full":
        brief = idea_engine.full_brief()
        db.log_idea(user["id"] if user else None, "full", " / ".join(brief.values())[:200])
        await query.edit_message_text(
            texts.full_brief_text(brief), reply_markup=kb.idea_full_again())
        return

    text = idea_engine.generate(category)
    db.log_idea(user["id"] if user else None, category, text)
    db.log_activity(user["id"] if user else None, "idea", f"ایده‌ی {category}")
    await query.edit_message_text(
        texts.idea_card(category, text),
        reply_markup=kb.idea_again(category),
    )
