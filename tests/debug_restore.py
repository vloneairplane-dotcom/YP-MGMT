#!/usr/bin/env python3
"""Round-trip test for /backup + /restore: wipe the board, then feed the bot a
backup document and prove everything comes back — plus bad-file rejection."""
from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp()
os.environ["BOT_TOKEN"] = "999:T"
os.environ["DB_PATH"] = os.path.join(TMP, "data", "yp_mgmt.db")
os.environ["DEMO_SEED"] = "1"  # fill demo data to have something to lose

from bot import database as db  # noqa: E402
from bot.handlers import admin  # noqa: E402

FAIL = 0


def ok(name, cond):
    global FAIL
    print(("✅ " if cond else "❌ ") + name)
    if not cond:
        FAIL += 1


class FakeFile:
    def __init__(self, src: str):
        self.src = src

    async def download_to_drive(self, custom_path=None, **kw):
        shutil.copy(self.src, custom_path)
        return Path(custom_path)


def mk_ctx(user_id: int):
    cx = MagicMock()
    cx.user_data = {}
    cx.chat_data = {}
    cx.bot_data = {"admin_ids": {user_id}}
    cx.bot = MagicMock()
    cx.bot.get_file = AsyncMock()
    return cx


def fake_tg_user(from_id: int) -> MagicMock:
    tu = MagicMock()
    tu.id = from_id
    tu.full_name = "Vlone"
    tu.username = None
    return tu


def mk_msg_doc(from_id: int, document):
    m = MagicMock()
    m.document = document
    m.text = None
    m.from_user = fake_tg_user(from_id)
    m.reply_text = AsyncMock()
    upd = MagicMock()
    upd.effective_user = m.from_user
    upd.effective_message = m
    upd.effective_chat = MagicMock()
    upd.effective_chat.id = 500
    upd.callback_query = None
    return upd, m


async def main():
    db.init_db()
    db.seed_demo()
    admin_tg = 4242
    db.upsert_user(admin_tg, "Vlone", "vlone", is_admin=True)
    db.set_role(admin_tg, "manager")
    before = db.stats()
    ok(f"demo data present ({before['projects']} projects)", before["projects"] == 7)

    # --- simulate /backup: copy the file like cmd_backup does
    backup_path = Path(TMP) / "backup.db"
    shutil.copy2(os.environ["DB_PATH"], backup_path)

    # --- wipe
    removed = db.wipe_data()
    ok("wiped", removed == 7 and db.stats()["projects"] == 0)

    # --- /restore flow through the REAL handler
    cx = mk_ctx(admin_tg)
    upd_cmd = MagicMock()
    upd_cmd.effective_user = fake_tg_user(admin_tg)
    upd_cmd.effective_message = MagicMock()
    upd_cmd.effective_message.reply_text = AsyncMock()
    upd_cmd.callback_query = None
    await admin.cmd_restore(upd_cmd, cx)
    ok("cmd_restore arms pending state", cx.user_data.get("restore_pending") is True)

    doc = MagicMock()
    doc.file_id = "FILE123"
    doc.file_size = backup_path.stat().st_size
    cx.bot.get_file.return_value = FakeFile(str(backup_path))
    upd_doc, m = mk_msg_doc(admin_tg, doc)
    await admin.restore_doc(upd_doc, cx)

    after = db.stats()
    ok(f"board restored ({after['projects']} projects, {after['tasks']} tasks)",
       after["projects"] == 7 and after["tasks"] == 10)
    ok("pre-restore snapshot kept", Path(str(os.environ['DB_PATH']) + ".pre-restore").exists())
    reply = m.reply_text.call_args
    ok("success message sent", reply and "بازگردانی شد" in reply.args[0])
    ok("pending flag cleared", not cx.user_data.get("restore_pending"))

    # --- random/garbage file must be rejected, live db untouched
    bad = Path(TMP) / "evil.db"
    bad.write_bytes(b"this is not a sqlite database at all " * 10)
    doc2 = MagicMock()
    doc2.file_id = "BAD"
    doc2.file_size = bad.stat().st_size
    cx2 = mk_ctx(admin_tg)
    cx2.bot.get_file.return_value = FakeFile(str(bad))
    cx2.user_data["restore_pending"] = True
    upd2, m2 = mk_msg_doc(admin_tg, doc2)
    await admin.restore_doc(upd2, cx2)
    ok("garbage file rejected", "معتبر نیست" in m2.reply_text.call_args.args[0])
    ok("live db untouched after rejection", db.stats()["projects"] == 7)
    ok("no .incoming leftovers", not Path(str(os.environ["DB_PATH"]) + ".incoming").exists())

    # --- document sent without arming → ignored
    cx3 = mk_ctx(admin_tg)
    cx3.bot.get_file.return_value = FakeFile(str(backup_path))
    upd3, m3 = mk_msg_doc(admin_tg, doc2)
    await admin.restore_doc(upd3, cx3)
    ok("unarmed document ignored", m3.reply_text.call_count == 0 and cx3.bot.get_file.call_count == 0)

    print("\n" + ("🎉 RESTORE TESTS PASS" if FAIL == 0 else f"⚠️ {FAIL} FAILURES"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
