#!/usr/bin/env python3
"""Full bot-flow debugger: walks conversations through the real state machine,
audits every keyboard button for a matching handler (dead-button detector)."""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "TEST:FAKE-TOKEN"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["ADMIN_IDS"] = "999"

from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler  # noqa: E402

from bot import database as db  # noqa: E402
from bot import keyboards as kb  # noqa: E402
from bot.config import PROJECT_STATUSES, PROJECT_TYPES  # noqa: E402
from bot.handlers import projects, tasks  # noqa: E402

db.init_db()
ADMIN_TG = 999
u = db.upsert_user(ADMIN_TG, "Vlone", "vlone", is_admin=True)
db.set_role(ADMIN_TG, "manager")
USER = dict(db.get_user(ADMIN_TG))
MEMBER_TG = 5550000001  # big tg id on purpose — must not be confused with db row id
mu = db.upsert_user(MEMBER_TG, "Sara", "sara", is_admin=False)
MEMBER = dict(mu)
assert MEMBER["id"] != MEMBER_TG, "test precondition: db id differs from tg id"

FAIL = 0


def ok(name, cond, extra=""):
    global FAIL
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}{(' — ' + extra) if extra and not cond else ''}")
    if not cond:
        FAIL += 1


def mk_ctx():
    cx = MagicMock()
    cx.user_data = {}
    cx.chat_data = {}
    cx.bot_data = {"admin_ids": {ADMIN_TG}, "group_chat_id": None}
    cx.bot = MagicMock()
    cx.bot.send_message = AsyncMock()
    return cx


def tg_user():
    tu = MagicMock()
    tu.id = ADMIN_TG
    tu.full_name = "Vlone 🕊️"
    tu.username = "vlone"
    return tu


def mk_cb(data: str):
    q = MagicMock()
    q.data = data
    q.from_user = tg_user()
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message = MagicMock()
    q.message.chat_id = 500
    q.message.from_user = tg_user()
    q.message.reply_text = AsyncMock()
    upd = MagicMock()
    upd.callback_query = q
    upd.effective_user = q.from_user
    upd.effective_chat = MagicMock()
    upd.effective_chat.id = 500
    upd.effective_message = q.message  # PTB: callback updates have the message too
    return upd, q


def mk_msg(text: str):
    m = MagicMock()
    m.text = text
    m.reply_text = AsyncMock()
    m.chat_id = 500
    m.from_user = tg_user()
    upd = MagicMock()
    upd.callback_query = None
    upd.effective_user = m.from_user
    upd.effective_chat = MagicMock()
    upd.effective_chat.id = 500
    upd.effective_message = m
    return upd, m


def match_conv(conv, state, update):
    """Return (handler, is_fallback) that PTB would pick for this update."""
    def h_match(h):
        pat = getattr(h, "pattern", None)
        if isinstance(h, CallbackQueryHandler):
            data = update.callback_query.data if update.callback_query else None
            return data is not None and (pat is None or re.match(pat, data))
        if isinstance(h, MessageHandler):
            if update.callback_query:
                return False
            t = update.effective_message.text if update.effective_message else None
            return bool(t) and not t.startswith("/") and pat is None
        return False

    if state is None:
        for h in conv.entry_points:
            if h_match(h):
                return h, "entry"
        return None, None
    for h in conv.states.get(state, []):
        if h_match(h):
            return h, "state"
    for h in conv.fallbacks:
        if h_match(h):
            return h, "fallback"
    return None, None


def run(h, update, cx):
    return asyncio.run(h.callback(update, cx))


