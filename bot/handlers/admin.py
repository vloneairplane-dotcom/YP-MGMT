"""Admin panel + team view handlers."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.config import ROLES
from bot.utils import is_manager, role_badge, user_of


async def show_admin(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     edit: bool = False) -> None:
    user = user_of(update, context)
    if not is_manager(user):
        text = texts.NO_PERMISSION
        markup = kb.back()
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        elif update.effective_message:
            await update.effective_message.reply_text(text, reply_markup=markup)
        return
    text = (
        "⚙️ <b>پنل ادمین</b>\n"
        "─────────────────────\n"
        "مدیریت اعضا، آمار، آرشیو و اعلان‌ها"
    )
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb.admin_menu())
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=kb.admin_menu())


async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = user_of(update, context)
    if not is_manager(user):
        await query.answer(texts.NO_PERMISSION, show_alert=True)
        return
    await query.answer()
    data = (query.data or "").split(":")
    action = data[1] if len(data) > 1 else ""

    if action == "stats":
        s = db.stats()
        projects = db.list_projects()
        lines = [texts.STATS_HEADER]
        lines.append(f"📁 پروژه‌ی فعال: <b>{s['projects']}</b> (تمام‌شده: {s['projects_done']})")
        lines.append(f"🧩 تسک: <b>{s['tasks']}</b> (انجام‌شده: {s['tasks_done']})")
        lines.append(f"👥 عضو: <b>{s['members']}</b> | 💡 ایده ثبت‌شده: <b>{s['ideas']}</b>")
        lines.append("─────────────────────\n📂 وضعیت پروژه‌ها:")
        from bot.config import PROJECT_STATUSES as PS
        counter: dict[str, int] = {}
        for p in projects:
            counter[p["status"]] = counter.get(p["status"], 0) + 1
        for key, meta in PS.items():
            if counter.get(key):
                lines.append(f"   {meta['emoji']} {meta['label']}: {counter[key]}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb.back("menu:admin"))

    elif action == "members":
        users = db.list_users()
        lines = ["👥 <b>مدیریت اعضا</b>", "─────────────────────"]
        for u in users:
            r = ROLES.get(u["role"] or "", {"emoji": "👤", "label": "بدون نقش"})
            lines.append(f"{r['emoji']} {u['full_name']} (@{u['username'] or '—'})")
        await query.edit_message_text("\n".join(lines), reply_markup=kb.members_manage(users))

    elif action == "user":
        uid = int(data[2])
        u = db.get_user(uid)
        if not u:
            return
        text = (
            f"👤 <b>{u['full_name']}</b>\n─────────────────────\n"
            f"🆔 <code>{u['tg_id']}</code>\n"
            f"{role_badge(dict(u))}\n"
            f"📅 عضویت: {texts.fmt_dt(u['joined_at'])}\n\n"
            "نقش جدید رو انتخاب کن:"
        )
        await query.edit_message_text(text, reply_markup=kb.member_role_pick(uid))

    elif action == "setrole":
        uid, role = int(data[2]), data[3]
        if role in ROLES:
            u = db.get_user(uid)
            if u:
                db.set_role(u["tg_id"], role)
                db.log_activity(user["id"] if user else None, "admin",
                                f"نقش {u['full_name']} → {ROLES[role]['label']}")
        users = db.list_users()
        await query.edit_message_text("✅ نقش عضو تغییر کرد.",
                                      reply_markup=kb.members_manage(users))

    elif action == "archived":
        projects = db.list_projects(archived=1)
        lines = ["🗄 <b>پروژه‌های آرشیو</b>", "─────────────────────"]
        if not projects:
            lines.append("— خالیه")
        for p in projects:
            lines.append(f"📦 {p['title']} · {p['deadline'] or '—'}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb.back("menu:admin"))

    elif action == "broadcast":
        context.user_data["broadcast"] = True
        await query.edit_message_text(
            "📣 متن اعلان همگانی رو بفرست (به همه‌ی اعضا در دی‌ام ارسال میشه):",
            reply_markup=kb.back("menu:admin"))


async def show_team(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    edit: bool = False) -> None:
    users = db.list_users()
    lines = [texts.TEAM_HEADER]
    if not users:
        lines.append("— هنوز عضوی ثبت نشده")
    for u in users:
        r = ROLES.get(u["role"] or "", {"emoji": "👤", "label": "بدون نقش"})
        lines.append(f"{r['emoji']} <b>{u['full_name']}</b> · {r['label']}")
    text = "\n".join(lines)
    markup = kb.back("menu:main")
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup)
