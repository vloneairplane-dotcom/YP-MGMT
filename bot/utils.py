"""Shared helpers: permissions, formatting, deadline math."""
from __future__ import annotations

from datetime import datetime, timedelta
from html import escape as _html_escape

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot import jdate
from bot.config import MANAGER_ROLES, ROLES


def esc(value) -> str:
    """HTML-escape user-generated text before embedding in HTML messages."""
    return _html_escape(str(value or ""), quote=False)


def user_of(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Upsert and return the DB user for the current Telegram user."""
    tg_user = update.effective_user
    if not tg_user:
        return None
    row = db.upsert_user(
        tg_user.id, tg_user.full_name, tg_user.username,
        is_admin=tg_user.id in context.bot_data.get("admin_ids", set()),
    )
    return dict(row)


def is_manager(user: dict | None) -> bool:
    return bool(user and user.get("role") in MANAGER_ROLES)


def role_badge(user: dict | None) -> str:
    if not user or not user.get("role"):
        return "🎯 <i>نقش انتخاب‌نشده</i>"
    r = ROLES.get(user["role"], {"emoji": "👤", "label": user["role"]})
    return f"{r['emoji']} <b>{r['label']}</b>"


def days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        target = datetime.fromisoformat(deadline[:10])
    except ValueError:
        return None
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (target.replace(hour=0, minute=0, second=0, microsecond=0) - today).days


def deadline_badge(deadline: str | None) -> str:
    d = days_left(deadline)
    if d is None:
        return "بدون ددلاین"
    if d < 0:
        return f"⛔ گذشته ({abs(d)} روز)"
    if d == 0:
        return "🔥 امروز!"
    if d == 1:
        return "⚡ فردا"
    if d <= 3:
        return f"⚠️ {d} روز مونده"
    return f"📅 {d} روز مونده"


def parse_deadline(text: str) -> str | None:
    """Human-typed deadline → ISO Gregorian for storage. Speaks Jalali first:
    '۱۴/۰۸/۱۶', '16 آبان', '10 روز دیگر', 'فردا', ISO Gregorian, '+7'."""
    return jdate.parse(text)


def date_disp(deadline: str | None) -> str:
    """Stored ISO Gregorian → Persian Jalali display (۱۴۰۵/۰۸/۱۶), wrapped in LRM
    marks so RTL bidi never flips digits."""
    if not deadline:
        return "—"
    j = jdate.jalali_disp(deadline)
    if j:
        return f"\u200e{j}\u200e"
    return f"\u200e{esc(deadline)}\u200e"


def progress_bar(done: int, total: int, width: int = 8) -> str:
    if total == 0:
        return "▫️" * width
    filled = round(width * done / total)
    return "🟪" * filled + "⬜" * (width - filled)
