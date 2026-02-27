from __future__ import annotations

import re
import sqlite3
from typing import List, Tuple

from .config import DB_PATH, MAX_MEMORY_ROWS
from .runtime import now_utc_iso


def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA busy_timeout=5000;")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key)")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS kb_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            source_url TEXT,
            title TEXT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_kb_topic ON kb_docs(topic)")

    con.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts
        USING fts5(topic, title, content, url, doc_id UNINDEXED);
        """
    )
    con.commit()
    return con


def upsert_memory(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO memory(key,value,created_at) VALUES(?,?,?)",
        (key, value.strip(), now_utc_iso()),
    )
    con.commit()
    con.execute(
        "DELETE FROM memory WHERE id NOT IN (SELECT id FROM memory ORDER BY id DESC LIMIT ?)",
        (MAX_MEMORY_ROWS,),
    )
    con.commit()


def load_memory_latest_per_key(con: sqlite3.Connection) -> str:
    rows = con.execute(
        """
        SELECT m.key, m.value
        FROM memory m
        JOIN (
            SELECT key, MAX(id) AS max_id
            FROM memory
            GROUP BY key
        ) t ON m.id = t.max_id
        ORDER BY m.key ASC
        """
    ).fetchall()
    if not rows:
        return ""
    rows = [(k, v) for (k, v) in rows if k and not str(k).startswith("__")]
    return "\n".join([f"{k}: {v}" for (k, v) in rows])


def list_memory_keys(con: sqlite3.Connection) -> List[str]:
    rows = con.execute("SELECT DISTINCT key FROM memory WHERE substr(key, 1, 2) != '__' ORDER BY key ASC").fetchall()
    return [r[0] for r in rows if r and r[0]]


def get_last_topic(con: sqlite3.Connection) -> str:
    row = con.execute("SELECT value FROM memory WHERE key='__last_topic' ORDER BY id DESC LIMIT 1").fetchone()
    return (row[0] if row else "").strip()


def extract_memory(con: sqlite3.Connection, msg: str) -> list[dict]:
    stored: list[dict] = []
    text = msg.strip()

    m = re.search(
        r"(?:remember\s+)?(?:my\s+name\s+is|call\s+me|i\s+am)\s+([A-Za-z][A-Za-z\-']{1,30}(?:\s+[A-Za-z][A-Za-z\-']{1,30})?)",
        text,
        re.IGNORECASE,
    )
    if m:
        name = m.group(1).strip()
        upsert_memory(con, "user_name", name)
        stored.append({"key": "user_name", "value": name})

    m = re.search(
        r"(?:remember\s+)?(?:my\s+)?dog(?:'s|s)?\s+name\s+is\s+([A-Za-z][A-Za-z\-']{1,30})",
        text,
        re.IGNORECASE,
    )
    if m:
        dog = m.group(1).strip()
        upsert_memory(con, "dog_name", dog)
        upsert_memory(con, "dog_owner", "user")
        stored.append({"key": "dog_name", "value": dog})
        stored.append({"key": "dog_owner", "value": "user"})

    return stored


def kb_clear(con: sqlite3.Connection) -> None:
    con.execute("DELETE FROM kb_docs")
    con.execute("DELETE FROM kb_fts")
    con.commit()


def db_counts_fast() -> Tuple[int, int]:
    try:
        con = sqlite3.connect(DB_PATH, timeout=1)
        try:
            mem = con.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        except Exception:
            mem = 0
        try:
            kb = con.execute("SELECT COUNT(*) FROM kb_docs").fetchone()[0]
        except Exception:
            kb = 0
        con.close()
        return int(mem), int(kb)
    except Exception:
        return (0, 0)
