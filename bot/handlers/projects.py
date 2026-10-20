"""Project handlers: list, detail, create-conversation, status, archive, deadlines."""
from __future__ import annotations

from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.config import PROJECT_STATUSES, PROJECT_TYPES, STATUS_FLOW
from bot.utils import (deadline_badge, is_manager, parse_deadline, user_of,
                       progress_bar)

# conversation states
P_TITLE, P_TYPE, P_DESC, P_DL = range(4)
DL_WAIT = 100

_draft: dict[int, dict] = {}


# ----------------------------------------------------------------- list
async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        edit: bool = False) -> None:
    projects = db.list_projects()
    if not projects:
        text = "📁 هنوز پروژه‌ای ثبت نشده.\nاولین پروژه رو بساز 👇"
    else:
        lines = [texts.PROJECT_LIST_HEADER]
        for p in projects[:15]:
            lines.append(texts.project_card_short(p))
            lines.append(f"   {deadline_badge(p['deadline'])}")
        text = "\n".join(lines)
    markup = kb.projects_list(projects)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def project_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    pid = int((query.data or "").split(":")[2])
    p = db.get_project(pid)
    if not p:
        await query.edit_message_text("⚠️ پروژه پیدا نشد.", reply_markup=kb.back("menu:projects"))
        return
    tasks = db.list_tasks(project_id=pid)
    done = sum(1 for t in tasks if t["status"] == "done")
    text = texts.project_detail(p, tasks)
    text += f"\n─────────────────────\n{progress_bar(done, len(tasks))} {done}/{len(tasks)} تسک انجام‌شده"
    text += f"\n🕐 {deadline_badge(p['deadline'])}"
    user = user_of(update, context)
    await query.edit_message_text(
        text, reply_markup=kb.project_detail(pid, is_manager(user)),
    )


async def project_next_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = user_of(update, context)
    if not is_manager(user):
        await query.answer(texts.NO_PERMISSION, show_alert=True)
        return
    pid = int((query.data or "").split(":")[2])
    p = db.get_project(pid)
    if not p:
        return
    idx = STATUS_FLOW.index(p["status"]) if p["status"] in STATUS_FLOW else 0
    new_status = STATUS_FLOW[min(idx + 1, len(STATUS_FLOW) - 1)]
    db.set_project_status(pid, new_status)
    db.log_activity(user["id"], "project", f"وضعیت «{p['title']}» → {PROJECT_STATUSES[new_status]['label']}")
    await query.answer(f"✅ وضعیت: {PROJECT_STATUSES[new_status]['emoji']} {PROJECT_STATUSES[new_status]['label']}")
    await project_view(update, context)


async def project_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    pid = int((query.data or "").split(":")[2])
    await query.edit_message_text("📌 وضعیت جدید پروژه رو انتخاب کن:",
                                  reply_markup=kb.project_status_pick(pid))


async def project_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = user_of(update, context)
    if not is_manager(user):
        await query.answer(texts.NO_PERMISSION, show_alert=True)
        return
    _, _, pid, status = (query.data or "").split(":")
    if status in PROJECT_STATUSES:
        db.set_project_status(int(pid), status)
        p = db.get_project(int(pid))
        if p:
            db.log_activity(user["id"], "project", f"وضعیت «{p['title']}» → {PROJECT_STATUSES[status]['label']}")
    await project_view(update, context)


async def project_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = user_of(update, context)
    if not is_manager(user):
        await query.answer(texts.NO_PERMISSION, show_alert=True)
        return
    pid = int((query.data or "").split(":")[2])
    p = db.get_project(pid)
    db.archive_project(pid)
    if p:
        db.log_activity(user["id"], "project", f"پروژه «{p['title']}» آرشیو شد")
    await query.edit_message_text("🗄 پروژه آرشیو شد.", reply_markup=kb.back("menu:projects"))


async def show_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         edit: bool = False) -> None:
    rows = []
    for p in db.list_projects():
        d = None
        try:
            if p["deadline"]:
                d = datetime.fromisoformat(p["deadline"][:10])
        except ValueError:
            continue
        if d and d <= datetime.utcnow() + timedelta(days=7):
            rows.append(p)
    rows.sort(key=lambda r: r["deadline"] or "9999")
    if not rows:
        text = texts.DEADLINE_HEADER + "\n✅ هیچ ددلاینی برای ۷ روز آینده نیست."
    else:
        lines = [texts.DEADLINE_HEADER]
        for p in rows:
            lines.append(f"📁 <b>{p['title']}</b>\n   ⏰ {p['deadline']} · {deadline_badge(p['deadline'])}")
        text = "\n".join(lines)
    markup = kb.back("menu:main")
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup)


