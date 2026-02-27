from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass

from .config import ABOUT_TEXT, WEB_ENABLED, WEB_MAX_PAGES_TO_READ, WEB_MAX_RESULTS
from .db import extract_memory, get_last_topic, kb_clear, list_memory_keys, load_memory_latest_per_key
from .integrations import build_prompt, ddg_search, fetch_page_text_with_retries, ollama_generate
from .runtime import cap, is_blocked_url

log = logging.getLogger("thelocalai")


@dataclass
class ChatResult:
    assistant: str
    stored: list[dict]


def generate_reply(con: sqlite3.Connection, model: str, message: str, *, num_predict: int, temperature: float) -> ChatResult:
    stored = extract_memory(con, message)
    memory = load_memory_latest_per_key(con)
    last_topic = get_last_topic(con)

    cmd = message.strip().lower()
    if cmd == "about":
        return ChatResult(ABOUT_TEXT, stored)
    if cmd in {"memorytopics", "memory topics", "memory_topics"}:
        keys = list_memory_keys(con)
        text = "No personal memory stored yet." if not keys else "Stored memory keys:\n- " + "\n- ".join(keys)
        return ChatResult(text, stored)
    if cmd == "kbclear":
        kb_clear(con)
        return ChatResult("Knowledge base cleared.", stored)

    m = re.search(r"\b(learn|web|kb)\s*:\s*(.+)$", message, re.IGNORECASE)
    c = (m.group(1).lower().strip() if m else "")
    arg = (m.group(2).strip() if m else "")

    web_used = c in {"learn", "web"}
    web_context = ""

    if c in {"learn", "web"}:
        if not WEB_ENABLED:
            return ChatResult("Web mode is disabled.", stored)
        if not arg:
            return ChatResult(f"Usage: {c}: <query/topic>", stored)

        results = ddg_search(arg, max_results=WEB_MAX_RESULTS)
        if not results:
            return ChatResult("No search results found.", stored)

        pages = []
        for r in results:
            if len(pages) >= WEB_MAX_PAGES_TO_READ:
                break
            url = r.get("url", "")
            if not url:
                continue
            if is_blocked_url(url):
                snip = (r.get("snippet") or "").strip()
                if snip:
                    pages.append({"url": url, "title": r.get("title", ""), "text": f"(Snippet) {snip}"})
                continue
            try:
                title, text = fetch_page_text_with_retries(url)
                pages.append({"url": url, "title": title or r.get("title", ""), "text": text})
            except Exception:
                snip = (r.get("snippet") or "").strip()
                if snip:
                    pages.append({"url": url, "title": r.get("title", ""), "text": f"(Snippet) {snip}"})

        lines = [f"QUERY/TOPIC: {arg}", "", "SOURCES:"]
        for i, p in enumerate(pages, 1):
            lines.append(f"[{i}] {p.get('title', '')}")
            lines.append(f"URL: {p.get('url', '')}")
            lines.append((p.get("text", "") or "")[:3500])
            lines.append("")
        web_context = "\n".join(lines).strip()

    prompt = build_prompt(
        cap(memory, 6000),
        message,
        kb_material="",
        web_context=cap(web_context, 18000),
        last_topic=last_topic,
        web_used=web_used,
    )
    response = ollama_generate(model, prompt, num_predict=num_predict, temperature=temperature)
    return ChatResult(response, stored)
