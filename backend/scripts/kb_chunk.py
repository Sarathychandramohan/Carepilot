"""
D:\\CarePilotAI\\backend\\scripts\\kb_chunk.py

Chunks cleaned medical documents into 400-token segments with 60-token overlap.
Uses BAAI/bge-small-en-v1.5 tokenizer to ensure accurate chunk lengths.
Assigns stable namespaced chunk IDs: kb:{doc_id}:chunk{n:04d}
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer

TOKENIZER_NAME = "BAAI/bge-small-en-v1.5"
CHUNK_SIZE = 400
OVERLAP = 60
STRIDE = CHUNK_SIZE - OVERLAP


def split_into_sections(text: str) -> list[dict[str, Any]]:
    """Splits markdown text into sections by heading (#, ##, ###)."""
    lines = text.splitlines()
    sections = []
    current_heading = None
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append({
                        "section_heading": current_heading,
                        "text": content,
                    })
            if stripped.startswith("### "):
                current_heading = stripped[4:].strip()
            elif stripped.startswith("## "):
                current_heading = stripped[3:].strip()
            elif stripped.startswith("# "):
                current_heading = stripped[2:].strip()
            else:
                current_heading = None
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({
                "section_heading": current_heading,
                "text": content,
            })

    return sections


def chunk_document(
    doc_id: str,
    doc_title: str,
    source_name: str,
    license_type: str,
    commercial_restricted: bool,
    text: str,
    snapshot_id: str = "v2",
    tokenizer: AutoTokenizer | None = None,
) -> list[dict[str, Any]]:
    """
    Chunks a single document into a list of chunk dicts with stable IDs.
    """
    if tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_NAME)

    sections = split_into_sections(text)
    chunks = []
    chunk_index = 0

    for section in sections:
        sec_heading = section["section_heading"]
        sec_text = section["text"]

        tokens = tokenizer.encode(sec_text, add_special_tokens=False)

        if len(tokens) <= CHUNK_SIZE:
            chunk_id = f"kb:{doc_id}:chunk{chunk_index:04d}"
            chunks.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "doc_title": doc_title,
                "snapshot_id": snapshot_id,
                "section_heading": sec_heading,
                "text": sec_text,
                "token_count": len(tokens),
                "char_count": len(sec_text),
                "source_name": source_name,
                "license": license_type,
                "commercial_use_restricted": commercial_restricted,
            })
            chunk_index += 1
        else:
            # Sliding window over section tokens
            for start_idx in range(0, len(tokens), STRIDE):
                end_idx = min(start_idx + CHUNK_SIZE, len(tokens))
                window_tokens = tokens[start_idx:end_idx]
                window_text = tokenizer.decode(window_tokens, skip_special_tokens=True).strip()

                if not window_text:
                    continue

                chunk_id = f"kb:{doc_id}:chunk{chunk_index:04d}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "snapshot_id": snapshot_id,
                    "section_heading": sec_heading,
                    "text": window_text,
                    "token_count": len(window_tokens),
                    "char_count": len(window_text),
                    "source_name": source_name,
                    "license": license_type,
                    "commercial_use_restricted": commercial_restricted,
                })
                chunk_index += 1

                if end_idx == len(tokens):
                    break

    return chunks
