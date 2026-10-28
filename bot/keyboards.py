"""Inline keyboards — glass-panel style menu layout (mirrors the design mockup)."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import (IDEA_CATEGORIES, PROJECT_STATUSES, PROJECT_TYPES,
                        ROLES, TASK_PRIORITIES, TASK_STATUSES)
from bot import texts


def role_pick() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(f"{ROLES['artist']['emoji']} {ROLES['artist']['label']}",
                                 callback_data="role:artist"),
            InlineKeyboardButton(f"{ROLES['producer']['emoji']} {ROLES['producer']['label']}",
                                 callback_data="role:producer"),
        ],
        [
            InlineKeyboardButton(f"{ROLES['designer']['emoji']} {ROLES['designer']['label']}",
                                 callback_data="role:designer"),
            InlineKeyboardButton(f"{ROLES['manager']['emoji']} {ROLES['manager']['label']}",
                                 callback_data="role:manager"),
        ],
        [
            InlineKeyboardButton(f"{ROLES['admin']['emoji']} {ROLES['admin']['label']}",
                                 callback_data="role:admin"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def main_menu(has_role: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📁 پروژه‌ها", callback_data="menu:projects"),
            InlineKeyboardButton("➕ پروژه جدید", callback_data="proj:new"),
        ],
        [
            InlineKeyboardButton("💡 ایده بگیر", callback_data="menu:ideas"),
            InlineKeyboardButton("📊 وضعیت تسک", callback_data="menu:tasks"),
        ],
        [
            InlineKeyboardButton("⏰ ددلاین‌ها", callback_data="menu:deadlines"),
            InlineKeyboardButton("👥 تیم", callback_data="menu:team"),
        ],
        [
            InlineKeyboardButton("⚙️ ادمین", callback_data="menu:admin"),
            InlineKeyboardButton("📖 راهنما", callback_data="menu:help"),
        ],
    ]
    if not has_role:
        rows.insert(0, [InlineKeyboardButton("🎯 انتخاب نقش من", callback_data="menu:role")])
    return InlineKeyboardMarkup(rows)


def back(to: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(texts.BACK, callback_data=to)]]
    )


def projects_list(projects) -> InlineKeyboardMarkup:
    rows = []
    for p in projects:
        from bot.config import PROJECT_STATUSES as PS, PROJECT_TYPES as PT
        t = PT.get(p["ptype"], {"emoji": "📦"})
        s = PS.get(p["status"], {"emoji": "❓"})
        label = f"{t['emoji']} {p['title']} · {s['emoji']}"
        rows.append([InlineKeyboardButton(label, callback_data=f"proj:view:{p['id']}")])
    rows.append([InlineKeyboardButton("➕ پروژه جدید", callback_data="proj:new")])
    rows.append([InlineKeyboardButton(texts.BACK, callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def project_detail(pid: int, is_manager: bool) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton("📋 تسک‌ها", callback_data=f"task:list:{pid}"),
        InlineKeyboardButton("➕ تسک جدید", callback_data=f"task:new:{pid}"),
    ]]
    if is_manager:
        rows.append([
            InlineKeyboardButton("➡️ وضعیت بعدی", callback_data=f"proj:next:{pid}"),
            InlineKeyboardButton("📌 وضعیت…", callback_data=f"proj:status:{pid}"),
        ])
        rows.append([
            InlineKeyboardButton("✏️ ویرایش ددلاین", callback_data=f"proj:dl:{pid}"),
            InlineKeyboardButton("🗄 آرشیو", callback_data=f"proj:archive:{pid}"),
        ])
    rows.append([InlineKeyboardButton(texts.BACK, callback_data="menu:projects")])
    return InlineKeyboardMarkup(rows)


def project_status_pick(pid: int) -> InlineKeyboardMarkup:
    rows = []
    items = list(PROJECT_STATUSES.items())
    for i in range(0, len(items), 2):
        row = []
        for key, meta in items[i:i + 2]:
            row.append(InlineKeyboardButton(
                f"{meta['emoji']} {meta['label']}", callback_data=f"proj:set:{pid}:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(texts.BACK, callback_data=f"proj:view:{pid}")])
    return InlineKeyboardMarkup(rows)


def project_type_pick() -> InlineKeyboardMarkup:
    rows, items = [], list(PROJECT_TYPES.items())
    for i in range(0, len(items), 2):
        row = []
        for key, meta in items[i:i + 2]:
            row.append(InlineKeyboardButton(
                f"{meta['emoji']} {meta['label']}", callback_data=f"ptype:{key}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def deadline_pick(prefix: str = "dl", pid: int | None = None) -> InlineKeyboardMarkup:
    """Quick deadline buttons. With `pid` they target `{prefix}:{pid}:{val}`
    (used by the standalone deadline-edit flow); otherwise `{prefix}:{val}`."""
    def data(val: str) -> str:
        return f"{prefix}:{pid}:{val}" if pid is not None else f"{prefix}:{val}"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 ۳ روز", callback_data=data("3")),
            InlineKeyboardButton("📅 ۱ هفته", callback_data=data("7")),
        ],
        [
            InlineKeyboardButton("📅 ۲ هفته", callback_data=data("14")),
            InlineKeyboardButton("📅 ۱ ماه", callback_data=data("30")),
        ],
        [
            InlineKeyboardButton("✍️ تاریخ دستی", callback_data=data("manual")),
            InlineKeyboardButton("🚫 بدون ددلاین", callback_data=data("none")),
        ],
    ])


def tasks_list(tasks, prefix: str = "task:view") -> InlineKeyboardMarkup:
    rows = []
    for tk in tasks[:20]:
        ts = TASK_STATUSES.get(tk["status"], {"emoji": "❓"})
        label = f"{ts['emoji']} #{tk['id']} {tk['title'][:24]}"
        rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}:{tk['id']}")])
    rows.append([InlineKeyboardButton(texts.BACK, callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def task_detail(tid: int, project_id: int, is_manager: bool) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton("✅ انجام شد", callback_data=f"task:st:{tid}:done"),
        InlineKeyboardButton("🔄 در حال انجام", callback_data=f"task:st:{tid}:doing"),
    ], [
        InlineKeyboardButton("🔍 بررسی", callback_data=f"task:st:{tid}:review"),
        InlineKeyboardButton("⏳ انتظار", callback_data=f"task:st:{tid}:pending"),
    ]]
    if is_manager:
        rows.append([InlineKeyboardButton("🗑 حذف تسک", callback_data=f"task:del:{tid}")])
    rows.append([InlineKeyboardButton(texts.BACK, callback_data=f"proj:view:{project_id}")])
    return InlineKeyboardMarkup(rows)


def task_assignee_pick(users, project_id: int) -> InlineKeyboardMarkup:
    rows = []
    for u in users:
        r = ROLES.get(u["role"] or "", {"emoji": "👤", "label": "—"})
        rows.append([InlineKeyboardButton(
            f"{r['emoji']} {u['full_name']}", callback_data=f"task:assign:{project_id}:{u['id']}")])
    return InlineKeyboardMarkup(rows)


def task_priority_pick(project_id: int) -> InlineKeyboardMarkup:
    rows = []
    items = list(TASK_PRIORITIES.items())
    for i in range(0, len(items), 2):
        row = []
        for key, meta in items[i:i + 2]:
            row.append(InlineKeyboardButton(
                f"{meta['emoji']} {meta['label']}",
                callback_data=f"task:prio:{project_id}:{key}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def ideas_menu() -> InlineKeyboardMarkup:
    rows, items = [], list(IDEA_CATEGORIES.items())
    for i in range(0, len(items), 2):
        row = []
        for key, meta in items[i:i + 2]:
            row.append(InlineKeyboardButton(
                f"{meta['emoji']} {meta['label']}", callback_data=f"idea:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🧠 بریف کامل پروژه", callback_data="idea:full")])
    rows.append([InlineKeyboardButton(texts.BACK, callback_data="menu:main")])
    return InlineKeyboardMarkup(rows)


def idea_again(category: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 یه ایده‌ی دیگه", callback_data=f"idea:{category}")],
        [InlineKeyboardButton("💡 بقیه‌ی دسته‌ها", callback_data="menu:ideas"),
         InlineKeyboardButton(texts.BACK, callback_data="menu:main")],
    ])


def idea_full_again() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بریف جدید", callback_data="idea:full")],
        [InlineKeyboardButton(texts.BACK, callback_data="menu:main")],
    ])


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار کامل", callback_data="admin:stats"),
         InlineKeyboardButton("👥 مدیریت اعضا", callback_data="admin:members")],
        [InlineKeyboardButton("🗄 پروژه‌های آرشیو", callback_data="admin:archived"),
         InlineKeyboardButton("📣 اعلان همگانی", callback_data="admin:broadcast")],
        [InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admin:backup"),
         InlineKeyboardButton("🧹 پاک‌سازی بورد", callback_data="admin:wipe")],
        [InlineKeyboardButton(texts.BACK, callback_data="menu:main")],
    ])


def wipe_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 اول بکاپ بگیر", callback_data="admin:backup"),
         InlineKeyboardButton("🧹 بله، پاک کن", callback_data="admin:wipe_go")],
        [InlineKeyboardButton(texts.BACK, callback_data="menu:admin")],
    ])


def reset_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧨 بله، ریست کامل", callback_data="admin:reset_go"),
         InlineKeyboardButton("🙅 لغو", callback_data="admin:reset_no")],
    ])


def members_manage(users) -> InlineKeyboardMarkup:
    rows = []
    for u in users[:25]:
        r = ROLES.get(u["role"] or "", {"emoji": "👤", "label": "بدون نقش"})
        rows.append([InlineKeyboardButton(
            f"{r['emoji']} {u['full_name']}", callback_data=f"admin:user:{u['id']}")])
    rows.append([InlineKeyboardButton(texts.BACK, callback_data="menu:admin")])
    return InlineKeyboardMarkup(rows)


def member_role_pick(user_db_id: int) -> InlineKeyboardMarkup:
    rows = []
    items = list(ROLES.items())
    for i in range(0, len(items), 2):
        row = []
        for key, meta in items[i:i + 2]:
            row.append(InlineKeyboardButton(
                f"{meta['emoji']} {meta['label']}",
                callback_data=f"admin:setrole:{user_db_id}:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(texts.BACK, callback_data="admin:members")])
    return InlineKeyboardMarkup(rows)


def confirm_new_project() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأیید و ساخت", callback_data="proj:confirm")],
        [InlineKeyboardButton("❎ لغو", callback_data="proj:cancel")],
    ])
