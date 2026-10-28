"""All user-facing Persian texts of the bot."""
from __future__ import annotations

from datetime import datetime

from bot import jdate
from bot.config import (IDEA_CATEGORIES, PROJECT_STATUSES, PROJECT_TYPES,
                        ROLES, TASK_PRIORITIES, TASK_STATUSES)
from bot.utils import date_disp, esc

BRAND = "Ye Pesare · Management"
BRAND_FA = "یه پسر | پنل مدیریت تیم"

WELCOME = (
    "🪩 <b>{name}</b> خوش برگشتی به {brand}\n"
    "─────────────────────\n"
    "پنل مدیریت تیم، پروژه و تسک‌ها.\n"
    "نقشتو انتخاب کن تا وارد بشی 👇"
)

MAIN_MENU = (
    "🎛️ <b>{brand}</b>\n"
    "سلام {name} {role_badge}\n"
    "─────────────────────\n"
    "📊 پروژه‌های فعال: <b>{projects}</b>  |  ✅ تسک انجام‌شده: <b>{tasks_done}/{tasks}</b>\n"
    "👥 اعضای تیم: <b>{members}</b>  |  💡 ایده‌ها: <b>{ideas}</b>\n"
    "─────────────────────\n"
    "از منوی زیر یکی رو انتخاب کن 👇"
)

HELP = (
    "📖 <b>راهنمای {brand}</b>\n"
    "─────────────────────\n"
    "📁 <b>پروژه‌ها</b> — لیست پروژه‌ها با ددلاین و وضعیت\n"
    "➕ <b>پروژه جدید</b> — ساخت پروژه با ددلاین مشخص\n"
    "💡 <b>ایده بگیر</b> — ایده‌ی خودکار برای ترک، بیت، کاور و ریلیز\n"
    "📊 <b>وضعیت تسک</b> — تسک‌هات رو ببین و وضعیتشون رو عوض کن\n"
    "👥 <b>تیم</b> — اعضا و نقش‌ها\n"
    "⚙️ <b>ادمین</b> — تنظیمات، آمار و مدیریت اعضا\n"
    "─────────────────────\n"
    "🆔 دستورهای گروه:\n"
    "/start — ثبت‌نام و انتخاب نقش\n"
    "/team — لیست تیم\n"
    "/tasks — تسک‌های من\n"
    "/deadline — نزدیک‌ترین ددلاین‌ها\n"
    "/idea — یه ایده‌ی سریع\n"
    "/whoami — نقش من\n"
    "🔐 دستورهای مدیر:\n"
    "/backup — گرفتن بکاپ دیتابیس در دی‌ام\n"
    "/restore — بازگردانی بکاپ (فایل .db رو بفرست)\n"
    "/wipe — خالی‌کردن بورد با تأییدیه\n"
    "/reset_all — ریست کامل کارخانه‌ای (اعضا+نقش‌ها هم پاک!)"
)


def role_pick_text(name: str) -> str:
    return (
        f"👤 <b>{name}</b> نقشت توی تیم چیه؟\n"
        "─────────────────────\n"
        "هر نقش دسترسی‌های خودش رو داره:"
    )


ROLES_DESC = (
    "🎤 <b>آرتیست</b> — اجرای وکال، ایده‌پردازی متن\n"
    "🎛️ <b>پرودیوسر</b> — بیت، میکس و مستر\n"
    "🎨 <b>دیزاینر</b> — کاور، ویژوال و محتوای بصری\n"
    "🧑‍💼 <b>منیجر</b> — مدیریت پروژه، تسک و ددلاین\n"
    "👑 <b>ادمین</b> — دسترسی کامل + مدیریت اعضا"
)


def role_set_text(role_key: str) -> str:
    r = ROLES[role_key]
    return f"✅ نقش تو ثبت شد: {r['emoji']} <b>{r['label']}</b>\nحالا از منوی اصلی شروع کن 👇"


PROJECT_LIST_HEADER = "📁 <b>پروژه‌ها:</b>\n─────────────────────"


def project_card_short(p) -> str:
    t = PROJECT_TYPES.get(p["ptype"], {"label": "?", "emoji": "📦"})
    s = PROJECT_STATUSES.get(p["status"], {"label": "?", "emoji": "❓"})
    dl = f"⏰ {date_disp(p['deadline'])}" if p["deadline"] else "⏰ بدون ددلاین"
    return (
        f"{t['emoji']} <b>{esc(p['title'])}</b>\n"
        f"   {s['emoji']} {s['label']}  |  {dl}"
    )


