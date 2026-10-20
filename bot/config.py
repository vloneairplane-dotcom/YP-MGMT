"""Configuration loaded from environment / .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID") or 0) or None
# Render (and similar PaaS) inject PORT — honor it so the proxy can reach us
DASH_PORT = int(os.getenv("PORT") or os.getenv("DASH_PORT", "8000"))
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/yp_mgmt.db")

# ---------- Roles ----------
ROLES = {
    "artist": {"label": "آرتیست", "emoji": "🎤"},
    "producer": {"label": "پرودیوسر", "emoji": "🎛️"},
    "designer": {"label": "دیزاینر", "emoji": "🎨"},
    "manager": {"label": "منیجر", "emoji": "🧑‍💼"},
    "admin": {"label": "ادمین", "emoji": "👑"},
}

# Who can manage projects / assign tasks
MANAGER_ROLES = {"manager", "admin"}

# ---------- Project ----------
PROJECT_TYPES = {
    "beat": {"label": "بیت", "emoji": "🎹"},
    "demo": {"label": "دمو", "emoji": "🎙️"},
    "single": {"label": "سینگل", "emoji": "💿"},
    "ep": {"label": "ای‌پی / آلبوم", "emoji": "📀"},
    "cover": {"label": "کاور / عکاسی", "emoji": "📸"},
    "mv": {"label": "موزیک‌ویدیو", "emoji": "🎬"},
    "mix": {"label": "میکس / مستر", "emoji": "🎚️"},
    "other": {"label": "سایر", "emoji": "📦"},
}

PROJECT_STATUSES = {
    "idea": {"label": "ایده", "emoji": "💡"},
    "demo": {"label": "دمو", "emoji": "🎤"},
    "record": {"label": "ضبط", "emoji": "🎙️"},
    "mix": {"label": "میکس", "emoji": "🎛️"},
    "master": {"label": "مستر", "emoji": "🎚️"},
    "release": {"label": "ریلیز", "emoji": "🚀"},
    "done": {"label": "تمام‌شده", "emoji": "✅"},
}

STATUS_FLOW = ["idea", "demo", "record", "mix", "master", "release", "done"]

TASK_STATUSES = {
    "pending": {"label": "در انتظار", "emoji": "⏳"},
    "doing": {"label": "در حال انجام", "emoji": "🔄"},
    "review": {"label": "در حال بررسی", "emoji": "🔍"},
    "done": {"label": "انجام‌شده", "emoji": "✅"},
}

TASK_PRIORITIES = {
    "low": {"label": "کم", "emoji": "🟢"},
    "normal": {"label": "معمولی", "emoji": "🟡"},
    "high": {"label": "زیاد", "emoji": "🟠"},
    "urgent": {"label": "فوری", "emoji": "🔴"},
}

IDEA_CATEGORIES = {
    "concept": {"label": "کانسپت آهنگ", "emoji": "🎵"},
    "beat": {"label": "بیت و سبک", "emoji": "🎹"},
    "lyrics": {"label": "تم متن", "emoji": "📝"},
    "visual": {"label": "کاور و ویژوال", "emoji": "🎨"},
    "release": {"label": "استراتژی ریلیز", "emoji": "📣"},
    "collab": {"label": "کالب و همکاری", "emoji": "🤝"},
}
