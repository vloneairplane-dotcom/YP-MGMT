"""Lets the handler tests run on a machine without python-telegram-bot / jdatetime.

Only used when the real packages are missing; with them installed the tests use the real ones.
The stubs are intentionally tiny: the tests drive handlers with hand-made fake updates.
"""
from __future__ import annotations

import sys
import types


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)

    def __getattr__(attr):  # any other `from telegram import X` yields a dummy class
        if attr.startswith("__"):
            raise AttributeError(attr)
        dummy = type(attr, (), {"__init__": lambda self, *a, **k: None})
        setattr(mod, attr, dummy)
        return dummy

    mod.__getattr__ = __getattr__
    return mod


class InlineKeyboardButton:
    def __init__(self, text, callback_data=None, url=None, web_app=None, **_):
        self.text, self.callback_data, self.url, self.web_app = text, callback_data, url, web_app


class InlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class WebAppInfo:
    def __init__(self, url):
        self.url = url


class _Enum:
    PRIVATE = "private"
    UPLOAD_DOCUMENT = "upload_document"
    HTML = "HTML"


class _ConversationHandler:
    END = -1

    def __init__(self, *a, **k):
        pass


class _Filters:
    def __getattr__(self, _):
        return self

    def __or__(self, _):
        return self

    def __invert__(self):
        return self

    def __and__(self, _):
        return self


def install() -> None:
    try:
        import telegram  # noqa: F401
    except ModuleNotFoundError:
        tg = _module("telegram", InlineKeyboardButton=InlineKeyboardButton,
                     InlineKeyboardMarkup=InlineKeyboardMarkup, WebAppInfo=WebAppInfo)
        sys.modules["telegram"] = tg
        sys.modules["telegram.constants"] = _module(
            "telegram.constants", ChatType=_Enum, ChatAction=_Enum, ParseMode=_Enum)
        sys.modules["telegram.request"] = _module("telegram.request")
        sys.modules["telegram.warnings"] = _module(
            "telegram.warnings", PTBUserWarning=type("PTBUserWarning", (UserWarning,), {}))
        sys.modules["telegram.ext"] = _module(
            "telegram.ext", ContextTypes=types.SimpleNamespace(DEFAULT_TYPE=object),
            ConversationHandler=_ConversationHandler, filters=_Filters())
    try:
        import jdatetime  # noqa: F401
    except ModuleNotFoundError:
        fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        sys.modules["bot.jdate"] = _module(
            "bot.jdate", FA_DIGITS=fa,
            fa_num=lambda n: str(n).translate(fa),
            jalali_disp=lambda iso: iso.replace("-", "/") if iso else None,
            parse=lambda text: None)
