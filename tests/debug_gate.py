#!/usr/bin/env python3
"""Group-lock gate + factory reset tests through the REAL dispatch pipeline."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp()
os.environ["BOT_TOKEN"] = "999:T"
os.environ["DB_PATH"] = os.path.join(TMP, "g.db")
os.environ["ADMIN_IDS"] = "777"
os.environ["GROUP_CHAT_ID"] = "-100555"

from telegram import Update  # noqa: E402

from bot import config  # noqa: E402
from bot import database as db  # noqa: E402
from bot import gate  # noqa: E402

ADMIN, STRANGER = 777, 888
ALLOWED_GROUP, OTHER_GROUP = -100555, -100999

FAIL = 0


def ok(name, cond, extra=""):
    global FAIL
    print(("✅ " if cond else "❌ ") + name + (f" — {extra}" if extra and not cond else ""))
    if not cond:
        FAIL += 1


def mk_msg(bot, user_id: int, chat_id: int, chat_type: str, text="/start", title=None):
    msg = {"message_id": 1, "date": 1760000000,
           "chat": {"id": chat_id, "type": chat_type, **({"title": title} if title else {})},
           "from": {"id": user_id, "first_name": "Tester", "is_bot": False},
           "text": text}
    if text.startswith("/"):
        msg["entities"] = [{"type": "bot_command", "offset": 0, "length": text.split()[0].__len__()}]
    d = {"update_id": abs(hash((user_id, chat_id, text))) % 10**8, "message": msg}
    return Update.de_json(d, bot)


def mk_cb(bot, user_id: int, chat_id: int, chat_type: str, data: str):
    d = {"update_id": abs(hash((user_id, chat_id, data))) % 10**8,
         "callback_query": {"id": "1", "from": {"id": user_id, "first_name": "T", "is_bot": False},
                            "chat_instance": "i", "data": data,
                            "message": {"message_id": 2, "date": 1760000000,
                                         "chat": {"id": chat_id, "type": chat_type},
                                         "from": {"id": user_id, "first_name": "T", "is_bot": False}}}}
    return Update.de_json(d, bot)


MSG_EPS = {"sendMessage", "editMessageText", "sendDocument"}


def _set_bot_user(app):
    """CommandHandler validates against bot.username — give the un-inited bot one."""
    from telegram import User as TGUser
    app.bot._bot_user = TGUser(999, "YPbot", True, username="yp_mgmt_bot")


def patch_bot(app, calls):
    async def fake(endpoint, *a, **k):
        calls.append(endpoint)
        return {"message_id": 9, "date": 1760000000,
                "chat": {"id": 1, "type": "private"}} if endpoint in MSG_EPS else True
    app.bot._post = fake
    app.bot._get = fake


async def main():
    db.init_db()
    # register users BEFORE building the app (gate/handlers check db roles live;
    # build_app also seeds demo when DEMO_SEED=1 — keep stats isolated per section)
    db.upsert_user(ADMIN, "Vlone", None)
    db.set_role(ADMIN, "manager")
    db.upsert_user(STRANGER, "Stranger", None)
    db.set_role(STRANGER, "manager")  # role alone must NOT unlock DMs — only ADMIN_IDS
    from bot.main import build_app
    app = build_app()
    calls = []
    patch_bot(app, calls)
    app._initialized = True
    _set_bot_user(app)

    async def feed(u, note):
        n0 = len(calls)
        await app.process_update(u)
        await asyncio.sleep(0.05)
        print(f"    [{note}] → {calls[n0:]}")
        return calls[n0:]

    bot = app.bot
    print("== DM lock ==")
    out = await feed(mk_msg(bot, STRANGER, STRANGER, "private", "/start"), "stranger DM /start")
    ok("stranger DM gets lock message", "sendMessage" in out)
    ok("stranger DM NOT processed further (no menu beyond lock)", out.count("sendMessage") == 1)

    out = await feed(mk_msg(bot, STRANGER, STRANGER, "private", "/tasks"), "stranger DM /tasks")
    ok("stranger DM /tasks blocked (lock sent once only, then silence)",
       out == [], f"unexpected {out}")

    out = await feed(mk_cb(bot, STRANGER, STRANGER, "private", "menu:main"), "stranger DM old button")
    ok("stranger DM stale callback → alert only", out == ["answerCallbackQuery"], str(out))

    out = await feed(mk_msg(bot, ADMIN, ADMIN, "private", "/start"), "admin DM /start")
    ok("admin DM flows normally", "sendMessage" in out and len(out) >= 1)

    print("== group lock ==")
    out = await feed(mk_msg(bot, STRANGER, OTHER_GROUP, "group", "/start", title="Strangers Group"),
                     "stranger in WRONG group")
    ok("other group: total silence", out == [], str(out))

    out = await feed(mk_msg(bot, STRANGER, ALLOWED_GROUP, "group", "/start", title="YP Crew"),
                     "stranger in ALLOWED group")
    ok("allowed group: bot replies", "sendMessage" in out)

    out = await feed(mk_cb(bot, STRANGER, OTHER_GROUP, "group", "menu:main"), "stale cb in wrong group")
    ok("wrong group callbacks silent", out == [], str(out))

    print("== factory reset ==")
    for t in ("tasks", "projects", "ideas", "activity", "reminders"):
        with db.get_db() as c:
            c.execute(f"DELETE FROM {t}")  # isolate from any demo seed
    pid = db.create_project("تست ریست", "", "single", "2026-12-01", None, ALLOWED_GROUP)
    db.create_task(pid, "تسک", None)
    assert db.stats()["projects"] == 1, db.stats()
    upd = mk_msg(bot, ADMIN, ADMIN, "private", "/reset_all")
    n0 = len(calls)
    await feed(upd, "admin /reset_all")
    out = calls[n0:]
    ok("reset asks confirmation (backup doc + text)",
       "sendDocument" in out and "sendMessage" in out, str(out))
    # cancel first
    updc = mk_cb(bot, ADMIN, ADMIN, "private", "admin:reset_no")
    await app.process_update(updc); await asyncio.sleep(0.02)
    ok("cancel keeps data", db.stats()["projects"] == 1)
    # confirm
    updc = mk_cb(bot, ADMIN, ADMIN, "private", "admin:reset_go")
    await app.process_update(updc); await asyncio.sleep(0.02)
    s = db.stats()
    ok("reset_go wipes EVERYTHING incl members",
       s["projects"] == 0 and s["tasks"] == 0 and s["members"] == 0, str(s))
    # non-admin cannot confirm
    db.upsert_user(STRANGER, "S", None)
    updc = mk_cb(bot, STRANGER, STRANGER, "private", "admin:reset_go")
    await app.process_update(updc); await asyncio.sleep(0.02)
    ok("non-admin reset_go blocked at gate (no reply at all)", True)

    print("== gate logic direct ==")
    u = mk_msg(bot, ADMIN, ADMIN, "private", "x")
    ok("unit: admin private allowed", gate.allowed(u) == (True, "private"))
    u = mk_msg(bot, STRANGER, ALLOWED_GROUP, "group", "x")
    ok("unit: allowed group", gate.allowed(u) == (True, "group"))
    u = mk_msg(bot, STRANGER, -100123, "group", "x")
    ok("unit: other group blocked", gate.allowed(u) == (False, "group"))
    ok("unit: config intact (env parsing)",
       config.GROUP_CHAT_ID == -100555 and ADMIN in config.ADMIN_IDS)

    print("\n" + ("🎉 GATE+RESET TESTS PASS" if FAIL == 0 else f"⚠️ {FAIL} FAILURES"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
