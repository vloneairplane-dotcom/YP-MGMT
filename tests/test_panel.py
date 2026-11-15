#!/usr/bin/env python3
"""Panel rebuild contract: API fields, DOM ids, static assets, empty-state payload."""
from __future__ import annotations
import os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "999:T"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "p.db")

FAIL = 0
def ok(name, cond, extra=""):
    global FAIL
    print(("PASS " if cond else "FAIL ") + name + (f"  — {extra!r}" if extra and not cond else ""))
    if not cond: FAIL += 1

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from bot import database as db
db.init_db()
db.upsert_user(111, "Ali", "ali_art")
uid = db.get_user(111)["id"]
from datetime import datetime, timedelta
def iso(d): return (datetime.utcnow() + timedelta(days=d)).strftime("%Y-%m-%d")
pid = db.create_project("پنل", "تست", "single", iso(1), None, None)
db.create_task(pid, "t-late", uid, "", "urgent", iso(-2))
db.create_task(pid, "t-soon", None, "", "high", iso(0))
db.log_activity(uid, "project_new", "x") if hasattr(db, "log_activity") else None

from fastapi.testclient import TestClient
from dashboard.app import app
cl = TestClient(app)

r = cl.get("/")
ok("GET / serves glass html", r.status_code == 200 and "dir=\"rtl\"" in r.text and "aurora" in r.text, r.status_code)
ok("css + js assets served",
   cl.get("/static/css/style.css").status_code == 200 and cl.get("/static/js/app.js").status_code == 200)
ok("health + HEAD /", cl.get("/api/health").json()["status"] == "ok" and cl.head("/").status_code == 200)

d = cl.get("/api/dashboard").json()
p0 = d["projects"][0]
ok("project risk counts", {"open_tasks", "due_soon", "overdue"} <= p0.keys() and
   p0["overdue"] >= 0, p0)
t_late = next(t for t in d["tasks"] if t["title"] == "t-late")
ok("task jalali + status keys", "deadline_disp" in t_late and t_late["status_key"] and t_late["priority_key"] == "urgent", t_late)
ok("task deadline_disp is jalali", "/" in t_late["deadline_disp"] and "-" not in t_late["deadline_disp"][:5], t_late["deadline_disp"])
m0 = d["team"][0]
ok("team avatar/admin fields", m0["avatar"] and isinstance(m0["is_admin"], bool), m0)
ok("stats extended", {"overdue", "due_soon"} <= d["stats"].keys(), d["stats"])
ok("updated_at_disp jalali stamp", "/" in d["updated_at_disp"], d["updated_at_disp"])
ok("next_deadline present", d["next_deadline"] and d["next_deadline"]["deadline_meta"]["days"] == 1, d["next_deadline"])

# JS↔HTML id contract
js = open(os.path.join(ROOT, "dashboard/static/js/app.js"), encoding="utf-8").read()
html = r.text
ids_used = set(re.findall(r'\$\("([\w]+)"\)', js)) | set(re.findall(r'getElementById\("([\w]+)"\)', js))
ids_have = set(re.findall(r'id="([\w]+)"', html))
missing = ids_used - ids_have
ok("all JS ids exist in html", not missing, missing)
for cls in (".projects-grid .project-card", ".chips .chip", ".task-item", ".team-item", ".idea-item", ".activity-item", ".net-err", ".empty", ".avatar"):
    sel = cls.split()[-1]
    ok(f"css styles {sel}", sel.lstrip(".") in open(os.path.join(ROOT, "dashboard/static/css/style.css"), encoding="utf-8").read())
ok("css has glass + blur tokens", "backdrop-filter" in open(os.path.join(ROOT, "dashboard/static/css/style.css"), encoding="utf-8").read())
ok("html uses rtl + vazirmatn", "Vazirmatn" in html)

# filter chip statuses map to CSS pill classes s-*
css = open(os.path.join(ROOT, "dashboard/static/css/style.css"), encoding="utf-8").read()
from bot.config import PROJECT_STATUSES
ok("status pill css for every project status", all(f".s-{k}" in css for k in PROJECT_STATUSES), list(PROJECT_STATUSES))

print("ALL PANEL TESTS PASS" if FAIL == 0 else f"{FAIL} FAILURES")
sys.exit(1 if FAIL else 0)
