#!/usr/bin/env python3
"""Run everything: glass dashboard (always) + Telegram bot (if BOT_TOKEN set)."""
from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def run_dashboard() -> None:
    from dashboard.app import main as dash_main
    dash_main()


def run_bot() -> None:
    from bot.main import main as bot_main
    bot_main()


def main() -> None:
    from bot import database as db
    from bot.config import BOT_TOKEN, DASH_PORT

    db.init_db()
    db.seed_demo()

    procs = []
    dash = multiprocessing.Process(target=run_dashboard, daemon=True,
                                   name="glass-dashboard")
    dash.start()
    procs.append(dash)
    print(f"💎 Glass dashboard → http://0.0.0.0:{DASH_PORT}")

    if BOT_TOKEN:
        bot = multiprocessing.Process(target=run_bot, daemon=True, name="telegram-bot")
        bot.start()
        procs.append(bot)
        print("🤖 Telegram bot → polling …")
    else:
        print("⚠️  BOT_TOKEN تنظیم نشده؛ فقط داشبورد اجرا شد. "
              "بعد از ساخت .env دوباره اجرا کن.")

    try:
        for p in procs:
            p.join()
    except KeyboardInterrupt:
        print("\n👋 Bye!")
        os._exit(0)


if __name__ == "__main__":
    main()
