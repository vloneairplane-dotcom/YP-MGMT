"""Start / main menu / help handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.utils import role_badge, user_of


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = user_of(update, context)
    if not user or not update.effective_message:
        return
    first = user["full_name"].split(" ")[0]
    if not user.get("role"):
        await update.effective_message.reply_text(
            texts.WELCOME.format(name=first, brand=texts.BRAND),
            reply_markup=kb.role_pick(),
        )
        return
    await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         edit: bool = False) -> None:
    user = user_of(update, context)
    if not user:
        return
    s = db.stats()
    first = user["full_name"].split(" ")[0]
    text = texts.MAIN_MENU.format(
        brand=texts.BRAND_FA, name=first, role_badge=role_badge(user),
        projects=s["projects"], tasks=s["tasks"], tasks_done=s["tasks_done"],
        members=s["members"], ideas=s["ideas"],
    )
    target = update.effective_message
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb.main_menu(bool(user.get("role"))))
    elif target:
        await target.reply_text(text, reply_markup=kb.main_menu(bool(user.get("role"))))


async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route main-menu callback buttons."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    action = data.split(":")[1] if ":" in data else ""

    if action == "main":
        await show_main_menu(update, context, edit=True)
    elif action == "help":
        await query.edit_message_text(texts.HELP, reply_markup=kb.back())
    elif action == "role":
        user = user_of(update, context)
        name = user["full_name"] if user else "رفیق"
        await query.edit_message_text(
            texts.role_pick_text(name) + "\n\n" + texts.ROLES_DESC,
            reply_markup=kb.role_pick(),
        )
    elif action == "projects":
        from bot.handlers.projects import show_projects
        await show_projects(update, context, edit=True)
    elif action == "ideas":
        from bot.handlers.ideas import show_ideas_menu
        await show_ideas_menu(update, context, edit=True)
    elif action == "tasks":
        from bot.handlers.tasks import show_my_tasks
        await show_my_tasks(update, context, edit=True)
    elif action == "team":
        from bot.handlers.admin import show_team
        await show_team(update, context, edit=True)
    elif action == "deadlines":
        from bot.handlers.projects import show_deadlines
        await show_deadlines(update, context, edit=True)
    elif action == "admin":
        from bot.handlers.admin import show_admin
        await show_admin(update, context, edit=True)
