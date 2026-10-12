"""
D:\\CarePilotAI\\backend\\scripts\\kb_clean.py

Cleans and normalizes raw text/markdown/HTML documents for the Knowledge Base.
Computes SHA-256 hash for deduplication and provenance tracking.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Optional


def normalize_text(text: str) -> str:
    """Normalize unicode and whitespace."""
    text = unicodedata.normalize("NFKD", text)
    # Remove control characters except newline and tab
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or not unicodedata.category(ch).startswith("C"))
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace on each line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


def remove_boilerplate(text: str) -> str:
    """Remove common web boilerplate patterns."""
    patterns = [
        r"(?i)last reviewed:?.*$",
        r"(?i)page last updated:?.*$",
        r"(?i)to use the sharing features on this page.*$",
        r"(?i)subscribe to.*newsletter.*$",
        r"(?i)follow us on (facebook|twitter|instagram|youtube).*$",
        r"(?i)was this page helpful\?.*$",
        r"(?i)an official website of the united states government.*$",
        r"(?i)all rights reserved\..*$",
    ]
    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        if any(re.search(pat, line.strip()) for pat in patterns):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()


def clean_markdown_document(raw_text: str) -> Optional[dict]:
    """
    Cleans raw markdown or text document.
    Returns a dict with cleaned text, char count, and sha256 hash.
    Returns None if document is too short (< 200 chars after cleaning).
    """
    cleaned = normalize_text(raw_text)
    cleaned = remove_boilerplate(cleaned)

    if len(cleaned) < 200:
        return None

    sha256_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

    return {
        "text": cleaned,
        "char_count": len(cleaned),
        "sha256": sha256_hash,
    }
