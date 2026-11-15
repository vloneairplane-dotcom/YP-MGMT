"""Glass-panel web dashboard — FastAPI app over the same SQLite database."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from bot import database as db
from bot import jdate
from bot.config import (IDEA_CATEGORIES, PROJECT_STATUSES, PROJECT_TYPES, ROLES,
                        TASK_PRIORITIES, TASK_STATUSES)
from bot.utils import days_left

BASE = Path(__file__).resolve().parent

app = FastAPI(title="Ye Pesare · Glass Panel", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


def _fmt_at(ts: str | None) -> str:
    """Stored UTC ISO → '۱۴۰/۰۸/۱۶ — ۱۲:۳۰' Persian stamp."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts)[:19])
    except ValueError:
        return jdate.fa_num(str(ts)[:16].replace("T", " "))
    jal = jdate.to_jalali(dt.date().isoformat())
    return f"{jdate.fa_num(jal)} — {jdate.fa_num(f'{dt:%H:%M}')}" if jal else jdate.fa_num(str(ts))


def _deadline_meta(iso: str | None) -> dict:
    d = days_left(iso)
    if d is None:
        return {"days": None, "label": "بدون ددلاین", "tone": "muted"}
    if d < 0:
        return {"days": d, "label": jdate.fa_num(f"{abs(d)} روز گذشته"), "tone": "danger"}
    if d == 0:
        return {"days": 0, "label": "امروز!", "tone": "danger"}
    if d <= 2:
        return {"days": d, "label": jdate.fa_num(f"{d} روز مونده"), "tone": "warn"}
    if d <= 7:
        return {"days": d, "label": jdate.fa_num(f"{d} روز مونده"), "tone": "info"}
    return {"days": d, "label": jdate.fa_num(f"{d} روز مونده"), "tone": "muted"}


@app.get("/api/dashboard")
def api_dashboard() -> dict:
    projects = []
    for p in db.list_projects():
        tasks = db.list_tasks(project_id=p["id"])
        done = sum(1 for t in tasks if t["status"] == "done")
        open_tks = [t for t in tasks if t["status"] != "done"]
        due_soon = sum(1 for t in open_tks
                       if (dl := days_left(t["deadline"])) is not None and dl <= 0)
        late = sum(1 for t in open_tks
                   if (dl := days_left(t["deadline"])) is not None and dl < 0)
        projects.append({
            "id": p["id"],
            "title": p["title"],
            "description": p["description"],
            "type": PROJECT_TYPES.get(p["ptype"], {"label": "?", "emoji": "📦"}),
            "status": PROJECT_STATUSES.get(p["status"], {"label": "?", "emoji": "❓"}),
            "status_key": p["status"],
            "deadline": jdate.jalali_disp(p["deadline"]) or "—",
            "deadline_meta": _deadline_meta(p["deadline"]),
            "tasks_total": len(tasks),
            "tasks_done": done,
            "progress": round(100 * done / len(tasks)) if tasks else 0,
            "open_tasks": len(open_tks),
            "due_soon": due_soon,
            "overdue": late,
        })

    team = []
    for u in db.list_users():
        role = ROLES.get(u["role"] or "", {"label": "بدون نقش", "emoji": "👤"})
        my_tasks = db.list_tasks(assignee_id=u["id"])
        team.append({
            "name": u["full_name"],
            "username": u["username"],
            "role": role,
            "role_key": u["role"] or "",
            "is_admin": bool(u["is_admin"]),
            "avatar": (u["full_name"] or "؟").strip()[:1],
            "total": len(my_tasks),
            "open_tasks": sum(1 for t in my_tasks if t["status"] != "done"),
            "done_tasks": sum(1 for t in my_tasks if t["status"] == "done"),
        })

    task_rows = []
    for t in db.list_tasks()[:14]:
        task_rows.append({
            "id": t["id"],
            "title": t["title"],
            "project": t["project_title"],
            "assignee": t["assignee_name"] or "—",
            "status": TASK_STATUSES.get(t["status"], {"label": "?", "emoji": "❓"}),
            "priority": TASK_PRIORITIES.get(t["priority"], {"label": "?", "emoji": "🟡"}),
            "deadline": _deadline_meta(t["deadline"]),
            "deadline_disp": jdate.jalali_disp(t["deadline"]) or "—",
            "status_key": t["status"],
            "priority_key": t["priority"],
        })

    ideas = []
    for i in db.recent_ideas(8):
        meta = IDEA_CATEGORIES.get(i["category"] or "", {"label": "ایده", "emoji": "💡"})
        ideas.append({"category": meta, "content": i["content"]})

    activity = []
    for a in db.recent_activity(10):
        activity.append({
            "who": a["full_name"] or "سیستم",
            "action": a["action"],
            "detail": a["detail"],
            "at": a["created_at"],
            "at_disp": _fmt_at(a["created_at"]),
        })

    s = db.stats()
    open_all = [t for t in db.list_tasks() if t["status"] != "done"]
    s["overdue"] = sum(1 for t in open_all
                       if (d := days_left(t["deadline"])) is not None and d < 0)
    def _dl(t):
        return days_left(t["deadline"])
    s["due_soon"] = sum(1 for t in open_all
                        if _dl(t) is not None and 0 <= _dl(t) <= 1)
    upcoming = sorted(
        (p for p in projects if p["deadline_meta"]["days"] is not None
         and p["deadline_meta"]["days"] >= 0),
        key=lambda p: p["deadline_meta"]["days"],
    )
    return {
        "stats": s,
        "projects": projects,
        "team": team,
        "tasks": task_rows,
        "ideas": ideas,
        "activity": activity,
        "next_deadline": upcoming[0] if upcoming else None,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "updated_at_disp": _fmt_at(datetime.utcnow().isoformat(timespec="seconds")),
    }


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((BASE / "templates" / "index.html").read_text(encoding="utf-8"))


@app.head("/", include_in_schema=False)
def index_head() -> Response:
    """Accept HEAD probes (Render/UptimeRobot health checks)."""
    return Response(status_code=200, media_type="text/html")


@app.api_route("/api/health", methods=["GET", "HEAD"], response_class=JSONResponse)
def health() -> dict:
    return {"status": "ok", "service": "ye-pesare-mgmt"}


def main() -> None:
    import uvicorn
    from bot.config import DASH_PORT
    db.init_db()
    db.seed_demo()
    uvicorn.run(app, host="0.0.0.0", port=DASH_PORT)


if __name__ == "__main__":
    main()
