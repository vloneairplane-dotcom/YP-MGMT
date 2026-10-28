"""Bot entrypoint — wires handlers, jobs and run polling."""
from __future__ import annotations

import asyncio
import logging
import os
import warnings

from telegram.constants import ParseMode
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ConversationHandler, Defaults, MessageHandler,
                          filters)
from telegram.request import HTTPXRequest
from telegram.warnings import PTBUserWarning

from bot import database as db
from bot import gate
from bot import keyboards as kb
from bot import texts
from bot.config import ADMIN_IDS, BOT_TOKEN, DASH_PORT, GROUP_CHAT_ID
from bot.handlers import admin, group, ideas, projects, roles, start, tasks
from bot.services.reminders import check_deadlines
from bot.utils import user_of

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("yp-mgmt")

# mixed message/callback conversations intentionally use per_message=False
warnings.filterwarnings("ignore", message="If 'per_message=False'", category=PTBUserWarning)


async def _wizard_cancel(update, context) -> int:
    """proj:cancel — ends whichever wizard is active and clears both drafts."""
    from bot.handlers import projects as _p
    from bot.handlers import tasks as _t
    user = user_of(update, context)
    if user:
        _p._draft.pop(user["tg_id"], None)
        _t._tdraft.pop(user["tg_id"], None)
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(texts.CANCELLED, reply_markup=kb.back("menu:main"))
    return ConversationHandler.END