def project_detail(p, tasks) -> str:
    t = PROJECT_TYPES.get(p["ptype"], {"label": "?", "emoji": "📦"})
    s = PROJECT_STATUSES.get(p["status"], {"label": "?", "emoji": "❓"})
    desc = esc(p["description"]) or "—"
    lines = [
        f"{t['emoji']} <b>{esc(p['title'])}</b>",
        "─────────────────────",
        f"📄 {desc}",
        f"{s['emoji']} وضعیت: <b>{s['label']}</b>",
        f"⏰ ددلاین: <b>{date_disp(p['deadline'])}</b>",
        "─────────────────────",
        f"📋 <b>تسک‌ها ({len(tasks)}):</b>",
    ]
    if not tasks:
        lines.append("   — تسکی ثبت نشده")
    for tk in tasks:
        ts = TASK_STATUSES.get(tk["status"], {"label": "?", "emoji": "❓"})
        pr = TASK_PRIORITIES.get(tk["priority"], {"label": "?", "emoji": "🟡"})
        who = esc(tk["assignee_name"]) or "—"
        lines.append(
            f"   {ts['emoji']} <b>#{tk['id']}</b> {esc(tk['title'])}\n"
            f"      👤 {who} | {pr['emoji']} {pr['label']} | ⏰ {date_disp(tk['deadline'])}"
        )
    return "\n".join(lines)


def task_line(tk) -> str:
    ts = TASK_STATUSES.get(tk["status"], {"label": "?", "emoji": "❓"})
    pr = TASK_PRIORITIES.get(tk["priority"], {"label": "?", "emoji": "🟡"})
    return (
        f"{ts['emoji']} <b>#{tk['id']}</b> {esc(tk['title'])}\n"
        f"   📁 {esc(tk['project_title'])} | 👤 {esc(tk['assignee_name']) or '—'} | "
        f"{pr['emoji']} {pr['label']} | ⏰ {date_disp(tk['deadline'])}"
    )


def idea_card(category: str, text: str) -> str:
    meta = IDEA_CATEGORIES.get(category, {"label": "ایده", "emoji": "💡"})
    return (
        f"{meta['emoji']} <b>ایده — {meta['label']}</b>\n"
        "─────────────────────\n"
        f"{text}"
    )


def full_brief_text(brief: dict[str, str]) -> str:
    lines = ["🧠 <b>بریف کامل پروژه — از ایده تا ریلیز</b>", "─────────────────────"]
    for key, text in brief.items():
        emoji, label = "💡", key
        meta = IDEA_CATEGORIES.get(key)
        if meta:
            emoji, label = meta["emoji"], meta["label"]
        lines.append(f"{emoji} <b>{label}:</b>\n{text}")
    return "\n".join(lines)


TEAM_HEADER = "👥 <b>تیم یه پسر</b>\n─────────────────────"
STATS_HEADER = "📊 <b>آمار کلی</b>\n─────────────────────"
DEADLINE_HEADER = "⏰ <b>ددلاین‌های نزدیک</b>\n─────────────────────"
NOT_SET_ROLE = "⚠️ هنوز نقشت رو انتخاب نکردی — از منوی اصلی «نقش من» رو بزن."
NO_PERMISSION = "⛔ این بخش فقط برای منیجر/ادمین‌هاست."
CANCELLED = "❎ عملیات لغو شد."

GROUP_LOCK_DM = (
    "🔐 <b>این ربات فقط توی گروه کاری فعاله</b>\n"
    "─────────────────────\n"
    "اگه عضو تیمی: برو همین‌جا توی گروهت <code>/start</code> بزن 🚀\n"
    "اگه عضو تیم نیستی: اینجا جای تو نیست 🙂"
)
UNKNOWN = "🤔 متوجه نشدم — از دکمه‌های زیر استفاده کن."
BACK = "🔙 بازگشت"


def fmt_dt(iso: str | None) -> str:
    """ISO timestamp → '۱۴۰۵/۰۸/۰۶ — ۱۲:۳۱' (Jalali with Persian digits)."""
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    j = jdate.jalali_disp(dt.strftime("%Y-%m-%d"))
    if not j:
        return iso[:16].replace("T", " ")
    time_str = f"{dt.hour:02d}:{dt.minute:02d}".translate(jdate.FA_DIGITS)
    return f"{j} — {time_str}"
