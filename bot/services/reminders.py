"""Deadline reminders — the bot nags people by @mention inside the team group.

The bot is group-only, so DM reminders are pointless (they fail for anyone who
never pressed /start). Instead each scheduler run posts one message per member
listing their at-risk tasks, tagged. Task stages fire once each — «tomorrow»,
«today» — and while a task is overdue it re-tags the assignee once per day.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from telegram.ext import ContextTypes

from bot import config as cfg
from bot import database as db
from bot.config import TASK_STATUSES
from bot.jdate import fa_num
from bot.utils import date_disp, days_left, esc

logger = logging.getLogger(__name__)


def _age_days(ts) -> float:
    """Days elapsed since a stored UTC iso timestamp (0 on junk)."""
    try:
        return (datetime.utcnow() - datetime.fromisoformat(str(ts)[:19])).total_seconds() / 86400
    except (TypeError, ValueError):
        return 0.0


def _mention(tk) -> str | None:
    """HTML mention for a task's assignee — prefer public @username, fall
    back to an invisible tg:// link (works since the bot has seen them post)."""
    if tk["assignee_username"]:
        return "@" + tk["assignee_username"]
    if tk["assignee_tg"]:
        name = esc(tk["assignee_name"] or "کاربر")
        return f'<a href="tg://user?id={tk["assignee_tg"]}">{name}</a>'
    return None


def _stage_line(tk, kind: str) -> str:
    """One task bullet, with a stage-dependent emoji and Jalali date."""
    st = TASK_STATUSES[tk["status"]]
    when = {
        "tag:tomorrow": f"ددلاین فردا ({date_disp(tk['deadline'])})",
        "tag:today": f"ددلاین <b>امروز!</b> ({date_disp(tk['deadline'])})",
    }.get(kind, f"ددلاین <b>گذشته</b> ({date_disp(tk['deadline'])})")
    emo = {"tag:tomorrow": "⏳", "tag:today": "⚡"}.get(kind, "⛔")
    return (f"{emo} {esc(tk['title'])} — {when} · 📁 {esc(tk['project_title'])}"
            f" · {st['emoji']} {st['label']}")


async def check_deadlines(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post near/overdue-deadline nudges into the team group, tagging assignees."""
    chat_id = context.bot_data.get("group_chat_id")
    if not chat_id:
        projects = db.list_projects()
        chat_id = next((p["chat_id"] for p in projects if p["chat_id"]), None)

    all_tasks = db.list_tasks()

    # ---- project-level stages: -2 days, same day, overdue (one-shot per stage)
    for p in db.list_projects():
        d = days_left(p["deadline"])
        if d is None:
            continue
        for kind, label in ((2, "۲ روز مونده"), (0, "امروز!"), (-1, "گذشته")):
            if d != kind or db.already_reminded(p["id"], None, f"proj:{kind}"):
                continue
            msg = (
                "⏰ <b>یادآور ددلاین پروژه</b>\n"
                f"📁 {esc(p['title'])}\n"
                f"🕓 {date_disp(p['deadline'])} · ددلاین {label}"
            )
            if chat_id:
                await _send(context, chat_id, msg)
            db.mark_reminded(p["id"], None, f"proj:{kind}")

    # ---- task-level: group open tasks per assignee, tag them once each
    today = datetime.utcnow().strftime("%Y-%m-%d")
    per_user: dict[int, list] = defaultdict(list)
    unassigned: list = []
    for tk in all_tasks:
        if tk["status"] == "done":
            continue
        d = days_left(tk["deadline"])
        if d is None:
            continue
        if d == 1:
            kind = "tag:tomorrow"
        elif d == 0:
            kind = "tag:today"
        elif d < 0:
            kind = f"tag:late:{today}"  # daily nag while overdue
        else:
            continue
        if db.already_reminded(None, tk["id"], kind):
            continue
        if tk["assignee_id"] is None:
            unassigned.append((tk, kind))
        else:
            per_user[tk["assignee_id"]].append((tk, kind))
        db.mark_reminded(None, tk["id"], kind)

    for tasks in per_user.values():
        tk0 = tasks[0][0]
        mention = _mention(tk0) or esc(tk0["assignee_name"] or "کاربر")
        head = (f"📣 {mention}، {fa_num(len(tasks))} تسکت به ددلاین رسیده —"
                " لطفاً تکمیلشون کن و بزن «انجام شد» ✅"
                if len(tasks) > 1 else
                f"📣 {mention}، یک تسکت به ددلاین رسیده — لطفاً تکمیلش کن و بزن «انجام شد» ✅")
        msg = head + "\n" + "\n".join(_stage_line(t, k) for t, k in tasks)
        if chat_id:
            await _send(context, chat_id, msg)

    if unassigned:
        msg = ("🧩 <b>تسک‌های بی‌مسئول نزدیک ددلاین:</b>\n"
               + "\n".join(_stage_line(t, k) for t, k in unassigned)
               + "\nبا دکمهٔ «واگذاری» کسی رو مشخص کنید 🙏")
        if chat_id:
            await _send(context, chat_id, msg)

    # ---- cycle nags: every N days re-list each member's open tasks per project,
    # tagged — regardless of deadlines (REMIND_EVERY_DAYS env = global default,
    # per-project override via «🔁 یادآور معطل‌ها» on the project screen).
    for p in db.list_projects():
        raw = p["nag_days"] if "nag_days" in p.keys() else None
        days = cfg.NAG_DEFAULT_DAYS if raw is None else int(raw)
        if days <= 0:
            continue
        open_tks = [t for t in all_tasks
                    if t["project_id"] == p["id"] and t["status"] != "done"
                    and t["assignee_id"]]
        if not open_tks:
            continue
        anchor = db.get_reminder_sent_at(p["id"], None, "cycle") or p["created_at"]
        if _age_days(anchor) < days:
            continue
        by_u: dict[int, list] = defaultdict(list)
        for t in open_tks:
            by_u[t["assignee_id"]].append(t)
        for uid, tl in by_u.items():
            tk0 = tl[0]
            mention = _mention(tk0) or esc(tk0["assignee_name"] or "کاربر")
            bullets = []
            for t in tl:
                st = TASK_STATUSES[t["status"]]
                dl = (date_disp(t["deadline"]) if t["deadline"] else "بدون ددلاین")
                late = " · ⛔" if (dd := days_left(t["deadline"])) is not None and dd < 0 else ""
                bullets.append(f"• {esc(t['title'])} — {st['emoji']} {st['label']} · ⏰ {dl}{late}")
            head = (f"🔁 {mention}، {fa_num(len(tl))} تسک معطل در «{esc(p['title'])}» داری:"
                    if len(tl) > 1 else
                    f"🔁 {mention}، تسک «{esc(tl[0]['title'])}» در «{esc(p['title'])}» هنوز بازه:")
            if chat_id:
                await _send(context, chat_id, head + "\n" + "\n".join(bullets)
                            + "\nوضعیتش رو از «📊 وضعیت تسک» آپدیت کن 🙏")
        db.bump_reminded(p["id"], None, "cycle")

    if not chat_id and (per_user or unassigned):
        logger.warning("reminder: no group chat id — nudges not delivered")


async def _send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id, text)
    except Exception as exc:  # noqa: BLE001 — scheduler must never die on one chat
        logger.warning("reminder send failed for chat %s: %s", chat_id, exc)