def walk_create_project(conv):
    cx = mk_ctx()
    state = None
    steps = [
        ("cb", "proj:new", projects.P_TITLE),
        ("text", "تست آهنگ جدید", projects.P_TYPE),
        ("cb", "ptype:single", projects.P_DESC),
        ("text", "تم شب/شهر", projects.P_DL),
        ("cb", "dl:7", projects.P_CONFIRM),   # after fix: review state
    ]
    for kind, payload, expect_state in steps:
        upd = mk_cb(payload)[0] if kind == "cb" else mk_msg(payload)[0]
        h, src = match_conv(conv, state, upd)
        if not h:
            ok(f"walk: {payload!r} handled in state {state}", False, "DEAD INPUT")
            return None
        new_state = run(h, upd, cx)
        state = None if new_state == ConversationHandler.END else new_state
        ok(f"walk: {kind}:{payload!r} → state {expect_state}", state == expect_state,
           f"got {state}")
    # review message keyboard must be fully routable in P_CONFIRM
    last_cb_upd = steps[-1]
    q = mk_cb("x")[1]
    # grab actual markup from the review edit we captured earlier:
    # rerun _confirm to inspect buttons
    upd, m = mk_cb("dl:7")
    before = state
    # state machine already P_CONFIRM; feed a stray text -> should NOT match
    stray_h, _ = match_conv(conv, projects.P_CONFIRM, mk_msg("hallo")[0])
    ok("walk: stray text ignored at review step", stray_h is None)
    # now confirm
    upd = mk_cb("proj:confirm")[0]
    q = upd.callback_query
    h, src = match_conv(conv, state, upd)
    ok("walk: proj:confirm routed (was DEAD before fix)", h is not None and src == "state")
    if h:
        end = run(h, upd, cx)
        state = None if end == ConversationHandler.END else end
        ok("walk: conversation ended after confirm", state is None, f"got {state}")
    rows = db.list_projects()
    created = [p for p in rows if p["title"] == "تست آهنگ جدید"]
    ok("walk: project exists in DB", bool(created))
    if created:
        p = created[0]
        want = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
        ok("walk: deadline = +7d normalized", p["deadline"] == want, f"{p['deadline']} vs {want}")
        btns = [b.callback_data for row in q.edit_message_text.call_args.kwargs.get("reply_markup").inline_keyboard for b in row] if q.edit_message_text.call_args else []
        ok("walk: after create shows project_detail buttons", any(str(x or '').startswith(f"task:new:{p['id']}") for x in btns), str(btns))
        return p
    return None


def walk_tasks_create(conv_p, pid):
    cx = mk_ctx()
    conv = conv_p  # merged wizard conversation from main.wizard_conversation()
    state = None
    db_rows_before = None
    steps = [
        ("cb", f"task:new:{pid}", tasks.T_TITLE),
        ("text", "ضبط وکال", tasks.T_ASSIGN),
    ]
    for kind, payload, expect_state in steps:
        upd = mk_cb(payload)[0] if kind == "cb" else mk_msg(payload)[0]
        h, src = match_conv(conv, state, upd)
        ok(f"task-walk: {payload!r} routed", h is not None)
        if h:
            end = run(h, upd, cx)
            state = None if end == ConversationHandler.END else end
            ok(f"task-walk: state == {expect_state}", state == expect_state, f"got {state}")
    # assignee pick: use real user id
    upd = mk_cb(f"task:assign:{pid}:{USER['id']}")[0]
    h, src = match_conv(conv, state, upd)
    ok("task-walk: assignee button routed", h is not None)
    if h:
        state = run(h, upd, cx)
    upd = mk_cb(f"task:prio:{pid}:high")[0]
    h, _ = match_conv(conv, state, upd)
    ok("task-walk: priority button routed", h is not None)
    if h:
        state = run(h, upd, cx)
    upd = mk_cb("dl:3")[0]
    h, _ = match_conv(conv, state, upd)
    ok("task-walk: deadline button routed", h is not None)
    if h:
        end = run(h, upd, cx)
        ok("task-walk: task flow ends (creates directly)", end == ConversationHandler.END)
    tk = [t for t in db.list_tasks(project_id=pid)]
    ok("task-walk: task created", bool(tk), f"{len(tk)} tasks")
    if tk:
        want = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")
        ok("task-walk: task deadline +3d", tk[0]["deadline"] == want, str(tk[0]))
        ok("task-walk: assignee stored as db id", tk[0]["assignee_id"] == USER["id"], str(tk[0]))
        ok("task-walk: assignee DM notification sent", cx.bot.send_message.await_count == 1,
           str(cx.bot.send_message.await_count))


