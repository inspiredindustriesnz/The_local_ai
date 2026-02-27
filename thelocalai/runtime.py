from __future__ import annotations

import logging
import random
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import tkinter as tk
from tkinter import messagebox

from .config import APP_TITLE, BLOCKED_DOMAINS, LOG_PATH, MAX_PROMPT_CHARS


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def domain_of(url: str) -> str:
    try:
        netloc = (urlparse(url).netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def is_blocked_url(url: str) -> bool:
    d = domain_of(url)
    return d in BLOCKED_DOMAINS if d else False


def truncate_prompt(s: str) -> str:
    if len(s) <= MAX_PROMPT_CHARS:
        return s
    head = s[: int(MAX_PROMPT_CHARS * 0.75)]
    tail = s[-int(MAX_PROMPT_CHARS * 0.20) :]
    return head + "\n\n[...TRUNCATED...]\n\n" + tail


def cap(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + " …"


def setup_logging() -> None:
    logger = logging.getLogger("thelocalai")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)

    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(sh)


def install_exception_hooks(log: logging.Logger) -> None:
    def _show_crash_popup(title: str, body: str) -> None:
        try:
            root = tk._default_root
            if root is None:
                tmp = tk.Tk()
                tmp.withdraw()
                messagebox.showerror(title, body)
                tmp.destroy()
            else:
                messagebox.showerror(title, body)
        except Exception:
            pass

    def _sys_excepthook(exc_type, exc, tb):
        msg = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Uncaught exception:\n%s", msg)
        _show_crash_popup(f"{APP_TITLE} crashed", msg)

    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):

        def _thread_excepthook(args):
            msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            log.error("Uncaught thread exception in %s:\n%s", getattr(args, "thread", None), msg)
            _show_crash_popup(f"{APP_TITLE} thread crashed", msg)

        threading.excepthook = _thread_excepthook


def random_matrix_speed() -> int:
    r = random.random()
    if r < 0.12:
        return random.randint(26, 44)
    if r < 0.35:
        return random.randint(20, 30)
    return random.randint(10, 22)


def sentence_chunks(text: str, max_len: int = 650) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    buf: list[str] = []
    cur = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = sentence.strip()
        if not s:
            continue
        if cur + len(s) + 1 > max_len and buf:
            parts.append(" ".join(buf))
            buf = [s]
            cur = len(s)
        else:
            buf.append(s)
            cur += len(s) + 1
    if buf:
        parts.append(" ".join(buf))
    return parts
