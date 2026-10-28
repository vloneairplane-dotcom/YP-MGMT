#!/usr/bin/env python3
"""True end-to-end simulation: pushes real telegram.Update objects through
Application.process_update() with a mocked Telegram API, following the exact
user click-path. Reveals handler-gating bugs the unit harness cannot see."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "999:TEST-E2E"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "e2e.db")
os.environ["ADMIN_IDS"] = "999"

from telegram import (CallbackQuery, Chat, Message, Update,  # noqa: E402
                      User as TGUser)

from bot import database as db  # noqa: E402

ADMIN_TG = 999
CHAT_ID = 500


MSG_ENDPOINTS = {"sendMessage", "editMessageText", "editMessageCaption", "sendDocument",
                 "sendPhoto", "copyMessage", "sendMediaGroup"}


def patch_bot(app, calls):
    async def fake(endpoint, *args, **kwargs):
        payload = {"endpoint": endpoint}
        for a in args:
            if isinstance(a, dict):
                payload.update(a)
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        calls.append(payload)
        if endpoint in MSG_ENDPOINTS:
            # Telegram returns the sent Message object
            return {"message_id": 900000 + Ids.n, "date": 1760000000,
                    "chat": CHAT_JSON, "text": payload.get("text")}
        return True

    app.bot._post = fake
    app.bot._get = fake


class Ids:
    n = 1000

    @classmethod
    def next(cls):
        cls.n += 1
        return cls.n


USER_JSON = {"id": ADMIN_TG, "first_name": "Vlone", "is_bot": False, "username": "vlone"}
CHAT_JSON = {"id": CHAT_ID, "type": "private"}


def upd_cb(bot, data: str) -> Update:
    return Update.de_json({
        "update_id": Ids.next(),
        "callback_query": {
            "id": str(Ids.next()), "from": USER_JSON, "chat_instance": "inst", "data": data,
            "message": {"message_id": Ids.next(), "date": 1760000000,
                         "chat": CHAT_JSON, "from": USER_JSON},
        },
    }, bot)


def upd_text(bot, text: str) -> Update:
    msg = {"message_id": Ids.next(), "date": 1760000000,
           "chat": CHAT_JSON, "from": USER_JSON, "text": text}
    if text.startswith("/"):
        msg["entities"] = [{"type": "bot_command", "offset": 0,
                            "length": len(text.split()[0])}]
    return Update.de_json({"update_id": Ids.next(), "message": msg}, bot)


def show_tracebacks(app):
    import traceback

    async def err(update, context):
        exc = getattr(context, "error", None)
        print("!!! handler raised:")
        if exc:
            traceback.print_exception(type(exc), exc, exc.__traceback__)
    app.error_handlers.clear()
    app.add_error_handler(err)


def dump(calls, since, title):
    new = calls[since:]
    print(f"--- {title} → {len(new)} api call(s)")
    for c in new:
        txt = str(c.get("text", ""))[:60].replace("\n", "⏎")
        print(f"    {c['endpoint']:<18} {txt}")
    return len(calls)


async def main():
    db.init_db()
    db.upsert_user(ADMIN_TG, "Vlone", "vlone", is_admin=True)

    from bot.main import build_app
    app = build_app()
    calls: list[dict] = []
    patch_bot(app, calls)  # patch BEFORE any init; we never initialize the bot
    app._initialized = True  # skip full initialize() (would hit network for getMe)
    from telegram import User as TGUser
    app.bot._bot_user = TGUser(999, "YPbot", True, username="yp_mgmt_bot")
    show_tracebacks(app)

    convs = [h for grp in app.handlers.values() for h in grp
             if type(h).__name__ == "ConversationHandler"]
    assert len(convs) == 1, f"expected ONE merged wizard conversation, got {len(convs)}"
    proj_conv = task_conv = convs[0]

    mark = 0
    async def feed(update, title, expect=None):
        nonlocal mark
        await app.process_update(update)
        await asyncio.sleep(0.05)  # let PTB handler tasks (blocking conv) drain
        mark = dump(calls, mark, title)
        if expect:
            last_text = " ".join(str(c.get("text", "")) for c in calls)
            assert expect in last_text, f"EXPECTED {expect!r} not seen after: {title}"

    # 1) /start → main menu (user already has role? no role yet → role keyboard)
    await feed(upd_text(app.bot, "/start"), "/start")
    await feed(upd_cb(app.bot, "role:manager"), "pick role")

    # 2) full project creation via conversation
    await feed(upd_cb(app.bot, "proj:new"), "proj:new (conv entry)")
    await feed(upd_text(app.bot, "دی 18-19"), "title")
    await feed(upd_cb(app.bot, "ptype:single"), "type")
    await feed(upd_text(app.bot, "توضیح تست"), "desc")
    await feed(upd_cb(app.bot, "dl:60"), "deadline → review")
    pid = None
    await feed(upd_cb(app.bot, "proj:confirm"), "confirm → create")
    rows = db.list_projects()
    pid = rows[0]["id"] if rows else None
    print(f"project id={pid}, state after confirm: proj_conv._conversations={dict(proj_conv._conversations)}")

    # 2b) THE REAL FAILURE MODE (reported by user): start task wizard, abandon it
    #     mid-flow (no text typed), then press "task new" again → second press was
    #     silently dropped because ConversationHandler skips entry_points when the
    #     conversation is already tracking this user (no allow_reentry).
    await feed(upd_cb(app.bot, f"task:new:{pid}"), "task:new first press")
    print(f"task conv state after first press: {dict(task_conv._conversations)}")
    await feed(upd_cb(app.bot, f"task:new:{pid}"), "task:new SECOND press (reentry)")
    print(f"task conv state after second press: {dict(task_conv._conversations)}")

    # 3) THE USER'S BROKEN STEP: task new from project detail after abandoning a wizard
    await feed(upd_cb(app.bot, f"task:new:{pid}"), "task:new ✴️")
    # 4) continue task flow
    await feed(upd_text(app.bot, "ضبط وکال"), "task title")
    member = db.list_users()[0]
    await feed(upd_cb(app.bot, f"task:assign:{pid}:{member['id']}"), "assignee")
    await feed(upd_cb(app.bot, f"task:prio:{pid}:high"), "priority")
    await feed(upd_cb(app.bot, "dl:3"), "task deadline → create")
    tks = db.list_tasks(project_id=pid)
    print(f"tasks in project: {len(tks)}")
    print(f"task_conv state left: {dict(task_conv._conversations)}")

    ok_flow = bool(tks)
    # 5) misc regressions in the same pipeline
    await feed(upd_cb(app.bot, f"proj:dl:{pid}"), "edit deadline open")
    await feed(upd_cb(app.bot, f"proj:dlq:{pid}:7"), "edit deadline apply")
    await feed(upd_cb(app.bot, f"proj:view:{pid}"), "open project")
    await feed(upd_cb(app.bot, "menu:tasks"), "status tasks")

    print("\n" + ("🎉 E2E PASS" if ok_flow else "💥 E2E FAIL: task flow did not create a task"))
    return 0 if ok_flow else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
