#!/usr/bin/env python3
"""Reminder-job tests: group tagging, mentions, per-day overdue nag, dedupe."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "999:T"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "r.db")

from bot import database as db, jdate  # noqa: E402
from bot.services import reminders  # noqa: E402
from bot.utils import date_disp  # noqa: E402

FAIL = 0


def ok(name, cond, extra=""):
    global FAIL
    print(("PASS " if cond else "FAIL ") + name + (f"  — {extra!r}" if extra and not cond else ""))
    if not cond:
        FAIL += 1


def iso(days: int) -> str:
    return (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")


db.init_db()
db.upsert_user(111, "Ali Designer", "ali_art")
ali_id = db.get_user(111)["id"]
db.upsert_user(222, "Reza Mix", None)  # no username → tg:// link fallback
reza_id = db.get_user(222)["id"]

PID = db.create_project("Alpha", "demo", "single", iso(2), None, None)
T_TOMORROW = db.create_task(PID, "cover-art", ali_id, "", "high", iso(1))
T_TODAY = db.create_task(PID, "mix-master", reza_id, "", "urgent", iso(0))
T_LATE = db.create_task(PID, "captions", ali_id, "", "normal", iso(-3))
T_ORPHAN = db.create_task(PID, "no-owner", None, "", "normal", iso(0))
T_FAR = db.create_task(PID, "not-due", ali_id, "", "low", iso(9))
T_DONE = db.create_task(PID, "finished", ali_id, "", "low", iso(0))
with db.get_db() as conn:
    conn.execute("UPDATE tasks SET status='done' WHERE id=?", (T_DONE,))

sent: list[tuple[int, str]] = []


class FakeBot:
    async def send_message(self, chat_id, text, **kw):
        sent.append((chat_id, text))
        return SimpleNamespace(message_id=len(sent))


ctx = SimpleNamespace(bot=FakeBot(), bot_data={"group_chat_id": -100})
asyncio.run(reminders.check_deadlines(ctx))

ali_msgs = [t for _, t in sent if "@ali_art" in t]
reza_msgs = [t for _, t in sent if "tg://user?id=222" in t]
orphan_msgs = [t for _, t in sent if "no-owner" in t]

ok("all messages go to the group chat", all(c == -100 for c, _ in sent), sent[:2])
ok("ali tagged once with both at-risk tasks", len(ali_msgs) == 1 and
   "cover-art" in ali_msgs[0] and "captions" in ali_msgs[0], ali_msgs)
ok("count uses Persian digits", jdate.fa_num(2) in ali_msgs[0], ali_msgs[0][:60])
ok("jalali dates in nag", date_disp(iso(1)) in ali_msgs[0], ali_msgs[0])
ok("tomorrow stage bullet ⏳", any("⏳ cover-art" in m for m in ali_msgs))
ok("overdue stage bullet ⛔", any("⛔ captions" in m for m in ali_msgs))
ok("reza falls back to tg:// mention", len(reza_msgs) == 1 and "mix-master" in reza_msgs[0], reza_msgs)
ok("today stage bullet ⚡", any("⚡ mix-master" in m for m in reza_msgs))
ok("unassigned tasks posted without mention", len(orphan_msgs) == 1 and "@ali" not in orphan_msgs[0])
ok("far-future task not nagged", all("not-due" not in t for _, t in sent))
ok("done task not nagged", all("finished" not in t for _, t in sent))
ok("project-level stage fires (2 days)", any("Alpha" in t and "⏰" in t for _, t in sent),
   [t for _, t in sent if "Alpha" in t])
ok("project msg shows Jalali not raw ISO",
   all(iso(2) not in t for _, t in sent if "Alpha" in t and "⏰" in t))

n_after_first = len(sent)
asyncio.run(reminders.check_deadlines(ctx))
ok("dedupe: second run sends nothing new", len(sent) == n_after_first, len(sent) - n_after_first)

# tomorrow becomes today? simulate by advancing the dedupe: clear reminders for T_LATE
# to ensure a NEW overdue day key nags again next day
with db.get_db() as conn:
    conn.execute("DELETE FROM reminders WHERE task_id=? AND kind LIKE 'tag:late%'", (T_LATE,))
yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
db.mark_reminded(None, T_LATE, f"tag:late:{yesterday}")  # old day already nagged
sent.clear()
asyncio.run(reminders.check_deadlines(ctx))
late_today = [t for _, t in sent if "captions" in t]
ok("overdue nags again on a new day only", len(late_today) == 1, len(late_today))

print("ALL REMINDER TESTS PASS" if FAIL == 0 else f"{FAIL} FAILURES")
sys.exit(1 if FAIL else 0)