def test_admin_member_flow():
    from bot.handlers import admin
    # click a member row -> must open role picker with that member's name
    cx = mk_ctx()
    upd, q = mk_cb(f"admin:user:{MEMBER['id']}")
    asyncio.run(admin.admin_router(upd, cx))
    assert_txt = q.edit_message_text.call_args
    ok("admin: member card opens (was silently dead)", assert_txt is not None)
    if assert_txt:
        sent = assert_txt.args[0] if assert_txt.args else assert_txt.kwargs.get("text", "")
        ok("admin: card shows member name", "Sara" in sent, sent[:80])
    # change role via db-id based button, big tg_id — must actually write
    cx = mk_ctx()
    upd, q = mk_cb(f"admin:setrole:{MEMBER['id']}:artist")
    asyncio.run(admin.admin_router(upd, cx))
    ok("admin: setrole persists role by db-id", db.get_user(MEMBER_TG)["role"] == "artist",
       str(dict(db.get_user(MEMBER_TG))))
    msg = q.edit_message_text.call_args.args[0]
    ok("admin: success wording (not fake ok)", "✅" in msg, msg)


def test_deadline_editor(pid):
    # button proj:dl:{pid} -> router match
    from bot.main import build_app
    app = build_app()
    routers = []
    for grp in app.handlers.values():
        for h in grp:
            if isinstance(h, CallbackQueryHandler):
                routers.append(h)
            elif isinstance(h, ConversationHandler):
                routers.extend(list(h.entry_points) + list(h.fallbacks) +
                              [x for lst in h.states.values() for x in lst])

    def any_match(data):
        return any(getattr(h, "pattern", None) and re.match(h.pattern, data) for h in routers)

    ok("router: proj:dl:{pid} matches a handler", any_match(f"proj:dl:{pid}"))
    ok("router: proj:dlq:{pid}:14 matches a handler", any_match(f"proj:dlq:{pid}:14"))
    ok("router: proj:confirm matches conversation state",
       any(isinstance(h, ConversationHandler) and
           any(getattr(x, "pattern", None) and re.match(x.pattern, "proj:confirm")
               for lst in h.states.values() for x in lst)
           for grp in app.handlers.values() for h in grp))

    # exercise standalone editor: preset path
    cx = mk_ctx()
    upd, q = mk_cb(f"proj:dl:{pid}")
    asyncio.run(projects.project_edit_deadline(upd, cx))
    markup = q.edit_message_text.call_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    ok("editor: shows preset buttons", all(d.startswith(f"proj:dlq:{pid}:") for d in datas) and len(datas) == 6)
    ok("editor: pid saved for manual fallback", cx.user_data.get("dl_edit_pid") == pid)

    upd, q = mk_cb(f"proj:dlq:{pid}:14")
    asyncio.run(projects.project_edit_pick(upd, cx))
    p = db.get_project(pid)
    want = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")
    ok("editor: preset 14d applied", p["deadline"] == want, f"{p['deadline']} vs {want}")

    # manual text path
    cx.user_data["dl_edit_pid"] = pid
    upd, m = mk_msg("2027-05-01")
    consumed = asyncio.run(projects.handle_dl_edit_text(upd, cx))
    ok("editor: manual text consumed", consumed)
    p = db.get_project(pid)
    ok("editor: manual date applied", p["deadline"] == "2027-05-01", str(p["deadline"]))

    # manual then remove
    cx.user_data["dl_edit_pid"] = pid
    upd, m = mk_msg("-")
    asyncio.run(projects.handle_dl_edit_text(upd, cx))
    ok("editor: '-' removes deadline", db.get_project(pid)["deadline"] is None)

    # junk input retries (stays pending)
    cx.user_data["dl_edit_pid"] = pid
    upd, m = mk_msg("salam")
    consumed = asyncio.run(projects.handle_dl_edit_text(upd, cx))
    ok("editor: junk keeps flow pending for retry", consumed and cx.user_data.get("dl_edit_pid") == pid)
    cx.user_data.pop("dl_edit_pid", None)
    # not consumed when no pending edit
    upd, m = mk_msg("2027-05-01")
    ok("editor: text without pending edit ignored",
       not asyncio.run(projects.handle_dl_edit_text(upd, cx)))


