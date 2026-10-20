"""Bot entrypoint — wires handlers, jobs and run polling."""
from __future__ import annotations

import logging

from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

from bot import database as db
from bot.config import ADMIN_IDS, BOT_TOKEN, DASH_PORT, GROUP_CHAT_ID
from bot.handlers import admin, group, ideas, projects, roles, start, tasks
from bot.services.reminders import check_deadlines

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("yp-mgmt")


def build_app() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده — فایل .env رو از روی .env.example بساز.")

    db.init_db()
    db.seed_demo()

    app = (Application.builder()
           .token(BOT_TOKEN)
           .build())

    app.bot_data["admin_ids"] = ADMIN_IDS
    app.bot_data["group_chat_id"] = GROUP_CHAT_ID

    # ---- commands (work in DM + groups)
    app.add_handler(CommandHandler("start", start.cmd_start))
    app.add_handler(CommandHandler("help", start.cmd_start))
    app.add_handler(CommandHandler("whoami", group.cmd_whoami))
    app.add_handler(CommandHandler("team", group.cmd_team))
    app.add_handler(CommandHandler("tasks", group.cmd_tasks))
    app.add_handler(CommandHandler("deadline", group.cmd_deadline))
    app.add_handler(CommandHandler("idea", group.cmd_idea))

    # ---- conversations (create project / task)
    app.add_handler(projects.conversation())
    app.add_handler(tasks.conversation())

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
    app.add_handler(CallbackQueryHandler(start.menu_router, pattern=r"^menu:"))

    # ---- free text (broadcast mode etc.)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group.broadcast_text))

    # ---- deadline reminders every 30 minutes
    if app.job_queue:
        app.job_queue.run_repeating(check_deadlines, interval=1800, first=15)

    logger.info("Bot application built. Dashboard port=%s", DASH_PORT)
    return app


def main() -> None:
    app = build_app()
    logger.info("Starting polling …")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