# ------------------------------------------------------------- create flow
async def new_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = user_of(update, context)
    if not is_manager(user):
        if query:
            await query.answer(texts.NO_PERMISSION, show_alert=True)
        return ConversationHandler.END
    if query:
        await query.answer()
        await query.edit_message_text(
            "➕ <b>پروژه جدید</b>\n─────────────────────\nعنوان پروژه چیه؟")
    elif update.effective_message:
        await update.effective_message.reply_text("عنوان پروژه چیه؟")
    if user:
        _draft[user["tg_id"]] = {}
    return P_TITLE


async def new_project_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = user_of(update, context)
    if not user or not update.effective_message:
        return ConversationHandler.END
    _draft.setdefault(user["tg_id"], {})["title"] = (update.effective_message.text or "").strip()
    await update.effective_message.reply_text(
        "📦 نوع پروژه رو انتخاب کن:", reply_markup=kb.project_type_pick())
    return P_TYPE


async def new_project_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return P_TYPE
    await query.answer()
    user = user_of(update, context)
    ptype = (query.data or "").split(":")[1]
    if user:
        _draft.setdefault(user["tg_id"], {})["ptype"] = ptype
    await query.edit_message_text(
        "📝 یه توضیح کوتاه بنویس (یا «-» برای رد شدن):")
    return P_DESC


async def new_project_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = user_of(update, context)
    if not user or not update.effective_message:
        return ConversationHandler.END
    text = (update.effective_message.text or "").strip()
    _draft.setdefault(user["tg_id"], {})["description"] = "" if text == "-" else text
    await update.effective_message.reply_text(
        "⏰ ددلاین پروژه رو مشخص کن:",
        reply_markup=kb.deadline_pick())
    return P_DL


async def new_project_dl_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return P_DL
    await query.answer()
    user = user_of(update, context)
    val = (query.data or "").split(":")[1]
    deadline = None
    if val.isdigit():
        deadline = (datetime.utcnow() + timedelta(days=int(val))).strftime("%Y-%m-%d")
    elif val == "manual":
        await query.edit_message_text(
            "✍️ تاریخ رو بنویس (مثال: <code>2026-11-01</code> یا <code>10 روز دیگر</code>)",
        )
        return DL_WAIT
    draft = _draft.setdefault(user["tg_id"] if user else 0, {})
    draft["deadline"] = deadline
    return await _confirm(update, context)


async def new_project_dl_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = user_of(update, context)
    if not user or not update.effective_message:
        return ConversationHandler.END
    deadline = parse_deadline(update.effective_message.text or "")
    _draft.setdefault(user["tg_id"], {})["deadline"] = deadline
    return await _confirm(update, context)


async def _confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = user_of(update, context)
    if not user:
        return ConversationHandler.END
    d = _draft.get(user["tg_id"], {})
    ptype = PROJECT_TYPES.get(d.get("ptype", "other"), {"label": "?", "emoji": "📦"})
    text = (
        "✅ <b>تأیید پروژه</b>\n─────────────────────\n"
        f"📌 {d.get('title', '—')}\n"
        f"{ptype['emoji']} نوع: {ptype['label']}\n"
        f"📝 {d.get('description') or '—'}\n"
        f"⏰ ددلاین: {d.get('deadline') or '—'}"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb.confirm_new_project())
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=kb.confirm_new_project())
    return P_DL


async def new_project_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = user_of(update, context)
    if not user or not query:
        return ConversationHandler.END
    await query.answer()
    d = _draft.pop(user["tg_id"], {})
    pid = db.create_project(
        d.get("title", "بدون عنوان"), d.get("description", ""),
        d.get("ptype", "other"), d.get("deadline"),
        user["id"], update.effective_chat.id if update.effective_chat else None,
    )
    db.log_activity(user["id"], "project", f"پروژه «{d.get('title')}» ساخته شد")
    await query.edit_message_text(
        f"🎉 پروژه «{d.get('title')}» ساخته شد!\nحالا براش تسک تعریف کن 👇",
        reply_markup=kb.project_detail(pid, True),
    )
    return ConversationHandler.END


async def new_project_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = user_of(update, context)
    if user:
        _draft.pop(user["tg_id"], None)
    if query:
        await query.answer()
        await query.edit_message_text(texts.CANCELLED, reply_markup=kb.back("menu:main"))
    return ConversationHandler.END


def conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(new_project_start, pattern=r"^proj:new$")],
        states={
            P_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_project_title)],
            P_TYPE: [CallbackQueryHandler(new_project_type, pattern=r"^ptype:")],
            P_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_project_desc)],
            P_DL: [
                CallbackQueryHandler(new_project_dl_btn, pattern=r"^dl:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_project_dl_text),
            ],
            DL_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_project_dl_text)],
        },
        fallbacks=[CallbackQueryHandler(new_project_cancel, pattern=r"^proj:cancel$")],
        per_message=False,
    )
