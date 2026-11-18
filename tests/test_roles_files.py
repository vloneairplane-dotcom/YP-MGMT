#!/usr/bin/env python3
"""Role privilege boundary + per-project file vault, driven with fake updates.

Runs with or without python-telegram-bot installed (tests/_stubs.py fills the gaps).
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ["BOT_TOKEN"] = "999:T"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["ADMIN_IDS"] = "777"
os.environ["GROUP_CHAT_ID"] = "-100555"
os.environ["VAULT_CHAT_ID"] = "-100999"

import _stubs  # noqa: E402

_stubs.install()

from bot import config  # noqa: E402
from bot import database as db  # noqa: E402
from bot import keyboards as kb  # noqa: E402
from bot import texts  # noqa: E402
from bot.handlers import admin, files, roles, tasks  # noqa: E402
from bot.utils import is_manager, user_of  # noqa: E402

FAIL = 0
GROUP = -100555


def ok(name, cond, extra=""):
    global FAIL
    print(("PASS " if cond else "FAIL ") + name + (f"  — {extra!r}" if extra and not cond else ""))
    if not cond:
        FAIL += 1


# ------------------------------------------------------------------ fakes
class FakeBot:
    def __init__(self):
        self.sent, self.copied, self.edited = [], [], []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append(("message", chat_id, text, kw))

    async def send_chat_action(self, *a, **kw):
        pass

    async def copy_message(self, chat_id, from_chat_id, message_id, **kw):
        self.copied.append((chat_id, from_chat_id, message_id))
        return NS(message_id=5000 + len(self.copied))

    async def edit_message_text(self, text, **kw):
        self.edited.append(text)

    def __getattr__(self, name):
        if name.startswith("send_"):
            async def _send(**kw):
                self.sent.append((name, kw.get("chat_id"), kw, None))
            return _send
        raise AttributeError(name)


class FakeQuery:
    def __init__(self, data, chat_id=GROUP):
        self.data = data
        self.answers, self.edits, self.markup_edits, self.deleted = [], [], [], False
        q = self

        async def _delete():
            q.deleted = True

        self.message = NS(chat=NS(id=chat_id), chat_id=chat_id, message_id=42,
                          message_thread_id=None, is_topic_message=False, delete=_delete)

    async def answer(self, text=None, show_alert=False, **_):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, text, reply_markup=None, **_):
        self.edits.append((text, reply_markup))

    async def edit_message_reply_markup(self, reply_markup=None, **_):
        self.markup_edits.append(reply_markup)


def person(tg_id, name):
    return NS(id=tg_id, full_name=name, username=name.lower())


def ctx(bot=None):
    return NS(bot=bot or FakeBot(), user_data={}, bot_data={})


def cb(user, data, chat_id=GROUP):
    q = FakeQuery(data, chat_id)
    upd = NS(callback_query=q, effective_user=user, effective_message=q.message,
             effective_chat=NS(id=chat_id, type="supergroup"))
    return upd, q


def file_msg(kind, uid, chat_id=GROUP, caption=None, name="x.wav", msg_id=10, reply_to=None):
    reactions, replies = [], []

    async def set_reaction(r):
        reactions.append(r)

    async def reply_text(t, **kw):
        replies.append(t)

    base = dict(chat_id=chat_id, message_id=msg_id, caption=caption, audio=None, voice=None,
                video=None, video_note=None, photo=None, document=None,
                set_reaction=set_reaction, reply_text=reply_text, reply_to_message=reply_to,
                reactions=reactions, replies=replies, message_thread_id=None, is_topic_message=False)
    if kind == "audio":
        base["audio"] = NS(file_id=f"F-{uid}", file_unique_id=uid, file_name=name,
                           mime_type="audio/wav", file_size=1000, duration=30, title="", performer="")
    elif kind == "photo":
        base["photo"] = [NS(file_id="small", file_unique_id="s", file_size=1),
                         NS(file_id=f"F-{uid}", file_unique_id=uid, file_size=999)]
    return NS(**base)


def run(coro):
    return asyncio.run(coro)


async def main():
    # ---- people: 777 = owner (ADMIN_IDS), 1 = member, 2 = member, 3 = future manager
    owner, alice, bob, carol = (person(777, "Owner"), person(1, "Alice"),
                                person(2, "Bob"), person(3, "Carol"))

    # ================================================================ ROLES
    c = ctx()
    u_alice = user_of(NS(effective_user=alice), c)
    u_owner = user_of(NS(effective_user=owner), c)
    ok("owner in ADMIN_IDS starts as admin with no picker", u_owner["role"] == "admin" and is_manager(u_owner))
    ok("fresh member has no powers", u_alice["role"] is None and not is_manager(u_alice))

    # picker no longer offers manager/admin as plain buttons
    flat = [b.callback_data for row in kb.role_pick().inline_keyboard for b in row]
    ok("role picker: only working roles + request", set(flat) == {
        "role:artist", "role:producer", "role:designer", "role:req"}, flat)
    ok("owner picker also offers admin",
       "role:admin" in [b.callback_data for r in kb.role_pick(owner=True).inline_keyboard for b in r])

    # THE BUG: self-assigning admin / manager
    for data in ("role:admin", "role:manager"):
        upd, q = cb(alice, data)
        await roles.role_router(upd, ctx())
        now = db.get_user(1)
        ok(f"self-assign via {data} is refused/queued", now["role"] is None and not is_manager(dict(now)), now["role"])

    upd, q = cb(alice, "role:producer")
    await roles.role_router(upd, ctx())
    ok("working role can be chosen freely", db.get_user(1)["role"] == "producer")

    # manager request → owner gets approve/deny buttons
    bot = FakeBot()
    c2 = ctx(bot)
    upd, q = cb(alice, "role:req")
    await roles.role_router(upd, c2)
    dm = [s for s in bot.sent if s[0] == "message" and s[1] == 777]
    ok("request notifies the owner", len(dm) == 1)
    markup = dm[0][3]["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    alice_db_id = db.get_user(1)["id"]
    ok("request has approve/deny buttons", datas == [f"role:ok:{alice_db_id}", f"role:no:{alice_db_id}"], datas)
    ok("role unchanged until approved", db.get_user(1)["role"] == "producer")

    upd, q = cb(alice, "role:req")
    await roles.role_router(upd, c2)
    ok("request spam is rate-limited", len([s for s in bot.sent if s[1] == 777]) == 1 and q.answers[-1][1])

    # a plain member cannot approve (even their own request)
    upd, q = cb(alice, f"role:ok:{alice_db_id}")
    await roles.role_router(upd, c2)
    ok("member cannot approve own request", db.get_user(1)["role"] == "producer")

    upd, q = cb(owner, f"role:ok:{alice_db_id}")
    await roles.role_router(upd, c2)
    ok("owner approval grants manager", db.get_user(1)["role"] == "manager")
    ok("approved member is now a manager", is_manager(dict(db.get_user(1))))

    # deny path
    user_of(NS(effective_user=bob), c)
    bob_id = db.get_user(2)["id"]
    upd, q = cb(owner, f"role:no:{bob_id}")
    await roles.role_router(upd, c2)
    ok("denied request leaves role alone", db.get_user(2)["role"] is None)

    # manager (non-owner) cannot mint admins or edit owners from the admin panel
    user_of(NS(effective_user=carol), c)
    carol_id = db.get_user(3)["id"]
    upd, q = cb(alice, f"admin:setrole:{carol_id}:admin")
    await admin.admin_router(upd, ctx())
    ok("manager cannot grant admin", db.get_user(3)["role"] is None)
    owner_id = db.get_user(777)["id"]
    upd, q = cb(alice, f"admin:setrole:{owner_id}:artist")
    await admin.admin_router(upd, ctx())
    ok("manager cannot demote an owner", db.get_user(777)["role"] == "admin")
    upd, q = cb(alice, f"admin:setrole:{carol_id}:designer")
    await admin.admin_router(upd, ctx())
    ok("manager can still set working roles", db.get_user(3)["role"] == "designer")
    upd, q = cb(owner, f"admin:setrole:{carol_id}:admin")
    await admin.admin_router(upd, ctx())
    ok("owner can grant admin", db.get_user(3)["role"] == "admin")
    db.set_role(3, "designer")

    # non-managers are locked out of the admin router entirely
    upd, q = cb(bob, f"admin:setrole:{bob_id}:admin")
    await admin.admin_router(upd, ctx())
    ok("plain member cannot use admin router", db.get_user(2)["role"] is None)

    # task status: assignee or manager only
    pid = db.create_project("پروژه تست", "d", "single", None, None, None)
    bob_db = db.get_user(2)["id"]
    tid = db.create_task(pid, "mix", bob_db)
    upd, q = cb(carol, f"task:st:{tid}:done")
    await tasks.task_set_status(upd, ctx())
    ok("non-assignee cannot change task status", db.get_task(tid)["status"] == "pending")
    upd, q = cb(bob, f"task:st:{tid}:doing")
    await tasks.task_set_status(upd, ctx())
    ok("assignee can change task status", db.get_task(tid)["status"] == "doing")

    # ================================================================ FILES (db)
    f1 = db.add_file(pid, "beat", "audio", "FID1", "U1", title="beat v1", uploaded_by=bob_db)
    ok("add_file returns id", isinstance(f1, int))
    ok("same file twice is rejected", db.add_file(pid, "beat", "audio", "FID1b", "U1") is None)
    db.add_file(pid, "cover", "photo", "FID2", "U2", uploaded_by=bob_db)
    ok("counts + summary", db.count_files(pid) == 2 and db.files_summary(pid) == {"beat": 1, "cover": 1})
    ok("list by category", [r["file_id"] for r in db.list_files(pid, "beat")] == ["FID1"])
    ok("stats exposes files", db.stats()["files"] == 2)

    # ================================================================ FILES (flow)
    # arm upload as Bob (producer → ⭐ beat)
    db.set_role(2, "producer")
    c3 = ctx()
    upd, q = cb(bob, f"pf:u:{pid}")
    await files.files_router(upd, c3)
    picker = [b for row in q.edits[-1][1].inline_keyboard for b in row]
    ok("category picker stars the role's category first", picker[0].text.startswith("⭐") and "beat" in picker[0].callback_data, picker[0].text)

    upd, q = cb(bob, f"pf:ua:{pid}:vocal")
    await files.files_router(upd, c3)
    ok("upload mode armed", c3.user_data["upload"]["cat"] == "vocal")

    m = file_msg("audio", "U10", name="verse.wav")
    await files.receive_file(NS(effective_message=m, effective_user=bob), c3)
    ok("file stored in chosen category", db.count_files(pid, "vocal") == 1)
    ok("quiet 👍 reaction instead of a reply", m.reactions == ["👍"] and not m.replies)
    ok("counter incremented", c3.user_data["upload"]["count"] == 1)
    ok("vault channel got a backup copy", len(c3.bot.copied) == 1 and c3.bot.copied[0][0] == -100999)
    ok("vault message id remembered", db.get_file(db.list_files(pid, "vocal")[0]["id"])["vault_msg_id"] == 5001)

    m2 = file_msg("audio", "U10", name="verse.wav", msg_id=11)
    await files.receive_file(NS(effective_message=m2, effective_user=bob), c3)
    ok("duplicate is not stored twice", db.count_files(pid, "vocal") == 1 and m2.reactions == ["🤝"])

    m3 = file_msg("audio", "U11", chat_id=-100123)
    await files.receive_file(NS(effective_message=m3, effective_user=bob), c3)
    ok("files from another chat are ignored", db.count_files(pid, "vocal") == 1)

    c_idle = ctx()
    await files.receive_file(NS(effective_message=file_msg("audio", "U12"), effective_user=bob), c_idle)
    ok("no upload mode → file ignored", db.count_files(pid, "vocal") == 1)

    c3.user_data["upload"]["ts"] = time.time() - files.UPLOAD_TTL - 5
    await files.receive_file(NS(effective_message=file_msg("audio", "U13"), effective_user=bob), c3)
    ok("expired upload mode stops accepting", db.count_files(pid, "vocal") == 1 and "upload" not in c3.user_data)

    # finish
    c3.user_data["upload"] = {"pid": pid, "cat": "vocal", "chat_id": GROUP, "panel_id": 1, "count": 3, "ts": time.time()}
    upd, q = cb(bob, "pf:ue")
    await files.files_router(upd, c3)
    ok("finish closes upload mode and reports count", "upload" not in c3.user_data and "۳" in q.edits[-1][0])

    # browse + send
    upd, q = cb(alice, f"pf:c:{pid}:beat:0")
    await files.files_router(upd, ctx())
    btns = [b.callback_data for row in q.edits[-1][1].inline_keyboard for b in row]
    ok("category list shows file buttons", f"pf:v:{f1}" in btns, btns)

    c4 = ctx()
    upd, q = cb(alice, f"pf:v:{f1}")
    await files.files_router(upd, c4)
    sent = [s for s in c4.bot.sent if s[0] == "send_audio"]
    ok("stored file is re-sent by file_id with caption", sent and sent[0][2]["audio"] == "FID1" and "beat v1" in sent[0][2]["caption"], c4.bot.sent)

    # delete permissions: other plain member cannot, uploader can, manager can
    plain = person(9, "Dave")
    user_of(NS(effective_user=plain), ctx())
    upd, q = cb(plain, f"pf:dy:{f1}")
    await files.files_router(upd, ctx())
    ok("random member cannot delete", db.get_file(f1) is not None and q.answers[-1][1])
    upd, q = cb(bob, f"pf:d:{f1}")
    await files.files_router(upd, ctx())
    ok("uploader is asked to confirm", q.markup_edits and db.get_file(f1) is not None)
    upd, q = cb(bob, f"pf:dy:{f1}")
    await files.files_router(upd, ctx())
    ok("uploader can delete their file", db.get_file(f1) is None and q.deleted)

    f3 = db.add_file(pid, "mix", "audio", "FID3", "U3", uploaded_by=bob_db)
    upd, q = cb(alice, f"pf:dy:{f3}")          # alice is a manager now
    await files.files_router(upd, ctx())
    ok("manager can delete anyone's file", db.get_file(f3) is None)

    # /save: reply to a photo
    photo = file_msg("photo", "UP1", msg_id=77)
    c5 = ctx()
    cmd = NS(effective_message=NS(reply_to_message=photo, reply_text=photo.reply_text, chat_id=GROUP),
             effective_user=bob)
    await files.cmd_save(cmd, c5)
    ok("/save remembers the replied file", c5.user_data["pending_save"]["msg"] is photo)
    upd, q = cb(bob, f"pf:sv:{pid}")
    await files.files_router(upd, c5)
    stars = [b for row in q.edits[-1][1].inline_keyboard for b in row if b.text.startswith("⭐")]
    ok("/save suggests 'cover' for a photo", stars and stars[0].callback_data == f"pf:sc:{pid}:cover", [b.text for b in stars])
    upd, q = cb(bob, f"pf:sc:{pid}:cover")
    await files.files_router(upd, c5)
    ok("/save stores the photo", db.count_files(pid, "cover") == 2 and "pending_save" not in c5.user_data)

    c6 = ctx()
    await files.cmd_save(NS(effective_message=NS(reply_to_message=None, reply_text=photo.reply_text), effective_user=bob), c6)
    ok("/save without a file explains itself", photo.replies and "ریپلای" in photo.replies[-1])

    # ================================================================ UI contract
    p = db.get_project(pid)
    text = texts.project_detail(p, db.list_tasks(project_id=pid), db.files_summary(pid))
    ok("project card shows file counts", "🗂 فایل‌ها" in text and "🎨" in text)
    ok("project card uses expandable blockquote", "<blockquote expandable>" in text)

    def all_callbacks(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]

    boards = [
        kb.main_menu(True, True, "https://x.y", False, 3), kb.role_pick(True),
        kb.projects_list(db.list_projects(), 0, True), kb.project_detail(pid, True, 5),
        kb.vault_home(pid, {"beat": 2}), kb.category_pick("pf:ua", pid, "producer"),
        kb.vault_list(pid, "beat", db.list_files(pid, "beat"), 0, 1),
        kb.file_actions(1, pid, "beat", True), kb.file_delete_confirm(1), kb.upload_active(pid),
        kb.project_picker(db.list_projects(), "h", {pid: 2}),
    ]
    too_long = [d for m_ in boards for d in all_callbacks(m_) if len(d.encode()) > 64]
    ok("every callback_data fits Telegram's 64 bytes", not too_long, too_long)

    member_menu = kb.main_menu(True, False, None, False, 0)
    mgr_menu = kb.main_menu(True, True, None, False, 0)
    ok("members don't see manager buttons", "menu:admin" not in all_callbacks(member_menu) and "proj:new" not in all_callbacks(member_menu))
    ok("managers do", "menu:admin" in all_callbacks(mgr_menu) and "proj:new" in all_callbacks(mgr_menu))
    web_priv = [b for r in kb.main_menu(True, False, "https://x.y", True, 0).inline_keyboard for b in r if b.text.startswith("🌐")]
    web_grp = [b for r in kb.main_menu(True, False, "https://x.y", False, 0).inline_keyboard for b in r if b.text.startswith("🌐")]
    ok("Mini App button only in private chats (groups get a link)", web_priv[0].web_app and web_grp[0].url == "https://x.y" and not web_grp[0].web_app)

    many = [{"id": i, "ptype": "beat", "status": "idea", "title": f"p{i}"} for i in range(1, 21)]
    nav = [b.callback_data for r in kb.projects_list(many, 1, False).inline_keyboard for b in r if "proj:pg" in (b.callback_data or "")]
    ok("project list paginates", nav == ["proj:pg:0", "proj:pg:2"], nav)

    db.wipe_data()
    ok("wipe clears files too", db.count_files(pid) == 0 and db.stats()["files"] == 0)


db.init_db()
run(main())
print("ALL ROLE/FILE TESTS PASS" if FAIL == 0 else f"{FAIL} FAILURES")
sys.exit(1 if FAIL else 0)
