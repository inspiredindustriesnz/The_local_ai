from __future__ import annotations

from pathlib import Path

APP_TITLE = "TheLocalAI"

OLLAMA_BASE = "http://127.0.0.1:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE}/api/tags"
OLLAMA_GEN_URL = f"{OLLAMA_BASE}/api/generate"

DEFAULT_MODEL = "gemma3:4b"

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "memory.db"
LOG_PATH = DATA_DIR / "thelocalai.log"

MAX_USER_CHARS = 4000
MAX_MEMORY_ROWS = 2000

OLLAMA_CONNECT_TIMEOUT = 5
OLLAMA_READ_TIMEOUT = 240

DEFAULT_NUM_PREDICT = 320
DEFAULT_TEMPERATURE = 0.25
MAX_PROMPT_CHARS = 52000

WEB_ENABLED = True
WEB_TIMEOUT = 20
WEB_MAX_RESULTS = 10
WEB_MAX_PAGES_TO_READ = 5
WEB_MAX_CHARS_PER_PAGE = 14000

BLOCKED_DOMAINS = {
    "researchgate.net",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "medium.com",
}

OLLAMA_RETRIES = 2
WEB_FETCH_RETRIES = 1

SINGLE_INSTANCE_HOST = "127.0.0.1"
SINGLE_INSTANCE_PORT = 48231

GEN_WATCHDOG_SECONDS = max(OLLAMA_READ_TIMEOUT + 20, 300)

VOSK_MODEL_DIR = DATA_DIR / "vosk-model-en-us-0.22"

DEV_AUTH_PATH = DATA_DIR / "dev_auth.json"
DEV_SESSION_MINUTES = 30

THEME = {
    "bg": "#000000",
    "panel_bg": "#050505",
    "border": "#083808",
    "green": "#00ff66",
    "green_dim": "#00aa44",
    "green_dim2": "#007733",
    "error": "#ff3355",
}

ABOUT_TEXT = f"""\
I’m {APP_TITLE}, a local desktop app on your machine.

What I can do:
- Chat using your selected local Ollama model (currently: {DEFAULT_MODEL} by default).
- Store simple “facts” you explicitly tell me (in a local SQLite DB).
- Optional web research only when you use commands like `web:` or `learn:`.

What “model knowledge” means:
- The language model (e.g., gemma3:4b) has patterns/skills from its training done by its original authors.
- Inside this app, I do NOT have direct access to the model’s original training dataset, size, disk footprint, or exact cutoff date unless YOU provide that info.
- My reliable knowledge comes from:
  1) The model’s built-in behavior (what it can generate),
  2) Your local memory + local knowledge base (KB),
  3) Web results that I fetch only when you explicitly request it.
"""