def audit_keyboards():
    """Every callback_data any keyboard can emit must match some handler."""
    from telegram.ext import ConversationHandler as CH
    from bot.main import build_app
    app = build_app()
    patterns = []
    for grp in app.handlers.values():
        for h in grp:
            if isinstance(h, CallbackQueryHandler) and h.pattern:
                patterns.append(h.pattern)
            elif isinstance(h, MessageHandler):
                pass
            elif isinstance(h, CH):
                for x in list(h.entry_points) + list(h.fallbacks) + [y for lst in h.states.values() for y in lst]:
                    if isinstance(x, CallbackQueryHandler) and x.pattern:
                        patterns.append(x.pattern)
            elif isinstance(h, type(app.handlers[0][0])) and hasattr(h, "commands"):
                pass

    p = {"id": 1, "title": "ت", "ptype": "single", "status": "idea",
         "deadline": "2026-11-01", "description": "x"}
    tk = {"id": 2, "title": "t", "project_title": "p", "assignee_name": "Vlone",
          "status": "pending", "priority": "high", "deadline": "2026-11-02"}
    users = db.list_users()
    kbs = {
        "role_pick": kb.role_pick(),
        "main_menu": kb.main_menu(True),
        "back": kb.back(),
        "projects_list": kb.projects_list([p]),
        "project_detail": kb.project_detail(1, True),
        "project_status_pick": kb.project_status_pick(1),
        "project_type_pick": kb.project_type_pick(),
        "deadline_pick": kb.deadline_pick(),
        "deadline_edit": kb.deadline_pick(prefix="proj:dlq", pid=1),
        "tasks_list": kb.tasks_list([tk]),
        "task_detail": kb.task_detail(2, 1, True),
        "task_assignee_pick": kb.task_assignee_pick(users, 1),
        "task_priority_pick": kb.task_priority_pick(1),
        "ideas_menu": kb.ideas_menu(),
        "idea_again": kb.idea_again("music"),
        "idea_full_again": kb.idea_full_again(),
        "admin_menu": kb.admin_menu(),
        "wipe_confirm": kb.wipe_confirm(),
        "members_manage": kb.members_manage(users),
        "member_role_pick": kb.member_role_pick(1),
        "confirm_new_project": kb.confirm_new_project(),
    }
    dead = []
    for name, markup in kbs.items():
        for row in markup.inline_keyboard:
            for b in row:
                d = b.callback_data
                if d and not any(re.match(pat, d) for pat in patterns):
                    dead.append(f"{name}: {d!r}")
    ok(f"audit: all keyboard buttons routable ({sum(len(r) for m in kbs.values() for r in m.inline_keyboard)} buttons)",
       not dead, "DEAD→ " + ", ".join(dead))


def main():
    print("== conversation walk: create project ==")
    from bot.main import wizard_conversation
    conv = wizard_conversation()
    ok("wiring: P_CONFIRM state registered", projects.P_CONFIRM in conv.states)
    ok("wiring: merged conv also carries task states", tasks.T_TITLE in conv.states and getattr(conv, "allow_reentry", False))
    pid = None
    cx = mk_ctx()
    p = walk_create_project(conv)
    pid = p["id"] if p else None
    print("== conversation walk: create task ==")
    if pid:
        walk_tasks_create(conv, pid)
    print("== standalone deadline editor ==")
    if pid:
        test_deadline_editor(pid)
    print("== admin member management flow ==")
    test_admin_member_flow()
    print("== global dead-button audit ==")
    audit_keyboards()
    print("== display polish ==")
    from bot.utils import date_disp
    s = date_disp("2027-01-08")
    ok("bidi: LRM wraps dates (RTL won't flip them)", s.startswith("\u200e") and s.endswith("\u200e"))
    import bot.texts as texts
    card = texts.project_card_short({"id": 1, "title": "x", "ptype": "single",
                                     "status": "idea", "deadline": "2027-01-08"})
    import bot.utils as _u
    ok("bidi: project card uses wrapped Jalali date",
       _u.date_disp("2027-01-08") in card, repr(card)[:140])
    print("\n" + ("🎉 ALL FLOW CHECKS PASS" if FAIL == 0 else f"⚠️ {FAIL} FAILURES"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
