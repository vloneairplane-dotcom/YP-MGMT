"""SQLite persistence layer for Ye Pesare MGMT bot + dashboard."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from bot.config import DB_PATH, DEMO_SEED

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    full_name TEXT,
    role TEXT,
    is_admin INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    joined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    ptype TEXT DEFAULT 'other',
    status TEXT DEFAULT 'idea',
    deadline TEXT,
    created_by INTEGER,
    chat_id INTEGER,
    archived INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    assignee_id INTEGER,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT 'normal',
    deadline TEXT,
    created_at TEXT NOT NULL,
    done_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    category TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    detail TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    task_id INTEGER,
    kind TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    UNIQUE(project_id, task_id, kind)
);
"""


def now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


@contextmanager
def get_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(SCHEMA)


# ---------------------------------------------------------------- users
def upsert_user(tg_id: int, full_name: str, username: str | None = None,
                is_admin: bool = False) -> sqlite3.Row:
    with get_db() as db:
        db.execute(
            """INSERT INTO users (tg_id, full_name, username, is_admin, joined_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(tg_id) DO UPDATE SET
                 full_name=excluded.full_name,
                 username=excluded.username,
                 is_admin=MAX(users.is_admin, excluded.is_admin)""",
            (tg_id, full_name, username, int(is_admin), now()),
        )
        return db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()


def set_role(tg_id: int, role: str) -> None:
    with get_db() as db:
        db.execute("UPDATE users SET role=? WHERE tg_id=?", (role, tg_id))


def get_user(tg_id: int) -> sqlite3.Row | None:
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()


def list_users(role: str | None = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM users WHERE is_banned=0"
    args: tuple = ()
    if role:
        q += " AND role=?"
        args = (role,)
    q += " ORDER BY joined_at"
    with get_db() as db:
        return db.execute(q, args).fetchall()


# ------------------------------------------------------------- projects
def create_project(title: str, description: str, ptype: str, deadline: str | None,
                   created_by: int, chat_id: int | None = None) -> int:
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO projects (title, description, ptype, deadline,
                                     created_by, chat_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, description, ptype, deadline, created_by, chat_id, now()),
        )
        return int(cur.lastrowid)


def get_project(pid: int) -> sqlite3.Row | None:
    with get_db() as db:
        return db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()


def list_projects(archived: int = 0) -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute(
            "SELECT * FROM projects WHERE archived=? ORDER BY "
            "CASE WHEN deadline IS NULL THEN 1 ELSE 0 END, deadline, id DESC",
            (archived,),
        ).fetchall()


def update_project(pid: int, **fields) -> None:
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with get_db() as db:
        db.execute(f"UPDATE projects SET {keys} WHERE id=?", (*fields.values(), pid))


def set_project_status(pid: int, status: str) -> None:
    update_project(pid, status=status)


def archive_project(pid: int) -> None:
    update_project(pid, archived=1)


# ---------------------------------------------------------------- tasks
def create_task(project_id: int, title: str, assignee_id: int | None,
                description: str = "", priority: str = "normal",
                deadline: str | None = None) -> int:
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO tasks (project_id, assignee_id, title, description,
                                  priority, deadline, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, assignee_id, title, description, priority, deadline, now()),
        )
        return int(cur.lastrowid)


def get_task(tid: int) -> sqlite3.Row | None:
    with get_db() as db:
        return db.execute(
            """SELECT t.*, p.title AS project_title FROM tasks t
               JOIN projects p ON p.id = t.project_id WHERE t.id=?""",
            (tid,),
        ).fetchone()


def list_tasks(project_id: int | None = None, assignee_id: int | None = None,
               status: str | None = None) -> list[sqlite3.Row]:
    q = """SELECT t.*, p.title AS project_title, u.full_name AS assignee_name,
                  u.tg_id AS assignee_tg
           FROM tasks t
           JOIN projects p ON p.id = t.project_id
           LEFT JOIN users u ON u.id = t.assignee_id
           WHERE p.archived=0"""
    args: list = []
    if project_id is not None:
        q += " AND t.project_id=?"
        args.append(project_id)
    if assignee_id is not None:
        q += " AND t.assignee_id=?"
        args.append(assignee_id)
    if status:
        q += " AND t.status=?"
        args.append(status)
    q += """ ORDER BY CASE t.status WHEN 'done' THEN 1 ELSE 0 END,
             CASE t.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
                  WHEN 'normal' THEN 2 ELSE 3 END,
             t.deadline IS NULL, t.deadline"""
    with get_db() as db:
        return db.execute(q, args).fetchall()


