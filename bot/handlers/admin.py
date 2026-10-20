"""Admin panel + team view handlers."""
from __future__ import annotations

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.config import DB_PATH, ROLES
from bot.utils import esc, is_manager, role_badge, user_of


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/backup — DM the SQLite file to the manager (free-host data insurance)."""
    user = user_of(update, context)
    if not is_manager(user) or not update.effective_message:
        return
    try:
        fname = f"yp-mgmt-backup-{datetime.utcnow():%Y-%m-%d-%H%M}.db"
        with open(DB_PATH, "rb") as fh:
            await update.effective_message.reply_document(fh, filename=fname)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ خطا در بکاپ: {e}")


async def cmd_wipe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/wipe — confirmation keyboard before clearing the board."""
    user = user_of(update, context)
    if not is_manager(user) or not update.effective_message:
        return
    await update.effective_message.reply_text(
        "⚠️ <b>پاک‌سازی کامل بورد</b>\n─────────────────────\n"
        "همه‌ی <b>پروژه‌ها، تسک‌ها، ایده‌ها و لاگ فعالیت</b> حذف می‌شن.\n"
        "اعضا و نقش‌ها دست‌نخورده می‌مونن.\n\n"
        "💡 پیشنهاد: اول با /backup بکاپ بگیر.",
        reply_markup=kb.wipe_confirm())


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
            lines.append(f"{r['emoji']} {esc(u['full_name'])} (@{esc(u['username'] or '—')})")
        await query.edit_message_text("\n".join(lines), reply_markup=kb.members_manage(users))

    elif action == "user":
        uid = int(data[2])
        u = db.get_user_by_id(uid)
        if not u:
            await query.edit_message_text(
                "⚠️ عضو پیدا نشد (لیست قدیمی بود) — اینتو ببین:",
                reply_markup=kb.members_manage(db.list_users()))
            return
        text = (
            f"👤 <b>{esc(u['full_name'])}</b>\n─────────────────────\n"
            f"🆔 <code>{u['tg_id']}</code>\n"
            f"{role_badge(dict(u))}\n"
            f"📅 عضویت: {texts.fmt_dt(u['joined_at'])}\n\n"
            "نقش جدید رو انتخاب کن:"
        )
        await query.edit_message_text(text, reply_markup=kb.member_role_pick(uid))

    elif action == "setrole":
        uid, role = int(data[2]), data[3]
        changed = False
        if role in ROLES:
            u = db.get_user_by_id(uid)
            if u:
                db.set_role(u["tg_id"], role)
                db.log_activity(user["id"] if user else None, "admin",
                                f"نقش {u['full_name']} → {ROLES[role]['label']}")
                changed = True
        users = db.list_users()
        msg = "✅ نقش عضو تغییر کرد." if changed else "⚠️ عضو پیدا نشد — لیست تازه رو ببین:"
        await query.edit_message_text(msg, reply_markup=kb.members_manage(users))

    elif action == "archived":
        projects = db.list_projects(archived=1)
        lines = ["🗄 <b>پروژه‌های آرشیو</b>", "─────────────────────"]
        if not projects:
            lines.append("— خالیه")
        for p in projects:
            lines.append(f"📦 {esc(p['title'])} · {p['deadline'] or '—'}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb.back("menu:admin"))

    elif action == "broadcast":
        context.user_data["broadcast"] = True
        await query.edit_message_text(
            "📣 متن اعلان همگانی رو بفرست (به همه‌ی اعضا در دی‌ام ارسال میشه):",
            reply_markup=kb.back("menu:admin"))

    elif action == "wipe":
        await query.edit_message_text(
            "⚠️ <b>پاک‌سازی کامل بورد</b>\n─────────────────────\n"
            "همه‌ی <b>پروژه‌ها، تسک‌ها، ایده‌ها و لاگ فعالیت</b> حذف می‌شن.\n"
            "اعضا و نقش‌ها دست‌نخورده می‌مونن.\n\n"
            "💡 پیشنهاد: اول بکاپ بگیر، بعد پاک کن.",
            reply_markup=kb.wipe_confirm())

    elif action == "wipe_go":
        n = db.wipe_data()
        db.log_activity(user["id"], "admin", f"پاک‌سازی بورد ({n} پروژه حذف شد)")
        await query.edit_message_text(
            f"🧹 بورد خالی شد — {n} پروژه و همه‌ی تسک‌ها/ایده‌ها حذف شدن.\n"
            "حالا از صفر بچین! ✨",
            reply_markup=kb.back("menu:admin"))

    elif action == "backup":
        try:
            fname = f"yp-mgmt-backup-{datetime.utcnow():%Y-%m-%d-%H%M}.db"
            with open(DB_PATH, "rb") as fh:
                await query.message.reply_document(fh, filename=fname)
            await query.answer("💾 بکاپ برات ارسال شد")
        except Exception as e:  # file missing etc.
            await query.answer(f"❌ خطا در بکاپ: {e}", show_alert=True)


async def show_team(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    edit: bool = False) -> None:
    users = db.list_users()
    lines = [texts.TEAM_HEADER]
    if not users:
        lines.append("— هنوز عضوی ثبت نشده")
    for u in users:
        r = ROLES.get(u["role"] or "", {"emoji": "👤", "label": "بدون نقش"})
        lines.append(f"{r['emoji']} <b>{esc(u['full_name'])}</b> · {r['label']}")
    text = "\n".join(lines)
    markup = kb.back("menu:main")
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup)
