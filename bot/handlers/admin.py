"""Admin panel + team view handlers."""
from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import keyboards as kb
from bot import texts
from bot.config import ADMIN_IDS, DB_PATH, ROLES
from bot.utils import esc, is_manager, role_badge, user_of

logger = logging.getLogger("yp-mgmt")
MAX_RESTORE_BYTES = 20 * 1024 * 1024
REQUIRED_TABLES = {"users", "projects", "tasks"}


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


async def _send_backup(query, chat) -> bool:
    """Snapshot the DB into the current chat; True on success."""
    try:
        fname = f"yp-mgmt-backup-{datetime.utcnow():%Y-%m-%d-%H%M}.db"
        with open(DB_PATH, "rb") as fh:
            await chat.reply_document(fh, filename=fname)
        return True
    except Exception:
        return False


async def cmd_reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reset_all — full factory reset (board + members + roles), ADMIN_IDS only.
    Sends a safety backup first; wipes only after explicit confirmation."""
    user = user_of(update, context)
    uid = update.effective_user.id if update.effective_user else None
    if uid not in ADMIN_IDS or not update.effective_message:
        return
    sent = await _send_backup(None, update.effective_message)
    await update.effective_message.reply_text(
        "💣 <b>ریست کامل کارخانه‌ای</b>\n─────────────────────\n"
        + ("📦 بکاپ اضطراری بالا فرستاده شد — اگه پشیمون شدی با /restore برش گردون.\n"
           if sent else "⚠️ ارسال بکاپ اضطراری ممکن نشد!\n")
        + "همه‌ی <b>پروژه‌ها، تسک‌ها، اعضا و نقش‌ها</b> برای همیشه پاک می‌شن.\n"
        "مطمئنی؟",
        reply_markup=kb.reset_confirm())


async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/restore — arm the bot to accept the next backup file (.db) from a manager."""
    user = user_of(update, context)
    if not is_manager(user) or not update.effective_message:
        return
    context.user_data["restore_pending"] = True
    await update.effective_message.reply_text(
        "📦 <b>حالت بازگردانی فعال شد</b>\n─────────────────────\n"
        "فایل بکاپ (`.db`) که با /backup گرفتی رو همین‌جا بفرست.\n"
        "اول سالم بودنش چک می‌شه، بعد جایگزین دیتابیس فعال می‌شه.\n"
        "⚠️ دیتای فعلی با نام `.pre-restore` نگه داشته می‌شه.")


async def restore_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Incoming document handler: restores a validated SQLite backup file."""
    user = user_of(update, context)
    msg = update.effective_message
    if not user or not msg or not msg.document or not is_manager(user):
        return
    if not context.user_data.get("restore_pending"):
        return  # bot is not expecting a file — ignore silently
    context.user_data["restore_pending"] = False

    doc = msg.document
    if doc.file_size and doc.file_size > MAX_RESTORE_BYTES:
        await msg.reply_text(f"❌ فایل بیشتر از {MAX_RESTORE_BYTES // (1024 * 1024)} مگابایته — با /backup جدید بگیر.")
        return

    tmp = Path(str(DB_PATH) + ".incoming")
    try:
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(custom_path=str(tmp))

        # validate BEFORE touching the live database
        try:
            con = sqlite3.connect(tmp)
            try:
                integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
                tables = {r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                con.close()
        except sqlite3.Error as exc:
            integrity, tables = f"خطا: {exc}", set()
        if integrity != "ok" or not REQUIRED_TABLES <= tables:
            os.remove(tmp)
            await msg.reply_text(
                f"❌ فایل معتبر نیست (integrity: {esc(integrity)}).\n"
                "مطمئن شو همون بکاپی هست که خود ربات فرستاده.")
            return

        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        if Path(DB_PATH).exists():
            shutil.copy2(DB_PATH, str(DB_PATH) + ".pre-restore")
        os.replace(tmp, DB_PATH)
        for side in (str(DB_PATH) + "-wal", str(DB_PATH) + "-shm"):
            if os.path.exists(side):
                os.remove(side)

        s = db.stats()
        await msg.reply_text(
            "✅ <b>بکاپ بازگردانی شد!</b>\n─────────────────────\n"
            f"📁 پروژه: <b>{s['projects']}</b> · 🧩 تسک: <b>{s['tasks']}</b> · "
            f"👥 عضو: <b>{s['members']}</b>\n"
            "نسخه‌ی قبلی در `data/…db.pre-restore` حفظ شد.")
    except Exception as e:  # noqa: BLE001 — report, never leave junk
        logger.exception("restore failed")
        if tmp.exists():
            try:
                os.remove(tmp)
            except OSError:
                pass
        await msg.reply_text(f"❌ خطا در بازگردانی: {esc(e)}")


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
        await _send_backup(query, query.message)
        await query.answer("💾 بکاپ برات ارسال شد")

    elif action == "reset_go":
        if user["tg_id"] not in ADMIN_IDS:
            await query.answer("فقط ادمین اصلی (ADMIN_IDS) مجاز به ریست کامله",
                               show_alert=True)
            return
        db.wipe_all()
        await query.edit_message_text(
            "🧨 <b>ربات کامل ریست شد</b>\n─────────────────────\n"
            "پروژه‌ها، تسک‌ها، اعضا و نقش‌ها — همه صفر.\n"
            "برای شروع دوباره: توی گروه /start بزنید 🚀",
            reply_markup=kb.back("menu:main"))

    elif action == "reset_no":
        await query.edit_message_text("🙅 هیچی پاک نشد — امن موند.",
                                      reply_markup=kb.admin_menu())


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
