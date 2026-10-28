"""Group-lock gate: the bot only chats inside the team group.

Registered as the FIRST handler group (-1), before every command/menu:
- private chats (DMs)      → blocked for everyone except ADMIN_IDS
                             (admins keep DM access for /backup //restore //tools)
- groups                   → if GROUP_CHAT_ID is set, ONLY that group may use the bot;
                             anywhere else the bot stays completely silent.
To find your group id: add the bot to the group, say anything — the id shows up
in the Render logs (🔒 blocked chat id=…).
"""
from __future__ import annotations

import logging

from telegram import Chat, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bot import texts
from bot import config

logger = logging.getLogger("yp-mgmt")

_notified: set[int] = set()  # DM spammers get the lock note once per process


def allowed(update: Update) -> tuple[bool, str]:
    """Returns (is_allowed, kind) for any update."""
    chat = update.effective_chat
    user = update.effective_user
    uid = user.id if user else None
    if chat is None:
        return True, "none"
    if chat.type == Chat.PRIVATE:
        return uid in config.ADMIN_IDS, "private"
    if config.GROUP_CHAT_ID and chat.id != config.GROUP_CHAT_ID:
        return False, "group"
    return True, "group"


def _note_blocked(update: Update) -> None:
    chat = update.effective_chat
    if chat is not None and chat.type != Chat.PRIVATE:
        logger.info("🔒 blocked chat id=%s type=%s title=%r — to allow it set "
                    "GROUP_CHAT_ID=%s", chat.id, chat.type, chat.title, chat.id)


async def message_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ok, kind = allowed(update)
    if ok:
        return  # let the real handlers in group 0 do their job
    _note_blocked(update)
    if kind == "private":
        uid = update.effective_user.id if update.effective_user else 0
        logger.info("🔒 blocked DM from user id=%s (%s)", uid,
                    update.effective_user.full_name if update.effective_user else "?")
        msg = update.effective_message
        if msg and uid not in _notified:
            _notified.add(uid)
            await msg.reply_text(texts.GROUP_LOCK_DM)
    raise ApplicationHandlerStop


async def callback_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ok, kind = allowed(update)
    if ok:
        return
    _note_blocked(update)
    query = update.callback_query
    if query and kind == "private":
        await query.answer("🔐 این ربات فقط توی گروه کاری فعاله", show_alert=True)
    raise ApplicationHandlerStop
