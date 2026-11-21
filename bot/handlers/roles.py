"""Role registration handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.config import ROLES
from bot.utils import user_of


async def role_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user = user_of(update, context)
    role = (query.data or "").split(":")[1]
    if role not in ROLES or not user:
        return
    db.set_role(user["tg_id"], role)
    db.log_activity(user["id"], "role", f"نقش {ROLES[role]['label']} انتخاب شد")
    await query.edit_message_text(
        texts.role_set_text(role),
        reply_markup=kb.back("menu:main"),
    )
