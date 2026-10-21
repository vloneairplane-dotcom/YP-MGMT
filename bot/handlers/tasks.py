"""Task handlers: my tasks, per-project lists, create-conversation, status changes."""
from __future__ import annotations

from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (CallbackQueryHandler, ContextTypes, ConversationHandler,
                          MessageHandler, filters)

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.config import TASK_PRIORITIES, TASK_STATUSES
from bot.utils import date_disp, esc, is_manager, parse_deadline, user_of

# conversation states (offset from projects' range so BOTH flows can share
# one merged ConversationHandler — see bot/main.py: a user can only have one
# active wizard at a time, and re-entry always works)
T_TITLE, T_ASSIGN, T_PRIO, T_DL = range(10, 14)
T_DL_WAIT = 14

_tdraft: dict[int, dict] = {}


async def show_my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        edit: bool = False) -> None:
    user = user_of(update, context)
    tasks = db.list_tasks() if is_manager(user) else db.list_tasks(assignee_id=user["id"] if user else -1)
    title = "📊 <b>تسک‌های من</b>" if not is_manager(user) else "📊 <b>همه‌ی تسک‌ها</b>"
    if not tasks:
        text = title + "\n─────────────────────\n✅ تسکی نداری! 🎉"
    else:
        lines = [title, "─────────────────────"]
        for tk in tasks[:12]:
            lines.append(texts.task_line(tk))
        text = "\n".join(lines)
    markup = kb.tasks_list(tasks) if tasks else kb.back("menu:main")
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def show_project_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    pid = int((query.data or "").split(":")[2])
    p = db.get_project(pid)
    tasks = db.list_tasks(project_id=pid)
    text = f"📋 <b>تسک‌های «{p['title'] if p else '?'}»</b>\n─────────────────────"
    if not tasks:
        text += "\n— تسکی ثبت نشده"
    else:
        for tk in tasks:
            text += "\n" + texts.task_line(tk)
    await query.edit_message_text(text, reply_markup=kb.tasks_list(tasks) if tasks else kb.back(f"proj:view:{pid}"))


async def task_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    tid = int((query.data or "").split(":")[2])
    tk = db.get_task(tid)
    if not tk:
        await query.edit_message_text("⚠️ تسک پیدا نشد.", reply_markup=kb.back("menu:main"))
        return
    ts = TASK_STATUSES[tk["status"]]
    pr = TASK_PRIORITIES[tk["priority"]]
    text = (
        f"🧩 <b>تسک #{tk['id']}</b>\n─────────────────────\n"
        f"📌 {esc(tk['title'])}\n"
        f"📁 پروژه: {esc(tk['project_title'])}\n"
        f"📝 {esc(tk['description']) or '—'}\n"
        f"{ts['emoji']} وضعیت: <b>{ts['label']}</b>\n"
        f"{pr['emoji']} اولویت: <b>{pr['label']}</b>\n"
        f"⏰ ددلاین: {date_disp(tk['deadline'])}"
    )
    user = user_of(update, context)
    await query.edit_message_text(
        text, reply_markup=kb.task_detail(tid, tk["project_id"], is_manager(user)),
    )


async def task_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    _, _, tid, status = (query.data or "").split(":")
    if status not in TASK_STATUSES:
        return
    tk = db.get_task(int(tid))
    db.set_task_status(int(tid), status)
    user = user_of(update, context)
    if tk:
        db.log_activity(user["id"] if user else None, "task",
                        f"تسک «{tk['title']}» → {TASK_STATUSES[status]['label']}")
    await query.answer(f"✅ {TASK_STATUSES[status]['emoji']} {TASK_STATUSES[status]['label']}")
    await task_view(update, context)


async def task_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = user_of(update, context)
    if not is_manager(user):
        await query.answer(texts.NO_PERMISSION, show_alert=True)
        return
    tid = int((query.data or "").split(":")[2])
    db.delete_task(tid)
    await query.edit_message_text("🗑 تسک حذف شد.", reply_markup=kb.back("menu:main"))


