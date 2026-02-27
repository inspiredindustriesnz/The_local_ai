from __future__ import annotations

import re
from pathlib import Path

from .config import APP_DIR

_EXCLUDED_DIRS = {".git", "data", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv"}
_MAX_FILES = 500


def should_include_project_context(message: str) -> bool:
    low = (message or "").strip().lower()
    if not low:
        return False
    key_phrases = [
        "project structure",
        "repo structure",
        "codebase structure",
        "where is",
        "which file",
        "which module",
        "what file",
    ]
    if any(p in low for p in key_phrases):
        return True
    return bool(re.search(r"\b(file|files|folder|folders|directory|directories|repo|repository|codebase|module|modules|source)\b", low))


def _iter_project_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= _MAX_FILES:
            break
        rel_parts = path.relative_to(root).parts
        if any(part in _EXCLUDED_DIRS for part in rel_parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def build_project_context(message: str, *, root: Path = APP_DIR) -> str:
    files = _iter_project_files(root)
    if not files:
        return "Project context unavailable: no readable files found."

    rels = [str(p.relative_to(root)).replace("\\", "/") for p in files]
    top_level = sorted({p.split("/", 1)[0] for p in rels})

    tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_\-]{2,}", (message or "").lower()))
    noise = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "what",
        "where",
        "which",
        "about",
        "does",
        "know",
        "your",
        "repo",
        "files",
        "file",
        "code",
        "codebase",
        "project",
        "structure",
    }
    tokens = {t for t in tokens if t not in noise}

    scored: list[tuple[int, str]] = []
    for rel in rels:
        rel_low = rel.lower()
        score = sum(1 for t in tokens if t in rel_low)
        if score > 0:
            scored.append((score, rel))

    scored.sort(key=lambda x: (-x[0], x[1]))
    matches = [rel for _, rel in scored[:20]]

    py_files = [p for p in rels if p.endswith(".py")][:30]

    lines = [
        "PROJECT SNAPSHOT:",
        f"- Root: {root}",
        f"- Total files indexed: {len(rels)} (capped at {_MAX_FILES})",
        "",
        "TOP-LEVEL ENTRIES:",
        *[f"- {e}" for e in top_level[:25]],
        "",
        "PYTHON FILES (sample):",
        *[f"- {p}" for p in py_files],
    ]

    if matches:
        lines.extend(["", "PATHS RELEVANT TO USER QUESTION:", *[f"- {m}" for m in matches]])

    lines.append("")
    lines.append("Use only these paths as evidence for structure/file-location answers.")
    return "\n".join(lines).strip()