def set_task_status(tid: int, status: str) -> None:
    done_at = now() if status == "done" else None
    with get_db() as db:
        db.execute("UPDATE tasks SET status=?, done_at=? WHERE id=?",
                   (status, done_at, tid))


def assign_task(tid: int, assignee_id: int) -> None:
    with get_db() as db:
        db.execute("UPDATE tasks SET assignee_id=? WHERE id=?", (assignee_id, tid))


def delete_task(tid: int) -> None:
    with get_db() as db:
        db.execute("DELETE FROM tasks WHERE id=?", (tid,))


# ---------------------------------------------------------------- ideas
def log_idea(user_id: int | None, category: str, content: str) -> None:
    with get_db() as db:
        db.execute(
            "INSERT INTO ideas (user_id, category, content, created_at) VALUES (?,?,?,?)",
            (user_id, category, content, now()),
        )


def recent_ideas(limit: int = 12) -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute(
            "SELECT * FROM ideas ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


# ------------------------------------------------------------- activity
def log_activity(user_id: int | None, action: str, detail: str = "") -> None:
    with get_db() as db:
        db.execute(
            "INSERT INTO activity (user_id, action, detail, created_at) VALUES (?,?,?,?)",
            (user_id, action, detail, now()),
        )


def recent_activity(limit: int = 15) -> list[sqlite3.Row]:
    with get_db() as db:
        return db.execute(
            """SELECT a.*, u.full_name FROM activity a
               LEFT JOIN users u ON u.id = a.user_id
               ORDER BY a.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()


# ------------------------------------------------------------ reminders
def already_reminded(project_id: int | None, task_id: int | None, kind: str) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT 1 FROM reminders WHERE project_id IS ? AND task_id IS ? AND kind=?",
            (project_id, task_id, kind),
        ).fetchone()
        return row is not None


def mark_reminded(project_id: int | None, task_id: int | None, kind: str) -> None:
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO reminders (project_id, task_id, kind, sent_at)"
            " VALUES (?,?,?,?)",
            (project_id, task_id, kind, now()),
        )


# ---------------------------------------------------------------- stats
def stats() -> dict:
    with get_db() as db:
        one = lambda q, *a: db.execute(q, a).fetchone()[0]  # noqa: E731
        return {
            "projects": one("SELECT COUNT(*) FROM projects WHERE archived=0"),
            "projects_done": one(
                "SELECT COUNT(*) FROM projects WHERE archived=0 AND status='done'"),
            "tasks": one(
                """SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id=t.project_id
                   WHERE p.archived=0"""),
            "tasks_done": one(
                """SELECT COUNT(*) FROM tasks t JOIN projects p ON p.id=t.project_id
                   WHERE p.archived=0 AND t.status='done'"""),
            "members": one("SELECT COUNT(*) FROM users WHERE is_banned=0"),
            "ideas": one("SELECT COUNT(*) FROM ideas"),
        }


def wipe_data() -> int:
    """Delete all projects/tasks/ideas/activity/reminders (members & roles stay)."""
    with get_db() as db:
        n = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        for table in ("tasks", "projects", "ideas", "activity", "reminders"):
            db.execute(f"DELETE FROM {table}")
    return n


def seed_demo() -> None:
    """Insert realistic demo data so the glass dashboard looks alive.

    Opt-in only (DEMO_SEED=1) — a fresh production board starts empty
    so the team can build it themselves from scratch.
    """
    if not DEMO_SEED:
        return
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] > 0:
            return

    members = [
        (1001, "Vlone 🕊️", "vloneairplane", "manager"),
        (1002, "Ye Pesare", "ye_pesare", "artist"),
        (1003, "Dana", "dana_beats", "producer"),
        (1004, "Nima", "nima_design", "designer"),
        (1005, "Sara", "sara_mgmt", "admin"),
    ]
    for tg, name, uname, role in members:
        u = upsert_user(tg, name, uname, is_admin=(role == "admin"))
        set_role(tg, role)
        _ = u

    today = datetime.utcnow()
    d = lambda n: (today + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731

    demo_projects = [
        ("دانا بیت", "بیت جدید برای سینگل بعدی — تم شب/شهر، BPM حدود ۱۴۰", "beat", "mix", d(4)),
        ("عکاسی قدیمیه", "شوت عکاسی برای کاور سینگل — فیلم ۳۵ میلی‌متری، تم نوستالژی", "cover", "demo", d(9)),
        ("دو نفر", "سینگل مشترک — فیت با آرتیست مهمان، دمو اولیه آماده", "single", "record", d(7)),
        ("از صفر", "سینگل اصلی ای‌پی — متن اولیه نوشته‌شده، نیاز به ضبط وکال", "single", "demo", d(12)),
        ("بدون همه‌چی", "اسلحه‌ی احساسی ای‌پی — ملودی پیانو، فضای مینیمال", "single", "idea", d(21)),
        ("03:17", "اینترود ای‌پی — اتمسفریک با صدای محیط شهر ساعت ۳:۱۷ صبح", "ep", "idea", d(28)),
        ("یل پسر (تایتل‌ترک)", "تایتل‌ترک ای‌پی «یه پسر» — باید تا آخر ماه به مستر برسه", "ep", "mix", d(2)),
    ]
    pids = []
    for title, desc, ptype, status, deadline in demo_projects:
        pid = create_project(title, desc, ptype, deadline, 1, None)
        update_project(pid, status=status)
        pids.append(pid)

    demo_tasks = [
        (pids[0], 3, "ادامه‌ی آرایش بیت (ورس دوم)", "اضافه کردن لایه‌های پد و تغییر درام در هوک", "doing", "high", d(1)),
        (pids[0], 3, "ارسال نسخه‌ی ۲ بیت برای تیم", "", "pending", "normal", d(2)),
        (pids[1], 4, "طراحی موودبورد شوت", "رنگ‌بندی، لوکیشن، لباس — ارجاع به تم نوستالژی", "done", "normal", d(-1)),
        (pids[1], 4, "طراحی کاور نهایی", "نسخه‌ی اولیه‌ی کاور با تایپوگرافی فارسی", "pending", "high", d(8)),
        (pids[2], 2, "ضبط وکال ورس اول", "", "doing", "urgent", d(2)),
        (pids[2], 3, "میکس دموی نهایی", "قبل از ارسال برای مستر", "pending", "high", d(5)),
        (pids[3], 2, "نوشتن ورس دوم", "تم «از صفر» — شروع دوباره", "pending", "normal", d(6)),
        (pids[4], 1, "ایده‌پردازی متن", "", "pending", "low", d(15)),
        (pids[6], 1, "هماهنگی سشن مستر با استودیو", "رزرو سشن برای مستر نهایی", "doing", "urgent", d(1)),
        (pids[6], 4, "طراحی پکیج ریلیز", "کاور، بنرهای پلتفرم‌ها، محتوای پرومو", "pending", "high", d(3)),
    ]
    for project_id, assignee, title, desc, status, prio, deadline in demo_tasks:
        tid = create_task(project_id, title, assignee, desc, prio, deadline)
        if status != "pending":
            set_task_status(tid, status)

    for cat, content in [
        ("concept", "ترکی «ساعت سه‌ونیم‌بیدار» — بی‌خوابی شهری با ساختار سه‌پاره"),
        ("beat", "بیت درام‌محور با تمپو ۱۴۰ + اینسِترمنت نوستالژیک دهه‌ی ۸۰"),
        ("visual", "کاور سیاه‌وسفید با یک نقطه‌ی نئونی — مینیمال و خشن"),
    ]:
        log_idea(1002, cat, content)

    for action, detail in [
        ("seed", "داده‌ی دمو ساخته شد"),
        ("project", "پروژه «دانا بیت» ساخته شد"),
        ("task", "تسک «ادامه‌ی آرایش بیت» به Dana داده شد"),
    ]:
        log_activity(1001, action, detail)