# ------------------------------------------------------------ create flow
async def new_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = user_of(update, context)
    if not is_manager(user):
        if query:
            await query.answer(texts.NO_PERMISSION, show_alert=True)
        return ConversationHandler.END
    if not query:
        return ConversationHandler.END
    await query.answer()
    parts = (query.data or "").split(":")
    pid = int(parts[2])
    _tdraft[user["tg_id"] if user else 0] = {"project_id": pid}
    await query.edit_message_text(
        "🧩 <b>تسک جدید</b>\n─────────────────────\nعنوان تسک چیه؟")
    return T_TITLE


async def new_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = user_of(update, context)
    if not user or not update.effective_message:
        return ConversationHandler.END
    _tdraft.setdefault(user["tg_id"], {})["title"] = (update.effective_message.text or "").strip()
    users = db.list_users()
    await update.effective_message.reply_text(
        "👤 این تسک برای کیه؟", reply_markup=kb.task_assignee_pick(users, _tdraft[user["tg_id"]]["project_id"]))
    return T_ASSIGN


async def new_task_assign(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return T_ASSIGN
    await query.answer()
    user = user_of(update, context)
    _, _, pid, uid = (query.data or "").split(":")
    if user:
        _tdraft.setdefault(user["tg_id"], {})["assignee_id"] = int(uid)
    await query.edit_message_text("🎯 اولویت تسک؟",
                                  reply_markup=kb.task_priority_pick(int(pid)))
    return T_PRIO


async def new_task_prio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return T_PRIO
    await query.answer()
    user = user_of(update, context)
    _, _, pid, prio = (query.data or "").split(":")
    if user:
        _tdraft.setdefault(user["tg_id"], {})["priority"] = prio
    await query.edit_message_text(
        "⏰ ددلاین تسک؟ (تاریخ بنویس یا «-»)",
        reply_markup=kb.deadline_pick())
    return T_DL


async def new_task_dl_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return T_DL
    await query.answer()
    user = user_of(update, context)
    val = (query.data or "").split(":")[1]
    deadline = None
    if val.isdigit():
        deadline = (datetime.utcnow() + timedelta(days=int(val))).strftime("%Y-%m-%d")
    elif val == "manual":
        await query.edit_message_text("✍️ تاریخ رو بنویس (مثال: <code>2026-11-01</code>)")
        return T_DL_WAIT
    if user:
        _tdraft.setdefault(user["tg_id"], {})["deadline"] = deadline
    return await _task_confirm(update, context)


async def new_task_dl_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = user_of(update, context)
    if not user or not update.effective_message:
        return ConversationHandler.END
    text = (update.effective_message.text or "").strip()
    deadline = None if text in {"-", "ندارد"} else parse_deadline(text)
    _tdraft.setdefault(user["tg_id"], {})["deadline"] = deadline
    return await _task_confirm(update, context)


async def _task_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = user_of(update, context)
    if not user:
        return ConversationHandler.END
    d = _tdraft.pop(user["tg_id"], {})
    tid = db.create_task(
        d.get("project_id", 0), d.get("title", "—"), d.get("assignee_id"),
        priority=d.get("priority", "normal"), deadline=d.get("deadline"),
    )
    assignee = db.get_user_by_id(d["assignee_id"]) if d.get("assignee_id") else None
    db.log_activity(user["id"], "task",
                    f"تسک «{d.get('title')}» به {assignee['full_name'] if assignee else '—'} داده شد")
    # notify assignee in DM
    if assignee and assignee["tg_id"] and context.bot:
        try:
            await context.bot.send_message(
                assignee["tg_id"],
                f"🧩 تسک جدید برات ثبت شد!\n📌 {esc(d.get('title'))}\n⏰ {date_disp(d.get('deadline'))}",
            )
        except Exception:  # user may have not started the bot
            pass
    msg = f"🎉 تسک «{esc(d.get('title'))}» ثبت شد!"
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=kb.back(f"proj:view:{d.get('project_id')}"))
    elif update.effective_message:
        await update.effective_message.reply_text(msg, reply_markup=kb.back(f"proj:view:{d.get('project_id')}"))
    _ = tid
    return ConversationHandler.END
