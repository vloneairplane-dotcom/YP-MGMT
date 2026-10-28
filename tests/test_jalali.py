#!/usr/bin/env python3
"""Jalali calendar layer tests — storage stays ISO Gregorian, humans speak Shamsi."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "999:T"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "j.db")

from bot import jdate  # noqa: E402
from bot.utils import date_disp, parse_deadline  # noqa: E402

FA = jdate.FA_DIGITS
def fa(s: str) -> str:
    return s.translate(FA)

FAIL = 0


def ok(name, cond, extra=""):
    global FAIL
    print(("PASS " if cond else "FAIL ") + name + (f"  — got {extra!r}" if extra and not cond else ""))
    if not cond:
        FAIL += 1


# --- core conversions (fixed pairs)
ok("2026-11-07 to 1405-08-16", jdate.to_jalali("2026-11-07") == "1405/08/16",
   jdate.to_jalali("2026-11-07"))
ok("back-conversion", jdate.from_jalali(1405, 8, 16) == "2026-11-07")
ok("user today 1405-08-07 = 2026-10-29", jdate.from_jalali(1405, 8, 7) == "2026-10-29",
   jdate.from_jalali(1405, 8, 7))
ok("persian digits display", jdate.jalali_disp("2026-11-07") == fa("1405/08/16"),
   jdate.jalali_disp("2026-11-07"))

# --- parse numeric forms (Persian digits input via translate, never hand-typed)
for inp in ("1405/08/16", fa("1405-08-16"), "1405-08-16", "1405.08.16", "1405/8/16"):
    ok(f"parse {inp!r}", parse_deadline(inp) == "2026-11-07", parse_deadline(inp))

# --- month names (upcoming-occurrence rule)
r = parse_deadline(fa("16") + " " + "آبان".replace("آ", "آ"))
exp_this = jdate.from_jalali(1405, 8, 16)
exp_next = jdate.from_jalali(1406, 8, 16)
ok("16 Aban = upcoming", r in {exp_this, exp_next} and (r or "") >= datetime.utcnow().strftime("%Y-%m-%d"),
   r)
ok("2 Aban (passed) -> next year", parse_deadline("2 آبان") == jdate.from_jalali(1406, 8, 2),
   parse_deadline("2 آبان"))
ok("7 Aban 1405 explicit", parse_deadline("7 Aban 1405") == "2026-10-29")
ok("invalid 13/40 rejected", parse_deadline("1405/13/40") is None)

# --- relative
plus7 = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d")
ok("+7", parse_deadline("+7") == plus7, parse_deadline("+7"))
ok("10 روز دیگر (persian digits)",
   parse_deadline(fa("10") + " روز دیگر") == (datetime.utcnow() + timedelta(days=10)).strftime("%Y-%m-%d"))
ok("فردا", parse_deadline("فردا") == (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"))
ok("پس‌فردا", parse_deadline("پس\u200cفردا") == (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d"))

# --- clears / passthrough / junk
ok("clear words", parse_deadline("-") is None and parse_deadline("بدون") is None)
ok("ISO Gregorian passthrough", parse_deadline("2026-12-25") == "2026-12-25")
ok("junk None", parse_deadline("فلان تاریخ") is None)

# --- display helper
ok("date_disp LRM+fa", date_disp("2026-11-07") == "\u200e" + fa("1405/08/16") + "\u200e",
   repr(date_disp("2026-11-07")))
ok("date_disp None", date_disp(None) == "—")

from bot import texts  # noqa: E402
f = texts.fmt_dt("2026-10-28T12:30:00")
ok("fmt_dt jalali", f == fa("1405/08/06") + " — " + fa("12:30"), f)

# --- db round-trip
from bot import database as db  # noqa: E402
db.init_db()
pid = db.create_project("شمسی‌تست", "", "single", parse_deadline(fa("1405/08/16")), None, None)
p = db.get_project(pid)
ok("db stores ISO", p["deadline"] == "2026-11-07", p["deadline"])
card = texts.project_card_short(p)
ok("card shows jalali", fa("1405/08/16") in card, card)

# --- dashboard
from fastapi.testclient import TestClient  # noqa: E402
from dashboard.app import app as dash  # noqa: E402
d = TestClient(dash).get("/api/dashboard").json()
proj = next(x for x in d["projects"] if x["id"] == pid)
ok("dashboard project deadline jalali", proj["deadline"] == fa("1405/08/16"), proj["deadline"])

print(("ALL JALALI TESTS PASS" if FAIL == 0 else f"{FAIL} FAILURES"))
sys.exit(1 if FAIL else 0)
