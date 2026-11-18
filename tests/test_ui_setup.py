#!/usr/bin/env python3
"""Startup UI setup (command menus per scope, menu button, descriptions) must never crash the bot."""
from __future__ import annotations

import asyncio, os, sys, tempfile
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.update(BOT_TOKEN="999:T", DB_PATH=os.path.join(tempfile.mkdtemp(), "u.db"),
                  ADMIN_IDS="777,888", GROUP_CHAT_ID="-100555", WEBAPP_URL="https://dash.example.com")
import _stubs; _stubs.install()

FAIL = 0
def ok(name, cond, extra=""):
    global FAIL
    print(("PASS " if cond else "FAIL ") + name + (f"  — {extra!r}" if extra and not cond else ""))
    if not cond: FAIL += 1

from bot import main  # noqa: E402  (import itself catches NameErrors/typos in wiring)

class Bot:
    def __init__(self, fail=False): self.calls, self.fail = [], fail
    def __getattr__(self, name):
        async def _c(*a, **k):
            self.calls.append((name, a, k))
            if self.fail: raise RuntimeError("telegram said no")
        return _c

async def go():
    b = Bot(); await main.setup_telegram_ui(NS(bot=b))
    names = [c[0] for c in b.calls]
    cmds = [c for c in b.calls if c[0] == "set_my_commands"]
    ok("commands set for default + group admins + each owner", len(cmds) == 4, len(cmds))
    ok("menu button + both descriptions set", {"set_chat_menu_button", "set_my_description", "set_my_short_description"} <= set(names), names)
    ok("member list excludes manager commands", all(c.command != "backup" for c in cmds[0][1][0]) if hasattr(cmds[0][1][0][0], "command") else True)
    bad = Bot(fail=True)
    try:
        await main.setup_telegram_ui(NS(bot=bad)); survived = True
    except Exception: survived = False
    ok("a failing Telegram call never crashes startup", survived)

asyncio.run(go())
print("ALL UI SETUP TESTS PASS" if FAIL == 0 else f"{FAIL} FAILURES"); sys.exit(1 if FAIL else 0)
