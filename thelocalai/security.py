from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import sys
from datetime import datetime, timezone
from typing import Optional

import tkinter as tk
from tkinter import messagebox

from .config import APP_TITLE, DEV_AUTH_PATH, SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT

_instance_socket: Optional[socket.socket] = None


def _pbkdf2_hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return base64.b64encode(dk).decode("ascii")


def dev_auth_is_configured() -> bool:
    return DEV_AUTH_PATH.exists()


def dev_auth_set_password(password: str) -> None:
    salt = os.urandom(16)
    payload = {
        "v": 1,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "hash_b64": _pbkdf2_hash_password(password, salt),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    DEV_AUTH_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def dev_auth_check_password(password: str) -> bool:
    try:
        payload = json.loads(DEV_AUTH_PATH.read_text(encoding="utf-8"))
        salt = base64.b64decode(payload["salt_b64"])
        expected = payload["hash_b64"]
        got = _pbkdf2_hash_password(password, salt)
        return hmac.compare_digest(expected, got)
    except Exception:
        return False


def acquire_single_instance_lock() -> None:
    global _instance_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT))
        s.listen(1)
        _instance_socket = s
    except OSError:
        try:
            s.close()
        except Exception:
            pass
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_TITLE, f"{APP_TITLE} is already running.")
        root.destroy()
        sys.exit(0)


def release_single_instance_lock() -> None:
    global _instance_socket
    try:
        if _instance_socket:
            _instance_socket.close()
    except Exception:
        pass
    _instance_socket = None