def wizard_conversation() -> ConversationHandler:
    """ONE merged conversation for both wizards (create-project + create-task).

    Why merged: with two separate ConversationHandlers a user could get stuck in
    one wizard — PTB skips entry_points while a conversation is active, so the
    second tap on "➕ تسک جدید" was silently dropped forever (the reported bug).
    A single handler means one active flow per user, unique state ids
    (task states are 10+), and allow_reentry=True lets tapping any wizard
    button restart the flow cleanly instead of dying silently.
    """
    from bot.handlers import projects as _p
    from bot.handlers import tasks as _t

    text_any = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        name="wizards",
        entry_points=[
            CallbackQueryHandler(_p.new_project_start, pattern=r"^proj:new$"),
            CallbackQueryHandler(_t.new_task_start, pattern=r"^task:new:\d+$"),
        ],
        states={
            # ---- project wizard
            _p.P_TITLE: [MessageHandler(text_any, _p.new_project_title)],
            _p.P_TYPE: [CallbackQueryHandler(_p.new_project_type, pattern=r"^ptype:")],
            _p.P_DESC: [MessageHandler(text_any, _p.new_project_desc)],
            _p.P_DL: [CallbackQueryHandler(_p.new_project_dl_btn, pattern=r"^dl:"),
                      MessageHandler(text_any, _p.new_project_dl_text)],
            _p.DL_WAIT: [MessageHandler(text_any, _p.new_project_dl_text)],
            _p.P_CONFIRM: [CallbackQueryHandler(_p.new_project_confirm, pattern=r"^proj:confirm$")],
            # ---- task wizard
            _t.T_TITLE: [MessageHandler(text_any, _t.new_task_title)],
            _t.T_ASSIGN: [CallbackQueryHandler(_t.new_task_assign, pattern=r"^task:assign:")],
            _t.T_PRIO: [CallbackQueryHandler(_t.new_task_prio, pattern=r"^task:prio:")],
            _t.T_DL: [CallbackQueryHandler(_t.new_task_dl_btn, pattern=r"^dl:"),
                      MessageHandler(text_any, _t.new_task_dl_text)],
            _t.T_DL_WAIT: [MessageHandler(text_any, _t.new_task_dl_text)],
        },
        fallbacks=[CallbackQueryHandler(_wizard_cancel, pattern=r"^proj:cancel$")],
        per_message=False,
        allow_reentry=True,
    )


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده — فایل .env رو از روی .env.example بساز.")

    db.init_db()
    db.seed_demo()

    builder = (Application.builder().token(BOT_TOKEN)
               .defaults(Defaults(parse_mode=ParseMode.HTML)))
    # Optional proxy for servers that can't reach api.telegram.org directly
    proxy = os.getenv("TELEGRAM_PROXY", "").strip()
    if proxy:
        builder = builder.request(HTTPXRequest(proxy=proxy))
        logger.info("Using TELEGRAM proxy for Telegram API")
    app = builder.build()

    app.bot_data["admin_ids"] = ADMIN_IDS
    app.bot_data["group_chat_id"] = GROUP_CHAT_ID

    # ---- group-lock gate (runs FIRST, can stop every update below it)
    app.add_handler(MessageHandler(filters.ALL, gate.message_gate), group=-1)
    app.add_handler(CallbackQueryHandler(gate.callback_gate), group=-1)
    if GROUP_CHAT_ID:
        logger.info("🔐 group-lock ON — only chat %s may use the bot", GROUP_CHAT_ID)
    else:
        logger.info("🔓 group-lock OFF — set GROUP_CHAT_ID to lock the bot to one group")

    # ---- commands (work in DM + groups)
    app.add_handler(CommandHandler("start", start.cmd_start))
    app.add_handler(CommandHandler("help", start.cmd_start))
    app.add_handler(CommandHandler("whoami", group.cmd_whoami))
    app.add_handler(CommandHandler("team", group.cmd_team))
    app.add_handler(CommandHandler("tasks", group.cmd_tasks))
    app.add_handler(CommandHandler("deadline", group.cmd_deadline))
    app.add_handler(CommandHandler("idea", group.cmd_idea))
    app.add_handler(CommandHandler("backup", admin.cmd_backup))
    app.add_handler(CommandHandler("wipe", admin.cmd_wipe))
    app.add_handler(CommandHandler("restore", admin.cmd_restore))
    app.add_handler(CommandHandler("reset_all", admin.cmd_reset_all))

    # ---- wizards: ONE merged conversation for project+task flows
    app.add_handler(wizard_conversation())

    # ---- callback routers (order matters: more specific first)
    app.add_handler(CallbackQueryHandler(tasks.task_set_status, pattern=r"^task:st:"))
    app.add_handler(CallbackQueryHandler(tasks.task_delete, pattern=r"^task:del:"))
    app.add_handler(CallbackQueryHandler(tasks.task_view, pattern=r"^task:view:"))
    app.add_handler(CallbackQueryHandler(tasks.show_project_tasks, pattern=r"^task:list:"))
    app.add_handler(CallbackQueryHandler(admin.admin_router, pattern=r"^admin:"))
    app.add_handler(CallbackQueryHandler(roles.role_router, pattern=r"^role:"))
    app.add_handler(CallbackQueryHandler(ideas.idea_router, pattern=r"^idea:"))
    app.add_handler(CallbackQueryHandler(projects.project_view, pattern=r"^proj:view:"))
    app.add_handler(CallbackQueryHandler(projects.project_next_status, pattern=r"^proj:next:"))
    app.add_handler(CallbackQueryHandler(projects.project_status_menu, pattern=r"^proj:status:"))
    app.add_handler(CallbackQueryHandler(projects.project_set_status, pattern=r"^proj:set:"))
    app.add_handler(CallbackQueryHandler(projects.project_archive, pattern=r"^proj:archive:"))
    app.add_handler(CallbackQueryHandler(projects.project_edit_pick, pattern=r"^proj:dlq:"))
    app.add_handler(CallbackQueryHandler(projects.project_edit_deadline, pattern=r"^proj:dl:"))
    app.add_handler(CallbackQueryHandler(start.menu_router, pattern=r"^menu:"))

    # ---- free text (broadcast mode etc.) + backup restore files
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group.broadcast_text))
    app.add_handler(MessageHandler(filters.Document.ALL, admin.restore_doc))

    # ---- catch-all: a callback no handler matched (e.g. a stale button pressed
    # after a re-deploy wiped conversation state) — tell the user, never silence
    async def _stale_cb(update, context):
        query = update.callback_query
        if query:
            await query.answer("این دکمه منقضی شده 🕳️ — با /start منوی تازه رو باز کن",
                               show_alert=True)

    app.add_handler(CallbackQueryHandler(_stale_cb))

    # ---- graceful error logging (e.g. HTML parse hiccups from odd user text)
    async def _on_error(update, context):
        logger.warning("Update failed: %s", context.error)

    app.add_error_handler(_on_error)

    # ---- deadline reminders every 30 minutes
    if app.job_queue:
        app.job_queue.run_repeating(check_deadlines, interval=1800, first=15)

    logger.info("Bot application built. Dashboard port=%s", DASH_PORT)
    return app


def main() -> None:
    app = build_app()
    logger.info("Starting polling …")
    # Python 3.12+/3.14 no longer auto-creates a loop via asyncio.get_event_loop();
    # make sure one exists so run_polling's internals never crash.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
