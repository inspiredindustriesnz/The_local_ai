from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Tuple

import requests

from .config import (
    ABOUT_TEXT,
    APP_TITLE,
    DEFAULT_MODEL,
    OLLAMA_CONNECT_TIMEOUT,
    OLLAMA_GEN_URL,
    OLLAMA_READ_TIMEOUT,
    OLLAMA_RETRIES,
    OLLAMA_TAGS_URL,
    WEB_FETCH_RETRIES,
    WEB_MAX_CHARS_PER_PAGE,
    WEB_MAX_RESULTS,
    WEB_TIMEOUT,
)
from .runtime import domain_of, is_blocked_url, truncate_prompt

log = logging.getLogger("thelocalai")

try:
    from ddgs import DDGS  # type: ignore
except Exception:
    DDGS = None  # type: ignore

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # type: ignore


def ddg_search(query: str, max_results: int = WEB_MAX_RESULTS) -> List[Dict[str, str]]:
    if DDGS is None:
        log.warning("ddgs not installed; web search disabled for this run.")
        return []
    results: List[Dict[str, str]] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = (r.get("title") or "").strip()
                url = (r.get("href") or "").strip()
                body = (r.get("body") or "").strip()
                if url:
                    results.append({"title": title, "url": url, "snippet": body})
    except Exception as e:
        log.warning("ddg_search failed: %s", e)
        return []
    return results


def fetch_page_text(url: str, timeout: int = WEB_TIMEOUT) -> Tuple[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    html = r.text

    if BeautifulSoup is None:
        title = ""
        mt = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if mt:
            title = re.sub(r"\s+", " ", re.sub(r"<.*?>", "", mt.group(1))).strip()
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    else:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

    if len(text) > WEB_MAX_CHARS_PER_PAGE:
        text = text[:WEB_MAX_CHARS_PER_PAGE] + " …"
    return title, text


def fetch_page_text_with_retries(url: str) -> Tuple[str, str]:
    if is_blocked_url(url):
        raise RuntimeError(f"Blocked domain (skipped): {domain_of(url)}")
    last: Optional[Exception] = None
    for attempt in range(WEB_FETCH_RETRIES + 1):
        try:
            return fetch_page_text(url)
        except Exception as e:
            last = e
            time.sleep(0.6 * (2**attempt))
    raise RuntimeError(f"Failed to fetch page after retries: {url} | last error: {last}")


def ollama_list_models(timeout: int = 5) -> List[str]:
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return sorted(set(models))
    except Exception as e:
        log.warning("ollama_list_models failed: %s", e)
        return []


def ollama_generate(model: str, prompt: str, *, num_predict: int, temperature: float) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": int(num_predict), "temperature": float(temperature)},
    }

    last: Optional[Exception] = None
    for attempt in range(OLLAMA_RETRIES + 1):
        try:
            r = requests.post(
                OLLAMA_GEN_URL,
                json=payload,
                timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT),
            )
            if r.status_code != 200:
                try:
                    err = r.json().get("error") or r.text
                except Exception:
                    err = r.text
                raise RuntimeError(f"Ollama error ({model}) {r.status_code}: {str(err)[:400]}")
            return (r.json().get("response") or "").strip()
        except Exception as e:
            last = e
            time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"Ollama failed after retries: {last}")


def build_prompt(
    memory: str,
    user_msg: str,
    kb_material: str = "",
    web_context: str = "",
    project_context: str = "",
    last_topic: str = "",
    web_used: bool = False,
) -> str:
    parts = [
        "SYSTEM:",
        f"You are {APP_TITLE}, a local desktop app using the user's selected local Ollama model.",
        "",
        "IMPORTANT APP CAPABILITIES:",
        "- The APP (not the model) can optionally SPEAK assistant responses when the user enables Voice (TTS).",
        "- Do not claim web browsing unless WEB CONTEXT is present.",
        "",
        "STRICT TRUTH RULES (IMPORTANT):",
        "- If asked who trained the model, the dataset size, the disk size of training data, or the training cutoff date: say you DO NOT know unless the user provides it.",
        "- Never claim you are trained by Google/OpenAI/etc unless the user provided that fact.",
        "- Do not invent URLs, sources, reports, or 'local news'.",
        "- If PROJECT CONTEXT is provided, use it for file/structure questions and do not invent filenames.",
        "",
        f"WEB_USED: {'YES' if web_used else 'NO'}",
        "",
        "ABOUT (ground truth):",
        ABOUT_TEXT,
        "",
    ]

    if last_topic:
        parts.append(f"SESSION last_topic: {last_topic}\n")
    if memory.strip():
        parts.append("MEMORY:\n" + memory + "\n")
    if kb_material.strip():
        parts.append("KB:\n" + kb_material + "\n")
    if web_context.strip():
        parts.append("WEB CONTEXT:\n" + web_context + "\n")
    if project_context.strip():
        parts.append("PROJECT CONTEXT:\n" + project_context + "\n")

    parts.append("USER:\n" + user_msg.strip())
    parts.append("\nASSISTANT:")
    return truncate_prompt("\n".join(parts))
