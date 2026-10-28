"""Jalali (Persian/Shamsi) calendar helpers.

Golden rule: the DATABASE always stores ISO Gregorian (YYYY-MM-DD) so day-math,
sorting and reminders stay exact; every USER-FACING string goes through here and
comes out Jalali with Persian digits (۱۴۵/۰۸/۱۶). Input parsing also speaks Jalali
(accepts Persian or Latin digits, slashes/dots/dashes, month names, ISO Gregorian).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import jdatetime

# built from codepoints — Persian digit literals are easy to mangle
FA_DIGITS = str.maketrans({str(i): chr(0x06F0 + i) for i in range(10)})
EN_DIGITS = str.maketrans({chr(0x06F0 + i): str(i) for i in range(10)})

MONTHS = {
    "فروردین": 1, "اردیبهشت": 2, "خرداد": 3, "تیر": 4, "مرداد": 5,
    "شهریور": 6, "مهر": 7, "آبان": 8, "آذر": 9, "دی": 10, "بهمن": 11,
    "اسفند": 12, "اسپند": 12,
}
# latin-ish spellings some folks type
MONTHS_LATIN = {
    "farvardin": 1, "ordibehesht": 2, "khordad": 3, "tir": 4, "mordad": 5,
    "shahrivar": 6, "mehr": 7, "aban": 8, "azar": 9, "dey": 10, "bahman": 11,
    "esfand": 12, "espand": 12,
}


def month_num(token: str) -> int | None:
    t = (token or "").strip().lower().replace("\u200c", "").replace("ي", "ی").replace("ك", "ک")
    if t in MONTHS:
        return MONTHS[t]
    if t.startswith("ابان") or t.startswith("اذر"):  # without madda
        return 8 if t.startswith("ابان") else 9
    if t.startswith("اسپند") or t.startswith("اسفند"):
        return 12
    return MONTHS_LATIN.get(t)


def to_jalali(iso: str | None) -> str | None:
    """'2026-11-07' → '1405/08/16' (Latin digits). None on junk."""
    if not iso:
        return None
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    j = jdatetime.date.fromgregorian(date=d)
    return f"{j.year:04d}/{j.month:02d}/{j.day:02d}"


def jalali_disp(iso: str | None) -> str | None:
    """User-facing Persian date: '۱۴۰۵/۰۸/۱۶'."""
    s = to_jalali(iso)
    return s.translate(FA_DIGITS) if s else None


def from_jalali(y: int, m: int, d: int) -> str | None:
    """Jalali parts → ISO Gregorian string; None if the date is invalid."""
    try:
        return jdatetime.date(int(y), int(m), int(d)).togregorian().strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def today_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def jalali_year_today() -> int:
    return jdatetime.date.today().year


_NUM_DATE = re.compile(r"^(1[34]\d\d)\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})$")


def parse(text: str) -> str | None:
    """Parse a human-typed deadline into ISO Gregorian (or None).

    Accepts: 1405/08/16 · ۱۴۰-۰۸-۱۶ · 16 آبان · 2026-11-01 (ISO Gregorian) ·
    +7 · 10 روز دیگر · فردا/پس‌فردا. The day-number form without a year targets
    the NEXT occurrence (never the past) — that's what people mean.
    """
    raw = (text or "").strip().translate(EN_DIGITS).replace("\u200c", " ")
    raw = re.sub(r"\s+", " ", raw)
    if not raw or raw in {"-", "بدون", "ندارد", "none", "no"}:
        return None

    # --- numeric Jalali: 1405/8/16
    m = _NUM_DATE.match(raw)
    if m:
        return from_jalali(*m.groups())

    # --- relative days: +7, 10 روز دیگر, ۳ روز, 7 days
    low = raw.lower()
    if "روز" in low or "day" in low or low.startswith("+"):
        num = re.search(r"(\d+)", raw)
        if num:
            if "پیش" in low or "قبل" in low or "ago" in low:  # "3 days ago" — refuse
                return None
            return (datetime.utcnow() + timedelta(days=int(num.group(1)))).strftime("%Y-%m-%d")
    if low in {"فردا", "پس فردا", "پسفردا", "tomorrow"}:
        return (datetime.utcnow() + timedelta(days=1 if low in {"فردا", "tomorrow"} else 2)).strftime("%Y-%m-%d")

    # --- Jalali with month name: "16 آبان", "آبان 16 1405", "7 Aban 1405"
    tokens = raw.split()
    month = None
    for t in tokens:
        month = month_num(t) or month
    nums = [t for t in tokens if t.isdigit()]
    day = year = None
    for t in nums:
        if len(t) == 4 and t.startswith(("13", "14")):
            year = int(t)
        elif day is None and 1 <= int(t) <= 31:
            day = int(t)
    if month and day:
        base = year or jalali_year_today()
        if year is None:  # no year given → next occurrence, never the past
            cand = from_jalali(base, month, day)
            if cand is not None and cand >= today_iso():
                return cand
            return from_jalali(base + 1, month, day)
        return from_jalali(base, month, day)

    # --- ISO / legacy Gregorian
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
